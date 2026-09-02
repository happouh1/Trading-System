# Phase 6K proposal: portable prospective-chain exports v1

## Purpose

Phase 6K makes the complete prospective-selection evidence chain portable as deterministic local
bytes without changing or interpreting any source record.

## Envelope

The canonical envelope includes the Phase 6I plan, each plan slot and binding, the Phase 6J
materialization, the Phase 6G catalog, and each catalog entry. Every source carries its stored
canonical payload hash. Sorted unique source names and hashes form the chain root.

## Publication and verification

The SHA-256 of canonical bytes determines a contained path beside the file-backed registry.
Publication is flushed, atomic, and conflict rejecting. Independent read-only verification checks
the exact bytes, size, schema, source hashes, current-code provenance, canonical ordering, count,
materialization ID, and root, then appends `VERIFIED` or `FAILED` evidence.

## Limitations

The artifact is local, unsigned, unencrypted, and not externally transported. Content integrity is
not identity, trusted time, reviewer independence, consensus, quality, readiness, promotion, broker
permission, or trading authorization.

## Exit criteria

Strict config, immutable contracts, migration parity, deterministic exports, containment, atomic
publication, tamper detection, restart recovery, CLI coverage, documentation, and full-suite success
are required.
