"""Phase 4B research-only option-chain commands."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from trading_system.domain import Direction
from trading_system.options.config import load_options_config
from trading_system.options.contracts import (
    ExerciseStyle,
    OptionChainSnapshot,
    OptionHorizon,
    OptionQuote,
    OptionRight,
    OptionScreenRequest,
    OptionSeries,
    SettlementType,
)
from trading_system.options.engine import OptionsScreenEngine
from trading_system.options.registry import OptionsRegistry
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_json


def configure_options_parser(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    options = commands.add_parser("options")
    actions = options.add_subparsers(dest="options_command", required=True)
    validate = actions.add_parser("validate-config")
    validate.add_argument("--config", required=True)
    screen = actions.add_parser("screen")
    screen.add_argument("--config", required=True)
    screen.add_argument("--input", required=True)
    screen.add_argument("--database")


def _object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{name} must be an object")
    return value


def _exact_keys(item: dict[str, object], expected: set[str], name: str) -> None:
    if set(item) != expected:
        raise ValueError(f"{name} fields are invalid")


def _time(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an ISO timestamp")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return result


def _date(value: object, name: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an ISO date")
    return date.fromisoformat(value)


def _decimal(value: object, name: str, *, optional: bool = False) -> Decimal | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"{name} must be numeric")
    return Decimal(str(value))


def _integer(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    return value


def _required_decimal(value: object, name: str) -> Decimal:
    result = _decimal(value, name)
    assert result is not None
    return result


def _quote(raw: object) -> OptionQuote:
    item = _object(raw, "quote")
    _exact_keys(
        item,
        {
            "observed_at",
            "bid",
            "ask",
            "last",
            "volume",
            "open_interest",
            "implied_volatility",
            "delta",
            "gamma",
            "theta",
            "vega",
        },
        "quote",
    )
    return OptionQuote(
        _time(item["observed_at"], "quote.observed_at"),
        _required_decimal(item["bid"], "quote.bid"),
        _required_decimal(item["ask"], "quote.ask"),
        _decimal(item.get("last"), "quote.last", optional=True),
        _integer(item["volume"], "quote.volume"),
        _integer(item["open_interest"], "quote.open_interest"),
        _decimal(item.get("implied_volatility"), "quote.implied_volatility", optional=True),
        _decimal(item.get("delta"), "quote.delta", optional=True),
        _decimal(item.get("gamma"), "quote.gamma", optional=True),
        _decimal(item.get("theta"), "quote.theta", optional=True),
        _decimal(item.get("vega"), "quote.vega", optional=True),
    )


def _series(raw: object) -> OptionSeries:
    item = _object(raw, "contract")
    _exact_keys(
        item,
        {
            "contract_id",
            "occ_symbol",
            "underlying",
            "expiration",
            "strike",
            "right",
            "multiplier",
            "exercise_style",
            "settlement_type",
            "standard_contract",
            "quote",
        },
        "contract",
    )
    standard = item["standard_contract"]
    if not isinstance(standard, bool):
        raise ValueError("contract.standard_contract must be boolean")
    return OptionSeries(
        str(item["contract_id"]),
        str(item["occ_symbol"]),
        str(item["underlying"]),
        _date(item["expiration"], "contract.expiration"),
        _required_decimal(item["strike"], "contract.strike"),
        OptionRight(str(item["right"])),
        _required_decimal(item["multiplier"], "contract.multiplier"),
        ExerciseStyle(str(item["exercise_style"])),
        SettlementType(str(item["settlement_type"])),
        standard,
        _quote(item["quote"]),
    )


def _parse_input(path: str) -> tuple[OptionScreenRequest, OptionChainSnapshot]:
    root = _object(json.loads(Path(path).read_text(encoding="utf-8")), "options input")
    if set(root) != {"request", "snapshot"}:
        raise ValueError("options input must contain request and snapshot")
    request_raw = _object(root["request"], "request")
    snapshot_raw = _object(root["snapshot"], "snapshot")
    _exact_keys(
        request_raw,
        {
            "upstream_candidate_id",
            "underlying",
            "direction",
            "as_of",
            "horizon",
            "maximum_debit",
        },
        "request",
    )
    _exact_keys(
        snapshot_raw,
        {
            "underlying",
            "as_of",
            "underlying_price",
            "contracts",
            "source",
            "source_revision",
        },
        "snapshot",
    )
    raw_contracts = snapshot_raw["contracts"]
    if not isinstance(raw_contracts, list):
        raise ValueError("snapshot.contracts must be an array")
    contracts = tuple(_series(item) for item in raw_contracts)
    as_of = _time(snapshot_raw["as_of"], "snapshot.as_of")
    snapshot = OptionChainSnapshot.create(
        underlying=str(snapshot_raw["underlying"]),
        as_of=as_of,
        underlying_price=_required_decimal(
            snapshot_raw["underlying_price"], "snapshot.underlying_price"
        ),
        contracts=contracts,
        source=str(snapshot_raw["source"]),
        source_revision=str(snapshot_raw["source_revision"]),
    )
    request = OptionScreenRequest.create(
        upstream_candidate_id=str(request_raw["upstream_candidate_id"]),
        underlying=str(request_raw["underlying"]),
        direction=Direction(str(request_raw["direction"])),
        as_of=_time(request_raw["as_of"], "request.as_of"),
        horizon=OptionHorizon(str(request_raw["horizon"])),
        maximum_debit=_required_decimal(request_raw["maximum_debit"], "maximum_debit"),
    )
    return request, snapshot


def handle_options(args: argparse.Namespace) -> int:
    config = load_options_config(args.config)
    if args.options_command == "validate-config":
        print(canonical_json({"config_hash": config.config_hash, "valid": True}))
        return 0
    request, snapshot = _parse_input(args.input)
    result = OptionsScreenEngine(config).screen(request, snapshot)
    if args.database:
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            registry = OptionsRegistry(repository)
            registry.insert_snapshot(snapshot)
            registry.insert_result(result)
    print(result.to_json())
    return 0
