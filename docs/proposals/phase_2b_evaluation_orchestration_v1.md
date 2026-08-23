# Proposed Phase 2B evaluation orchestration v1

Status: **IMPLEMENTED — CI VALIDATION PENDING**

## Purpose

Phase 2B turns the immutable Phase 2A primitives into a reproducible experiment workflow over
persisted Phase 1 observations, decisions, trades, and outcomes. It evaluates the existing system;
it does not change signals, confidence, thresholds, position sizing, or execution behavior.

## Proposed bounded scope

1. A deterministic experiment orchestrator that validates source-run identity, research configuration,
   data revisions, universe revision, calendar versions, and label availability before execution.
2. Exchange-session fold assignment using the approved expanding `504/63/63`, 63-session step, and
   five-session embargo defaults. Fold membership and every exclusion reason are persisted.
3. Immutable cohort specifications for pattern, direction, timeframe, regime, confidence bucket,
   decision action, and data-quality status. Cohorts are declared before test evaluation and carry a
   canonical specification hash.
4. Per-fold training, validation, and test reports containing the approved descriptive statistics,
   calibration bins, similarity diagnostics, rejected-signal counts, and data-quality exclusions.
5. A deterministic symbol-held-out diagnostic in addition to chronological folds. Proposed initial
   policy: assign symbols to `5` stable hash buckets (**TUNABLE**) and rotate one bucket as the held-out
   diagnostic. This report is supplemental and cannot replace chronological test results.
6. An explicit experiment lifecycle:

   ```text
   DEFINED -> TRAIN_EVALUATED -> VALIDATION_EVALUATED -> FROZEN -> TEST_EVALUATED -> COMPLETE
   ```

   Test evaluation is prohibited until cohort definitions, metric version, similarity configuration,
   and validation-stage selections are frozen. Lifecycle transitions are append-only.
7. Research CLI commands for defining, validating, running, freezing, resuming, reporting, and
   explaining experiments. Proposed interface:

   ```text
   trading-system research define --runs RUNS --universe FILE --config FILE
   trading-system research validate --experiment-id ID
   trading-system research run --experiment-id ID --stage train
   trading-system research run --experiment-id ID --stage validation
   trading-system research freeze --experiment-id ID
   trading-system research run --experiment-id ID --stage test
   trading-system research report --experiment-id ID --output REPORT.md
   trading-system research explain --result-id ID
   ```

8. Human-review import/export commands using append-only Phase 2A records. No consensus label is
   inferred; conflicting reviews remain visible and `UNCERTAIN` remains excluded from training truth.
9. Restart-safe checkpoints, canonical CSV/Parquet/JSONL/Markdown outputs, and complete causal
   provenance for every result.

## Proposed conditional-report policy

Every experiment emits an unconditional baseline. Conditional cohorts are emitted only when declared
in the frozen cohort specification. To limit misleading small-sample claims, proposed reports show
statistics for all counts but mark cohorts with fewer than `30` eligible observations as
`INSUFFICIENT_SAMPLE` (**TUNABLE**). They are not ranked or described as superior/inferior.

No multiple-comparison correction is proposed in Phase 2B because Phase 2B performs no automated
selection. The report MUST disclose the number of evaluated cohorts and warn that manual comparison
can still overfit. Any future automated selection requires a separate approved proposal.

## Persistence additions

Proposed append-only tables:

- `experiment_transitions`;
- `experiment_cohorts`;
- `fold_assignments`;
- `experiment_exclusions`;
- `experiment_checkpoints`;
- `experiment_reports`;
- `symbol_holdout_assignments`.

All rows carry experiment/fold identity, known-at time where applicable, canonical payload JSON, and
payload hash. Existing Phase 1 and Phase 2A records are never rewritten.

## Anti-leakage and authority requirements

- source observations and outcomes are joined by immutable identifiers, never mutable current state;
- a row is unavailable until `label_available_at` satisfies the stage cutoff;
- training-derived normalization is fitted separately for each fold and never on validation/test;
- validation may inform a newly versioned frozen experiment definition, but test results cannot;
- test results cannot be deleted, rerun under the same experiment ID with changed inputs, or used to
  modify Phase 1 decisions;
- current universe membership cannot substitute for historical membership;
- incomplete, conflicting, or revision-mismatched inputs fail before evaluation;
- research packages remain forbidden dependencies of `decisions`.

## Required validation

- end-to-end fixture experiment through every lifecycle transition;
- rejection of test execution before freeze;
- rejection of post-freeze cohort/config mutation;
- fold assignment, embargo, label cutoff, delisting, and symbol-holdout golden fixtures;
- training-only normalization and future-truncation tests;
- deterministic restart/checkpoint and byte-equivalent export tests;
- conflicting source revision and duplicate-result persistence tests;
- architecture tests preserving research/decision separation;
- complete installation, Ruff, strict mypy, pytest, and CI checks.

## Explicit exclusions

- parameter optimization, threshold search, cohort mining, or automated strategy selection;
- supervised learning, empirical confidence promotion, or model-driven decisions;
- portfolio construction, capital allocation, options, paper/live brokerage, or order routing;
- external market-data acquisition or a production universe vendor integration;
- claims that any cohort, pattern, or strategy is profitable.

## Approved decisions

Approval authorizes only the bounded workflow above:

1. the append-only lifecycle and mandatory freeze before test evaluation;
2. declared conditional cohorts with `30` as the tunable insufficient-sample threshold;
3. the supplemental five-bucket stable symbol-held-out diagnostic;
4. individual human-review tooling with consensus still deferred;
5. CLI orchestration and persistence additions, with no optimization or ML authority.
