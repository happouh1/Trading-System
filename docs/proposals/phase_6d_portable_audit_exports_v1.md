# Phase 6D Portable Offline Audit Exports v1

## Purpose

Phase 6D makes one persisted Phase 6C observation-audit packet portable as deterministic local
JSON and verifies that file independently. It does not reinterpret the packet, reconciliation, or
campaign result and grants no operational or trading authority.

## Export contract

The input names exactly one packet, a timezone-aware export timestamp no earlier than packet
creation, and a source revision. Export revalidates the packet's canonical payload and current code
version, every child artifact payload/hash, embedded artifact identities, and the artifact-root
hash. Failure occurs before publication.

The envelope contains its schema version, packet identity and payload hash, retained reconciliation
and campaign statuses, the parsed packet, and artifacts sorted by name. It is serialized as UTF-8
canonical JSON. The file name is the SHA-256 of those exact bytes, so re-exporting unchanged source
evidence produces identical bytes and the same file path.

Files are confined to `observation_audit_exports` beside the registry database. Absolute paths,
parent traversal, symlinks, conflicting pre-existing bytes, and in-memory registries fail closed.
Publication writes and flushes a temporary file in the destination directory before atomic replace.

## Verification contract

Verification loads only the persisted manifest and local file. It checks containment, regular-file
status, exact byte count and SHA-256, canonical JSON, envelope schema, embedded packet hash,
artifact payload hashes, artifact order, artifact root, and count. A failed check creates immutable
`FAILED` evidence with canonical reasons. Verification never repairs, deletes, replaces, promotes,
signs, encrypts, transmits, or submits anything.

## Explicit exclusions

- Digital signatures, trusted timestamps, key custody, or external attestation.
- Encryption, compression, archival packaging, removable media, or external transfer.
- Retention/deletion policy or source-database snapshots.
- Production-readiness conclusions or campaign-success thresholds.
- Network, credential, notification, brokerage, live-trading, or promotion authority.

## Acceptance

- Identical source evidence yields byte-identical content-addressed JSON.
- Source payload tampering prevents export.
- File tampering produces persisted `FAILED` verification.
- Path traversal cannot cause an outside read or write.
- Source reconciliation and campaign statuses remain unchanged.
- Migrations, restart behavior, CLI behavior, Ruff, strict mypy, and the complete test suite pass.
