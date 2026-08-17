"""Learning-ready observation exports with immutable provenance columns."""

from __future__ import annotations

import importlib
from collections.abc import Mapping, Sequence
from pathlib import Path

from trading_system.reporting import export_csv


def write_observations(
    rows: Sequence[Mapping[str, object]],
    destination: str | Path,
    format_name: str,
) -> None:
    target = Path(destination)
    if format_name == "csv":
        target.write_text(export_csv(rows), encoding="utf-8", newline="")
        return
    if format_name == "parquet":
        pyarrow = importlib.import_module("pyarrow")
        parquet = importlib.import_module("pyarrow.parquet")
        table = pyarrow.Table.from_pylist([dict(row) for row in rows])
        parquet.write_table(table, target, compression="zstd")
        return
    raise ValueError("format must be csv or parquet")
