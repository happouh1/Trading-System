CREATE TABLE IF NOT EXISTS range_boxes (
    box_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    start_candle_id TEXT NOT NULL,
    end_candle_id TEXT NOT NULL,
    known_at TEXT NOT NULL,
    parent_box_id TEXT,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS range_box_outcomes (
    outcome_id TEXT PRIMARY KEY,
    box_id TEXT NOT NULL REFERENCES range_boxes(box_id),
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    horizon_bars INTEGER NOT NULL CHECK (horizon_bars > 0),
    label_available_at TEXT NOT NULL,
    terminal_location TEXT NOT NULL CHECK (terminal_location IN ('ABOVE', 'INSIDE', 'BELOW')),
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE (box_id, horizon_bars)
);

CREATE INDEX IF NOT EXISTS idx_range_boxes_asof
ON range_boxes(run_id, symbol, timeframe, known_at);

CREATE INDEX IF NOT EXISTS idx_range_box_outcomes_available
ON range_box_outcomes(run_id, label_available_at);
