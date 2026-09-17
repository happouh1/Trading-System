CREATE TABLE IF NOT EXISTS webull_trade_evidence_imports (
    import_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL REFERENCES burn_in_trade_evidence_candidates(candidate_id),
    capture_id TEXT NOT NULL,
    account_id_hash TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE(account_id_hash, capture_id),
    CHECK(captured_at <= imported_at)
);
CREATE TABLE IF NOT EXISTS webull_trade_evidence_claims (
    account_id_hash TEXT NOT NULL,
    record_kind TEXT NOT NULL CHECK(record_kind IN ('ORDER', 'CLIENT_ORDER', 'FILL')),
    record_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL REFERENCES burn_in_trade_evidence_candidates(candidate_id),
    content_hash TEXT NOT NULL,
    PRIMARY KEY(account_id_hash, record_kind, record_id)
);
CREATE TRIGGER IF NOT EXISTS webull_trade_imports_no_update
BEFORE UPDATE ON webull_trade_evidence_imports
BEGIN SELECT RAISE(ABORT, 'trade evidence imports are immutable'); END;
CREATE TRIGGER IF NOT EXISTS webull_trade_imports_no_delete
BEFORE DELETE ON webull_trade_evidence_imports
BEGIN SELECT RAISE(ABORT, 'trade evidence imports are immutable'); END;
CREATE TRIGGER IF NOT EXISTS webull_trade_claims_no_update
BEFORE UPDATE ON webull_trade_evidence_claims
BEGIN SELECT RAISE(ABORT, 'trade evidence claims are immutable'); END;
CREATE TRIGGER IF NOT EXISTS webull_trade_claims_no_delete
BEFORE DELETE ON webull_trade_evidence_claims
BEGIN SELECT RAISE(ABORT, 'trade evidence claims are immutable'); END;
