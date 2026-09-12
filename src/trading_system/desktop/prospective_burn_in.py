"""Phase 9Y offline prospective sandbox burn-in control and assessment."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from trading_system.desktop.release_audit import (
    ReleaseAuditAssessment,
    ReleaseAuditState,
)
from trading_system.serialization import canonical_hash, deterministic_id


class ProspectiveBurnInConfigError(ValueError):
    pass


class ProspectiveBurnInState(StrEnum):
    IN_PROGRESS = "IN_PROGRESS"
    PASS = "PASS"
    FAIL = "FAIL"


@dataclass(frozen=True, slots=True)
class ProspectiveBurnInConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class ProspectiveBurnInPlan:
    plan_id: str
    declared_at: datetime
    window_start: datetime
    window_end: datetime
    minimum_sessions: int
    minimum_market_days: int
    minimum_completed_trades: int
    required_regimes: tuple[str, ...]
    required_symbols: tuple[str, ...]
    required_timeframes: tuple[str, ...]
    required_strategy_categories: tuple[str, ...]
    maximum_incidents: int
    maximum_unmatched_reconciliations: int
    maximum_stale_data_events: int
    maximum_rejection_fraction: Decimal
    maximum_unresolved_recoveries: int
    release_assessment_id: str
    release_assessment_hash: str
    config_hash: str
    burn_in_version: str = "9Y.1.0"
    execution_authorized: bool = False
    network_authorized: bool = False
    credential_loading_authorized: bool = False
    production_release_authorized: bool = False
    live_trading_authorized: bool = False

    def __post_init__(self) -> None:
        timestamps = (self.declared_at, self.window_start, self.window_end)
        collections = (
            self.required_regimes,
            self.required_symbols,
            self.required_timeframes,
            self.required_strategy_categories,
        )
        if (
            not self.plan_id
            or any(not _utc(value) for value in timestamps)
            or not self.declared_at < self.window_start < self.window_end
            or min(
                self.minimum_sessions,
                self.minimum_market_days,
                self.minimum_completed_trades,
            )
            <= 0
            or any(not values or tuple(sorted(set(values))) != values for values in collections)
            or min(
                self.maximum_incidents,
                self.maximum_unmatched_reconciliations,
                self.maximum_stale_data_events,
                self.maximum_unresolved_recoveries,
            )
            < 0
            or not Decimal(0) <= self.maximum_rejection_fraction <= Decimal(1)
            or not self.release_assessment_id
            or not _sha(self.release_assessment_hash)
            or not _sha(self.config_hash)
            or self.burn_in_version != "9Y.1.0"
            or self.execution_authorized
            or self.network_authorized
            or self.credential_loading_authorized
            or self.production_release_authorized
            or self.live_trading_authorized
        ):
            raise ValueError("invalid Phase 9Y prospective burn-in plan")


@dataclass(frozen=True, slots=True)
class ProspectiveBurnInObservation:
    observation_id: str
    session_id: str
    market_day: date
    observed_at: datetime
    regime: str
    symbols: tuple[str, ...]
    timeframes: tuple[str, ...]
    strategy_categories: tuple[str, ...]
    completed_trades: int
    order_attempts: int
    rejected_orders: int
    incidents: int
    unmatched_reconciliations: int
    stale_data_events: int
    unresolved_recoveries: int
    evidence_hash: str
    environment: str = "WEBULL_SANDBOX"

    def __post_init__(self) -> None:
        collections = (self.symbols, self.timeframes, self.strategy_categories)
        if (
            not all((self.observation_id, self.session_id, self.regime))
            or not _utc(self.observed_at)
            or any(not values or tuple(sorted(set(values))) != values for values in collections)
            or min(
                self.completed_trades,
                self.order_attempts,
                self.rejected_orders,
                self.incidents,
                self.unmatched_reconciliations,
                self.stale_data_events,
                self.unresolved_recoveries,
            )
            < 0
            or self.rejected_orders > self.order_attempts
            or not _sha(self.evidence_hash)
            or self.environment != "WEBULL_SANDBOX"
        ):
            raise ValueError("invalid Phase 9Y prospective burn-in observation")


@dataclass(frozen=True, slots=True)
class ProspectiveBurnInAssessment:
    assessment_id: str
    plan_id: str
    evaluated_at: datetime
    state: ProspectiveBurnInState
    observation_count: int
    session_count: int
    market_day_count: int
    completed_trade_count: int
    order_attempt_count: int
    rejected_order_count: int
    rejection_fraction: Decimal
    incident_count: int
    unmatched_reconciliation_count: int
    stale_data_event_count: int
    unresolved_recovery_count: int
    missing_regimes: tuple[str, ...]
    missing_symbols: tuple[str, ...]
    missing_timeframes: tuple[str, ...]
    missing_strategy_categories: tuple[str, ...]
    reason_codes: tuple[str, ...]
    observation_root_hash: str
    plan_hash: str
    config_hash: str
    burn_in_version: str = "9Y.1.0"
    evidence_only: bool = True
    automatic_promotion_performed: bool = False
    file_write_performed: bool = False
    process_launched: bool = False
    credentials_loaded: bool = False
    network_used: bool = False
    sandbox_execution_performed: bool = False
    production_release_authorized: bool = False
    broker_write_performed: bool = False
    live_trading_enabled: bool = False

    def __post_init__(self) -> None:
        missing = (
            self.missing_regimes,
            self.missing_symbols,
            self.missing_timeframes,
            self.missing_strategy_categories,
        )
        if (
            not self.assessment_id
            or not self.plan_id
            or not _utc(self.evaluated_at)
            or min(
                self.observation_count,
                self.session_count,
                self.market_day_count,
                self.completed_trade_count,
                self.order_attempt_count,
                self.rejected_order_count,
                self.incident_count,
                self.unmatched_reconciliation_count,
                self.stale_data_event_count,
                self.unresolved_recovery_count,
            )
            < 0
            or self.rejected_order_count > self.order_attempt_count
            or not Decimal(0) <= self.rejection_fraction <= Decimal(1)
            or any(tuple(sorted(set(values))) != values for values in missing)
            or tuple(sorted(set(self.reason_codes))) != self.reason_codes
            or not all(_sha(value) for value in (
                self.observation_root_hash,
                self.plan_hash,
                self.config_hash,
            ))
            or self.burn_in_version != "9Y.1.0"
            or not self.evidence_only
            or self.automatic_promotion_performed
            or self.file_write_performed
            or self.process_launched
            or self.credentials_loaded
            or self.network_used
            or self.sandbox_execution_performed
            or self.production_release_authorized
            or self.broker_write_performed
            or self.live_trading_enabled
        ):
            raise ValueError("invalid Phase 9Y prospective burn-in assessment")


def load_prospective_burn_in_config(path: str | Path) -> ProspectiveBurnInConfig:
    raw = _object(Path(path))
    if set(raw) != {"burn_in_version", "mode", "method", "authority"}:
        raise ProspectiveBurnInConfigError("Phase 9Y configuration keys are invalid")
    if raw["burn_in_version"] != "9Y.1.0" or raw["mode"] != (
        "OFFLINE_PROSPECTIVE_SANDBOX_BURN_IN_CONTROL"
    ):
        raise ProspectiveBurnInConfigError("Phase 9Y mode is invalid")
    if raw["method"] != {
        "release_gate": "CURRENT_PHASE9X_ASSESSMENT",
        "threshold_source": "PREREGISTERED_OPERATOR_REQUEST",
        "evidence_source": "OPERATOR_SUPPLIED_SANDBOX_OBSERVATIONS",
        "coverage_required": True,
        "causal_window_required": True,
        "default_thresholds_enabled": False,
        "automatic_collection_enabled": False,
        "automatic_promotion_enabled": False,
    }:
        raise ProspectiveBurnInConfigError("Phase 9Y method is invalid")
    authority = raw["authority"]
    if not isinstance(authority, dict) or set(authority) != {
        "file_write_enabled",
        "process_launch_enabled",
        "credential_loading_enabled",
        "network_enabled",
        "broker_writes_enabled",
        "sandbox_execution_enabled",
        "production_release_enabled",
        "live_trading_enabled",
    } or any(value is not False for value in authority.values()):
        raise ProspectiveBurnInConfigError("Phase 9Y authority must remain disabled")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return ProspectiveBurnInConfig(MappingProxyType(frozen), canonical_hash(raw))


def build_prospective_burn_in_plan(
    config: ProspectiveBurnInConfig,
    release: ReleaseAuditAssessment,
    request: Mapping[str, object],
) -> ProspectiveBurnInPlan:
    if release.state is not ReleaseAuditState.READY_FOR_PROSPECTIVE_SANDBOX_BURN_IN:
        raise ValueError("Phase 9Y requires a ready Phase 9X assessment")
    if release.sandbox_burn_in_authorized or release.production_release_authorized:
        raise ValueError("Phase 9X assessment contains forbidden authority")
    expected = {
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
    }
    if set(request) != expected:
        raise ValueError("Phase 9Y operator request keys are invalid")
    values = (
        _time(request["declared_at"]),
        _time(request["window_start"]),
        _time(request["window_end"]),
        _positive_int(request["minimum_sessions"]),
        _positive_int(request["minimum_market_days"]),
        _positive_int(request["minimum_completed_trades"]),
        _names(request["required_regimes"]),
        _names(request["required_symbols"]),
        _names(request["required_timeframes"]),
        _names(request["required_strategy_categories"]),
        _nonnegative_int(request["maximum_incidents"]),
        _nonnegative_int(request["maximum_unmatched_reconciliations"]),
        _nonnegative_int(request["maximum_stale_data_events"]),
        _fraction(request["maximum_rejection_fraction"]),
        _nonnegative_int(request["maximum_unresolved_recoveries"]),
    )
    identity = (*values, release.assessment_id, canonical_hash(release), config.config_hash)
    return ProspectiveBurnInPlan(
        deterministic_id("prospective_burn_in_plan", identity),
        *values,
        release.assessment_id,
        canonical_hash(release),
        config.config_hash,
    )


def load_prospective_burn_in_observations(
    path: str | Path,
) -> tuple[ProspectiveBurnInObservation, ...]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {"observations"}:
        raise ValueError("Phase 9Y evidence root is invalid")
    rows = raw["observations"]
    if not isinstance(rows, list):
        raise ValueError("Phase 9Y observations must be a list")
    observations = tuple(_observation(row) for row in rows)
    ordered = tuple(sorted(observations, key=lambda item: (item.observed_at, item.observation_id)))
    if len({item.observation_id for item in ordered}) != len(ordered):
        raise ValueError("Phase 9Y observation identities must be unique")
    return ordered


def evaluate_prospective_burn_in(
    plan: ProspectiveBurnInPlan,
    observations: Sequence[ProspectiveBurnInObservation],
    *,
    evaluated_at: datetime,
) -> ProspectiveBurnInAssessment:
    if not _utc(evaluated_at):
        raise ValueError("Phase 9Y evaluation time must be UTC")
    ordered = tuple(sorted(observations, key=lambda item: (item.observed_at, item.observation_id)))
    if len({item.observation_id for item in ordered}) != len(ordered):
        raise ValueError("Phase 9Y observation identities must be unique")
    if any(
        not plan.window_start <= item.observed_at <= plan.window_end
        or item.observed_at > evaluated_at
        for item in ordered
    ):
        raise ValueError("Phase 9Y observation is outside the causal plan window")
    sessions = {item.session_id for item in ordered}
    days = {item.market_day for item in ordered}
    regimes = {item.regime for item in ordered}
    symbols = {value for item in ordered for value in item.symbols}
    timeframes = {value for item in ordered for value in item.timeframes}
    strategies = {value for item in ordered for value in item.strategy_categories}
    totals = tuple(
        sum(getattr(item, field) for item in ordered)
        for field in (
            "completed_trades",
            "order_attempts",
            "rejected_orders",
            "incidents",
            "unmatched_reconciliations",
            "stale_data_events",
            "unresolved_recoveries",
        )
    )
    trades, attempts, rejections, incidents, unmatched, stale, recoveries = totals
    rejection_fraction = Decimal(rejections) / Decimal(attempts) if attempts else Decimal(0)
    missing = (
        tuple(sorted(set(plan.required_regimes) - regimes)),
        tuple(sorted(set(plan.required_symbols) - symbols)),
        tuple(sorted(set(plan.required_timeframes) - timeframes)),
        tuple(sorted(set(plan.required_strategy_categories) - strategies)),
    )
    reasons: set[str] = set()
    if evaluated_at < plan.window_end:
        reasons.add("WINDOW_OPEN")
    if len(sessions) < plan.minimum_sessions:
        reasons.add("INSUFFICIENT_SESSIONS")
    if len(days) < plan.minimum_market_days:
        reasons.add("INSUFFICIENT_MARKET_DAYS")
    if trades < plan.minimum_completed_trades:
        reasons.add("INSUFFICIENT_COMPLETED_TRADES")
    for values, reason in zip(
        missing,
        ("MISSING_REGIMES", "MISSING_SYMBOLS", "MISSING_TIMEFRAMES", "MISSING_STRATEGIES"),
        strict=True,
    ):
        if values:
            reasons.add(reason)
    failures = {
        reason
        for condition, reason in (
            (incidents > plan.maximum_incidents, "INCIDENT_LIMIT_EXCEEDED"),
            (
                unmatched > plan.maximum_unmatched_reconciliations,
                "UNMATCHED_RECONCILIATION_LIMIT_EXCEEDED",
            ),
            (stale > plan.maximum_stale_data_events, "STALE_DATA_LIMIT_EXCEEDED"),
            (rejection_fraction > plan.maximum_rejection_fraction, "REJECTION_LIMIT_EXCEEDED"),
            (recoveries > plan.maximum_unresolved_recoveries, "RECOVERY_LIMIT_EXCEEDED"),
        )
        if condition
    }
    reasons.update(failures)
    state = (
        ProspectiveBurnInState.FAIL
        if failures
        else ProspectiveBurnInState.IN_PROGRESS
        if reasons
        else ProspectiveBurnInState.PASS
    )
    root_hash = canonical_hash(tuple(canonical_hash(item) for item in ordered))
    identity = (
        plan.plan_id,
        evaluated_at,
        state,
        len(ordered),
        len(sessions),
        len(days),
        totals,
        rejection_fraction,
        missing,
        tuple(sorted(reasons)),
        root_hash,
    )
    return ProspectiveBurnInAssessment(
        deterministic_id("prospective_burn_in_assessment", identity),
        plan.plan_id,
        evaluated_at,
        state,
        len(ordered),
        len(sessions),
        len(days),
        trades,
        attempts,
        rejections,
        rejection_fraction,
        incidents,
        unmatched,
        stale,
        recoveries,
        *missing,
        tuple(sorted(reasons)),
        root_hash,
        canonical_hash(plan),
        plan.config_hash,
    )


def load_operator_request(path: str | Path) -> Mapping[str, object]:
    return MappingProxyType(_object(Path(path)))


def _observation(value: object) -> ProspectiveBurnInObservation:
    if not isinstance(value, dict) or set(value) != {
        "session_id",
        "market_day",
        "observed_at",
        "regime",
        "symbols",
        "timeframes",
        "strategy_categories",
        "completed_trades",
        "order_attempts",
        "rejected_orders",
        "incidents",
        "unmatched_reconciliations",
        "stale_data_events",
        "unresolved_recoveries",
        "evidence_hash",
        "environment",
    }:
        raise ValueError("Phase 9Y observation keys are invalid")
    fields = (
        _text(value["session_id"]),
        date.fromisoformat(_text(value["market_day"])),
        _time(value["observed_at"]),
        _text(value["regime"]),
        _names(value["symbols"]),
        _names(value["timeframes"]),
        _names(value["strategy_categories"]),
        _nonnegative_int(value["completed_trades"]),
        _nonnegative_int(value["order_attempts"]),
        _nonnegative_int(value["rejected_orders"]),
        _nonnegative_int(value["incidents"]),
        _nonnegative_int(value["unmatched_reconciliations"]),
        _nonnegative_int(value["stale_data_events"]),
        _nonnegative_int(value["unresolved_recoveries"]),
        _text(value["evidence_hash"]),
        _text(value["environment"]),
    )
    return ProspectiveBurnInObservation(
        deterministic_id("prospective_burn_in_observation", fields), *fields
    )


def _object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ProspectiveBurnInConfigError("configuration root must be an object")
    return value


def _time(value: object) -> datetime:
    result = datetime.fromisoformat(_text(value).replace("Z", "+00:00"))
    if not _utc(result):
        raise ValueError("Phase 9Y timestamp must be UTC")
    return result


def _names(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError("Phase 9Y name collection must be a list")
    result = tuple(_text(item) for item in value)
    if not result or result != tuple(sorted(set(result))):
        raise ValueError("Phase 9Y name collection must be sorted and unique")
    return result


def _text(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError("Phase 9Y text value is invalid")
    return value


def _positive_int(value: object) -> int:
    result = _nonnegative_int(value)
    if result == 0:
        raise ValueError("Phase 9Y positive integer is required")
    return result


def _nonnegative_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("Phase 9Y nonnegative integer is required")
    return value


def _fraction(value: object) -> Decimal:
    try:
        result = Decimal(_text(value))
        valid = result.is_finite() and Decimal(0) <= result <= Decimal(1)
    except InvalidOperation as error:
        raise ValueError("Phase 9Y fraction is invalid") from error
    if not valid:
        raise ValueError("Phase 9Y fraction is outside zero and one")
    return result


def _utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == UTC.utcoffset(value)


def _sha(value: str) -> bool:
    return value.startswith("sha256:") and len(value) == 71
