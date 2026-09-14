from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import pytest

from tests.unit.test_phase11a_workstation import _snapshot as base_snapshot
from trading_system.desktop.workstation_alerts import (
    AlertWorkstationSnapshot,
    DecisionAlert,
    WorkstationAlertConfig,
    WorkstationAlertConfigError,
    _load_alerts,
    load_alert_config,
    render_alert_workstation,
)
from trading_system.serialization import canonical_hash, canonical_json

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config/desktop.phase11b.v1.yaml"
NOW = datetime(2026, 9, 14, 15, 30, tzinfo=UTC)


def _config(output: str = "workstation.html") -> WorkstationAlertConfig:
    loaded = load_alert_config(CONFIG)
    values = dict(loaded.values)
    values["output"] = output
    return WorkstationAlertConfig(MappingProxyType(values), loaded.config_hash)


def _alert(action: str = "WATCH") -> DecisionAlert:
    directional = action in {"LONG", "SHORT"}
    return DecisionAlert(
        f"alert-{action}",
        f"decision-{action}",
        "run-1",
        f"observation-{action}",
        NOW,
        "AAPL",
        "1h",
        action,
        action if directional else "NONE",
        Decimal("78"),
        Decimal("80"),
        Decimal("74"),
        ("WAIT_FOR_TRIGGER",) if action == "WATCH" else (),
        ("WAIT_FOR_TRIGGER",) if action == "WATCH" else (),
        ("NO_VALID_SETUP",) if action == "NO_TRADE" else (),
        Decimal("101") if directional else None,
        Decimal("99") if directional else None,
        Decimal("2") if directional else None,
        Decimal("1.5") if directional else None,
    )


def _database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE candles(candle_id TEXT PRIMARY KEY,symbol TEXT,timeframe TEXT);
            CREATE TABLE feature_snapshots(observation_id TEXT PRIMARY KEY,candle_id TEXT);
            CREATE TABLE decisions(
              decision_id TEXT PRIMARY KEY,run_id TEXT,observation_id TEXT,known_at TEXT,
              action TEXT,confidence TEXT,setup_quality TEXT,entry_quality TEXT,
              reason_codes_json TEXT,payload_json TEXT,payload_hash TEXT);
            """
        )
        connection.executemany(
            "INSERT INTO candles VALUES(?,?,?)",
            (("c1", "AAPL", "1h"), ("c2", "AAPL", "1h"), ("c3", "MSFT", "1d")),
        )
        connection.executemany(
            "INSERT INTO feature_snapshots VALUES(?,?)",
            (("o1", "c1"), ("o2", "c2"), ("o3", "c3")),
        )
        _insert_decision(connection, "d-old", "o1", "2026-09-14T14:00:00+00:00", "WATCH")
        _insert_decision(connection, "d-new", "o2", "2026-09-14T15:00:00+00:00", "LONG")
        _insert_decision(connection, "d-future", "o3", "2026-09-14T16:00:00+00:00", "NO_TRADE")


def _insert_decision(
    connection: sqlite3.Connection,
    decision_id: str,
    observation_id: str,
    known_at: str,
    action: str,
) -> None:
    directional = action in {"LONG", "SHORT"}
    reasons = ["WAIT_FOR_TRIGGER"] if action == "WATCH" else []
    plan = None
    if directional:
        plan = {
            "__type__": "TradePlan",
            "planned_entry": {"__decimal__": "101"},
            "initial_stop": {"__decimal__": "99"},
            "reward_risk": {"__decimal__": "2"},
            "runway_adr": {"__decimal__": "1.5"},
        }
    payload = {
        "__type__": "Decision",
        "action": action,
        "direction": action if directional else "NONE",
        "entry_plan": plan,
        "missing_conditions": reasons,
        "rejection_reasons": ["NO_VALID_SETUP"] if action == "NO_TRADE" else [],
    }
    connection.execute(
        "INSERT INTO decisions VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            decision_id,
            "run-1",
            observation_id,
            known_at,
            action,
            "78",
            "80",
            "74",
            canonical_json(reasons),
            canonical_json(payload),
            canonical_hash(payload),
        ),
    )


def test_alert_config_rejects_authority_and_path_escape(tmp_path: Path) -> None:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["external_notifications_enabled"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(WorkstationAlertConfigError, match="unsafe"):
        load_alert_config(invalid)
    raw["authority"]["external_notifications_enabled"] = False
    raw["output"] = "../outside.html"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(WorkstationAlertConfigError, match="unsafe"):
        load_alert_config(invalid)


def test_alert_loading_is_causal_latest_per_symbol_timeframe(tmp_path: Path) -> None:
    database = tmp_path / "alerts.sqlite"
    _database(database)
    alerts = _load_alerts(database, as_of=NOW, maximum=40)
    assert [(item.decision_id, item.symbol, item.timeframe) for item in alerts] == [
        ("d-new", "AAPL", "1h")
    ]
    assert alerts[0].action == "LONG"
    assert alerts[0].planned_entry == Decimal("101")


def test_alert_loading_rejects_tampered_payload(tmp_path: Path) -> None:
    database = tmp_path / "alerts.sqlite"
    _database(database)
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE decisions SET payload_json='{}' WHERE decision_id='d-new'")
    with pytest.raises(ValueError, match="integrity"):
        _load_alerts(database, as_of=NOW, maximum=40)


def test_alert_workstation_render_is_deterministic_and_safe(tmp_path: Path) -> None:
    alert = _alert("WATCH")
    snapshot = AlertWorkstationSnapshot(
        "alert-workstation-fixture",
        NOW,
        base_snapshot(),
        (alert,),
        canonical_hash(("phase11b", alert.alert_id)),
    )
    output = (tmp_path / "workstation.html").relative_to(ROOT).as_posix()
    first = render_alert_workstation(_config(output), snapshot, project_root=ROOT)
    document = Path(first.output_path).read_text(encoding="utf-8")
    second = render_alert_workstation(_config(output), snapshot, project_root=ROOT)
    assert first == second
    assert "Decision alerts" in document
    assert "WAIT_FOR_TRIGGER" in document
    assert "Local display only" in document
    assert "<script" not in document
    assert "http://" not in document and "https://" not in document
    assert not first.network_used
    assert not first.external_notification_sent
    assert not first.broker_write_performed


def test_alert_contract_rejects_authority_and_invalid_direction() -> None:
    with pytest.raises(ValueError, match="workstation snapshot"):
        replace(
            AlertWorkstationSnapshot(
                "alert-workstation-fixture",
                NOW,
                base_snapshot(),
                (),
                canonical_hash("phase11b"),
            ),
            external_notification_sent=True,
        )
    with pytest.raises(ValueError, match="direction"):
        replace(_alert("LONG"), direction="SHORT")


def test_missing_database_has_no_alerts(tmp_path: Path) -> None:
    assert _load_alerts(tmp_path / "missing.sqlite", as_of=NOW, maximum=40) == ()
