PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, code_version TEXT NOT NULL,
  config_hash TEXT NOT NULL, data_revision TEXT NOT NULL, calendar_version TEXT NOT NULL,
  random_seed INTEGER NOT NULL, status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS candles (
  candle_id TEXT PRIMARY KEY, symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
  open_time TEXT NOT NULL, close_time TEXT NOT NULL, session_date TEXT NOT NULL,
  open TEXT NOT NULL, high TEXT NOT NULL, low TEXT NOT NULL, close TEXT NOT NULL,
  volume TEXT NOT NULL, raw_open TEXT, raw_high TEXT, raw_low TEXT, raw_close TEXT,
  raw_volume TEXT, adjustment_factor TEXT NOT NULL,
  is_complete INTEGER NOT NULL CHECK (is_complete IN (0, 1)),
  source TEXT NOT NULL, source_revision TEXT NOT NULL, payload_hash TEXT NOT NULL,
  UNIQUE(symbol, timeframe, open_time, source_revision)
);
CREATE TABLE IF NOT EXISTS feature_snapshots (
  observation_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(run_id),
  candle_id TEXT NOT NULL REFERENCES candles(candle_id), known_at TEXT NOT NULL,
  schema_version TEXT NOT NULL, input_fingerprint TEXT NOT NULL,
  features_json TEXT NOT NULL, data_quality_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
  UNIQUE(run_id, candle_id, schema_version)
);
CREATE INDEX IF NOT EXISTS idx_candles_replay ON candles(symbol, timeframe, close_time);
CREATE INDEX IF NOT EXISTS idx_snapshots_run_known ON feature_snapshots(run_id, known_at);
PRAGMA user_version = 1;

