"""Read-only Phase 12K shadow-evidence storage capacity inspection."""

from __future__ import annotations

import json
import shutil
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType

from trading_system.serialization import canonical_hash, canonical_json, deterministic_id


class ShadowStorageCapacityConfigError(ValueError):
    """The Phase 12K storage-capacity configuration is malformed or unsafe."""


@dataclass(frozen=True, slots=True)
class ShadowStorageCapacityConfig:
    database: str
    output: str
    warning_database_bytes: int
    critical_database_bytes: int
    warning_free_bytes: int
    critical_free_bytes: int
    warning_backup_copies: int
    critical_backup_copies: int
    config_hash: str
    monitor_version: str = "12K.1.0"


@dataclass(frozen=True, slots=True)
class ShadowStorageCapacityArtifact:
    artifact_id: str
    snapshot_id: str
    output_path: str
    content_hash: str
    status: str
    monitor_version: str = "12K.1.0"
    mode: str = "READ_ONLY_STORAGE_CAPACITY"
    database_write_performed: bool = False
    evidence_deleted: bool = False
    network_used: bool = False
    credentials_loaded: bool = False
    broker_write_performed: bool = False
    live_trading_enabled: bool = False
    automatic_promotion_enabled: bool = False


def load_shadow_storage_capacity_config(
    path: str | Path,
) -> ShadowStorageCapacityConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "monitor_version",
        "mode",
        "database",
        "output",
        "thresholds",
        "authority",
    }
    authority = {
        "database_read_enabled": True,
        "artifact_write_enabled": True,
        "evidence_deletion_enabled": False,
        "network_enabled": False,
        "credential_loading_enabled": False,
        "broker_writes_enabled": False,
        "live_trading_enabled": False,
        "automatic_promotion_enabled": False,
    }
    thresholds = raw.get("thresholds") if isinstance(raw, dict) else None
    threshold_names = {
        "warning_database_bytes",
        "critical_database_bytes",
        "warning_free_bytes",
        "critical_free_bytes",
        "warning_backup_copies",
        "critical_backup_copies",
    }
    if (
        not isinstance(raw, dict)
        or set(raw) != expected
        or raw["monitor_version"] != "12K.1.0"
        or raw["mode"] != "READ_ONLY_STORAGE_CAPACITY"
        or raw["authority"] != authority
        or not _relative(raw.get("database"))
        or not _relative(raw.get("output"))
        or not str(raw["output"]).endswith(".json")
        or not isinstance(thresholds, dict)
        or set(thresholds) != threshold_names
        or any(
            isinstance(thresholds.get(name), bool)
            or not isinstance(thresholds.get(name), int)
            or int(thresholds[name]) <= 0
            for name in threshold_names
        )
        or thresholds["warning_database_bytes"]
        >= thresholds["critical_database_bytes"]
        or thresholds["warning_free_bytes"] <= thresholds["critical_free_bytes"]
        or thresholds["warning_backup_copies"]
        <= thresholds["critical_backup_copies"]
    ):
        raise ShadowStorageCapacityConfigError(
            "Phase 12K storage-capacity configuration is invalid or unsafe"
        )
    return ShadowStorageCapacityConfig(
        str(raw["database"]),
        str(raw["output"]),
        int(thresholds["warning_database_bytes"]),
        int(thresholds["critical_database_bytes"]),
        int(thresholds["warning_free_bytes"]),
        int(thresholds["critical_free_bytes"]),
        int(thresholds["warning_backup_copies"]),
        int(thresholds["critical_backup_copies"]),
        canonical_hash(_freeze(raw)),
    )


