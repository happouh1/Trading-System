from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from pytest import CaptureFixture
from tests.unit.test_phase4c import (
    CONFIG,
    ENTRY_TIME,
    EXIT_TIME,
    SCREEN_TIME,
    series,
    validation_case,
)

from trading_system.cli.main import main
from trading_system.domain import Direction
from trading_system.options import (
    OptionChainSnapshot,
    OptionHorizon,
    OptionScreenRequest,
    OptionScreenResult,
    OptionsRegistry,
    OptionsScreenEngine,
    OptionsValidationEngine,
    load_options_config,
    load_options_validation_config,
)
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
SCREEN_CONFIG = ROOT / "config" / "options.phase4b.v1.yaml"


def _screen() -> tuple[OptionChainSnapshot, OptionScreenResult]:
    contract = series(SCREEN_TIME)
    snapshot = OptionChainSnapshot.create(
        underlying="AAPL",
        as_of=SCREEN_TIME,
        underlying_price=contract.strike,
        contracts=(contract,),
        source="fixture",
        source_revision="sha256:screen-chain",
    )
    request = OptionScreenRequest.create(
        upstream_candidate_id="candidate-phase4c",
        underlying="AAPL",
        direction=Direction.LONG,
        as_of=SCREEN_TIME,
        horizon=OptionHorizon.FORTY_FIVE_DTE,
        maximum_debit=contract.quote.ask * contract.multiplier,
    )
    result = OptionsScreenEngine(load_options_config(SCREEN_CONFIG)).screen(request, snapshot)
    return snapshot, result


def test_validation_registry_is_append_only_and_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "options-validation.sqlite"
    snapshot, screen_result = _screen()
    case = validation_case(screen_result_id=screen_result.result_id)
    engine = OptionsValidationEngine(load_options_validation_config(CONFIG))
    result = engine.evaluate(case)
    report = engine.report((result,), source_revision="sha256:batch")
    with SQLiteRepository(database) as repository:
        repository.migrate()
        registry = OptionsRegistry(repository)
        registry.insert_snapshot(snapshot)
        registry.insert_result(screen_result)
        assert registry.insert_validation_case(case)
        assert not registry.insert_validation_case(case)
        assert registry.insert_validation_result(result)
        assert not registry.insert_validation_result(result)
        assert registry.insert_backtest_report(report)
        assert not registry.insert_backtest_report(report)
    with SQLiteRepository(database) as repository:
        repository.migrate()
        assert OptionsRegistry(repository).validation_result_payloads() == (result.to_json(),)


def test_validation_registry_rejects_conflicting_payload(tmp_path: Path) -> None:
    database = tmp_path / "options-validation.sqlite"
    snapshot, screen_result = _screen()
    case = validation_case(screen_result_id=screen_result.result_id)
    with SQLiteRepository(database) as repository:
        repository.migrate()
        registry = OptionsRegistry(repository)
        registry.insert_snapshot(snapshot)
        registry.insert_result(screen_result)
        assert registry.insert_validation_case(case)
        with pytest.raises(ValueError, match="conflicting"):
            registry.insert_validation_case(replace(case, exit_reason="CHANGED"))


def _contract_payload(observed_at: str, bid: str, ask: str) -> dict[str, object]:
    return {
        "contract_id": "AAPL-20261016-100-C",
        "occ_symbol": "AAPL261016C00100000",
        "underlying": "AAPL",
        "expiration": "2026-10-16",
        "strike": "100",
        "right": "CALL",
        "multiplier": "100",
        "exercise_style": "AMERICAN",
        "settlement_type": "PHYSICAL",
        "standard_contract": True,
        "quote": {
            "observed_at": observed_at,
            "bid": bid,
            "ask": ask,
            "last": bid,
            "volume": 100,
            "open_interest": 1000,
            "implied_volatility": "0.30",
            "delta": "0.65",
            "gamma": "0.02",
            "theta": "-0.04",
            "vega": "0.10",
        },
    }


def test_backtest_cli_persists_reproducible_results(
    tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    database = tmp_path / "options-validation.sqlite"
    snapshot, screen_result = _screen()
    with SQLiteRepository(database) as repository:
        repository.migrate()
        registry = OptionsRegistry(repository)
        registry.insert_snapshot(snapshot)
        registry.insert_result(screen_result)
    payload = {
        "source_revision": "sha256:cli-batch-v1",
        "cases": [
            {
                "screen_result_id": screen_result.result_id,
                "screen_known_at": SCREEN_TIME.isoformat(),
                "selected_contract_id": "AAPL-20261016-100-C",
                "horizon": "FORTY_FIVE_DTE",
                "direction": "LONG",
                "quantity": 1,
                "entry": {
                    "snapshot_id": "entry-snapshot",
                    "as_of": ENTRY_TIME.isoformat(),
                    "source": "fixture",
                    "source_revision": "sha256:entry",
                    "contract": _contract_payload(ENTRY_TIME.isoformat(), "4.80", "5.00"),
                },
                "exit": {
                    "snapshot_id": "exit-snapshot",
                    "as_of": EXIT_TIME.isoformat(),
                    "source": "fixture",
                    "source_revision": "sha256:exit",
                    "contract": _contract_payload(EXIT_TIME.isoformat(), "6.00", "6.20"),
                },
                "exit_reason": "EXTERNAL_VALIDATION_HORIZON",
                "source_revision": "sha256:case",
            }
        ],
    }
    source = tmp_path / "backtest.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    assert main(
        [
            "options",
            "backtest",
            "--config",
            str(CONFIG),
            "--input",
            str(source),
            "--database",
            str(database),
        ]
    ) == 0
    output = capsys.readouterr().out
    assert '"status":"COMPLETED"' in output
    assert '"completed_count":1' in output
    assert "order" not in output.lower()


def test_phase4c_migration_copies_are_identical() -> None:
    root_copy = ROOT / "migrations" / "019_phase_4c_option_validation.sql"
    package_copy = (
        ROOT
        / "src"
        / "trading_system"
        / "persistence"
        / "migrations"
        / "019_phase_4c_option_validation.sql"
    )
    assert root_copy.read_bytes() == package_copy.read_bytes()
