from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from trading_system.webull.case1 import Case1IncompleteError
from trading_system.webull.case5 import (
    Case5EvidenceSet,
    TimedCase5Response,
    build_case5_capture,
    exact_case5_entry,
    exact_case5_exit,
    exact_case5_stop,
)
from trading_system.webull.contracts import WebullResponse
from trading_system.webull.smoke import SmokeCase, SmokeConfig, load_smoke_config
from trading_system.webull.transport import OfficialSdkWebullCase1Transport

ROOT = Path(__file__).parents[2]


def detail(
    client_id: str,
    *,
    side: str,
    quantity: int,
    filled: int,
    order_type: str,
    time_in_force: str,
    status: str,
) -> WebullResponse:
    return WebullResponse(200, {"order": {
        "client_order_id": client_id,
        "symbol": "AAPL",
        "side": side,
        "total_quantity": str(quantity),
        "filled_quantity": str(filled),
        "order_type": order_type,
        "time_in_force": time_in_force,
        "support_trading_session": "CORE",
        "status": status,
    }})


def evidence_set(
    session_id: str,
    *,
    terminal_fill: int = 2,
    stop_fill: int = 1,
    exit_fill: int = 1,
) -> tuple[Case5EvidenceSet, datetime]:
    start = datetime(2026, 8, 28, 14, tzinfo=UTC)
    entry = exact_case5_entry(session_id)
    stop = exact_case5_stop(session_id)
    exit_order = exact_case5_exit(session_id)
    responses = Case5EvidenceSet(
        TimedCase5Response(start, detail(
            entry.client_order_id,
            side="BUY",
            quantity=4,
            filled=2,
            order_type="MARKET",
            time_in_force="DAY",
            status="PARTIALLY_FILLED",
        )),
        TimedCase5Response(start + timedelta(seconds=1), WebullResponse(200, {
            "client_order_id": entry.client_order_id,
        })),
        TimedCase5Response(start + timedelta(seconds=2), detail(
            entry.client_order_id,
            side="BUY",
            quantity=4,
            filled=terminal_fill,
            order_type="MARKET",
            time_in_force="DAY",
            status="CANCELLED",
        )),
        TimedCase5Response(start + timedelta(seconds=3), detail(
            stop.client_order_id,
            side="SELL",
            quantity=2,
            filled=stop_fill,
            order_type="STOP_LOSS",
            time_in_force="GTC",
            status="PARTIALLY_FILLED",
        )),
        TimedCase5Response(start + timedelta(seconds=4), detail(
            exit_order.client_order_id,
            side="SELL",
            quantity=2,
            filled=exit_fill,
            order_type="MARKET",
            time_in_force="DAY",
            status="PARTIALLY_FILLED",
        )),
    )
    return responses, start + timedelta(seconds=5)


def config() -> SmokeConfig:
    return load_smoke_config(ROOT / "config/webull.phase3d5.smoke.v1.json")


def test_case5_builds_deterministic_ordered_capture() -> None:
    evidence, captured_at = evidence_set("case5-valid")
    first = build_case5_capture("case5-valid", evidence, captured_at, config())
    second = build_case5_capture("case5-valid", evidence, captured_at, config())
    assert first == second
    assert first.case is SmokeCase.PARTIAL_FILLS
    assert tuple(item.operation for item in first.evidence) == (
        "PARTIAL_ENTRY_DETAIL",
        "ENTRY_CANCEL",
        "ENTRY_TERMINAL_DETAIL",
        "PARTIAL_STOP_DETAIL",
        "PARTIAL_EXIT_DETAIL",
    )


@pytest.mark.parametrize(
    ("terminal_fill", "stop_fill", "exit_fill"),
    ((1, 1, 1), (2, 0, 1), (2, 1, 2)),
)
def test_case5_rejects_cumulative_fill_mismatch(
    terminal_fill: int, stop_fill: int, exit_fill: int
) -> None:
    evidence, captured_at = evidence_set(
        "case5-fill-mismatch",
        terminal_fill=terminal_fill,
        stop_fill=stop_fill,
        exit_fill=exit_fill,
    )
    with pytest.raises(Case1IncompleteError, match="cumulative fill"):
        build_case5_capture(
            "case5-fill-mismatch", evidence, captured_at, config()
        )


def test_case5_rejects_noncausal_capture_time() -> None:
    evidence, _captured_at = evidence_set("case5-time")
    with pytest.raises(ValueError, match="precede"):
        build_case5_capture(
            "case5-time",
            evidence,
            evidence.partial_entry_detail.occurred_at - timedelta(seconds=1),
            config(),
        )


def test_case5_has_no_official_write_surface() -> None:
    assert not hasattr(OfficialSdkWebullCase1Transport, "cancel_partial_entry")
    assert not hasattr(OfficialSdkWebullCase1Transport, "place_partial_stop")
    assert not hasattr(OfficialSdkWebullCase1Transport, "place_partial_exit")
