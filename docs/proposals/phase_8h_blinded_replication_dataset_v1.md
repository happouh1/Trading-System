# Phase 8H — Blinded Prospective Replication Dataset v1

Status: **OWNER-APPROVED TEST-ONLY REFERENCE IMPLEMENTATION; REAL DEPLOYMENT NOT APPROVED**.

## 1. Purpose

Phase 8H would create the first dataset boundary capable of satisfying Phase 8F/8G's independent
replication requirement. It would collect causal range-reclaim predictions and their source evidence
before outcomes are knowable, keep future outcomes inaccessible during collection, and produce an
immutable freeze manifest for later independent analysis.

This phase would not calculate outcomes, run Phase 8G statistics, inspect performance, select
parameters, change decisions, emit alerts, route orders, or trade.

## 2. Required upstream inputs

An approved implementation must bind each collection to:

- one independently reviewed and registered Phase 8F protocol;
- the exact verified Phase 8D hypothesis-family export referenced by that protocol;
- one immutable Phase 7 strategy/configuration lineage;
- one point-in-time universe provider and revision;
- one market-data provider, adjustment policy, calendar, and source-revision policy;
- one collection start and end rule fixed before collection starts;
- one authenticated data steward and separately authenticated analysis reviewer; and
- one trusted external timestamp/signature policy.

Missing or placeholder values fail closed. The synthetic Phase 8F test manifest is forbidden.

## 3. Separation of responsibilities

The proposed design uses three non-overlapping roles:

1. **Collector**: may read causal market data and append prediction/evidence records. It cannot read
   future outcome fields or Phase 8G results.
2. **Outcome steward**: may append outcomes only after their registered horizons close. It cannot
   change predictions, membership, hypotheses, costs, thresholds, or collection rules.
3. **Analysis reviewer**: receives a frozen, verified release only after collection ends. It cannot
   modify either source partition.

One person or credential must not hold conflicting privileges in the real protocol. Local test
fixtures may simulate roles but must be permanently marked synthetic.

## 4. Dataset lifecycle

```text
PROPOSED
  -> REGISTERED
  -> COLLECTING
  -> COLLECTION_CLOSED
  -> OUTCOMES_COMPLETE
  -> FROZEN
  -> RELEASED_FOR_ONE_ANALYSIS

Any state -> INVALIDATED
```

Transitions are append-only and require the immediately preceding state. No reopening, extending,
or shortening a collection after `COLLECTING` begins. A technical correction creates a new dataset
identity and preserves the invalidated lineage.

`RELEASED_FOR_ONE_ANALYSIS` grants only offline access to the separately approved Phase 8G adapter.
It grants no efficacy, configuration, alert, broker, or production authority.

## 5. Prediction partition

At each causal signal timestamp, the collector appends a record containing:

- deterministic collection, hypothesis, observation, entry, and `BOX_ID` identities;
- symbol, point-in-time instrument ID, direction, timeframe, horizon, and fold identity;
- signal, entry, and earliest outcome-availability timestamps;
- complete source candle/event/decision/config/code/calendar/universe identities and hashes;
- causal capacity and cost-input identities known at entry;
- membership acceptance or rejection and its frozen reason codes;
- a canonical payload hash and collection sequence number; and
- `outcome_present=false` with no outcome-valued fields.

The collection service rejects records received after their earliest outcome-availability timestamp.
It also rejects duplicate identities, conflicting content, noncanonical ordering, future evidence,
unknown family members, and mutable source revisions.

## 6. Outcome partition

Outcome records are physically and logically separate from predictions. Each record binds one
existing prediction and includes:

- the registered horizon close and `known_at` timestamp;
- gross directional return;
- each frozen transaction-cost component;
- net directional return in exact Decimal `R` units;
- capacity eligibility and reason;
- missingness or terminal-data reason;
- raw/adjusted source identities and corporate-action revision; and
- canonical payload and content hashes.

An outcome may be appended only when `known_at` is at or after the prediction's registered outcome
availability. It cannot update or delete the prediction. Missing outcomes remain explicit records;
they are never imputed or silently removed.

The collector process and normal operator CLI must have no method that returns outcome values.

## 7. Blindness and access controls

The real implementation must use an independently reviewed storage boundary. Merely placing two
tables in the same SQLite file is insufficient for a claim of blinding.

Required design inputs before implementation:

- separate storage locations or encryption domains for predictions and outcomes;
- distinct least-privilege credentials for collector, outcome steward, and reviewer;
- append-only authenticated access logs;
- an external trusted clock/timestamp source;
- signed hashes at registration, collection close, outcome completion, freeze, and release;
- backup, retention, correction, and secure-deletion policy; and
- a rule that any unauthorized outcome access permanently invalidates the replication dataset.

The repository may implement interfaces and offline fakes, but must not claim real blinding until an
external security review verifies the deployed controls.

## 8. Point-in-time universe and survivorship controls

Every session must resolve universe membership as it was knowable at that session. The release must
retain additions, removals, ticker and exchange changes, mergers, delistings, bankruptcies,
suspensions, and corporate actions. Symbols that disappear remain in the dataset.

The universe definition, provider, revision cadence, late-correction policy, and lookup failure
behavior must be registered before collection. A current constituent list or present-day symbol
lookup cannot reconstruct historical membership.

## 9. Family and membership freeze

