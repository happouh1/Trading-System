from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.unit.test_phase11c_burn_in_collector import CONFIG, _plan
from trading_system.cli.main import main
from trading_system.desktop.burn_in_collector import load_burn_in_collector_config
from trading_system.desktop.burn_in_status import inspect_immutable_burn_in
from trading_system.serialization import canonical_json


def _fixture(tmp_path: Path, *, evidence: bool = True) -> Path:
    (tmp_path / "plan.json").write_text(canonical_json(_plan()) + "\n", encoding="utf-8")
    if evidence:
        (tmp_path / "observations.json").write_text(
            '{"observations":[]}\n', encoding="utf-8"
        )
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["plan"] = "plan.json"
    raw["evidence_output"] = "observations.json"
    config = tmp_path / "collector.json"
    config.write_text(json.dumps(raw), encoding="utf-8")
    return config


def test_status_uses_saved_plan_and_missing_evidence_is_explicit(tmp_path: Path) -> None:
    config = load_burn_in_collector_config(_fixture(tmp_path, evidence=False))
    status = inspect_immutable_burn_in(
        config,
        project_root=tmp_path,
        evaluated_at=datetime(2026, 9, 14, 20, tzinfo=UTC),
    )
    assert status.plan_id == "plan-1"
    assert status.assessment.plan_id == "plan-1"
    assert status.assessment.observation_count == 0
    assert status.assessment.state.value == "IN_PROGRESS"
    assert not status.evidence_present
    assert not status.file_write_performed
    assert not status.network_used
    assert not status.broker_write_performed


def test_status_is_deterministic_and_rejects_added_authority(tmp_path: Path) -> None:
    config = load_burn_in_collector_config(_fixture(tmp_path))
    evaluated_at = datetime(2026, 9, 14, 20, tzinfo=UTC)
    first = inspect_immutable_burn_in(
        config, project_root=tmp_path, evaluated_at=evaluated_at
    )
    second = inspect_immutable_burn_in(
        config, project_root=tmp_path, evaluated_at=evaluated_at
    )
    assert first == second
    with pytest.raises(ValueError, match="immutable burn-in status"):
        replace(first, automatic_promotion_performed=True)


def test_status_rejects_noncausal_time_and_tampered_plan(tmp_path: Path) -> None:
    config_path = _fixture(tmp_path)
    config = load_burn_in_collector_config(config_path)
    with pytest.raises(ValueError, match="predates"):
        inspect_immutable_burn_in(
            config,
            project_root=tmp_path,
            evaluated_at=datetime(2026, 9, 11, tzinfo=UTC),
        )
    raw = json.loads((tmp_path / "plan.json").read_text(encoding="utf-8"))
    raw["live_trading_authorized"] = True
    (tmp_path / "plan.json").write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="prospective burn-in plan"):
        inspect_immutable_burn_in(
            config,
            project_root=tmp_path,
            evaluated_at=datetime(2026, 9, 14, 20, tzinfo=UTC),
        )


def test_cli_reports_immutable_plan_without_writes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = _fixture(tmp_path)
    assert main(
        [
            "desktop",
            "burn-in-status",
            "--config",
            str(config),
            "--as-of",
            "2026-09-14T20:00:00Z",
            "--project-root",
            str(tmp_path),
        ]
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["plan_id"] == "plan-1"
    assert payload["assessment"]["state"] == "IN_PROGRESS"
    assert payload["file_write_performed"] is False
    assert payload["network_used"] is False
