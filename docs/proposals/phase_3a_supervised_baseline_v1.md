# Proposed Phase 3A supervised baseline evaluation v1

Status: **APPROVED AND IMPLEMENTED — VALIDATION PENDING**

## Purpose

Phase 3A evaluates whether a simple supervised baseline contains out-of-sample information beyond the
existing deterministic rules. Model outputs remain separate empirical evidence. They cannot modify
Phase 1 confidence, decisions, trade plans, sizing, execution, or persisted historical predictions.

This phase is model evaluation, not automated trading and not proof of an investable edge.

## Proposed bounded scope

1. A versioned model-experiment contract referencing one frozen Phase 2B experiment, its folds,
   immutable dataset hash, feature schema, target definition, estimator specification, random seed,
   dependency versions, and code version.
2. A binary target derived only from versioned, available outcome records. Proposed initial target:

   ```text
   positive = generic outcome reached MFE >= 2R before MAE >= 1R
   negative = generic outcome failed that rule within its declared horizon
   ```

   `UNCERTAIN`, unlabeled, conflicting, unavailable-at-cutoff, or nonfinite rows are excluded with
   explicit reason records. Pattern-specific targets remain deferred until their label catalog is
   complete and separately approved.
3. A fixed initial feature allowlist drawn only from causal Phase 1 observation fields:

   - pattern quality and confirmation/acceptance score;
   - trend score and multi-timeframe alignment;
   - RVOL20, CLV, signed CLV, and body fraction;
   - ADR utilization, runway ADR, stop distance ADR, and location score;
   - confluence score, base duration/width/quality, and reclaim velocity when available;
   - declared categorical pattern, direction, timeframe, and regime values.

   Identifiers, timestamps, prices, future outcomes, reviews, trade exits, MFE/MAE, and post-decision
   fields are forbidden features. Missingness indicators MAY accompany allowed causal features.
4. Two immutable baselines:

   - prevalence-only `DummyClassifier` as the mandatory reference;
   - L2-regularized logistic regression as the only trainable Phase 3A estimator.

   Proposed logistic defaults (**TUNABLE**): `C=1.0`, `max_iter=2000`, balanced class weights, fixed
   seed, deterministic single-process fitting, and no hyperparameter search.
5. Fold-local preprocessing fitted on training rows only:

   - continuous median imputation plus explicit missingness indicators;
   - standard scaling for continuous inputs;
   - one-hot encoding for declared categorical inputs with unknown categories ignored;
   - no full-sample preprocessing, target encoding, feature selection, or dimensionality reduction.
6. Existing Phase 2B chronological train/validation/test boundaries, embargoes, label cutoffs,
   point-in-time universes, and frozen-test barrier remain mandatory. Test fitting is prohibited.
7. Validation-stage selection is limited to comparing the fixed logistic model against the dummy
   baseline. Any feature, target, or estimator change creates a new child experiment before test is
   opened. Test results are append-only and may not trigger another test under the same lineage.
8. Separate model calibration fitted on training predictions only. Proposed method: logistic sigmoid
   calibration when both classes and enough samples exist; otherwise calibration is unavailable and
   disclosed. Rule confidence is never used as a writable target and is never overwritten.
9. Per-fold and aggregate reporting:

   - eligible/excluded counts and class prevalence;
   - ROC AUC and average precision;
   - log loss and Brier score;
   - calibration bins and expected calibration error;
   - threshold-free comparison against the dummy baseline;
   - fixed diagnostic thresholds `0.50`, `0.60`, and `0.70` for precision, recall, specificity,
     confusion matrix, and coverage (**TUNABLE diagnostics only**);
   - bootstrap confidence intervals using the experiment seed;
   - pattern/timeframe/regime breakdowns marked `INSUFFICIENT_SAMPLE` under the approved count of 30.
10. Immutable model artifacts containing estimator bytes, preprocessing definition, feature order,
    training-fold identity, dependency lock, canonical manifest, artifact hash, and creation time.
    Deserialization is permitted only for artifacts created by this repository and matching the
    recorded hash and dependency policy.
11. Append-only prediction records with `model_probability`, model/version identity, source
    observation ID, fold/partition, known-at time, and payload hash. They are stored outside Phase 1
    decisions and are inaccessible to `decisions`, `risk`, and `execution_sim`.
12. CLI commands for defining, validating, fitting training folds, evaluating validation/test folds,
    freezing, reporting, explaining a model prediction, and verifying artifact hashes.

## Proposed model lifecycle

```text
DEFINED
  -> TRAINED
  -> VALIDATION_EVALUATED
  -> FROZEN
  -> TEST_EVALUATED
  -> COMPLETE
```

Every transition is append-only. Test evaluation requires the exact frozen feature, target,
preprocessing, estimator, calibration, dependency, dataset, and fold hashes.

## Persistence additions

Proposed append-only tables:

- `model_experiments`;
- `model_experiment_lineage`;
- `model_transitions`;
- `model_fold_artifacts`;
- `model_predictions`;
- `model_metrics`;
- `model_exclusions`;
- `model_reports`.

Model artifacts SHOULD be stored as content-addressed files with their hashes and paths registered in
SQLite. Large binary artifacts MUST NOT be embedded in decision or observation payloads.

## Anti-leakage and safety requirements

- preprocessing and calibration fit on each training fold only;
- labels must be available at the partition cutoff;
- duplicate observations cannot cross partitions within a fold;
- outcome horizons crossing a cutoff remain excluded under the Phase 2 embargo/availability policy;
- no random row split and no full-sample normalization;
- feature schemas reject forbidden or unknown fields;
- model probabilities never become rule confidence or trade gates;
- model packages cannot be imported by `decisions`, `risk`, or `execution_sim`;
- model artifacts are treated as untrusted unless their manifest and hash verify;
- all reports disclose survivorship, revision, selection, calibration, and profitability limitations.

## Required tests

- training-only imputation, scaling, encoding, and calibration traps;
- future-label, outcome-feature, identifier-feature, and post-trade-feature rejection;
- deterministic fit/prediction equivalence for identical inputs and dependency versions;
- dummy/logistic golden fixtures with fixed expected probabilities within declared tolerance;
- single-class and insufficient-sample behavior;
- unseen categorical value and missing-feature behavior;
- lifecycle freeze/test enforcement and child-lineage tests;
- artifact hash tampering and incompatible-version rejection;
- append-only prediction/result persistence and restart recovery;
- architecture tests preventing model imports into Phase 1 authority paths;
- complete installation, Ruff, strict mypy, pytest, and CI validation.

## Explicit exclusions

- hyperparameter optimization, grid/random/Bayesian search, feature mining, or automated selection;
- tree ensembles, boosting, neural networks, embeddings, vision, NLP, or LLM predictions;
- empirical probability controlling entries, exits, confidence, sizing, or execution;
- portfolio construction, options modeling, brokerage, paper/live trading, or order routing;
- online learning, active learning, automatic pattern discovery, or model promotion;
- profitability claims or production deployment.

## Approval decisions required

Approval would authorize only the bounded research baseline above. Please approve or amend:

1. generic 2R-before-1R binary outcome target and exclusion policy;
2. dummy classifier plus fixed L2 logistic regression, with no hyperparameter search;
3. the causal feature allowlist and forbidden-field policy;
4. training-only preprocessing and optional sigmoid calibration;
5. proposed evaluation metrics and diagnostic thresholds;
6. content-addressed artifacts and append-only model predictions;
7. absolute separation from Phase 1 decisions and trading authority.
