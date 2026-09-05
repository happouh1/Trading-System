# Phase 7U incident-notification export verification receipts v1

## Purpose

Phase 7U records append-only local evidence that a persisted Phase 7T notification export either
passed or failed exact-byte and full-source verification at a caller-asserted, timezone-aware time.
It preserves every result; a later success does not erase an earlier failure.

## Deterministic rules

1. Load the persisted Phase 7T receipt and its latest Phase 7R incident-event time.
2. Reject a naive timestamp or one earlier than that incident history.
3. Read the path bound into the Phase 7T receipt and calculate SHA-256 over the exact bytes.
4. Re-run Phase 7T verification, including its validated Phase 7S source chain.
5. Append `VERIFIED` only when every check succeeds. Otherwise append `FAILED` with the stable
   reason `INCIDENT_NOTIFICATION_EXPORT_VERIFICATION_FAILED` and the observed hash when readable.
6. Derive the receipt ID from all source IDs, hashes, configurations, result fields, and time.
7. Treat exact retries as idempotent and conflicting stored data as corruption.

## Authority boundary

This phase never changes the file, quarantines it, sends it, retries delivery, escalates an
incident, authenticates a person or recipient, grants approval, promotes research, scores a
strategy, routes an option, writes to a broker, or trades live. Its timestamp is caller asserted,
and its hash is not a digital signature.
