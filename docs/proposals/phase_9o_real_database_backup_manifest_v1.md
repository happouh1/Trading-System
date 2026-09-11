# Phase 9O Proposal — Offline Real-Database Backup Manifest v1

## Purpose

Create deterministic review material describing the exact backup that could be requested after a
successful Phase 9N preflight. This phase cannot authorize or execute the operation.

## Bound evidence

The manifest includes the canonical Phase 9N preflight hash, source identity, source size and hash,
content-addressed target, operator-supplied policy hashes, proposed execution-component identity,
and UTC creation time.

## Fixed proposed procedure

1. Recheck the source hash.
2. Use SQLite's backup API to an exclusively created new file.
3. Recheck the source hash.
4. Run target `quick_check` and `foreign_key_check`.
5. Require the target hash to match the captured backup identity.
6. Perform the separately defined isolated restore test.

The sequence is descriptive only. No code in Phase 9O carries it out.

## States

- `READY_FOR_AUTHORIZATION_REVIEW`
- `EXISTING_BACKUP_REVIEW_REQUIRED`
- `BLOCKED`

## Exclusions

No backup authorization, directory creation, backup creation, database write, migration, restore,
process launch, credential loading, network use, broker write, sandbox execution, or live trading.
