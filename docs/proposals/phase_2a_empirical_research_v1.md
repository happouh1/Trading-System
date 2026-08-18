# Proposed Phase 2A empirical research foundation v1

Status: **APPROVED — IMPLEMENTATION IN PROGRESS**

## Purpose

Phase 2A adds reproducible, point-in-time historical experiments over immutable Phase 1 records.
It must not change Phase 1 features, events, decisions, trades, confidence, or outcomes.

## Proposed bounded scope

1. An immutable experiment contract and registry containing experiment ID, creation time, source run
   IDs, code version, configuration hashes, data revisions, calendar versions, universe revision,
   fold specification, metric specification, seed, status, and canonical payload hash.
2. Point-in-time universe membership snapshots with `effective_from`, optional `effective_to`, source,
   and source revision. Membership is joined as-of evaluation time; current constituents cannot be
   applied retroactively.
3. Expanding-window walk-forward fold generation. Proposed **TUNABLE** default:
   - minimum training history: 504 XNYS sessions;
   - validation window: 63 sessions;
   - test window: 63 sessions;
   - step: 63 sessions;
   - embargo: 5 sessions between training/validation and validation/test;
   - no randomized splits.
4. Descriptive conditional statistics computed separately inside each training fold and evaluated on
   untouched validation/test folds. Proposed outputs: count, win rate, mean/median net R, expectancy,
   profit factor, MFE/MAE quantiles, maximum drawdown, and bootstrap confidence intervals.
5. Versioned calibration reports comparing rule-confidence buckets with observed outcomes. Calibration
   remains research metadata and cannot overwrite or adjust rule confidence.
6. Deterministic similarity search using training-fold-only normalization. Proposed initial distance:

   ```text
   distance = sum(weight_i * abs(z_i(query) - z_i(candidate))) / sum(weight_i)
   ```

   Missing-pair dimensions are excluded; fewer than 60% available weighted dimensions rejects the
   comparison. Feature list and weights must live in a new immutable versioned configuration.
7. Append-only human review records using the existing verdict catalog. `UNCERTAIN` is excluded from
   truth labels. Consensus policy remains out of scope unless separately approved.
8. Deterministic CSV/Parquet/Markdown experiment exports with complete provenance and bias disclosures.

## Explicit exclusions

- no parameter optimization or automatic threshold search;
- no learned adjustment to Phase 1 decisions or confidence;
- no supervised model training;
- no options, portfolio allocation, brokerage, paper trading, or live data;
- no survivorship-biased present-day universe substitution;
- no claims of profitability or production readiness.

## Proposed modules and persistence

```text
src/trading_system/research/
  contracts.py
  folds.py
  universe.py
  statistics.py
  calibration.py
  similarity.py
  registry.py
  exports.py
```

New append-only tables are proposed for experiments, experiment folds, universe snapshots,
conditional-statistic results, calibration results, similarity queries/results, and human reviews.
Every result references its experiment, fold, source records, and canonical payload hash.

## Anti-leakage requirements

- fold boundaries use exchange sessions, never row counts across mixed symbols;
- normalization, imputation, bucketing, feature selection, and similarity candidates use training
  records only;
- labels must satisfy `label_available_at <= fold cutoff` before use;
- overlapping outcome horizons cannot cross from training into validation/test through the embargo;
- test folds remain unread until the experiment definition and validation-stage choices are frozen;
- repeated runs over identical inputs must produce identical canonical exports.

## Required validation

- fold boundary and embargo golden fixtures;
- point-in-time membership and delisting fixtures;
- label-availability and future-truncation tests;
- training-only normalization and calibration tests;
- deterministic similarity ranking, tie-break, and missing-dimension tests;
- registry immutability, restart, and conflicting-payload tests;
- architecture test proving research outputs cannot enter `decisions`;
- complete Ruff, strict mypy, pytest, and documented performance results.

## Approved decisions

Approval authorizes only the foundation above. The following defaults are accepted as tunable:

1. expanding-window `504/63/63`, 63-session step, and 5-session embargo;
2. the descriptive metric set and bootstrap confidence intervals;
3. weighted Manhattan similarity, 60% minimum dimension coverage, and config-defined weights;
4. append-only individual human reviews with consensus deferred;
5. strict separation preventing empirical outputs from changing Phase 1 decisions.
