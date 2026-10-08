# Phase 12B review — locked prospective shadow launch

Phase 12B binds the September 28–October 23 prospective plan to new daily `SHADOW`
sessions. The checked-in launch identity freezes the exact plan bytes, plan ID, package version,
paper configuration hash, strategy configuration hash, data revision, calendar version, MSFT/SPY
universe, read-only Webull worker, and offline decision worker.

The start path is local and idempotent. It creates only a rejecting-adapter `SHADOW` session and an
immutable `paper_burn_in_session_bindings` record. It cannot load credentials, use the network,
simulate fills, submit orders, enable live trading, or promote a release. Plan-byte tampering,
configuration drift, authority widening, a mismatched worker, or an out-of-window start fails before
the target database is opened for writing.

`scripts/start-prospective-shadow-day.ps1` starts the daily session and then performs the separately
authorized same-session, read-only Webull account verification. Its `-OfflineVerify` mode exercises
the complete local launch and both worker configurations without credentials or network access.

After the XNYS close, `scripts/collect-prospective-shadow-day.ps1` performs one bounded read-only
market-data cycle, one offline causal decision cycle, and one immutable evidence collection. The
operator must explicitly declare the observed `BULLISH`, `BEARISH`, or `RANGE` regime. The script
has no order API or broker-write authority.

For the first session on September 28, 2026, start at `13:30:00Z` (09:30 America/New_York) and
collect no earlier than `20:05:00Z` (16:05 America/New_York). Subsequent sessions must use unique
session IDs and their real timestamps while remaining inside the frozen window.