The verified Phase 8D family is copied by identity, not re-derived from new outcomes. Every collected
prediction must map to exactly one registered family member and one causal `BOX_ID` cluster.

Phase 8H must not:

- add a promising symbol, horizon, direction, timeframe, or subgroup;
- remove a weak or inconvenient family member;
- alter `BOX_ID` clustering after outcome availability;
- change eligibility based on realized returns;
- extend collection to reach significance; or
- reuse a dataset after analysis for a second confirmatory claim.

## 10. Freeze manifest

The immutable freeze manifest must contain:

- protocol, source report/export, family, dataset, universe, data, code, calendar, adjustment, cost,
  and capacity hashes;
- collection lifecycle events and trusted timestamps;
- prediction and outcome partition roots, record counts, sequence ranges, and Merkle or canonical
  aggregate hashes;
- counts by hypothesis and every rejection/missingness reason;
- access-log root and all access-policy violations;
- corporate-action and late-source-revision disclosures;
- reviewer/steward identities and signatures; and
- permanent no-authority disclosures.

Freeze verification recomputes every record and aggregate hash. It never repairs, rewrites, or fills
missing evidence.

## 11. Failure and invalidation catalog

At minimum:

```text
UNREGISTERED_OR_PLACEHOLDER_PROTOCOL
SOURCE_FAMILY_MISMATCH
COLLECTION_STARTED_BEFORE_TRUSTED_REGISTRATION
PREDICTION_RECEIVED_AFTER_OUTCOME_AVAILABILITY
FUTURE_EVIDENCE_REFERENCE
DUPLICATE_OR_CONFLICTING_IDENTITY
UNIVERSE_REVISION_MISSING
DATA_REVISION_DRIFT
OUTCOME_PARTITION_ACCESSED_EARLY
ROLE_SEPARATION_VIOLATION
ACCESS_LOG_INCOMPLETE
COLLECTION_WINDOW_MUTATED
OUTCOME_FORMULA_OR_COST_MODEL_DRIFT
MISSING_OR_CONFLICTING_CORPORATE_ACTION
FREEZE_HASH_MISMATCH
```

Integrity, causality, early access, role separation, or collection-window failures invalidate the
whole dataset. Ordinary missing outcomes and capacity exclusions remain reportable evidence governed
by the preregistered Phase 8G gates.

## 12. Proposed repository components

Only after approval:

```text
config/range_reclaim.phase8h.v1.yaml
src/trading_system/research/range_replication_collection_contracts.py
src/trading_system/research/range_replication_collection_registry.py
src/trading_system/research/range_replication_freeze.py
migrations/080_phase_8h_replication_collection.sql
tests/unit/test_phase8h_replication_collection.py
tests/integration/test_phase8h_replication_collection.py
docs/phase_8h_review.md
```

The migration number must be recalculated from the repository at implementation time. Real storage,
credentials, signing, and timestamp adapters remain out of scope until their providers are approved.

## 13. Proposed tests

- deterministic identities and canonical serialization;
- append-only lifecycle and restart idempotence;
- rejection of late, duplicate, conflicting, future-referencing, and unknown-family predictions;
- outcome insertion only after the registered availability timestamp;
- immutable prediction payloads after outcomes exist;
- missing/delisted/corporate-action fixture retention;
- family completeness and point-in-time universe lineage;
- tamper detection for every record and aggregate hash;
- access-log and early-outcome-access invalidation;
- role-capability and package-import boundaries;
- input-order normalization or deterministic rejection; and
- proof that no CLI/API returns outcomes before a verified release.

## 14. Exit criteria

Phase 8H would be complete only when:

1. every required real provider, role, access, timestamp, and retention choice is independently
   approved;
2. predictions can be captured causally before outcome availability;
3. outcomes cannot alter predictions and remain inaccessible during collection;
4. the exact registered family and point-in-time universe are preserved;
5. collection closes under a fixed rule without result inspection;
6. a deterministic signed freeze manifest detects any mutation or early access;
7. the complete install, Ruff, strict mypy, pytest, restart, tamper, and architecture suites pass;
   and
8. analysis, efficacy, selection, alerts, broker writes, and production authority remain disabled.

## 15. Decisions required before implementation

- `REVIEWER_REQUIRED_DATA_PROVIDER_AND_REVISION_POLICY`
- `REVIEWER_REQUIRED_POINT_IN_TIME_UNIVERSE_PROVIDER`
- `REVIEWER_REQUIRED_COLLECTION_WINDOW`
- `REVIEWER_REQUIRED_STORAGE_AND_ENCRYPTION_BOUNDARY`
- `REVIEWER_REQUIRED_AUTHENTICATED_ROLE_DIRECTORY`
- `REVIEWER_REQUIRED_TRUSTED_TIMESTAMP_AND_SIGNATURE_SERVICE`
- `REVIEWER_REQUIRED_ACCESS_LOG_ATTESTATION`
- `REVIEWER_REQUIRED_RETENTION_CORRECTION_AND_DELETION_POLICY`
- `REVIEWER_REQUIRED_OUTCOME_STEWARD`
- `REVIEWER_REQUIRED_INDEPENDENT_ANALYSIS_REVIEWER`

Current decision: `TEST_ONLY_REFERENCE_IMPLEMENTED__REAL_COLLECTION_NOT_READY`.
