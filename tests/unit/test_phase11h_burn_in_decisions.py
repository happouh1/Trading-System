from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from trading_system.cli.main import main
from trading_system.config import load_config
from trading_system.domain import Candle, Timeframe
from trading_system.market_data import XNYSCalendar
from trading_system.paper import (
    PaperMode,
    PaperRegistry,
    PaperRuntime,
    PaperSession,
    RejectingAdapter,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json
from trading_system.webull import (
    BurnInDecisionWorkerConfigError,
    MarketDataKind,
    ShadowBar,
    WebullRegistry,
    load_burn_in_decision_worker_config,
    run_burn_in_decision_cycle,
)

ROOT = Path(__file__).parents[2]
OBSERVED = datetime(2026, 9, 18, 21, tzinfo=UTC)
PLAN_ID = "plan-11h"


def _config(tmp_path: Path, *, simulated_fills: bool = False) -> Path:
    thresholds = load_config(ROOT / "config/thresholds.phase1e.v1.yaml")
    path = tmp_path / "phase11h.json"
    path.write_text(
        json.dumps(
            {
                "decision_worker_version": "11H.1.0",
                "mode": "LOCAL_CAUSAL_SHADOW_DECISIONS",
                "plan_id": PLAN_ID,
                "strategy_config_hash": thresholds.config_hash,
                "signal_timeframes": ["1h", "4h"],
                "authority": {
                    "database_read_enabled": True,
                    "database_write_enabled": True,
                    "shadow_intent_staging_enabled": True,
                    "network_enabled": False,
                    "credential_loading_enabled": False,
                    "simulated_fills_enabled": simulated_fills,
                    "broker_writes_enabled": False,
                    "sandbox_execution_enabled": False,
                    "live_trading_enabled": False,
                    "automatic_promotion_enabled": False,
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _session(repository: SQLiteRepository) -> None:
    created_at = OBSERVED - timedelta(days=7)
    paper = PaperRegistry(repository)
    paper.insert_session(
        PaperSession(
            "worker-11h",
            created_at,
            PaperMode.SHADOW,
            "0.2.0",
            "sha256:" + "a" * 64,
            "PHASE11H-TEST",
            "exchange-calendars-4",
        )
    )
    PaperRuntime(
        paper,
        "worker-11h",
        PaperMode.SHADOW,
        RejectingAdapter(),
    ).start(created_at)
    binding = {
        "binding_id": "binding-11h",
        "session_id": "worker-11h",
        "plan_id": PLAN_ID,
    }
    repository.connection.execute(
        """INSERT INTO paper_burn_in_session_bindings
           (binding_id,session_id,plan_id,baseline_session_id,runtime_lock_hash,
            started_at,code_version,config_hash,data_revision,calendar_version,
            payload_json,payload_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "binding-11h",
            "worker-11h",
            PLAN_ID,
            "baseline-11h",
            "sha256:" + "b" * 64,
            created_at.isoformat().replace("+00:00", "Z"),
            "0.2.0",
            "sha256:" + "a" * 64,
            "PHASE11H-TEST",
            "exchange-calendars-4",
            canonical_json(binding),
            canonical_hash(binding),
        ),
    )
    worker = {"cycle_id": "worker-cycle-11h", "session_id": "worker-11h"}
    repository.connection.execute(
        """INSERT INTO webull_burn_in_worker_cycles
           (cycle_id,session_id,observed_at,config_hash,history_responses,
            completed_bars_seen,new_bars_persisted,heartbeat_inserted,network_used,
            payload_json,payload_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "worker-cycle-11h",
            "worker-11h",
            OBSERVED.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            "sha256:" + "c" * 64,
            1,
            35,
            35,
            1,
            0,
            canonical_json(worker),
            canonical_hash(worker),
        ),
    )
    repository.connection.commit()


def _bars(repository: SQLiteRepository) -> None:
    calendar = XNYSCalendar()
    registry = WebullRegistry(repository)
    for offset in range(5):
        session_date = datetime(2026, 9, 14, tzinfo=UTC).date() + timedelta(days=offset)
        bounds = calendar.bounds(session_date)
        assert bounds is not None
        opened = bounds[0]
        index = 0
        while opened < bounds[1]:
            closed = min(opened + timedelta(hours=1), bounds[1])
            price = Decimal(100 + offset + index)
            candle = Candle(
                "AAPL",
                Timeframe.HOUR_1,
                opened,
                closed,
                session_date,
                price,
                price + Decimal("1"),
                price - Decimal("1"),
                price + Decimal("0.5"),
                Decimal(1000 + index),
                True,
                Decimal("1"),
                "WEBULL_SANDBOX",
                f"revision-{session_date.isoformat()}-{index}",
                raw_open=price,
                raw_high=price + Decimal("1"),
                raw_low=price - Decimal("1"),
                raw_close=price + Decimal("0.5"),
                raw_volume=Decimal(1000 + index),
            )
            registry.insert_shadow_bar(
                "worker-11h",
                ShadowBar(
                    candle,
                    closed,
                    OBSERVED,
                    OBSERVED,
                    canonical_hash(candle),
                    MarketDataKind.HISTORICAL,
                ),
            )
            opened = closed
            index += 1


def test_phase11h_config_is_strict_and_checked_in_hash_matches() -> None:
    config = load_burn_in_decision_worker_config(
        ROOT / "config/webull.phase11h.offline.v1.yaml"
    )
    thresholds = load_config(ROOT / "config/thresholds.phase1e.v1.yaml")
    assert config.strategy_config_hash == thresholds.config_hash
    assert config.signal_timeframes == (Timeframe.HOUR_1, Timeframe.HOUR_4)


def test_phase11h_verify_cli_discloses_disabled_authority(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(
        [
            "webull",
            "verify-burn-in-decisions",
            "--config",
            str(ROOT / "config/webull.sandbox.v1.yaml"),
            "--decision-config",
            str(ROOT / "config/webull.phase11h.offline.v1.yaml"),
            "--thresholds",
            str(ROOT / "config/thresholds.phase1e.v1.yaml"),
        ]
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["network_used"] is False
    assert payload["credentials_loaded"] is False
    assert payload["simulated_fills_enabled"] is False
    assert payload["broker_write_performed"] is False


def test_phase11h_rejects_simulated_fill_authority(tmp_path: Path) -> None:
    with pytest.raises(BurnInDecisionWorkerConfigError, match="invalid or unsafe"):
        load_burn_in_decision_worker_config(_config(tmp_path, simulated_fills=True))

    raw = json.loads(_config(tmp_path).read_text(encoding="utf-8"))
    raw["authority"]["network_enabled"] = 0
    (tmp_path / "phase11h.json").write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(BurnInDecisionWorkerConfigError, match="invalid or unsafe"):
        load_burn_in_decision_worker_config(tmp_path / "phase11h.json")


def test_phase11h_persists_causal_decisions_and_restart_deduplicates(
    tmp_path: Path,
) -> None:
    config = load_burn_in_decision_worker_config(_config(tmp_path))
    thresholds = load_config(ROOT / "config/thresholds.phase1e.v1.yaml")
    with SQLiteRepository(tmp_path / "phase11h.sqlite") as repository:
        repository.migrate()
        _session(repository)
        _bars(repository)
        first = run_burn_in_decision_cycle(
            repository,
            config,
            thresholds,
            session_id="worker-11h",
            observed_at=OBSERVED,
        )
        second = run_burn_in_decision_cycle(
            repository,
            config,
            thresholds,
            session_id="worker-11h",
            observed_at=OBSERVED + timedelta(minutes=5),
        )
        assert first.source_1h_candles == 35
        assert first.derived_candles == 16
        assert first.processed_candles == 51
        assert first.emitted_decisions == 51
        assert not first.network_used
        assert not first.simulated_fills_enabled
        assert not first.broker_write_performed
        assert second.processed_candles == 0
        assert second.emitted_decisions == 0
        assert repository.connection.execute(
            "SELECT COUNT(*) FROM burn_in_shadow_decision_cycles"
        ).fetchone() == (2,)
        assert repository.connection.execute(
            "SELECT COUNT(*) FROM feature_snapshots WHERE run_id=?", (first.run_id,)
        ).fetchone() == (51,)
        assert repository.connection.execute(
            "SELECT COUNT(*) FROM decisions WHERE run_id=?", (first.run_id,)
        ).fetchone() == (51,)
        assert repository.connection.execute(
            "SELECT COUNT(*) FROM completed_trades"
        ).fetchone() == (0,)
        assert repository.connection.execute(
            "SELECT COUNT(*) FROM paper_adapter_events"
        ).fetchone() == (0,)


def test_phase11h_requires_a_successful_phase11g_cycle(tmp_path: Path) -> None:
    config = load_burn_in_decision_worker_config(_config(tmp_path))
    thresholds = load_config(ROOT / "config/thresholds.phase1e.v1.yaml")
    with SQLiteRepository(tmp_path / "phase11h.sqlite") as repository:
        repository.migrate()
        _session(repository)
        _bars(repository)
        repository.connection.execute("DELETE FROM webull_burn_in_worker_cycles")
        repository.connection.commit()
        with pytest.raises(ValueError, match="Phase 11G worker cycle"):
            run_burn_in_decision_cycle(
                repository,
                config,
                thresholds,
                session_id="worker-11h",
                observed_at=OBSERVED,
            )


def test_phase11h_rejects_conflicting_source_revision(tmp_path: Path) -> None:
    config = load_burn_in_decision_worker_config(_config(tmp_path))
    thresholds = load_config(ROOT / "config/thresholds.phase1e.v1.yaml")
    with SQLiteRepository(tmp_path / "phase11h.sqlite") as repository:
        repository.migrate()
        _session(repository)
        _bars(repository)
        first = repository.connection.execute(
            "SELECT candle_id FROM webull_shadow_bars LIMIT 1"
        ).fetchone()
        assert first is not None
        row = repository.connection.execute(
            """SELECT symbol,timeframe,open_time,close_time,session_date,open,high,low,
                      close,volume,adjustment_factor,source,raw_open,raw_high,raw_low,
                      raw_close,raw_volume FROM candles WHERE candle_id=?""",
            (first[0],),
        ).fetchone()
        assert row is not None
        duplicate = Candle(
            str(row[0]), Timeframe(str(row[1])),
            datetime.fromisoformat(str(row[2]).replace("Z", "+00:00")),
            datetime.fromisoformat(str(row[3]).replace("Z", "+00:00")),
            datetime.fromisoformat(str(row[4])).date(),
            Decimal(str(row[5])), Decimal(str(row[6])), Decimal(str(row[7])),
            Decimal(str(row[8])), Decimal(str(row[9])), True,
            Decimal(str(row[10])), str(row[11]), "conflicting-revision",
            raw_open=Decimal(str(row[12])), raw_high=Decimal(str(row[13])),
            raw_low=Decimal(str(row[14])), raw_close=Decimal(str(row[15])),
            raw_volume=Decimal(str(row[16])),
        )
        WebullRegistry(repository).insert_shadow_bar(
            "worker-11h",
            ShadowBar(duplicate, duplicate.close_time, OBSERVED, OBSERVED,
                      canonical_hash(duplicate), MarketDataKind.HISTORICAL),
        )
        with pytest.raises(ValueError, match="conflicting persisted source-bar revisions"):
            run_burn_in_decision_cycle(
                repository, config, thresholds,
                session_id="worker-11h", observed_at=OBSERVED,
            )
