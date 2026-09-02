# Phase 6G Verified Review-Bundle Catalogs v1

## Purpose

Phase 6G records a deterministic catalog of explicitly selected verified Phase 6F bundles. It
supports local evidence inventory without discovering a population, aggregating verdicts,
calculating consensus, ranking bundles, or making readiness claims.

## Catalog contract

Input supplies a catalog name, causal timestamp, nonempty exact bundle/verification pairs, and
source revision. Duplicate bundle IDs fail and order is normalized. Each source manifest and exact
verification must be canonical, current-code, linked, `VERIFIED`, reason-free, unpromoted, and have
matching expected/actual artifact hashes.

The local bundle file is independently re-hashed at catalog time. Every entry retains exact source
hashes, review-root hash, descriptive counts, and verification time. Ordered source identities and
hashes form the catalog root. Parent and child rows are inserted transactionally and append-only.

## Explicit exclusions

- Automatic discovery or a claim that caller selection is complete or unbiased.
- Verdict synthesis, reviewer authentication, ranking, quorum, consensus, or statistics.
- File export, signing, trusted time, encryption, external transport, or notification.
- Production readiness, promotion, brokerage, orders, or live trading.

## Acceptance

- Input permutations yield identical catalogs; duplicate bundle IDs fail.
- Unknown, failed, future, corrupt, missing, unsafe, or changed evidence fails closed.
- Identical creation is restart-safe and child rows remain canonical and complete.
- Root and packaged migrations match; CLI, Ruff, strict mypy, and the full suite pass.
