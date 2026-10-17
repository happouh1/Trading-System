from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from trading_system.paper.prospective_shadow_research_dashboard import (
    ShadowResearchDashboardConfigError,
    load_shadow_research_dashboard_config,
    render_shadow_research_dashboard,
)

NOW = datetime(2026, 10, 16, 20, tzinfo=UTC)


def _stage_config(root: Path) -> None:
    (root / "stage.json").write_text(
        json.dumps(
            {
                "stage_a_version": "1.0.0",
                "setup": {
                    "minimum_price": "5",
                    "minimum_adr20_pct": "3.5",
                    "minimum_recent_volume_surge": "2",
                    "minimum_off_20d_high_pct": "-3",
                },
                "entry_quality": {
                    "extended_watch_vs_ema8_pct": "6",
                    "maximum_vs_ema8_pct": "8",
                    "gap_chase_warning_pct": "3",
                    "supporting_volume_surge": "2.5",
                    "exceptional_volume_surge": "4",
                },
                "evaluation": {
                    "forward_sessions": 8,
                    "dedupe_scope": "SYMBOL_SESSION",
                    "record_mfe": True,
                    "record_mae": True,
                    "record_time_to_peak": True,
                },
                "authority": {
                    "research_only": True,
                    "decision_authority": False,
                    "broker_writes_enabled": False,
                    "automatic_promotion_enabled": False,
                },
            }
        ),
        encoding="utf-8",
    )


def _short_config(root: Path) -> None:
    (root / "short.json").write_text(
        json.dumps(
            {
                "overlay_version": "12I.1.0",
                "mode": "SHADOW_RESEARCH_ONLY",
                "plan_id": "plan-12j",
                "universe": ["AAPL"],
                "benchmark_symbols": ["AAPL"],
                "signal_timeframes": ["1h"],
                "regime": {
                    "minimum_bearish_benchmarks": 1,
                    "minimum_bearish_breadth": "1",
                },
                "classification": {
                    "armed_min_setup_quality": "40",
                    "armed_min_entry_quality": "50",
                },
                "outcomes": {"horizon_bars": [1]},
                "authority": {
                    "database_read_enabled": True,
                    "database_write_enabled": True,
                    "network_enabled": False,
                    "credential_loading_enabled": False,
                    "shadow_only": True,
                    "broker_writes_enabled": False,
                    "live_trading_enabled": False,
                    "automatic_promotion_enabled": False,
                },
            }
        ),
        encoding="utf-8",
    )


