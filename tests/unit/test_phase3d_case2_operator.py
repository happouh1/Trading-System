from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_case2_operator_blocks_before_credentials_without_case1_pass(
    tmp_path: Path,
) -> None:
    environment = dict(os.environ)
    environment["WEBULL_ENVIRONMENT"] = "SANDBOX"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "webull-case2-replace.py"),
            "--database",
            str(tmp_path / "case2.sqlite"),
            "--session-id",
            "case2-locked",
            "--config",
            str(ROOT / "config" / "webull.sandbox.v1.yaml"),
            "--smoke-config",
            str(ROOT / "config" / "webull.phase3d5.smoke.v1.json"),
            "--confirmation",
            "REPLACE-SELL-1-AAPL-STOP-1.00-TO-1.01-GTC-CORE-WEBULL-SANDBOX",
        ],
        capture_output=True,
        check=False,
        encoding="utf-8",
        env=environment,
    )
    assert result.returncode == 4
    assert json.loads(result.stdout) == {
        "broker_write_performed": False,
        "environment": "SANDBOX",
        "reason": "CASE1_PASS_REVIEW_REQUIRED",
        "session_id": "case2-locked",
    }
    assert "WEBULL_APP_KEY" not in result.stdout


def test_case2_seed_operator_blocks_before_credentials_without_case1_pass(
    tmp_path: Path,
) -> None:
    environment = dict(os.environ)
    environment["WEBULL_ENVIRONMENT"] = "SANDBOX"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "webull-case2-seed.py"),
            "--database",
            str(tmp_path / "case2.sqlite"),
            "--session-id",
            "case2-locked",
            "--config",
            str(ROOT / "config" / "webull.sandbox.v1.yaml"),
            "--confirmation",
            "PLACE-SELL-1-AAPL-STOP-1.00-GTC-CORE-FOR-CASE2-WEBULL-SANDBOX",
        ],
        capture_output=True,
        check=False,
        encoding="utf-8",
        env=environment,
    )
    assert result.returncode == 4
    assert json.loads(result.stdout) == {
        "broker_write_performed": False,
        "environment": "SANDBOX",
        "reason": "CASE1_PASS_REVIEW_REQUIRED",
        "session_id": "case2-locked",
    }
    assert "WEBULL_APP_KEY" not in result.stdout
