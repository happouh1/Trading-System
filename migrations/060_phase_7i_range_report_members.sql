CREATE TABLE IF NOT EXISTS range_evaluation_report_members (
    report_id TEXT NOT NULL REFERENCES range_evaluation_reports(report_id),
    member_type TEXT NOT NULL CHECK (member_type IN ('ASSIGNMENT', 'SUMMARY')),
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    source_id TEXT NOT NULL,
    source_payload_hash TEXT NOT NULL,
    PRIMARY KEY (report_id, member_type, ordinal),
    UNIQUE (report_id, member_type, source_id)
);

CREATE INDEX IF NOT EXISTS idx_range_evaluation_report_members_source
ON range_evaluation_report_members(report_id, member_type, source_id);
