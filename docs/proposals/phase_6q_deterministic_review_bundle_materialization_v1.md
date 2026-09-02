# Phase 6Q deterministic review-bundle materialization v1

Phase 6Q converts one complete Phase 6P prospective review-bundle plan into one exact Phase 6O
catalog plan and one exact Phase 6N catalog. The caller identifies the Phase 6P plan and supplies
causal timestamps and provenance only. Catalog name and bundle-verification membership derive
exclusively from the frozen slots and their bindings.

Bindings are read in canonical Phase 6P slot order. Their ordered slot, bundle, and verification
identities form a binding root. Phase 6O canonicalizes the derived bundle-verification sources and
records its source root at `materialized_at`; Phase 6N independently revalidates the same sources
and records its catalog root at the strictly later `cataloged_at`.

The append-only materialization binds all three records, all four roots, slot count, timestamps,
source revision, code version, disclosures, and configuration hash. Unique constraints permit one
materialization per Phase 6P plan, Phase 6O plan, and Phase 6N catalog. Exact retries are
idempotent; conflicting retries fail before creating new downstream evidence. A failure after the
Phase 6O plan is stored but before Phase 6N completes can be retried with the same input.

Status revalidates the complete Phase 6P plan and bindings, the Phase 6O plan, the Phase 6N catalog,
membership, roots, child records, artifacts, canonical payloads, current code provenance, and
configuration hashes. It does not assess timing compliance against expected slot times because no
tolerance or missed-window policy exists.

Materialization is local evidence plumbing. It authenticates no identity or timestamp, calculates
no consensus, asserts no selection quality or production readiness, performs no promotion or
network operation, and grants no brokerage or live-trading authority.

