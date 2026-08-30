from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from trading_system.domain import Direction
from trading_system.options import (
    ExerciseStyle,
    OptionHorizon,
    OptionMark,
    OptionQuote,
    OptionRight,
    OptionSeries,
    OptionsValidationConfigError,
    OptionsValidationEngine,
    OptionValidationCase,
    OptionValidationStatus,
    SettlementType,
    load_options_validation_config,
)

D = Decimal
ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "options.phase4c.v1.yaml"
SCREEN_TIME = datetime(2026, 8, 28, 14, 0, tzinfo=UTC)
ENTRY_TIME = datetime(2026, 8, 28, 15, 0, tzinfo=UTC)
EXIT_TIME = datetime(2026, 9, 1, 15, 0, tzinfo=UTC)
DEFAULT_BID = D("4.80")
DEFAULT_ASK = D("5.00")


def quote(
    observed_at: datetime,
    *,
    bid: Decimal = DEFAULT_BID,
    ask: Decimal = DEFAULT_ASK,
) -> OptionQuote:
    return OptionQuote(
        observed_at,
        bid,
        ask,
        (bid + ask) / 2,
        100,
        1000,
        D("0.30"),
        D("0.65"),
        D("0.02"),
        D("-0.04"),
        D("0.10"),
    )


def series(
    observed_at: datetime,
    *,
    right: OptionRight = OptionRight.CALL,
    option_quote: OptionQuote | None = None,
) -> OptionSeries:
    return OptionSeries(
        "AAPL-20261016-100-C",
        "AAPL261016C00100000",
        "AAPL",
        datetime(2026, 10, 16, tzinfo=UTC).date(),
        D("100"),
        right,
        D("100"),
        ExerciseStyle.AMERICAN,
        SettlementType.PHYSICAL,
        True,
        option_quote or quote(observed_at),
    )


def mark(
    name: str,
    as_of: datetime,
    *,
    option_series: OptionSeries | None = None,
) -> OptionMark:
    return OptionMark(
        f"snapshot-{name}",
        as_of,
        "fixture",
        f"sha256:{name}",
        option_series or series(as_of),
    )


def validation_case(
    *,
    screen_result_id: str = "option-screen-result-1",
    entry: OptionMark | None = None,
    exit: OptionMark | None = None,
    direction: Direction = Direction.LONG,
    quantity: int = 1,
    revision: str = "sha256:case-v1",
) -> OptionValidationCase:
    return OptionValidationCase.create(
        screen_result_id=screen_result_id,
        screen_known_at=SCREEN_TIME,
        selected_contract_id="AAPL-20261016-100-C",
        horizon=OptionHorizon.FORTY_FIVE_DTE,
        direction=direction,
        quantity=quantity,
        entry=entry or mark("entry", ENTRY_TIME),
        exit=exit
        or mark(
            "exit",
            EXIT_TIME,
            option_series=series(
                EXIT_TIME,
                option_quote=quote(EXIT_TIME, bid=D("6.00"), ask=D("6.20")),
            ),
        ),
        exit_reason="EXTERNAL_VALIDATION_HORIZON",
        source_revision=revision,
    )


def test_validation_config_is_strict_and_cannot_expand_authority(tmp_path: Path) -> None:
    config = load_options_validation_config(CONFIG)
    assert config.config_hash.startswith("sha256:")
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["options_execution_enabled"] = True
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(OptionsValidationConfigError, match="research-only"):
        load_options_validation_config(path)


def test_conservative_fill_math_is_exact() -> None:
    engine = OptionsValidationEngine(load_options_validation_config(CONFIG))
    result = engine.evaluate(validation_case(quantity=2))
    assert result.status is OptionValidationStatus.COMPLETED
    assert result.entry_fill == D("5.01")
    assert result.exit_fill == D("5.99")
    assert result.entry_debit == D("1002")
    assert result.gross_pnl == D("196")
    assert result.fees == D("0")
    assert result.net_pnl == D("196")
    assert result.return_on_debit == D("196") / D("1002")
    assert result.holding_seconds == 345600


def test_zero_bid_exit_caps_long_premium_loss_at_debit() -> None:
    exit_mark = mark(
        "exit-zero",
        EXIT_TIME,
        option_series=series(
            EXIT_TIME,
            option_quote=quote(EXIT_TIME, bid=D("0"), ask=D("0.05")),
        ),
    )
    result = OptionsValidationEngine(load_options_validation_config(CONFIG)).evaluate(
        validation_case(exit=exit_mark)
    )
    assert result.exit_fill == D("0")
    assert result.entry_debit is not None
    assert result.net_pnl == -result.entry_debit


