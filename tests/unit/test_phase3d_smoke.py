from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from trading_system.serialization import canonical_hash
from trading_system.webull.exit_config import load_exit_capabilities
from trading_system.webull.smoke import (
    SmokeCase,
    load_smoke_capture,
    load_smoke_config,
    smoke_plan,
)

ROOT = Path(__file__).parents[2]
SMOKE_CONFIG = ROOT / "config/webull.phase3d5.smoke.v1.json"


def capture_payload(case: SmokeCase = SmokeCase.LONG_STOP_LIFECYCLE) -> dict[str, object]:
    config = load_smoke_config(SMOKE_CONFIG)
    operations = config.required_evidence(case)
    return {
        "capture_version": "3D-SMOKE-CAPTURE.1.0",
        "session_id": "smoke-session",
        "case_id": case.value,
        "case_sequence": config.cases.index(case) + 1,
        "environment": "SANDBOX",
        "sdk_version": "2.0.17",
        "captured_at": "2026-01-05T15:00:00Z",
        "adjustment_factor": "1",
        "disposable_position_attested": True,
        "explicit_write_invocation_attested": True,
        "evidence": [
            {
                "operation": operation,
                "occurred_at": f"2026-01-05T14:{30 + index:02d}:00Z",
                "client_order_id": "smoke-client-1",
                "request": {"account_id": "[REDACTED]", "operation": operation},
                "response": {"status": "CAPTURED"},
                "observation": {"semantic_review_required": True},
            }
            for index, operation in enumerate(operations)
        ],
    }


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_smoke_plan_is_fixed_offline_and_does_not_promote_manifest() -> None:
    config = load_smoke_config(SMOKE_CONFIG)
    plan = smoke_plan(config)
    capabilities = load_exit_capabilities(
        ROOT / "config/webull.exit_capabilities.pending.v1.json"
    )
    cases = cast(tuple[dict[str, object], ...], plan["cases"])
    assert tuple(item["case_id"] for item in cases) == tuple(
        case.value for case in SmokeCase
    )
    assert plan["network_used"] is False
    assert plan["broker_write_performed"] is False
    assert plan["automatic_manifest_promotion"] is False
    assert capabilities.approved is False


def test_capture_is_deterministic_and_requires_ordered_evidence(tmp_path: Path) -> None:
    config = load_smoke_config(SMOKE_CONFIG)
    path = tmp_path / "capture.json"
    write_json(path, capture_payload())
    first = load_smoke_capture(path, config)
    second = load_smoke_capture(path, config)
    assert first.capture_id == second.capture_id
    assert first.capture_hash == second.capture_hash
    assert first.capture_hash == canonical_hash({
        "capture_version": "3D-SMOKE-CAPTURE.1.0",
        "session_id": first.session_id,
        "case_id": first.case.value,
        "case_sequence": first.case_sequence,
        "environment": "SANDBOX",
        "sdk_version": "2.0.17",
        "captured_at": first.captured_at,
        "adjustment_factor": first.adjustment_factor,
        "disposable_position_attested": True,
        "explicit_write_invocation_attested": True,
        "evidence": first.evidence,
    })

    payload = capture_payload()
    evidence = payload["evidence"]
    assert isinstance(evidence, list)
    evidence.reverse()
    write_json(path, payload)
    with pytest.raises(ValueError, match="ordered required evidence"):
        load_smoke_capture(path, config)


def test_capture_rejects_unredacted_sensitive_fields(tmp_path: Path) -> None:
    payload = capture_payload()
    evidence = payload["evidence"]
    assert isinstance(evidence, list)
    first = evidence[0]
    assert isinstance(first, dict)
    first["request"] = {"account_id": "actual-account-value"}
    path = tmp_path / "secret.json"
    write_json(path, payload)
    with pytest.raises(ValueError, match="unredacted sensitive"):
        load_smoke_capture(path, load_smoke_config(SMOKE_CONFIG))


def test_capture_rejects_future_evidence(tmp_path: Path) -> None:
    payload = capture_payload()
    evidence = payload["evidence"]
    assert isinstance(evidence, list)
    last = evidence[-1]
    assert isinstance(last, dict)
    last["occurred_at"] = datetime(2026, 1, 5, 16, tzinfo=UTC).isoformat()
    path = tmp_path / "future.json"
    write_json(path, payload)
    with pytest.raises(ValueError, match="cannot precede"):
        load_smoke_capture(path, load_smoke_config(SMOKE_CONFIG))
