from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from trading_system.paper import (
    InternalSimulatorAdapter,
    PaperMode,
    PaperRegistry,
    PaperRuntime,
    PaperSession,
    RuntimeState,
)
from trading_system.persistence import SQLiteRepository
from trading_system.webull.automatic_submission import (
    AutomaticSubmissionConfigError,
    load_automatic_submission_config,
    run_automatic_submission_cycle,
)
from trading_system.webull.service import WebullSandboxService

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config/webull.phase12a.automatic-sandbox.v1.json"
NOW = datetime(2026, 9, 28, 8, 0, tzinfo=UTC)


def test_automatic_submission_config_is_sandbox_only_and_blocks_aapl() -> None:
    config = load_automatic_submission_config(CONFIG)

    assert config.symbols == ("MSFT", "SPY")
    assert config.blocked_symbols == ("AAPL",)
    assert config.tick_seconds == 30
    assert config.max_release_lateness_seconds == 120


def test_automatic_submission_config_rejects_live_authority(tmp_path: Path) -> None:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["live_trading_enabled"] = True
    path = tmp_path / "unsafe.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(AutomaticSubmissionConfigError, match="invalid or unsafe"):
        load_automatic_submission_config(path)


def test_automatic_cycle_fails_closed_before_network_when_paper_not_enabled(
    tmp_path: Path,
) -> None:
    config = load_automatic_submission_config(CONFIG)
    with SQLiteRepository(tmp_path / "blocked.sqlite") as repository:
        repository.migrate()
        paper = PaperRegistry(repository)
        paper.insert_session(
            PaperSession(
                "sandbox-auto",
                NOW,
                PaperMode.SHADOW,
                "code",
                "config",
                "data",
                "exchange-calendars-4",
            )
        )
        PaperRuntime(
            paper,
            "sandbox-auto",
            PaperMode.SHADOW,
            InternalSimulatorAdapter(),
        ).start(NOW)

        result = run_automatic_submission_cycle(
            repository,
            cast(WebullSandboxService, object()),
            config,
            session_id="sandbox-auto",
            observed_at=NOW,
            snapshot=None,
            environment_enabled=True,
            cli_enabled=True,
        )

        assert result.status == "BLOCKED"
        assert result.reason == "PAPER_NOT_ENABLED"
        assert not result.broker_write_performed
        assert repository.connection.execute(
            "SELECT status,reason FROM webull_automatic_submission_cycles"
        ).fetchone() == ("BLOCKED", "PAPER_NOT_ENABLED")


def test_automatic_cycle_rejects_unbound_plan_before_network(tmp_path: Path) -> None:
    config = load_automatic_submission_config(CONFIG)
    with SQLiteRepository(tmp_path / "unbound.sqlite") as repository:
        repository.migrate()
        paper = PaperRegistry(repository)
        paper.insert_session(
            PaperSession(
                "sandbox-auto",
                NOW,
                PaperMode.SIMULATED,
                "code",
                "config",
                "data",
                "exchange-calendars-4",
            )
        )
        PaperRuntime(
            paper,
            "sandbox-auto",
            PaperMode.SIMULATED,
            InternalSimulatorAdapter(),
        ).start(NOW)
        assert paper.current_state("sandbox-auto") is RuntimeState.PAPER_ENABLED

        result = run_automatic_submission_cycle(
            repository,
            cast(WebullSandboxService, object()),
            config,
            session_id="sandbox-auto",
            observed_at=NOW,
            snapshot=None,
            environment_enabled=True,
            cli_enabled=True,
        )

        assert result.status == "BLOCKED"
        assert result.reason == "PLAN_NOT_BOUND"
        assert not result.network_used
