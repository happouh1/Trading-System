# Phase 12C review — unattended replacement SHADOW cohort

Phase 12C supersedes the incomplete September 28 prospective cohort without mutating it. The new
cohort contains exactly twenty XNYS sessions from 2026-10-07 through 2026-11-03. Every market day has
a frozen session ID, exchange open, exchange close, and post-close collection timestamp, including
the UTC offset change after daylight-saving time ends.

The daily start and close paths are idempotent. Start creates only a rejecting-adapter `SHADOW`
session. Close uses the Webull market-data protocol for MSFT/SPY and the offline decision worker,
then seals their exact cycle IDs in an immutable receipt. Neither path imports or invokes order
submission. Windows Task Scheduler supplies the clock; Codex is not involved at runtime.

Regime annotation intentionally remains outside unattended automation. The raw daily session,
market-data cycle, decisions, and completion receipt are captured automatically, while a later
operator review must classify BULLISH, BEARISH, or RANGE from actually observed evidence.
