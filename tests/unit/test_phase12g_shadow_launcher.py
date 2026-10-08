from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from trading_system.cli import main
from trading_system.paper.prospective_shadow_launcher import (
    ProspectiveShadowLauncherConfigError,
    inspect_prospective_shadow_launcher,
    load_prospective_shadow_launcher_config,
)

ROOT = Path(__file__).parents[2]


def _project(tmp_path: Path, *, output: bool = False) -> Path:
    config = tmp_path / "config/burn-in.phase12g.launcher.v1.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "config/burn-in.phase12g.launcher.v1.json", config)
    for relative in (
        ".venv/Scripts/python.exe",
        "config/burn-in.phase12f.dashboard.v1.json",
        "scripts/render-phase12f-dashboard.ps1",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"test prerequisite")
    if output:
        target = tmp_path / ".operator-home/phase12f/burn-in-operations.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("<!doctype html>", encoding="utf-8")
    return tmp_path


def test_launcher_status_is_read_only_and_output_is_optional(tmp_path: Path) -> None:
    root = _project(tmp_path)
    config = load_prospective_shadow_launcher_config(
        root / "config/burn-in.phase12g.launcher.v1.json"
    )
    before = inspect_prospective_shadow_launcher(config, project_root=root)
    assert before.launcher_ready is True
    assert before.output_exists is False
    assert before.missing_paths == ()
    assert before.shortcut_name == "Trading System.lnk"
    assert before.scheduler_modified is False
    assert before.network_used is False
    assert before.credentials_loaded is False
    assert before.database_write_performed is False
    assert before.broker_write_performed is False
    assert before.order_api_available is False

    output = root / ".operator-home/phase12f/burn-in-operations.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("<!doctype html>", encoding="utf-8")
    after = inspect_prospective_shadow_launcher(config, project_root=root)
    assert after.launcher_ready is True
    assert after.output_exists is True
    assert after.status_id != before.status_id


def test_launcher_reports_missing_prerequisite(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / "scripts/render-phase12f-dashboard.ps1").unlink()
    config = load_prospective_shadow_launcher_config(
        root / "config/burn-in.phase12g.launcher.v1.json"
    )
    status = inspect_prospective_shadow_launcher(config, project_root=root)
    assert status.launcher_ready is False
    assert status.missing_paths == ("render_script",)


def test_launcher_rejects_authority_widening(tmp_path: Path) -> None:
    root = _project(tmp_path)
    path = root / "config/burn-in.phase12g.launcher.v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["authority"]["network_enabled"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ProspectiveShadowLauncherConfigError, match="invalid or unsafe"):
        load_prospective_shadow_launcher_config(path)


def test_launcher_status_cli_is_machine_readable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path, output=True)
    assert (
        main(
            [
                "paper",
                "scheduled-shadow-launcher-status",
                "--config",
                str(root / "config/burn-in.phase12g.launcher.v1.json"),
                "--project-root",
                str(root),
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["launcher_ready"] is True
    assert payload["output_exists"] is True
    assert payload["network_used"] is False
    assert payload["broker_write_performed"] is False
