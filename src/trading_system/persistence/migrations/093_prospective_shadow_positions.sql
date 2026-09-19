CREATE TABLE IF NOT EXISTS prospective_shadow_positions (
 trade_id TEXT PRIMARY KEY,
 decision_id TEXT NOT NULL UNIQUE REFERENCES prospective_entry_outcomes(decision_id),
 symbol TEXT NOT NULL,
 entry_price TEXT NOT NULL,
 initial_stop TEXT NOT NULL,
 known_at TEXT NOT NULL,
 payload_json TEXT NOT NULL,
 payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS prospective_shadow_exit_receipts (
 trade_id TEXT PRIMARY KEY REFERENCES prospective_shadow_positions(trade_id),
 known_at TEXT NOT NULL,
 payload_json TEXT NOT NULL,
 payload_hash TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS shadow_positions_unique_open
BEFORE INSERT ON prospective_shadow_positions
WHEN EXISTS (
 SELECT 1 FROM prospective_shadow_positions p
 WHERE p.symbol = NEW.symbol
   AND NOT EXISTS (SELECT 1 FROM prospective_shadow_exit_receipts x WHERE x.trade_id = p.trade_id)
)
BEGIN SELECT RAISE(ABORT, 'symbol already has an open shadow position'); END;
CREATE TRIGGER IF NOT EXISTS shadow_position_no_update BEFORE UPDATE ON prospective_shadow_positions
BEGIN SELECT RAISE(ABORT, 'shadow positions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS shadow_position_no_delete BEFORE DELETE ON prospective_shadow_positions
BEGIN SELECT RAISE(ABORT, 'shadow positions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS shadow_exit_no_update BEFORE UPDATE ON prospective_shadow_exit_receipts
BEGIN SELECT RAISE(ABORT, 'shadow exits are immutable'); END;
CREATE TRIGGER IF NOT EXISTS shadow_exit_no_delete BEFORE DELETE ON prospective_shadow_exit_receipts
BEGIN SELECT RAISE(ABORT, 'shadow exits are immutable'); END;
