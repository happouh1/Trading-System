"""Offline Case-6 ambiguous-write recovery harness."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from trading_system.serialization import canonical_hash, deterministic_id
from trading_system.webull.case1 import Case1AmbiguousError, Case1IncompleteError
from trading_system.webull.contracts import (
    WebullResponse,
    WebullSide,
    WebullStockOrder,
)
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


class Case6Transport(Protocol):
    def submit_once(self, account_id: str, order: WebullStockOrder) -> WebullResponse: ...

    def order_detail(self, account_id: str, client_order_id: str) -> WebullResponse: ...


@dataclass(frozen=True, slots=True)
class Case6Result:
    capture: SmokeCapture
    client_order_id: str


def case6_client_order_id(session_id: str) -> str:
    return client_order_id(f"{session_id}:phase3d5:case6:ambiguous:AAPL")


def exact_case6_order(session_id: str) -> WebullStockOrder:
    return WebullStockOrder(
        case6_client_order_id(session_id),
        "AAPL",
        WebullSide.BUY,
        1,
    )


def validate_case6_order(session_id: str, order: WebullStockOrder) -> None:
    if order != exact_case6_order(session_id):
        raise ValueError("order does not match the exact approved Case-6 fixture")


def _detail_item(response: WebullResponse, client_id: str) -> Mapping[str, object]:
    candidates: object = response.payload.get("orders")
    if candidates is None:
        single = response.payload.get("order")
        candidates = (single,) if isinstance(single, Mapping) else ()
    if not isinstance(candidates, (tuple, list)):
        raise Case1IncompleteError("Case-6 detail response has no orders array")
    matches = tuple(
        item
        for item in candidates
        if isinstance(item, Mapping) and item.get("client_order_id") == client_id
    )
    if len(matches) != 1:
        raise Case1IncompleteError("Case-6 detail did not resolve exactly one order")
    return matches[0]


def _recovery_matches(response: WebullResponse, expected: WebullStockOrder) -> bool:
    if not 200 <= response.status_code < 300:
        return False
    item = _detail_item(response, expected.client_order_id)
    quantity = item.get("total_quantity", item.get("quantity"))
    status = item.get("status")
    return (
        item.get("symbol") == expected.symbol
        and item.get("side") == expected.side.value
        and str(quantity) == str(expected.quantity)
        and item.get("order_type") == expected.order_type
        and item.get("time_in_force") == expected.time_in_force
        and item.get("support_trading_session") == expected.support_trading_session
        and isinstance(status, str)
        and bool(status)
    )


class Case6Runner:
    """Inject one fake ambiguity and resolve it by one exact query."""

    def __init__(
        self,
        session_id: str,
        service: WebullSandboxService,
        transport: Case6Transport,
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
        self.case = SmokeCase.AMBIGUITY_RECOVERY
        self.order = exact_case6_order(session_id)
        validate_case6_order(session_id, self.order)
        self.request_hash = canonical_hash(self.order)

    def _event(
        self, event_type: SmokeOperationEventType, detail: Mapping[str, object]
    ) -> None:
        occurred_at = self.clock()
        safe = redact(detail)
        if not isinstance(safe, Mapping):
            raise TypeError("redacted Case-6 detail must be a mapping")
        identity = (
            self.session_id,
            self.case.value,
            "AMBIGUOUS_WRITE",
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
            "AMBIGUOUS_WRITE",
            event_type,
            self.order.client_order_id,
            occurred_at,
            self.request_hash,
            safe,
        ))

    def _evidence(
        self,
        operation: str,
        response: Mapping[str, object],
        observation: Mapping[str, object],
    ) -> SmokeEvidence:
        safe_response = redact(response)
        safe_observation = redact(observation)
        if not isinstance(safe_response, Mapping) or not isinstance(
            safe_observation, Mapping
        ):
            raise TypeError("redacted Case-6 evidence must be mappings")
        return SmokeEvidence(
            operation,
            self.clock(),
            self.order.client_order_id,
            self.order.sdk_payload(),
            safe_response,
            safe_observation,
        )

    def run(self) -> Case6Result:
        if self.registry.has_call_boundary(self.session_id, self.case):
            raise Case1IncompleteError("Case 6 already crossed a write boundary")
        self.service.verify_account(self.clock(), account_class="INDIVIDUAL_MARGIN")
        account_id = self.service._require_verified()
        self._event(SmokeOperationEventType.PREPARED, {"request": self.order})
        self._event(SmokeOperationEventType.CALL_STARTED, {"request": self.order})
        try:
            response = self.transport.submit_once(account_id, self.order)
        except Exception as error:
            error_type = type(error).__name__
            self._event(SmokeOperationEventType.EXCEPTION, {"error_type": error_type})
        else:
            self._event(SmokeOperationEventType.RESPONSE, {
                "status_code": response.status_code,
                "response": dict(response.payload),
            })
            raise Case1IncompleteError("Case 6 requires an injected ambiguous write")

        ambiguous = self._evidence(
            "AMBIGUOUS_WRITE",
            {"error_type": error_type},
            {"write_attempts": 1, "write_retry_performed": False},
        )
        try:
            detail = self.transport.order_detail(account_id, self.order.client_order_id)
        except Exception as query_error:
            recovery = {"error_type": type(query_error).__name__}
            self._event(SmokeOperationEventType.RECOVERED, recovery)
            raise Case1AmbiguousError(
                "Case-6 same-client recovery query failed; halted"
            ) from query_error
        self.registry.insert_envelope(
            self.session_id,
            "SMOKE_CASE6_SAME_CLIENT_DETAIL_QUERY",
            self.clock(),
            detail,
            self.order,
        )
        query = self._evidence(
            "SAME_CLIENT_DETAIL_QUERY",
            {"status_code": detail.status_code, "payload": dict(detail.payload)},
            {"query_attempts": 1, "queried_client_order_id": self.order.client_order_id},
        )
        if not _recovery_matches(detail, self.order):
            self._event(SmokeOperationEventType.RECOVERED, {
                "resolved": False,
                "status_code": detail.status_code,
            })
            raise Case1AmbiguousError("Case-6 recovery remained unresolved; halted")
        recovered_item = _detail_item(detail, self.order.client_order_id)
        recovery_result = self._evidence(
            "RECOVERY_RESULT",
            {
                "classification": "SAME_CLIENT_ORDER_FOUND",
                "provider_status": recovered_item["status"],
            },
            {
                "resolved": True,
                "write_attempts": 1,
                "query_attempts": 1,
                "write_retry_performed": False,
            },
        )
        self._event(SmokeOperationEventType.RECOVERED, {
            "resolved": True,
            "classification": "SAME_CLIENT_ORDER_FOUND",
        })
        capture = build_smoke_capture(
            self.session_id,
            self.case,
            self.clock(),
            (ambiguous, query, recovery_result),
            self.config,
        )
        self.registry.insert_capture(capture)
        return Case6Result(capture, self.order.client_order_id)
