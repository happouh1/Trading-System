"""Deterministic Phase 12I bearish-regime and short-opportunity research overlay."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id


class ShortOpportunityConfigError(ValueError):
    """Raised when Phase 12I configuration is malformed or unsafe."""


class ShortOpportunityState(StrEnum):
    WATCH = "WATCH"
    ARMED = "ARMED"
    TRIGGER = "TRIGGER"
    TOO_LATE = "TOO_LATE"


class BearishRegimeState(StrEnum):
    CONFIRMED = "BEARISH_CONFIRMED"
    DEVELOPING = "BEARISH_DEVELOPING"
    NOT_CONFIRMED = "NOT_BEARISH"


@dataclass(frozen=True, slots=True)
class ShortOpportunityConfig:
    plan_id: str
    universe: tuple[str, ...]
    benchmark_symbols: tuple[str, ...]
    signal_timeframes: tuple[str, ...]
    minimum_bearish_benchmarks: int
    minimum_bearish_breadth: Decimal
    armed_min_setup_quality: Decimal
    armed_min_entry_quality: Decimal
    horizons: tuple[int, ...]
    config_hash: str
    overlay_version: str = "12I.1.0"


@dataclass(frozen=True, slots=True)
class ShortRegimeSnapshot:
    snapshot_id: str
    session_id: str
    run_id: str
    observed_at: datetime
    config_hash: str
    bearish_benchmarks: int
    evaluated_benchmarks: int
    bearish_breadth: Decimal
    regime_state: BearishRegimeState
    bearish_symbols: tuple[str, ...]
    evaluated_symbols: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ShortOpportunityAlert:
    alert_id: str
    snapshot_id: str
    session_id: str
    run_id: str
    decision_id: str
    observation_id: str
    symbol: str
    timeframe: str
    known_at: datetime
    state: ShortOpportunityState
    setup_quality: Decimal
    entry_quality: Decimal
    entry_reference: Decimal
    reason_codes: tuple[str, ...]
    regime_state: BearishRegimeState
    timeframe_states: Mapping[str, str]
    broker_write_performed: bool = False


@dataclass(frozen=True, slots=True)
class ShortOpportunityResult:
    snapshot: ShortRegimeSnapshot
    alerts: tuple[ShortOpportunityAlert, ...]
    inserted_alerts: int
    watch: int
    armed: int
    trigger: int
    too_late: int
    broker_write_performed: bool = False
    network_used: bool = False


def load_short_opportunity_config(path: str | Path) -> ShortOpportunityConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "overlay_version",
        "mode",
        "plan_id",
        "universe",
        "benchmark_symbols",
        "signal_timeframes",
        "regime",
        "classification",
        "outcomes",
        "authority",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise ShortOpportunityConfigError("Phase 12I configuration keys are invalid")
    universe = _symbols(raw["universe"], "universe")
    benchmarks = _symbols(raw["benchmark_symbols"], "benchmark_symbols")
    timeframes = raw["signal_timeframes"]
    regime = raw["regime"]
    classification = raw["classification"]
    outcomes = raw["outcomes"]
    authority = raw["authority"]
    if (
        raw["overlay_version"] != "12I.1.0"
        or raw["mode"] != "SHADOW_RESEARCH_ONLY"
        or not isinstance(raw["plan_id"], str)
        or not raw["plan_id"]
        or not set(benchmarks) <= set(universe)
        or not isinstance(timeframes, list)
        or tuple(timeframes) != tuple(sorted(set(timeframes)))
        or not set(timeframes) <= {"1h", "4h"}
        or not isinstance(regime, dict)
        or set(regime) != {"minimum_bearish_benchmarks", "minimum_bearish_breadth"}
        or not isinstance(classification, dict)
        or set(classification) != {"armed_min_setup_quality", "armed_min_entry_quality"}
        or not isinstance(outcomes, dict)
        or set(outcomes) != {"horizon_bars"}
        or not isinstance(authority, dict)
        or authority
        != {
            "database_read_enabled": True,
            "database_write_enabled": True,
            "network_enabled": False,
            "credential_loading_enabled": False,
            "shadow_only": True,
            "broker_writes_enabled": False,
            "live_trading_enabled": False,
            "automatic_promotion_enabled": False,
        }
    ):
        raise ShortOpportunityConfigError("Phase 12I configuration is invalid or unsafe")
    minimum_benchmarks = regime["minimum_bearish_benchmarks"]
    breadth = _decimal(regime["minimum_bearish_breadth"], "minimum bearish breadth")
    setup = _decimal(classification["armed_min_setup_quality"], "armed setup quality")
    entry = _decimal(classification["armed_min_entry_quality"], "armed entry quality")
    horizons = outcomes["horizon_bars"]
    if (
        isinstance(minimum_benchmarks, bool)
        or not isinstance(minimum_benchmarks, int)
        or not 1 <= minimum_benchmarks <= len(benchmarks)
        or not Decimal("0") <= breadth <= Decimal("1")
        or not Decimal("0") <= setup <= Decimal("100")
        or not Decimal("0") <= entry <= Decimal("100")
        or not isinstance(horizons, list)
        or not horizons
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in horizons
        )
        or tuple(horizons) != tuple(sorted(set(horizons)))
    ):
        raise ShortOpportunityConfigError("Phase 12I thresholds are invalid")
    return ShortOpportunityConfig(
        str(raw["plan_id"]),
        universe,
        benchmarks,
        tuple(str(value) for value in timeframes),
        minimum_benchmarks,
        breadth,
        setup,
        entry,
        tuple(horizons),
        canonical_hash(_freeze(raw)),
    )


def materialize_short_opportunities(
    repository: SQLiteRepository,
    config: ShortOpportunityConfig,
    *,
    session_id: str,
    observed_at: datetime,
) -> ShortOpportunityResult:
    """Persist early short states from the latest immutable decision cycle."""
    _utc(observed_at)
    cycle = repository.connection.execute(
        """SELECT run_id FROM burn_in_shadow_decision_cycles
           WHERE session_id=? AND observed_at<=?
           ORDER BY observed_at DESC,cycle_id DESC LIMIT 1""",
        (session_id, _time(observed_at)),
    ).fetchone()
    if cycle is None:
        raise ValueError("Phase 12I requires a completed shadow decision cycle")
    run_id = str(cycle[0])
    _validate_plan(repository, config.plan_id, session_id)
    rows = _decision_rows(repository, run_id, observed_at, config.universe)
    if not rows:
        raise ValueError("Phase 12I found no causal decisions for the configured universe")
    snapshot = _regime_snapshot(config, session_id, run_id, observed_at, rows)
    _insert_snapshot(repository, snapshot)
    alerts: list[ShortOpportunityAlert] = []
    inserted = 0
    for row in rows:
        payload = json.loads(str(row[9]))
        if payload.get("direction") != "SHORT" or str(row[3]) not in config.signal_timeframes:
            continue
        reasons = tuple(str(value) for value in json.loads(str(row[8])))
        state = _classify(
            str(row[6]),
            Decimal(str(row[7])),
            Decimal(str(row[5])),
            reasons,
            snapshot.regime_state,
            config,
        )
        states_raw = payload.get("timeframe_states", {})
        states = (
            MappingProxyType({str(key): str(value) for key, value in states_raw.items()})
            if isinstance(states_raw, dict)
            else MappingProxyType({})
        )
        item = ShortOpportunityAlert(
            deterministic_id("short_opportunity_alert", (str(row[0]), state, config.config_hash)),
            snapshot.snapshot_id,
            session_id,
            run_id,
            str(row[0]),
            str(row[1]),
            str(row[2]),
            str(row[3]),
            _parse_time(row[4]),
            state,
            Decimal(str(row[7])),
            Decimal(str(row[5])),
            Decimal(str(row[10])),
            reasons,
            snapshot.regime_state,
            states,
        )
        inserted += int(_insert_alert(repository, item))
        alerts.append(item)
    counts = {state: sum(item.state is state for item in alerts) for state in ShortOpportunityState}
    return ShortOpportunityResult(
        snapshot,
        tuple(alerts),
        inserted,
        counts[ShortOpportunityState.WATCH],
        counts[ShortOpportunityState.ARMED],
        counts[ShortOpportunityState.TRIGGER],
        counts[ShortOpportunityState.TOO_LATE],
    )


def label_short_opportunity_outcomes(
    repository: SQLiteRepository,
    config: ShortOpportunityConfig,
    *,
    as_of: datetime,
) -> int:
    """Append percentage-return labels only after their future bars are available."""
    _utc(as_of)
    rows = repository.connection.execute(
        """SELECT alert_id,symbol,timeframe,known_at,entry_reference
           FROM short_opportunity_alerts ORDER BY known_at,alert_id"""
    ).fetchall()
    inserted = 0
    for alert_id, symbol, timeframe, known_at, fallback_entry in rows:
        future = repository.connection.execute(
            """SELECT open,high,low,close,close_time FROM candles
               WHERE symbol=? AND timeframe=? AND open_time>=? AND close_time<=?
               ORDER BY open_time,candle_id""",
            (symbol, timeframe, known_at, _time(as_of)),
        ).fetchall()
        for horizon in config.horizons:
            if len(future) < horizon:
                continue
            window = future[:horizon]
            entry_price = Decimal(str(window[0][0])) if window else Decimal(str(fallback_entry))
            if entry_price <= 0:
                continue
            close = Decimal(str(window[-1][3]))
            lowest = min(Decimal(str(item[2])) for item in window)
            highest = max(Decimal(str(item[1])) for item in window)
            forward_return = (entry_price - close) / entry_price
            mfe_return = (entry_price - lowest) / entry_price
            mae_return = (highest - entry_price) / entry_price
            label_available_at = _parse_time(window[-1][4])
            outcome = {
                "alert_id": str(alert_id),
                "horizon_bars": horizon,
                "label_available_at": label_available_at,
                "entry_price": entry_price,
                "forward_return": forward_return,
                "mfe_return": mfe_return,
                "mae_return": mae_return,
                "label_version": config.overlay_version,
            }
            outcome_id = deterministic_id(
                "short_opportunity_outcome",
                (alert_id, horizon, config.config_hash),
            )
            values = (
                outcome_id,
                alert_id,
                horizon,
                _time(label_available_at),
                _number(entry_price),
                _number(forward_return),
                _number(mfe_return),
                _number(mae_return),
                canonical_json(outcome),
                canonical_hash(outcome),
            )
            cursor = repository.connection.execute(
                """INSERT OR IGNORE INTO short_opportunity_outcomes
                   (outcome_id,alert_id,horizon_bars,label_available_at,entry_price,
                    forward_return,mfe_return,mae_return,payload_json,payload_hash)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                values,
            )
            inserted += int(cursor.rowcount > 0)
    repository.connection.commit()
    return inserted


