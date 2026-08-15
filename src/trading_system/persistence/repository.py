"""SQLite Phase 1A repositories with idempotent restart behavior."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from importlib.resources import files
from pathlib import Path

from trading_system.domain import Candle, Observation
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
        migration = files("trading_system.persistence.migrations").joinpath("001_phase_1a.sql")
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

    def counts(self) -> tuple[int, int, int]:
        counts: list[int] = []
        for table in ("runs", "candles", "feature_snapshots"):
            row = self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            assert row is not None
            counts.append(int(row[0]))
        return counts[0], counts[1], counts[2]

