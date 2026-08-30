"""Read-only SQLite evidence inspection for Phase 5A."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from trading_system.operations.config import OperationsConfig
from trading_system.operations.contracts import ComponentEvidence, ReadinessStatus
from trading_system.serialization import canonical_hash, deterministic_id


def inspect_component(
    config: OperationsConfig,
    *,
    component: str,
    database_label: str,
    database_path: str | Path,
    known_at: datetime,
) -> ComponentEvidence:
    if component not in config.components:
        raise ValueError(f"unknown operations component: {component}")
    if not database_label:
        raise ValueError("database label is required")
    if known_at.tzinfo is None or known_at.utcoffset() is None:
        raise ValueError("inspection known_at must be timezone-aware")
    path = Path(database_path).resolve()
    reasons: list[str] = []
    counts: list[tuple[str, int]] = []
    monotonic_markers: list[tuple[str, int, int]] = []
    if not path.is_file():
        reasons.append("DATABASE_NOT_FOUND")
    else:
        uri = path.as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        try:
            present = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            for table in sorted(config.components[component]):
                if table not in present:
                    reasons.append(f"MISSING_TABLE:{table}")
                    counts.append((table, 0))
                    continue
                row = connection.execute(
                    f'SELECT COUNT(*), COALESCE(MAX(rowid), 0) FROM "{table}"'
                ).fetchone()
                if row is None:
                    raise ValueError(f"unable to inspect required table: {table}")
                count, maximum_rowid = int(row[0]), int(row[1])
                counts.append((table, count))
                monotonic_markers.append((table, count, maximum_rowid))
                if count == 0:
                    reasons.append(f"NO_EVIDENCE:{table}")
            reconciliation_table = {
                "PAPER": "paper_reconciliations",
                "WEBULL_SANDBOX": "webull_reconciliations",
            }.get(component)
            if reconciliation_table is not None and reconciliation_table in present:
                columns = {
                    str(row[1])
                    for row in connection.execute(
                        f'PRAGMA table_info("{reconciliation_table}")'
                    ).fetchall()
                }
                if "matched" not in columns:
                    reasons.append(f"INVALID_SCHEMA:{reconciliation_table}:matched")
                else:
                    latest = connection.execute(
                        f'SELECT matched FROM "{reconciliation_table}" '
                        "ORDER BY rowid DESC LIMIT 1"
                    ).fetchone()
                    if latest is not None and int(latest[0]) != 1:
                        reasons.append("LATEST_RECONCILIATION_UNMATCHED")
        finally:
            connection.close()
    ordered_counts = tuple(sorted(counts))
    ordered_reasons = tuple(sorted(reasons))
    fingerprint = canonical_hash(
        (component, database_label, ordered_counts, tuple(monotonic_markers), ordered_reasons)
    )
    identity = (component, database_label, known_at, fingerprint, config.config_hash)
    return ComponentEvidence(
        deterministic_id("operations_component_evidence", identity),
        component,
        database_label,
        known_at,
        ReadinessStatus.READY if not ordered_reasons else ReadinessStatus.NOT_READY,
        ordered_counts,
        ordered_reasons,
        fingerprint,
    )
