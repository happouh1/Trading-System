CREATE TABLE IF NOT EXISTS prospective_verifier_approval_credentials (
    credential_id TEXT PRIMARY KEY, principal_id TEXT NOT NULL, role TEXT NOT NULL,
    public_key_base64 TEXT NOT NULL, valid_from TEXT NOT NULL, valid_until TEXT NOT NULL,
    payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS prospective_verifier_approval_requests (
    request_id TEXT PRIMARY KEY,
    receipt_bound_assessment_id TEXT NOT NULL UNIQUE
        REFERENCES prospective_receipt_bound_governance_assessments(assessment_id),
    requested_at TEXT NOT NULL, valid_from TEXT NOT NULL, valid_until TEXT NOT NULL,
    request_hash TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS prospective_verifier_approval_attestations (
    attestation_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES prospective_verifier_approval_requests(request_id),
    credential_id TEXT NOT NULL
        REFERENCES prospective_verifier_approval_credentials(credential_id),
    principal_id TEXT NOT NULL, role TEXT NOT NULL, signed_at TEXT NOT NULL,
    signature_base64 TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
    UNIQUE(request_id, role)
);
CREATE TABLE IF NOT EXISTS prospective_verifier_approval_assessments (
    assessment_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE REFERENCES prospective_verifier_approval_requests(request_id),
    receipt_bound_assessment_id TEXT NOT NULL, evaluated_at TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('APPROVED','INCOMPLETE','BLOCKED')),
    request_hash TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS prospective_verifier_approval_credentials_no_update
BEFORE UPDATE ON prospective_verifier_approval_credentials
BEGIN SELECT RAISE(ABORT, 'prospective verifier approval credentials are immutable'); END;
CREATE TRIGGER IF NOT EXISTS prospective_verifier_approval_credentials_no_delete
BEFORE DELETE ON prospective_verifier_approval_credentials
BEGIN SELECT RAISE(ABORT, 'prospective verifier approval credentials are immutable'); END;
CREATE TRIGGER IF NOT EXISTS prospective_verifier_approval_requests_no_update
BEFORE UPDATE ON prospective_verifier_approval_requests
BEGIN SELECT RAISE(ABORT, 'prospective verifier approval requests are immutable'); END;
CREATE TRIGGER IF NOT EXISTS prospective_verifier_approval_requests_no_delete
BEFORE DELETE ON prospective_verifier_approval_requests
BEGIN SELECT RAISE(ABORT, 'prospective verifier approval requests are immutable'); END;
CREATE TRIGGER IF NOT EXISTS prospective_verifier_approval_attestations_no_update
BEFORE UPDATE ON prospective_verifier_approval_attestations
BEGIN SELECT RAISE(ABORT, 'prospective verifier approval attestations are immutable'); END;
CREATE TRIGGER IF NOT EXISTS prospective_verifier_approval_attestations_no_delete
BEFORE DELETE ON prospective_verifier_approval_attestations
BEGIN SELECT RAISE(ABORT, 'prospective verifier approval attestations are immutable'); END;
CREATE TRIGGER IF NOT EXISTS prospective_verifier_approval_assessments_no_update
BEFORE UPDATE ON prospective_verifier_approval_assessments
BEGIN SELECT RAISE(ABORT, 'prospective verifier approval assessments are immutable'); END;
CREATE TRIGGER IF NOT EXISTS prospective_verifier_approval_assessments_no_delete
BEFORE DELETE ON prospective_verifier_approval_assessments
BEGIN SELECT RAISE(ABORT, 'prospective verifier approval assessments are immutable'); END;
