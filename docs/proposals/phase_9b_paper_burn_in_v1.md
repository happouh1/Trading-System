# Phase 9B Proposal — Paper Burn-In Evidence

## Purpose

Measure paper-runtime stability over a fixed prospective window using immutable Phase 9A health
snapshots and thresholds chosen before observation begins.

## Controls

- Every threshold is operator-supplied and content-addressed.
- Protocol declaration precedes the observation window.
- Snapshot identity, session, time, persistence hash, and canonical root are verified.
- One assessment is permitted per protocol.
- Passing evidence carries no readiness or promotion authority.

## Exit criteria

1. Configuration rejects defaults and widened authority.
2. Evaluation is deterministic under input permutation.
3. Future, duplicate, cross-session, and out-of-window snapshots are rejected.
4. Complete passing, complete failing, and incomplete evidence are distinguished.
5. Persistence is append-only, restart-idempotent, and tamper-evident.
6. Root and packaged migrations match; Ruff, strict mypy, and pytest pass.
