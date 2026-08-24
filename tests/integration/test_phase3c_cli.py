from __future__ import annotations

from pathlib import Path

from trading_system.cli import main

ROOT = Path(__file__).parents[2]


def test_webull_verify_config_is_offline() -> None:
    assert main([
        "webull", "verify-config", "--config",
        str(ROOT / "config/webull.sandbox.v1.yaml"),
    ]) == 0
