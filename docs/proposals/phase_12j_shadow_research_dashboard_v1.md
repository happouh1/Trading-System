# Phase 12J — Shadow research dashboard v1

## Purpose

Phase 12J turns the evidence already produced by the Stage A and Phase 12I research
overlays into a local operator view. It does not alter signal classification, decision
thresholds, scheduler behavior, or order authority.

## Inputs

- completed `1h` and `1d` candles known at the requested `as_of` time;
- the immutable Stage A configuration;
- Phase 12I regime snapshots, short-opportunity alerts, and matured outcome labels;
- the frozen Phase 12I universe and plan identity.

Stage A values are computed from completed daily candles only. The report requires 50
daily observations before it classifies a symbol. Symbols without sufficient history are
shown explicitly instead of silently omitted.

## Output

The command `paper scheduled-shadow-research-dashboard` creates a static local HTML file
containing:

- hourly data freshness for every configured symbol;
- current Stage A state, eligibility, volume band, extension, and reason codes;
- short WATCH, ARMED, TRIGGER, and TOO_LATE totals;
- the latest bearish-regime snapshot;
- forward return, MFE, and MAE summaries by state and horizon.

## Safety contract

The source SQLite database is opened with `mode=ro`. Rendering may write only the configured
HTML artifact. It cannot load broker credentials, use the network, submit or cancel orders,
enable live trading, or promote research automatically. Report content is evidence for
review, not execution authority.