def test_stale_quotes_are_excluded_without_manufactured_prices() -> None:
    stale_entry = mark(
        "stale",
        ENTRY_TIME,
        option_series=series(ENTRY_TIME - timedelta(seconds=901)),
    )
    result = OptionsValidationEngine(load_options_validation_config(CONFIG)).evaluate(
        validation_case(entry=stale_entry)
    )
    assert result.status is OptionValidationStatus.EXCLUDED
    assert result.exclusion_reasons == ("OPTION_ENTRY_QUOTE_STALE",)
    assert result.net_pnl is None


@pytest.mark.parametrize(
    ("change", "message"),
    (
        ("ENTRY_NOT_AFTER_SCREEN", "entry mark"),
        ("ENTRY_QUOTE_NOT_AFTER_SCREEN", "entry quote"),
        ("EXIT_NOT_AFTER_ENTRY", "exit mark"),
        ("EXIT_QUOTE_NOT_AFTER_ENTRY", "exit quote"),
        ("EXPIRATION_DAY", "expiration-day"),
        ("METADATA_MISMATCH", "metadata differ"),
    ),
)
def test_case_rejects_lookahead_and_unsupported_lifecycle(
    change: str, message: str
) -> None:
    entry = mark("entry", ENTRY_TIME)
    exit_mark = mark("exit", EXIT_TIME)
    if change == "ENTRY_NOT_AFTER_SCREEN":
        entry = mark("entry", SCREEN_TIME, option_series=series(SCREEN_TIME))
    elif change == "ENTRY_QUOTE_NOT_AFTER_SCREEN":
        entry = mark("entry", ENTRY_TIME, option_series=series(SCREEN_TIME))
    elif change == "EXIT_NOT_AFTER_ENTRY":
        exit_mark = mark("exit", ENTRY_TIME, option_series=series(ENTRY_TIME))
    elif change == "EXIT_QUOTE_NOT_AFTER_ENTRY":
        exit_mark = mark("exit", EXIT_TIME, option_series=series(ENTRY_TIME))
    elif change == "EXPIRATION_DAY":
        expiration = datetime(2026, 10, 16, 15, 0, tzinfo=UTC)
        exit_mark = mark("exit", expiration, option_series=series(expiration))
    else:
        changed = replace(series(EXIT_TIME), strike=D("101"))
        exit_mark = mark("exit", EXIT_TIME, option_series=changed)
    with pytest.raises(ValueError, match=message):
        validation_case(entry=entry, exit=exit_mark)


def test_report_metrics_and_order_are_deterministic() -> None:
    engine = OptionsValidationEngine(load_options_validation_config(CONFIG))
    win = engine.evaluate(validation_case(revision="win"))
    losing_exit = mark(
        "losing-exit",
        EXIT_TIME + timedelta(days=1),
        option_series=series(
            EXIT_TIME + timedelta(days=1),
            option_quote=quote(
                EXIT_TIME + timedelta(days=1), bid=D("3.00"), ask=D("3.20")
            ),
        ),
    )
    loss = engine.evaluate(validation_case(exit=losing_exit, revision="loss"))
    report = engine.report((loss, win), source_revision="sha256:batch-v1")
    assert report.result_ids == (win.result_id, loss.result_id)
    assert report.metrics.completed_count == 2
    assert report.metrics.win_count == 1
    assert report.metrics.loss_count == 1
    assert report.metrics.win_rate == D("0.5")
    assert report.metrics.maximum_drawdown == D("202")
    assert report == engine.report((win, loss), source_revision="sha256:batch-v1")


def test_all_excluded_report_keeps_undefined_rates_null() -> None:
    stale = mark(
        "stale",
        ENTRY_TIME,
        option_series=series(ENTRY_TIME - timedelta(seconds=901)),
    )
    engine = OptionsValidationEngine(load_options_validation_config(CONFIG))
    excluded = engine.evaluate(validation_case(entry=stale))
    report = engine.report((excluded,), source_revision="sha256:excluded")
    assert report.metrics.completed_count == 0
    assert report.metrics.excluded_count == 1
    assert report.metrics.win_rate is None
    assert report.metrics.mean_return_on_debit is None


def test_report_rejects_mixed_configuration_identity() -> None:
    engine = OptionsValidationEngine(load_options_validation_config(CONFIG))
    result = engine.evaluate(validation_case())
    with pytest.raises(ValueError, match="configuration hash"):
        engine.report(
            (replace(result, config_hash="sha256:different"),),
            source_revision="sha256:mixed",
        )
