from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from trading_system.paper import RuntimeState
from trading_system.paper.burn_in import (
    BurnInState,
    PaperBurnInConfigError,
    PaperBurnInProtocol,
    build_burn_in_protocol,
    evaluate_burn_in,
    load_paper_burn_in_config,
)
from trading_system.paper.operator_control import OperatorHealth, PaperOperatorSnapshot

ROOT = Path(__file__).parents[2]
D = Decimal


def _snapshot(
    identity: str,
    observed_at: datetime,
    health: OperatorHealth = OperatorHealth.HEALTHY,
    incidents: int = 0,
    unmatched: int = 0,
) -> PaperOperatorSnapshot:
    return PaperOperatorSnapshot(
        identity,
        "paper-9b",
        observed_at,
        RuntimeState.SHADOW,
        health,
        () if health is OperatorHealth.HEALTHY else ("TEST_ATTENTION",),
        0,
        incidents,
        unmatched,
        observed_at,
        observed_at,
        "sha256:replication",
        "sha256:operator-config",
    )


def _protocol() -> PaperBurnInProtocol:
    config = load_paper_burn_in_config(ROOT / "config/paper.phase9b.v1.yaml")
    start = datetime(2026, 9, 10, 13, 30, tzinfo=UTC)
    return build_burn_in_protocol(
        config,
        session_id="paper-9b",
        declared_at=start - timedelta(days=1),
        window_start=start,
        window_end=start + timedelta(hours=2),
        minimum_observations=3,
        maximum_attention_fraction=D("0.34"),
        maximum_incidents=0,
        maximum_unmatched_reconciliations=0,
    )


def test_burn_in_pass_is_deterministic_and_has_no_authority() -> None:
    protocol = _protocol()
    start = protocol.window_start
    snapshots = tuple(_snapshot(f"snapshot-{index}", start + timedelta(minutes=index * 30))
                      for index in range(3))
    first = evaluate_burn_in(protocol, snapshots=snapshots, evaluated_at=protocol.window_end)
    second = evaluate_burn_in(
        protocol, snapshots=tuple(reversed(snapshots)), evaluated_at=protocol.window_end
    )
    assert first == second
    assert first.state is BurnInState.PASS
    assert not first.readiness_claimed
    assert not first.automatic_promotion_performed


def test_burn_in_fail_and_inconclusive_are_distinct() -> None:
    protocol = _protocol()
    start = protocol.window_start
    failing = (
        _snapshot("snapshot-1", start, OperatorHealth.ATTENTION, incidents=1),
        _snapshot("snapshot-2", start + timedelta(minutes=30)),
        _snapshot("snapshot-3", start + timedelta(minutes=60)),
    )
    failed = evaluate_burn_in(protocol, snapshots=failing, evaluated_at=protocol.window_end)
    assert failed.state is BurnInState.FAIL
    assert "INCIDENT_LIMIT_EXCEEDED" in failed.reason_codes
    incomplete = evaluate_burn_in(
        protocol,
        snapshots=failing[:1],
        evaluated_at=start + timedelta(minutes=15),
    )
    assert incomplete.state is BurnInState.INCONCLUSIVE
    assert "WINDOW_OPEN" in incomplete.reason_codes


def test_burn_in_rejects_future_or_cross_session_snapshots() -> None:
    protocol = _protocol()
    snapshot = _snapshot("snapshot-1", protocol.window_start)
    with pytest.raises(ValueError, match="causal protocol window"):
        evaluate_burn_in(
            protocol,
            snapshots=(snapshot,),
            evaluated_at=protocol.window_start - timedelta(seconds=1),
        )


def test_burn_in_config_rejects_defaults_and_promotion(tmp_path: Path) -> None:
    source = ROOT / "config/paper.phase9b.v1.yaml"
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["authority"]["default_thresholds_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(PaperBurnInConfigError, match="authority"):
        load_paper_burn_in_config(unsafe)
