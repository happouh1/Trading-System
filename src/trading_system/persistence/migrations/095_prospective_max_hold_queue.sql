CREATE TABLE IF NOT EXISTS prospective_shadow_queued_exits (
 trade_id TEXT PRIMARY KEY REFERENCES prospective_shadow_positions(trade_id),
 reason TEXT NOT NULL CHECK (reason = 'MAX_HOLD'),
 signal_ordinal INTEGER NOT NULL CHECK (signal_ordinal = 40),
 signal_candle_id TEXT NOT NULL,
 known_at TEXT NOT NULL,
 payload_json TEXT NOT NULL,
 payload_hash TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS shadow_queue_no_update BEFORE UPDATE ON prospective_shadow_queued_exits
BEGIN SELECT RAISE(ABORT, 'shadow queued exits are immutable'); END;
CREATE TRIGGER IF NOT EXISTS shadow_queue_no_delete BEFORE DELETE ON prospective_shadow_queued_exits
BEGIN SELECT RAISE(ABORT, 'shadow queued exits are immutable'); END;
