CREATE TABLE IF NOT EXISTS prospective_transparency_checkpoint_exports (
    export_id TEXT PRIMARY KEY,
    transparency_entry_id TEXT NOT NULL
        REFERENCES prospective_approval_transparency_entries(entry_id),
    sequence INTEGER NOT NULL CHECK (sequence >= 1),
    entry_hash TEXT NOT NULL,
    approval_assessment_id TEXT NOT NULL,
    output_path TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    byte_count INTEGER NOT NULL CHECK (byte_count > 0),
    exported_at TEXT NOT NULL,
    export_config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE(transparency_entry_id, output_path)
);
CREATE TRIGGER IF NOT EXISTS prospective_transparency_checkpoint_exports_no_update
BEFORE UPDATE ON prospective_transparency_checkpoint_exports
BEGIN SELECT RAISE(ABORT, 'prospective transparency checkpoint exports are immutable'); END;
CREATE TRIGGER IF NOT EXISTS prospective_transparency_checkpoint_exports_no_delete
BEFORE DELETE ON prospective_transparency_checkpoint_exports
BEGIN SELECT RAISE(ABORT, 'prospective transparency checkpoint exports are immutable'); END;
