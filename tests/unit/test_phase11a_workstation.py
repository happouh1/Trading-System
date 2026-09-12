from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import pytest

from trading_system.desktop.workstation import (
    WorkstationBar,
    WorkstationChart,
    WorkstationConfig,
    WorkstationConfigError,
    WorkstationSnapshot,
    load_workstation_config,
    render_workstation,
)
from trading_system.serialization import canonical_hash

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config/desktop.phase11a.v1.yaml"


def _config(output: str = "workstation.html") -> WorkstationConfig:
    loaded = load_workstation_config(CONFIG)
    values = dict(loaded.values)
    values["output"] = output
    return WorkstationConfig(MappingProxyType(values), loaded.config_hash)


def _snapshot() -> WorkstationSnapshot:
    bars = (
        WorkstationBar(
            "candle-1",
            "AAPL",
            "1H",
            "2026-09-14T14:30:00+00:00",
            Decimal("100"),
            Decimal("102"),
            Decimal("99"),
            Decimal("101"),
        ),
        WorkstationBar(
            "candle-2",
            "AAPL",
            "1H",
            "2026-09-14T15:30:00+00:00",
            Decimal("101"),
            Decimal("103"),
            Decimal("100"),
            Decimal("102"),
        ),
    )
    charts = tuple(
        sorted(
            (
                WorkstationChart("AAPL", "1H", bars),
                WorkstationChart("AAPL", "4H", ()),
                WorkstationChart("AAPL", "1D", ()),
                WorkstationChart("AAPL", "1W", ()),
            ),
            key=lambda item: (item.symbol, item.timeframe),
        )
    )
    identity = ("fixture", tuple(item.timeframe for item in charts))
    return WorkstationSnapshot(
        "workstation_snapshot_fixture",
        datetime(2026, 9, 14, 15, 30, tzinfo=UTC),
        "READY_FOR_PROSPECTIVE_SANDBOX_BURN_IN",
        "READY",
        "AVAILABLE",
        "SHADOW",
        "HEALTHY",
        "sandbox-001",
        0,
        0,
        "IN_PROGRESS",
        "plan-001",
        "2026-09-14T13:30:00+00:00",
        "2026-10-09T20:00:00+00:00",
        1,
        10,
        1,
        20,
        1,
        10,
        Decimal("0"),
        Decimal("0.10"),
        ("WINDOW_OPEN",),
        charts,
        canonical_hash(identity),
    )


def test_workstation_render_is_deterministic_and_read_only(tmp_path: Path) -> None:
    config = _config()
    snapshot = _snapshot()
    first = render_workstation(config, snapshot, project_root=tmp_path)
    content = Path(first.output_path).read_bytes()
    second = render_workstation(config, snapshot, project_root=tmp_path)
    assert first == second
    assert Path(second.output_path).read_bytes() == content
    assert not second.network_used
    assert not second.broker_write_performed
    assert not second.sandbox_execution_enabled
    assert not second.live_trading_enabled


def test_workstation_html_has_mtf_charts_progress_and_no_remote_code(tmp_path: Path) -> None:
    artifact = render_workstation(_config(), _snapshot(), project_root=tmp_path)
    document = Path(artifact.output_path).read_text(encoding="utf-8")
    assert "Multi-Timeframe Research Workstation" in document
    assert "Prospective sandbox burn-in" in document
    assert "1 / 10" in document
    assert "Weekly" in document and "Daily" in document and "4 Hour" in document
    assert "Completed candle chart" in document
    assert "Broker writes by UI" in document
    assert "<script" not in document
    assert "http://" not in document
    assert "https://" not in document
    assert "WEBULL_APP_SECRET" not in document


def test_workstation_configuration_rejects_authority_and_path_escape(tmp_path: Path) -> None:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["broker_writes_enabled"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(WorkstationConfigError, match="authority"):
        load_workstation_config(invalid)
    raw["authority"]["broker_writes_enabled"] = False
    raw["output"] = "../escape.html"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(WorkstationConfigError, match="paths"):
        load_workstation_config(invalid)


def test_workstation_snapshot_rejects_added_authority() -> None:
    with pytest.raises(ValueError, match="workstation snapshot"):
        replace(_snapshot(), network_used=True)


def test_workstation_chart_rejects_invalid_candle() -> None:
    with pytest.raises(ValueError, match="workstation bar"):
        WorkstationBar(
            "bad",
            "AAPL",
            "1H",
            "2026-09-14T14:30:00+00:00",
            Decimal("100"),
            Decimal("99"),
            Decimal("98"),
            Decimal("101"),
        )
