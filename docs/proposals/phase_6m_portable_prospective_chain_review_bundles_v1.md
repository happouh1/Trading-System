# Phase 6M proposal: portable prospective-chain review bundles v1

## Purpose

Phase 6M packages one exact verified Phase 6K prospective-chain export and its complete retained
Phase 6L review history into deterministic local bytes. It preserves evidence without interpreting
review verdicts.

## Canonical envelope

The envelope embeds the export manifest, the cited successful verification, and every stored
review for the export. It binds the export-manifest hash, verification-payload hash, prospective
chain root, and a canonical review root built from sorted `(review_id, payload_hash)` pairs.
Superseded reviews remain present. Active and summary-eligible counts are descriptive checks of the
embedded history.

## Publication and verification

Canonical UTF-8 JSON determines the SHA-256 filename in a configured registry-adjacent directory.
Publication is contained, atomic, restart safe, and conflict rejecting. A separate read-only
verification checks bytes, size, canonical schema, all embedded hashes and identities, chain and
review roots, supersession history, counts, and current code provenance. Verification appends
`VERIFIED` or `FAILED` evidence.

## Limitations

Bundles are local, unsigned, and unencrypted. Reviewer identities remain unauthenticated
assertions. Hash integrity is not trusted time, authorship, reviewer independence, consensus,
quality, production readiness, promotion, broker permission, or trading authorization.

## Exit criteria

Strict config, immutable contracts, migration parity, complete-history enforcement, deterministic
canonical bytes, atomic contained publication, causal timing, independent tamper detection,
restart recovery, CLI coverage, documentation, and full-suite success are required.
