from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from trading_system.cli.main import main
from trading_system.domain import Direction
from trading_system.persistence import SQLiteRepository
from trading_system.portfolio import (
    PortfolioCandidate,
    PortfolioEngine,
    PortfolioRegistry,
    PortfolioState,
    load_portfolio_config,
)

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "portfolio.phase4a.v1.yaml"
NOW = datetime(2026, 8, 28, 14, 0, tzinfo=UTC)
D = Decimal


def test_registry_is_append_only_and_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "portfolio.sqlite"
    config = load_portfolio_config(CONFIG)
    state = PortfolioState("portfolio-1", NOW, D("100000"))
    candidate = PortfolioCandidate(
        "candidate-1",
        "plan-1",
        "AAPL",
        Direction.LONG,
        NOW,
        10,
        D("100"),
        D("98"),
        D("50"),
        D("10000000"),
        "TECHNOLOGY",
        "sha256:point-in-time",
    )
    assessment = PortfolioEngine(config).assess(state, candidate)
    with SQLiteRepository(database) as repository:
        repository.migrate()
        registry = PortfolioRegistry(repository)
        assert registry.insert_state(state, config.config_hash)
        assert not registry.insert_state(state, config.config_hash)
        assert registry.insert_assessment(assessment)
        assert not registry.insert_assessment(assessment)
    with SQLiteRepository(database) as repository:
        repository.migrate()
        assert PortfolioRegistry(repository).assessment_payloads("portfolio-1") == (
            assessment.to_json(),
        )


def test_cli_assessment_persists_without_broker_authority(
    tmp_path: Path, capsys: object
) -> None:
    database = tmp_path / "portfolio.sqlite"
    payload = {
        "state": {
            "portfolio_id": "portfolio-cli",
            "as_of": "2026-08-28T14:00:00Z",
            "equity": "100000",
            "positions": [],
            "pending_symbols": [],
        },
        "candidate": {
            "candidate_id": "candidate-cli",
            "trade_plan_id": "plan-cli",
            "symbol": "AAPL",
            "direction": "LONG",
            "known_at": "2026-08-28T14:00:00Z",
            "planned_hold_sessions": 10,
            "entry_price": "100",
            "stop_price": "98",
            "quantity": "50",
            "average_daily_dollar_volume": "10000000",
            "sector": "TECHNOLOGY",
            "source_revision": "sha256:point-in-time",
        },
    }
    source = tmp_path / "portfolio.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    assert main(
        [
            "portfolio",
            "assess",
            "--config",
            str(CONFIG),
            "--input",
            str(source),
            "--database",
            str(database),
        ]
    ) == 0
    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert '"action":"ACCEPT"' in output
    assert "broker" not in output.lower()
