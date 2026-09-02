# Phase 6T — Artifact-trust security-review exports v1

## Purpose

Phase 6T produces a canonical local packet that a future security review can inspect when deciding
the unresolved Phase 6S trust policy. It packages exact Phase 6R and Phase 6S records without
altering them and independently verifies the exported bytes.

The packet is a handoff artifact, not a signature request sent to a provider. It is unsigned,
unencrypted, and local. No reviewer identity is authenticated and no policy answer, approval,
consensus, trusted timestamp, readiness result, or trading authority is created.

## Exact source chain

One packet contains exactly four canonical sources in lexical order:

1. the Phase 6R export manifest;
2. its successful Phase 6R verification;
3. the Phase 6S unresolved trust policy; and
4. the Phase 6S blocked signing request.

Before export, Phase 6T invokes Phase 6S restart validation. The envelope then validates all
cross-record IDs, source payload hashes, artifact and chain hashes, Phase 6R verified state, empty
failure reasons, nonpromotion state, and Phase 6S blocked/unsigned state. Export cannot predate the
signing request.

## Artifact and persistence rules

Canonical JSON bytes determine a SHA-256 content-addressed filename beneath the configured single
local directory. Publication is atomic, symlinks and escaping paths are rejected, and a conflicting
existing file fails. The manifest and each verification are append-only and retain code and config
versions. One signing request may produce one persisted export.

Independent verification rehashes the bytes, confirms canonical JSON, validates every embedded
payload hash and lineage relationship, reconstructs the chain root, and compares it with the
manifest. Failure records reasons without modifying or promoting the artifact.

## Deferred work

The packet contains no secret or key material and is not externally transmitted. Algorithm,
canonical signed bytes, key custody, signer identity, trusted timestamp, rotation/revocation,
recipient authorization, and receiving-verifier interoperability remain separately governed work.
