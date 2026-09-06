# Phase 8B — Causal Confirmatory Registry v1

Status: implemented as an offline research-only boundary.

## Purpose

Phase 8B connects the Phase 8A exact sign-test implementation to persisted, point-in-time
Phase 7 evidence. It materializes only Phase 7G `TEST` cohort summaries whose frozen evidence
gate passed. It does not search cohorts, tune parameters, or interpret results as efficacy.

## Deterministic source chain

For one Phase 7C plan, the adapter:

1. verifies the canonical payload hash of the plan and reads its frozen familywise alpha;
2. selects only Phase 7G rows with `partition=TEST` and `gate_passed=1`;
3. verifies every selected summary and exact Phase 7G assignment payload hash;
4. requires summary observation and independent-cluster counts to equal the source records;
5. verifies the matching Phase 7F outcome and its entry, box, timeframe, direction, and horizon;
6. groups net directional returns by `BOX_ID` and takes the exact Decimal arithmetic mean;
7. invokes Phase 8A once for the complete eligible family so Holm correction is family-wide; and
8. writes immutable, idempotent test records with both analysis and adapter configuration hashes.

Missing, extra, corrupt, mismatched, or ambiguous evidence fails closed. An empty eligible family
is a valid zero-result materialization.

## Authority boundary

Phase 8B is offline and makes no network or broker call. It cannot claim efficacy, select a
parameter, change scoring or decisions, emit alerts, route options, submit orders, or trade live.
Those capabilities require separately specified evidence and authorization.
