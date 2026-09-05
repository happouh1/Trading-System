# Phase 7M — portable reviewed range-evidence bundles

Phase 7M packages one exact verified Phase 7K artifact and the complete locally persisted Phase 7L
review history into deterministic ZIP_STORED bytes. The manifest separately binds the unchanged
source artifact hash and a canonical root of sorted `(annotation_id, payload_hash)` pairs.

Every review must reference the embedded bundle, report, and artifact hash. Export requires at
least one review. Offline verification checks fixed ZIP metadata and membership, canonical review
payloads and deterministic identities, the review root, and the complete nested Phase 7K bundle.
Artifact identity is path-independent; local export identity includes the destination path.

The package is unsigned and unencrypted. Reviewer identities and timestamps remain unauthenticated
caller assertions. Complete history is not consensus, approval, efficacy, or promotion, and the
phase has no network, scoring, alerts, options, brokerage, or live-trading authority.
