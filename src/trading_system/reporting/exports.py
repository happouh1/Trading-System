"""Deterministic reporting helpers."""

from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping
from io import StringIO

from trading_system.backtest import BacktestMetrics
from trading_system.serialization import canonical_json, canonical_value


def export_jsonl(rows: Iterable[object]) -> str:
    return "".join(f"{canonical_json(row)}\n" for row in rows)


def export_csv(rows: Iterable[Mapping[str, object]]) -> str:
    materialized = tuple(rows)
    if not materialized:
        return ""
    columns = tuple(sorted({key for row in materialized for key in row}))
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in materialized:
        writer.writerow(
            {column: canonical_json(row[column]) if column in row else "" for column in columns}
        )
    return output.getvalue()


def markdown_report(run_id: str, metrics: BacktestMetrics) -> str:
    data = canonical_value(metrics)
    assert isinstance(data, dict)
    lines = [f"# Backtest report: {run_id}", "", "## Metrics", ""]
    for key in sorted(key for key in data if key != "__type__"):
        lines.append(f"- {key}: `{canonical_json(data[key])}`")
    lines.extend(
        [
            "",
            "## Bias disclosures",
            "",
            "- File universes may have survivorship bias without point-in-time membership.",
            "- Corporate actions are limited to the recorded revision and adjustment policy.",
            "- OHLC cannot reconstruct intrabar order; collisions resolve adverse-first.",
            "- Results are research outputs, not evidence of future profitability.",
            "",
        ]
    )
    return "\n".join(lines)
