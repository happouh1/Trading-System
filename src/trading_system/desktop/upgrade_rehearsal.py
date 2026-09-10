"""Phase 9L test-only backup, migration, and restore rehearsal."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType

from trading_system.desktop.upgrade_plan import load_upgrade_plan_config
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, deterministic_id


class UpgradeRehearsalConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class UpgradeRehearsalConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class UpgradeRehearsalResult:
    rehearsal_id: str
    status: str
    source_revision: str
    source_hash_before: str
    source_hash_after: str
    backup_hash: str
    upgraded_hash: str
    restored_hash: str
    original_tables: tuple[str, ...]
    required_tables: tuple[str, ...]
    missing_required_tables: tuple[str, ...]
    preserved_row_counts: tuple[tuple[str, int], ...]
    upgraded_quick_check: tuple[str, ...]
    restored_quick_check: tuple[str, ...]
    upgraded_foreign_key_violations: int
    restored_foreign_key_violations: int
    backup_path: str
    upgraded_path: str
    restored_path: str
    config_hash: str
    rehearsal_version: str = "9L.1.0"
    test_only: bool = True
    backup_created: bool = True
    copy_migration_executed: bool = True
    source_database_write_performed: bool = False
    restore_promoted: bool = False
    production_migration_executed: bool = False
    network_used: bool = False
    credentials_loaded: bool = False
    broker_write_performed: bool = False
    sandbox_execution_enabled: bool = False
    live_trading_enabled: bool = False

    def __post_init__(self) -> None:
        hashes = (
            self.source_hash_before,
            self.source_hash_after,
            self.backup_hash,
            self.upgraded_hash,
            self.restored_hash,
        )
        if (
            not self.rehearsal_id
            or self.status != "VERIFIED"
            or not self.source_revision.startswith("TEST_ONLY_")
            or any(not value.startswith("sha256:") for value in hashes)
            or self.source_hash_before != self.source_hash_after
            or self.backup_hash != self.restored_hash
            or self.original_tables != tuple(sorted(set(self.original_tables)))
            or self.required_tables != tuple(sorted(set(self.required_tables)))
            or self.missing_required_tables
            or self.preserved_row_counts != tuple(sorted(self.preserved_row_counts))
            or self.upgraded_quick_check != ("ok",)
            or self.restored_quick_check != ("ok",)
            or self.upgraded_foreign_key_violations
            or self.restored_foreign_key_violations
            or not all((self.backup_path, self.upgraded_path, self.restored_path))
            or not self.config_hash.startswith("sha256:")
            or self.rehearsal_version != "9L.1.0"
            or not self.test_only
            or not self.backup_created
            or not self.copy_migration_executed
            or any(
                (
                    self.source_database_write_performed,
                    self.restore_promoted,
                    self.production_migration_executed,
                    self.network_used,
                    self.credentials_loaded,
                    self.broker_write_performed,
                    self.sandbox_execution_enabled,
                    self.live_trading_enabled,
                )
            )
        ):
            raise ValueError("invalid Phase 9L upgrade rehearsal result")


def load_upgrade_rehearsal_config(path: str | Path) -> UpgradeRehearsalConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "rehearsal_version",
        "mode",
        "upgrade_config",
        "allowed_source_root",
        "output_directory",
        "verification",
        "authority",
    }:
        raise UpgradeRehearsalConfigError("Phase 9L configuration keys are invalid")
    if (
        raw["rehearsal_version"] != "9L.1.0"
        or raw["mode"] != "TEST_ONLY_COPY_MIGRATION_REHEARSAL"
    ):
        raise UpgradeRehearsalConfigError("Phase 9L mode is invalid")
    for key in ("upgrade_config", "allowed_source_root", "output_directory"):
        if not _relative(raw[key]):
            raise UpgradeRehearsalConfigError(f"Phase 9L {key} path is invalid")
    if raw["verification"] != {
        "sqlite_quick_check": True,
        "foreign_key_check": True,
        "preserve_source_hash": True,
        "preserve_existing_row_counts": True,
        "verify_required_tables": True,
        "verify_restore_hash": True,
    }:
        raise UpgradeRehearsalConfigError("Phase 9L verification controls are invalid")
    if raw["authority"] != {
        "real_database_source_enabled": False,
        "source_database_write_enabled": False,
        "restore_promotion_enabled": False,
        "production_migration_enabled": False,
        "network_enabled": False,
        "credential_loading_enabled": False,
        "broker_writes_enabled": False,
        "sandbox_execution_enabled": False,
        "live_trading_enabled": False,
    }:
        raise UpgradeRehearsalConfigError("Phase 9L authority must remain test-only")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return UpgradeRehearsalConfig(MappingProxyType(frozen), canonical_hash(raw))


def rehearse_schema_upgrade(
    config: UpgradeRehearsalConfig,
    *,
    project_root: str | Path,
    source_path: str,
    source_revision: str,
) -> UpgradeRehearsalResult:
    if not source_revision.startswith("TEST_ONLY_"):
        raise ValueError("Phase 9L source revision must begin with TEST_ONLY_")
    root = Path(project_root).resolve()
    allowed = _contained_directory(root, config.values["allowed_source_root"])
    source = _contained_file(root, source_path)
    if allowed != source.parent and allowed not in source.parents:
        raise ValueError("Phase 9L source must be inside the test-only fixture directory")
    output_root = _contained_directory(root, config.values["output_directory"])
    if output_root == source.parent or output_root in source.parents:
        raise ValueError("Phase 9L output cannot contain the source fixture")
    upgrade_value = config.values["upgrade_config"]
    if not isinstance(upgrade_value, str):
        raise TypeError("validated Phase 9L upgrade config path must be text")
    upgrade = load_upgrade_plan_config(root / upgrade_value)
    required_value = upgrade.values["required_tables"]
    if not isinstance(required_value, tuple):
        raise TypeError("validated Phase 9K required tables must be a tuple")
    required = tuple(sorted(str(value) for value in required_value))
    source_hash = _hash_file(source)
    original_rows = _table_row_counts(source)
    rehearsal_id = deterministic_id(
        "schema_upgrade_rehearsal",
        (source_path, source_revision, source_hash, required, config.config_hash),
    )
    output_root.mkdir(parents=True, exist_ok=True)
    target = output_root / rehearsal_id
    stage = Path(tempfile.mkdtemp(prefix=".stage-", dir=output_root))
    try:
        backup = stage / "backup.sqlite"
        upgraded = stage / "upgraded.sqlite"
        restored = stage / "restored.sqlite"
        _sqlite_backup(source, backup)
        shutil.copyfile(backup, upgraded)
        with SQLiteRepository(upgraded) as repository:
            repository.migrate()
        shutil.copyfile(backup, restored)
        source_hash_after = _hash_file(source)
        if source_hash_after != source_hash:
            raise ValueError("Phase 9L source changed during rehearsal")
        result = _verified_result(
            config=config,
            rehearsal_id=rehearsal_id,
            source_revision=source_revision,
            source_hash=source_hash,
            source_hash_after=source_hash_after,
            original_rows=original_rows,
            required=required,
            backup=backup,
            upgraded=upgraded,
            restored=restored,
            target=target,
            root=root,
        )
        if target.exists():
            _verify_existing(target, backup, upgraded, restored)
        else:
            stage.replace(target)
        return result
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def _verified_result(
    *,
    config: UpgradeRehearsalConfig,
    rehearsal_id: str,
    source_revision: str,
    source_hash: str,
    source_hash_after: str,
    original_rows: tuple[tuple[str, int], ...],
    required: tuple[str, ...],
    backup: Path,
    upgraded: Path,
    restored: Path,
    target: Path,
    root: Path,
) -> UpgradeRehearsalResult:
    backup_hash = _hash_file(backup)
    upgraded_hash = _hash_file(upgraded)
    restored_hash = _hash_file(restored)
    if restored_hash != backup_hash:
        raise ValueError("Phase 9L restore hash mismatch")
    upgraded_original_rows = _table_row_counts(
        upgraded, tables=tuple(name for name, _ in original_rows)
    )
    if upgraded_original_rows != original_rows:
        raise ValueError("Phase 9L migration changed existing table row counts")
    upgraded_tables = _table_names(upgraded)
    missing = tuple(name for name in required if name not in upgraded_tables)
    upgraded_quick, upgraded_foreign = _sqlite_checks(upgraded)
    restored_quick, restored_foreign = _sqlite_checks(restored)
    if missing or upgraded_quick != ("ok",) or restored_quick != ("ok",):
        raise ValueError("Phase 9L copy verification failed")
    if upgraded_foreign or restored_foreign:
        raise ValueError("Phase 9L copy has foreign-key violations")
    target_relative = target.relative_to(root)
    identity = (
        rehearsal_id,
        source_revision,
        source_hash,
        source_hash_after,
        backup_hash,
        upgraded_hash,
        restored_hash,
        original_rows,
        required,
        config.config_hash,
    )
    return UpgradeRehearsalResult(
        deterministic_id("schema_upgrade_rehearsal_result", identity),
        "VERIFIED",
        source_revision,
        source_hash,
        source_hash_after,
        backup_hash,
        upgraded_hash,
        restored_hash,
        tuple(name for name, _ in original_rows),
        required,
        missing,
        original_rows,
        upgraded_quick,
        restored_quick,
        upgraded_foreign,
        restored_foreign,
        (target_relative / "backup.sqlite").as_posix(),
        (target_relative / "upgraded.sqlite").as_posix(),
        (target_relative / "restored.sqlite").as_posix(),
        config.config_hash,
    )


def _sqlite_backup(source: Path, destination: Path) -> None:
    source_connection = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
    destination_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(destination_connection)
    finally:
        destination_connection.close()
        source_connection.close()


def _sqlite_checks(path: Path) -> tuple[tuple[str, ...], int]:
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only = ON")
        quick = tuple(str(row[0]) for row in connection.execute("PRAGMA quick_check"))
        foreign = sum(1 for _ in connection.execute("PRAGMA foreign_key_check"))
        return quick, foreign
    finally:
        connection.close()


def _table_names(path: Path) -> tuple[str, ...]:
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        return tuple(
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        )
    finally:
        connection.close()


def _table_row_counts(
    path: Path, *, tables: tuple[str, ...] | None = None
) -> tuple[tuple[str, int], ...]:
    names = _table_names(path) if tables is None else tuple(sorted(tables))
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        result = []
        for name in names:
            quoted = name.replace('"', '""')
            row = connection.execute(f'SELECT COUNT(*) FROM "{quoted}"').fetchone()
            if row is None:
                raise ValueError("Phase 9L table count is unavailable")
            result.append((name, int(row[0])))
        return tuple(result)
    finally:
        connection.close()


def _verify_existing(target: Path, backup: Path, upgraded: Path, restored: Path) -> None:
    if not target.is_dir() or target.is_symlink():
        raise ValueError("Phase 9L existing rehearsal target is invalid")
    for name, staged in (
        ("backup.sqlite", backup),
        ("upgraded.sqlite", upgraded),
        ("restored.sqlite", restored),
    ):
        existing = target / name
        invalid = (
            not existing.is_file()
            or existing.is_symlink()
            or _hash_file(existing) != _hash_file(staged)
        )
        if invalid:
            raise ValueError("Phase 9L existing rehearsal artifact conflicts")


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _contained_directory(root: Path, value: object) -> Path:
    if not isinstance(value, str):
        raise TypeError("validated Phase 9L directory must be text")
    result = (root / Path(*PurePosixPath(value).parts)).resolve()
    if root not in result.parents:
        raise ValueError("Phase 9L directory escapes the project root")
    return result


def _contained_file(root: Path, value: str) -> Path:
    if not _relative(value):
        raise ValueError("Phase 9L source path must be contained and relative")
    result = (root / Path(*PurePosixPath(value).parts)).resolve()
    if root not in result.parents or not result.is_file() or result.is_symlink():
        raise ValueError("Phase 9L source must be an existing regular file")
    return result


def _relative(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and path != PurePosixPath(".")
