CREATE TABLE IF NOT EXISTS prospective_control_assessments (
    decision_id TEXT PRIMARY KEY REFERENCES prospective_entry_outcomes(decision_id),
    known_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('CONTROL_APPROVED', 'CONTROL_REJECTED_PORTFOLIO')
    ),
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS prospective_controls_no_update
BEFORE UPDATE ON prospective_control_assessments
BEGIN SELECT RAISE(ABORT, 'prospective control assessments are immutable'); END;
CREATE TRIGGER IF NOT EXISTS prospective_controls_no_delete
BEFORE DELETE ON prospective_control_assessments
BEGIN SELECT RAISE(ABORT, 'prospective control assessments are immutable'); END;
