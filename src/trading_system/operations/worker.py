"""Packaged Phase 5C worker actions; not a general command executor."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from trading_system.operations.runner import WorkerAction
from trading_system.serialization import canonical_hash, canonical_json


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trading-system-operations-worker")
    parser.add_argument("--action", choices=tuple(WorkerAction), required=True)
    parser.add_argument("--target")
    return parser


def execute(action: WorkerAction, target: Path | None) -> dict[str, object]:
    if action is WorkerAction.EVIDENCE_NOOP:
        if target is not None:
            raise ValueError("evidence noop cannot have a target")
        return {
            "action": action.value,
            "evidence_hash": canonical_hash({"action": action.value}),
            "status": "OK",
        }
    if target is None or not target.is_absolute() or not target.is_file():
        raise ValueError("SQLite quick check requires an existing absolute target")
    uri = f"file:{target.as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.execute("PRAGMA query_only = ON")
        rows = tuple(str(row[0]) for row in connection.execute("PRAGMA quick_check"))
    return {
        "action": action.value,
        "database_label": target.name,
        "quick_check": rows,
        "status": "OK" if rows == ("ok",) else "FAILED",
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    action = WorkerAction(args.action)
    target = None if args.target is None else Path(args.target)
    result = execute(action, target)
    print(canonical_json(result))
    return 0 if result["status"] == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
