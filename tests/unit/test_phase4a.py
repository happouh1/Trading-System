from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from trading_system.domain import Direction
from trading_system.portfolio import (
    PortfolioAction,
    PortfolioCandidate,
    PortfolioConfigError,
    PortfolioEngine,
    PortfolioPosition,
    PortfolioState,
    StrategyClass,
    classify_strategy,
    load_portfolio_config,
)

D = Decimal
ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "portfolio.phase4a.v1.yaml"
NOW = datetime(2026, 8, 28, 14, 0, tzinfo=UTC)


def state(*positions: PortfolioPosition, pending: tuple[str, ...] = ()) -> PortfolioState:
    return PortfolioState("portfolio-1", NOW, D("100000"), positions, pending)


def candidate(**changes: object) -> PortfolioCandidate:
    values: dict[str, object] = {
        "candidate_id": "candidate-1",
        "trade_plan_id": "plan-1",
        "symbol": "AAPL",
        "direction": Direction.LONG,
        "known_at": NOW,
        "planned_hold_sessions": 10,
        "entry_price": D("100"),
        "stop_price": D("98"),
        "quantity": D("50"),
        "average_daily_dollar_volume": D("10000000"),
        "sector": "TECHNOLOGY",
        "source_revision": "sha256:point-in-time",
    }
    values.update(changes)
    return PortfolioCandidate(**values)  # type: ignore[arg-type]


def test_config_and_classification_boundaries() -> None:
    config = load_portfolio_config(CONFIG)
    assert classify_strategy(1, config) is StrategyClass.INTRADAY
    assert classify_strategy(2, config) is StrategyClass.SWING
    assert classify_strategy(20, config) is StrategyClass.SWING
    assert classify_strategy(21, config) is StrategyClass.POSITION
    assert classify_strategy(126, config) is StrategyClass.POSITION
    assert classify_strategy(127, config) is StrategyClass.LONG_TERM_RESEARCH
    assert config.config_hash.startswith("sha256:")


def test_config_rejects_authority_expansion(tmp_path: Path) -> None:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["broker_writes_enabled"] = True
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(PortfolioConfigError, match="research-only"):
        load_portfolio_config(path)


def test_candidate_contract_and_derived_risk() -> None:
    item = candidate()
    assert item.notional == D("5000")
    assert item.risk_amount == D("100")
    assert item.volume_participation == D("0.0005")
    with pytest.raises(ValueError, match="stop"):
        replace(item, stop_price=D("101"))


def test_clean_swing_candidate_is_accepted_and_applied() -> None:
    config = load_portfolio_config(CONFIG)
    engine = PortfolioEngine(config)
    starting = state()
    item = candidate()
    result = engine.assess(starting, item)
    assert result.action is PortfolioAction.ACCEPT
    assert result.strategy_class is StrategyClass.SWING
    assert result.reason_codes == ()
    updated = engine.apply(starting, item, result)
    assert len(updated.positions) == 1
    assert updated.positions[0].symbol == "AAPL"


def test_all_portfolio_and_liquidity_reasons_are_stably_sorted() -> None:
    config = load_portfolio_config(CONFIG)
    existing = PortfolioPosition(
        "position-1",
        "AAPL",
        Direction.LONG,
        D("100"),
        D("100"),
        D("98"),
        "TECHNOLOGY",
        StrategyClass.SWING,
    )
    item = candidate(
        entry_price=D("1"),
        stop_price=D("0.5"),
        quantity=D("30000"),
        average_daily_dollar_volume=D("1000"),
    )
    result = PortfolioEngine(config).assess(state(existing), item)
    assert result.action is PortfolioAction.REJECT
    assert result.reason_codes == tuple(sorted(result.reason_codes))
    assert "PORTFOLIO_DUPLICATE_SYMBOL" in result.reason_codes
    assert "LIQUIDITY_PRICE_BELOW_MINIMUM" in result.reason_codes
    assert "LIQUIDITY_DOLLAR_VOLUME_BELOW_MINIMUM" in result.reason_codes
    assert "LIQUIDITY_PARTICIPATION_EXCEEDED" in result.reason_codes