def _dashboard_config(root: Path, *, unsafe: bool = False) -> Path:
    path = root / "dashboard.json"
    path.write_text(
        json.dumps(
            {
                "dashboard_version": "12J.1.0",
                "mode": "READ_ONLY_SHADOW_RESEARCH",
                "database": "research.sqlite",
                "stage_a_config": "stage.json",
                "short_config": "short.json",
                "output": "output/research.html",
                "freshness_minutes": 180,
                "authority": {
                    "database_read_enabled": True,
                    "artifact_write_enabled": True,
                    "network_enabled": False,
                    "credential_loading_enabled": False,
                    "broker_writes_enabled": unsafe,
                    "live_trading_enabled": False,
                    "automatic_promotion_enabled": False,
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _database(root: Path) -> Path:
    path = root / "research.sqlite"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE candles (
              candle_id TEXT PRIMARY KEY,symbol TEXT,timeframe TEXT,open_time TEXT,
              close_time TEXT,session_date TEXT,open TEXT,high TEXT,low TEXT,close TEXT,
              volume TEXT,is_complete INTEGER
            );
            CREATE TABLE short_regime_snapshots (
              snapshot_id TEXT PRIMARY KEY,observed_at TEXT,regime_state TEXT,
              bearish_benchmarks INTEGER,evaluated_benchmarks INTEGER,bearish_breadth TEXT
            );
            CREATE TABLE short_opportunity_alerts (
              alert_id TEXT PRIMARY KEY,symbol TEXT,timeframe TEXT,known_at TEXT,state TEXT,
              setup_quality TEXT,entry_quality TEXT,reason_codes_json TEXT
            );
            CREATE TABLE short_opportunity_outcomes (
              outcome_id TEXT PRIMARY KEY,alert_id TEXT,horizon_bars INTEGER,
              label_available_at TEXT,forward_return TEXT,mfe_return TEXT,mae_return TEXT
            );
            """
        )
        for offset in range(60):
            day = date(2026, 8, 18) + timedelta(days=offset)
            close_at = datetime(day.year, day.month, day.day, 20, tzinfo=UTC)
            price = 100 + offset
            connection.execute(
                "INSERT INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    f"day-{offset}",
                    "AAPL",
                    "1d",
                    (close_at - timedelta(hours=7))
                    .isoformat(timespec="microseconds")
                    .replace("+00:00", "Z"),
                    close_at.isoformat(timespec="microseconds").replace("+00:00", "Z"),
                    day.isoformat(),
                    str(price - 1),
                    str(price + 3),
                    str(price - 3),
                    str(price),
                    "5000" if offset == 59 else "1000",
                    1,
                ),
            )
        connection.execute(
            "INSERT INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "hour-1",
                "AAPL",
                "1h",
                "2026-10-16T18:00:00Z",
                "2026-10-16T19:00:00Z",
                "2026-10-16",
                "158",
                "160",
                "157",
                "159",
                "1000",
                1,
            ),
        )
        connection.execute(
            "INSERT INTO short_regime_snapshots VALUES (?,?,?,?,?,?)",
            ("regime", "2026-10-16T19:00:00Z", "BEARISH_CONFIRMED", 1, 1, "1"),
        )
        connection.execute(
            "INSERT INTO short_opportunity_alerts VALUES (?,?,?,?,?,?,?,?)",
            ("alert", "AAPL", "1h", "2026-10-16T19:00:00Z", "TRIGGER", "75", "80", "[]"),
        )
        connection.execute(
            "INSERT INTO short_opportunity_outcomes VALUES (?,?,?,?,?,?,?)",
            ("outcome", "alert", 1, "2026-10-16T19:30:00Z", "0.02", "0.03", "0.01"),
        )
        connection.commit()
    return path


def test_phase12j_rejects_broker_authority(tmp_path: Path) -> None:
    with pytest.raises(ShadowResearchDashboardConfigError, match="invalid or unsafe"):
        load_shadow_research_dashboard_config(_dashboard_config(tmp_path, unsafe=True))


def test_phase12j_renders_read_only_research_evidence(tmp_path: Path) -> None:
    _stage_config(tmp_path)
    _short_config(tmp_path)
    database = _database(tmp_path)
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    config = load_shadow_research_dashboard_config(_dashboard_config(tmp_path))

    artifact, snapshot = render_shadow_research_dashboard(
        config, project_root=tmp_path, as_of=NOW
    )

    assert artifact.status == "GREEN"
    assert snapshot["short_research"]["state_counts"]["TRIGGER"] == 1  # type: ignore[index]
    assert snapshot["stage_a"][0]["state"] == "QUALIFIED"  # type: ignore[index]
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
    output = Path(artifact.output_path).read_text(encoding="utf-8")
    assert "Shadow Research Dashboard" in output
    assert "Research only" in output
    assert "<script" not in output
    assert "http://" not in output and "https://" not in output
    assert not artifact.database_write_performed
    assert not artifact.network_used
    assert not artifact.broker_write_performed


def test_phase12j_is_deterministic_for_same_evidence(tmp_path: Path) -> None:
    _stage_config(tmp_path)
    _short_config(tmp_path)
    _database(tmp_path)
    config = load_shadow_research_dashboard_config(_dashboard_config(tmp_path))

    first, _ = render_shadow_research_dashboard(config, project_root=tmp_path, as_of=NOW)
    second, _ = render_shadow_research_dashboard(config, project_root=tmp_path, as_of=NOW)

    assert first.snapshot_id == second.snapshot_id
    assert first.content_hash == second.content_hash
