CREATE TABLE IF NOT EXISTS prospective_credential_issuances (
 issuance_id TEXT PRIMARY KEY, issuer_id TEXT NOT NULL,
 credential_id TEXT NOT NULL UNIQUE REFERENCES prospective_evidence_review_credentials(credential_id),
 issued_at TEXT NOT NULL, supersedes_credential_id TEXT, payload_json TEXT NOT NULL,
 payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS prospective_credential_revocations (
 revocation_id TEXT PRIMARY KEY, issuer_id TEXT NOT NULL,
 credential_id TEXT NOT NULL REFERENCES prospective_evidence_review_credentials(credential_id),
 revoked_at TEXT NOT NULL, reason_code TEXT NOT NULL, payload_json TEXT NOT NULL,
 payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS prospective_review_timestamps (
 timestamp_id TEXT PRIMARY KEY, provider_id TEXT NOT NULL,
 attestation_id TEXT NOT NULL UNIQUE REFERENCES prospective_evidence_review_attestations(attestation_id),
 timestamped_at TEXT NOT NULL, received_at TEXT NOT NULL, payload_json TEXT NOT NULL,
 payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS prospective_governed_review_assessments (
 assessment_id TEXT PRIMARY KEY,
 review_assessment_id TEXT NOT NULL UNIQUE REFERENCES prospective_evidence_review_assessments(assessment_id),
 evaluated_at TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('VERIFIED','INCOMPLETE','BLOCKED')),
 payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS prospective_issuances_no_update BEFORE UPDATE ON prospective_credential_issuances BEGIN SELECT RAISE(ABORT,'credential issuances are immutable'); END;
CREATE TRIGGER IF NOT EXISTS prospective_issuances_no_delete BEFORE DELETE ON prospective_credential_issuances BEGIN SELECT RAISE(ABORT,'credential issuances are immutable'); END;
CREATE TRIGGER IF NOT EXISTS prospective_revocations_no_update BEFORE UPDATE ON prospective_credential_revocations BEGIN SELECT RAISE(ABORT,'credential revocations are immutable'); END;
CREATE TRIGGER IF NOT EXISTS prospective_revocations_no_delete BEFORE DELETE ON prospective_credential_revocations BEGIN SELECT RAISE(ABORT,'credential revocations are immutable'); END;
CREATE TRIGGER IF NOT EXISTS prospective_timestamps_no_update BEFORE UPDATE ON prospective_review_timestamps BEGIN SELECT RAISE(ABORT,'review timestamps are immutable'); END;
CREATE TRIGGER IF NOT EXISTS prospective_timestamps_no_delete BEFORE DELETE ON prospective_review_timestamps BEGIN SELECT RAISE(ABORT,'review timestamps are immutable'); END;
CREATE TRIGGER IF NOT EXISTS prospective_governance_no_update BEFORE UPDATE ON prospective_governed_review_assessments BEGIN SELECT RAISE(ABORT,'governed review assessments are immutable'); END;
CREATE TRIGGER IF NOT EXISTS prospective_governance_no_delete BEFORE DELETE ON prospective_governed_review_assessments BEGIN SELECT RAISE(ABORT,'governed review assessments are immutable'); END;
