CREATE TABLE IF NOT EXISTS range_evidence_bundle_reviews (
    annotation_id TEXT PRIMARY KEY,
    bundle_export_id TEXT NOT NULL REFERENCES range_evaluation_bundle_exports(bundle_export_id),
    bundle_id TEXT NOT NULL,
    report_id TEXT NOT NULL,
    reviewer_id TEXT NOT NULL,
    reviewed_at TEXT NOT NULL,
    verdict TEXT NOT NULL CHECK (verdict IN (
        'CONFIRMED_CONTENT_INTEGRITY',
        'PARTIAL_CONTENT_INTEGRITY',
        'DISPUTED_CONTENT_INTEGRITY',
        'UNCERTAIN_CONTENT_INTEGRITY'
    )),
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE (bundle_export_id, reviewer_id, reviewed_at)
);

CREATE INDEX IF NOT EXISTS idx_range_evidence_bundle_reviews_bundle
ON range_evidence_bundle_reviews(bundle_id, reviewed_at, annotation_id);
