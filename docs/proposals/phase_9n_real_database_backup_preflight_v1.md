# Phase 9N Proposal — Read-Only Real-Database Backup Preflight v1

## Purpose

Determine whether the configured operator database and an explicitly supplied destination are ready
for later human review of a real backup. This phase does not create that backup.

## Inputs

- Versioned Phase 9N configuration and the existing 9K → 9J → 9I source chain.
- A Phase 9M request and matching `REVIEW_EVIDENCE_VERIFIED` assessment.
- Existing approved destination root and destination directory, expressed as canonical paths relative
  to the project root.
- Operator-supplied positive minimum-free-bytes value and quiescence-evidence SHA-256 identity.
- A UTC observation time within the reviewed maintenance window.

## Deterministic assessment

The preflight validates the review binding and current source hash, checks for SQLite sidecars before
opening the source, performs read-only integrity and foreign-key checks, validates destination
containment and type, checks capacity, and derives a content-addressed target name. Existing target
content must exactly match the current source or the result is blocked.

## Outcomes

- `READY_FOR_BACKUP_REVIEW`: checks pass and the target does not exist.
- `BACKUP_ALREADY_PRESENT`: checks pass and an exact target already exists.
- `BLOCKED`: at least one canonical blocker is present.

No outcome authorizes an action. A later phase must define independently authenticated authority,
backup mechanics, verification, retention, and recovery before a real backup can occur.

## Explicit exclusions

No directory creation, backup creation, database write, migration, restore promotion, process launch,
credential loading, network use, broker write, sandbox execution, or live trading.
