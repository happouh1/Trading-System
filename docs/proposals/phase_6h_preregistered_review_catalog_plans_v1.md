# Phase 6H proposal: preregistered review-catalog plans v1

## Purpose

Phase 6G makes explicit catalogs but lets callers select their membership at catalog creation.
Phase 6H adds an earlier immutable record of the intended catalog name and exact bundle-verification
pairs, then reconciles the resulting catalog against that record.

## Scope

The phase is an offline evidence-control layer. It adds immutable contracts, strict configuration,
SQLite persistence, CLI operations, and deterministic tests. It does not create bundles or
catalogs, discover evidence, schedule work, authenticate reviewers, calculate consensus, set
thresholds, promote artifacts, access a broker, or trade.

## Plan construction

A caller supplies:

- an exact catalog name;
- a timezone-aware registration timestamp;
- a nonempty list of exact `(bundle_id, verification_id)` pairs;
- a source revision.

Bundle IDs must be unique. Input order is normalized. A canonical source-root hash binds the whole
set, and the plan ID binds its name, timestamp, sources, root, provenance, code version,
disclosures, and configuration hash. Planned source identities need not exist yet.

## Reconciliation

A caller supplies the plan ID, requested catalog ID, timezone-aware reconciliation timestamp, and
source revision. The registry re-hashes canonical plan evidence, reads the requested Phase 6G
catalog when present, requires current-code provenance and a catalog timestamp strictly later than
registration, and compares the exact name and source map.

Statuses are:

- `MATCHED`: exact name and source membership agree and evidence is intact;
- `DEVIATION`: intact evidence differs in name or membership;
- `MISSING`: the requested catalog does not exist;
- `CORRUPT`: canonical integrity, code provenance, or causal timestamp validation fails.

Reason codes preserve each detected difference. Results are immutable and restart-idempotent.

## Interpretation boundary

This design freezes only the later catalog denominator. Content-derived bundle identities may be
available only after the corresponding review history is known. A caller can therefore select
favorable bundle identities and then register them before cataloging. `MATCHED` must never be
described as proof of unbiased initial selection, catalog completeness, reviewer independence,
consensus, statistical evidence, production readiness, or trading authorization.

## Exit criteria

- strict authority-denying configuration validates and hashes deterministically;
- plans and reconciliations are immutable and canonical;
- future or missing source identities can be preregistered;
- exact matches, deviations, missing catalogs, and corrupt causal evidence are distinguished;
- migration copies are identical and restart behavior is idempotent;
- CLI paths expose explicit non-authority fields;
- installation, Ruff, strict mypy, and the complete pytest suite pass.
