CREATE TABLE IF NOT EXISTS prospective_shadow_bar_receipts (
 trade_id TEXT NOT NULL REFERENCES prospective_shadow_positions(trade_id),
 ordinal INTEGER NOT NULL CHECK (ordinal > 0),
 candle_id TEXT NOT NULL,
 open_time TEXT NOT NULL,
 close_time TEXT NOT NULL,
 known_at TEXT NOT NULL,
 payload_json TEXT NOT NULL,
 payload_hash TEXT NOT NULL,
 PRIMARY KEY (trade_id, ordinal),
 UNIQUE (trade_id, candle_id)
);
CREATE TRIGGER IF NOT EXISTS shadow_bar_no_update BEFORE UPDATE ON prospective_shadow_bar_receipts
BEGIN SELECT RAISE(ABORT, 'shadow bar receipts are immutable'); END;
CREATE TRIGGER IF NOT EXISTS shadow_bar_no_delete BEFORE DELETE ON prospective_shadow_bar_receipts
BEGIN SELECT RAISE(ABORT, 'shadow bar receipts are immutable'); END;
