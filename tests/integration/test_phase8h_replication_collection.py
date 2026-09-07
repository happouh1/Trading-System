from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from trading_system.persistence import SQLiteRepository
from trading_system.research.range_replication_collection import (
    ReplicationCollectionState,
    load_range_replication_collection_config,
)
from trading_system.research.range_replication_collection_registry import (
    RangeReplicationCollectionRegistry,
)
from trading_system.research.range_replication_protocol_registry import (
    RangeReplicationProtocolStatus,
)

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config/range_reclaim.phase8h.v1.yaml"
D = Decimal


def _protocol() -> RangeReplicationProtocolStatus:
    return RangeReplicationProtocolStatus(
        "protocol-1",
        "export-1",
        "report-1",
        "TEST_ONLY_REPLICATION_V1",
        "2026-09-07T12:00:00.000000Z",
        "sha256:definition",
        True,
    )


def test_test_only_collection_lifecycle_is_causal_append_only_and_restart_safe(
    tmp_path: Path,
) -> None:
    database = tmp_path / "phase8h.sqlite"
    config = load_range_replication_collection_config(CONFIG)
    registered = datetime(2026, 9, 7, 12, tzinfo=UTC)
    start = registered + timedelta(days=1)
    end = registered + timedelta(days=2)
    outcome_time = end + timedelta(days=1)
    with SQLiteRepository(database) as repository:
        repository.migrate()
        registry = RangeReplicationCollectionRegistry(repository)
        collection = registry.create(
            config,
            protocol=_protocol(),
            dataset_id="TEST_ONLY_REPLICATION_V1",
            registered_at=registered,
            collection_start=start,
            collection_end=end,
        )
        registry.start(collection.collection_id, start)
        prediction = registry.append_prediction(
            collection.collection_id,
            hypothesis_id="hypothesis-1",
            box_id="box-1",
            symbol="AAPL",
            known_at=start + timedelta(hours=1),
            earliest_outcome_at=outcome_time,
            evidence_hash="sha256:evidence",
        )
        with pytest.raises(ValueError, match="COLLECTION_CLOSED"):
            registry.append_outcome(
                collection.collection_id,
                prediction_id=prediction.prediction_id,
                known_at=outcome_time,
                gross_directional_return=D("0.5"),
                costs=(("spread", D("0.1")),),
                net_directional_return=D("0.4"),
                capacity_eligible=True,
                source_hash="sha256:source",
            )
        registry.close(collection.collection_id, end)
        with pytest.raises(ValueError, match="not yet available"):
            registry.append_outcome(
                collection.collection_id,
                prediction_id=prediction.prediction_id,
                known_at=end,
                gross_directional_return=D("0.5"),
                costs=(("spread", D("0.1")),),
                net_directional_return=D("0.4"),
                capacity_eligible=True,
                source_hash="sha256:source",
            )
        registry.append_outcome(
            collection.collection_id,
            prediction_id=prediction.prediction_id,
            known_at=outcome_time,
            gross_directional_return=D("0.5"),
            costs=(("spread", D("0.1")),),
            net_directional_return=D("0.4"),
            capacity_eligible=True,
            source_hash="sha256:source",
        )
        registry.complete_outcomes(collection.collection_id, outcome_time)
        manifest = registry.freeze(collection.collection_id, outcome_time + timedelta(seconds=1))
        assert manifest.prediction_count == manifest.outcome_count == 1
        assert not manifest.released_for_analysis
        assert not manifest.real_blinding_attested

    with SQLiteRepository(database) as repository:
        repository.migrate()
        status = RangeReplicationCollectionRegistry(repository).status(collection.collection_id)
        assert status.state is ReplicationCollectionState.FROZEN
        assert status.prediction_count == status.outcome_count == 1
        assert not status.released_for_analysis


def test_freeze_rejects_tampered_outcome_payload(tmp_path: Path) -> None:
    database = tmp_path / "tamper.sqlite"
    config = load_range_replication_collection_config(CONFIG)
    registered = datetime(2026, 9, 7, 12, tzinfo=UTC)
    start = registered + timedelta(days=1)
    end = registered + timedelta(days=2)
    outcome_time = end + timedelta(days=1)
    with SQLiteRepository(database) as repository:
        repository.migrate()
        registry = RangeReplicationCollectionRegistry(repository)
        collection = registry.create(
            config,
            protocol=_protocol(),
            dataset_id="TEST_ONLY_TAMPER",
            registered_at=registered,
            collection_start=start,
            collection_end=end,
        )
        registry.start(collection.collection_id, start)
        prediction = registry.append_prediction(
            collection.collection_id,
            hypothesis_id="hypothesis-1",
            box_id="box-1",
            symbol="AAPL",
            known_at=start,
            earliest_outcome_at=outcome_time,
            evidence_hash="sha256:evidence",
        )
        registry.close(collection.collection_id, end)
        registry.append_outcome(
            collection.collection_id,
            prediction_id=prediction.prediction_id,
            known_at=outcome_time,
            gross_directional_return=D("0.5"),
            costs=(("spread", D("0.1")),),
            net_directional_return=D("0.4"),
            capacity_eligible=True,
            source_hash="sha256:source",
        )
        registry.complete_outcomes(collection.collection_id, outcome_time)
        repository.connection.execute(
            """UPDATE range_replication_outcomes_blinded_test_only
               SET payload_json = '{}'"""
        )
        repository.connection.commit()
        with pytest.raises(ValueError, match="evidence is corrupt"):
            registry.freeze(collection.collection_id, outcome_time + timedelta(seconds=1))