def _decision_rows(
    repository: SQLiteRepository,
    run_id: str,
    observed_at: datetime,
    universe: tuple[str, ...],
) -> list[tuple[object, ...]]:
    placeholders = ",".join("?" for _ in universe)
    return repository.connection.execute(
        f"""SELECT d.decision_id,d.observation_id,c.symbol,c.timeframe,d.known_at,
                    d.entry_quality,d.action,d.setup_quality,d.reason_codes_json,
                    d.payload_json,c.close
             FROM decisions d
             JOIN feature_snapshots f ON f.observation_id=d.observation_id
             JOIN candles c ON c.candle_id=f.candle_id
             WHERE d.run_id=? AND d.known_at<=? AND c.symbol IN ({placeholders})
             ORDER BY d.known_at,c.symbol,c.timeframe,d.decision_id""",
        (run_id, _time(observed_at), *universe),
    ).fetchall()


def _regime_snapshot(
    config: ShortOpportunityConfig,
    session_id: str,
    run_id: str,
    observed_at: datetime,
    rows: list[tuple[object, ...]],
) -> ShortRegimeSnapshot:
    latest: dict[str, tuple[datetime, Mapping[str, object]]] = {}
    for row in rows:
        if str(row[3]) != "1h":
            continue
        payload = json.loads(str(row[9]))
        known_at = _parse_time(row[4])
        prior = latest.get(str(row[2]))
        if prior is None or prior[0] < known_at:
            latest[str(row[2])] = (known_at, payload)
    bearish: list[str] = []
    for symbol, (_, payload) in latest.items():
        raw = payload.get("timeframe_states", {})
        state = str(raw.get("1h", "UNKNOWN")) if isinstance(raw, dict) else "UNKNOWN"
        if state == "DOWNTREND":
            bearish.append(symbol)
    evaluated = tuple(sorted(latest))
    bearish_symbols = tuple(sorted(bearish))
    evaluated_benchmarks = tuple(symbol for symbol in config.benchmark_symbols if symbol in latest)
    bearish_benchmarks = sum(symbol in bearish_symbols for symbol in evaluated_benchmarks)
    breadth = Decimal(len(bearish_symbols)) / Decimal(len(evaluated)) if evaluated else Decimal("0")
    if (
        bearish_benchmarks >= config.minimum_bearish_benchmarks
        and breadth >= config.minimum_bearish_breadth
    ):
        state = BearishRegimeState.CONFIRMED
    elif bearish_benchmarks > 0 or bearish_symbols:
        state = BearishRegimeState.DEVELOPING
    else:
        state = BearishRegimeState.NOT_CONFIRMED
    snapshot_id = deterministic_id(
        "short_regime_snapshot", (session_id, run_id, observed_at, config.config_hash)
    )
    return ShortRegimeSnapshot(
        snapshot_id,
        session_id,
        run_id,
        observed_at,
        config.config_hash,
        bearish_benchmarks,
        len(evaluated_benchmarks),
        breadth,
        state,
        bearish_symbols,
        evaluated,
    )


