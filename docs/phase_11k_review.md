# Phase 11K Review — Signed Prospective Evidence Review

## Engineering outcome

Phase 11K adds offline Ed25519 review evidence for an exact Phase 11J corroboration receipt. An
operator supplies the required roles; no role or quorum is hidden in configuration. Every signature
binds the decision, receipt and request hashes, four evidence IDs and exact source-byte hashes,
bounded validity window, credential, principal, role, and signing time.

Evaluation is deterministic and input-order independent. Missing required roles produce
`INCOMPLETE`. An invalid signature, invalid window, or reused principal/role produces `BLOCKED`.
Only valid signatures by distinct principals for every requested role produce
`SIGNATURES_VERIFIED`. Migration 100 stores credentials, requests, attestations, and terminal
assessments as immutable records. The strictest prospective control path requires the exact stored
verified assessment as well as the stored Phase 11J receipt.

## Safety outcome

Verified signatures establish that named credential holders signed the exact local review request.
They do not prove that either upstream evidence provider created accurate data. Source authenticity,
control override, network, broker writes, trade qualification, cohort activation, and live trading
remain disabled by contract and configuration.

## Exit criteria

- Strict offline-only Phase 11K configuration.
- Ed25519 credential and signature validation over exact receipt scope.
- Bounded request and credential windows with future-signature rejection.
- Operator-supplied roles and distinct-principal enforcement.
- Stable `SIGNATURES_VERIFIED`, `INCOMPLETE`, and `BLOCKED` outcomes.
- Immutable migration 100 persistence and restart validation.
- Reviewed evidence-bound control refuses missing or changed assessments.
- Unit, integration, Ruff, strict mypy, and complete pytest checks pass.

## Remaining blockers

Credential issuance, key custody, rotation, revocation, trusted timestamps, reviewer-role policy, and
external provider attestation remain governance decisions. Phase 11K creates no prospective cohort,
real capital reservation, broker path, or live authorization.
