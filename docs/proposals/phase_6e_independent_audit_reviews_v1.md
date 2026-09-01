# Phase 6E Offline Audit Review Assertions v1

## Purpose

Phase 6E records immutable human review assertions about one verified Phase 6D export. It keeps
those opinions separate from source evidence and does not claim that the asserted reviewer is
authenticated, independent, qualified, or part of a consensus process.

## Source validation

A review names exactly one export and one verification. Creation revalidates both canonical
payload hashes, their exact link, current package version, `VERIFIED` status, empty verification
reasons, equal expected and actual artifact hashes, and `promoted=false`. The timezone-aware review
timestamp cannot precede verification.

## Review contract

The fixed verdicts are `CONFIRMED`, `REJECTED`, `PARTIAL`, and `UNCERTAIN`. Reason codes and
disclosures are sorted and deduplicated. Notes are retained verbatim. `UNCERTAIN` is preserved but
excluded from summary-eligible counts.

Reviewer identity is an unauthenticated assertion. No minimum reviewer count, quorum, consensus,
weight, reliability estimate, or production threshold is defined. A superseding review is a new
append-only record and may reference only an earlier review by the same asserted reviewer for the
same export at an earlier timestamp. All prior rows remain queryable.

## Explicit exclusions

- Authentication, qualification, independence, conflict checks, signatures, or trusted time.
- Consensus, quorum, voting, weighting, performance thresholds, or production interpretation.
- Mutation of exports, verifications, packets, campaigns, plans, or other source evidence.
- Network, credential, notification, promotion, brokerage, order, or live-trading authority.
- Portable review bundles, encryption, external transfer, or legal-retention policy.

## Acceptance

- Only an exact, canonically intact, current-code `VERIFIED` export can receive a review.
- Reviews and supersessions are causal, deterministic, append-only, and restart-safe.
- Supersession cannot cross an export or asserted reviewer.
- `UNCERTAIN` remains visible and is excluded from summary-eligible counts.
- Tampered or failed verification evidence fails closed.
- Root and packaged migrations are byte-identical.
- CLI, migration, restart, supersession, tamper, Ruff, strict mypy, and full pytest checks pass.
