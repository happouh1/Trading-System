# Phase 6L proposal: independent prospective-chain reviews v1

## Purpose

Phase 6L records an independent reviewer's asserted assessment of one exact, successfully verified
Phase 6K prospective-chain export. It does not alter the export, its verification, or any source
evidence.

## Review evidence

Each immutable assertion binds the exact export ID, verification ID, export-manifest payload hash,
verification payload hash, and prospective chain-root hash. Verdicts are `CONFIRMED`, `REJECTED`,
`PARTIAL`, or `UNCERTAIN`. Reason codes are sorted and deduplicated before identity calculation.
`UNCERTAIN` remains visible but is excluded from descriptive summary-eligible counts.

Reviewer IDs are caller assertions, not authenticated identities. A later assertion may supersede
only an earlier assertion by the same asserted reviewer for the same export, and the original
record remains immutable and visible.

## Validation

Creation revalidates canonical stored manifest and verification payloads, exact identity links,
current code provenance, a `VERIFIED` result with no failure reasons, matching expected and actual
artifact hashes, and a review timestamp no earlier than verification. Duplicate writes are
idempotent; conflicting writes fail.

## Limitations

Counts describe active local assertions only. They are not reviewer authentication, independence
proof, consensus, evidence quality, statistical validation, production readiness, promotion,
broker permission, or trading authorization. Phase 6L performs no network or broker operations.

## Exit criteria

Strict no-authority configuration, immutable contracts, migration parity, causal source
revalidation, append-only supersession, restart safety, corruption rejection, CLI coverage,
documentation, and full-suite success are required.
