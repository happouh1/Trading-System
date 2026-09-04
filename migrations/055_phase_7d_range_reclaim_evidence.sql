CREATE TABLE IF NOT EXISTS range_reclaim_evidence (
    evidence_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    box_id TEXT NOT NULL REFERENCES range_boxes(box_id),
    event_id TEXT NOT NULL REFERENCES pattern_events(event_id),
    known_at TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('LONG', 'SHORT')),
    boundary TEXT NOT NULL CHECK (boundary IN ('LOWER', 'UPPER')),
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE (box_id, event_id)
);

CREATE INDEX IF NOT EXISTS idx_range_reclaim_evidence_asof
ON range_reclaim_evidence(run_id, known_at, evidence_id);
