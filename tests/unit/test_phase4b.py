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
    OptionChainSnapshot,
    OptionHorizon,
    OptionQuote,
    OptionRight,
    OptionsConfigError,
    OptionScreenRequest,
    OptionSeries,
    OptionsScreenEngine,
    ScreeningAction,
    SettlementType,
    load_options_config,
)

D = Decimal
ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "options.phase4b.v1.yaml"
NOW = datetime(2026, 8, 28, 15, 0, tzinfo=UTC)
DEFAULT_MAXIMUM_DEBIT = D("1000")


def quote(**changes: object) -> OptionQuote:
    values: dict[str, object] = {
        "observed_at": NOW,
        "bid": D("4.80"),
        "ask": D("5.00"),
        "last": D("4.90"),
        "volume": 100,
        "open_interest": 1000,
        "implied_volatility": D("0.30"),
        "delta": D("0.65"),
        "gamma": D("0.02"),
        "theta": D("-0.04"),
        "vega": D("0.10"),
    }
    values.update(changes)
    return OptionQuote(**values)  # type: ignore[arg-type]


def series(
    contract_id: str = "AAPL-CALL-45",
    *,
    dte: int = 45,
    right: OptionRight = OptionRight.CALL,
    option_quote: OptionQuote | None = None,
    **changes: object,
) -> OptionSeries:
    values: dict[str, object] = {
        "contract_id": contract_id,
        "occ_symbol": contract_id,
        "underlying": "AAPL",
        "expiration": (NOW + timedelta(days=dte)).date(),
        "strike": D("100"),
        "right": right,
        "multiplier": D("100"),
        "exercise_style": ExerciseStyle.AMERICAN,
        "settlement_type": SettlementType.PHYSICAL,
        "standard_contract": True,
        "quote": option_quote or quote(delta=D("-0.65") if right is OptionRight.PUT else D("0.65")),
    }
    values.update(changes)
    return OptionSeries(**values)  # type: ignore[arg-type]


def chain(*contracts: OptionSeries) -> OptionChainSnapshot:
    ordered = tuple(
        sorted(
            contracts or (series(),),
            key=lambda item: (
                item.expiration,
                item.right.value,
                item.strike,
                item.contract_id,
            ),
        )
    )
    return OptionChainSnapshot.create(
        underlying="AAPL",
        as_of=NOW,
        underlying_price=D("100"),
        contracts=ordered,
        source="fixture",
        source_revision="sha256:chain-v1",
    )


def request(
    *,
    direction: Direction = Direction.LONG,
    horizon: OptionHorizon = OptionHorizon.FORTY_FIVE_DTE,
    maximum_debit: Decimal = DEFAULT_MAXIMUM_DEBIT,
) -> OptionScreenRequest:
    return OptionScreenRequest.create(
        upstream_candidate_id="candidate-1",
        underlying="AAPL",
        direction=direction,
        as_of=NOW,
        horizon=horizon,
        maximum_debit=maximum_debit,
    )


def test_config_is_strict_and_authority_cannot_expand(tmp_path: Path) -> None:
    config = load_options_config(CONFIG)
    assert config.config_hash.startswith("sha256:")
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["options_execution_enabled"] = True
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(OptionsConfigError, match="research-only"):
        load_options_config(path)


def test_snapshot_rejects_future_quote_and_noncanonical_order() -> None:
    future = series(option_quote=quote(observed_at=NOW + timedelta(seconds=1)))
    with pytest.raises(ValueError, match="known after"):
        chain(future)
    first = series("B", dte=46)
    second = series("A", dte=45)
    with pytest.raises(ValueError, match="canonically ordered"):
        OptionChainSnapshot(
            "snapshot",
            "AAPL",
            NOW,
            D("100"),
            (first, second),
            "fixture",
            "revision",
        )


def test_45_dte_selects_closest_target_then_delta() -> None:
    engine = OptionsScreenEngine(load_options_config(CONFIG))
    contracts = (
        series("AAPL-CALL-44", dte=44),
        series("AAPL-CALL-45-B", dte=45, option_quote=quote(delta=D("0.66"))),
        series("AAPL-CALL-45-A", dte=45, option_quote=quote(delta=D("0.65"))),
    )
    result = engine.screen(request(), chain(*contracts))
    assert result.action is ScreeningAction.ELIGIBLE
    assert result.selected_contract_id == "AAPL-CALL-45-A"
    assert result.eligible_contract_ids[0] == "AAPL-CALL-45-A"
    assert result.rejection_reasons == ()


