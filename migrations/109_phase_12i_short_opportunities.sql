CREATE TABLE IF NOT EXISTS short_regime_snapshots (
  snapshot_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
  run_id TEXT NOT NULL REFERENCES runs(run_id),
  observed_at TEXT NOT NULL,
  config_hash TEXT NOT NULL,
  bearish_benchmarks INTEGER NOT NULL,
  evaluated_benchmarks INTEGER NOT NULL,
  bearish_breadth TEXT NOT NULL,
  regime_state TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  UNIQUE(session_id, run_id, observed_at, config_hash)
);

CREATE TABLE IF NOT EXISTS short_opportunity_alerts (
  alert_id TEXT PRIMARY KEY,
  snapshot_id TEXT NOT NULL REFERENCES short_regime_snapshots(snapshot_id),
  session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
  run_id TEXT NOT NULL REFERENCES runs(run_id),
  decision_id TEXT NOT NULL REFERENCES decisions(decision_id),
  observation_id TEXT NOT NULL REFERENCES feature_snapshots(observation_id),
  symbol TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  known_at TEXT NOT NULL,
  state TEXT NOT NULL,
  setup_quality TEXT NOT NULL,
  entry_quality TEXT NOT NULL,
  entry_reference TEXT NOT NULL,
  reason_codes_json TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  UNIQUE(decision_id, state)
);

CREATE TABLE IF NOT EXISTS short_opportunity_outcomes (
  outcome_id TEXT PRIMARY KEY,
  alert_id TEXT NOT NULL REFERENCES short_opportunity_alerts(alert_id),
  horizon_bars INTEGER NOT NULL,
  label_available_at TEXT NOT NULL,
  entry_price TEXT NOT NULL,
  forward_return TEXT NOT NULL,
  mfe_return TEXT NOT NULL,
  mae_return TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  UNIQUE(alert_id, horizon_bars)
);

CREATE INDEX IF NOT EXISTS idx_short_regime_session_time
  ON short_regime_snapshots(session_id, observed_at);
CREATE INDEX IF NOT EXISTS idx_short_alert_symbol_time
  ON short_opportunity_alerts(symbol, timeframe, known_at);
CREATE INDEX IF NOT EXISTS idx_short_outcome_alert
  ON short_opportunity_outcomes(alert_id, horizon_bars);
