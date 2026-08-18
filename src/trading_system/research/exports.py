"""Deterministic Phase 2A research exports and bias disclosures."""

from __future__ import annotations

import csv
import importlib
from collections.abc import Mapping, Sequence
from pathlib import Path

from trading_system.serialization import canonical_json

BIAS_DISCLOSURES = (
    "Historical results do not establish future profitability.",
    "Point-in-time membership is required to limit survivorship bias.",
    "Repeated validation choices can overfit even when test folds are untouched.",
    "Empirical outputs do not alter Phase 1 rule decisions.",
)


def export_jsonl(rows: Sequence[object], path: str | Path) -> None:
    body = "".join(f"{canonical_json(row)}\n" for row in rows)
    Path(path).write_text(body, encoding="utf-8", newline="\n")


def export_csv(rows: Sequence[Mapping[str, object]], path: str | Path) -> None:
    fields = tuple(sorted({key for row in rows for key in row}))
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        if fields:
            writer.writeheader()
            for row in rows:
                writer.writerow({key: canonical_json(row.get(key)) for key in fields})


def export_parquet(rows: Sequence[Mapping[str, object]], path: str | Path) -> None:
    """Write stable columns and canonical JSON cells using Zstandard compression."""
    fields = tuple(sorted({key for row in rows for key in row}))
    normalized = [
        {key: canonical_json(row.get(key)) for key in fields}
        for row in rows
    ]
    pyarrow = importlib.import_module("pyarrow")
    parquet = importlib.import_module("pyarrow.parquet")
    schema = pyarrow.schema([(key, pyarrow.string()) for key in fields])
    table = pyarrow.Table.from_pylist(normalized, schema=schema)
    parquet.write_table(table, Path(path), compression="zstd")


def research_markdown(experiment_id: str, sections: Mapping[str, object]) -> str:
    lines = [f"# Empirical research report: {experiment_id}", ""]
    for name in sorted(sections):
        lines.extend((f"## {name}", "", f"`{canonical_json(sections[name])}`", ""))
    lines.extend(("## Bias and authority disclosures", ""))
    lines.extend(f"- {item}" for item in BIAS_DISCLOSURES)
    return "\n".join(lines) + "\n"
