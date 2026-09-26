# Phase 11L credential governance review

## Outcome

Phase 11L adds an offline, fail-closed boundary for externally verified reviewer-credential
issuance, supersession, revocation, and trusted timestamp evidence. It governs the signed Phase 11K
review without changing Phase 11K signatures or granting execution authority.

## Implemented

- Strict, deterministic issuance, revocation, timestamp, and governed-assessment contracts.
- Required injected issuer, revocation, and timestamp verifier callbacks.
- Causal validation at an explicit UTC cutoff, including issuance-before-signing,
  signed-at/timestamped-at/received-at ordering, and immediate revocation/supersession blocking.
- Exact Phase 11K role scope and attestation binding.
- Append-only SQLite migration 101, hash-checked repositories, restart recovery, and immutable
  delete/update protection.
- A governed control path that requires exact stored Phase 11J, Phase 11K, and Phase 11L records.

## Deliberate boundary

The repository does not select or call a certificate authority, revocation service, hardware key
store, or timestamp authority. It does not load or create private keys. Provider-specific proof
validation must be supplied through the verifier interfaces and reviewed separately. A `VERIFIED`
result means those injected verifiers accepted the exact stored records at the cutoff; it does not
authenticate the underlying market observations, qualify a trade, activate a cohort, or authorize
a broker/live write.

## Exit criteria

The phase is complete when Ruff, strict mypy, focused governance tests, migration-copy checks, and
the full pytest suite pass. Operational provider selection, custody, quorum, and activation remain
open prerequisites.
