# Phase 7Q — Reviewed-catalog export verification receipts v1

## Purpose

Phase 7Q records append-only local integrity-check attempts for exact Phase 7P catalog exports.
It preserves both successful and failed checks so later damage does not erase earlier evidence.

## Verification

An attempt references one persisted Phase 7P export and uses a caller-supplied timezone-aware
verification time. The time cannot precede the source Phase 7O catalog time and is explicitly not
trusted. The checker reads and hashes the current manifest bytes, validates the Phase 7P receipt,
regenerates the expected manifest, and repeats the complete Phase 7O, Phase 7N, Phase 7M, and
nested Phase 7K verification chain.

Success records `VERIFIED` with matching expected and actual hashes and no reasons. A missing,
changed, malformed, configuration-mismatched, or upstream-invalid export records `FAILED` with the
stable reason `REVIEWED_CATALOG_EXPORT_VERIFICATION_FAILED`. Exception and path details are not
placed in the receipt.

## Persistence and determinism

Receipt identity binds export/catalog identity, caller time, result, expected and actual hashes,
reason, and all five configuration hashes. Records are append-only and chronologically ordered.
An exact retry is idempotent; a new time creates a distinct historical attempt.

## Explicit exclusions

Phase 7Q performs no scheduling, network access, remote attestation, signature, authenticated
identity, trusted timestamp, completeness claim, ranking, consensus, approval, efficacy inference,
promotion, scoring, alerts, options routing, broker write, or live trading.

## Exit criteria

- Intact Phase 7P and complete upstream evidence produce `VERIFIED`.
- Changed, missing, or invalid evidence produces an append-only `FAILED` receipt.
- Exact retries are deterministic and idempotent; distinct attempts retain history.
- Status validates canonical receipt history and fails closed on database corruption.
- Full lint, strict typing, and test suites pass.