def test_long_term_candidate_is_research_only() -> None:
    result = PortfolioEngine(load_portfolio_config(CONFIG)).assess(
        state(), candidate(planned_hold_sessions=127)
    )
    assert result.action is PortfolioAction.REJECT
    assert "LONG_TERM_FUNDAMENTALS_REQUIRED" in result.reason_codes
    assert "STRATEGY_RISK_BUDGET" in result.reason_codes


@pytest.mark.parametrize(
    ("starting", "item", "expected"),
    (
        (
            state(
                *tuple(
                    PortfolioPosition(
                        f"position-{index}",
                        f"SYM{index}",
                        Direction.LONG,
                        D("1"),
                        D("100"),
                        D("99"),
                        f"SECTOR{index}",
                        StrategyClass.SWING,
                    )
                    for index in range(10)
                )
            ),
            candidate(),
            "PORTFOLIO_MAX_POSITIONS",
        ),
        (
            state(),
            candidate(quantity=D("101")),
            "PORTFOLIO_POSITION_EXPOSURE",
        ),
        (
            state(),
            candidate(quantity=D("501"), stop_price=D("98")),
            "STRATEGY_RISK_BUDGET",
        ),
        (
            state(
                PortfolioPosition(
                    "position-sector",
                    "MSFT",
                    Direction.LONG,
                    D("200"),
                    D("100"),
                    D("98"),
                    "TECHNOLOGY",
                    StrategyClass.SWING,
                )
            ),
            candidate(quantity=D("51")),
            "PORTFOLIO_SECTOR_EXPOSURE",
        ),
        (
            state(
                PortfolioPosition(
                    "position-gross",
                    "MSFT",
                    Direction.LONG,
                    D("950"),
                    D("100"),
                    D("98"),
                    "TECHNOLOGY",
                    StrategyClass.SWING,
                )
            ),
            candidate(quantity=D("60"), sector="CONSUMER"),
            "PORTFOLIO_GROSS_EXPOSURE",
        ),
        (
            state(
                PortfolioPosition(
                    "position-net",
                    "MSFT",
                    Direction.LONG,
                    D("590"),
                    D("100"),
                    D("98"),
                    "TECHNOLOGY",
                    StrategyClass.SWING,
                )
            ),
            candidate(quantity=D("20"), sector="CONSUMER"),
            "PORTFOLIO_NET_EXPOSURE",
        ),
    ),
)
def test_each_portfolio_limit_has_an_explicit_reason(
    starting: PortfolioState,
    item: PortfolioCandidate,
    expected: str,
) -> None:
    result = PortfolioEngine(load_portfolio_config(CONFIG)).assess(starting, item)
    assert result.action is PortfolioAction.REJECT
    assert expected in result.reason_codes


def test_simulation_requires_canonical_order_and_prevents_duplicate_symbol() -> None:
    engine = PortfolioEngine(load_portfolio_config(CONFIG))
    first = candidate(candidate_id="a")
    second = candidate(candidate_id="b")
    final, assessments = engine.simulate(state(), (first, second))
    assert assessments[0].action is PortfolioAction.ACCEPT
    assert assessments[1].action is PortfolioAction.REJECT
    assert len(final.positions) == 1
    with pytest.raises(ValueError, match="ordered"):
        engine.simulate(state(), (second, first))


def test_long_short_exposure_is_mirror_symmetric() -> None:
    engine = PortfolioEngine(load_portfolio_config(CONFIG))
    long_result = engine.assess(state(), candidate())
    short_result = engine.assess(
        state(),
        candidate(direction=Direction.SHORT, stop_price=D("102")),
    )
    assert long_result.proposed_gross_exposure_pct == short_result.proposed_gross_exposure_pct
    assert long_result.proposed_net_exposure_pct == -short_result.proposed_net_exposure_pct
    assert long_result.proposed_risk_pct == short_result.proposed_risk_pct
