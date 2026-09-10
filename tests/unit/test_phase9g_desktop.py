from __future__ import annotations

import json
from pathlib import Path

import pytest

from trading_system.cli import main
from trading_system.desktop import inspect_desktop_launcher, load_desktop_launch_config
from trading_system.desktop.launcher import DesktopLaunchConfigError

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config/desktop.phase9g.v1.yaml"


def _complete_root(root: Path) -> None:
    for relative in (
        ".venv/Scripts/python.exe",
        "config/thresholds.phase1e.v1.yaml",
        "config/paper.phase3b.v1.yaml",
        "config/webull.sandbox.v1.yaml",
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("fixture", encoding="utf-8")


def test_desktop_status_is_deterministic_read_only_and_fail_closed(tmp_path: Path) -> None:
    config = load_desktop_launch_config(CONFIG)
    first = inspect_desktop_launcher(config, project_root=tmp_path)
    assert not first.operator_home_ready
    assert first.missing_paths == ("paper_config", "python", "thresholds", "webull_config")
    _complete_root(tmp_path)
    second = inspect_desktop_launcher(config, project_root=tmp_path)
    assert second == inspect_desktop_launcher(config, project_root=tmp_path)
    assert second.operator_home_ready
    assert not second.scheduler_started
    assert not second.network_used
    assert not second.credentials_loaded
    assert not second.broker_write_performed
    assert not second.sandbox_execution_enabled
    assert not second.live_trading_enabled


def test_desktop_home_is_nontechnical_and_reports_disabled_trading(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _complete_root(tmp_path)
    assert main([
        "desktop", "home", "--config", str(CONFIG), "--project-root", str(tmp_path)
    ]) == 0
    output = capsys.readouterr().out
    assert "Operator Home" in output
    assert "Installation: READY" in output
    assert "Trading: DISABLED" in output
    assert "Broker writes: DISABLED" in output


def test_desktop_status_returns_attention_when_required_path_is_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([
        "desktop", "status", "--config", str(CONFIG), "--project-root", str(tmp_path)
    ]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["operator_home_ready"] is False
    assert payload["network_used"] is False


def test_config_rejects_authority_and_escaping_paths(tmp_path: Path) -> None:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["network_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(DesktopLaunchConfigError, match="authority"):
        load_desktop_launch_config(unsafe)
    raw["authority"]["network_enabled"] = False
    raw["paths"]["python"] = "../python.exe"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(DesktopLaunchConfigError, match="paths"):
        load_desktop_launch_config(unsafe)


def test_shortcut_scripts_are_repository_relative_and_contain_no_secrets() -> None:
    launcher = (ROOT / "scripts/start-trading-system.ps1").read_text(encoding="utf-8")
    installer = (ROOT / "scripts/install-desktop-shortcut.ps1").read_text(encoding="utf-8")
    combined = launcher + installer
    assert "WEBULL_APP_SECRET" not in combined
    assert "WEBULL_APP_KEY" not in combined
    assert "trading_system.cli desktop home" in launcher
    assert "WScript.Shell" in installer
    assert "start-trading-system.ps1" in installer
