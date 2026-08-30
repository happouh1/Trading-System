# Phase 5E offline resilience proposal

## Objective

Phase 5E implements the release-backup requirement in specification Section 23.5 for SQLite
evidence. It creates content-addressed backups, records immutable manifests, performs isolated
restore drills, and reports retention eligibility. It is not a disaster-recovery service, backup
pruner, encryption system, remote store, or database-promotion mechanism.

## Backup boundary

The caller supplies a workspace-contained SQLite path, explicit known-at timestamp, and source
revision. The source is opened in SQLite read-only mode and copied with SQLite's online backup API,
which produces one consistent snapshot without copying WAL files independently. The completed
artifact must pass `PRAGMA quick_check` and `PRAGMA foreign_key_check` before publication.

The artifact filename is its SHA-256 digest. Existing identical content is reused; conflicting
bytes at a content-addressed path fail closed. The manifest records relative source and artifact
paths, byte count, artifact hash, source revision, code version, configuration hash, and integrity
results. The resilience registry must be separate from the source database.

## Restore drill

A restore drill resolves only an existing manifest and verifies the artifact hash before copying.
The copy goes to a configured isolated restore-drill directory under a deterministic identity. It
must retain the exact artifact hash and pass both SQLite checks. Verification is append-only and
`promoted=false`; no command can replace or activate an operational database.

## Retention reporting

At an explicit `as_of`, manifests newer than the configured 30-day initial minimum are protected.
Older manifests are `review_eligible`, not deleted. The threshold is **TUNABLE** and is an
operational placeholder, not an approved legal, regulatory, or business retention policy.

## Deliberately unavailable

- Artifact deletion, pruning, overwrite, compaction, or automatic lifecycle actions.
- Encryption, key management, credentials, network access, cloud/offsite replication, or alerts.
- Restore promotion, database replacement, failover, or mutation of source evidence.
- RPO/RTO guarantees, cross-host recovery, multi-database consistency groups, or live service
  coordination.
- Broker writes, market actions, options execution, or live trading.
