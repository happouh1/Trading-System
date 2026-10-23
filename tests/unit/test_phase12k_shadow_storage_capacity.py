from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from trading_system.paper.prospective_shadow_storage_capacity import (
    ShadowStorageCapacityConfigError,
    inspect_shadow_storage_capacity,
    load_shadow_storage_capacity_config,
)

NOW = datetime(2026, 10, 22, 23, tzinfo=UTC)
GIB = 1024**3


def _config(root: Path, *, broker_writes: bool = False) -> Path:
    path = root / "capacity.json"
    path.write_text(
        json.dumps(
            {
                "monitor_version": "12K.1.0",
                "mode": "READ_ONLY_STORAGE_CAPACITY",
                "database": "evidence.sqlite",
                "output": "output/capacity.json",
                "thresholds": {
                    "warning_database_bytes": 8 * GIB,
                    "critical_database_bytes": 16 * GIB,
                    "warning_free_bytes": 50 * GIB,
                    "critical_free_bytes": 20 * GIB,
                    "warning_backup_copies": 5,
                    "critical_backup_copies": 3,
                },
                "authority": {
                    "database_read_enabled": True,
                    "artifact_write_enabled": True,
                    "evidence_deletion_enabled": False,
                    "network_enabled": False,
                    "credential_loading_enabled": False,
                    "broker_writes_enabled": broker_writes,
                    "live_trading_enabled": False,
                    "automatic_promotion_enabled": False,
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _database(root: Path) -> Path:
    path = root / "evidence.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE evidence (identity TEXT PRIMARY KEY, payload TEXT)")
        connection.execute("INSERT INTO evidence VALUES ('one','immutable')")
        connection.commit()
    return path


def _disk(total: int, free: int) -> SimpleNamespace:
    return SimpleNamespace(total=total, used=total - free, free=free)


def test_phase12k_rejects_broker_authority(tmp_path: Path) -> None:
    with pytest.raises(ShadowStorageCapacityConfigError, match="invalid or unsafe"):
        load_shadow_storage_capacity_config(_config(tmp_path, broker_writes=True))


def test_phase12k_reads_sqlite_without_mutating_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _database(tmp_path)
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    monkeypatch.setattr(
        "trading_system.paper.prospective_shadow_storage_capacity.shutil.disk_usage",
        lambda _path: _disk(1000 * GIB, 600 * GIB),
    )
    config = load_shadow_storage_capacity_config(_config(tmp_path))

    artifact, snapshot = inspect_shadow_storage_capacity(
        config, project_root=tmp_path, as_of=NOW
    )

    assert artifact.status == "GREEN"
    assert snapshot["reason_codes"] == ("CAPACITY_WITHIN_LIMITS",)
    assert snapshot["database"]["bytes"] == database.stat().st_size  # type: ignore[index]
    assert snapshot["database"]["page_count"] > 0  # type: ignore[index]
    assert snapshot["filesystem"]["database_copy_headroom"] > 5  # type: ignore[index]
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
    assert not artifact.database_write_performed
    assert not artifact.evidence_deleted
    assert not artifact.network_used
    assert not artifact.broker_write_performed
    output = Path(artifact.output_path).read_text(encoding="utf-8")
    assert "CAPACITY_WITHIN_LIMITS" in output


def test_phase12k_warns_before_critical_capacity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _database(tmp_path)
    monkeypatch.setattr(
        "trading_system.paper.prospective_shadow_storage_capacity.shutil.disk_usage",
        lambda _path: _disk(100 * GIB, 40 * GIB),
    )
    config = load_shadow_storage_capacity_config(_config(tmp_path))

    artifact, snapshot = inspect_shadow_storage_capacity(
        config, project_root=tmp_path, as_of=NOW
    )

    assert artifact.status == "AMBER"
    reasons = cast(tuple[str, ...], snapshot["reason_codes"])
    assert "FILESYSTEM_FREE_WARNING" in reasons


def test_phase12k_fails_closed_when_backup_headroom_is_critical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _database(tmp_path)
    monkeypatch.setattr(
        "trading_system.paper.prospective_shadow_storage_capacity.shutil.disk_usage",
        lambda _path: _disk(100 * GIB, database.stat().st_size * 2),
    )
    config = load_shadow_storage_capacity_config(_config(tmp_path))

    artifact, snapshot = inspect_shadow_storage_capacity(
        config, project_root=tmp_path, as_of=NOW
    )

    assert artifact.status == "RED"
    reasons = cast(tuple[str, ...], snapshot["reason_codes"])
    assert "BACKUP_COPY_HEADROOM_CRITICAL" in reasons


def test_phase12k_is_deterministic_for_same_capacity_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _database(tmp_path)
    monkeypatch.setattr(
        "trading_system.paper.prospective_shadow_storage_capacity.shutil.disk_usage",
        lambda _path: _disk(1000 * GIB, 600 * GIB),
    )
    config = load_shadow_storage_capacity_config(_config(tmp_path))

    first, _ = inspect_shadow_storage_capacity(config, project_root=tmp_path, as_of=NOW)
    second, _ = inspect_shadow_storage_capacity(config, project_root=tmp_path, as_of=NOW)

    assert first.snapshot_id == second.snapshot_id
    assert first.content_hash == second.content_hash