def _classify(
    action: str,
    setup_quality: Decimal,
    entry_quality: Decimal,
    reasons: tuple[str, ...],
    regime: BearishRegimeState,
    config: ShortOpportunityConfig,
) -> ShortOpportunityState:
    if action == "SHORT":
        return ShortOpportunityState.TRIGGER
    if "ENTRY_EXTENDED" in reasons:
        return ShortOpportunityState.TOO_LATE
    blockers = {"INVALID_OR_MISSING_DATA", "MTF_CONFLICT", "POOR_RUNWAY", "POOR_REWARD_RISK"}
    if (
        regime is BearishRegimeState.CONFIRMED
        and not blockers.intersection(reasons)
        and setup_quality >= config.armed_min_setup_quality
        and entry_quality >= config.armed_min_entry_quality
    ):
        return ShortOpportunityState.ARMED
    return ShortOpportunityState.WATCH


def _insert_snapshot(repository: SQLiteRepository, item: ShortRegimeSnapshot) -> bool:
    payload = canonical_json(item)
    payload_hash = canonical_hash(item)
    values = (
        item.snapshot_id,
        item.session_id,
        item.run_id,
        _time(item.observed_at),
        item.config_hash,
        item.bearish_benchmarks,
        item.evaluated_benchmarks,
        _number(item.bearish_breadth),
        item.regime_state.value,
        payload,
        payload_hash,
    )
    cursor = repository.connection.execute(
        """INSERT OR IGNORE INTO short_regime_snapshots
           (snapshot_id,session_id,run_id,observed_at,config_hash,bearish_benchmarks,
            evaluated_benchmarks,bearish_breadth,regime_state,payload_json,payload_hash)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        values,
    )
    if cursor.rowcount == 0:
        stored = repository.connection.execute(
            "SELECT payload_hash FROM short_regime_snapshots WHERE snapshot_id=?",
            (item.snapshot_id,),
        ).fetchone()
        if stored != (payload_hash,):
            raise ValueError(f"conflicting short regime snapshot: {item.snapshot_id}")
        return False
    repository.connection.commit()
    return True


def _insert_alert(repository: SQLiteRepository, item: ShortOpportunityAlert) -> bool:
    payload = canonical_json(item)
    payload_hash = canonical_hash(item)
    values = (
        item.alert_id,
        item.snapshot_id,
        item.session_id,
        item.run_id,
        item.decision_id,
        item.observation_id,
        item.symbol,
        item.timeframe,
        _time(item.known_at),
        item.state.value,
        _number(item.setup_quality),
        _number(item.entry_quality),
        _number(item.entry_reference),
        canonical_json(item.reason_codes),
        payload,
        payload_hash,
    )
    cursor = repository.connection.execute(
        """INSERT OR IGNORE INTO short_opportunity_alerts
           (alert_id,snapshot_id,session_id,run_id,decision_id,observation_id,symbol,
            timeframe,known_at,state,setup_quality,entry_quality,entry_reference,
            reason_codes_json,payload_json,payload_hash)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        values,
    )
    if cursor.rowcount == 0:
        stored = repository.connection.execute(
            "SELECT payload_hash FROM short_opportunity_alerts WHERE alert_id=?",
            (item.alert_id,),
        ).fetchone()
        if stored != (payload_hash,):
            raise ValueError(f"conflicting short opportunity alert: {item.alert_id}")
        return False
    repository.connection.commit()
    return True


def _validate_plan(repository: SQLiteRepository, plan_id: str, session_id: str) -> None:
    row = repository.connection.execute(
        "SELECT plan_id FROM paper_burn_in_session_bindings WHERE session_id=?",
        (session_id,),
    ).fetchone()
    if row != (plan_id,):
        raise ValueError("Phase 12I session is not bound to the configured plan")


def _symbols(value: object, name: str) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or item != item.upper() for item in value)
        or tuple(value) != tuple(sorted(set(value)))
    ):
        raise ShortOpportunityConfigError(f"Phase 12I {name} must be sorted uppercase symbols")
    return tuple(value)


def _decimal(value: object, name: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ShortOpportunityConfigError(f"Phase 12I {name} must be numeric")
    result = Decimal(str(value))
    if not result.is_finite():
        raise ShortOpportunityConfigError(f"Phase 12I {name} must be finite")
    return result


def _number(value: Decimal) -> str:
    return format(value, "f")


def _utc(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("Phase 12I timestamps must be UTC")


def _time(value: datetime) -> str:
    _utc(value)
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_time(value: object) -> datetime:
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
    _utc(result)
    return result


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value
