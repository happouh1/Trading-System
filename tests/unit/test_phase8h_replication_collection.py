from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from trading_system.research.range_replication_collection import (
    RangeReplicationCollectionConfigError,
    ReplicationCollectionState,
    build_test_collection,
    load_range_replication_collection_config,
)

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config/range_reclaim.phase8h.v1.yaml"


def test_collection_identity_is_deterministic_and_non_authoritative() -> None:
    config = load_range_replication_collection_config(CONFIG)
    registered = datetime(2026, 9, 7, 12, tzinfo=UTC)
    first = build_test_collection(
        config,
        protocol_id="protocol-1",
        dataset_id="TEST_ONLY_REPLICATION_V1",
        registered_at=registered,
        collection_start=registered + timedelta(days=1),
        collection_end=registered + timedelta(days=31),
    )
    second = build_test_collection(
        config,
        protocol_id="protocol-1",
        dataset_id="TEST_ONLY_REPLICATION_V1",
        registered_at=registered,
        collection_start=registered + timedelta(days=1),
        collection_end=registered + timedelta(days=31),
    )
    assert first == second
    assert first.state is ReplicationCollectionState.REGISTERED
    assert first.test_only
    assert not first.real_blinding_attested
    assert not first.production_authority


def test_collection_rejects_real_dataset_identity_and_invalid_time_order() -> None:
    config = load_range_replication_collection_config(CONFIG)
    registered = datetime(2026, 9, 7, 12, tzinfo=UTC)
    with pytest.raises(ValueError, match="invalid Phase 8H collection"):
        build_test_collection(
            config,
            protocol_id="protocol-1",
            dataset_id="REAL_DATASET",
            registered_at=registered,
            collection_start=registered + timedelta(days=1),
            collection_end=registered + timedelta(days=2),
        )
    with pytest.raises(ValueError, match="invalid Phase 8H collection"):
        build_test_collection(
            config,
            protocol_id="protocol-1",
            dataset_id="TEST_ONLY_BAD_TIME",
            registered_at=registered,
            collection_start=registered,
            collection_end=registered + timedelta(days=2),
        )


def test_config_rejects_real_collection_and_outcome_read_authority(tmp_path: Path) -> None:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["real_collection_enabled"] = True
    path = tmp_path / "unsafe.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RangeReplicationCollectionConfigError, match="authority"):
        load_range_replication_collection_config(path)

    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["rules"]["real_blinding_claimed"] = True
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RangeReplicationCollectionConfigError, match="policy"):
        load_range_replication_collection_config(path)
