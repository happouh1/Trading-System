# Phase 5F Offline Release Evidence v1

## Purpose

Phase 5F closes the current offline operations sequence with a deterministic evidence bundle. The
bundle answers one narrow question: are the exact named Phase 5A-E records present, causal,
hash-valid, correctly linked, and in their reviewed terminal statuses?

It does not answer whether data is fresh, strategies are profitable, infrastructure is
production-grade, capital is approved, or trading should occur.

## Inputs

- one explicit timezone-aware `as_of`;
- readiness manifest ID;
- monitor report ID;
- control snapshot ID;
- run request ID;
- backup manifest ID;
- restore verification ID;
- nonempty source revision;
- versioned `config/operations.phase5f.v1.yaml`.

## Deterministic evaluation

The evaluator requires fixed statuses: `READY` readiness, `READY` monitor, `READY` controls,
latest `SUCCEEDED` attempt, and `VERIFIED` restore. The control snapshot must reference the named
request, while the restore must reference the named backup. Readiness and backup evidence must use
the active package version. Each stored payload is canonically re-hashed, and every evidence time
must be no later than `as_of`.

Any failure yields `INCOMPLETE` plus sorted reason codes. The evidence that was found is still
recorded through canonical evidence-name/hash pairs. Missing evidence is never treated as success.

## Persistence and restart behavior

`ReleaseEvidenceBundle` is immutable. Its deterministic identifier covers the exact identities,
as-of, hashes, reasons, disclosures, revision, package version, and config hash. Re-inserting an
identical bundle is idempotent; conflicting content under the same ID fails closed.

## Authority boundary

The configuration rejects network, credential, notification, broker-write, live-trading, and
production-readiness authority. The CLI reads one local SQLite registry and appends only the
resulting bundle. It cannot run jobs, promote restores, release kill switches, or submit orders.

Every bundle discloses `FRESHNESS_NOT_ASSESSED`, `OFFLINE_PERSISTED_EVIDENCE_ONLY`,
`NO_BROKER_OR_LIVE_TRADING_AUTHORITY`, and `NOT_A_PRODUCTION_READINESS_CLAIM`.

## Acceptance criteria

1. Strict configuration rejects any expanded authority or weakened consistency rule.
2. A valid seeded Phase 5A-E chain produces a deterministic `COMPLETE` bundle.
3. Missing, future, status-invalid, link-invalid, code-invalid, and hash-invalid evidence produces
   `INCOMPLETE` with explicit canonical reasons.
4. Persistence is append-only, idempotent, restart-safe, and covered by migration parity tests.
5. CLI creation and status lookup expose all non-authority flags.
6. Installation, Ruff, strict mypy, and the complete pytest suite pass.
