# Phase 9Q Proposal — Test-Only Authorized-Backup Rehearsal v1

## Purpose

Exercise the proposed backup and restore-verification path end to end without accepting or changing
the real operator database.

## Boundary

Sources must be regular SQLite fixtures beneath `fixtures/backup-authorization-rehearsal` and carry
a `TEST_ONLY_` revision. Outputs exist only beneath the ignored `.p9q-backup-rehearsal` directory.

## Procedure

1. Validate the exact Phase 9O manifest and verified Phase 9P evidence within its time window.
2. Reject SQLite journal, SHM, and WAL sidecars before opening the source.
3. Hash and open the source read-only.
4. Create an isolated backup with SQLite's backup API.
5. Restore that backup into another isolated copy with the same API.
6. Verify both copies with `quick_check`, `foreign_key_check`, row counts, and canonical logical data.
7. Recheck the source hash and publish a deterministic test-only result.

Restart reuses an existing deterministic artifact set only when every artifact hash matches.

## Exclusions

No real database source, executable authorization, production backup, source write, migration,
restore promotion, process launch, credential loading, network use, broker write, or trading.
