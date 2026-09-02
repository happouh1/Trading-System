# Phase 6N verified prospective-review catalogs v1

## Scope

Phase 6N creates deterministic, append-only catalogs from an explicit caller-supplied set of
independently `VERIFIED` Phase 6M prospective-chain review bundles. It is an offline evidence
organization layer. It does not select investments, rank evidence, calculate consensus, promote a
configuration, claim production readiness, access a broker, or enable live trading.

## Deterministic input and validation

The caller supplies a nonempty catalog name, timezone-aware catalog time, source revision, and a
nonempty list of exact `(bundle_id, verification_id)` pairs. Bundle IDs must be unique. Input order
is normalized by bundle and verification ID before construction.

For every pair the registry requires:

- canonical stored Phase 6M manifest and verification payloads with matching payload hashes;
- an exact verification-to-bundle link and `VERIFIED` status with no failure reasons;
- matching expected, actual, and manifest artifact hashes;
- fixed `promoted=false` and current package-code provenance;
- manifest chain and review roots matching their indexed database values;
- a contained, regular, non-symlink local artifact whose bytes rehash to the manifest hash; and
- a catalog timestamp no earlier than the cited verification timestamp.

Any missing, corrupt, stale, unsafe, mismatched, or failed source is rejected. No missing bundle is
silently omitted.

## Identity and roots

Each entry retains the bundle ID, verification ID, artifact hash, both stored payload hashes,
prospective chain root, review root, review counts, and verification time. Canonical entry order is
ascending bundle ID. The catalog root hashes the ordered identity and root tuple for every entry.
Catalog identity includes its name, time, entries, root, source revision, package version,
disclosures, and strict configuration hash.

## Persistence and recovery

Migration `041_phase_6n_prospective_chain_review_catalogs.sql` adds one immutable catalog table and
one immutable child-entry table. Parent and children are inserted transactionally. Re-inserting
identical evidence is idempotent; an identity collision with different content fails closed.
Status reconstructs canonical payloads and validates child completeness and hashes after restart.

## Explicit limitations

Catalog membership is caller-declared and is not a preregistered denominator. Reviewer identities
remain assertions. Counts are descriptive sums, not votes, quorum, agreement, quality, performance,
or readiness measures. Phase 6N defines no minimum sample size or production threshold.
