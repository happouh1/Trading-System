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

Migration 094 adds immutable, ordinal bar-check receipts. `process_bar` requires the exact next
session-aligned XNYS 1H/4H bar, including transitions after a partial 4H final bar. It checks
the locked calendar name/version, symbol, timeframe, session date, source revision (once the
first exit-side bar is recorded), receipt time and prior-known stop/ATR. A skipped, reordered,
revised or unavailable bar fails closed. No-hit bars are retained across restarts; a hit records
the bar check and terminal stop atomically. Repeating an identical bar is idempotent, while
changed evidence is rejected.

At migration 094 this was a narrow initial-stop state machine, not a complete trade lifecycle.
There was no trailing or structural exit queue, max-hold close, portfolio-capital gate, locked
prospective window, or independently reviewed fees/spread model. The entry bar's source revision
was not yet bound to the exit series; revision was checked only across exit-side bars.
These rows are not completed-trade evidence. Nothing operational imports the class; the
replacement burn-in cohort remains inactive.

## Entry-bar and maximum-hold follow-up

The first shadow bar is now the exact candle used to assess the modelled entry. Its candle ID,
ATR, feature-known-at, and receipt time must match that immutable entry receipt; the protective
stop is checked on that same bar. Later bars must keep its source revision and exact XNYS slot
sequence. This closes the previously noted entry-bar omission; it does not establish feed
completeness outside the supplied sequence.

Migration 095 adds an immutable maximum-hold queue. If the initial stop has not fired after
40 completed checked bars (including the entry bar), the 40th check atomically queues a
`MAX_HOLD` exit. The 41st exact eligible XNYS bar models a one-share sell at its open less
adverse slippage of the larger of 1 basis point or 0.02 ATR20. Although the economic event is
the open, the result is unavailable until the completed 41st bar is received. The exit and bar
receipt are atomic and restart-idempotent. A stop hit on bar 40 takes precedence and queues
nothing. Fees are not modelled. All assessments remain nonqualifying, offline-only, and incapable
of broker writes.

Trailing stops, structural-damage/opposing-trap exits, portfolio-capital checks, reviewed fee
and spread treatment, complete data-source auditing, and independent review are still required.
No operational runtime imports this state machine or promotes the proposed cohort.

## Pure trailing-stop assessment follow-up

`execution_sim/prospective_trail.py` wraps the existing Phase 1C `update_trail` and
`structural_damage` rules in a causal, offline assessment. It requires a prior-known long
position state, prior-known ADR and prior-bar extreme, paired known-at timestamps for any
EMA20 or confirmed swing, and completed-bar knowledge for the five structural-damage inputs.
It rejects a bar that has already touched the old stop: stop resolution must precede any
trail update. The calculated monotonic stop and structural-damage queue flag apply only after
the current bar is received, so neither is retroactively active within that bar. Status and
assessment ID are deterministic; qualification and broker-write flags remain false.

At this stage it was a pure evaluator, not a persistence or runtime integration. Missing
provenance or incomplete inputs must not be inferred by the caller.

## Durable trail and structural exit follow-up

Migration 096 adds immutable, bar-linked trail assessments and one structural-damage queue per
trade. The caller may opt into trail processing on the entry bar by supplying explicit
`TrailEvidence`; a surviving trade cannot switch between trail and fixed-stop modes later.
Each completed bar checks the previously persisted stop first, then atomically stores its
bar and next-bar trail state. A restart reconstructs the prior state only from the immutable,
hash-checked assessment. A bar that hits the old stop gets a terminal stop receipt and no
new trail. These changes remain offline; they do not update any Webull position.

Damage score >=70 queues `STRUCTURAL_DAMAGE` at bar receipt. The immediately next eligible
XNYS 1H/4H bar models a one-share long exit at its open less the larger of 1 basis point or
0.02 prior-known ATR20, but the result remains unavailable until that next bar is completed
and received. The signal queue, trail assessment, bar check and eventual terminal exit are
append-only and restart-idempotent. A stop on the signal bar takes precedence; structural
damage takes precedence over max-hold if both would queue at bar 40. Independent evidence
review, fees/spread treatment, portfolio capital, and activation are still missing. None
of these receipts qualifies a completed trade.

## Offline opposing-trap exit follow-up

Migration 097 adds an immutable per-trade opposing-trap queue. The optional signal is a full
`PatternEvent` plus confidence, not a Boolean. It must be a current completed-bar
`TRAP_CONFIRMED` short event for the long position's symbol and timeframe, cite the signal
candle, have confidence at least 75, and be known between candle close and receipt. Invalid
or future evidence fails closed. The full event and score remain in the immutable bar payload;
the queue binds event ID, score, candle and receipt time.

The old stop is checked first. Structural damage outranks an opposing trap on the same bar;
an opposing trap outranks 40-bar maximum hold. The next exact eligible XNYS bar models a
one-share exit at its open less the larger of 1 basis point or 0.02 ATR20. The fill is
unavailable until that bar's completed receipt. Queue, bar and terminal exit are atomic,
hash-checked and restart-idempotent. This model neither authenticates the supplied pattern
event nor places a broker order. Independent source review, fees/spread treatment, portfolio
capital and activation remain open.
