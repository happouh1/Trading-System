"""Persist-first orchestration for the exact approved Phase 3D-5 Case 1."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from trading_system.serialization import canonical_hash, deterministic_id
from trading_system.webull.case1_transport import case1_client_order_id
from trading_system.webull.contracts import WebullResponse, WebullSide
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


class Case1Transport(Protocol):
    def preview_exact_stop(
        self, account_id: str, order: WebullExitOrder
    ) -> WebullResponse: ...

    def place_exact_stop(
        self, account_id: str, order: WebullExitOrder
    ) -> WebullResponse: ...

    def order_detail(self, account_id: str, client_order_id: str) -> WebullResponse: ...

    def cancel_exact_stop(
        self, account_id: str, order: WebullExitOrder
    ) -> WebullResponse: ...


class Case1IncompleteError(RuntimeError):
    """The approved sequence halted without manufacturing complete evidence."""


class Case1AmbiguousError(Case1IncompleteError):
    """A write raised and was queried exactly once without automatic retry."""


@dataclass(frozen=True, slots=True)
class Case1Result:
    capture: SmokeCapture
    client_order_id: str


def exact_case1_order(session_id: str) -> WebullExitOrder:
    return WebullExitOrder(
        case1_client_order_id(session_id),
        "AAPL",
        WebullSide.SELL,
        1,
        "STOP_LOSS",
        "GTC",
        Decimal("1.00"),
        False,
        "CORE",
    )


class Case1Runner:
    def __init__(
        self,
        session_id: str,
        service: WebullSandboxService,
        transport: Case1Transport,
        registry: WebullSmokeRegistry,
        smoke_config: SmokeConfig,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.session_id = session_id
        self.service = service
        self.transport = transport
        self.registry = registry
        self.smoke_config = smoke_config
        self.clock = clock
        self.case = SmokeCase.LONG_STOP_LIFECYCLE
        self.order = exact_case1_order(session_id)
        self.request_hash = canonical_hash(self.order)

    def _event(
        self,
        operation: str,
        event_type: SmokeOperationEventType,
        detail: Mapping[str, object],
    ) -> None:
        occurred_at = self.clock()
        safe = redact(detail)
        if not isinstance(safe, Mapping):
            raise TypeError("redacted operation detail must be a mapping")
        identity = (
            self.session_id,
            self.case.value,
            operation,
            event_type.value,
            self.order.client_order_id,
            occurred_at,
            self.request_hash,
            safe,
        )
        item = SmokeOperationEvent(
            deterministic_id("webull_smoke_operation_event", identity),
            self.session_id,
            self.case,
            operation,
            event_type,
            self.order.client_order_id,
            occurred_at,
            self.request_hash,
            safe,
        )
        self.registry.insert_operation_event(item)

    def _evidence(
        self, operation: str, response: WebullResponse
    ) -> SmokeEvidence:
        safe_response = redact(dict(response.payload))
        safe_request = redact(self.order.sdk_payload())
        if not isinstance(safe_response, Mapping):
            raise TypeError("redacted Webull response must be a mapping")
        if not isinstance(safe_request, Mapping):
            raise TypeError("redacted Webull request must be a mapping")
        return SmokeEvidence(
            operation,
            self.clock(),
            self.order.client_order_id,
            safe_request,
            {"status_code": response.status_code, "payload": safe_response},
            {"semantic_review_required": True},
        )

    @staticmethod
    def _require_success(operation: str, response: WebullResponse) -> None:
        if not 200 <= response.status_code < 300:
            raise Case1IncompleteError(
                f"{operation} returned HTTP {response.status_code}; sequence halted"
            )

    def _write(
        self,
        operation: str,
        call: Callable[[], WebullResponse],
        account_id: str,
    ) -> WebullResponse:
        self._event(operation, SmokeOperationEventType.PREPARED, {"request": self.order})
        self._event(operation, SmokeOperationEventType.CALL_STARTED, {"request": self.order})
        try:
            response = call()
        except Exception as error:
            self._event(
                operation,
                SmokeOperationEventType.EXCEPTION,
                {"error_type": type(error).__name__},
            )
            try:
                recovered = self.transport.order_detail(
                    account_id, self.order.client_order_id
                )
                recovery_detail: Mapping[str, object] = {
                    "status_code": recovered.status_code,
                    "response": dict(recovered.payload),
                }
            except Exception as recovery_error:
                recovery_detail = {"error_type": type(recovery_error).__name__}
            self._event(operation, SmokeOperationEventType.RECOVERED, recovery_detail)
            raise Case1AmbiguousError(
                f"{operation} was ambiguous; queried the same client ID once and halted"
            ) from error
        self._event(
            operation,
            SmokeOperationEventType.RESPONSE,
            {"status_code": response.status_code, "response": dict(response.payload)},
        )
        self._require_success(operation, response)
        return response

    def run(self) -> Case1Result:
        if self.registry.has_call_boundary(self.session_id, self.case):
            raise Case1IncompleteError(
                "Case 1 already crossed a write boundary; automatic replay is prohibited"
            )
        now = self.clock()
        self.service.verify_account(now, account_class="INDIVIDUAL_MARGIN")
        positions, open_order_count = self.service.smoke_position_preflight(now)
        if positions != (("AAPL", 1),) or open_order_count != 0:
            raise Case1IncompleteError(
                "Case 1 requires exactly one AAPL long share and zero open orders"
            )
        account_id = self.service._require_verified()

        preview = self.transport.preview_exact_stop(account_id, self.order)
        self.registry.insert_envelope(
            self.session_id, "SMOKE_CASE1_STOP_PREVIEW", self.clock(), preview, self.order
        )
        self._require_success("STOP_PREVIEW", preview)
        evidence: list[SmokeEvidence] = [self._evidence("STOP_PREVIEW", preview)]

        placed = self._write(
            "STOP_PLACE", lambda: self.transport.place_exact_stop(account_id, self.order),
            account_id,
        )
        self.registry.insert_envelope(
            self.session_id, "SMOKE_CASE1_STOP_PLACE", self.clock(), placed, self.order
        )
        evidence.append(self._evidence("STOP_PLACE", placed))

        detail = self.transport.order_detail(account_id, self.order.client_order_id)
        self.registry.insert_envelope(
            self.session_id, "SMOKE_CASE1_STOP_DETAIL", self.clock(), detail, self.order
        )
        self._require_success("STOP_DETAIL", detail)
        evidence.append(self._evidence("STOP_DETAIL", detail))

        canceled = self._write(
            "STOP_CANCEL", lambda: self.transport.cancel_exact_stop(account_id, self.order),
            account_id,
        )
        self.registry.insert_envelope(
            self.session_id, "SMOKE_CASE1_STOP_CANCEL", self.clock(), canceled, self.order
        )
        evidence.append(self._evidence("STOP_CANCEL", canceled))

        final_detail = self.transport.order_detail(account_id, self.order.client_order_id)
        self.registry.insert_envelope(
            self.session_id,
            "SMOKE_CASE1_STOP_CANCEL_DETAIL",
            self.clock(),
            final_detail,
            self.order,
        )
        self._require_success("STOP_CANCEL_DETAIL", final_detail)
        evidence.append(self._evidence("STOP_CANCEL_DETAIL", final_detail))

        capture = build_smoke_capture(
            self.session_id, self.case, self.clock(), tuple(evidence), self.smoke_config
        )
        self.registry.insert_capture(capture)
        return Case1Result(capture, self.order.client_order_id)
