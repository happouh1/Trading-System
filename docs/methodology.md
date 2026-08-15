# Phase 1A methodology

Phase 0 establishes contracts only. It validates local invariants, produces canonical JSON and hashes,
and validates the versioned threshold configuration. It contains no signal, feature, state-transition,
execution, outcome-label, or backtest algorithms.

Canonical serialization sorts object keys, uses compact UTF-8 JSON, tags Decimal/date/datetime values,
rejects non-finite numbers and naive datetimes, and normalizes datetimes to UTC. Content identifiers use
SHA-256 over this representation with an explicit namespace.

Historical ingestion accepts the exact versioned column contract from CSV or Parquet, normalizes rows
by symbol/timeframe/open time, rejects all duplicates, validates adjusted/raw consistency, and checks
each bar against a supplied XNYS session calendar. No missing bar is created or forward-filled.

The production calendar adapter uses `exchange-calendars`; deterministic tests inject explicit session
bounds. Four-hour bars are partitioned at 13:30 America/New_York, producing a 09:30–13:30 bar and a
completed 13:30–16:00 remainder on normal sessions. Daily bars require complete session coverage.
Weekly bars are emitted only when every scheduled session in that exchange week is present.

The feature engine is streaming and requires strictly increasing completed candles per
symbol/timeframe. Candle anatomy is immediate. ATR initializes from 20 true ranges and then applies
Wilder smoothing. EMA initializes with the nth-close SMA. SMA200 appears on close 200. ADR20 and
same-slot RVOL20 use 20 strictly prior observations, so neither can include the current candle/session.
