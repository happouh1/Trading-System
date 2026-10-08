# Phase 12A review — automatic Webull sandbox submission

Phase 12A implements the broker-write edge of the approved dual-source burn-in blueprint. It is
strictly sandbox-only: the Webull configuration accepts only the official sandbox hosts, the local
schedule is Monday through Friday from 04:00 through 20:00 America/New_York, and an order can be
released only during the first 120 seconds of the XNYS regular session.

The replacement prospective window is 2026-09-28 through 2026-10-23 (twenty consecutive XNYS
sessions). The Webull lane and simulated lane each require ten independently qualifying completed
trades. Counts must never be pooled. The Webull universe is frozen to MSFT and SPY; AAPL remains
blocked because the legacy sandbox holding must not be mixed into the cohort.

## Submission gates

The automatic tick submits at most one new order per market day and only when every gate passes:

1. the target paper session is `PAPER_ENABLED` and bound to the exact replacement plan;
2. a due long-only intent exists for MSFT or SPY;
3. the account has neither an existing position nor an open order for that symbol;
4. the quantity is exactly one whole share and the session is CORE;
5. the Webull opening snapshot supplies a positive daily open and twenty prior daily sessions
   supply a causal ADR20;
6. an identical preview is accepted and the opening gap remains within 0.25 ADR;
7. reconciliation matches after account verification;
8. both the environment and CLI submission gates are enabled; and
9. the Phase 3D exit capability manifest is approved and a current exit authorization exists.

Ambiguous writes use the existing same-client-ID recovery path and halt rather than retrying.
Production endpoints, live trading, shorts, options, fractional shares, automatic promotion, and
unbounded retries remain impossible.

## Activation state

The Windows scheduled task can be installed now, but broker submission remains **armed and
fail-closed** while `config/webull.exit_capabilities.pending.v1.json` is unapproved and until the
replacement plan is bound to the two runtime sessions. This is deliberate: changing that manifest
would falsely attest that all seven required Webull exit lifecycle cases were independently
validated. Activation is complete only after those evidence gates are satisfied.
