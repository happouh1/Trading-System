# Phase 7H — Range evaluation audit reports v1

## Purpose

Phase 7H turns one complete Phase 7G evaluation result into a deterministic audit manifest and a
human-readable report. The report preserves the full denominator, verifies content integrity, and
uses canonical cohort order instead of ranking results.

## Integrity model

The builder requires one Phase 7C plan, at least one assignment, and at least one cohort summary.
It reconstructs every non-excluded cohort from Phase 7G assignments and requires exact agreement
with the summary's observation and distinct-box counts. It also requires statistics to exist if
and only if the evidence gate passed.

The manifest stores SHA-256 roots over the canonically ordered assignment and summary contracts.
Before append-only persistence, both roots and every source payload hash are checked against the
database. Exact retries are idempotent; missing or changed evidence fails closed.

## Presentation

Markdown lists cohorts by fold, partition, timeframe, direction, and horizon. Failed-gate
statistics are displayed as `WITHHELD_GATE_FAILED`. Passing statistics are shown verbatim. The
report does not sort by return, win rate, significance, or any other outcome.

## Authority boundary

Phase 7H makes no hypothesis test, multiple-testing inference, efficacy claim, horizon selection,
parameter selection, score change, alert, options route, broker request, or live-trading change.
