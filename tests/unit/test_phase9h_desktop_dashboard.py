from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from trading_system.cli import main
from trading_system.desktop import (
    inspect_desktop_launcher,
    load_desktop_dashboard_config,
    load_desktop_launch_config,
    render_desktop_dashboard,
)
from trading_system.desktop.dashboard import DesktopDashboardConfigError

ROOT = Path(__file__).parents[2]
DASHBOARD_CONFIG = ROOT / "config/desktop.phase9h.v1.yaml"
OPERATOR_CONFIG = ROOT / "config/desktop.phase9g.v1.yaml"


def _complete_root(root: Path) -> None:
    for source in (
        "config/desktop.phase9g.v1.yaml",
        "config/thresholds.phase1e.v1.yaml",
        "config/paper.phase3b.v1.yaml",
        "config/webull.sandbox.v1.yaml",
    ):
        target = root / source
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / source).read_bytes())
    python = root / ".venv/Scripts/python.exe"
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_text("fixture", encoding="utf-8")


def test_dashboard_render_is_deterministic_local_and_read_only(tmp_path: Path) -> None:
    _complete_root(tmp_path)
    dashboard_config = load_desktop_dashboard_config(DASHBOARD_CONFIG)
    launch_config = load_desktop_launch_config(OPERATOR_CONFIG)
    status = inspect_desktop_launcher(launch_config, project_root=tmp_path)
    first = render_desktop_dashboard(dashboard_config, status, project_root=tmp_path)
    first_bytes = Path(first.output_path).read_bytes()
    second = render_desktop_dashboard(dashboard_config, status, project_root=tmp_path)
    assert first == second
    assert Path(second.output_path).read_bytes() == first_bytes
    assert not second.network_used
    assert not second.credentials_loaded
    assert not second.broker_write_performed
    assert not second.scheduler_started
    assert not second.sandbox_execution_enabled
    assert not second.live_trading_enabled


def test_dashboard_html_is_accessible_static_and_secret_free(tmp_path: Path) -> None:
    _complete_root(tmp_path)
    status = inspect_desktop_launcher(
        load_desktop_launch_config(OPERATOR_CONFIG), project_root=tmp_path
    )
    artifact = render_desktop_dashboard(
        load_desktop_dashboard_config(DASHBOARD_CONFIG), status, project_root=tmp_path
    )
    document = Path(artifact.output_path).read_text(encoding="utf-8")
    assert '<html lang="en">' in document
    assert '<meta name="viewport"' in document
    assert "System readiness" in document
    assert "Trading</span><strong class=\"disabled\">DISABLED" in document
    assert "<script" not in document
    assert "http://" not in document
    assert "https://" not in document
    assert "WEBULL_APP_KEY" not in document
    assert "WEBULL_APP_SECRET" not in document


def test_dashboard_shows_missing_components_without_enabling_authority(tmp_path: Path) -> None:
    status = inspect_desktop_launcher(
        load_desktop_launch_config(OPERATOR_CONFIG), project_root=tmp_path
    )
    artifact = render_desktop_dashboard(
        load_desktop_dashboard_config(DASHBOARD_CONFIG), status, project_root=tmp_path
    )
    document = Path(artifact.output_path).read_text(encoding="utf-8")
    assert "NEEDS ATTENTION" in document
    assert document.count("MISSING") == 4
    assert document.count("DISABLED") == 5


def test_dashboard_cli_renders_machine_readable_artifact(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _complete_root(tmp_path)
    assert main([
        "desktop",
        "render",
        "--config",
        str(DASHBOARD_CONFIG),
        "--project-root",
        str(tmp_path),
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "READ_ONLY_LOCAL_DASHBOARD"
    assert payload["network_used"] is False
    assert Path(payload["output_path"]).is_file()


def test_dashboard_config_rejects_authority_and_escaping_output(tmp_path: Path) -> None:
    raw = json.loads(DASHBOARD_CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["broker_writes_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(DesktopDashboardConfigError, match="authority"):
        load_desktop_dashboard_config(unsafe)
    raw["authority"]["broker_writes_enabled"] = False
    raw["output"] = "../outside.html"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(DesktopDashboardConfigError, match="output"):
        load_desktop_dashboard_config(unsafe)


def test_dashboard_artifact_rejects_retrospective_authority(tmp_path: Path) -> None:
    _complete_root(tmp_path)
    status = inspect_desktop_launcher(
        load_desktop_launch_config(OPERATOR_CONFIG), project_root=tmp_path
    )
    artifact = render_desktop_dashboard(
        load_desktop_dashboard_config(DASHBOARD_CONFIG), status, project_root=tmp_path
    )
    with pytest.raises(ValueError, match="dashboard artifact"):
        replace(artifact, broker_write_performed=True)
