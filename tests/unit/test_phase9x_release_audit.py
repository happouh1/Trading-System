from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Mapping
from pathlib import Path

import pytest

from trading_system.cli.main import main
from trading_system.desktop.release_audit import (
    ReleaseAuditConfigError,
    ReleaseAuditState,
    audit_release_readiness,
    load_release_audit_config,
)

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config/desktop.phase9x.v1.yaml"


def _inventory_paths() -> tuple[Path, ...]:
    config = load_release_audit_config(CONFIG)
    paths: set[str] = set()
    for section in ("required_components", "safety_configs"):
        values = config.values[section]
        assert isinstance(values, Mapping)
        paths.update(str(value) for value in values.values())
    documents = config.values["required_documents"]
    assert isinstance(documents, tuple)
    paths.update(str(value) for value in documents)
    return tuple(ROOT / path for path in sorted(paths))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_repository_is_ready_and_audit_is_deterministic_and_read_only() -> None:
    before = {path: _digest(path) for path in _inventory_paths()}
    config = load_release_audit_config(CONFIG)
    first = audit_release_readiness(config, project_root=ROOT)
    second = audit_release_readiness(config, project_root=ROOT)
    after = {path: _digest(path) for path in _inventory_paths()}

    assert first == second
    assert first.state is ReleaseAuditState.READY_FOR_PROSPECTIVE_SANDBOX_BURN_IN
    assert not first.blockers
    assert all(component.valid for component in first.components)
    assert before == after
    assert first.read_only
    assert not first.sandbox_burn_in_authorized
    assert not first.production_release_authorized
    assert not first.process_launched
    assert not first.network_used
    assert not first.credentials_loaded
    assert not first.broker_write_performed
    assert not first.live_trading_enabled


def test_missing_repository_inventory_fails_closed(tmp_path: Path) -> None:
    assessment = audit_release_readiness(
        load_release_audit_config(CONFIG), project_root=tmp_path
    )
    assert assessment.state is ReleaseAuditState.BLOCKED
    assert any(blocker.endswith(":FILE_MISSING") for blocker in assessment.blockers)
    assert "SAFETY_CONFIGURATION_INVALID" in assessment.blockers


def test_weakened_authority_configuration_is_rejected(tmp_path: Path) -> None:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["network_enabled"] = True
    path = tmp_path / "weakened.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ReleaseAuditConfigError, match="authority"):
        load_release_audit_config(path)


def test_unsorted_inventory_configuration_is_rejected(tmp_path: Path) -> None:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["required_documents"] = list(reversed(raw["required_documents"]))
    path = tmp_path / "unsorted.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ReleaseAuditConfigError, match="inventory"):
        load_release_audit_config(path)


def test_changed_webull_safety_configuration_blocks_readiness(tmp_path: Path) -> None:
    for source in _inventory_paths():
        target = tmp_path / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    webull_path = tmp_path / "config/webull.sandbox.v1.yaml"
    raw = json.loads(webull_path.read_text(encoding="utf-8"))
    raw["api_endpoint"] = "api.webull.com"
    webull_path.write_text(json.dumps(raw), encoding="utf-8")

    assessment = audit_release_readiness(
        load_release_audit_config(CONFIG), project_root=tmp_path
    )
    assert assessment.state is ReleaseAuditState.BLOCKED
    assert "WEBULL_ENDPOINT_NOT_SANDBOX" in assessment.blockers
    assert not assessment.sandbox_burn_in_authorized


def test_release_audit_cli_reports_ready(capsys: pytest.CaptureFixture[str]) -> None:
    result = main(
        [
            "desktop",
            "release-audit",
            "--config",
            str(CONFIG),
            "--project-root",
            str(ROOT),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert payload["state"] == "READY_FOR_PROSPECTIVE_SANDBOX_BURN_IN"
    assert payload["sandbox_burn_in_authorized"] is False
    assert payload["production_release_authorized"] is False
