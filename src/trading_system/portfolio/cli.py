"""Phase 4A portfolio research commands."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from trading_system.domain import Direction
from trading_system.persistence import SQLiteRepository
from trading_system.portfolio.config import load_portfolio_config
from trading_system.portfolio.contracts import PortfolioCandidate, PortfolioPosition, PortfolioState
from trading_system.portfolio.engine import PortfolioEngine, classify_strategy
from trading_system.portfolio.registry import PortfolioRegistry
from trading_system.serialization import canonical_json


def configure_portfolio_parser(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    portfolio = commands.add_parser("portfolio")
    actions = portfolio.add_subparsers(dest="portfolio_command", required=True)
    validate = actions.add_parser("validate-config")
    validate.add_argument("--config", required=True)
    classify = actions.add_parser("classify")
    classify.add_argument("--config", required=True)
    classify.add_argument("--planned-hold-sessions", required=True, type=int)
    assess = actions.add_parser("assess")
    assess.add_argument("--config", required=True)
    assess.add_argument("--input", required=True)
    assess.add_argument("--database")


def _time(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an ISO timestamp")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return result


def _decimal(value: object, name: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"{name} must be numeric")
    return Decimal(str(value))


def _integer(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    return value


def _parse_input(path: str, config_path: str) -> tuple[PortfolioState, PortfolioCandidate]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {"state", "candidate"}:
        raise ValueError("portfolio input must contain state and candidate")
    state_raw, candidate_raw = raw["state"], raw["candidate"]
    if not isinstance(state_raw, dict) or not isinstance(candidate_raw, dict):
        raise ValueError("portfolio state and candidate must be objects")
    config = load_portfolio_config(config_path)
    positions: list[PortfolioPosition] = []
    raw_positions = state_raw.get("positions", [])
    if not isinstance(raw_positions, list):
        raise ValueError("state.positions must be an array")
    for item in raw_positions:
        if not isinstance(item, dict):
            raise ValueError("positions must contain objects")
        positions.append(
            PortfolioPosition(
                str(item["position_id"]),
                str(item["symbol"]),
                Direction(str(item["direction"])),
                _decimal(item["quantity"], "quantity"),
                _decimal(item["mark_price"], "mark_price"),
                _decimal(item["stop_price"], "stop_price"),
                str(item["sector"]),
                classify_strategy(
                    _integer(item["planned_hold_sessions"], "planned_hold_sessions"), config
                ),
            )
        )
    pending = state_raw.get("pending_symbols", [])
    if not isinstance(pending, list) or not all(isinstance(item, str) for item in pending):
        raise ValueError("state.pending_symbols must be a string array")
    state = PortfolioState(
        str(state_raw["portfolio_id"]),
        _time(state_raw["as_of"], "state.as_of"),
        _decimal(state_raw["equity"], "state.equity"),
        tuple(positions),
        tuple(pending),
    )
    candidate = PortfolioCandidate(
        str(candidate_raw["candidate_id"]),
        str(candidate_raw["trade_plan_id"]),
        str(candidate_raw["symbol"]),
        Direction(str(candidate_raw["direction"])),
        _time(candidate_raw["known_at"], "candidate.known_at"),
        _integer(candidate_raw["planned_hold_sessions"], "candidate.planned_hold_sessions"),
        _decimal(candidate_raw["entry_price"], "candidate.entry_price"),
        _decimal(candidate_raw["stop_price"], "candidate.stop_price"),
        _decimal(candidate_raw["quantity"], "candidate.quantity"),
        _decimal(
            candidate_raw["average_daily_dollar_volume"],
            "candidate.average_daily_dollar_volume",
        ),
        str(candidate_raw["sector"]),
        str(candidate_raw["source_revision"]),
    )
    return state, candidate


def handle_portfolio(args: argparse.Namespace) -> int:
    config = load_portfolio_config(args.config)
    if args.portfolio_command == "validate-config":
        print(canonical_json({"config_hash": config.config_hash, "valid": True}))
        return 0
    if args.portfolio_command == "classify":
        strategy = classify_strategy(args.planned_hold_sessions, config)
        print(canonical_json({"strategy_class": strategy.value, "config_hash": config.config_hash}))
        return 0
    state, candidate = _parse_input(args.input, args.config)
    assessment = PortfolioEngine(config).assess(state, candidate)
    if args.database:
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            registry = PortfolioRegistry(repository)
            registry.insert_state(state, config.config_hash)
            registry.insert_assessment(assessment)
    print(assessment.to_json())
    return 0
