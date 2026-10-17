"""Command-line boundary for research-only Stage A assessment."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from trading_system.research.trend_stage_a import (
    StageAObservation,
    assess_stage_a,
    load_stage_a_config,
)
from trading_system.serialization import canonical_json


def configure_stage_a_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    stage_a = commands.add_parser("stage-a")
    actions = stage_a.add_subparsers(dest="stage_a_command", required=True)
    assess = actions.add_parser("assess")
    assess.add_argument("--config", required=True)
    assess.add_argument("--input", required=True)


def _required(raw: dict[str, object], name: str) -> object:
    if name not in raw:
        raise ValueError(f"Stage A input is missing {name}")
    return raw[name]


def handle_stage_a(args: argparse.Namespace) -> int:
    if args.stage_a_command != "assess":
        raise ValueError(f"unsupported Stage A command: {args.stage_a_command}")
    raw = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Stage A input must be an object")
    gap_value = raw.get("gap_pct")
    observation = StageAObservation(
        str(_required(raw, "symbol")),
        date.fromisoformat(str(_required(raw, "session_date"))),
        datetime.fromisoformat(str(_required(raw, "known_at")).replace("Z", "+00:00")),
        Decimal(str(_required(raw, "close"))),
        Decimal(str(_required(raw, "ema8"))),
        Decimal(str(_required(raw, "ema21"))),
        Decimal(str(_required(raw, "ema50"))),
        Decimal(str(_required(raw, "recent_volume_surge"))),
        Decimal(str(_required(raw, "off_20d_high_pct"))),
        Decimal(str(_required(raw, "adr20_pct"))),
        Decimal(str(gap_value)) if gap_value is not None else None,
    )
    print(canonical_json(assess_stage_a(observation, load_stage_a_config(args.config))))
    return 0
