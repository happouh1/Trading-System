from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from trading_system.paper import PaperMode, PaperRegistry, PaperSession, RuntimeState
from trading_system.paper.burn_in import (
    build_burn_in_protocol,
    evaluate_burn_in,
    load_paper_burn_in_config,
)
from trading_system.paper.burn_in_registry import PaperBurnInRegistry
from trading_system.paper.operator_control import load_paper_operator_config
from trading_system.paper.operator_control_registry import PaperOperatorRegistry
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]


def test_phase9b_persists_one_assessment_and_detects_tamper(tmp_path: Path) -> None:
    now = datetime(2026, 9, 10, 12, tzinfo=UTC)
    database = tmp_path / "phase9b.sqlite"
    burn_config = load_paper_burn_in_config(ROOT / "config/paper.phase9b.v1.yaml")
    operator_config = load_paper_operator_config(ROOT / "config/paper.phase9a.v1.yaml")
    with SQLiteRepository(database) as repository:
        repository.migrate()
        paper = PaperRegistry(repository)
        paper.insert_session(PaperSession(
            "paper-9b", now, PaperMode.SHADOW, "test-code", "sha256:paper-config",
            "test-revision", "XNYS-test",
        ))
        paper.transition("paper-9b", RuntimeState.STARTING, now, "start")
        paper.transition("paper-9b", RuntimeState.SHADOW, now, "shadow")
        protocol = build_burn_in_protocol(
            burn_config,
            session_id="paper-9b",
            declared_at=now,
            window_start=now + timedelta(hours=1),
            window_end=now + timedelta(hours=2),
            minimum_observations=2,
            maximum_attention_fraction=Decimal("0"),
            maximum_incidents=0,
            maximum_unmatched_reconciliations=0,
        )
        registry = PaperBurnInRegistry(repository)
        assert registry.register(protocol)
        assert not registry.register(protocol)
        operator = PaperOperatorRegistry(repository)
        snapshots = []
        for index in range(2):
            observed = protocol.window_start + timedelta(minutes=index * 30)
            paper.insert_heartbeat("paper-9b", observed)
            paper.insert_checkpoint(
                "paper-9b", f"candle-{index}", "1H", observed,
                f"sha256:state-{index}", {"index": index},
            )
            snapshot = operator.observe(
                operator_config,
                session_id="paper-9b",
                observed_at=observed,
                replication_status_hash="sha256:replication",
            )
            operator.record_snapshot(snapshot)
            snapshots.append(snapshot)
        assessment = evaluate_burn_in(
            protocol, snapshots=tuple(snapshots), evaluated_at=protocol.window_end
        )
        assert registry.record_assessment(assessment, tuple(snapshots))
        assert not registry.record_assessment(assessment, tuple(snapshots))
        repository.connection.execute(
            "UPDATE paper_operator_snapshots SET payload_json = '{}' WHERE snapshot_id = ?",
            (snapshots[0].snapshot_id,),
        )
        repository.connection.commit()
        second_protocol = build_burn_in_protocol(
            burn_config,
            session_id="paper-9b",
            declared_at=now - timedelta(minutes=1),
            window_start=now + timedelta(hours=1),
            window_end=now + timedelta(hours=3),
            minimum_observations=2,
            maximum_attention_fraction=Decimal("0"),
            maximum_incidents=0,
            maximum_unmatched_reconciliations=0,
        )
        registry.register(second_protocol)
        second_assessment = evaluate_burn_in(
            second_protocol,
            snapshots=tuple(snapshots),
            evaluated_at=second_protocol.window_end,
        )
        with pytest.raises(ValueError, match="snapshot dependency"):
            registry.record_assessment(second_assessment, tuple(snapshots))
