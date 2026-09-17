"""Offline evidence commands with no credential or network boundary."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_json
from trading_system.webull.trade_evidence import timestamp
from trading_system.webull.trade_evidence_registry import (
    TradeEvidenceImportRegistry,
    reconcile_trade_evidence,
)

COMMANDS = frozenset({"import-trade-evidence", "reconcile-trade-evidence"})


def configure_trade_evidence_parser(
    actions: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    ingest = actions.add_parser("import-trade-evidence")
    ingest.add_argument("--config", required=True)
    ingest.add_argument("--database", required=True)
    ingest.add_argument("--session-id", required=True)
    ingest.add_argument("--evidence", required=True)
    ingest.add_argument("--source-document", required=True)
    reconcile = actions.add_parser("reconcile-trade-evidence")
    reconcile.add_argument("--config", required=True)
    reconcile.add_argument("--database", required=True)
    reconcile.add_argument("--import-id", required=True)
    reconcile.add_argument("--as-of", required=True)


def handle_trade_evidence(args: argparse.Namespace) -> int:
    try:
        if not Path(args.database).is_file():
            raise ValueError("an existing candidate database is required")
        with SQLiteRepository(args.database) as repository:
            if args.webull_command == "import-trade-evidence":
                repository.migrate()
                capture, inserted = TradeEvidenceImportRegistry(repository).import_files(
                    args.evidence, args.source_document, session_id=args.session_id,
                    imported_at=datetime.now(UTC),
                )
                print(canonical_json({
                    "import_id": capture.import_id, "candidate_id": capture.candidate_id,
                    "capture_hash": capture.payload_hash, "source_sha256": capture.source_sha256,
                    "inserted": inserted, "status": "IMPORTED_PENDING_RECONCILIATION",
                    "source_authenticity_verified": False, "qualifying_completed_trade": False,
                    "network_used": False, "broker_write_performed": False,
                }))
                return 0
            repository.connection.execute("PRAGMA query_only = ON")
            report = reconcile_trade_evidence(
                repository, args.import_id, as_of=timestamp(args.as_of),
            )
            print(canonical_json(report))
            return 0 if report.status == "RECONCILED_PENDING_REVIEW" else 1
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(f"trade evidence error: {exc}", file=sys.stderr)
        return 1
