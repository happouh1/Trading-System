CREATE TABLE IF NOT EXISTS completed_trades (
    trade_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_time TEXT NOT NULL,
    exit_time TEXT NOT NULL,
    entry_price TEXT NOT NULL,
    exit_price TEXT NOT NULL,
    initial_risk TEXT NOT NULL,
    gross_r TEXT NOT NULL,
    net_r TEXT NOT NULL,
    mfe_r TEXT NOT NULL,
    mae_r TEXT NOT NULL,
    hold_bars INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_completed_trades_run
ON completed_trades(run_id, exit_time, trade_id);
