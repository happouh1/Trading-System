CREATE TABLE IF NOT EXISTS prospective_point_in_time_evidence (
    evidence_id TEXT PRIMARY KEY,
    evidence_kind TEXT NOT NULL CHECK (evidence_kind IN ('PORTFOLIO', 'MARKET')),
    source_id TEXT NOT NULL,
    source_authority TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    known_at TEXT NOT NULL,
    source_bytes_hash TEXT NOT NULL,
    normalized_hash TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE(evidence_kind, source_id, source_revision, known_at)
);
CREATE TABLE IF NOT EXISTS prospective_evidence_receipts (
    decision_id TEXT PRIMARY KEY REFERENCES prospective_entry_outcomes(decision_id),
    receipt_id TEXT NOT NULL UNIQUE,
    known_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS prospective_evidence_no_update
BEFORE UPDATE ON prospective_point_in_time_evidence
BEGIN SELECT RAISE(ABORT, 'prospective point-in-time evidence is immutable'); END;
CREATE TRIGGER IF NOT EXISTS prospective_evidence_no_delete
BEFORE DELETE ON prospective_point_in_time_evidence
BEGIN SELECT RAISE(ABORT, 'prospective point-in-time evidence is immutable'); END;
CREATE TRIGGER IF NOT EXISTS prospective_evidence_receipts_no_update
BEFORE UPDATE ON prospective_evidence_receipts
BEGIN SELECT RAISE(ABORT, 'prospective evidence receipts are immutable'); END;
CREATE TRIGGER IF NOT EXISTS prospective_evidence_receipts_no_delete
BEFORE DELETE ON prospective_evidence_receipts
BEGIN SELECT RAISE(ABORT, 'prospective evidence receipts are immutable'); END;
