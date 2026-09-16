# Phase 11H review — local causal burn-in decisions

## Outcome

Phase 11H connects the completed 1H Webull sandbox bars persisted by Phase 11G to the existing causal
feature, structure, level, pattern, scoring, and decision pipeline. It deterministically reconstructs
only completed 4H, Daily, and Weekly candles, persists every resulting feature snapshot and decision,
and may stage a fresh directional decision as a non-executable `SHADOW` intent.

## Authority boundary

The checked-in configuration authorizes local SQLite reads/writes and shadow-intent staging only. It
does not load Webull credentials, use the network, simulate fills, call a broker order API, enable
sandbox execution, enable live trading, or promote a cohort. The cycle requires the same locked plan,
an active `SHADOW` session, and a successful same-session Phase 11G cycle.

## Causality and restart behavior

- Only Webull shadow bars known no later than the cycle timestamp are eligible.
- Conflicting revisions for the same symbol/timeframe/open time fail closed.
- 4H and Daily candles require a complete XNYS session; Weekly candles require every XNYS session in
  that week. Missing bars are never forward-filled.
- Replay ordering is deterministic and higher-timeframe values become available only at candle close.
- The replay checkpoint restores pipeline state and skips already processed closes after restart.
- `NO_TRADE` decisions are retained, not discarded.

## Evidence and limitations

The migration adds `burn_in_shadow_decision_cycles`, whose canonical payload and hash record source,
derived, processed, decision, directional, and staged-intent counts. Phase 11H intentionally does not
create fills, completed trades, outcome labels, broker envelopes, or promotion evidence. Therefore its
decisions do not yet satisfy the preregistered completed-trade requirement.

## Verification

The unit coverage validates strict authority parsing, checked-in threshold binding, deterministic
1H/4H/Daily/Weekly processing, append-only persistence, restart deduplication, and the Phase 11G
prerequisite. Repository-wide Ruff, strict mypy, and pytest results are reported at handoff.
