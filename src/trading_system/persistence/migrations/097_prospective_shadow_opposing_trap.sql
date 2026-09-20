CREATE TABLE IF NOT EXISTS prospective_shadow_trap_queues (
 trade_id TEXT PRIMARY KEY REFERENCES prospective_shadow_positions(trade_id),
 signal_ordinal INTEGER NOT NULL CHECK (signal_ordinal > 0 AND signal_ordinal <= 40),
 signal_candle_id TEXT NOT NULL,
 signal_event_id TEXT NOT NULL,
 confidence TEXT NOT NULL,
 known_at TEXT NOT NULL,
 payload_json TEXT NOT NULL,
 payload_hash TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS shadow_trap_queue_no_update BEFORE UPDATE ON prospective_shadow_trap_queues
BEGIN SELECT RAISE(ABORT, 'shadow trap queues are immutable'); END;
CREATE TRIGGER IF NOT EXISTS shadow_trap_queue_no_delete BEFORE DELETE ON prospective_shadow_trap_queues
BEGIN SELECT RAISE(ABORT, 'shadow trap queues are immutable'); END;
