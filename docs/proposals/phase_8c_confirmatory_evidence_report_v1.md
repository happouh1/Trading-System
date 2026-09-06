# Phase 8C — Confirmatory Evidence Report v1

Status: implemented as an offline, non-interpretive research artifact.

## Purpose

Phase 8C creates one immutable report for the complete verified Phase 8B confirmatory family. It
preserves exact sign counts, raw p-values, Holm-adjusted p-values, frozen alpha, null-hypothesis
status, and configuration lineage in canonical summary order.

## Rules

- The complete Phase 8B family must revalidate against Phase 7C, Phase 7F, and Phase 7G evidence.
- Rows are ordered by `summary_id`; there is no performance ordering or ranking.
- `REJECTED` means only that the configured statistical null was rejected by Phase 8A.
- The report does not calculate an effect size, interval, pooled estimate, or economic threshold.
- Empty eligible families produce a valid zero-row report pinned to the requested config hashes.
- Materialization is deterministic, append-only, idempotent, and conflicting identities fail closed.
- Status recomputes the report in memory and does not create or mutate records.

## Authority boundary

The report explicitly states that null rejection is not an efficacy claim. It cannot select
parameters, rank hypotheses, modify scoring or decisions, emit alerts, route options, perform
broker writes, or authorize production use.
