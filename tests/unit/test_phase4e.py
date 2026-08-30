from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from tests.integration.test_phase4d_options import _case_payload
from tests.unit.test_phase4c import CONFIG as PHASE4C_CONFIG
from tests.unit.test_phase4c import mark, quote, series, validation_case
from trading_system.cli.main import main
from trading_system.options import (
    OptionCapitalEventType,
    OptionsCapitalConfigError,
    OptionsCapitalEngine,
    OptionsValidationEngine,
    load_options_capital_config,
    load_options_validation_config,
)

D = Decimal
ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "options.phase4e.v1.yaml"


def _engines() -> tuple[OptionsCapitalEngine, OptionsValidationEngine]:
    return (
        OptionsCapitalEngine(load_options_capital_config(CONFIG)),
        OptionsValidationEngine(load_options_validation_config(PHASE4C_CONFIG)),
    )


def test_phase4e_config_locks_authority_and_cli_is_offline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["options", "validate-capital-config", "--config", str(CONFIG)]) == 0
    assert '"valid":true' in capsys.readouterr().out
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["automatic_allocation_enabled"] = True
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(OptionsCapitalConfigError, match="research-only"):
        load_options_capital_config(path)


def test_exact_cash_ledger_accepts_and_closes_case() -> None:
    capital, validation = _engines()
    case = validation_case()
    report, events = capital.evaluate(
        (case,),
        (validation.evaluate(case),),
        starting_cash=D("1000"),
        source_revision="sha256:capital-fixture",
    )
    assert tuple(item.event_type for item in events) == (
        OptionCapitalEventType.ENTRY_ACCEPTED,
        OptionCapitalEventType.EXIT_CREDITED,
    )
    assert events[0].cash_after == D("499")
    assert events[0].deployed_after == D("501")
    assert report.ending_cash == D("1098")
    assert report.realized_net_pnl == D("98")
    assert report.maximum_deployed_cash == D("501")
    assert report.peak_concurrent_positions == 1


def test_simultaneous_unaffordable_batch_is_rejected_without_favoritism() -> None:
    capital, validation = _engines()
    cases = (
        validation_case(revision="sha256:one"),
        validation_case(revision="sha256:two"),
    )
    results = tuple(validation.evaluate(case) for case in cases)
    first = capital.evaluate(
        cases,
        results,
        starting_cash=D("1000"),
        source_revision="sha256:batch",
    )
    second = capital.evaluate(
        tuple(reversed(cases)),
        tuple(reversed(results)),
        starting_cash=D("1000"),
        source_revision="sha256:batch",
    )
    report, events = first
    assert first == second
    assert report.accepted_count == 0
    assert report.rejected_count == 2
    assert report.ending_cash == D("1000")
    assert {item.event_type for item in events} == {OptionCapitalEventType.ENTRY_REJECTED}
    assert all(
        item.reason_codes == ("SIMULTANEOUS_ENTRY_BATCH_EXCEEDS_CASH",) for item in events
    )


def test_same_timestamp_exit_cannot_finance_entry() -> None:
    capital, validation = _engines()
    first = validation_case(revision="sha256:first")
    second_entry_time = first.exit.as_of
    second_exit_time = second_entry_time + timedelta(days=1)
    second = validation_case(
        revision="sha256:second",
        entry=mark("second-entry", second_entry_time),
        exit=mark(
            "second-exit",
            second_exit_time,
            option_series=series(
                second_exit_time,
                option_quote=quote(second_exit_time, bid=D("6.00"), ask=D("6.20")),
            ),
        ),
    )
    cases = (first, second)
    report, events = capital.evaluate(
        cases,
        tuple(validation.evaluate(case) for case in cases),
        starting_cash=D("501"),
        source_revision="sha256:same-time",
    )
    at_boundary = tuple(item for item in events if item.occurred_at == first.exit.as_of)
    assert tuple(item.event_type for item in at_boundary) == (
        OptionCapitalEventType.ENTRY_REJECTED,
        OptionCapitalEventType.EXIT_CREDITED,
    )
    assert report.accepted_count == 1
    assert report.rejected_count == 1


def test_excluded_case_never_consumes_cash() -> None:
    capital, validation = _engines()
    as_of = datetime(2026, 8, 28, 15, tzinfo=UTC)
    stale_entry = mark(
        "stale-entry",
        as_of,
        option_series=series(
            as_of,
            option_quote=quote(datetime(2026, 8, 28, 14, 1, tzinfo=UTC)),
        ),
    )
    case = validation_case(entry=stale_entry, revision="sha256:stale")
    result = validation.evaluate(case)
    report, events = capital.evaluate(
        (case,),
        (result,),
        starting_cash=D("1000"),
        source_revision="sha256:excluded",
    )
    assert report.excluded_count == 1
    assert report.ending_cash == D("1000")
    assert events[0].event_type is OptionCapitalEventType.CASE_EXCLUDED
    assert events[0].cash_change == 0


def test_capital_rejects_mismatched_results_and_invalid_cash() -> None:
    capital, validation = _engines()
    case = validation_case()
    result = validation.evaluate(case)
    with pytest.raises(ValueError, match="positive"):
        capital.evaluate(
            (case,), (result,), starting_cash=D("0"), source_revision="sha256:x"
        )
    with pytest.raises(ValueError, match="match exactly"):
        capital.evaluate(
            (case,), (), starting_cash=D("1000"), source_revision="sha256:x"
        )


def test_capital_feasibility_cli_evaluates_offline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "capital.json"
    source.write_text(
        json.dumps(
            {
                "source_revision": "sha256:cli",
                "starting_cash": "1000",
                "cases": [_case_payload(validation_case())],
            }
        ),
        encoding="utf-8",
    )
    assert (
        main(
            [
                "options",
                "capital-feasibility",
                "--config",
                str(CONFIG),
                "--backtest-config",
                str(PHASE4C_CONFIG),
                "--input",
                str(source),
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    report = output["report"]
    assert report["accepted_count"] == 1
    assert D(report["realized_net_pnl"]["__decimal__"]) == D("98")
