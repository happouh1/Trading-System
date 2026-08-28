"""Offline Case-5 cumulative-fill evidence validation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from trading_system.webull.case1 import Case1IncompleteError
from trading_system.webull.contracts import (
    WebullResponse,
    WebullSide,
    WebullStockOrder,
)
from trading_system.webull.exit_contracts import WebullExitOrder
from trading_system.webull.mapping import client_order_id
from trading_system.webull.security import redact
from trading_system.webull.smoke import (
    SmokeCapture,
    SmokeCase,
    SmokeConfig,
    SmokeEvidence,
    build_smoke_capture,
)

ENTRY_REQUESTED_QUANTITY = 4
ENTRY_CUMULATIVE_FILL = 2
PARTIAL_EXIT_REQUESTED_QUANTITY = 2
PARTIAL_EXIT_CUMULATIVE_FILL = 1


@dataclass(frozen=True, slots=True)
class TimedCase5Response:
    occurred_at: datetime
    response: WebullResponse

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("Case-5 evidence timestamps must be timezone-aware")


@dataclass(frozen=True, slots=True)
class Case5EvidenceSet:
    partial_entry_detail: TimedCase5Response
    entry_cancel: TimedCase5Response
    entry_terminal_detail: TimedCase5Response
    partial_stop_detail: TimedCase5Response
    partial_exit_detail: TimedCase5Response


def case5_client_order_id(session_id: str, operation: str) -> str:
    if operation not in {"entry", "stop", "exit"}:
        raise ValueError("unsupported Case-5 operation identity")
    return client_order_id(f"{session_id}:phase3d5:case5:{operation}:AAPL")


def exact_case5_entry(session_id: str) -> WebullStockOrder:
    return WebullStockOrder(
        case5_client_order_id(session_id, "entry"),
        "AAPL",
        WebullSide.BUY,
        ENTRY_REQUESTED_QUANTITY,
    )


def exact_case5_stop(session_id: str) -> WebullExitOrder:
    return WebullExitOrder(
        case5_client_order_id(session_id, "stop"),
        "AAPL",
        WebullSide.SELL,
        ENTRY_CUMULATIVE_FILL,
        "STOP_LOSS",
        "GTC",
        Decimal("1.00"),
        False,
        "CORE",
    )


def exact_case5_exit(session_id: str) -> WebullExitOrder:
    return WebullExitOrder(
        case5_client_order_id(session_id, "exit"),
        "AAPL",
        WebullSide.SELL,
        PARTIAL_EXIT_REQUESTED_QUANTITY,
        "MARKET",
        "DAY",
        None,
        False,
        "CORE",
    )


def _detail_item(response: WebullResponse, client_id: str) -> Mapping[str, object]:
    candidates: object = response.payload.get("orders")
    if candidates is None:
        single = response.payload.get("order")
        candidates = (single,) if isinstance(single, Mapping) else ()
    if not isinstance(candidates, (tuple, list)):
        raise Case1IncompleteError("Case-5 detail response has no orders array")
    matches = tuple(
        item
        for item in candidates
        if isinstance(item, Mapping) and item.get("client_order_id") == client_id
    )
    if len(matches) != 1:
        raise Case1IncompleteError("Case-5 detail did not resolve exactly one order")
    return matches[0]


def _validate_detail(
    item: TimedCase5Response,
    *,
    client_id: str,
    side: WebullSide,
    quantity: int,
    filled_quantity: int,
    order_type: str,
    time_in_force: str,
    statuses: frozenset[str],
) -> None:
    if not 200 <= item.response.status_code < 300:
        raise Case1IncompleteError("Case-5 detail response was unsuccessful")
    raw = _detail_item(item.response, client_id)
    actual_quantity = raw.get("total_quantity", raw.get("quantity"))
    actual_fill = raw.get(
        "filled_quantity", raw.get("cumulative_filled_quantity")
    )
    if not (
        raw.get("symbol") == "AAPL"
        and raw.get("side") == side.value
        and str(actual_quantity) == str(quantity)
        and str(actual_fill) == str(filled_quantity)
        and raw.get("order_type") == order_type
        and raw.get("time_in_force") == time_in_force
        and raw.get("support_trading_session") == "CORE"
        and raw.get("status") in statuses
    ):
        raise Case1IncompleteError("Case-5 order identity or cumulative fill is invalid")


def _smoke_evidence(
    operation: str,
    item: TimedCase5Response,
    client_id: str,
    request: Mapping[str, object],
) -> SmokeEvidence:
    safe = redact(dict(item.response.payload))
    if not isinstance(safe, Mapping):
        raise TypeError("redacted Case-5 response must be a mapping")
    return SmokeEvidence(
        operation,
        item.occurred_at,
        client_id,
        request,
        {"status_code": item.response.status_code, "payload": safe},
        {
            "offline_fixture_only": True,
            "semantic_review_required": True,
        },
    )


def build_case5_capture(
    session_id: str,
    evidence: Case5EvidenceSet,
    captured_at: datetime,
    config: SmokeConfig,
) -> SmokeCapture:
    """Validate supplied redacted evidence; never invokes a broker transport."""
    entry = exact_case5_entry(session_id)
    stop = exact_case5_stop(session_id)
    exit_order = exact_case5_exit(session_id)

    _validate_detail(
        evidence.partial_entry_detail,
        client_id=entry.client_order_id,
        side=WebullSide.BUY,
        quantity=ENTRY_REQUESTED_QUANTITY,
        filled_quantity=ENTRY_CUMULATIVE_FILL,
        order_type="MARKET",
        time_in_force="DAY",
        statuses=frozenset({"PARTIALLY_FILLED"}),
    )
    cancel = evidence.entry_cancel.response
    if not 200 <= cancel.status_code < 300 or (
        cancel.payload.get("client_order_id") != entry.client_order_id
    ):
        raise Case1IncompleteError("Case-5 entry cancellation identity is invalid")
    _validate_detail(
        evidence.entry_terminal_detail,
        client_id=entry.client_order_id,
        side=WebullSide.BUY,
        quantity=ENTRY_REQUESTED_QUANTITY,
        filled_quantity=ENTRY_CUMULATIVE_FILL,
        order_type="MARKET",
        time_in_force="DAY",
        statuses=frozenset({"CANCELED", "CANCELLED"}),
    )
    _validate_detail(
        evidence.partial_stop_detail,
        client_id=stop.client_order_id,
        side=WebullSide.SELL,
        quantity=ENTRY_CUMULATIVE_FILL,
        filled_quantity=PARTIAL_EXIT_CUMULATIVE_FILL,
        order_type="STOP_LOSS",
        time_in_force="GTC",
        statuses=frozenset({"PARTIALLY_FILLED"}),
    )
    _validate_detail(
        evidence.partial_exit_detail,
        client_id=exit_order.client_order_id,
        side=WebullSide.SELL,
        quantity=PARTIAL_EXIT_REQUESTED_QUANTITY,
        filled_quantity=PARTIAL_EXIT_CUMULATIVE_FILL,
        order_type="MARKET",
        time_in_force="DAY",
        statuses=frozenset({"PARTIALLY_FILLED"}),
    )

    items = (
        _smoke_evidence(
            "PARTIAL_ENTRY_DETAIL",
            evidence.partial_entry_detail,
            entry.client_order_id,
            entry.sdk_payload(),
        ),
        _smoke_evidence(
            "ENTRY_CANCEL",
            evidence.entry_cancel,
            entry.client_order_id,
            {"client_order_id": entry.client_order_id},
        ),
        _smoke_evidence(
            "ENTRY_TERMINAL_DETAIL",
            evidence.entry_terminal_detail,
            entry.client_order_id,
            entry.sdk_payload(),
        ),
        _smoke_evidence(
            "PARTIAL_STOP_DETAIL",
            evidence.partial_stop_detail,
            stop.client_order_id,
            stop.sdk_payload(),
        ),
        _smoke_evidence(
            "PARTIAL_EXIT_DETAIL",
            evidence.partial_exit_detail,
            exit_order.client_order_id,
            exit_order.sdk_payload(),
        ),
    )
    return build_smoke_capture(
        session_id, SmokeCase.PARTIAL_FILLS, captured_at, items, config
    )
