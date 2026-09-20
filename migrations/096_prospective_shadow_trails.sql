CREATE TABLE IF NOT EXISTS prospective_shadow_trail_receipts (
 trade_id TEXT NOT NULL,
 ordinal INTEGER NOT NULL CHECK (ordinal > 0),
 candle_id TEXT NOT NULL,
 known_at TEXT NOT NULL,
 payload_json TEXT NOT NULL,
 payload_hash TEXT NOT NULL,
 PRIMARY KEY (trade_id, ordinal),
 FOREIGN KEY (trade_id, ordinal) REFERENCES prospective_shadow_bar_receipts(trade_id, ordinal)
);
CREATE TRIGGER IF NOT EXISTS shadow_trail_no_update BEFORE UPDATE ON prospective_shadow_trail_receipts
BEGIN SELECT RAISE(ABORT, 'shadow trail receipts are immutable'); END;
CREATE TRIGGER IF NOT EXISTS shadow_trail_no_delete BEFORE DELETE ON prospective_shadow_trail_receipts
BEGIN SELECT RAISE(ABORT, 'shadow trail receipts are immutable'); END;
CREATE TABLE IF NOT EXISTS prospective_shadow_structural_queues (
 trade_id TEXT PRIMARY KEY REFERENCES prospective_shadow_positions(trade_id),
 signal_ordinal INTEGER NOT NULL CHECK (signal_ordinal > 0 AND signal_ordinal <= 40),
 signal_candle_id TEXT NOT NULL,
 known_at TEXT NOT NULL,
 payload_json TEXT NOT NULL,
 payload_hash TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS shadow_structural_queue_no_update BEFORE UPDATE ON prospective_shadow_structural_queues
BEGIN SELECT RAISE(ABORT, 'shadow structural queues are immutable'); END;
CREATE TRIGGER IF NOT EXISTS shadow_structural_queue_no_delete BEFORE DELETE ON prospective_shadow_structural_queues
BEGIN SELECT RAISE(ABORT, 'shadow structural queues are immutable'); END;
