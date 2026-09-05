# Phase 7O — Verified reviewed-range catalogs v1

## Purpose

Phase 7O creates an append-only local catalog from an explicit caller-supplied set of pairs:
one Phase 7M reviewed-bundle export ID and one successful Phase 7N verification ID per entry.
It gives operators a deterministic inventory boundary without claiming that the inventory is
complete, ranked, approved, effective, or eligible for promotion.

## Inputs and causality

The input is strict JSON containing `catalog_name`, aware `cataloged_at`, nonempty
`source_revision`, and a nonempty `sources` array. Export IDs must be unique. Catalog time may not
precede any cited verification time. Time and membership are caller assertions and are not
authenticated.

For every source, construction and status both validate the persisted Phase 7M export, validate
the exact successful Phase 7N receipt and its canonical payload, rehash the current artifact, and
run complete Phase 7M plus nested Phase 7K verification. A failed receipt cannot be cataloged.

## Determinism and persistence

Entries are sorted by export ID. The catalog root hashes each entry's export ID, reviewed-bundle
ID, verification ID, artifact hash, review root, export payload hash, and verification payload
hash. Catalog identity additionally binds name, caller time, source revision, configuration hash,
and fixed disclosures. Parent and entry rows are inserted transactionally; exact retries are
idempotent and conflicts fail closed.

## Explicit exclusions

Phase 7O performs no discovery, completeness assessment, deduplication across catalogs, ranking,
vote aggregation, approval, efficacy inference, promotion, parameter selection, scoring, alerts,
options routing, brokerage action, network access, or live trading.

## Exit criteria

- Strict policy and strict input schemas reject authority expansion and malformed membership.
- Every member has an exact successful Phase 7N receipt and currently valid nested artifact.
- Catalog membership, ordering, root, identity, and persistence are deterministic.
- Status revalidates database payloads and current artifacts after restart.
- Exact retries are idempotent and tampering fails closed.
- Full lint, strict typing, and test suites pass.
