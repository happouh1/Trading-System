"""Offline Case-3 full-long reducing-exit validation harness."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from trading_system.serialization import canonical_hash, deterministic_id
from trading_system.webull.case1 import Case1AmbiguousError, Case1IncompleteError
from trading_system.webull.contracts import WebullResponse, WebullSide
from trading_system.webull.exit_contracts import WebullExitOrder
from trading_system.webull.mapping import client_order_id
from trading_system.webull.security import redact
from trading_system.webull.service import WebullSandboxService
from trading_system.webull.smoke import (
    SmokeCapture,
    SmokeCase,
    SmokeConfig,
    SmokeEvidence,
    SmokeOperationEvent,
    SmokeOperationEventType,
    build_smoke_capture,
)
from trading_system.webull.smoke_registry import WebullSmokeRegistry


class Case3Transport(Protocol):
    def positions(self, account_id: str) -> WebullResponse: ...

    def open_orders(self, account_id: str) -> WebullResponse: ...

    def order_detail(self, account_id: str, client_order_id: str) -> WebullResponse: ...

    def place_exact_exit(
        self, account_id: str, order: WebullExitOrder
    ) -> WebullResponse: ...


@dataclass(frozen=True, slots=True)
class Case3Result:
    capture: SmokeCapture
    client_order_id: str


def case3_client_order_id(session_id: str) -> str:
    return client_order_id(f"{session_id}:phase3d5:case3:exit:AAPL")


def exact_case3_order(session_id: str) -> WebullExitOrder:
    return WebullExitOrder(
        case3_client_order_id(session_id),
        "AAPL",
        WebullSide.SELL,
        1,
        "MARKET",
        "DAY",
        None,
        False,
        "CORE",
    )


def validate_case3_order(session_id: str, order: WebullExitOrder) -> None:
    if order != exact_case3_order(session_id):
        raise ValueError("order does not match the exact approved Case-3 fixture")


def _detail_item(response: WebullResponse, client_id: str) -> Mapping[str, object]:
    candidates: object = response.payload.get("orders")
    if candidates is None:
        single = response.payload.get("order")
        candidates = (single,) if isinstance(single, Mapping) else ()
    if not isinstance(candidates, (tuple, list)):
        raise Case1IncompleteError("Case-3 detail response has no orders array")
    matches = tuple(
        item
        for item in candidates
        if isinstance(item, Mapping) and item.get("client_order_id") == client_id
    )
    if len(matches) != 1:
        raise Case1IncompleteError("Case-3 detail did not resolve exactly one order")
    return matches[0]


def _detail_matches(response: WebullResponse, expected: WebullExitOrder) -> bool:
    item = _detail_item(response, expected.client_order_id)
    quantity = item.get("total_quantity", item.get("quantity"))
    filled = item.get("filled_quantity", item.get("cumulative_filled_quantity"))
    return (
        item.get("symbol") == expected.symbol
        and item.get("side") == expected.side.value
        and str(quantity) == str(expected.quantity)
        and str(filled) == str(expected.quantity)
        and item.get("order_type") == expected.order_type
        and item.get("time_in_force") == expected.time_in_force
        and item.get("support_trading_session") == expected.support_trading_session
    )


class Case3Runner:
    """Exercise Case 3 only through a supplied test transport."""

    def __init__(
        self,
        session_id: str,
        service: WebullSandboxService,
        transport: Case3Transport,
        registry: WebullSmokeRegistry,
        config: SmokeConfig,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.session_id = session_id
        self.service = service
        self.transport = transport
        self.registry = registry
        self.config = config
        self.clock = clock
        self.case = SmokeCase.LONG_REDUCING_EXIT
        self.order = exact_case3_order(session_id)
        validate_case3_order(session_id, self.order)
        self.request_hash = canonical_hash(self.order)

    def _event(
        self, event_type: SmokeOperationEventType, detail: Mapping[str, object]
    ) -> None:
        occurred_at = self.clock()
        safe = redact(detail)
        if not isinstance(safe, Mapping):
            raise TypeError("redacted Case-3 detail must be a mapping")
        identity = (
            self.session_id,
            self.case.value,
            "EXIT_PLACE",
            event_type.value,
            self.order.client_order_id,
            occurred_at,
            self.request_hash,
            safe,
        )
        self.registry.insert_operation_event(SmokeOperationEvent(
            deterministic_id("webull_smoke_operation_event", identity),
            self.session_id,
            self.case,
            "EXIT_PLACE",
            event_type,
            self.order.client_order_id,
            occurred_at,
            self.request_hash,
            safe,
        ))

    def _evidence(
        self,
        operation: str,
        response: WebullResponse,
        request: Mapping[str, object] | None = None,
    ) -> SmokeEvidence:
        safe = redact(dict(response.payload))
        if not isinstance(safe, Mapping):
            raise TypeError("redacted Case-3 response must be a mapping")
        return SmokeEvidence(
            operation,
            self.clock(),
            self.order.client_order_id,
            self.order.sdk_payload() if request is None else request,
            {"status_code": response.status_code, "payload": safe},
            {"semantic_review_required": True},
        )

    def run(self) -> Case3Result:
        if self.registry.has_call_boundary(self.session_id, self.case):
            raise Case1IncompleteError("Case 3 already crossed a write boundary")
        self.service.verify_account(self.clock(), account_class="INDIVIDUAL_MARGIN")
        account_id = self.service._require_verified()

        position_before = self.transport.positions(account_id)
        open_before = self.transport.open_orders(account_id)
        self.registry.insert_envelope(
            self.session_id,
            "SMOKE_CASE3_POSITION_BEFORE",
            self.clock(),
            position_before,
        )
        self.registry.insert_envelope(
            self.session_id,
            "SMOKE_CASE3_OPEN_ORDERS_BEFORE",
            self.clock(),
            open_before,
        )
        if not 200 <= position_before.status_code < 300:
            raise Case1IncompleteError("Case-3 position preflight failed")
        if WebullSandboxService._positions(position_before, account_id) != {"AAPL": 1}:
            raise Case1IncompleteError("Case 3 requires exactly one AAPL long share")
        if not 200 <= open_before.status_code < 300:
            raise Case1IncompleteError("Case-3 open-order preflight failed")
        if WebullSandboxService._open_orders(open_before, account_id):
            raise Case1IncompleteError("Case 3 requires no working orders")
        evidence = [self._evidence("POSITION_BEFORE", position_before, {})]

        self._event(SmokeOperationEventType.PREPARED, {"request": self.order})
        self._event(SmokeOperationEventType.CALL_STARTED, {"request": self.order})
        try:
            placed = self.transport.place_exact_exit(account_id, self.order)
        except Exception as error:
            self._event(SmokeOperationEventType.EXCEPTION, {
                "error_type": type(error).__name__
            })
            try:
                recovered = self.transport.order_detail(
                    account_id, self.order.client_order_id
                )
                recovery: Mapping[str, object] = {
                    "status_code": recovered.status_code,
                    "response": dict(recovered.payload),
                }
            except Exception as recovery_error:
                recovery = {"error_type": type(recovery_error).__name__}
            self._event(SmokeOperationEventType.RECOVERED, recovery)
            raise Case1AmbiguousError(
                "Case-3 exit placement was ambiguous; queried once and halted"
            ) from error
        self._event(SmokeOperationEventType.RESPONSE, {
            "status_code": placed.status_code,
            "response": dict(placed.payload),
        })
        if not 200 <= placed.status_code < 300:
            raise Case1IncompleteError("Case-3 exit placement was unsuccessful")
        evidence.append(self._evidence("EXIT_PLACE", placed))

        detail = self.transport.order_detail(account_id, self.order.client_order_id)
        self.registry.insert_envelope(
            self.session_id, "SMOKE_CASE3_EXIT_DETAIL", self.clock(), detail, self.order
        )
        if not 200 <= detail.status_code < 300 or not _detail_matches(detail, self.order):
            raise Case1IncompleteError("Case-3 exit detail identity or fill is invalid")
        evidence.append(self._evidence("EXIT_DETAIL", detail))

        position_flat = self.transport.positions(account_id)
        self.registry.insert_envelope(
            self.session_id,
            "SMOKE_CASE3_POSITION_FLAT",
            self.clock(),
            position_flat,
        )
        if not 200 <= position_flat.status_code < 300:
            raise Case1IncompleteError("Case-3 flat-position reconciliation failed")
        if WebullSandboxService._positions(position_flat, account_id):
            raise Case1IncompleteError("Case 3 requires an exactly flat final position")
        evidence.append(self._evidence("POSITION_FLAT", position_flat, {}))

        capture = build_smoke_capture(
            self.session_id, self.case, self.clock(), tuple(evidence), self.config
        )
        self.registry.insert_capture(capture)
        return Case3Result(capture, self.order.client_order_id)
