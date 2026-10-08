"""Locked launcher for versioned prospective shadow cohorts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType

from trading_system import PACKAGE_VERSION
from trading_system.config import load_config
from trading_system.desktop.burn_in_runtime_lock import load_burn_in_runtime_lock
from trading_system.paper.adapters import RejectingAdapter
from trading_system.paper.config import load_paper_config
from trading_system.paper.contracts import PaperMode, PaperSession, RuntimeState
from trading_system.paper.registry import PaperRegistry
from trading_system.paper.runtime import PaperRuntime
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id
from trading_system.webull.burn_in_decision_worker import (
    load_burn_in_decision_worker_config,
)
from trading_system.webull.burn_in_worker import load_burn_in_worker_config


class ProspectiveShadowLaunchConfigError(ValueError):
    """The prospective launch identity or authority is malformed."""


@dataclass(frozen=True, slots=True)
class ProspectiveShadowLaunchConfig:
    plan_path: str
    plan_id: str
    plan_file_sha256: str
    window_start: datetime
    window_end: datetime
    paper_config: str
    paper_config_hash: str
    thresholds_config: str
    strategy_config_hash: str
    worker_config: str
    decision_config: str
    data_revision: str
    calendar_version: str
    symbols: tuple[str, ...]
    config_hash: str
    launch_version: str = "12B.1.0"


def load_prospective_shadow_launch_config(
    path: str | Path,
) -> ProspectiveShadowLaunchConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "launch_version",
        "mode",
        "plan",
        "plan_id",
        "plan_file_sha256",
        "window_start",
        "window_end",
        "paper_config",
        "paper_config_hash",
        "thresholds_config",
        "strategy_config_hash",
        "worker_config",
        "decision_config",
        "data_revision",
        "calendar_version",
        "symbols",
        "authority",
    }
    authority = {
        "database_write_enabled": True,
        "local_shadow_session_start_enabled": True,
        "network_enabled": False,
        "credential_loading_enabled": False,
        "broker_writes_enabled": False,
        "sandbox_order_submission_enabled": False,
        "simulated_fills_enabled": False,
        "live_trading_enabled": False,
        "automatic_promotion_enabled": False,
    }
    if (
        not isinstance(raw, dict)
        or set(raw) != expected
        or raw["launch_version"] not in {"12B.1.0", "12C.1.0"}
        or raw["mode"] != "LOCKED_PROSPECTIVE_SHADOW_ONLY"
        or raw["authority"] != authority
    ):
        raise ProspectiveShadowLaunchConfigError(
            "Phase 12B launch configuration is invalid or unsafe"
        )
    relative_paths = tuple(
        raw[name]
        for name in (
            "plan",
            "paper_config",
            "thresholds_config",
            "worker_config",
            "decision_config",
        )
    )
    symbols = raw["symbols"]
    if (
        any(not _relative(value) for value in relative_paths)
        or not _sha(raw["plan_file_sha256"])
        or not _sha(raw["paper_config_hash"])
        or not _sha(raw["strategy_config_hash"])
        or not isinstance(symbols, list)
        or tuple(symbols) != ("MSFT", "SPY")
        or not all(isinstance(value, str) and value for value in symbols)
    ):
        raise ProspectiveShadowLaunchConfigError(
            "Phase 12B launch identity is invalid or unsafe"
        )
    window_start = _parse_time(raw["window_start"])
    window_end = _parse_time(raw["window_end"])
    if window_start >= window_end:
        raise ProspectiveShadowLaunchConfigError("Phase 12B launch window is invalid")
    return ProspectiveShadowLaunchConfig(
        str(raw["plan"]),
        str(raw["plan_id"]),
        str(raw["plan_file_sha256"]),
        window_start,
        window_end,
        str(raw["paper_config"]),
        str(raw["paper_config_hash"]),
        str(raw["thresholds_config"]),
        str(raw["strategy_config_hash"]),
        str(raw["worker_config"]),
        str(raw["decision_config"]),
        str(raw["data_revision"]),
        str(raw["calendar_version"]),
        tuple(symbols),
        canonical_hash(_freeze(raw)),
        str(raw["launch_version"]),
    )


def start_prospective_shadow_session(
    *,
    database: str | Path,
    config_path: str | Path,
    runtime_lock_path: str | Path,
    project_root: str | Path,
    session_id: str,
    started_at: datetime,
) -> Mapping[str, object]:
    """Validate frozen identities and start one idempotent SHADOW session."""
    root = Path(project_root).resolve()
    config = load_prospective_shadow_launch_config(_contained(root, config_path))
    if not session_id or not _utc(started_at):
        raise ValueError("Phase 12B requires a session ID and UTC start time")
    if not config.window_start <= started_at <= config.window_end:
        raise ValueError("Phase 12B session start is outside the frozen window")
    _validate_frozen_inputs(root, config, runtime_lock_path)

    lock = load_burn_in_runtime_lock(_contained(root, runtime_lock_path))
    binding_payload = {
        "session_id": session_id,
        "plan_id": config.plan_id,
        "baseline_session_id": lock.baseline_session_id,
        "started_at": started_at,
        "code_version": PACKAGE_VERSION,
        "config_hash": config.paper_config_hash,
        "data_revision": config.data_revision,
        "calendar_version": config.calendar_version,
        "runtime_lock_hash": lock.lock_hash,
        "launch_config_hash": config.config_hash,
        "symbols": config.symbols,
        "launch_version": config.launch_version,
    }
    binding_id = deterministic_id(
        "prospective_shadow_session", tuple(binding_payload.values())
    )
    database_path = _contained(root, database)
    with SQLiteRepository(database_path) as repository:
        repository.migrate()
        paper = PaperRegistry(repository)
        inserted = paper.insert_session(
            PaperSession(
                session_id,
                started_at,
                PaperMode.SHADOW,
                PACKAGE_VERSION,
                config.paper_config_hash,
                config.data_revision,
                config.calendar_version,
            )
        )
        binding_inserted = _insert_binding(
            repository,
            binding_id=binding_id,
            payload=binding_payload,
            lock_hash=lock.lock_hash,
        )
        state = paper.current_state(session_id)
        if state is RuntimeState.CREATED:
            state = PaperRuntime(
                paper, session_id, PaperMode.SHADOW, RejectingAdapter()
            ).start(started_at)
        elif state is RuntimeState.STARTING:
            paper.transition(session_id, RuntimeState.SHADOW, started_at, "IDENTITY_VALIDATED")
            state = RuntimeState.SHADOW
        elif state is not RuntimeState.SHADOW:
            raise ValueError(f"Phase 12B session cannot recover from {state.value}")
    return MappingProxyType(
        {
            "binding_id": binding_id,
            "session_id": session_id,
            "plan_id": config.plan_id,
            "state": state,
            "symbols": config.symbols,
            "session_inserted": inserted,
            "binding_inserted": binding_inserted,
            "runtime_lock_hash": lock.lock_hash,
            "network_used": False,
            "credentials_loaded": False,
            "broker_write_performed": False,
            "simulated_fills_enabled": False,
            "live_trading_enabled": False,
        }
    )


def _validate_frozen_inputs(
    root: Path,
    config: ProspectiveShadowLaunchConfig,
    runtime_lock_path: str | Path,
) -> None:
    plan_path = _contained(root, config.plan_path)
    actual_plan_hash = "sha256:" + hashlib.sha256(plan_path.read_bytes()).hexdigest()
    if actual_plan_hash != config.plan_file_sha256:
        raise ValueError("Phase 12B plan bytes do not match the frozen identity")
    raw_plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if (
        raw_plan.get("plan_id") != config.plan_id
        or tuple(raw_plan.get("required_symbols", ())) != config.symbols
        or _tagged_time(raw_plan.get("window_start")) != config.window_start
        or _tagged_time(raw_plan.get("window_end")) != config.window_end
    ):
        raise ValueError("Phase 12B plan content does not match the launch configuration")
    paper = load_paper_config(_contained(root, config.paper_config))
    thresholds = load_config(_contained(root, config.thresholds_config))
    worker = load_burn_in_worker_config(_contained(root, config.worker_config))
    decisions = load_burn_in_decision_worker_config(_contained(root, config.decision_config))
    lock = load_burn_in_runtime_lock(_contained(root, runtime_lock_path))
    if (
        lock.code_version != PACKAGE_VERSION
        or paper.config_hash != config.paper_config_hash
        or thresholds.config_hash != config.strategy_config_hash
        or worker.plan_id != config.plan_id
        or worker.symbols != config.symbols
        or decisions.plan_id != config.plan_id
        or decisions.strategy_config_hash != config.strategy_config_hash
        or lock.plan_id != config.plan_id
        or lock.config_hash != config.paper_config_hash
        or lock.data_revision != config.data_revision
        or lock.calendar_version != config.calendar_version
        or lock.retrospective_baseline_disclosed
    ):
        raise ValueError("Phase 12B frozen runtime identities do not match")


def _insert_binding(
    repository: SQLiteRepository,
    *,
    binding_id: str,
    payload: Mapping[str, object],
    lock_hash: str,
) -> bool:
    payload_json = canonical_json(payload)
    payload_hash = canonical_hash(payload)
    cursor = repository.connection.execute(
        """INSERT OR IGNORE INTO paper_burn_in_session_bindings
           (binding_id,session_id,plan_id,baseline_session_id,runtime_lock_hash,
            started_at,code_version,config_hash,data_revision,calendar_version,
            payload_json,payload_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            binding_id,
            payload["session_id"],
            payload["plan_id"],
            payload["baseline_session_id"],
            lock_hash,
            _time(payload["started_at"]),
            payload["code_version"],
            payload["config_hash"],
            payload["data_revision"],
            payload["calendar_version"],
            payload_json,
            payload_hash,
        ),
    )
    if cursor.rowcount == 0:
        stored = repository.connection.execute(
            "SELECT binding_id,payload_hash FROM paper_burn_in_session_bindings WHERE session_id=?",
            (payload["session_id"],),
        ).fetchone()
        if stored != (binding_id, payload_hash):
            raise ValueError("conflicting Phase 12B session binding")
        return False
    repository.connection.commit()
    return True


def _contained(root: Path, value: object) -> Path:
    if not isinstance(value, (str, Path)):
        raise ValueError("Phase 12B path must be a string")
    path = Path(value)
    candidate = path.resolve() if path.is_absolute() else (root / path).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("Phase 12B path escapes project root")
    return candidate


def _relative(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and not Path(value).is_absolute()
        and ".." not in Path(value).parts
    )


def _tagged_time(value: object) -> datetime:
    if not isinstance(value, dict) or set(value) != {"__datetime__"}:
        raise ValueError("Phase 12B plan timestamp is invalid")
    return _parse_time(value["__datetime__"])


def _parse_time(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Phase 12B timestamp is invalid")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not _utc(parsed):
        raise ValueError("Phase 12B timestamps must be UTC")
    return parsed


def _utc(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() == UTC.utcoffset(value)
    )


def _sha(value: object) -> bool:
    return isinstance(value, str) and value.startswith("sha256:") and len(value) == 71


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _time(value: object) -> str:
    if not isinstance(value, datetime):
        raise ValueError("Phase 12B binding timestamp is invalid")
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")
