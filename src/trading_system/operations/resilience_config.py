"""Strict Phase 5E offline resilience configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from trading_system.serialization import canonical_hash


class OperationsResilienceConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class OperationsResilienceConfig:
    workspace_root: Path
    backup_directory: PurePosixPath
    restore_directory: PurePosixPath
    minimum_retention_days: int
    config_hash: str


def _relative_directory(value: object, name: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise OperationsResilienceConfigError(f"{name} must be a nonempty relative path")
    result = PurePosixPath(value)
    if result.is_absolute() or ".." in result.parts or result == PurePosixPath("."):
        raise OperationsResilienceConfigError(f"{name} must be a contained relative path")
    return result


def load_operations_resilience_config(path: str | Path) -> OperationsResilienceConfig:
    config_path = Path(path).resolve()
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "resilience_version",
        "authority",
        "storage",
        "verification",
        "retention",
    }:
        raise OperationsResilienceConfigError("resilience config top-level keys are invalid")
    if raw["resilience_version"] != "5E.1.0":
        raise OperationsResilienceConfigError("resilience_version must be 5E.1.0")
    if raw["authority"] != {
        "offline_only": True,
        "network_enabled": False,
        "credential_access_enabled": False,
        "external_notifications_enabled": False,
        "broker_writes_enabled": False,
        "restore_promotion_enabled": False,
        "backup_deletion_enabled": False,
        "live_trading_enabled": False,
    }:
        raise OperationsResilienceConfigError("Phase 5E authority must remain offline and inert")
    storage = raw["storage"]
    if not isinstance(storage, dict) or set(storage) != {
        "workspace_root",
        "backup_directory",
        "restore_directory",
        "content_addressed",
        "overwrite_existing",
    }:
        raise OperationsResilienceConfigError("resilience storage fields are invalid")
    root_value = storage["workspace_root"]
    if not isinstance(root_value, str) or not root_value:
        raise OperationsResilienceConfigError("workspace_root must be a nonempty path")
    root = (config_path.parent / root_value).resolve()
    if not root.is_dir():
        raise OperationsResilienceConfigError("workspace_root must exist")
    if storage["content_addressed"] is not True or storage["overwrite_existing"] is not False:
        raise OperationsResilienceConfigError(
            "backup storage must be content-addressed and immutable"
        )
    if raw["verification"] != {
        "sqlite_quick_check": True,
        "foreign_key_check": True,
        "require_identical_artifact_hash": True,
    }:
        raise OperationsResilienceConfigError("all restore verification checks are mandatory")
    retention = raw["retention"]
    if not isinstance(retention, dict) or set(retention) != {"minimum_days", "report_only"}:
        raise OperationsResilienceConfigError("retention fields are invalid")
    days = retention["minimum_days"]
    if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 3650:
        raise OperationsResilienceConfigError("minimum retention days must be in [1,3650]")
    if retention["report_only"] is not True:
        raise OperationsResilienceConfigError("Phase 5E retention must remain report-only")
    backup = _relative_directory(storage["backup_directory"], "backup directory")
    restore = _relative_directory(storage["restore_directory"], "restore directory")
    if backup == restore:
        raise OperationsResilienceConfigError("backup and restore directories must differ")
    return OperationsResilienceConfig(root, backup, restore, days, canonical_hash(raw))
