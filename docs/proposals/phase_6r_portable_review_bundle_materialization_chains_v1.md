# Phase 6R portable review-bundle materialization chains v1

Phase 6R exports one exact, fully revalidated Phase 6Q materialization chain as canonical local
JSON. The envelope embeds the Phase 6P plan, every child slot and binding, the derived Phase 6O
plan and every child source, the derived Phase 6N catalog and every child entry, and the Phase 6Q
materialization. Each embedded payload retains its stored canonical payload hash.

Source names are unique and lexically ordered. The ordered `(name, payload_hash)` pairs form a
chain root. Canonical envelope bytes determine a SHA-256 content-addressed filename inside one
configured relative directory. Publication uses a flushed same-directory temporary file and atomic
replacement; an existing path with different bytes is rejected.

Export first invokes complete Phase 6Q status validation, which recursively revalidates the Phase
6P, Phase 6O, and Phase 6N records and Phase 6M artifacts referenced by the catalog. Export time
cannot precede the Phase 6N catalog time. Independent verification reads only the artifact and its
manifest, rehashes the file, validates canonical embedded payload hashes and ordering, rebuilds the
chain root, and checks the manifest binding. Success and failure are append-only evidence.

The artifact is local, unsigned, unencrypted, and unauthenticated. A content hash is not a digital
signature or trusted timestamp. Export and verification calculate no consensus, selection quality,
or readiness and grant no promotion, network, brokerage, or live-trading authority.

