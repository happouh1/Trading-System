# Phase 2B review checklist

Phase 2B orchestrates deterministic evaluation without changing Phase 1 decisions.

Implemented scope includes append-only lifecycle transitions, declared cohorts, causal fold
assignments and exclusions, deterministic symbol holdouts, restart-safe stage recovery, conditional
statistics, strict versioned configuration, migrations, and the full research CLI workflow.

It excludes optimization, automated cohort selection, supervised learning, empirical-confidence
promotion, options, portfolio allocation, brokerage, and live execution.

Production point-in-time universe sourcing and multi-review consensus remain unresolved. Phase 2B
must not be tagged until installation, Ruff, strict mypy, pytest, and CI pass.

Local verification: source/test compilation, migration parity, diff checks, complete lifecycle command
workflow, conditional-result persistence, and human-review round-trip pass. The local environment could
not install Ruff, mypy, or pytest; GitHub CI remains the authoritative complete-suite validation.
