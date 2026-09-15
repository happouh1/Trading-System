"""Phase 11C deterministic collection of prospective sandbox burn-in evidence."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

from trading_system.desktop.burn_in_runtime_lock import (
    load_burn_in_runtime_lock,
    validate_burn_in_runtime,
)
from trading_system.desktop.prospective_burn_in import (
    ProspectiveBurnInObservation,
    ProspectiveBurnInPlan,
    load_prospective_burn_in_observations,
)
from trading_system.market_data import XNYSCalendar
from trading_system.serialization import canonical_hash, canonical_json


class BurnInCollectorConfigError(ValueError):
    """Raised when the Phase 11C collector configuration is unsafe or malformed."""


@dataclass(frozen=True, slots=True)
class BurnInCollectorConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class BurnInCollectionResult:
    observation: ProspectiveBurnInObservation
    inserted: bool
    source_row_count: int
    evidence_path: str
    evidence_file_hash: str
    collector_config_hash: str
    runtime_validation_id: str
    runtime_lock_hash: str
    collector_version: str = "11C.1.0"
    database_opened_read_only: bool = True
    local_evidence_write_performed: bool = True
    network_used: bool = False
    credentials_loaded: bool = False
    broker_write_performed: bool = False
    sandbox_order_submitted: bool = False
    live_trading_enabled: bool = False

    def __post_init__(self) -> None:
        if (
            self.source_row_count <= 0
            or not self.evidence_path
            or not _sha(self.evidence_file_hash)
            or not _sha(self.collector_config_hash)
            or not self.runtime_validation_id
            or not _sha(self.runtime_lock_hash)
            or self.collector_version != "11C.1.0"
            or not self.database_opened_read_only
            or self.local_evidence_write_performed != self.inserted
            or any(
                (
                    self.network_used,
                    self.credentials_loaded,
                    self.broker_write_performed,
                    self.sandbox_order_submitted,
                    self.live_trading_enabled,
                )
            )
        ):
            raise ValueError("invalid Phase 11C collection result")


_SOURCES: tuple[tuple[str, str | None, str], ...] = (
    ("paper_sessions", None, "session_id"),
    ("paper_transitions", "occurred_at", "transition_id"),
    ("paper_intents", "scheduled_open", "intent_id"),
    ("paper_adapter_events", "occurred_at", "adapter_event_id"),
    ("paper_reconciliations", "occurred_at", "reconciliation_id"),
    ("paper_incidents", "occurred_at", "incident_id"),
    ("paper_checkpoints", "known_at", "checkpoint_id"),
    ("paper_heartbeats", "occurred_at", "heartbeat_id"),
    ("paper_orders", "occurred_at", "paper_order_id"),
    ("paper_fills", "occurred_at", "paper_fill_id"),
    ("webull_connection_verifications", "occurred_at", "verification_id"),
    ("webull_stream_notifications", "received_at", "notification_id"),
    ("webull_stream_events", "occurred_at", "stream_event_id"),
    ("webull_submission_events", "occurred_at", "submission_event_id"),
    ("webull_broker_events", "occurred_at", "event_id"),
    ("webull_reconciliations", "occurred_at", "reconciliation_id"),
    ("webull_transport_incidents", "occurred_at", "incident_id"),
    ("webull_executions", "occurred_at", "execution_id"),
    ("webull_managed_positions", "opened_at", "managed_position_id"),
    ("webull_position_events", "occurred_at", "position_event_id"),
    ("webull_position_reconciliations", "occurred_at", "reconciliation_id"),
    ("webull_broker_action_events", "occurred_at", "broker_action_id"),
)


def load_burn_in_collector_config(path: str | Path) -> BurnInCollectorConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "collector_version",
        "mode",
        "plan",
        "evidence_output",
        "runtime_lock",
        "environment",
        "calendar",
        "authority",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise BurnInCollectorConfigError("Phase 11C configuration keys are invalid")
    authority = raw["authority"]
    expected_authority = {
        "database_read_enabled": True,
        "local_evidence_write_enabled": True,
        "network_enabled": False,
        "credential_loading_enabled": False,
        "broker_writes_enabled": False,
        "sandbox_order_submission_enabled": False,
        "live_trading_enabled": False,
        "automatic_promotion_enabled": False,
    }
    if (
        raw["collector_version"] != "11C.1.0"
        or raw["mode"] != "LOCAL_SANDBOX_BURN_IN_EVIDENCE_COLLECTION"
        or raw["environment"] != "WEBULL_SANDBOX"
        or raw["calendar"] != "XNYS"
        or not _relative_json(raw["plan"])
        or not _relative_json(raw["evidence_output"])
        or not _relative_json(raw["runtime_lock"])
        or authority != expected_authority
    ):
        raise BurnInCollectorConfigError("Phase 11C configuration is invalid or unsafe")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return BurnInCollectorConfig(MappingProxyType(frozen), canonical_hash(raw))


def load_burn_in_collector_plan(
    config: BurnInCollectorConfig, *, project_root: str | Path
) -> ProspectiveBurnInPlan:
    """Load the immutable plan captured before the prospective window opened."""
    raw = json.loads(_contained(Path(project_root).resolve(), config.values["plan"]).read_text(
        encoding="utf-8"
    ))
    expected = {
        "__type__",
        "plan_id",
        "declared_at",
        "window_start",
        "window_end",
        "minimum_sessions",
        "minimum_market_days",
        "minimum_completed_trades",
        "required_regimes",
        "required_symbols",
        "required_timeframes",
        "required_strategy_categories",
        "maximum_incidents",
        "maximum_unmatched_reconciliations",
        "maximum_stale_data_events",
        "maximum_rejection_fraction",
        "maximum_unresolved_recoveries",
        "release_assessment_id",
        "release_assessment_hash",
        "config_hash",
        "burn_in_version",
        "execution_authorized",
        "network_authorized",
        "credential_loading_authorized",
        "production_release_authorized",
        "live_trading_authorized",
    }
    if not isinstance(raw, dict) or set(raw) != expected or raw["__type__"] != (
        "ProspectiveBurnInPlan"
    ):
        raise ValueError("Phase 11C saved burn-in plan is invalid")
    return ProspectiveBurnInPlan(
        str(raw["plan_id"]),
        _tagged_datetime(raw["declared_at"]),
        _tagged_datetime(raw["window_start"]),
        _tagged_datetime(raw["window_end"]),
        _plain_int(raw["minimum_sessions"]),
        _plain_int(raw["minimum_market_days"]),
        _plain_int(raw["minimum_completed_trades"]),
        _string_tuple(raw["required_regimes"]),
        _string_tuple(raw["required_symbols"]),
        _string_tuple(raw["required_timeframes"]),
        _string_tuple(raw["required_strategy_categories"]),
        _plain_int(raw["maximum_incidents"]),
        _plain_int(raw["maximum_unmatched_reconciliations"]),
        _plain_int(raw["maximum_stale_data_events"]),
        _tagged_decimal(raw["maximum_rejection_fraction"]),
        _plain_int(raw["maximum_unresolved_recoveries"]),
        str(raw["release_assessment_id"]),
        str(raw["release_assessment_hash"]),
        str(raw["config_hash"]),
        str(raw["burn_in_version"]),
        _plain_bool(raw["execution_authorized"]),
        _plain_bool(raw["network_authorized"]),
        _plain_bool(raw["credential_loading_authorized"]),
        _plain_bool(raw["production_release_authorized"]),
        _plain_bool(raw["live_trading_authorized"]),
    )


def collect_burn_in_observation(
    config: BurnInCollectorConfig,
    plan: ProspectiveBurnInPlan,
    *,
    project_root: str | Path,
    database: str | Path,
    session_id: str,
    market_day: date,
    observed_at: datetime,
    regime: str,
    symbols: Sequence[str],
    timeframes: Sequence[str],
    strategy_categories: Sequence[str],
) -> BurnInCollectionResult:
    """Materialize one post-close observation from immutable local session evidence."""
    if observed_at.tzinfo is None or observed_at.utcoffset() != UTC.utcoffset(observed_at):
        raise ValueError("Phase 11C observed_at must be UTC")
    if not session_id:
        raise ValueError("Phase 11C session identity is required")
    classifications = (
        _declared((regime,), plan.required_regimes, "regime"),
        _declared(symbols, plan.required_symbols, "symbols"),
        _declared(timeframes, plan.required_timeframes, "timeframes"),
        _declared(
            strategy_categories,
            plan.required_strategy_categories,
            "strategy categories",
        ),
    )
    selected_regime = classifications[0][0]
    selected_symbols, selected_timeframes, selected_strategies = classifications[1:]
    if not plan.window_start <= observed_at <= plan.window_end:
        raise ValueError("Phase 11C observation is outside the preregistered window")
    bounds = XNYSCalendar().bounds(market_day)
    if bounds is None:
        raise ValueError("Phase 11C market day is not an XNYS session")
    _, session_close = bounds
    if observed_at < session_close:
        raise ValueError("Phase 11C collection requires the completed XNYS session")

    root = Path(project_root).resolve()
    output = _contained(root, config.values["evidence_output"])
    runtime_lock = load_burn_in_runtime_lock(_contained(root, config.values["runtime_lock"]))
    database_path = Path(database).resolve()
    if not database_path.is_file():
        raise ValueError("Phase 11C database does not exist")
    connection = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only = ON")
        runtime_validation = validate_burn_in_runtime(
            connection,
            runtime_lock,
            session_id=session_id,
            plan_id=plan.plan_id,
            validated_at=observed_at,
        )
        if not runtime_validation.matched:
            raise ValueError(
                "Phase 11E burn-in runtime drift: "
                + ", ".join(runtime_validation.mismatch_fields)
            )
        source_rows = _source_rows(connection, session_id, observed_at)
        _validate_session(connection, session_id, observed_at)
        metrics = _metrics(connection, session_id, observed_at)
    finally:
        connection.close()

    evidence_hash = canonical_hash(
        (
            plan.plan_id,
            session_id,
            market_day,
            observed_at,
            selected_regime,
            selected_symbols,
            selected_timeframes,
            selected_strategies,
            metrics,
            source_rows,
            runtime_validation.validation_id,
            runtime_lock.lock_hash,
            config.config_hash,
        )
    )
    payload: dict[str, object] = {
        "session_id": session_id,
        "market_day": market_day.isoformat(),
        "observed_at": observed_at.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "regime": selected_regime,
        "symbols": list(selected_symbols),
        "timeframes": list(selected_timeframes),
        "strategy_categories": list(selected_strategies),
        "completed_trades": metrics[0],
        "order_attempts": metrics[1],
        "rejected_orders": metrics[2],
        "incidents": metrics[3],
        "unmatched_reconciliations": metrics[4],
        "stale_data_events": metrics[5],
        "unresolved_recoveries": metrics[6],
        "evidence_hash": evidence_hash,
        "environment": "WEBULL_SANDBOX",
    }
    inserted, file_hash = _append_observation(output, payload)
    observations = load_prospective_burn_in_observations(output)
    observation = next(item for item in observations if item.session_id == session_id)
    return BurnInCollectionResult(
        observation,
        inserted,
        len(source_rows),
        str(output),
        file_hash,
        config.config_hash,
        runtime_validation.validation_id,
        runtime_lock.lock_hash,
        local_evidence_write_performed=inserted,
    )


def _source_rows(
    connection: sqlite3.Connection, session_id: str, observed_at: datetime
) -> tuple[tuple[str, str, str], ...]:
    cutoff = observed_at.isoformat(timespec="microseconds").replace("+00:00", "Z")
    rows: list[tuple[str, str, str]] = []
    tables = {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    missing = tuple(table for table, _, _ in _SOURCES if table not in tables)
    if missing:
        raise ValueError(f"Phase 11C database schema is incomplete: {', '.join(missing)}")
    for table, time_column, identity_column in _SOURCES:
        time_filter = "" if time_column is None else f" AND {time_column} <= ?"
        parameters: tuple[object, ...] = (session_id,) if time_column is None else (
            session_id,
            cutoff,
        )
        query = (
            f"SELECT {identity_column}, payload_hash FROM {table} "
            f"WHERE session_id = ?{time_filter} ORDER BY {identity_column}"
        )
        rows.extend(
            (table, str(row[0]), str(row[1]))
            for row in connection.execute(query, parameters)
        )
    if not rows:
        raise ValueError("Phase 11C session has no persisted evidence")
    if any(not _sha(row[2]) for row in rows):
        raise ValueError("Phase 11C source evidence contains an invalid payload hash")
    return tuple(rows)


def _validate_session(
    connection: sqlite3.Connection, session_id: str, observed_at: datetime
) -> None:
    cutoff = observed_at.isoformat(timespec="microseconds").replace("+00:00", "Z")
    session = connection.execute(
        "SELECT created_at, mode FROM paper_sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    if (
        session is None
        or str(session[0]) > cutoff
        or str(session[1]) not in {"SHADOW", "SIMULATED"}
    ):
        raise ValueError("Phase 11C paper session is invalid or future-known")
    verification = connection.execute(
        """SELECT 1 FROM webull_connection_verifications
           WHERE session_id = ? AND occurred_at <= ? LIMIT 1""",
        (session_id, cutoff),
    ).fetchone()
    if verification is None:
        raise ValueError("Phase 11C requires same-session Webull sandbox verification")
    operational_evidence = sum(
        _scalar(
            connection,
            f"SELECT COUNT(*) FROM {table} WHERE session_id = ? AND {time_column} <= ?",
            (session_id, cutoff),
        )
        for table, time_column in (
            ("paper_checkpoints", "known_at"),
            ("paper_heartbeats", "occurred_at"),
            ("paper_intents", "scheduled_open"),
            ("webull_stream_notifications", "received_at"),
        )
    )
    if operational_evidence == 0:
        raise ValueError("Phase 11C session has no causal operational evidence")


def _metrics(
    connection: sqlite3.Connection, session_id: str, observed_at: datetime
) -> tuple[int, int, int, int, int, int, int]:
    cutoff = observed_at.isoformat(timespec="microseconds").replace("+00:00", "Z")
    completed = _scalar(
        connection,
        """WITH ranked AS (
             SELECT managed_position_id,state,
                    ROW_NUMBER() OVER (
                      PARTITION BY managed_position_id
                      ORDER BY occurred_at DESC,position_event_id DESC
                    ) AS position_rank
             FROM webull_position_events WHERE session_id = ? AND occurred_at <= ?)
           SELECT COUNT(*) FROM ranked WHERE position_rank=1 AND state IN ('FLAT','STOP_FILLED')""",
        (session_id, cutoff),
    )
    entry_attempts = _scalar(
        connection,
        """SELECT COUNT(DISTINCT client_order_id) FROM webull_submission_events
           WHERE session_id = ? AND occurred_at <= ? AND event_type = 'CALL_STARTED'""",
        (session_id, cutoff),
    )
    exit_attempts = _scalar(
        connection,
        """SELECT COUNT(DISTINCT client_order_id || ':' || action_kind)
           FROM webull_broker_action_events
           WHERE session_id = ? AND occurred_at <= ? AND event_type = 'CALL_STARTED'""",
        (session_id, cutoff),
    )
    entry_rejections = _scalar(
        connection,
        """SELECT COUNT(DISTINCT client_order_id) FROM webull_submission_events
           WHERE session_id = ? AND occurred_at <= ? AND event_type = 'REJECTED'""",
        (session_id, cutoff),
    )
    exit_rejections = _scalar(
        connection,
        """SELECT COUNT(DISTINCT client_order_id || ':' || action_kind)
           FROM webull_broker_action_events
           WHERE session_id = ? AND occurred_at <= ? AND event_type = 'REJECTED'""",
        (session_id, cutoff),
    )
    incidents = sum(
        _scalar(
            connection,
            f"SELECT COUNT(*) FROM {table} WHERE session_id = ? AND occurred_at <= ?",
            (session_id, cutoff),
        )
        for table in ("paper_incidents", "webull_transport_incidents")
    )
    unmatched = sum(
        _scalar(
            connection,
            f"SELECT COUNT(*) FROM {table} WHERE session_id = ? AND occurred_at <= ? AND matched=0",
            (session_id, cutoff),
        )
        for table in (
            "paper_reconciliations",
            "webull_reconciliations",
            "webull_position_reconciliations",
        )
    )
    stale = sum(
        _scalar(
            connection,
            f"""SELECT COUNT(*) FROM {table}
                WHERE session_id = ? AND occurred_at <= ? AND UPPER(reason) LIKE '%STALE%'""",
            (session_id, cutoff),
        )
        for table in ("paper_incidents", "webull_transport_incidents")
    )
    unresolved = _unresolved_recoveries(connection, session_id, cutoff)
    return (
        completed,
        entry_attempts + exit_attempts,
        entry_rejections + exit_rejections,
        incidents,
        unmatched,
        stale,
        unresolved,
    )


def _unresolved_recoveries(
    connection: sqlite3.Connection, session_id: str, cutoff: str
) -> int:
    entry = _scalar(
        connection,
        """SELECT COUNT(*) FROM (
             SELECT client_order_id,
                    MAX(CASE WHEN event_type='AMBIGUOUS' THEN 1 ELSE 0 END) AS ambiguous,
                    MAX(CASE WHEN event_type='RECOVERED' THEN 1 ELSE 0 END) AS recovered
             FROM webull_submission_events
             WHERE session_id=? AND occurred_at<=? GROUP BY client_order_id)
           WHERE ambiguous=1 AND recovered=0""",
        (session_id, cutoff),
    )
    exits = _scalar(
        connection,
        """SELECT COUNT(*) FROM (
             SELECT client_order_id,action_kind,
                    MAX(CASE WHEN event_type='AMBIGUOUS' THEN 1 ELSE 0 END) AS ambiguous,
                    MAX(CASE WHEN event_type='RECOVERED' THEN 1 ELSE 0 END) AS recovered
             FROM webull_broker_action_events
             WHERE session_id=? AND occurred_at<=? GROUP BY client_order_id,action_kind)
           WHERE ambiguous=1 AND recovered=0""",
        (session_id, cutoff),
    )
    return entry + exits


def _scalar(
    connection: sqlite3.Connection, query: str, parameters: tuple[object, ...]
) -> int:
    row = connection.execute(query, parameters).fetchone()
    return 0 if row is None else int(row[0])


def _append_observation(output: Path, payload: dict[str, object]) -> tuple[bool, str]:
    output.parent.mkdir(parents=True, exist_ok=True)
    raw: dict[str, object] = {"observations": []}
    if output.is_file():
        load_prospective_burn_in_observations(output)
        loaded = json.loads(output.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("Phase 11C evidence root is invalid")
        raw = loaded
    rows = raw.get("observations")
    if not isinstance(rows, list):
        raise ValueError("Phase 11C evidence observations are invalid")
    existing = [
        row
        for row in rows
        if isinstance(row, dict) and row.get("session_id") == payload["session_id"]
    ]
    if existing:
        if len(existing) != 1 or canonical_hash(existing[0]) != canonical_hash(payload):
            raise ValueError("Phase 11C session already has conflicting evidence")
        return False, canonical_hash(output.read_text(encoding="utf-8"))
    normalized = [*rows, payload]
    normalized.sort(key=lambda row: (str(row["observed_at"]), str(row["session_id"])))
    document = canonical_json({"observations": normalized}) + "\n"
    descriptor, temporary = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(document)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return True, canonical_hash(document)


def _declared(values: Sequence[str], permitted: Sequence[str], label: str) -> tuple[str, ...]:
    normalized = tuple(sorted(set(values)))
    if not normalized or any(not value for value in normalized):
        raise ValueError(f"Phase 11C {label} must be non-empty")
    if not set(normalized).issubset(permitted):
        raise ValueError(f"Phase 11C {label} are outside the preregistered plan")
    return normalized


def _relative_json(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts


def _contained(root: Path, value: object) -> Path:
    if not _relative_json(value):
        raise ValueError("Phase 11C output path must be project-relative")
    result = (root / str(value)).resolve()
    if result != root and root not in result.parents:
        raise ValueError("Phase 11C output escapes project root")
    return result


def _sha(value: str) -> bool:
    return value.startswith("sha256:") and len(value) == 71


def _tagged_datetime(value: object) -> datetime:
    if not isinstance(value, dict) or set(value) != {"__datetime__"}:
        raise ValueError("Phase 11C saved plan timestamp is invalid")
    result = datetime.fromisoformat(str(value["__datetime__"]).replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() != UTC.utcoffset(result):
        raise ValueError("Phase 11C saved plan timestamp must be UTC")
    return result


def _tagged_decimal(value: object) -> Decimal:
    if not isinstance(value, dict) or set(value) != {"__decimal__"}:
        raise ValueError("Phase 11C saved plan decimal is invalid")
    return Decimal(str(value["__decimal__"]))


def _plain_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("Phase 11C saved plan integer is invalid")
    return value


def _plain_bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("Phase 11C saved plan boolean is invalid")
    return value


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("Phase 11C saved plan collection is invalid")
    return tuple(value)
