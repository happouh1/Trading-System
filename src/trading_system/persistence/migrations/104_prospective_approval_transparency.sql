CREATE TABLE IF NOT EXISTS prospective_approval_transparency_entries (
    entry_id TEXT PRIMARY KEY,
    sequence INTEGER NOT NULL UNIQUE CHECK (sequence >= 1),
    previous_entry_hash TEXT UNIQUE,
    approval_assessment_id TEXT NOT NULL UNIQUE
        REFERENCES prospective_verifier_approval_assessments(assessment_id),
    approval_request_id TEXT NOT NULL
        REFERENCES prospective_verifier_approval_requests(request_id),
    receipt_bound_assessment_id TEXT NOT NULL
        REFERENCES prospective_receipt_bound_governance_assessments(assessment_id),
    recorded_at TEXT NOT NULL, entry_hash TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
    CHECK ((sequence = 1 AND previous_entry_hash IS NULL)
        OR (sequence > 1 AND previous_entry_hash IS NOT NULL))
);
CREATE TRIGGER IF NOT EXISTS prospective_approval_transparency_no_update
BEFORE UPDATE ON prospective_approval_transparency_entries
BEGIN SELECT RAISE(ABORT, 'prospective approval transparency entries are immutable'); END;
CREATE TRIGGER IF NOT EXISTS prospective_approval_transparency_no_delete
BEFORE DELETE ON prospective_approval_transparency_entries
BEGIN SELECT RAISE(ABORT, 'prospective approval transparency entries are immutable'); END;
