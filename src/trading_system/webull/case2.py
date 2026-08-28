"""Offline Case-2 same-client protective-stop replacement harness."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from trading_system.serialization import canonical_hash, deterministic_id
from trading_system.webull.case1 import Case1AmbiguousError, Case1IncompleteError
from trading_system.webull.contracts import WebullOpenOrder, WebullResponse, WebullSide
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

INITIAL_STOP = Decimal("1.00")
REPLACEMENT_STOP = Decimal("1.01")


class Case2Transport(Protocol):
    def order_detail(self, account_id: str, client_order_id: str) -> WebullResponse: ...

    def replace_exact_stop(
        self, account_id: str, order: WebullExitOrder
    ) -> WebullResponse: ...


@dataclass(frozen=True, slots=True)
class Case2Result:
    capture: SmokeCapture
    client_order_id: str


def case2_client_order_id(session_id: str) -> str:
    return client_order_id(f"{session_id}:phase3d5:case2:stop:AAPL")


def exact_case2_order(session_id: str, stop_price: Decimal) -> WebullExitOrder:
    if stop_price not in {INITIAL_STOP, REPLACEMENT_STOP}:
        raise ValueError("Case-2 stop must match an approved validation price")
    return WebullExitOrder(
        case2_client_order_id(session_id),
        "AAPL",
        WebullSide.SELL,
        1,
        "STOP_LOSS",
        "GTC",
        stop_price,
        False,
        "CORE",
    )


def validate_case2_replacement(
    session_id: str, before: WebullExitOrder, after: WebullExitOrder
) -> None:
    expected_before = exact_case2_order(session_id, INITIAL_STOP)
    expected_after = exact_case2_order(session_id, REPLACEMENT_STOP)
    if before != expected_before or after != expected_after:
        raise ValueError("orders do not match the exact approved Case-2 replacement")
    if after.client_order_id != before.client_order_id:
        raise ValueError("Case-2 replacement must retain client identity")
    if after.stop_price is None or before.stop_price is None:
        raise ValueError("Case-2 replacement requires stop prices")
    if after.stop_price - before.stop_price != Decimal("0.01"):
        raise ValueError("Case-2 replacement must advance exactly one verified tick")


def _detail_item(response: WebullResponse, client_id: str) -> Mapping[str, object]:
    candidates: object = response.payload.get("orders")
    if candidates is None:
        single = response.payload.get("order")
        candidates = (single,) if isinstance(single, Mapping) else ()
    if not isinstance(candidates, (tuple, list)):
        raise Case1IncompleteError("Case-2 detail response has no orders array")
    matches = tuple(
        item for item in candidates
        if isinstance(item, Mapping) and item.get("client_order_id") == client_id
    )
    if len(matches) != 1:
        raise Case1IncompleteError("Case-2 detail did not resolve exactly one order")
    return matches[0]


def _detail_matches(response: WebullResponse, expected: WebullExitOrder) -> bool:
    item = _detail_item(response, expected.client_order_id)
    stop_price = item.get("stop_price")
    quantity = item.get("total_quantity", item.get("quantity"))
    return (
        item.get("symbol") == expected.symbol
        and item.get("side") == expected.side.value
        and str(quantity) == str(expected.quantity)
        and item.get("order_type") == expected.order_type
        and item.get("time_in_force") == expected.time_in_force
        and item.get("support_trading_session") == expected.support_trading_session
        and str(stop_price) == format(expected.stop_price, "f")
    )


def _open_matches(item: WebullOpenOrder, expected: WebullExitOrder) -> bool:
    return (
        item.client_order_id == expected.client_order_id
        and item.symbol == expected.symbol
        and item.side is expected.side
        and item.quantity == expected.quantity
        and item.filled_quantity == 0
        and item.order_type == expected.order_type
        and item.time_in_force == expected.time_in_force
        and item.support_trading_session == expected.support_trading_session
        and item.stop_price == expected.stop_price
    )


class Case2Runner:
    """Run only against a supplied transport; no official transport is exposed."""

    def __init__(
        self,
        session_id: str,
        service: WebullSandboxService,
        transport: Case2Transport,
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
        self.case = SmokeCase.LONG_STOP_REPLACE
        self.before = exact_case2_order(session_id, INITIAL_STOP)
        self.after = exact_case2_order(session_id, REPLACEMENT_STOP)
        validate_case2_replacement(session_id, self.before, self.after)
        self.request_hash = canonical_hash(self.after)

    def _event(
        self, event_type: SmokeOperationEventType, detail: Mapping[str, object]
    ) -> None:
        occurred_at = self.clock()
        safe = redact(detail)
        if not isinstance(safe, Mapping):
            raise TypeError("redacted Case-2 detail must be a mapping")
        identity = (
            self.session_id,
            self.case.value,
            "STOP_REPLACE",
            event_type.value,
            self.after.client_order_id,
            occurred_at,
            self.request_hash,
            safe,
        )
        self.registry.insert_operation_event(SmokeOperationEvent(
            deterministic_id("webull_smoke_operation_event", identity),
            self.session_id,
            self.case,
            "STOP_REPLACE",
            event_type,
            self.after.client_order_id,
            occurred_at,
            self.request_hash,
            safe,
        ))

    def _evidence(
        self, operation: str, order: WebullExitOrder, response: WebullResponse
    ) -> SmokeEvidence:
        safe = redact(dict(response.payload))
        if not isinstance(safe, Mapping):
            raise TypeError("redacted Case-2 response must be a mapping")
        return SmokeEvidence(
            operation,
            self.clock(),
            order.client_order_id,
            order.sdk_payload(),
            {"status_code": response.status_code, "payload": safe},
            {"semantic_review_required": True},
        )

    def run(self) -> Case2Result:
        if self.registry.has_call_boundary(self.session_id, self.case):
            raise Case1IncompleteError("Case 2 already crossed a write boundary")
        self.service.verify_account(self.clock(), account_class="INDIVIDUAL_MARGIN")
        positions = self.service.sandbox_positions(self.clock())
        open_orders = self.service.sandbox_open_orders(self.clock())
        if positions != (("AAPL", 1),):
            raise Case1IncompleteError("Case 2 requires exactly one AAPL long share")
        if len(open_orders) != 1 or not _open_matches(open_orders[0], self.before):
            raise Case1IncompleteError("Case 2 requires its exact initial stop to be open")
        account_id = self.service._require_verified()
        before = self.transport.order_detail(account_id, self.before.client_order_id)
        self.registry.insert_envelope(
            self.session_id, "SMOKE_CASE2_STOP_DETAIL_BEFORE", self.clock(),
            before, self.before,
        )
        if not 200 <= before.status_code < 300 or not _detail_matches(before, self.before):
            raise Case1IncompleteError("Case-2 detail-before identity is invalid")
        evidence = [self._evidence("STOP_DETAIL_BEFORE", self.before, before)]
        self._event(SmokeOperationEventType.PREPARED, {"request": self.after})
        self._event(SmokeOperationEventType.CALL_STARTED, {"request": self.after})
        try:
            replaced = self.transport.replace_exact_stop(account_id, self.after)
        except Exception as error:
            self._event(
                SmokeOperationEventType.EXCEPTION,
                {"error_type": type(error).__name__},
            )
            try:
                recovered = self.transport.order_detail(
                    account_id, self.after.client_order_id
                )
                recovery: Mapping[str, object] = {
                    "status_code": recovered.status_code,
                    "response": dict(recovered.payload),
                }
            except Exception as recovery_error:
                recovery = {"error_type": type(recovery_error).__name__}
            self._event(SmokeOperationEventType.RECOVERED, recovery)
            raise Case1AmbiguousError(
                "Case-2 replacement was ambiguous; queried once and halted"
            ) from error
        self._event(
            SmokeOperationEventType.RESPONSE,
            {"status_code": replaced.status_code, "response": dict(replaced.payload)},
        )
        if not 200 <= replaced.status_code < 300:
            raise Case1IncompleteError("Case-2 replacement response was unsuccessful")
        evidence.append(self._evidence("STOP_REPLACE", self.after, replaced))
        after = self.transport.order_detail(account_id, self.after.client_order_id)
        self.registry.insert_envelope(
            self.session_id, "SMOKE_CASE2_STOP_DETAIL_AFTER", self.clock(), after, self.after
        )
        if not 200 <= after.status_code < 300 or not _detail_matches(after, self.after):
            raise Case1IncompleteError("Case-2 detail-after identity is invalid")
        evidence.append(self._evidence("STOP_DETAIL_AFTER", self.after, after))
        capture = build_smoke_capture(
            self.session_id, self.case, self.clock(), tuple(evidence), self.config
        )
        self.registry.insert_capture(capture)
        return Case2Result(capture, self.after.client_order_id)
