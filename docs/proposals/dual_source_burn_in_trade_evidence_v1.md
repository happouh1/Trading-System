# Dual-source prospective burn-in trade evidence — scope decision

Decision recorded 2026-09-16: the operator wants both actual Webull sandbox trades and internal
simulated shadow trades considered for a future burn-in. This is a scope decision, not a new
preregistered plan or authority to execute orders or generate simulated fills.

Threshold decision recorded 2026-09-16: a replacement plan must require at least **10 qualifying
completed trades from each source**. Ten combined trades do not satisfy either source minimum.

## Current boundary

- The immutable 2026-09-14 plan is Webull-sandbox-only, and the Phase 11C collector currently counts
  terminal `webull_position_events` states. Neither is silently amended or backfilled.
- Phase 11H creates causal decisions and non-executable shadow intents. It creates no fills or
  completed trades.
- Historical replay `completed_trades` belong to a replay run. They are not automatically
  prospective burn-in evidence and must not be counted merely because they exist in SQLite.

## Proposed replacement evidence model

Record every candidate completed trade with an explicit `WEBULL_SANDBOX` or `SHADOW_SIMULATED`
source, immutable trade identity, session and decision linkage, entry/exit known-at times,
source-specific evidence references, model/config/code hashes, and a content hash. Keep separate
source subtotals and any plan-approved qualifying total in the assessment. Reject duplicate,
conflicting, future-known, or unverified records. Do not collapse simulated and broker records into
one unlabelled `completed_trades` number.

Only a newly approved, versioned prospective plan can encode the two independent 10-trade minima
and define which evidence checks qualify a trade. The simulation model and broker fill reconciliation
must be reviewed before either source feeds that plan. Until then, report source counts for
inspection only, with no PASS conclusion. These small minima test operational coverage, not strategy
profitability or readiness for live trading.

## Next gated work

1. Define and test a versioned, append-only dual-source trade evidence contract without changing
   the old plan or enabling either trade path.
2. Review the simulated fill/spread/slippage/fee and exit model, and the broker execution/fill/
   position reconciliation criteria.
3. Approve the source-specific evidence checks, prospective window, strategy hash, and replacement
   plan before any qualifying observations begin. Keep source counts distinct; do not let a surplus
   in one source compensate for a deficit in the other.
4. Run each path under its own explicit authority and verify the resulting evidence independently.

Open decisions are tracked in `docs/open_questions.md` (questions 567–575).
