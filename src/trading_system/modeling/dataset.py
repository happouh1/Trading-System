"""Causal Phase 3A feature and target validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from trading_system.modeling.contracts import ModelRow

FORBIDDEN_FEATURES = {
    "entry_price",
    "exit_price",
    "forward_return",
    "gross_r",
    "mae_r",
    "mfe_r",
    "net_r",
    "observation_id",
    "outcome_label",
    "review_verdict",
    "row_id",
    "time_to_1r",
    "time_to_2r",
    "trade_id",
}


@dataclass(frozen=True, slots=True)
class PreparedRows:
    rows: tuple[ModelRow, ...]
    targets: tuple[int, ...]
    excluded: tuple[tuple[str, str], ...]


def prepare_rows(
    rows: tuple[ModelRow, ...],
    *,
    numeric_features: tuple[str, ...],
    categorical_features: tuple[str, ...],
    positive_labels: tuple[str, ...],
    negative_labels: tuple[str, ...],
    cutoff: datetime,
) -> PreparedRows:
    allowed = set(numeric_features) | set(categorical_features)
    if allowed & FORBIDDEN_FEATURES:
        raise ValueError("feature schema contains forbidden future or identity fields")
    selected: list[ModelRow] = []
    targets: list[int] = []
    excluded: list[tuple[str, str]] = []
    seen: set[str] = set()
    for row in sorted(rows, key=lambda item: (item.label_available_at, item.row_id)):
        if row.row_id in seen:
            raise ValueError(f"duplicate model row: {row.row_id}")
        seen.add(row.row_id)
        unknown = set(row.features) - allowed
        if unknown:
            raise ValueError(f"unknown or forbidden model features: {sorted(unknown)}")
        if row.label_available_at > cutoff:
            excluded.append((row.row_id, "LABEL_UNAVAILABLE_AT_CUTOFF"))
        elif row.outcome_label in positive_labels:
            selected.append(row)
            targets.append(1)
        elif row.outcome_label in negative_labels:
            selected.append(row)
            targets.append(0)
        else:
            excluded.append((row.row_id, "UNSUPPORTED_OR_UNCERTAIN_LABEL"))
    return PreparedRows(tuple(selected), tuple(targets), tuple(excluded))
