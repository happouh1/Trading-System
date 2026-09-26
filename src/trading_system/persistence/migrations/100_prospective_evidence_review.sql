CREATE TABLE IF NOT EXISTS prospective_evidence_review_credentials (
    credential_id TEXT PRIMARY KEY, principal_id TEXT NOT NULL, role TEXT NOT NULL,
    public_key_base64 TEXT NOT NULL, valid_from TEXT NOT NULL, valid_until TEXT NOT NULL,
    payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS prospective_evidence_review_requests (
    request_id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL UNIQUE REFERENCES prospective_evidence_receipts(decision_id),
    receipt_id TEXT NOT NULL UNIQUE REFERENCES prospective_evidence_receipts(receipt_id),
    requested_at TEXT NOT NULL, valid_from TEXT NOT NULL, valid_until TEXT NOT NULL,
    request_hash TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS prospective_evidence_review_attestations (
    attestation_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES prospective_evidence_review_requests(request_id),
    credential_id TEXT NOT NULL REFERENCES prospective_evidence_review_credentials(credential_id),
    principal_id TEXT NOT NULL, role TEXT NOT NULL, signed_at TEXT NOT NULL,
    signature_base64 TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
    UNIQUE(request_id, role)
);
CREATE TABLE IF NOT EXISTS prospective_evidence_review_assessments (
    assessment_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE REFERENCES prospective_evidence_review_requests(request_id),
    decision_id TEXT NOT NULL, receipt_id TEXT NOT NULL, evaluated_at TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('SIGNATURES_VERIFIED','INCOMPLETE','BLOCKED')),
    request_hash TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS prospective_evidence_review_credentials_no_update
BEFORE UPDATE ON prospective_evidence_review_credentials
BEGIN SELECT RAISE(ABORT, 'prospective evidence review credentials are immutable'); END;
CREATE TRIGGER IF NOT EXISTS prospective_evidence_review_credentials_no_delete
BEFORE DELETE ON prospective_evidence_review_credentials
BEGIN SELECT RAISE(ABORT, 'prospective evidence review credentials are immutable'); END;
CREATE TRIGGER IF NOT EXISTS prospective_evidence_review_requests_no_update
BEFORE UPDATE ON prospective_evidence_review_requests
BEGIN SELECT RAISE(ABORT, 'prospective evidence review requests are immutable'); END;
CREATE TRIGGER IF NOT EXISTS prospective_evidence_review_requests_no_delete
BEFORE DELETE ON prospective_evidence_review_requests
BEGIN SELECT RAISE(ABORT, 'prospective evidence review requests are immutable'); END;
CREATE TRIGGER IF NOT EXISTS prospective_evidence_review_attestations_no_update
BEFORE UPDATE ON prospective_evidence_review_attestations
BEGIN SELECT RAISE(ABORT, 'prospective evidence review attestations are immutable'); END;
CREATE TRIGGER IF NOT EXISTS prospective_evidence_review_attestations_no_delete
BEFORE DELETE ON prospective_evidence_review_attestations
BEGIN SELECT RAISE(ABORT, 'prospective evidence review attestations are immutable'); END;
CREATE TRIGGER IF NOT EXISTS prospective_evidence_review_assessments_no_update
BEFORE UPDATE ON prospective_evidence_review_assessments
BEGIN SELECT RAISE(ABORT, 'prospective evidence review assessments are immutable'); END;
CREATE TRIGGER IF NOT EXISTS prospective_evidence_review_assessments_no_delete
BEFORE DELETE ON prospective_evidence_review_assessments
BEGIN SELECT RAISE(ABORT, 'prospective evidence review assessments are immutable'); END;
