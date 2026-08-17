"""SQLite Phase 1A repositories with idempotent restart behavior."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from importlib.resources import files
from pathlib import Path

from trading_system.domain import Candle, Decision, Level, Observation, PatternEvent, TradeEvent
from trading_system.serialization import canonical_hash, canonical_json


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("database timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _decimal(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


@dataclass(frozen=True, slots=True)
class RunRecord:
    run_id: str
    started_at: datetime
    code_version: str
    config_hash: str
    data_revision: str
    calendar_version: str
    random_seed: int
    status: str = "RUNNING"


class SQLiteRepository:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA foreign_keys = ON")

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> SQLiteRepository:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def migrate(self) -> None:
        migrations = files("trading_system.persistence.migrations")
        for migration in sorted(
            (item for item in migrations.iterdir() if item.name.endswith(".sql")),
            key=lambda item: item.name,
        ):
            self.connection.executescript(migration.read_text(encoding="utf-8"))
        self.connection.commit()

    def insert_run(self, run: RunRecord) -> bool:
        values = (
            run.run_id,
            _time(run.started_at),
            run.code_version,
            run.config_hash,
            run.data_revision,
            run.calendar_version,
            run.random_seed,
            run.status,
        )
        cursor = self.connection.execute(
            """INSERT OR IGNORE INTO runs
               (run_id, started_at, code_version, config_hash, data_revision,
                calendar_version, random_seed, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            values,
        )
        if cursor.rowcount == 0:
            stored = self.connection.execute(
                """SELECT run_id, started_at, code_version, config_hash, data_revision,
                          calendar_version, random_seed, status FROM runs WHERE run_id = ?""",
                (run.run_id,),
            ).fetchone()
            if stored != values:
                raise ValueError(f"conflicting run payload: {run.run_id}")
            return False
        self.connection.commit()
        return True

    def insert_candle(self, candle: Candle) -> bool:
        payload_hash = canonical_hash(candle)
        values = (
            candle.candle_id, candle.symbol, candle.timeframe.value,
            _time(candle.open_time), _time(candle.close_time), candle.session_date.isoformat(),
            _decimal(candle.open), _decimal(candle.high), _decimal(candle.low),
            _decimal(candle.close), _decimal(candle.volume), _decimal(candle.raw_open),
            _decimal(candle.raw_high), _decimal(candle.raw_low), _decimal(candle.raw_close),
            _decimal(candle.raw_volume), _decimal(candle.adjustment_factor),
            int(candle.is_complete), candle.source, candle.source_revision, payload_hash,
        )
        cursor = self.connection.execute(
            """INSERT OR IGNORE INTO candles
               (candle_id, symbol, timeframe, open_time, close_time, session_date,
                open, high, low, close, volume, raw_open, raw_high, raw_low, raw_close,
                raw_volume, adjustment_factor, is_complete, source, source_revision, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            values,
        )
        if cursor.rowcount == 0:
            stored = self.connection.execute(
                "SELECT payload_hash FROM candles WHERE candle_id = ?", (candle.candle_id,)
            ).fetchone()
            if stored != (payload_hash,):
                raise ValueError(f"conflicting candle payload: {candle.candle_id}")
            return False
        self.connection.commit()
        return True

    def insert_snapshot(self, observation: Observation) -> bool:
        payload_hash = canonical_hash(observation)
        values = (
            observation.observation_id, observation.run_id, observation.candle_id,
            _time(observation.known_at), observation.schema_version,
            observation.input_fingerprint, canonical_json(observation.features),
            canonical_json(observation.data_quality), payload_hash,
        )
        cursor = self.connection.execute(
            """INSERT OR IGNORE INTO feature_snapshots
               (observation_id, run_id, candle_id, known_at, schema_version,
                input_fingerprint, features_json, data_quality_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            values,
        )
        if cursor.rowcount == 0:
            stored = self.connection.execute(
                "SELECT payload_hash FROM feature_snapshots WHERE observation_id = ?",
                (observation.observation_id,),
            ).fetchone()
            if stored != (payload_hash,):
                raise ValueError(f"conflicting snapshot payload: {observation.observation_id}")
            return False
        self.connection.commit()
        return True

    def insert_level(self, level: Level) -> bool:
        payload_hash = canonical_hash(level)
        values = (
            level.level_id,
            level.run_id,
            level.symbol,
            level.timeframe.value,
            _time(level.known_at),
            _decimal(level.lower_price),
            _decimal(level.upper_price),
            level.kind.value,
            _decimal(level.confluence_score),
            canonical_json(level.evidence_candle_ids),
            payload_hash,
        )
        cursor = self.connection.execute(
            """INSERT OR IGNORE INTO levels
               (level_id, run_id, symbol, timeframe, known_at, lower_price, upper_price,
                kind, confluence_score, evidence_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            values,
        )
        if cursor.rowcount == 0:
            stored = self.connection.execute(
                "SELECT payload_hash FROM levels WHERE level_id = ?", (level.level_id,)
            ).fetchone()
            if stored != (payload_hash,):
                raise ValueError(f"conflicting level payload: {level.level_id}")
            return False
        self.connection.commit()
        return True

    def insert_pattern_event(self, event: PatternEvent) -> bool:
        payload_hash = canonical_hash(event)
        payload = {
            "features": event.features,
            "evidence_candle_ids": event.evidence_candle_ids,
            "reason_codes": event.reason_codes,
            "config_hash": event.config_hash,
            "code_version": event.code_version,
        }
        values = (
            event.event_id,
            event.run_id,
            event.observation_id,
            event.instance_id,
            _time(event.known_at),
            event.pattern_family,
            event.pattern_name,
            event.pattern_version,
            event.prior_state.value if event.prior_state is not None else None,
            event.new_state.value,
            event.direction.value,
            _decimal(event.reference_level),
            canonical_json(payload),
            payload_hash,
        )
        cursor = self.connection.execute(
            """INSERT OR IGNORE INTO pattern_events
               (event_id, run_id, observation_id, instance_id, known_at, pattern_family,
                pattern_name, pattern_version, prior_state, new_state, direction,
                reference_level, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            values,
        )
        if cursor.rowcount == 0:
            stored = self.connection.execute(
                "SELECT payload_hash FROM pattern_events WHERE event_id = ?", (event.event_id,)
            ).fetchone()
            if stored != (payload_hash,):
                raise ValueError(f"conflicting pattern event payload: {event.event_id}")
            return False
        self.connection.commit()
        return True

    def insert_decision(self, decision: Decision) -> bool:
        payload_hash = canonical_hash(decision)
        reasons = (*decision.missing_conditions, *decision.rejection_reasons)
        values = (
            decision.decision_id,
            decision.run_id,
            decision.observation_id,
            _time(decision.known_at),
            decision.action.value,
            _decimal(decision.confidence),
            _decimal(decision.setup_quality),
            _decimal(decision.entry_quality),
            canonical_json(reasons),
            decision.to_json(),
            payload_hash,
        )
        cursor = self.connection.execute(
            """INSERT OR IGNORE INTO decisions
               (decision_id, run_id, observation_id, known_at, action, confidence,
                setup_quality, entry_quality, reason_codes_json, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            values,
        )
        if cursor.rowcount == 0:
            stored = self.connection.execute(
                "SELECT payload_hash FROM decisions WHERE decision_id = ?",
                (decision.decision_id,),
            ).fetchone()
            if stored != (payload_hash,):
                raise ValueError(f"conflicting decision payload: {decision.decision_id}")
            return False
        self.connection.commit()
        return True

    def insert_trade_event(self, event: TradeEvent) -> bool:
        payload_hash = canonical_hash(event)
        values = (
            event.trade_event_id,
            event.run_id,
            event.trade_id,
            _time(event.event_time),
            event.event_type.value,
            _decimal(event.price),
            _decimal(event.quantity),
            canonical_json(event.payload),
            payload_hash,
        )
        cursor = self.connection.execute(
            """INSERT OR IGNORE INTO trade_events
               (trade_event_id, run_id, trade_id, event_time, event_type, price,
                quantity, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            values,
        )
        if cursor.rowcount == 0:
            stored = self.connection.execute(
                "SELECT payload_hash FROM trade_events WHERE trade_event_id = ?",
                (event.trade_event_id,),
            ).fetchone()
            if stored != (payload_hash,):
                raise ValueError(f"conflicting trade event payload: {event.trade_event_id}")
            return False
        self.connection.commit()
        return True

    def counts(self) -> tuple[int, int, int]:
        counts: list[int] = []
        for table in ("runs", "candles", "feature_snapshots"):
            row = self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            assert row is not None
            counts.append(int(row[0]))
        return counts[0], counts[1], counts[2]
