"""Phase 11E continuity lock for prospective burn-in runtime identity."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType

from trading_system.serialization import canonical_hash, deterministic_id


class BurnInRuntimeLockConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BurnInRuntimeLock:
    plan_id: str
    baseline_session_id: str
    code_version: str
    config_hash: str
    data_revision: str
    calendar_version: str
    retrospective_baseline_disclosed: bool
    lock_hash: str
    runtime_lock_version: str = "11E.1.0"

    def __post_init__(self) -> None:
        if (
            not all(
                (
                    self.plan_id,
                    self.baseline_session_id,
                    self.code_version,
                    self.data_revision,
                    self.calendar_version,
                )
            )
            or not _sha(self.config_hash)
            or not self.retrospective_baseline_disclosed
            or not _sha(self.lock_hash)
            or self.runtime_lock_version != "11E.1.0"
        ):
            raise ValueError("invalid Phase 11E runtime lock")


@dataclass(frozen=True, slots=True)
class BurnInRuntimeValidation:
    validation_id: str
    session_id: str
    validated_at: datetime
    plan_id: str
    lock_hash: str
    matched: bool
    mismatch_fields: tuple[str, ...]
    runtime_lock_version: str = "11E.1.0"
    read_only: bool = True
    database_write_performed: bool = False
    network_used: bool = False
    credentials_loaded: bool = False
    broker_write_performed: bool = False
    live_trading_enabled: bool = False

    def __post_init__(self) -> None:
        if (
            not all((self.validation_id, self.session_id, self.plan_id))
            or self.validated_at.tzinfo is None
            or self.validated_at.utcoffset() != UTC.utcoffset(self.validated_at)
            or not _sha(self.lock_hash)
            or self.matched == bool(self.mismatch_fields)
            or self.mismatch_fields != tuple(sorted(set(self.mismatch_fields)))
            or self.runtime_lock_version != "11E.1.0"
            or not self.read_only
            or any(
                (
                    self.database_write_performed,
                    self.network_used,
                    self.credentials_loaded,
                    self.broker_write_performed,
                    self.live_trading_enabled,
                )
            )
        ):
            raise ValueError("invalid Phase 11E runtime validation")


def load_burn_in_runtime_lock(path: str | Path) -> BurnInRuntimeLock:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "runtime_lock_version",
        "mode",
        "plan_id",
        "baseline",
        "retrospective_baseline_disclosed",
        "authority",
    }
    baseline_keys = {
        "session_id",
        "code_version",
        "config_hash",
        "data_revision",
        "calendar_version",
    }
    authority_expected = {
        "database_read_enabled": True,
        "database_write_enabled": False,
        "network_enabled": False,
        "credential_loading_enabled": False,
        "broker_writes_enabled": False,
        "sandbox_execution_enabled": False,
        "live_trading_enabled": False,
        "automatic_promotion_enabled": False,
    }
    baseline = raw.get("baseline") if isinstance(raw, dict) else None
    if (
        not isinstance(raw, dict)
        or set(raw) != expected
        or raw["runtime_lock_version"] != "11E.1.0"
        or raw["mode"] != "CONTINUITY_LOCK_FROM_INITIAL_SESSION"
        or not isinstance(baseline, dict)
        or set(baseline) != baseline_keys
        or raw["retrospective_baseline_disclosed"] is not True
        or raw["authority"] != authority_expected
    ):
        raise BurnInRuntimeLockConfigError("Phase 11E runtime lock is invalid or unsafe")
    identity = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    frozen: Mapping[str, object] = MappingProxyType(identity)
    return BurnInRuntimeLock(
        str(raw["plan_id"]),
        str(baseline["session_id"]),
        str(baseline["code_version"]),
        str(baseline["config_hash"]),
        str(baseline["data_revision"]),
        str(baseline["calendar_version"]),
        bool(raw["retrospective_baseline_disclosed"]),
        canonical_hash(frozen),
    )


def validate_burn_in_runtime(
    connection: sqlite3.Connection,
    lock: BurnInRuntimeLock,
    *,
    session_id: str,
    plan_id: str,
    validated_at: datetime,
) -> BurnInRuntimeValidation:
    if validated_at.tzinfo is None or validated_at.utcoffset() != UTC.utcoffset(validated_at):
        raise ValueError("Phase 11E validated_at must be UTC")
    if plan_id != lock.plan_id:
        raise ValueError("Phase 11E runtime lock belongs to a different plan")
    cutoff = validated_at.isoformat(timespec="microseconds").replace("+00:00", "Z")
    row = connection.execute(
        """SELECT created_at,code_version,config_hash,data_revision,calendar_version
           FROM paper_sessions WHERE session_id = ?""",
        (session_id,),
    ).fetchone()
    if row is None or str(row[0]) > cutoff:
        raise ValueError("Phase 11E session is missing or future-known")
    actual = tuple(str(value) for value in row[1:])
    expected = (
        lock.code_version,
        lock.config_hash,
        lock.data_revision,
        lock.calendar_version,
    )
    names = ("code_version", "config_hash", "data_revision", "calendar_version")
    mismatches = tuple(
        sorted(
            name
            for name, left, right in zip(names, actual, expected, strict=True)
            if left != right
        )
    )
    identity = (session_id, validated_at, plan_id, lock.lock_hash, mismatches)
    return BurnInRuntimeValidation(
        deterministic_id("burn_in_runtime_validation", identity),
        session_id,
        validated_at,
        plan_id,
        lock.lock_hash,
        not mismatches,
        mismatches,
    )


def _sha(value: str) -> bool:
    return value.startswith("sha256:") and len(value) == 71
