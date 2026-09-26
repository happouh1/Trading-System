CREATE TABLE IF NOT EXISTS prospective_external_verification_receipts (
    receipt_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN (
        'CREDENTIAL_ISSUANCE','CREDENTIAL_REVOCATION','TRUSTED_TIMESTAMP'
    )),
    subject_id TEXT NOT NULL, verifier_id TEXT NOT NULL, verifier_version TEXT NOT NULL,
    verified_at TEXT NOT NULL, accepted INTEGER NOT NULL CHECK (accepted IN (0,1)),
    payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
    UNIQUE(kind, subject_id)
);
CREATE TABLE IF NOT EXISTS prospective_receipt_bound_governance_assessments (
    assessment_id TEXT PRIMARY KEY,
    governance_assessment_id TEXT NOT NULL UNIQUE
        REFERENCES prospective_governed_review_assessments(assessment_id),
    review_assessment_id TEXT NOT NULL,
    evaluated_at TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('VERIFIED','INCOMPLETE','BLOCKED')),
    payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS prospective_external_verification_receipts_no_update
BEFORE UPDATE ON prospective_external_verification_receipts
BEGIN SELECT RAISE(ABORT, 'external verification receipts are immutable'); END;
CREATE TRIGGER IF NOT EXISTS prospective_external_verification_receipts_no_delete
BEFORE DELETE ON prospective_external_verification_receipts
BEGIN SELECT RAISE(ABORT, 'external verification receipts are immutable'); END;
CREATE TRIGGER IF NOT EXISTS prospective_receipt_bound_governance_no_update
BEFORE UPDATE ON prospective_receipt_bound_governance_assessments
BEGIN SELECT RAISE(ABORT, 'receipt-bound governance assessments are immutable'); END;
CREATE TRIGGER IF NOT EXISTS prospective_receipt_bound_governance_no_delete
BEFORE DELETE ON prospective_receipt_bound_governance_assessments
BEGIN SELECT RAISE(ABORT, 'receipt-bound governance assessments are immutable'); END;
