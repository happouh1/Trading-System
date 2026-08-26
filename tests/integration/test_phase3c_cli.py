from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from trading_system.cli import main
from trading_system.domain import Direction, Timeframe, TradePlan
from trading_system.paper import (
    InternalSimulatorAdapter,
    PaperMode,
    PaperRegistry,
    PaperRuntime,
    PaperSession,
)
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]


def test_webull_verify_config_is_offline() -> None:
    assert main([
        "webull", "verify-config", "--config",
        str(ROOT / "config/webull.sandbox.v1.yaml"),
    ]) == 0


def test_webull_preview_candidates_is_offline_and_uses_phase1_quantity(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "candidates.sqlite"
    created_at = datetime(2026, 1, 5, 20, tzinfo=UTC)
    scheduled_open = datetime(2026, 1, 6, 14, 30, tzinfo=UTC)
    with SQLiteRepository(database) as repository:
        repository.migrate()
        paper = PaperRegistry(repository)
        paper.insert_session(
            PaperSession(
                "candidate-session", created_at, PaperMode.SHADOW,
                "code", "config", "data", "XNYS",
            )
        )
        runtime = PaperRuntime(
            paper, "candidate-session", PaperMode.SHADOW, InternalSimulatorAdapter()
        )
        runtime.start(created_at)
        runtime.record_plan(
            TradePlan(
                "candidate-plan", "AAPL", Timeframe.HOUR_1, Direction.LONG,
                created_at, Decimal("101"), Decimal("99"), Decimal("2"),
                None, None, "candidate-pattern",
            ),
            scheduled_open,
            created_at,
        )
    assert main([
        "webull", "preview-candidates",
        "--database", str(database),
        "--session-id", "candidate-session",
        "--config", str(ROOT / "config/webull.sandbox.v1.yaml"),
        "--thresholds", str(ROOT / "config/thresholds.phase1e.v1.yaml"),
        "--as-of", "2026-01-05T21:00:00Z",
    ]) == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["network_used"] is False
    assert payload["order_submitted"] is False
    assert payload["candidates"][0]["eligible"] is True
    assert payload["candidates"][0]["quantity"] == 500


def test_webull_order_report_is_offline_and_production_disabled(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "order-report.sqlite"
    created_at = datetime(2026, 1, 5, 20, tzinfo=UTC)
    with SQLiteRepository(database) as repository:
        repository.migrate()
        paper = PaperRegistry(repository)
        paper.insert_session(
            PaperSession(
                "report-session",
                created_at,
                PaperMode.SHADOW,
                "code",
                "config",
                "data",
                "XNYS",
            )
        )
        PaperRuntime(
            paper, "report-session", PaperMode.SHADOW, InternalSimulatorAdapter()
        ).start(created_at)
    assert main([
        "webull",
        "order-report",
        "--database",
        str(database),
        "--session-id",
        "report-session",
        "--config",
        str(ROOT / "config/webull.sandbox.v1.yaml"),
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["network_used"] is False
    assert payload["production_enabled"] is False
    assert payload["unresolved_intent_ids"] == []
