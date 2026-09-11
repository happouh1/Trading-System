# Phase 9P Proposal — Signed Backup-Authorization Evidence v1

## Purpose

Cryptographically record that distinct reviewers attested to the exact proposed backup package. The
result is audit evidence and deliberately cannot execute the proposal.

## Signed package

The request binds the complete Phase 9O manifest hash, Phase 9N preflight hash, source hash, exact
target, proposed execution component, operator nonce, validity window, reviewer roles, and Phase 9P
configuration hash.

## Verification

- Only a review-ready Phase 9O manifest is accepted.
- Ed25519 credentials and attestations are checked at a supplied UTC evaluation time.
- Signatures and credentials must be valid inside the request window.
- Every required role must be present and each role must use a distinct principal.
- Altering any signed value invalidates the evidence.

## States

- `BACKUP_AUTHORIZATION_EVIDENCE_VERIFIED`
- `INCOMPLETE`
- `BLOCKED`

The verified state is intentionally not named `AUTHORIZED`. Replay-safe nonce consumption,
revocation, execution-component authentication, and backup mechanics remain unresolved.

## Exclusions

No executable capability, backup creation, directory creation, database write, migration, restore,
process launch, credential loading, network use, broker write, sandbox execution, or live trading.
