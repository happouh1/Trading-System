"""Phase 1D file-based research commands."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from trading_system import PACKAGE_VERSION
from trading_system.backtest import summarize
from trading_system.config import load_config
from trading_system.learning import write_observations
from trading_system.market_data import XNYSCalendar, read_ohlcv
from trading_system.modeling.cli import configure_model_parser, handle_model
from trading_system.operations.cli import configure_operations_parser, handle_operations
from trading_system.options.cli import configure_options_parser, handle_options
from trading_system.paper.cli import configure_paper_parser, handle_paper
from trading_system.persistence import RunRecord, SQLiteRepository
from trading_system.portfolio.cli import configure_portfolio_parser, handle_portfolio
from trading_system.replay import ReplayOrchestrator
from trading_system.reporting import markdown_report
from trading_system.research.cli import configure_research_parser, handle_research
from trading_system.serialization import canonical_hash, canonical_json
from trading_system.webull.cli import configure_webull_parser, handle_webull


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trading-system")
    commands = parser.add_subparsers(dest="command", required=True)
    replay = commands.add_parser("replay")
    replay.add_argument("--input", required=True)
    replay.add_argument("--database", required=True)
    replay.add_argument("--run-id", required=True)
    replay.add_argument("--config", required=True)
    replay.add_argument("--resume", action="store_true")
    export = commands.add_parser("export-observations")
    export.add_argument("--database", required=True)
    export.add_argument("--run-id", required=True)
    export.add_argument("--format", choices=("csv", "parquet"), required=True)
    export.add_argument("--output", required=True)
    report = commands.add_parser("report")
    report.add_argument("--database", required=True)
    report.add_argument("--run-id", required=True)
    report.add_argument("--output", required=True)
    explain = commands.add_parser("explain")
    explain.add_argument("--database", required=True)
    explain.add_argument("--decision-id", required=True)
    configure_research_parser(commands)
    configure_model_parser(commands)
    configure_paper_parser(commands)
    configure_webull_parser(commands)
    configure_portfolio_parser(commands)
    configure_options_parser(commands)
    configure_operations_parser(commands)
    return parser


def _replay(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    calendar = XNYSCalendar()
    candles = tuple(read_ohlcv(args.input, calendar))
    revisions = tuple((item.candle_id, item.source_revision) for item in candles)
    data_revision = canonical_hash(revisions)
    seed = config.section("determinism")["seed"]
    if not isinstance(seed, int):
        raise TypeError("validated determinism.seed must be an integer")
    with SQLiteRepository(args.database) as repository:
        repository.migrate()
        checkpoint = repository.load_checkpoint(args.run_id) if args.resume else None
        expected_metadata = (
            PACKAGE_VERSION,
            config.config_hash,
            data_revision,
            calendar.version,
            seed,
        )
        stored_metadata = repository.run_metadata(args.run_id)
        if stored_metadata is None:
            repository.insert_run(
                RunRecord(
                    args.run_id,
                    datetime.now(UTC),
                    PACKAGE_VERSION,
                    config.config_hash,
                    data_revision,
                    calendar.version,
                    seed,
                )
            )
        elif stored_metadata != expected_metadata:
            raise ValueError(
                "run ID exists with different code, config, data, or calendar metadata"
            )
        risk_budget = config.section("risk").get("normalized_risk_budget_currency")
        if isinstance(risk_budget, bool) or not isinstance(risk_budget, (int, float)):
            raise ValueError(
                "Phase 1E replay requires risk.normalized_risk_budget_currency"
            )
        summary = ReplayOrchestrator(
            args.run_id,
            repository,
            normalized_risk_budget=Decimal(str(risk_budget)),
        ).run(
            candles,
            resume_after=checkpoint[0] if checkpoint is not None else None,
            processed_before=checkpoint[1] if checkpoint is not None else 0,
            prior_state_hash=checkpoint[2] if checkpoint is not None else "GENESIS",
        )
    print(canonical_json(summary))
    return 0


def _export(args: argparse.Namespace) -> int:
    with SQLiteRepository(args.database) as repository:
        repository.migrate()
        rows = repository.observation_export_rows(args.run_id)
    write_observations(rows, args.output, args.format)
    print(canonical_json({"run_id": args.run_id, "rows": len(rows), "output": args.output}))
    return 0


def _report(args: argparse.Namespace) -> int:
    with SQLiteRepository(args.database) as repository:
        repository.migrate()
        counts = repository.run_counts(args.run_id)
        metrics = summarize(repository.trade_results(args.run_id))
    body = markdown_report(args.run_id, metrics)
    body += "\n## Persisted records\n\n"
    body += "\n".join(f"- {name}: `{counts[name]}`" for name in sorted(counts))
    body += "\n"
    Path(args.output).write_text(body, encoding="utf-8", newline="\n")
    print(canonical_json({"run_id": args.run_id, "output": args.output}))
    return 0


def _explain(args: argparse.Namespace) -> int:
    with SQLiteRepository(args.database) as repository:
        repository.migrate()
        payload = repository.decision_payload(args.decision_id)
    if payload is None:
        print(f"decision not found: {args.decision_id}", file=sys.stderr)
        return 1
    print(payload)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    handlers = {
        "replay": _replay,
        "export-observations": _export,
        "report": _report,
        "explain": _explain,
        "research": handle_research,
        "model": handle_model,
        "paper": handle_paper,
        "webull": handle_webull,
        "portfolio": handle_portfolio,
        "options": handle_options,
        "operations": handle_operations,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
