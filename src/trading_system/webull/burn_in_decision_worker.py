"""Phase 11H local causal decision cycle over persisted Webull sandbox bars."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

from trading_system.config import ThresholdConfig
from trading_system.domain import Candle, DecisionAction, Timeframe
from trading_system.market_data import XNYSCalendar
from trading_system.market_data.aggregation import (
    aggregate_4h,
    aggregate_daily,
    aggregate_weekly,
)
from trading_system.paper import PaperRegistry, RuntimeState, stage_shadow_decision
from trading_system.persistence import RunRecord, SQLiteRepository
from trading_system.replay import CausalNarrativePipeline, ReplayEngine
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id


class BurnInDecisionWorkerConfigError(ValueError):
    """Raised when Phase 11H decision-worker authority is malformed."""


@dataclass(frozen=True, slots=True)
class BurnInDecisionWorkerConfig:
    plan_id: str
    strategy_config_hash: str
    signal_timeframes: tuple[Timeframe, ...]
    config_hash: str
    decision_worker_version: str = "11H.1.0"


@dataclass(frozen=True, slots=True)
class BurnInDecisionWorkerResult:
    cycle_id: str
    session_id: str
    run_id: str
    observed_at: datetime
    source_1h_candles: int
    derived_candles: int
    processed_candles: int
    emitted_decisions: int
    directional_decisions: int
    staged_shadow_intents: int
    config_hash: str
    decision_worker_version: str = "11H.1.0"
    market_data_source: str = "PERSISTED_WEBULL_SANDBOX"
    decision_mode: str = "LOCAL_CAUSAL_SHADOW"
    network_used: bool = False
    credentials_loaded: bool = False
    simulated_fills_enabled: bool = False
    broker_write_performed: bool = False
    live_trading_enabled: bool = False
    automatic_promotion_enabled: bool = False

    def __post_init__(self) -> None:
        counts = (
            self.source_1h_candles,
            self.derived_candles,
            self.processed_candles,
            self.emitted_decisions,
            self.directional_decisions,
            self.staged_shadow_intents,
        )
        if (
            not all((self.cycle_id, self.session_id, self.run_id, self.config_hash))
            or self.observed_at.tzinfo is None
            or self.observed_at.utcoffset() != UTC.utcoffset(self.observed_at)
            or min(counts) < 0
            or self.directional_decisions > self.emitted_decisions
            or self.staged_shadow_intents > self.directional_decisions
            or self.decision_worker_version != "11H.1.0"
            or self.market_data_source != "PERSISTED_WEBULL_SANDBOX"
            or self.decision_mode != "LOCAL_CAUSAL_SHADOW"
            or any(
                (
                    self.network_used,
                    self.credentials_loaded,
                    self.simulated_fills_enabled,
                    self.broker_write_performed,
                    self.live_trading_enabled,
                    self.automatic_promotion_enabled,
                )
            )
        ):
            raise ValueError("invalid Phase 11H decision worker result")


def load_burn_in_decision_worker_config(
    path: str | Path,
) -> BurnInDecisionWorkerConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "decision_worker_version",
        "mode",
        "plan_id",
        "strategy_config_hash",
        "signal_timeframes",
        "authority",
    }
    authority = raw.get("authority") if isinstance(raw, dict) else None
    expected_authority = {
        "database_read_enabled": True,
        "database_write_enabled": True,
        "shadow_intent_staging_enabled": True,
        "network_enabled": False,
        "credential_loading_enabled": False,
        "simulated_fills_enabled": False,
        "broker_writes_enabled": False,
        "sandbox_execution_enabled": False,
        "live_trading_enabled": False,
        "automatic_promotion_enabled": False,
    }
    timeframes = raw.get("signal_timeframes") if isinstance(raw, dict) else None
    if (
        not isinstance(raw, dict)
        or set(raw) != expected
        or raw["decision_worker_version"] != "11H.1.0"
        or raw["mode"] != "LOCAL_CAUSAL_SHADOW_DECISIONS"
        or not isinstance(raw["plan_id"], str)
        or not raw["plan_id"]
        or not _sha(raw["strategy_config_hash"])
        or not isinstance(timeframes, list)
        or not timeframes
        or any(not isinstance(value, str) for value in timeframes)
        or tuple(timeframes) != tuple(sorted(set(timeframes)))
        or not set(timeframes) <= {"1h", "4h"}
        or not isinstance(authority, dict)
        or set(authority) != set(expected_authority)
        or any(
            type(authority[key]) is not bool or authority[key] is not expected
            for key, expected in expected_authority.items()
        )
    ):
        raise BurnInDecisionWorkerConfigError(
            "Phase 11H configuration is invalid or unsafe"
        )
    return BurnInDecisionWorkerConfig(
        str(raw["plan_id"]),
        str(raw["strategy_config_hash"]),
        tuple(Timeframe(value) for value in timeframes),
        canonical_hash(_freeze(raw)),
    )


def run_burn_in_decision_cycle(
    repository: SQLiteRepository,
    config: BurnInDecisionWorkerConfig,
    thresholds: ThresholdConfig,
    *,
    session_id: str,
    observed_at: datetime,
) -> BurnInDecisionWorkerResult:
    """Materialize causal decisions and non-executable shadow intents from local bars."""
    if observed_at.tzinfo is None or observed_at.utcoffset() != UTC.utcoffset(observed_at):
        raise ValueError("Phase 11H observed_at must be UTC")
    if thresholds.config_hash != config.strategy_config_hash:
        raise ValueError("Phase 11H strategy configuration hash mismatch")
    session = _validate_session(repository, config, session_id, observed_at)
    source = _load_source_candles(repository, session_id, observed_at)
    if not source:
        raise ValueError("Phase 11H session has no persisted completed 1H bars")
    derived = _derived_candles(source, XNYSCalendar())
    candles = ReplayEngine.normalize((*source, *derived))
    run_id = deterministic_id(
        "burn_in_shadow_decision_run",
        (session_id, config.plan_id, config.config_hash, thresholds.config_hash),
    )
    seed = thresholds.section("determinism")["seed"]
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("Phase 11H strategy seed must be an integer")
    repository.insert_run(
        RunRecord(
            run_id,
            session[0],
            session[1],
            thresholds.config_hash,
            session[2],
            session[3],
            seed,
        )
    )
    pipeline = CausalNarrativePipeline(run_id, thresholds.config_hash, session[1])
    checkpoint = repository.load_checkpoint(run_id)
    resume_after = None if checkpoint is None else checkpoint[0]
    processed_before = 0 if checkpoint is None else checkpoint[1]
    prior_hash = "GENESIS" if checkpoint is None else checkpoint[2]
    if resume_after is not None:
        for candle in candles:
            if candle.close_time <= resume_after:
                pipeline.push(candle)

    new_decisions: list[tuple[str, datetime, Timeframe, DecisionAction]] = []

    def evaluate(candle: Candle) -> object:
        narrative = pipeline.push(candle)
        repository.insert_candle(candle)
        repository.insert_snapshot(narrative.observation)
        for level in narrative.levels:
            repository.insert_level(level)
        for event in narrative.pattern_events:
            repository.insert_pattern_event(event)
        repository.insert_decision(narrative.decision)
        decision = narrative.decision
        new_decisions.append(
            (decision.decision_id, decision.known_at, candle.timeframe, decision.action)
        )
        return {
            "observation_id": narrative.observation.observation_id,
            "pattern_event_ids": tuple(event.event_id for event in narrative.pattern_events),
            "decision_id": decision.decision_id,
            "action": decision.action,
        }

    records, next_checkpoint = ReplayEngine(evaluate).run(
        candles,
        resume_after=resume_after,
        processed_before=processed_before,
        prior_state_hash=prior_hash,
    )
    if next_checkpoint is not None:
        repository.save_checkpoint(
            run_id,
            next_checkpoint.last_close_time,
            next_checkpoint.processed_candles,
            next_checkpoint.state_hash,
        )
    directional = tuple(
        item
        for item in new_decisions
        if item[2] in config.signal_timeframes
        and item[3] in {DecisionAction.LONG, DecisionAction.SHORT}
    )
    staged = 0
    calendar = XNYSCalendar()
    for decision_id, known_at, _timeframe, _action in directional:
        if observed_at < _next_session_open(known_at, calendar):
            stage_shadow_decision(
                repository,
                session_id,
                decision_id,
                observed_at,
                calendar,
            )
            staged += 1
    result = BurnInDecisionWorkerResult(
        deterministic_id(
            "burn_in_shadow_decision_cycle",
            (session_id, observed_at, config.config_hash, run_id),
        ),
        session_id,
        run_id,
        observed_at,
        len(source),
        len(derived),
        len(records),
        len(new_decisions),
        len(directional),
        staged,
        config.config_hash,
    )
    _insert_cycle(repository, result)
    return result


def _validate_session(
    repository: SQLiteRepository,
    config: BurnInDecisionWorkerConfig,
    session_id: str,
    observed_at: datetime,
) -> tuple[datetime, str, str, str]:
    paper = PaperRegistry(repository)
    if paper.current_state(session_id) is not RuntimeState.SHADOW:
        raise ValueError("Phase 11H requires a SHADOW paper session")
    row = repository.connection.execute(
        """SELECT s.created_at,s.code_version,s.data_revision,s.calendar_version,b.plan_id,
                  b.code_version,b.data_revision,b.calendar_version,b.config_hash,s.config_hash
           FROM paper_sessions s JOIN paper_burn_in_session_bindings b
             ON b.session_id=s.session_id WHERE s.session_id=?""",
        (session_id,),
    ).fetchone()
    if row is None or str(row[4]) != config.plan_id:
        raise ValueError("Phase 11H session is not bound to the configured plan")
    if (row[1], row[2], row[3], row[9]) != (row[5], row[6], row[7], row[8]):
        raise ValueError("Phase 11H session and binding runtime identities differ")
    created_at = _parse_time(row[0])
    if created_at > observed_at:
        raise ValueError("Phase 11H session is future-known")
    cycle = repository.connection.execute(
        """SELECT 1 FROM webull_burn_in_worker_cycles
           WHERE session_id=? AND observed_at<=? ORDER BY observed_at DESC LIMIT 1""",
        (session_id, _time(observed_at)),
    ).fetchone()
    if cycle != (1,):
        raise ValueError("Phase 11H requires a successful causal Phase 11G worker cycle")
    return created_at, str(row[1]), str(row[2]), str(row[3])


def _load_source_candles(
    repository: SQLiteRepository,
    session_id: str,
    observed_at: datetime,
) -> tuple[Candle, ...]:
    rows = repository.connection.execute(
        """SELECT c.symbol,c.timeframe,c.open_time,c.close_time,c.session_date,
                  c.open,c.high,c.low,c.close,c.volume,c.is_complete,
                  c.adjustment_factor,c.source,c.source_revision,c.candle_id,
                  c.raw_open,c.raw_high,c.raw_low,c.raw_close,c.raw_volume
           FROM webull_shadow_bars w JOIN candles c ON c.candle_id=w.candle_id
           WHERE w.session_id=? AND w.known_at<=? AND c.timeframe='1h'
           ORDER BY c.close_time,c.symbol,c.open_time,c.candle_id""",
        (session_id, _time(observed_at)),
    ).fetchall()
    candles = tuple(_candle(row) for row in rows)
    identities = [(item.symbol, item.timeframe, item.open_time) for item in candles]
    if len(identities) != len(set(identities)):
        raise ValueError("Phase 11H found conflicting persisted source-bar revisions")
    return candles


def _candle(row: tuple[object, ...]) -> Candle:
    return Candle(
        symbol=str(row[0]),
        timeframe=Timeframe(str(row[1])),
        open_time=_parse_time(row[2]),
        close_time=_parse_time(row[3]),
        session_date=date.fromisoformat(str(row[4])),
        open=Decimal(str(row[5])),
        high=Decimal(str(row[6])),
        low=Decimal(str(row[7])),
        close=Decimal(str(row[8])),
        volume=Decimal(str(row[9])),
        is_complete=bool(row[10]),
        adjustment_factor=Decimal(str(row[11])),
        source=str(row[12]),
        source_revision=str(row[13]),
        candle_id=str(row[14]),
        raw_open=Decimal(str(row[15])),
        raw_high=Decimal(str(row[16])),
        raw_low=Decimal(str(row[17])),
        raw_close=Decimal(str(row[18])),
        raw_volume=Decimal(str(row[19])),
    )


def _derived_candles(
    source: Iterable[Candle], calendar: XNYSCalendar
) -> tuple[Candle, ...]:
    by_symbol_session: dict[tuple[str, date], list[Candle]] = defaultdict(list)
    for candle in source:
        by_symbol_session[(candle.symbol, candle.session_date)].append(candle)
    four_hour: list[Candle] = []
    daily: list[Candle] = []
    for key in sorted(by_symbol_session):
        group = sorted(by_symbol_session[key], key=lambda item: item.open_time)
        revision = canonical_hash(tuple(item.source_revision for item in group))
        normalized = tuple(
            replace(item, source_revision=revision, candle_id="") for item in group
        )
        four_hour.extend(aggregate_4h(normalized, calendar))
        daily.extend(aggregate_daily(normalized, calendar))
    weekly: list[Candle] = []
    by_symbol_week: dict[tuple[str, date], list[Candle]] = defaultdict(list)
    for candle in daily:
        monday = candle.session_date - timedelta(days=candle.session_date.weekday())
        by_symbol_week[(candle.symbol, monday)].append(candle)
    for key in sorted(by_symbol_week):
        group = sorted(by_symbol_week[key], key=lambda item: item.open_time)
        revision = canonical_hash(tuple(item.source_revision for item in group))
        normalized = tuple(
            replace(item, source_revision=revision, candle_id="") for item in group
        )
        weekly.extend(aggregate_weekly(normalized, calendar))
    return tuple((*four_hour, *daily, *weekly))


def _next_session_open(known_at: datetime, calendar: XNYSCalendar) -> datetime:
    for offset in range(15):
        bounds = calendar.bounds(known_at.date() + timedelta(days=offset))
        if bounds is not None and bounds[0] > known_at:
            return bounds[0]
    raise ValueError("Phase 11H found no next XNYS session within 15 days")


def _insert_cycle(
    repository: SQLiteRepository, item: BurnInDecisionWorkerResult
) -> bool:
    payload_json = canonical_json(item)
    payload_hash = canonical_hash(item)
    values = (
        item.cycle_id,
        item.session_id,
        item.run_id,
        _time(item.observed_at),
        item.config_hash,
        item.source_1h_candles,
        item.derived_candles,
        item.processed_candles,
        item.emitted_decisions,
        item.directional_decisions,
        item.staged_shadow_intents,
        payload_json,
        payload_hash,
    )
    cursor = repository.connection.execute(
        """INSERT OR IGNORE INTO burn_in_shadow_decision_cycles
           (cycle_id,session_id,run_id,observed_at,config_hash,source_1h_candles,
            derived_candles,processed_candles,emitted_decisions,directional_decisions,
            staged_shadow_intents,payload_json,payload_hash)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        values,
    )
    if cursor.rowcount == 0:
        stored = repository.connection.execute(
            """SELECT cycle_id,session_id,run_id,observed_at,config_hash,
                      source_1h_candles,derived_candles,processed_candles,
                      emitted_decisions,directional_decisions,staged_shadow_intents,
                      payload_json,payload_hash
               FROM burn_in_shadow_decision_cycles WHERE cycle_id=?""",
            (item.cycle_id,),
        ).fetchone()
        if stored != values:
            raise ValueError(f"conflicting Phase 11H decision cycle: {item.cycle_id}")
        return False
    repository.connection.commit()
    return True


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Phase 11H timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_time(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Phase 11H timestamps must be timezone-aware")
    return parsed.astimezone(UTC)


def _sha(value: object) -> bool:
    return isinstance(value, str) and value.startswith("sha256:") and len(value) == 71


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value
