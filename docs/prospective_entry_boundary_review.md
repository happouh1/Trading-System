# Offline prospective entry boundary

The operator approved continuing implementation on 2026-09-18. This first increment implements
only the pure entry assessment boundary in `execution_sim/prospective.py`; the proposed complete
simulation wrapper is not yet finished or enabled.

An immutable request binds decision/plan identity, recorded time, prior feature time, ATR/ADR,
adjustment factor and code/config provenance. Session-aligned XNYS 1H/4H scheduling finds the
immediate eligible bar, including partial session-final bars. Unsupported symbols/directions,
late decisions, future features, unavailable receipts and adjustment changes fail closed.
Missing bars produce explicit expiry assessments rather than later-bar fills.

Economic event time is the eligible open. A modelled fill's known-at time is the receipt of the
completed bar, never its historical open. Quantity is one share; fees remain NOT_MODELLED,
spread NOT_SEPARATELY_MODELLED, and existing adverse slippage/gap rules are reused.

The pure evaluator is stateless, but the optional offline registry below retains terminal
assessments. Neither component is a prospective runtime. No collector, CLI, worker, or broker
transport invokes it. Qualification is always false. No actual simulation fills have been added
to operational databases.

Remaining implementation: portfolio gate linkage, complete sequential exit/trail lifecycle and
max-hold processing, locked window/universe
enforcement, independent review and source counts. Missing broker execution evidence remains
an independent activation blocker. Calendar search stops after fourteen future dates and rejects
if no slot is available; this is a fail-closed lookup bound, not permission to shift execution.

Tests cover receipt causality, deterministic evaluation, missing-bar expiry, no shifted fills,
late decisions, final-session 4H partition, AAPL/short exclusion, gap cancellation, corporate
actions and invalid/future features. No new phase completion or burn-in PASS is claimed.

## Offline receipt and stop follow-up

Migration 092 adds immutable request and terminal-assessment tables. The optional
`ProspectiveEntryRegistry` binds a decision identity to its original request/calendar and stores
the first non-WAITING assessment atomically. A restarted caller cannot replace expiry with a
fill, revise a terminal fill, change the request, or read a terminal receipt before its known-at.
WAITING evaluations bind the request but do not create terminal outcomes. Direct evaluator use
remains stateless; only registry callers obtain this finality guarantee.

`prospective_stop.assess_stop` evaluates a one-share long protective stop using prior-known
state and ATR. Gap-through exits retain economic open time but only become known at completed
bar receipt. It does not queue structural exits or qualify trades. Its caller must validate
calendar and series linkage before runtime use. No operational database was migrated.

Integration tests verify restart idempotence, expiry lock, request conflicts, as-of rejection,
and immutable database triggers. Unit tests verify stop slippage and gap/receipt timing.

## Offline position and terminal stop follow-up

Migration 093 adds an immutable one-share shadow-position claim bound to an existing modelled
entry receipt and a separate immutable terminal stop receipt. The database rejects a second open
position for the same symbol. Opening the same stored trade is idempotent; after a stop receipt,
that symbol can be claimed again only by a later decision whose economic entry open is no earlier
than the stop's known-at. Both writes persist across connection restarts. The receipt
retains the entry request, assessment, prices, timestamps, and content hash. The stop result
remains nonqualifying and has no broker-write path.

This is deliberately a narrow offline state machine, not a complete bar-by-bar exit runner.
There is no persisted no-hit-bar cursor, no enforced contiguous calendar series, no trailing or
structural exit queue, no max-hold close, no portfolio-capital gate, no locked prospective window,
and no independently reviewed fees/spread model. Callers must not feed selected later bars to
manufacture a stop result or use these rows as completed-trade evidence. Nothing operational
imports the class; the replacement burn-in cohort remains inactive.
