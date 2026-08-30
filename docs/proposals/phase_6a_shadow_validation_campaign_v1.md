# Phase 6A Offline Shadow-Validation Campaign v1

## Authorization and purpose

Phase 6A was explicitly approved after completion of Phase 5F. Because the baseline specification
does not define Phase 6A behavior, this implementation uses the narrow conservative extension:
aggregate exact persisted Phase 5F windows and report evidence completeness without defining an
operational success threshold or granting authority.

## Campaign input

The caller supplies a campaign name, start/end/evaluation timestamps, source revision, and a
nonempty set of windows. Each window contains a unique ID, unique exact expected as-of, and either
one Phase 5F bundle ID or `null`. Null is an explicit missing observation. Ordering is normalized;
duplicates and out-of-bounds windows are rejected.

No schedule is inferred from adjacent timestamps. Consequently a campaign cannot claim that its
declared windows are exhaustive; that governance question remains open.

## Window validation

An observed window is `COMPLETE` only when:

1. the named Phase 5F row exists;
2. its payload parses and canonically re-hashes to the stored digest;
3. its row and payload identities, timestamp, status, and current code version agree;
4. the exact mandatory Phase 5F non-authority disclosures remain present;
5. all six recorded source hashes match current persisted Phase 5A-E evidence;
6. readiness, monitoring, latest execution attempt, controls, and restore retain reviewed statuses.

Other classifications are `INCOMPLETE`, `MISSING`, and `CORRUPT`, each with canonical reasons.

## Campaign result

The campaign is structurally `COMPLETE` only when every declared window is complete. Metrics are
exact counts of declared/observed classifications and source statuses. Phase 6A defines no minimum
number of windows, duration, completion percentage, freshness SLO, or statistical threshold.

## Persistence

Reports and windows are stored transactionally in append-only SQLite tables with deterministic IDs,
canonical payloads, hashes, uniqueness constraints, and restart-safe idempotency. Source evidence
is never updated by Phase 6A.

## Authority boundary

Configuration locks network, credentials, notifications, automatic promotion, broker writes, live
trading, and production-readiness claims off. Phase 6A does not execute scheduled jobs, change kill
switches, restore databases, select trades, or submit orders.

## Exit criteria

1. Strict configuration rejects authority expansion and invented thresholds.
2. Window order is deterministic; duplicate and invalid bounds fail closed.
3. Missing, corrupt, future, mismatched, or mutated evidence cannot produce `COMPLETE`.
4. Valid multi-window campaigns are deterministic, append-only, restart-safe, and CLI-accessible.
5. Migration parity, unit, integration, repository-wide lint, type, and test suites pass.
