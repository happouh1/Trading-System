from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from trading_system.paper import PaperMode, PaperRegistry, PaperSession, RuntimeState
from trading_system.paper.operator_control import (
    OperatorHealth,
    build_operator_jobs,
    load_paper_operator_config,
)
from trading_system.paper.operator_control_registry import PaperOperatorRegistry
from trading_system.persistence import SQLiteRepository
from trading_system.research.range_replication_collection import (
    RangeReplicationFreezeManifest,
)
from trading_system.research.range_replication_runner import (
    load_range_replication_runner_config,
    run_replication_rehearsal,
)
from trading_system.research.range_replication_runner_registry import (
    RangeReplicationRunnerRegistry,
)
from trading_system.research.range_replication_statistics import (
    RangeReplicationHypothesis,
    load_range_replication_statistics_config,
)
from trading_system.serialization import canonical_hash, canonical_json

ROOT = Path(__file__).parents[2]
D = Decimal


def _insert_freeze(repository: SQLiteRepository) -> RangeReplicationFreezeManifest:
    frozen = datetime(2026, 9, 7, 12, tzinfo=UTC)
    freeze = RangeReplicationFreezeManifest(
        "freeze-integration-8k",
        "collection-integration-8k",
        frozen,
        12,
        12,
        "sha256:predictions",
        "sha256:outcomes",
        "sha256:manifest",
    )
    connection = repository.connection
    connection.execute(
        """INSERT INTO range_replication_collections
           (collection_id, protocol_id, dataset_id, registered_at, collection_start,
            collection_end, state, config_hash, payload_json, payload_hash)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            freeze.collection_id, "protocol", "TEST_ONLY_8K_INTEGRATION",
            "2026-09-01T12:00:00.000000Z", "2026-09-02T12:00:00.000000Z",
            "2026-09-06T12:00:00.000000Z", "FROZEN", "sha256:collection-config",
            "{}", canonical_hash({}),
        ),
    )
    connection.execute(
        """INSERT INTO range_replication_collection_freezes
           (freeze_id, collection_id, frozen_at, prediction_root_hash, outcome_root_hash,
            manifest_hash, payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            freeze.freeze_id, freeze.collection_id, "2026-09-07T12:00:00.000000Z",
            freeze.prediction_root_hash, freeze.outcome_root_hash, freeze.manifest_hash,
            canonical_json(freeze), canonical_hash(freeze),
        ),
    )
    connection.commit()
    return freeze


def test_phase8k_one_analysis_restart_and_tamper_detection(tmp_path: Path) -> None:
    database = tmp_path / "combined.sqlite"
    runner_config = load_range_replication_runner_config(
        ROOT / "config/range_reclaim.phase8k.v1.yaml"
    )
    statistics_config = load_range_replication_statistics_config(
        ROOT / "config/range_reclaim.phase8g.v1.yaml"
    )
    hypothesis = RangeReplicationHypothesis(
        "h-a", tuple((f"box-{index:02d}", D("0.3")) for index in range(12))
    )
    with SQLiteRepository(database) as repository:
        repository.migrate()
        freeze = _insert_freeze(repository)
        run, results = run_replication_rehearsal(
            runner_config,
            statistics_config,
            freeze=freeze,
            hypotheses=(hypothesis,),
            executed_at=freeze.frozen_at + timedelta(days=1),
            familywise_alpha=D("0.05"),
            economic_threshold_net_r=D("0.2"),
            minimum_total_clusters=10,
            minimum_nonzero_clusters=10,
        )
        registry = RangeReplicationRunnerRegistry(repository)
        assert registry.record(run, results)
        assert not registry.record(run, results)
        repository.connection.execute(
            "UPDATE range_replication_runs SET payload_json = '{}' WHERE run_id = ?",
            (run.run_id,),
        )
        repository.connection.commit()
        with pytest.raises(ValueError, match="corrupt"):
            registry.result_hashes(run.run_id)


def test_phase9a_snapshot_is_read_only_restart_safe_and_fail_closed(tmp_path: Path) -> None:
    database = tmp_path / "paper.sqlite"
    now = datetime(2026, 9, 7, 15, tzinfo=UTC)
    config = load_paper_operator_config(ROOT / "config/paper.phase9a.v1.yaml")
    with SQLiteRepository(database) as repository:
        repository.migrate()
        paper = PaperRegistry(repository)
        paper.insert_session(PaperSession(
            "paper-9a", now - timedelta(hours=1), PaperMode.SHADOW, "test-code",
            "sha256:paper-config", "test-revision", "XNYS-test",
        ))
        paper.transition("paper-9a", RuntimeState.STARTING, now - timedelta(minutes=59), "start")
        paper.transition("paper-9a", RuntimeState.SHADOW, now - timedelta(minutes=58), "ready")
        paper.insert_heartbeat("paper-9a", now - timedelta(minutes=1))
        paper.insert_checkpoint(
            "paper-9a", "candle-1", "1D", now - timedelta(minutes=2),
            "sha256:state", {"known_at": now - timedelta(minutes=2)},
        )
        registry = PaperOperatorRegistry(repository)
        snapshot = registry.observe(
            config,
            session_id="paper-9a",
            observed_at=now,
            replication_status_hash="sha256:opaque-replication-status",
        )
        assert snapshot.health is OperatorHealth.HEALTHY
        assert not snapshot.broker_write_performed
        assert registry.record_snapshot(snapshot)
        assert not registry.record_snapshot(snapshot)
        jobs = build_operator_jobs(config, session_id="paper-9a", anchor_at=now)
        assert registry.record_jobs(jobs) == 3
        assert registry.record_jobs(jobs) == 0
        assert paper.current_state("paper-9a") is RuntimeState.SHADOW


def test_phase9a_missing_inputs_and_halt_are_visible(tmp_path: Path) -> None:
    config = load_paper_operator_config(ROOT / "config/paper.phase9a.v1.yaml")
    now = datetime(2026, 9, 7, 15, tzinfo=UTC)
    with SQLiteRepository(tmp_path / "halted.sqlite") as repository:
        repository.migrate()
        paper = PaperRegistry(repository)
        paper.insert_session(PaperSession(
            "paper-halted", now, PaperMode.SHADOW, "test-code", "sha256:config",
            "revision", "calendar",
        ))
        paper.transition("paper-halted", RuntimeState.HALTED, now, "operator halt")
        snapshot = PaperOperatorRegistry(repository).observe(
            config, session_id="paper-halted", observed_at=now
        )
        assert snapshot.health is OperatorHealth.HALTED
        assert snapshot.reason_codes == (
            "CHECKPOINT_MISSING",
            "HEARTBEAT_MISSING",
            "REPLICATION_STATUS_UNAVAILABLE",
        )
