# Phase 3A review

## Scope

Phase 3A implements the approved isolated supervised baseline. It does not optimize trading rules,
select securities, simulate options, connect to brokers, or modify deterministic trade decisions.

## Implemented controls

- immutable experiments and append-only lifecycle transitions;
- exact data, configuration, feature, target, estimator, code, and dependency provenance;
- causal feature allowlisting and explicit exclusions;
- prevalence dummy and fixed L2 logistic baselines;
- train-fold-only preprocessing and optional sigmoid calibration;
- validation, exact-manifest freeze, untouched-test, and completion gates;
- content-addressed, hash-verified fitted artifacts;
- append-only probabilities, metrics, exclusions, reports, and lineage;
- deterministic diagnostics and bootstrap intervals;
- architecture tests excluding model imports from decisions, risk, and execution simulation.

## Deferred

Optimization, advanced estimators, pattern-specific targets, portfolio conclusions, model promotion,
brokerage connectivity, live inference, and model authority over trading remain outside Phase 3A.
Open question 48 requires a separate future proposal.

## Exit evidence

Local source compilation, Ruff, strict mypy, pytest, migration parity, and repository-diff checks are
recorded in the implementation handoff. GitHub CI remains the authoritative clean-environment check.
