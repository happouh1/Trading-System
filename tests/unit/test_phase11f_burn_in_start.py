from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from trading_system import PACKAGE_VERSION
from trading_system.cli.main import main
from trading_system.desktop.prospective_burn_in import ProspectiveBurnInPlan
from trading_system.paper.burn_in_start import (
    LockedBurnInStartConfigError,
    build_locked_burn_in_binding,
    load_locked_burn_in_start_config,
    start_locked_burn_in_session,
)
from trading_system.paper.config import load_paper_config
from trading_system.paper.contracts import RuntimeState
from trading_system.serialization import canonical_json

ROOT = Path(__file__).parents[2]
STARTED = datetime(2026, 9, 15, 14, tzinfo=UTC)
HASH = "sha256:" + "a" * 64


def _plan() -> ProspectiveBurnInPlan:
    return ProspectiveBurnInPlan(
        "plan-11f",
        datetime(2026, 9, 12, tzinfo=UTC),
        datetime(2026, 9, 14, 13, 30, tzinfo=UTC),
        datetime(2026, 10, 9, 20, tzinfo=UTC),
        10,
        20,
        10,
        ("BULLISH",),
        ("AAPL",),
        ("1H",),
        ("BREAKOUT",),
        0,
        0,
        0,
        Decimal("0.10"),
        0,
        "release-11f",
        HASH,
        HASH,
    )


def _files(tmp_path: Path, *, code_version: str = PACKAGE_VERSION) -> Path:
    paper = tmp_path / "paper.json"
    paper.write_text(
        (ROOT / "config/paper.phase3b.v1.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    paper_hash = load_paper_config(paper).config_hash
    (tmp_path / "plan.json").write_text(canonical_json(_plan()), encoding="utf-8")
    lock = {
        "runtime_lock_version": "11E.1.0",
        "mode": "CONTINUITY_LOCK_FROM_INITIAL_SESSION",
        "plan_id": "plan-11f",
        "baseline": {
            "session_id": "burn-in-baseline",
            "code_version": code_version,
            "config_hash": paper_hash,
            "data_revision": "LOCKED-DATA",
            "calendar_version": "exchange-calendars-4",
        },
        "retrospective_baseline_disclosed": True,
        "authority": {
            "database_read_enabled": True,
            "database_write_enabled": False,
            "network_enabled": False,
            "credential_loading_enabled": False,
            "broker_writes_enabled": False,
            "sandbox_execution_enabled": False,
            "live_trading_enabled": False,
            "automatic_promotion_enabled": False,
        },
    }
    (tmp_path / "lock.json").write_text(json.dumps(lock), encoding="utf-8")
    collector = json.loads(
        (ROOT / "config/desktop.phase11c.v1.yaml").read_text(encoding="utf-8")
    )
    collector["plan"] = "plan.json"
    collector["evidence_output"] = "observations.json"
    collector["runtime_lock"] = "lock.json"
    (tmp_path / "collector.json").write_text(json.dumps(collector), encoding="utf-8")
    start = json.loads(
        (ROOT / "config/paper.phase11f.v1.yaml").read_text(encoding="utf-8")
    )
    start["paper_config"] = "paper.json"
    start["collector_config"] = "collector.json"
    path = tmp_path / "start.json"
    path.write_text(json.dumps(start), encoding="utf-8")
    return path


def test_locked_start_is_idempotent_shadow_only_and_persisted(tmp_path: Path) -> None:
    config = _files(tmp_path)
    first = start_locked_burn_in_session(
        database="burn.sqlite",
        config_path=config,
        project_root=tmp_path,
        session_id="burn-in-11f-01",
        started_at=STARTED,
    )
    second = start_locked_burn_in_session(
        database="burn.sqlite",
        config_path=config,
        project_root=tmp_path,
        session_id="burn-in-11f-01",
        started_at=STARTED,
    )
    assert first["state"] is RuntimeState.SHADOW
    assert first["session_inserted"] is True
    assert first["binding_inserted"] is True
    assert second["session_inserted"] is False
    assert second["binding_inserted"] is False
    assert not first["network_used"]
    assert not first["broker_write_performed"]
    with sqlite3.connect(tmp_path / "burn.sqlite") as connection:
        session = connection.execute(
            "SELECT mode,code_version,data_revision FROM paper_sessions"
        ).fetchone()
        binding_count = connection.execute(
            "SELECT COUNT(*) FROM paper_burn_in_session_bindings"
        ).fetchone()
    assert session == ("SHADOW", PACKAGE_VERSION, "LOCKED-DATA")
    assert binding_count == (1,)


def test_build_rejects_drift_window_and_non_utc(tmp_path: Path) -> None:
    config_path = _files(tmp_path)
    config = load_locked_burn_in_start_config(config_path)
    paper_hash = load_paper_config(tmp_path / "paper.json").config_hash
    from trading_system.desktop.burn_in_runtime_lock import load_burn_in_runtime_lock

    lock = load_burn_in_runtime_lock(tmp_path / "lock.json")
    binding = build_locked_burn_in_binding(
        config,
        _plan(),
        lock,
        session_id="burn-in-11f-01",
        started_at=STARTED,
        paper_config_hash=paper_hash,
    )
    assert binding.code_version == PACKAGE_VERSION
    with pytest.raises(ValueError, match="code_version"):
        build_locked_burn_in_binding(
            config,
            _plan(),
            replace(lock, code_version="drift"),
            session_id="burn-in-11f-01",
            started_at=STARTED,
            paper_config_hash=paper_hash,
        )
    with pytest.raises(ValueError, match="outside"):
        build_locked_burn_in_binding(
            config,
            _plan(),
            lock,
            session_id="burn-in-11f-01",
            started_at=datetime(2027, 1, 1, tzinfo=UTC),
            paper_config_hash=paper_hash,
        )
    with pytest.raises(ValueError, match="UTC"):
        build_locked_burn_in_binding(
            config,
            _plan(),
            lock,
            session_id="burn-in-11f-01",
            started_at=datetime(2026, 9, 15),
            paper_config_hash=paper_hash,
        )


def test_config_rejects_widened_authority_and_path_escape(tmp_path: Path) -> None:
    config_path = _files(tmp_path)
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    raw["authority"]["network_enabled"] = True
    config_path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(LockedBurnInStartConfigError, match="unsafe"):
        load_locked_burn_in_start_config(config_path)
    raw["authority"]["network_enabled"] = False
    raw["paper_config"] = "../paper.json"
    config_path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(LockedBurnInStartConfigError, match="unsafe"):
        load_locked_burn_in_start_config(config_path)


def test_identity_failure_occurs_before_database_creation(tmp_path: Path) -> None:
    config = _files(tmp_path, code_version="wrong-version")
    with pytest.raises(ValueError, match="code_version"):
        start_locked_burn_in_session(
            database="must-not-exist.sqlite",
            config_path=config,
            project_root=tmp_path,
            session_id="burn-in-11f-01",
            started_at=STARTED,
        )
    assert not (tmp_path / "must-not-exist.sqlite").exists()


def test_cli_starts_only_locked_shadow_session(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = _files(tmp_path)
    assert main(
        [
            "paper",
            "start-burn-in",
            "--database",
            "cli.sqlite",
            "--session-id",
            "burn-in-cli-01",
            "--config",
            str(config),
            "--started-at",
            "2026-09-15T14:00:00Z",
            "--project-root",
            str(tmp_path),
        ]
    ) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["state"] == "SHADOW"
    assert output["network_used"] is False
    assert output["broker_write_performed"] is False
