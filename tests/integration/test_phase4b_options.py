from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from pytest import CaptureFixture

from trading_system.cli.main import main
from trading_system.domain import Direction
from trading_system.options import (
    ExerciseStyle,
    OptionChainSnapshot,
    OptionHorizon,
    OptionQuote,
    OptionRight,
    OptionScreenRequest,
    OptionSeries,
    OptionsRegistry,
    OptionsScreenEngine,
    SettlementType,
    load_options_config,
)
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "options.phase4b.v1.yaml"
NOW = datetime(2026, 8, 28, 15, 0, tzinfo=UTC)
D = Decimal


def _quote() -> OptionQuote:
    return OptionQuote(
        NOW,
        D("4.80"),
        D("5.00"),
        D("4.90"),
        100,
        1000,
        D("0.30"),
        D("0.65"),
        D("0.02"),
        D("-0.04"),
        D("0.10"),
    )


def _series() -> OptionSeries:
    return OptionSeries(
        "AAPL-CALL-45",
        "AAPL-CALL-45",
        "AAPL",
        (NOW + timedelta(days=45)).date(),
        D("100"),
        OptionRight.CALL,
        D("100"),
        ExerciseStyle.AMERICAN,
        SettlementType.PHYSICAL,
        True,
        _quote(),
    )


def _snapshot() -> OptionChainSnapshot:
    return OptionChainSnapshot.create(
        underlying="AAPL",
        as_of=NOW,
        underlying_price=D("100"),
        contracts=(_series(),),
        source="fixture",
        source_revision="sha256:chain-v1",
    )


def _request() -> OptionScreenRequest:
    return OptionScreenRequest.create(
        upstream_candidate_id="candidate-1",
        underlying="AAPL",
        direction=Direction.LONG,
        as_of=NOW,
        horizon=OptionHorizon.FORTY_FIVE_DTE,
        maximum_debit=D("1000"),
    )


def test_registry_is_append_only_and_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "options.sqlite"
    snapshot = _snapshot()
    result = OptionsScreenEngine(load_options_config(CONFIG)).screen(_request(), snapshot)
    with SQLiteRepository(database) as repository:
        repository.migrate()
        registry = OptionsRegistry(repository)
        assert registry.insert_snapshot(snapshot)
        assert not registry.insert_snapshot(snapshot)
        assert registry.insert_result(result)
        assert not registry.insert_result(result)
        counts = repository.connection.execute(
            """SELECT
               (SELECT COUNT(*) FROM option_chain_snapshots),
               (SELECT COUNT(*) FROM option_series_snapshots),
               (SELECT COUNT(*) FROM option_screen_results)"""
        ).fetchone()
        assert counts == (1, 1, 1)
    with SQLiteRepository(database) as repository:
        repository.migrate()
        assert OptionsRegistry(repository).result_payloads(result.request_id) == (
            result.to_json(),
        )


def test_registry_rejects_conflicting_deterministic_identity(tmp_path: Path) -> None:
    database = tmp_path / "options.sqlite"
    snapshot = _snapshot()
    conflicting = replace(snapshot, underlying_price=D("101"))
    with SQLiteRepository(database) as repository:
        repository.migrate()
        registry = OptionsRegistry(repository)
        assert registry.insert_snapshot(snapshot)
        with pytest.raises(ValueError, match="conflicting"):
            registry.insert_snapshot(conflicting)


def test_cli_screen_is_offline_strict_and_persistent(
    tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    database = tmp_path / "options.sqlite"
    source = tmp_path / "options.json"
    payload = {
        "request": {
            "upstream_candidate_id": "candidate-cli",
            "underlying": "AAPL",
            "direction": "LONG",
            "as_of": "2026-08-28T15:00:00Z",
            "horizon": "FORTY_FIVE_DTE",
            "maximum_debit": "1000",
        },
        "snapshot": {
            "underlying": "AAPL",
            "as_of": "2026-08-28T15:00:00Z",
            "underlying_price": "100",
            "source": "fixture",
            "source_revision": "sha256:cli-chain-v1",
            "contracts": [
                {
                    "contract_id": "AAPL-CALL-45",
                    "occ_symbol": "AAPL-CALL-45",
                    "underlying": "AAPL",
                    "expiration": "2026-10-12",
                    "strike": "100",
                    "right": "CALL",
                    "multiplier": "100",
                    "exercise_style": "AMERICAN",
                    "settlement_type": "PHYSICAL",
                    "standard_contract": True,
                    "quote": {
                        "observed_at": "2026-08-28T15:00:00Z",
                        "bid": "4.80",
                        "ask": "5.00",
                        "last": "4.90",
                        "volume": 100,
                        "open_interest": 1000,
                        "implied_volatility": "0.30",
                        "delta": "0.65",
                        "gamma": "0.02",
                        "theta": "-0.04",
                        "vega": "0.10",
                    },
                }
            ],
        },
    }
    source.write_text(json.dumps(payload), encoding="utf-8")
    assert main(
        [
            "options",
            "screen",
            "--config",
            str(CONFIG),
            "--input",
            str(source),
            "--database",
            str(database),
        ]
    ) == 0
    output = capsys.readouterr().out
    assert '"selected_contract_id":"AAPL-CALL-45"' in output
    assert "order" not in output.lower()
    with SQLiteRepository(database) as repository:
        repository.migrate()
        counts = repository.connection.execute(
            "SELECT COUNT(*), COUNT(selected_contract_id) FROM option_screen_results"
        ).fetchone()
        assert counts == (1, 1)


def test_cli_rejects_unknown_fields(tmp_path: Path) -> None:
    source = tmp_path / "invalid.json"
    source.write_text(
        json.dumps(
            {
                "request": {"unexpected": True},
                "snapshot": {"contracts": []},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="request fields are invalid"):
        main(
            [
                "options",
                "screen",
                "--config",
                str(CONFIG),
                "--input",
                str(source),
            ]
        )


def test_phase4b_migration_copies_are_identical() -> None:
    root_copy = ROOT / "migrations" / "018_phase_4b_options.sql"
    package_copy = (
        ROOT
        / "src"
        / "trading_system"
        / "persistence"
        / "migrations"
        / "018_phase_4b_options.sql"
    )
    assert root_copy.read_bytes() == package_copy.read_bytes()
