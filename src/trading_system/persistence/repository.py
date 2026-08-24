"""SQLite Phase 1A repositories with idempotent restart behavior."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from importlib.resources import files
from pathlib import Path

from trading_system.backtest import CompletedTrade, TradeResult
from trading_system.domain import (
    Candle,
    Decision,
    DecisionAction,
    Direction,
    Level,
    Observation,
    Outcome,
    PatternEvent,
    Timeframe,
    TradeEvent,
    TradePlan,
)
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

    def run_metadata(self, run_id: str) -> tuple[str, str, str, str, int] | None:
        row = self.connection.execute(
            """SELECT code_version, config_hash, data_revision, calendar_version, random_seed
               FROM runs WHERE run_id = ?""",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        return str(row[0]), str(row[1]), str(row[2]), str(row[3]), int(row[4])

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

    def insert_outcome(self, outcome: Outcome) -> bool:
        payload_hash = canonical_hash(outcome)
        values = (
            outcome.outcome_id,
            outcome.run_id,
            outcome.observation_id,
            outcome.label_version,
            outcome.horizon_bars,
            _decimal(outcome.forward_return),
            _decimal(outcome.mfe_r),
            _decimal(outcome.mae_r),
            outcome.time_to_1r,
            outcome.time_to_2r,
            outcome.outcome_label,
            _time(outcome.label_available_at),
            outcome.to_json(),
            payload_hash,
        )
        cursor = self.connection.execute(
            """INSERT OR IGNORE INTO outcomes
               (outcome_id, run_id, observation_id, label_version, horizon_bars,
                forward_return, mfe_r, mae_r, time_to_1r, time_to_2r, outcome_label,
                label_available_at, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            values,
        )
        if cursor.rowcount == 0:
            stored = self.connection.execute(
                "SELECT payload_hash FROM outcomes WHERE outcome_id = ?",
                (outcome.outcome_id,),
            ).fetchone()
            if stored != (payload_hash,):
                raise ValueError(f"conflicting outcome payload: {outcome.outcome_id}")
            return False
        self.connection.commit()
        return True

    def insert_completed_trade(self, trade: CompletedTrade) -> bool:
        payload_hash = canonical_hash(trade)
        values = (
            trade.trade_id,
            trade.run_id,
            trade.symbol,
            trade.timeframe.value,
            trade.direction.value,
            _time(trade.entry_time),
            _time(trade.exit_time),
            _decimal(trade.entry_price),
            _decimal(trade.exit_price),
            _decimal(trade.initial_risk),
            _decimal(trade.gross_r),
            _decimal(trade.net_r),
            _decimal(trade.mfe_r),
            _decimal(trade.mae_r),
            trade.hold_bars,
            canonical_json(trade),
            payload_hash,
        )
        cursor = self.connection.execute(
            """INSERT OR IGNORE INTO completed_trades
               (trade_id, run_id, symbol, timeframe, direction, entry_time, exit_time,
                entry_price, exit_price, initial_risk, gross_r, net_r, mfe_r, mae_r,
                hold_bars, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            values,
        )
        if cursor.rowcount == 0:
            stored = self.connection.execute(
                "SELECT payload_hash FROM completed_trades WHERE trade_id = ?",
                (trade.trade_id,),
            ).fetchone()
            if stored != (payload_hash,):
                raise ValueError(f"conflicting completed trade payload: {trade.trade_id}")
            return False
        self.connection.commit()
        return True

    def trade_results(self, run_id: str) -> tuple[TradeResult, ...]:
        rows = self.connection.execute(
            """SELECT trade_id, net_r, mfe_r, mae_r, hold_bars, gross_r
               FROM completed_trades WHERE run_id = ? ORDER BY exit_time, trade_id""",
            (run_id,),
        ).fetchall()
        return tuple(
            TradeResult(
                str(row[0]),
                Decimal(row[1]),
                Decimal(row[2]),
                Decimal(row[3]),
                int(row[4]),
                Decimal(row[5]),
            )
            for row in rows
        )

    def save_checkpoint(
        self,
        run_id: str,
        last_close_time: datetime,
        processed_candles: int,
        state_hash: str,
    ) -> None:
        if processed_candles < 0:
            raise ValueError("processed_candles cannot be negative")
        self.connection.execute(
            """INSERT INTO replay_checkpoints
               (run_id, last_close_time, processed_candles, state_hash)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(run_id) DO UPDATE SET
                 last_close_time=excluded.last_close_time,
                 processed_candles=excluded.processed_candles,
                 state_hash=excluded.state_hash""",
            (run_id, _time(last_close_time), processed_candles, state_hash),
        )
        self.connection.commit()

    def load_checkpoint(self, run_id: str) -> tuple[datetime, int, str] | None:
        row = self.connection.execute(
            """SELECT last_close_time, processed_candles, state_hash
               FROM replay_checkpoints WHERE run_id = ?""",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        return datetime.fromisoformat(str(row[0]).replace("Z", "+00:00")), int(row[1]), str(row[2])

    def observation_export_rows(self, run_id: str) -> tuple[dict[str, object], ...]:
        rows = self.connection.execute(
            """SELECT f.observation_id, f.run_id, f.candle_id, f.known_at,
                      f.schema_version, f.input_fingerprint, f.features_json,
                      f.data_quality_json, f.payload_hash, r.config_hash,
                      r.code_version, r.data_revision, r.calendar_version
               FROM feature_snapshots f JOIN runs r ON r.run_id = f.run_id
               WHERE f.run_id = ? ORDER BY f.known_at, f.observation_id""",
            (run_id,),
        ).fetchall()
        columns = (
            "observation_id",
            "run_id",
            "candle_id",
            "known_at",
            "schema_version",
            "input_fingerprint",
            "features_json",
            "data_quality_json",
            "payload_hash",
            "config_hash",
            "code_version",
            "data_revision",
            "calendar_version",
        )
        return tuple(dict(zip(columns, row, strict=True)) for row in rows)

    def decision_payload(self, decision_id: str) -> str | None:
        row = self.connection.execute(
            "SELECT payload_json FROM decisions WHERE decision_id = ?",
            (decision_id,),
        ).fetchone()
        return None if row is None else str(row[0])

    def load_decision_plan(
        self, decision_id: str
    ) -> tuple[TradePlan, datetime, DecisionAction, str]:
        row = self.connection.execute(
            """SELECT run_id, known_at, action, payload_json
               FROM decisions WHERE decision_id = ?""",
            (decision_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown decision: {decision_id}")
        action = DecisionAction(str(row[2]))
        if action not in (DecisionAction.LONG, DecisionAction.SHORT):
            raise ValueError("paper intents require a directional Phase 1 decision")
        payload = json.loads(str(row[3]))
        plan_payload = payload.get("entry_plan") if isinstance(payload, dict) else None
        if not isinstance(plan_payload, dict):
            raise ValueError("directional decision has no immutable trade plan")

        def tagged(value: object, tag: str) -> str:
            if not isinstance(value, dict) or set(value) != {tag}:
                raise ValueError(f"stored decision has invalid {tag} value")
            result = value[tag]
            if not isinstance(result, str):
                raise ValueError(f"stored decision has invalid {tag} value")
            return result

        plan = TradePlan(
            str(plan_payload["plan_id"]), str(plan_payload["symbol"]),
            Timeframe(str(plan_payload["timeframe"])),
            Direction(str(plan_payload["direction"])),
            datetime.fromisoformat(
                tagged(plan_payload["created_at"], "__datetime__").replace("Z", "+00:00")
            ).astimezone(UTC),
            Decimal(tagged(plan_payload["planned_entry"], "__decimal__")),
            Decimal(tagged(plan_payload["initial_stop"], "__decimal__")),
            Decimal(tagged(plan_payload["risk_per_unit"], "__decimal__")),
            None if plan_payload["runway_adr"] is None else Decimal(
                tagged(plan_payload["runway_adr"], "__decimal__")
            ),
            None if plan_payload["reward_risk"] is None else Decimal(
                tagged(plan_payload["reward_risk"], "__decimal__")
            ),
            str(plan_payload["pattern_instance_id"]),
        )
        expected_direction = (
            Direction.LONG if action is DecisionAction.LONG else Direction.SHORT
        )
        if plan.direction is not expected_direction:
            raise ValueError("decision action and trade-plan direction disagree")
        known_at = datetime.fromisoformat(str(row[1]).replace("Z", "+00:00")).astimezone(UTC)
        return plan, known_at, action, str(row[0])

    def run_counts(self, run_id: str) -> dict[str, int]:
        result: dict[str, int] = {}
        tables = (
            "candles",
            "feature_snapshots",
            "pattern_events",
            "decisions",
            "trade_events",
            "outcomes",
            "completed_trades",
        )
        for table in tables:
            column = "run_id" if table != "candles" else None
            if column is None:
                row = self.connection.execute("SELECT COUNT(*) FROM candles").fetchone()
            else:
                row = self.connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE run_id = ?",
                    (run_id,),
                ).fetchone()
            assert row is not None
            result[table] = int(row[0])
        return result

    def counts(self) -> tuple[int, int, int]:
        counts: list[int] = []
        for table in ("runs", "candles", "feature_snapshots"):
            row = self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            assert row is not None
            counts.append(int(row[0]))
        return counts[0], counts[1], counts[2]
