# Phase 6F Portable Offline Review-History Bundles v1

## Purpose

Phase 6F makes the complete local Phase 6E assertion history for one exact verified Phase 6D export
portable as deterministic JSON. It preserves source evidence and opinions without authenticating
reviewers, computing consensus, or granting authority.

## Bundle contract

Input names an export, the exact `VERIFIED` verification used by all included reviews, a causal
bundle timestamp, and source revision. The export manifest, verification, and every review payload
must be canonical, current-code, linked, and hash-intact. At least one review is required.

All reviews are retained, including superseded assertions. Review ID/hash pairs form a canonical
root. Active and summary-eligible counts are descriptive derivations only. The canonical envelope
contains no bundle wall-clock metadata, giving unchanged evidence identical content-addressed bytes.
The local path is contained beside the registry; publication is atomic and conflicting bytes fail.

## Verification contract

Read-only verification checks containment, regular-file status, bytes, hash, size, canonical JSON,
source identities and hashes, every review hash and link, same-reviewer supersession lineage, review
root, and counts. Successful and failed verification evidence is append-only.

## Explicit exclusions

- Authentication, qualification, independence, quorum, consensus, or production interpretation.
- Signatures, trusted timestamps, encryption, compression, or external transport.
- Mixed-verification review histories; they fail closed pending a versioned design.
- Mutation of source evidence or prior reviews.
- Network, credentials, notification, promotion, brokerage, orders, or live trading.

## Acceptance

- Unchanged evidence produces byte-identical content-addressed JSON.
- Missing reviews, mixed links, corrupt sources, or future timestamps fail closed.
- Superseded assertions remain present and descriptive counts are reproducible.
- File tampering and unsafe paths produce append-only failed verification.
- Migrations, restart behavior, CLI, Ruff, strict mypy, and the full suite pass.