def inspect_shadow_storage_capacity(
    config: ShadowStorageCapacityConfig,
    *,
    project_root: str | Path,
    as_of: datetime,
    database_override: str | Path | None = None,
) -> tuple[ShadowStorageCapacityArtifact, Mapping[str, object]]:
    """Inspect SQLite and filesystem headroom without changing retained evidence."""
    _utc(as_of)
    root = Path(project_root).resolve()
    database = _contained(
        root, config.database if database_override is None else database_override
    )
    if not database.is_file():
        raise FileNotFoundError(f"Phase 12K database does not exist: {database}")
    before = database.stat()
    with sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        page_count = _pragma_int(connection, "page_count")
        page_size = _pragma_int(connection, "page_size")
        freelist_count = _pragma_int(connection, "freelist_count")
    after = database.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError("Phase 12K source database changed during inspection")

    usage = shutil.disk_usage(database.parent)
    database_bytes = before.st_size
    backup_copies = usage.free // max(database_bytes, 1)
    sidecars = {
        "wal_bytes": _file_size(Path(f"{database}-wal")),
        "shm_bytes": _file_size(Path(f"{database}-shm")),
        "journal_bytes": _file_size(Path(f"{database}-journal")),
    }
    status, reasons = _status(
        config,
        database_bytes=database_bytes,
        free_bytes=usage.free,
        backup_copies=backup_copies,
    )
    body = {
        "as_of": as_of,
        "status": status,
        "reason_codes": reasons,
        "database": {
            "path": str(database),
            "bytes": database_bytes,
            "allocated_page_bytes": page_count * page_size,
            "page_count": page_count,
            "page_size": page_size,
            "freelist_count": freelist_count,
            "freelist_bytes": freelist_count * page_size,
            **sidecars,
        },
        "filesystem": {
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
            "database_copy_headroom": backup_copies,
        },
        "thresholds": {
            "warning_database_bytes": config.warning_database_bytes,
            "critical_database_bytes": config.critical_database_bytes,
            "warning_free_bytes": config.warning_free_bytes,
            "critical_free_bytes": config.critical_free_bytes,
            "warning_backup_copies": config.warning_backup_copies,
            "critical_backup_copies": config.critical_backup_copies,
        },
        "safety": {
            "database_write_performed": False,
            "evidence_deleted": False,
            "network_used": False,
            "credentials_loaded": False,
            "broker_write_performed": False,
            "live_trading_enabled": False,
            "automatic_promotion_enabled": False,
            "release_authorized": False,
        },
        "config_hash": config.config_hash,
    }
    snapshot_id = deterministic_id("shadow_storage_capacity_snapshot", body)
    snapshot: Mapping[str, object] = MappingProxyType(
        {**body, "snapshot_id": snapshot_id}
    )
    content = canonical_json(snapshot) + "\n"
    output = _contained(root, config.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(output)
    artifact = ShadowStorageCapacityArtifact(
        deterministic_id(
            "shadow_storage_capacity_artifact",
            (snapshot_id, config.config_hash, canonical_hash(content)),
        ),
        snapshot_id,
        str(output),
        canonical_hash(content),
        status,
    )
    return artifact, snapshot


def _status(
    config: ShadowStorageCapacityConfig,
    *,
    database_bytes: int,
    free_bytes: int,
    backup_copies: int,
) -> tuple[str, tuple[str, ...]]:
    critical: list[str] = []
    warning: list[str] = []
    if database_bytes >= config.critical_database_bytes:
        critical.append("DATABASE_SIZE_CRITICAL")
    elif database_bytes >= config.warning_database_bytes:
        warning.append("DATABASE_SIZE_WARNING")
    if free_bytes <= config.critical_free_bytes:
        critical.append("FILESYSTEM_FREE_CRITICAL")
    elif free_bytes <= config.warning_free_bytes:
        warning.append("FILESYSTEM_FREE_WARNING")
    if backup_copies < config.critical_backup_copies:
        critical.append("BACKUP_COPY_HEADROOM_CRITICAL")
    elif backup_copies < config.warning_backup_copies:
        warning.append("BACKUP_COPY_HEADROOM_WARNING")
    if critical:
        return "RED", tuple((*critical, *warning))
    if warning:
        return "AMBER", tuple(warning)
    return "GREEN", ("CAPACITY_WITHIN_LIMITS",)


def _pragma_int(connection: sqlite3.Connection, name: str) -> int:
    row = connection.execute(f"PRAGMA {name}").fetchone()
    if row is None or isinstance(row[0], bool) or not isinstance(row[0], int):
        raise RuntimeError(f"Phase 12K SQLite {name} is unavailable")
    return int(row[0])


def _file_size(path: Path) -> int:
    return path.stat().st_size if path.is_file() else 0


def _relative(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and not Path(value).is_absolute()
        and ".." not in Path(value).parts
    )


def _contained(root: Path, value: str | Path) -> Path:
    candidate = (root / value).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("Phase 12K path escapes the project root")
    return candidate


def _utc(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("Phase 12K as_of must be UTC")


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value
