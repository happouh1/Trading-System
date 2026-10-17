from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from trading_system.domain import (
    Candle,
    Decision,
    DecisionAction,
    Direction,
    Observation,
    Timeframe,
    TradeStyle,
)
from trading_system.paper import (
    PaperMode,
    PaperRegistry,
    PaperRuntime,
    PaperSession,
    RejectingAdapter,
)
from trading_system.persistence import RunRecord, SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json
from trading_system.webull.short_opportunities import (
    BearishRegimeState,
    ShortOpportunityConfigError,
    ShortOpportunityState,
    label_short_opportunity_outcomes,
    load_short_opportunity_config,
    materialize_short_opportunities,
)

D = Decimal
NOW = datetime(2026, 10, 16, 20, tzinfo=UTC)
PLAN = "plan-12i"
RUN = "run-12i"
SESSION = "session-12i"


def _config(tmp_path: Path, *, unsafe: bool = False) -> Path:
    path = tmp_path / "short.json"
    path.write_text(
        json.dumps(
            {
                "overlay_version": "12I.1.0",
                "mode": "SHADOW_RESEARCH_ONLY",
                "plan_id": PLAN,
                "universe": ["SPY"],
                "benchmark_symbols": ["SPY"],
                "signal_timeframes": ["1h", "4h"],
                "regime": {
                    "minimum_bearish_benchmarks": 1,
                    "minimum_bearish_breadth": "1",
                },
                "classification": {
                    "armed_min_setup_quality": "40",
                    "armed_min_entry_quality": "50",
                },
                "outcomes": {"horizon_bars": [1, 3]},
                "authority": {
                    "database_read_enabled": True,
                    "database_write_enabled": True,
                    "network_enabled": False,
                    "credential_loading_enabled": False,
                    "shadow_only": True,
                    "broker_writes_enabled": unsafe,
                    "live_trading_enabled": False,
                    "automatic_promotion_enabled": False,
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _candle(opened: datetime, price: str, revision: str) -> Candle:
    value = D(price)
    return Candle(
        "SPY",
        Timeframe.HOUR_1,
        opened,
        opened + timedelta(hours=1),
        date.fromisoformat(opened.date().isoformat()),
        value,
        value + D("1"),
        value - D("2"),
        value - D("1"),
        D("1000"),
        True,
        D("1"),
        "TEST",
        revision,
        raw_open=value,
        raw_high=value + D("1"),
        raw_low=value - D("2"),
        raw_close=value - D("1"),
        raw_volume=D("1000"),
    )


def _seed(repository: SQLiteRepository) -> None:
    created = NOW - timedelta(days=2)
    paper = PaperRegistry(repository)
    paper.insert_session(
        PaperSession(
            SESSION,
            created,
            PaperMode.SHADOW,
            "0.2.0",
            "sha256:" + "a" * 64,
            "PHASE12I-TEST",
            "exchange-calendars-4",
        )
    )
    PaperRuntime(paper, SESSION, PaperMode.SHADOW, RejectingAdapter()).start(created)
    binding = {"binding_id": "binding-12i", "session_id": SESSION, "plan_id": PLAN}
    repository.connection.execute(
        """INSERT INTO paper_burn_in_session_bindings
           (binding_id,session_id,plan_id,baseline_session_id,runtime_lock_hash,
            started_at,code_version,config_hash,data_revision,calendar_version,
            payload_json,payload_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "binding-12i",
            SESSION,
            PLAN,
            "baseline-12i",
            "sha256:" + "b" * 64,
            created.isoformat().replace("+00:00", "Z"),
            "0.2.0",
            "sha256:" + "a" * 64,
            "PHASE12I-TEST",
            "exchange-calendars-4",
            canonical_json(binding),
            canonical_hash(binding),
        ),
    )
    repository.insert_run(
        RunRecord(
            RUN,
            created,
            "0.2.0",
            "sha256:" + "c" * 64,
            "PHASE12I-TEST",
            "exchange-calendars-4",
            1,
        )
    )
    candle = _candle(NOW - timedelta(hours=1), "100", "source-1")
    repository.insert_candle(candle)
    observation = Observation(
        "observation-12i",
        RUN,
        candle.candle_id,
        NOW,
        "1.0.0",
        "fingerprint-12i",
        {},
        {"complete": True},
    )
    repository.insert_snapshot(observation)
    repository.insert_decision(
        Decision(
            "decision-12i",
            RUN,
            observation.observation_id,
            NOW,
            DecisionAction.NO_TRADE,
            Direction.SHORT,
            D("60"),
            D("70"),
            D("55"),
            TradeStyle.CONTINUATION,
            None,
            rejection_reasons=("LOW_CONFIDENCE",),
            timeframe_states={
                "1w": "DOWNTREND",
                "1d": "DOWNTREND",
                "4h": "DOWNTREND",
                "1h": "DOWNTREND",
            },
        )
    )
    cycle = {"cycle_id": "cycle-12i", "session_id": SESSION, "run_id": RUN}
    repository.connection.execute(
        """INSERT INTO burn_in_shadow_decision_cycles
           (cycle_id,session_id,run_id,observed_at,config_hash,source_1h_candles,
            derived_candles,processed_candles,emitted_decisions,directional_decisions,
            staged_shadow_intents,payload_json,payload_hash)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "cycle-12i",
            SESSION,
            RUN,
            NOW.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            "sha256:" + "d" * 64,
            1,
            0,
            1,
            1,
            0,
            0,
            canonical_json(cycle),
            canonical_hash(cycle),
        ),
    )
    repository.connection.commit()


def test_phase12i_rejects_broker_write_authority(tmp_path: Path) -> None:
    with pytest.raises(ShortOpportunityConfigError, match="invalid or unsafe"):
        load_short_opportunity_config(_config(tmp_path, unsafe=True))


def test_phase12i_materializes_armed_alert_and_forward_outcomes(tmp_path: Path) -> None:
    config = load_short_opportunity_config(_config(tmp_path))
    with SQLiteRepository(tmp_path / "phase12i.sqlite") as repository:
        repository.migrate()
        _seed(repository)
        result = materialize_short_opportunities(
            repository,
            config,
            session_id=SESSION,
            observed_at=NOW,
        )
        assert result.snapshot.regime_state is BearishRegimeState.CONFIRMED
        assert result.armed == 1
        assert result.alerts[0].state is ShortOpportunityState.ARMED
        assert not result.broker_write_performed

        future = _candle(NOW, "99", "source-2")
        repository.insert_candle(future)
        assert label_short_opportunity_outcomes(
            repository,
            config,
            as_of=future.close_time,
        ) == 1
        row = repository.connection.execute(
            """SELECT horizon_bars,entry_price,forward_return,mfe_return,mae_return
               FROM short_opportunity_outcomes"""
        ).fetchone()
        assert row is not None
        assert row[0] == 1
        assert D(row[1]) == D("99")
        assert D(row[2]) == D(1) / D(99)
        assert D(row[3]) == D(2) / D(99)
        assert D(row[4]) == D(1) / D(99)


def test_phase12i_extended_entry_is_never_armed(tmp_path: Path) -> None:
    config = load_short_opportunity_config(_config(tmp_path))
    with SQLiteRepository(tmp_path / "phase12i.sqlite") as repository:
        repository.migrate()
        _seed(repository)
        repository.connection.execute(
            "UPDATE decisions SET reason_codes_json=? WHERE decision_id='decision-12i'",
            (canonical_json(("ENTRY_EXTENDED",)),),
        )
        payload = json.loads(
            repository.connection.execute(
                "SELECT payload_json FROM decisions WHERE decision_id='decision-12i'"
            ).fetchone()[0]
        )
        payload["rejection_reasons"] = ["ENTRY_EXTENDED"]
        repository.connection.execute(
            "UPDATE decisions SET payload_json=? WHERE decision_id='decision-12i'",
            (json.dumps(payload, separators=(",", ":"), sort_keys=True),),
        )
        repository.connection.commit()
        result = materialize_short_opportunities(
            repository,
            config,
            session_id=SESSION,
            observed_at=NOW,
        )
        assert result.too_late == 1
        assert result.armed == 0
