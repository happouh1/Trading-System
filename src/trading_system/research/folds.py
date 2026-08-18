"""Deterministic exchange-session walk-forward folds."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from trading_system.research.contracts import ResearchRow, WalkForwardFold, WalkForwardSpec
from trading_system.serialization import deterministic_id


def build_walk_forward_folds(
    experiment_id: str,
    sessions: Sequence[date],
    spec: WalkForwardSpec,
) -> tuple[WalkForwardFold, ...]:
    ordered = tuple(sessions)
    if tuple(sorted(set(ordered))) != ordered:
        raise ValueError("sessions must be unique and strictly increasing")
    required = (
        spec.minimum_train_sessions
        + spec.embargo_sessions
        + spec.validation_sessions
        + spec.embargo_sessions
        + spec.test_sessions
    )
    folds: list[WalkForwardFold] = []
    train_end_index = spec.minimum_train_sessions - 1
    while train_end_index + required - spec.minimum_train_sessions < len(ordered):
        validation_start_index = train_end_index + spec.embargo_sessions + 1
        validation_end_index = validation_start_index + spec.validation_sessions - 1
        test_start_index = validation_end_index + spec.embargo_sessions + 1
        test_end_index = test_start_index + spec.test_sessions - 1
        if test_end_index >= len(ordered):
            break
        ordinal = len(folds)
        identity = (
            experiment_id,
            ordinal,
            ordered[0],
            ordered[train_end_index],
            ordered[validation_start_index],
            ordered[validation_end_index],
            ordered[test_start_index],
            ordered[test_end_index],
        )
        folds.append(
            WalkForwardFold(
                deterministic_id("experiment_fold", identity),
                experiment_id,
                ordinal,
                ordered[0],
                ordered[train_end_index],
                ordered[validation_start_index],
                ordered[validation_end_index],
                ordered[test_start_index],
                ordered[test_end_index],
            )
        )
        train_end_index += spec.step_sessions
    return tuple(folds)


def eligible_labeled_rows(
    rows: Sequence[ResearchRow],
    *,
    cutoff: date,
) -> tuple[ResearchRow, ...]:
    """Select rows whose session and label availability are both known by cutoff."""
    selected: list[ResearchRow] = []
    for row in rows:
        if row.label_available_at is None:
            continue
        if row.session_date <= cutoff and row.label_available_at.date() <= cutoff:
            selected.append(row)
    return tuple(selected)
