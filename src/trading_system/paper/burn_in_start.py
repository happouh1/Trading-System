"""Phase 11F fail-closed start for lock-bound prospective burn-in sessions."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType

from trading_system import PACKAGE_VERSION
from trading_system.desktop.burn_in_collector import (
    load_burn_in_collector_config,
    load_burn_in_collector_plan,
)
from trading_system.desktop.burn_in_runtime_lock import (
    BurnInRuntimeLock,
    load_burn_in_runtime_lock,
)
from trading_system.desktop.prospective_burn_in import ProspectiveBurnInPlan
from trading_system.paper.adapters import RejectingAdapter
from trading_system.paper.config import load_paper_config
from trading_system.paper.contracts import PaperMode, PaperSession, RuntimeState
from trading_system.paper.registry import PaperRegistry
from trading_system.paper.runtime import PaperRuntime
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id


class LockedBurnInStartConfigError(ValueError):
    """Raised when Phase 11F configuration is malformed or unsafe."""


@dataclass(frozen=True, slots=True)
class LockedBurnInStartConfig:
    paper_config: str
    collector_config: str
    config_hash: str
    start_version: str = "11F.1.0"


@dataclass(frozen=True, slots=True)
class LockedBurnInSessionBinding:
    binding_id: str
    session_id: str
    plan_id: str
    baseline_session_id: str
    started_at: datetime
    code_version: str
    config_hash: str
    data_revision: str
    calendar_version: str
    runtime_lock_hash: str
    retrospective_baseline_disclosed: bool
    start_version: str = "11F.1.0"
    mode: str = "LOCKED_PROSPECTIVE_BURN_IN_SHADOW"
    database_write_performed: bool = True
    network_used: bool = False
    credentials_loaded: bool = False
    broker_write_performed: bool = False
    simulated_order_execution_enabled: bool = False
    production_release_enabled: bool = False
    live_trading_enabled: bool = False
    automatic_promotion_enabled: bool = False

    def __post_init__(self) -> None:
        if (
            not all(
                (
                    self.binding_id,
                    self.session_id,
                    self.plan_id,
                    self.baseline_session_id,
                    self.code_version,
                    self.data_revision,
                    self.calendar_version,
                )
            )
            or not _utc(self.started_at)
            or not _sha(self.config_hash)
            or not _sha(self.runtime_lock_hash)
            or not self.retrospective_baseline_disclosed
            or self.start_version != "11F.1.0"
            or self.mode != "LOCKED_PROSPECTIVE_BURN_IN_SHADOW"
            or not self.database_write_performed
            or any(
                (
                    self.network_used,
                    self.credentials_loaded,
                    self.broker_write_performed,
                    self.simulated_order_execution_enabled,
                    self.production_release_enabled,
                    self.live_trading_enabled,
                    self.automatic_promotion_enabled,
                )
            )
        ):
            raise ValueError("invalid Phase 11F locked burn-in session binding")


def load_locked_burn_in_start_config(path: str | Path) -> LockedBurnInStartConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {"start_version", "mode", "paper_config", "collector_config", "authority"}
    authority = {
        "database_write_enabled": True,
        "local_shadow_session_start_enabled": True,
        "network_enabled": False,
        "credential_loading_enabled": False,
        "broker_writes_enabled": False,
        "simulated_order_execution_enabled": False,
        "production_release_enabled": False,
        "live_trading_enabled": False,
        "automatic_promotion_enabled": False,
    }
    if (
        not isinstance(raw, dict)
        or set(raw) != expected
        or raw["start_version"] != "11F.1.0"
        or raw["mode"] != "LOCKED_PROSPECTIVE_BURN_IN_SHADOW"
        or raw["authority"] != authority
        or not _relative(raw["paper_config"])
        or not _relative(raw["collector_config"])
    ):
        raise LockedBurnInStartConfigError("Phase 11F configuration is invalid or unsafe")
    return LockedBurnInStartConfig(
        str(raw["paper_config"]),
        str(raw["collector_config"]),
        canonical_hash(_freeze(raw)),
    )


def build_locked_burn_in_binding(
    config: LockedBurnInStartConfig,
    plan: ProspectiveBurnInPlan,
    lock: BurnInRuntimeLock,
    *,
    session_id: str,
    started_at: datetime,
    paper_config_hash: str,
    code_version: str = PACKAGE_VERSION,
) -> LockedBurnInSessionBinding:
    """Validate the complete identity before a database is opened for writing."""
    if not session_id or not _utc(started_at):
        raise ValueError("Phase 11F session identity and UTC started_at are required")
    if not plan.window_start <= started_at <= plan.window_end:
        raise ValueError("Phase 11F session start is outside the preregistered window")
    if plan.plan_id != lock.plan_id:
        raise ValueError("Phase 11F plan and runtime lock identities differ")
    mismatches = tuple(
        name
        for name, actual, expected in (
            ("code_version", code_version, lock.code_version),
            ("config_hash", paper_config_hash, lock.config_hash),
        )
        if actual != expected
    )
    if mismatches:
        raise ValueError(f"Phase 11F runtime identity mismatch: {','.join(mismatches)}")
    identity = (
        session_id,
        plan.plan_id,
        lock.baseline_session_id,
        started_at,
        code_version,
        paper_config_hash,
        lock.data_revision,
        lock.calendar_version,
        lock.lock_hash,
        config.config_hash,
        "11F.1.0",
    )
    return LockedBurnInSessionBinding(
        deterministic_id("locked_burn_in_session", identity),
        session_id,
        plan.plan_id,
        lock.baseline_session_id,
        started_at,
        code_version,
        paper_config_hash,
        lock.data_revision,
        lock.calendar_version,
        lock.lock_hash,
        lock.retrospective_baseline_disclosed,
    )


def start_locked_burn_in_session(
    *,
    database: str | Path,
    config_path: str | Path,
    project_root: str | Path,
    session_id: str,
    started_at: datetime,
) -> Mapping[str, object]:
    """Start or deterministically recover one offline, non-executable shadow session."""
    root = Path(project_root).resolve()
    config = load_locked_burn_in_start_config(_contained(root, config_path))
    paper_config = load_paper_config(_contained(root, config.paper_config))
    collector = load_burn_in_collector_config(_contained(root, config.collector_config))
    plan = load_burn_in_collector_plan(collector, project_root=root)
    lock_path = _contained(root, collector.values["runtime_lock"])
    lock = load_burn_in_runtime_lock(lock_path)
    binding = build_locked_burn_in_binding(
        config,
        plan,
        lock,
        session_id=session_id,
        started_at=started_at,
        paper_config_hash=paper_config.config_hash,
    )

    database_path = _contained(root, database)
    with SQLiteRepository(database_path) as repository:
        repository.migrate()
        registry = PaperRegistry(repository)
        session = PaperSession(
            session_id,
            started_at,
            PaperMode.SHADOW,
            binding.code_version,
            binding.config_hash,
            binding.data_revision,
            binding.calendar_version,
        )
        inserted = registry.insert_session(session)
        binding_inserted = _insert_binding(repository, binding)
        state = registry.current_state(session_id)
        if state is RuntimeState.CREATED:
            state = PaperRuntime(
                registry,
                session_id,
                PaperMode.SHADOW,
                RejectingAdapter(),
            ).start(started_at)
        elif state is RuntimeState.STARTING:
            registry.transition(session_id, RuntimeState.SHADOW, started_at, "IDENTITY_VALIDATED")
            state = RuntimeState.SHADOW
        elif state is not RuntimeState.SHADOW:
            raise ValueError(f"Phase 11F session cannot recover from {state.value}")
    return MappingProxyType(
        {
            "binding_id": binding.binding_id,
            "session_id": session_id,
            "plan_id": plan.plan_id,
            "state": state,
            "session_inserted": inserted,
            "binding_inserted": binding_inserted,
            "retrospective_baseline_disclosed": True,
            "database_write_performed": True,
            "network_used": False,
            "credentials_loaded": False,
            "broker_write_performed": False,
            "simulated_order_execution_enabled": False,
            "live_trading_enabled": False,
            "automatic_promotion_enabled": False,
        }
    )


def _insert_binding(
    repository: SQLiteRepository, binding: LockedBurnInSessionBinding
) -> bool:
    payload_json = canonical_json(binding)
    payload_hash = canonical_hash(binding)
    cursor = repository.connection.execute(
        """INSERT OR IGNORE INTO paper_burn_in_session_bindings
           (binding_id,session_id,plan_id,baseline_session_id,runtime_lock_hash,started_at,
            code_version,config_hash,data_revision,calendar_version,payload_json,payload_hash)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            binding.binding_id,
            binding.session_id,
            binding.plan_id,
            binding.baseline_session_id,
            binding.runtime_lock_hash,
            _time(binding.started_at),
            binding.code_version,
            binding.config_hash,
            binding.data_revision,
            binding.calendar_version,
            payload_json,
            payload_hash,
        ),
    )
    if cursor.rowcount == 0:
        stored = repository.connection.execute(
            """SELECT binding_id,payload_hash FROM paper_burn_in_session_bindings
               WHERE session_id = ?""",
            (binding.session_id,),
        ).fetchone()
        if stored != (binding.binding_id, payload_hash):
            raise ValueError("conflicting Phase 11F session binding")
        return False
    repository.connection.commit()
    return True


def _contained(root: Path, value: object) -> Path:
    if not isinstance(value, (str, Path)):
        raise ValueError("Phase 11F path must be a string")
    path = Path(value)
    candidate = path.resolve() if path.is_absolute() else (root / path).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("Phase 11F path escapes project root")
    return candidate


def _relative(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and not Path(value).is_absolute()
        and ".." not in Path(value).parts
    )


def _freeze(raw: dict[str, object]) -> Mapping[str, object]:
    return MappingProxyType(
        {
            key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
            for key, value in raw.items()
        }
    )


def _time(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == UTC.utcoffset(value)


def _sha(value: str) -> bool:
    return value.startswith("sha256:") and len(value) == 71
