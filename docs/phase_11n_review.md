# Phase 11N signed verifier-bundle approval review

## Outcome

Phase 11N supplies a deterministic, offline approval record for the exact immutable Phase 11M
verifier-receipt bundle. It closes the repository-level independent-signoff format gap without
claiming that the signers, providers, or verifier software are operationally trusted.

## Implemented

- Bounded Ed25519 approval credentials with explicit operator-supplied roles.
- Requests binding the exact Phase 11M assessment/hash, Phase 11L identity, and complete ordered
  verifier receipt IDs/hashes.
- Signatures binding the request, bundle, credential, principal, role, and signing time.
- Deterministic `APPROVED`, `INCOMPLETE`, and `BLOCKED` states with distinct-principal enforcement.
- Append-only migration 103, hash-checked restart recovery, immutable update/delete protection, and
  a final offline control gate that revalidates the full Phase 11J–11N chain.

## Boundary

Approval roles and credentials are supplied by the operator because the specification does not name
the production quorum, issuer, custody model, or revocation service. No private key is generated or
loaded by runtime code; tests create ephemeral keys only. The feature makes no network request,
selects no provider, and grants no broker-write, trade-qualification, cohort-activation, or live
authority. Those choices remain explicitly unresolved in `docs/open_questions.md`.