def test_short_request_selects_negative_delta_put() -> None:
    result = OptionsScreenEngine(load_options_config(CONFIG)).screen(
        request(direction=Direction.SHORT),
        chain(series("AAPL-PUT-45", right=OptionRight.PUT)),
    )
    assert result.selected_contract_id == "AAPL-PUT-45"


def test_leaps_window_and_target_are_separate() -> None:
    result = OptionsScreenEngine(load_options_config(CONFIG)).screen(
        request(horizon=OptionHorizon.LEAPS, maximum_debit=D("2000")),
        chain(
            series(
                "LEAPS-730",
                dte=730,
                option_quote=quote(bid=D("9.80"), ask=D("10"), delta=D("0.80")),
            ),
            series(
                "LEAPS-600",
                dte=600,
                option_quote=quote(bid=D("9.80"), ask=D("10"), delta=D("0.80")),
            ),
        ),
    )
    assert result.selected_contract_id == "LEAPS-730"


@pytest.mark.parametrize(
    ("item", "maximum_debit", "reason"),
    (
        (series(standard_contract=False), D("1000"), "OPTION_NONSTANDARD_CONTRACT"),
        (series(multiplier=D("10")), D("1000"), "OPTION_MULTIPLIER_MISMATCH"),
        (
            series(exercise_style=ExerciseStyle.EUROPEAN),
            D("1000"),
            "OPTION_EXERCISE_STYLE_UNSUPPORTED",
        ),
        (series(settlement_type=SettlementType.CASH), D("1000"), "OPTION_SETTLEMENT_UNSUPPORTED"),
        (series(dte=20), D("1000"), "OPTION_DTE_OUTSIDE_WINDOW"),
        (
            series(option_quote=quote(observed_at=NOW - timedelta(seconds=901))),
            D("1000"),
            "OPTION_QUOTE_STALE",
        ),
        (
            series(option_quote=quote(bid=D("0.01"), ask=D("0.02"))),
            D("1000"),
            "OPTION_BID_BELOW_MINIMUM",
        ),
        (series(option_quote=quote(volume=9)), D("1000"), "OPTION_VOLUME_BELOW_MINIMUM"),
        (
            series(option_quote=quote(open_interest=99)),
            D("1000"),
            "OPTION_OPEN_INTEREST_BELOW_MINIMUM",
        ),
        (
            series(option_quote=quote(bid=D("4"), ask=D("5"))),
            D("1000"),
            "OPTION_ABSOLUTE_SPREAD_EXCEEDED",
        ),
        (
            series(option_quote=quote(bid=D("0.10"), ask=D("0.12"))),
            D("1000"),
            "OPTION_RELATIVE_SPREAD_EXCEEDED",
        ),
        (series(option_quote=quote(implied_volatility=None)), D("1000"), "OPTION_IV_UNAVAILABLE"),
        (series(option_quote=quote(delta=None)), D("1000"), "OPTION_DELTA_UNAVAILABLE"),
        (series(option_quote=quote(delta=D("0.40"))), D("1000"), "OPTION_DELTA_OUTSIDE_WINDOW"),
        (series(option_quote=quote(delta=D("-0.65"))), D("1000"), "OPTION_DELTA_SIGN_MISMATCH"),
        (series(), D("499"), "OPTION_MAXIMUM_DEBIT_EXCEEDED"),
    ),
)
def test_each_screening_gate_has_an_explicit_reason(
    item: OptionSeries, maximum_debit: Decimal, reason: str
) -> None:
    result = OptionsScreenEngine(load_options_config(CONFIG)).screen(
        request(maximum_debit=maximum_debit), chain(item)
    )
    assert result.action is ScreeningAction.REJECT
    assert reason in result.rejection_reasons


def test_result_identity_and_output_are_deterministic() -> None:
    engine = OptionsScreenEngine(load_options_config(CONFIG))
    first = engine.screen(request(), chain(series()))
    second = engine.screen(request(), chain(series()))
    assert first == second
    assert first.to_json() == second.to_json()


def test_request_and_snapshot_must_share_underlying_and_asof() -> None:
    engine = OptionsScreenEngine(load_options_config(CONFIG))
    with pytest.raises(ValueError, match="underlying"):
        engine.screen(replace(request(), underlying="MSFT"), chain(series()))
    with pytest.raises(ValueError, match="as-of"):
        engine.screen(replace(request(), as_of=NOW - timedelta(seconds=1)), chain(series()))
