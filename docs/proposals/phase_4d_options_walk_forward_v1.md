# Phase 4D — Chronological Options Experiments v1

## Purpose and authority

Phase 4D evaluates the fixed Phase 4B screening rules and Phase 4C conservative fill model across
expanding chronological folds. It is offline research infrastructure. It does not optimize a
threshold, choose an exit, promote a strategy, allocate capital, contact a broker, or authorize an
options order.

## Immutable inputs

An experiment receives one ordered, explicit exchange-session sequence and immutable Phase 4C
cases. The dataset revision, ordered case IDs, session sequence, Phase 4C configuration hash, and
Phase 4D configuration hash form the deterministic experiment identity. Input permutations are
canonicalized by `(screen_known_at, case_id)`; duplicate cases or unordered/duplicate sessions fail.

The session sequence is supplied by the research dataset. Phase 4D does not infer missing sessions
or manufacture a calendar. Its provenance is included in the experiment source revision.

## Causal fold assignment

The checked-in fold defaults match the existing Phase 2 research baseline and are **TUNABLE**:
504 training sessions, 63 validation sessions, 63 test sessions, a 63-session step, and a five-session
embargo before validation and test. Training expands from the first declared session.

Cases are assigned using the UTC date of `screen_known_at`. A case is eligible only when the UTC
date of `exit.as_of` is no later than that partition's cutoff. Otherwise it is `EXCLUDED` with
`LABEL_UNAVAILABLE_AT_CUTOFF`. This prevents later option marks from becoming training,
validation, or test truth prematurely.

## Experiment lifecycle

```text
DEFINED -> DEVELOPMENT_EVALUATED -> FROZEN -> TEST_EVALUATED -> COMPLETE
```

Development evaluates TRAIN and VALIDATION only. The freeze hash binds the experiment definition,
fold identities, and development evaluation identities. TEST evaluation requires an exact stored
freeze match. Definitions, assignments, evaluations, and transitions are append-only and
content-addressed; conflicting identity reuse fails.

No Phase 4D command compares alternative configurations or selects a winner. Any proposed change
after validation requires a new versioned experiment identity and cannot reuse the frozen test.

## Metrics and disclosures

Each fold/partition reports the existing Phase 4C case-level metrics. The configured minimum sample
is 30 completed cases (**TUNABLE**); smaller partitions remain visible but carry
`PARTITION_SAMPLE_BELOW_CONFIGURED_MINIMUM` and cannot support comparative claims.

Every evaluation discloses that cases may overlap and that no portfolio capital allocation exists.
Therefore total P&L and drawdown are descriptive case-sequence values, not funded-portfolio CAGR,
Sharpe, exposure, capacity, or buying-power results.

## Explicit exclusions

- threshold search, optimization, calibration, or automatic promotion;
- random or shuffled time splits;
- exits not already supplied by the Phase 4C dataset;
- expiration, exercise, assignment, delivery, rolls, or multi-leg positions;
- finite-capital portfolio simulation, quote-size capacity, margin, or buying power;
- broker, Webull, paper, live-data, or order dependencies.

## Exit criteria

- deterministic expanding folds and embargo boundaries;
- exit-label availability enforced at every partition cutoff;
- development/test separation with exact freeze-before-test enforcement;
- append-only, restart-safe SQLite lifecycle and canonical payload hashes;
- null-safe case-level metrics and mandatory overlap/sample disclosures;
- strict configuration, CLI, migration parity, architecture, lint, typing, and full tests pass.
