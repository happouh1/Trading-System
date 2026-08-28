"""Read-only Case-7 restart and existing-protection reconciliation."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from trading_system.domain import Direction
from trading_system.webull.case1 import Case1IncompleteError
from trading_system.webull.contracts import WebullResponse, WebullSide
from trading_system.webull.exit_contracts import (
    ManagedPosition,
    PositionLifecycleState,
    ProtectiveStopVersion,
    WebullExitOrder,
)
from trading_system.webull.exit_registry import WebullExitRegistry
from trading_system.webull.security import redact
from trading_system.webull.service import WebullSandboxService
from trading_system.webull.smoke import (
    SmokeCapture,
    SmokeCase,
    SmokeConfig,
    SmokeEvidence,
    build_smoke_capture,
)
from trading_system.webull.smoke_registry import WebullSmokeRegistry


@dataclass(frozen=True, slots=True)
class Case7Result:
    capture: SmokeCapture
    managed_position_id: str
    protective_client_order_id: str


def _restart_order(
    position: ManagedPosition, stop: ProtectiveStopVersion
) -> WebullExitOrder:
    side = WebullSide.SELL if position.direction is Direction.LONG else WebullSide.BUY
    return WebullExitOrder(
        stop.client_order_id,
        position.symbol,
        side,
        stop.quantity,
        "STOP_LOSS",
        "GTC",
        stop.raw_stop,
        False,
        "CORE",
    )


def _detail_item(response: WebullResponse, client_id: str) -> Mapping[str, object]:
    candidates: object = response.payload.get("orders")
    if candidates is None:
        single = response.payload.get("order")
        candidates = (single,) if isinstance(single, Mapping) else ()
    if not isinstance(candidates, (tuple, list)):
        raise Case1IncompleteError("Case-7 stop detail response has no orders array")
    matches = tuple(
        item
        for item in candidates
        if isinstance(item, Mapping) and item.get("client_order_id") == client_id
    )
    if len(matches) != 1:
        raise Case1IncompleteError("Case-7 stop detail did not resolve exactly one order")
    return matches[0]


def _stop_matches(response: WebullResponse, expected: WebullExitOrder) -> bool:
    if not 200 <= response.status_code < 300:
        return False
    item = _detail_item(response, expected.client_order_id)
    quantity = item.get("total_quantity", item.get("quantity"))
    filled = item.get("filled_quantity", item.get("cumulative_filled_quantity", 0))
    status = item.get("status")
    return (
        item.get("symbol") == expected.symbol
        and item.get("side") == expected.side.value
        and str(quantity) == str(expected.quantity)
        and str(filled) == "0"
        and item.get("order_type") == expected.order_type
        and item.get("time_in_force") == expected.time_in_force
        and item.get("support_trading_session") == expected.support_trading_session
        and str(item.get("stop_price")) == format(expected.stop_price, "f")
        and isinstance(status, str)
        and bool(status)
    )


class Case7Recovery:
    """Load durable ownership, then reconcile with read-only broker evidence."""

    def __init__(
        self,
        session_id: str,
        managed_position_id: str,
        service: WebullSandboxService,
        exit_registry: WebullExitRegistry,
        smoke_registry: WebullSmokeRegistry,
        config: SmokeConfig,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.session_id = session_id
        self.managed_position_id = managed_position_id
        self.service = service
        self.exit_registry = exit_registry
        self.smoke_registry = smoke_registry
        self.config = config
        self.clock = clock

    @staticmethod
    def _evidence(
        operation: str,
        occurred_at: datetime,
        client_order_id: str,
        request: Mapping[str, object],
        response: Mapping[str, object],
        observation: Mapping[str, object],
    ) -> SmokeEvidence:
        safe_response = redact(response)
        safe_observation = redact(observation)
        if not isinstance(safe_response, Mapping) or not isinstance(
            safe_observation, Mapping
        ):
            raise TypeError("redacted Case-7 evidence must be mappings")
        return SmokeEvidence(
            operation,
            occurred_at,
            client_order_id,
            request,
            safe_response,
            safe_observation,
        )

    def run(self) -> Case7Result:
        position = self.exit_registry.managed_position(self.managed_position_id)
        event = self.exit_registry.latest_position_event(self.managed_position_id)
        stop = self.exit_registry.latest_stop(self.managed_position_id)
        if position.session_id != self.session_id:
            raise Case1IncompleteError("Case-7 position belongs to another session")
        if (
            position.symbol != "AAPL"
            or position.direction is not Direction.LONG
            or position.filled_quantity != 1
            or position.remaining_quantity != 1
        ):
            raise Case1IncompleteError("Case 7 requires its exact managed AAPL long fixture")
        if (
            event is None
            or event.session_id != self.session_id
            or event.state is not PositionLifecycleState.PROTECTED
            or event.remaining_quantity != 1
        ):
            raise Case1IncompleteError("Case 7 requires durable PROTECTED state")
        if (
            stop is None
            or stop.session_id != self.session_id
            or stop.managed_position_id != position.managed_position_id
            or stop.quantity != 1
            or stop.adjustment_factor != 1
            or stop.raw_stop != stop.adjusted_stop
        ):
            raise Case1IncompleteError("Case 7 requires one exact persisted protective stop")
        if self.exit_registry.unresolved_actions(self.session_id):
            raise Case1IncompleteError("Case 7 requires no unresolved broker action")
        order = _restart_order(position, stop)
        loaded_at = self.clock()
        state_load = self._evidence(
            "RESTART_STATE_LOAD",
            loaded_at,
            stop.client_order_id,
            {"managed_position_id": position.managed_position_id},
            {
                "state": event.state.value,
                "remaining_quantity": event.remaining_quantity,
                "stop_request_hash": stop.request_hash,
            },
            {"loaded_from_persistence": True, "broker_write_performed": False},
        )

        self.service.verify_account(self.clock(), account_class="INDIVIDUAL_MARGIN")
        account_id = self.service._require_verified()
        detail = self.service.transport.order_detail(account_id, stop.client_order_id)
        self.smoke_registry.insert_envelope(
            self.session_id,
            "SMOKE_CASE7_EXISTING_STOP_DETAIL",
            self.clock(),
            detail,
            order,
        )
        if not _stop_matches(detail, order):
            raise Case1IncompleteError("Case-7 existing protective stop does not match")
        stop_detail = self._evidence(
            "EXISTING_STOP_DETAIL",
            self.clock(),
            stop.client_order_id,
            order.sdk_payload(),
            {"status_code": detail.status_code, "payload": dict(detail.payload)},
            {"exact_identity_match": True, "broker_write_performed": False},
        )

        positions_response = self.service.transport.positions(account_id)
        self.smoke_registry.insert_envelope(
            self.session_id,
            "SMOKE_CASE7_POSITION_RECONCILIATION",
            self.clock(),
            positions_response,
        )
        if not 200 <= positions_response.status_code < 300:
            raise Case1IncompleteError("Case-7 position query failed")
        actual = WebullSandboxService._positions(positions_response, account_id)
        if actual != {"AAPL": 1}:
            raise Case1IncompleteError("Case-7 position reconciliation did not match")
        reconciliation = self._evidence(
            "POSITION_RECONCILIATION",
            self.clock(),
            stop.client_order_id,
            {"expected_positions": {"AAPL": 1}},
            {"status_code": positions_response.status_code, "positions": actual},
            {"matched": True, "broker_write_performed": False},
        )
        capture = build_smoke_capture(
            self.session_id,
            SmokeCase.RESTART_PROTECTION,
            self.clock(),
            (state_load, stop_detail, reconciliation),
            self.config,
        )
        self.smoke_registry.insert_capture(capture)
        return Case7Result(capture, position.managed_position_id, stop.client_order_id)
