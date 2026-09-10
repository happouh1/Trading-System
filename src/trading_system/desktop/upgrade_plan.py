"""Phase 9K read-only SQLite schema-upgrade planning."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from trading_system.desktop.local_status import load_local_status_config
from trading_system.desktop.readiness import load_launch_readiness_config
from trading_system.serialization import canonical_hash, deterministic_id


class UpgradePlanConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class UpgradePlanConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class LocalSchemaUpgradePlan:
    plan_id: str
    database_state: str
    plan_status: str
    current_tables: tuple[str, ...]
    required_tables: tuple[str, ...]
    missing_tables: tuple[str, ...]
    quick_check: tuple[str, ...]
    source_hash: str | None
    schema_hash: str | None
    backup_required: bool
    config_hash: str
    upgrade_version: str = "9K.1.0"
    backup_created: bool = False
    migration_executed: bool = False
    database_write_performed: bool = False
    network_used: bool = False
    credentials_loaded: bool = False
    broker_write_performed: bool = False
    sandbox_execution_enabled: bool = False
    live_trading_enabled: bool = False

    def __post_init__(self) -> None:
        if (
            not self.plan_id
            or self.database_state not in {"AVAILABLE", "MISSING", "INVALID"}
            or self.plan_status not in {"NOT_REQUIRED", "REQUIRED", "BLOCKED"}
            or self.current_tables != tuple(sorted(set(self.current_tables)))
            or self.required_tables != tuple(sorted(set(self.required_tables)))
            or self.missing_tables != tuple(sorted(set(self.missing_tables)))
            or any(item not in self.required_tables for item in self.missing_tables)
            or self.backup_required != (self.plan_status == "REQUIRED")
            or (self.source_hash is not None and not self.source_hash.startswith("sha256:"))
            or (self.schema_hash is not None and not self.schema_hash.startswith("sha256:"))
            or not self.config_hash.startswith("sha256:")
            or self.upgrade_version != "9K.1.0"
            or any((
                self.backup_created,
                self.migration_executed,
                self.database_write_performed,
                self.network_used,
                self.credentials_loaded,
                self.broker_write_performed,
                self.sandbox_execution_enabled,
                self.live_trading_enabled,
            ))
        ):
            raise ValueError("invalid Phase 9K schema upgrade plan")


def load_upgrade_plan_config(path: str | Path) -> UpgradePlanConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "upgrade_version", "mode", "readiness_config", "required_tables", "authority"
    }:
        raise UpgradePlanConfigError("Phase 9K configuration keys are invalid")
    if raw["upgrade_version"] != "9K.1.0" or raw["mode"] != "OFFLINE_SCHEMA_UPGRADE_PLAN":
        raise UpgradePlanConfigError("Phase 9K mode is invalid")
    if not _relative(raw["readiness_config"]):
        raise UpgradePlanConfigError("Phase 9K readiness path is invalid")
    required = raw["required_tables"]
    expected = [
        "paper_burn_in_assessments",
        "paper_certification_assessments",
        "paper_operator_snapshots",
        "paper_rollout_gate_assessments",
        "paper_sandbox_lease_assessments",
        "paper_stage_authorization_assessments",
    ]
    if required != expected:
        raise UpgradePlanConfigError("Phase 9K required tables are invalid")
    authority = raw["authority"]
    expected_authority = {
        "backup_creation_enabled", "migration_execution_enabled", "database_write_enabled",
        "network_enabled", "credential_loading_enabled", "broker_writes_enabled",
        "sandbox_execution_enabled", "live_trading_enabled",
    }
    if (
        not isinstance(authority, dict)
        or set(authority) != expected_authority
        or any(value is not False for value in authority.values())
    ):
        raise UpgradePlanConfigError("Phase 9K authority must remain disabled")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else tuple(value)
        if isinstance(value, list) else value
        for key, value in raw.items()
    }
    return UpgradePlanConfig(MappingProxyType(frozen), canonical_hash(raw))


def build_local_schema_upgrade_plan(
    config: UpgradePlanConfig, *, project_root: str | Path
) -> LocalSchemaUpgradePlan:
    root = Path(project_root).resolve()
    readiness_value = config.values["readiness_config"]
    required_value = config.values["required_tables"]
    if not isinstance(readiness_value, str) or not isinstance(required_value, tuple):
        raise TypeError("validated Phase 9K configuration has invalid types")
    readiness = load_launch_readiness_config(root / readiness_value)
    local_value = readiness.values["local_status_config"]
    if not isinstance(local_value, str):
        raise TypeError("validated Phase 9J local status path must be text")
    local = load_local_status_config(root / local_value)
    database_value = local.values["database"]
    if not isinstance(database_value, str):
        raise TypeError("validated Phase 9I database path must be text")
    database = (root / database_value).resolve()
    if root not in database.parents:
        raise UpgradePlanConfigError("Phase 9K database path escapes the project root")
    required = tuple(sorted(str(item) for item in required_value))
    if not database.is_file():
        return _plan(config, "MISSING", "BLOCKED", (), required, required, (), None, None)
    source_hash = _file_hash(database)
    try:
        connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
        try:
            quick = tuple(str(row[0]) for row in connection.execute("PRAGMA quick_check"))
            rows = tuple(
                connection.execute(
                    "SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name"
                )
            )
        finally:
            connection.close()
    except sqlite3.DatabaseError:
        return _plan(
            config,
            "INVALID",
            "BLOCKED",
            (),
            required,
            required,
            ("database_error",),
            source_hash,
            None,
        )
    current = tuple(str(row[0]) for row in rows)
    schema_hash = canonical_hash(tuple((str(row[0]), str(row[1])) for row in rows))
    missing = tuple(item for item in required if item not in current)
    if quick != ("ok",):
        status = "BLOCKED"
        database_state = "INVALID"
    else:
        status = "REQUIRED" if missing else "NOT_REQUIRED"
        database_state = "AVAILABLE"
    return _plan(
        config, database_state, status, current, required, missing, quick, source_hash, schema_hash
    )


def _plan(
    config: UpgradePlanConfig,
    database_state: str,
    plan_status: str,
    current: tuple[str, ...],
    required: tuple[str, ...],
    missing: tuple[str, ...],
    quick: tuple[str, ...],
    source_hash: str | None,
    schema_hash: str | None,
) -> LocalSchemaUpgradePlan:
    identity = (
        database_state, plan_status, current, required, missing, quick, source_hash,
        schema_hash, config.config_hash,
    )
    return LocalSchemaUpgradePlan(
        deterministic_id("local_schema_upgrade_plan", identity),
        database_state,
        plan_status,
        current,
        required,
        missing,
        quick,
        source_hash,
        schema_hash,
        plan_status == "REQUIRED",
        config.config_hash,
    )


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _relative(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = Path(value)
    return not path.is_absolute() and path.as_posix() == value and ".." not in path.parts
