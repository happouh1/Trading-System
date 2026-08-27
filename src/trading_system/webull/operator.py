"""Sandbox-only operator reads and exact Case-1 cancellation recovery."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from trading_system.serialization import canonical_hash, deterministic_id
from trading_system.webull.case1 import Case1AmbiguousError, Case1IncompleteError
from trading_system.webull.case1_transport import case1_client_order_id
from trading_system.webull.contracts import WebullOpenOrder, WebullResponse
from trading_system.webull.exit_contracts import WebullExitOrder
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

OPERATION = "OPERATOR_CANCEL_EXACT_CASE1_STOP"


class Case1CancelTransport(Protocol):
    def order_detail(self, account_id: str, client_order_id: str) -> WebullResponse: ...

    def cancel_exact_stop(
        self, account_id: str, order: WebullExitOrder
    ) -> WebullResponse: ...


@dataclass(frozen=True, slots=True)
class Case1CancelResult:
    client_order_id: str
    prior_status: str
    final_status: str
    cancel_requested: bool


@dataclass(frozen=True, slots=True)
class Case1StatusResult:
    client_order_id: str
    detail_status: str
    aapl_position_quantity: int
    open_order_count: int
    exact_order_open: bool
    assessment: str


def case1_cancel_confirmation(session_id: str) -> str:
    return (
        f"CANCEL-{case1_client_order_id(session_id)}-AAPL-SELL-1-"
        "STOP_LOSS-1.00-GTC-CORE-WEBULL-SANDBOX"
    )


def case1_order_matches(item: WebullOpenOrder, order: WebullExitOrder) -> bool:
    return (
        item.client_order_id == order.client_order_id
        and item.symbol == order.symbol
        and item.side is order.side
        and item.quantity == order.quantity
        and item.filled_quantity == 0
        and item.order_type == order.order_type
        and item.time_in_force == order.time_in_force
        and item.support_trading_session == order.support_trading_session
        and item.stop_price == order.stop_price
    )


def _assessment(
    detail_status: str, position_quantity: int, exact_order_open: bool
) -> str:
    if exact_order_open:
        return "ORDER_STILL_OPEN"
    if detail_status in {"CANCELED", "CANCELLED"}:
        return (
            "CANCEL_CONFIRMED_POSITION_REMAINS"
            if position_quantity > 0
            else "CANCEL_CONFIRMED_POSITION_ABSENT"
        )
    if detail_status in {"FILLED", "EXECUTED"} and position_quantity == 0:
        return "ORDER_FILLED_POSITION_FLAT"
    return "MANUAL_REVIEW_REQUIRED"


def _detail_status(response: WebullResponse, client_order_id: str) -> str:
    payload = response.payload
    candidates: object = payload.get("orders")
    if candidates is None:
        single = payload.get("order")
        candidates = (single,) if isinstance(single, Mapping) else ()
    if not isinstance(candidates, (tuple, list)):
        raise Case1IncompleteError("Case-1 detail response has no orders array")
    matches = tuple(
        item for item in candidates
        if isinstance(item, Mapping) and item.get("client_order_id") == client_order_id
    )
    if len(matches) != 1:
        raise Case1IncompleteError("Case-1 detail did not resolve exactly one order")
    status = matches[0].get("status")
    if not isinstance(status, str) or not status:
        raise Case1IncompleteError("Case-1 detail status is invalid")
    return status.upper()


class Case1StatusInspector:
    """Read the exact Case-1 order and current account state without writes."""

    def __init__(
        self,
        session_id: str,
        service: WebullSandboxService,
        transport: Case1CancelTransport,
        order: WebullExitOrder,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.session_id = session_id
        self.service = service
        self.transport = transport
        self.order = order
        self.clock = clock

    def run(self) -> Case1StatusResult:
        self.service.verify_account(self.clock(), account_class="INDIVIDUAL_MARGIN")
        positions = dict(self.service.sandbox_positions(self.clock()))
        orders = self.service.sandbox_open_orders(self.clock())
        matches = tuple(item for item in orders if case1_order_matches(item, self.order))
        if len(matches) > 1:
            raise Case1IncompleteError("multiple exact Case-1 open orders were returned")
        account_id = self.service._require_verified()
        detail = self.transport.order_detail(account_id, self.order.client_order_id)
        self.service.registry.insert_envelope(
            self.session_id,
            "OPERATOR_CASE1_STATUS_DETAIL",
            self.clock(),
            detail,
            self.order,
        )
        if not 200 <= detail.status_code < 300:
            raise Case1IncompleteError(
                f"Case-1 status detail returned HTTP {detail.status_code}"
            )
        detail_status = _detail_status(detail, self.order.client_order_id)
        position_quantity = positions.get("AAPL", 0)
        exact_order_open = len(matches) == 1
        return Case1StatusResult(
            self.order.client_order_id,
            detail_status,
            position_quantity,
            len(orders),
            exact_order_open,
            _assessment(detail_status, position_quantity, exact_order_open),
        )


class Case1RecoveryCaptureFinalizer:
    """Package persisted ambiguous-cancel evidence without network access."""

    def __init__(
        self,
        session_id: str,
        registry: WebullSmokeRegistry,
        config: SmokeConfig,
        order: WebullExitOrder,
    ) -> None:
        self.session_id = session_id
        self.registry = registry
        self.config = config
        self.order = order
        self.request_hash = canonical_hash(order)

    def _envelope_evidence(self, operation: str, envelope: str) -> SmokeEvidence:
        occurred_at, request_hash, response = self.registry.latest_envelope_evidence(
            self.session_id, envelope
        )
        if request_hash != self.request_hash:
            raise Case1IncompleteError(f"{envelope} request identity does not match Case 1")
        status_code = response.get("status_code")
        if not isinstance(status_code, int) or not 200 <= status_code < 300:
            raise Case1IncompleteError(f"{envelope} is not successful evidence")
        return SmokeEvidence(
            operation,
            occurred_at,
            self.order.client_order_id,
            self.order.sdk_payload(),
            response,
            {"semantic_review_required": True, "recovered_capture": True},
        )

    def run(self) -> tuple[SmokeCapture, bool]:
        evidence = [
            self._envelope_evidence("STOP_PREVIEW", "SMOKE_CASE1_STOP_PREVIEW"),
            self._envelope_evidence("STOP_PLACE", "SMOKE_CASE1_STOP_PLACE"),
            self._envelope_evidence("STOP_DETAIL", "SMOKE_CASE1_STOP_DETAIL"),
        ]
        cancel_events = tuple(
            item for item in self.registry.operation_events(
                self.session_id, SmokeCase.LONG_STOP_LIFECYCLE
            ) if item.operation == "STOP_CANCEL"
        )
        required_types = (
            SmokeOperationEventType.PREPARED,
            SmokeOperationEventType.CALL_STARTED,
            SmokeOperationEventType.EXCEPTION,
            SmokeOperationEventType.RECOVERED,
        )
        if tuple(item.event_type for item in cancel_events) != required_types:
            raise Case1IncompleteError("ambiguous cancel journal is incomplete or reordered")
        if any(item.request_hash != self.request_hash for item in cancel_events):
            raise Case1IncompleteError("ambiguous cancel journal request identity mismatch")
        exception_event, recovered_event = cancel_events[-2:]
        evidence.append(SmokeEvidence(
            "STOP_CANCEL",
            recovered_event.occurred_at,
            self.order.client_order_id,
            self.order.sdk_payload(),
            {
                "exception": dict(exception_event.detail),
                "single_detail_recovery": dict(recovered_event.detail),
            },
            {
                "ambiguous_write": True,
                "automatic_retry": False,
                "semantic_review_required": True,
            },
        ))
        final = self._envelope_evidence(
            "STOP_CANCEL_DETAIL", "OPERATOR_CASE1_STATUS_DETAIL"
        )
        payload = final.response.get("payload")
        status_code = final.response.get("status_code")
        if not isinstance(payload, Mapping) or not isinstance(status_code, int):
            raise Case1IncompleteError("final Case-1 detail evidence is malformed")
        final_status = _detail_status(
            WebullResponse(status_code, payload), self.order.client_order_id
        )
        if final_status not in {"CANCELED", "CANCELLED"}:
            raise Case1IncompleteError(
                f"final Case-1 detail is not canceled: {final_status}"
            )
        evidence.append(final)
        captured_at = final.occurred_at
        capture = build_smoke_capture(
            self.session_id,
            SmokeCase.LONG_STOP_LIFECYCLE,
            captured_at,
            tuple(evidence),
            self.config,
        )
        return capture, self.registry.insert_capture(capture)


class Case1CancelRecovery:
    def __init__(
        self,
        session_id: str,
        service: WebullSandboxService,
        transport: Case1CancelTransport,
        registry: WebullSmokeRegistry,
        order: WebullExitOrder,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.session_id = session_id
        self.service = service
        self.transport = transport
        self.registry = registry
        self.order = order
        self.clock = clock
        self.case = SmokeCase.LONG_STOP_LIFECYCLE
        self.request_hash = canonical_hash(order)

    def _event(
        self, event_type: SmokeOperationEventType, detail: Mapping[str, object]
    ) -> None:
        occurred_at = self.clock()
        safe = redact(detail)
        if not isinstance(safe, Mapping):
            raise TypeError("redacted operator detail must be a mapping")
        identity = (
            self.session_id,
            self.case.value,
            OPERATION,
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
            OPERATION,
            event_type,
            self.order.client_order_id,
            occurred_at,
            self.request_hash,
            safe,
        ))

    def run(self, confirmation: str) -> Case1CancelResult:
        if confirmation != case1_cancel_confirmation(self.session_id):
            raise ValueError("exact Case-1 cancellation confirmation is required")
        if self.registry.has_operation_call_boundary(
            self.session_id, self.case, OPERATION
        ):
            raise Case1IncompleteError(
                "operator cancellation already crossed a write boundary; replay is prohibited"
            )
        now = self.clock()
        self.service.verify_account(now, account_class="INDIVIDUAL_MARGIN")
        orders = self.service.sandbox_open_orders(self.clock())
        matches = tuple(
            item for item in orders if item.client_order_id == self.order.client_order_id
        )
        if not matches:
            return Case1CancelResult(
                self.order.client_order_id, "NOT_OPEN", "NOT_OPEN", False
            )
        if len(matches) != 1 or not case1_order_matches(matches[0], self.order):
            raise Case1IncompleteError(
                "open order does not match the exact approved Case-1 identity"
            )
        prior_status = matches[0].status
        account_id = self.service._require_verified()
        before = self.transport.order_detail(account_id, self.order.client_order_id)
        if not 200 <= before.status_code < 300:
            raise Case1IncompleteError("pre-cancel detail request failed")
        detail_status = _detail_status(before, self.order.client_order_id)
        if detail_status not in {"PENDING", "SUBMITTED", "ACKNOWLEDGED"}:
            raise Case1IncompleteError(
                f"Case-1 stop is not cancelable from status {detail_status}"
            )
        self.registry.insert_envelope(
            self.session_id, "OPERATOR_CANCEL_CASE1_DETAIL_BEFORE", self.clock(),
            before, self.order,
        )
        self._event(SmokeOperationEventType.PREPARED, {"request": self.order})
        self._event(SmokeOperationEventType.CALL_STARTED, {"request": self.order})
        try:
            canceled = self.transport.cancel_exact_stop(account_id, self.order)
        except Exception as error:
            self._event(
                SmokeOperationEventType.EXCEPTION,
                {"error_type": type(error).__name__},
            )
            try:
                recovered = self.transport.order_detail(
                    account_id, self.order.client_order_id
                )
                recovery: Mapping[str, object] = {
                    "status_code": recovered.status_code,
                    "status": _detail_status(recovered, self.order.client_order_id),
                }
            except Exception as recovery_error:
                recovery = {"error_type": type(recovery_error).__name__}
            self._event(SmokeOperationEventType.RECOVERED, recovery)
            raise Case1AmbiguousError(
                "operator cancellation was ambiguous; queried once and halted"
            ) from error
        self._event(
            SmokeOperationEventType.RESPONSE,
            {"status_code": canceled.status_code, "response": dict(canceled.payload)},
        )
        if not 200 <= canceled.status_code < 300:
            raise Case1IncompleteError(
                f"operator cancellation returned HTTP {canceled.status_code}"
            )
        self.registry.insert_envelope(
            self.session_id, "OPERATOR_CANCEL_CASE1_RESPONSE", self.clock(),
            canceled, self.order,
        )
        final = self.transport.order_detail(account_id, self.order.client_order_id)
        self.registry.insert_envelope(
            self.session_id, "OPERATOR_CANCEL_CASE1_DETAIL_AFTER", self.clock(),
            final, self.order,
        )
        if not 200 <= final.status_code < 300:
            raise Case1IncompleteError("post-cancel detail request failed")
        final_status = _detail_status(final, self.order.client_order_id)
        if final_status not in {"CANCELED", "CANCELLED"}:
            raise Case1IncompleteError(
                f"operator cancellation is not terminal: {final_status}"
            )
        return Case1CancelResult(
            self.order.client_order_id, prior_status, final_status, True
        )
