# Proposed Phase 3D deterministic sandbox exit lifecycle v1

Status: **APPROVED FOR OFFLINE IMPLEMENTATION; 3D-5 OFFICIAL WRITES REMAIN LOCKED**

## Purpose

Phase 3D maps the already-approved Phase 1 position-management rules to Webull sandbox stock
operations without changing strategy behavior. It adds protective-stop ownership, monotonic stop
updates, queued full-position exits, cancel/replace ambiguity handling, restart recovery, draining,
and an explicitly authorized single-position emergency flatten workflow.

This proposal does not authorize production endpoints, real-money trading, options, new entry
signals, new exit triggers, partial profit-taking, portfolio allocation, or model-driven behavior.
Phase 1 remains the sole strategy authority; Phase 3D is an operational translation layer.

## Existing normative behavior reused unchanged

Phase 3D MUST consume immutable Phase 1 evidence and MUST NOT recalculate a different strategy:

- initial and trailing stops come from `PositionState.current_stop`;
- long stops are monotonic nondecreasing and short stops are monotonic nonincreasing;
- damage score `>=70` queues a full exit at the next eligible signal-timeframe bar open;
- an opposing confirmed trap with confidence `>=75` queues a full exit at the next eligible open;
- maximum hold is `40` signal-timeframe bars from the versioned Phase 1 configuration;
- a stop has precedence when stop and favorable or queued conditions collide;
- gap-through stop outcomes use the broker's actual fill in sandbox operation;
- no partial strategy exits exist;
- Phase 3A probabilities and all later outcome labels have no execution authority.

The operational adapter records actual sandbox fills separately from simulated Phase 1 fills. It may
report variance, but it cannot rewrite the original decision, plan, stop history, or simulated event.

## Pinned broker boundary

Phase 3D remains pinned to Python 3.12 and `webull-openapi-python-sdk==2.0.17`. Local inspection
confirms that `TradeClient.order_v2` exposes `place_order(account_id, orders)`,
`replace_order(account_id, orders)`, and `cancel_order(account_id, client_order_id)`. The SDK also
declares stock sides `BUY`, `SELL`, and `SHORT`, order types including `MARKET` and `STOP_LOSS`, and
time-in-force values `DAY` and `GTC`.

Method presence is not response-schema proof. Redacted sandbox captures remain mandatory for stop
preview/place/detail, replace, cancel, short-cover, and partial-fill behavior. Unknown response
fields, aliases, status meanings, tick rules, or netting behavior MUST fail closed.

The existing Phase 3C exact sandbox host allowlist, credentials, SDK logger suppression, recursive
redaction, transport isolation, two-factor submission gate, and production-host prohibition remain
normative.

## Bounded implementation stages

### 3D-1 — Offline contracts, action journal, and fake transport

1. Add immutable contracts for managed position identity, exit intent, protective-stop version,
   broker action, cancel/replace result, position snapshot, flatten authorization, and exit outcome.
2. Extend only the fake transport initially with preview/place/replace/cancel behavior.
3. Add append-only migrations and repositories described below.
4. Reconstruct managed positions only from an exact Phase 3C entry mapping plus cumulative broker
   executions. No database row may manufacture broker exposure.
5. Keep the official cancel/replace methods unreachable until offline tests and the corresponding
   redacted sandbox schema review pass.

### 3D-2 — Protective stops and monotonic replacement

1. Phase 3C entry submission gains an additional prerequisite: the Phase 3D exit subsystem must be
   durably armed for the exact session/configuration before exposure can be opened. Arming requires
   `WEBULL_SANDBOX_EXIT_ENABLED=true`, explicit CLI `--enable-sandbox-exits`, successful read-only
   account/position reconciliation, an approved adapter-capability manifest from the 3D-5 smoke
   review, and a persisted authorization hash. If exits are unarmed, entry fails before its transport
   call.
2. A fully filled entry creates protection for exactly the reconciled filled quantity. If an entry
   remains `PARTIALLY_FILLED` at authenticated reconciliation, first persist and issue one cancel of
   the unfilled remainder, prove the terminal entry state, reconcile the final cumulative fill, and
   only then protect that exact final position. The adapter never leaves a working entry and an
   independently executable closing stop that could race through zero.
3. The proposed initial broker representation is:

   ```text
   long position stop  -> SELL STOP_LOSS GTC
   short position stop -> BUY  STOP_LOSS GTC
   quantity            -> exact absolute reconciled open quantity
   stop price          -> Phase 1 current stop converted to executable raw price
   extended hours      -> false
   ```

4. `GTC` is proposed because a Phase 1 position and its stop may span sessions. A `DAY` stop would
   silently remove protection at the close and therefore would not represent Phase 1 behavior.
5. A stable, at-most-32-character protective client ID is derived from
   `(session_id, managed_position_id, "protective-stop-v1")`. Stop updates use replace on that same
   logical order only after sandbox evidence confirms provider behavior.
6. Every replacement must preserve symbol, reducing side, GTC, stop type, and exact reconciled
   remaining quantity. Only a monotonic stop-price change is allowed. Entry quantity is terminal
   before protection; stop replacement cannot compensate for an unresolved entry fill.
7. A replacement commits `PREPARED` and `CALL_STARTED` first. Timeout, malformed response, or
   contradictory status queries the same client ID once and halts. It is never permission to issue a
   second replacement or a cancel-and-recreate fallback.
8. A position with a confirmed fill but no exactly reconciled protective stop is `UNPROTECTED` and
   halts new entries immediately. Automatic strategy activity cannot continue until protection or an
   explicitly authorized flatten is proven.

### 3D-3 — Stop fills and queued next-open exits

1. Broker order detail and position reconciliation are authoritative for actual fills. Notifications
   remain append-only hints under Phase 3C rules.
2. A confirmed protective-stop fill closes only the filled quantity it reports. Cumulative fills are
   idempotent; a partial stop fill reduces the remaining managed quantity and the still-open stop
   must reconcile exactly.
3. Structural-damage, opposing-trap, and maximum-hold signals create immutable exit intents at the
   completed signal candle's `known_at`. They schedule the first eligible open of the same signal
   timeframe and cannot fill at the signal close.
4. Immediately after the eligible open becomes known, the adapter performs this fixed sequence:

   ```text
   persist exit-release evidence
   -> REST reconcile entry, stop, fills, and position
   -> if stop already filled or position is flat: close intent without another order
   -> cancel the protective stop
   -> prove cancellation and unchanged remaining position through REST
   -> submit one full-remaining-quantity MARKET/DAY exit
   -> reconcile order, cumulative fills, and flat position
   ```

5. The stop remains active overnight and until the next-open release sequence begins. The system
   never cancels protection at the preceding signal close.
6. Proposed reducing market sides are `SELL` for a long position and `BUY` for a short position.
   Short-cover netting must be proven by a redacted sandbox preview/capture before official transport
   enablement.
7. A stop fill discovered during cancellation wins. The market exit is suppressed or reduced to the
   newly reconciled remaining quantity. This is the operational equivalent of adverse-first
   collision precedence.
8. Cancel ambiguity halts without submitting the market exit. Exit-placement ambiguity queries the
   same deterministic exit client ID once and halts without resubmission.
9. No OCO, bracket, simultaneous stop-plus-market exit, limit fallback, or partial profit-taking is
   authorized in v1.

### 3D-4 — Restart ownership, drain, and emergency flatten

1. Restart loads append-only action boundaries, then queries every unresolved stop, cancel, replace,
   and exit client ID before any new action.
2. A position is manageable only when all of these match exactly:

   - sandbox account and current runtime session;
   - Phase 3C entry intent, client ID, request hash, and broker order ID;
   - symbol, direction, cumulative entry fills, cumulative exit fills, and remaining quantity;
   - code, configuration, data revision, calendar, and adapter versions.

3. Unknown or pre-existing broker orders/positions are never adopted. Any unexplained exposure,
   excess quantity, opposing sign, missing order, or identity mismatch records an incident and halts.
4. `DRAINING` prohibits new entries, cancels only definitively unfilled entry orders, and continues
   reconciling existing protection. It does not silently flatten a position. The session becomes
   `STOPPED` only after positions and managed open orders are both empty.
5. Risk-reducing actions are distinct from entry authority. Entry requires `PAPER_ENABLED`; exact
   reconciliation and protection reporting continue in `DRAINING` or `HALTED`. No automatic broker
   write is made from uncertain `HALTED` state.
6. The proposed emergency command operates on one exact managed sandbox position, never the whole
   account. It requires all of:

   - `WEBULL_SANDBOX_FLATTEN_ENABLED=true`;
   - explicit CLI `--enable-sandbox-flatten`;
   - exact session, managed-position, symbol, and direction arguments;
   - a fresh successful reconciliation;
   - a persisted one-use authorization hash.

7. Emergency flatten uses the same cancel-confirm-query-before-place sequence as a normal full exit.
   If cancellation or placement is ambiguous, it halts; it does not loop or submit an alternate ID.
8. An explicit flatten may run from `HALTED` only when a new exact reconciliation succeeds after the
   halt and the halt did not involve account identity, unknown exposure, position sign, or quantity
   mismatch. Those mismatch classes require manual broker intervention because the system cannot
   prove which exposure it owns.

### 3D-5 — Separately invoked sandbox validation

Ordinary CI remains offline. Official cancel/replace/exit methods become reachable only after
redacted sandbox captures validate, in order:

1. long protective-stop preview/place/detail/cancel;
2. monotonic long stop replacement with the same client identity;
3. long MARKET/DAY reducing exit and flat-position reconciliation;
4. short-cover preview and proof that `BUY` reduces, rather than reverses, the short;
5. partial entry and partial stop/exit cumulative-fill behavior;
6. timeout or injected ambiguity with same-client-ID recovery;
7. restart with an existing managed position and protective stop.

These smoke tests require separate operator invocation and must use disposable sandbox positions.
Passing offline CI alone does not authorize a sandbox broker write.

## Proposed state model

```text
ENTRY_PENDING
  -> PARTIALLY_OPEN -> CANCELING_ENTRY -> PROTECTING -> PROTECTED
  -> OPEN                            -> PROTECTING -> PROTECTED

PROTECTED -> REPLACING_STOP -> PROTECTED
PROTECTED -> EXIT_QUEUED -> EXIT_RELEASING
EXIT_RELEASING -> CANCELING_STOP -> EXIT_SUBMITTING -> EXIT_WORKING -> FLAT

PROTECTED -> STOP_PARTIALLY_FILLED -> PROTECTED
PROTECTED -> STOP_FILLED -> FLAT

any nonterminal state -> AMBIGUOUS -> HALTED
any exact known position -> FLATTEN_AUTHORIZED -> EXIT_RELEASING
```

State advances only from persisted, validated evidence. An SDK call returning is not by itself proof
of a broker transition.

## Deterministic identifiers

```text
managed_position_id = H(session_id, entry_intent_id, entry_client_order_id)
protective_stop_id   = H(session_id, managed_position_id, "protective-stop-v1")[:32]
exit_intent_id       = H(session_id, managed_position_id, reason, signal_known_at)
exit_client_id       = H(session_id, exit_intent_id, "market-exit-v1")[:32]
broker_action_id     = H(session_id, action_kind, client_id, request_hash, event_type, occurred_at)
flatten_auth_id      = H(session_id, managed_position_id, reconciliation_id, created_at)
```

`H` uses the repository's canonical deterministic-ID/hash utilities. A conflicting payload with an
existing identity is corruption and halts; it never creates a random replacement ID.

## Proposed immutable record shapes

Illustrative JSON-like fields below are normative for meaning; implementation uses frozen typed
contracts and canonical serialization:

```json
{
  "managed_position_id": "...",
  "session_id": "...",
  "entry_intent_id": "...",
  "entry_client_order_id": "...",
  "entry_broker_order_id": "...",
  "symbol": "AAPL",
  "direction": "LONG",
  "filled_quantity": 100,
  "remaining_quantity": 100,
  "entry_price": "101.25",
  "initial_stop_adjusted": "99.50",
  "opened_at": "2026-01-05T14:30:00Z",
  "config_hash": "sha256:...",
  "code_version": "git:..."
}
```

```json
{
  "exit_intent_id": "...",
  "managed_position_id": "...",
  "reason": "STRUCTURAL_DAMAGE",
  "signal_candle_id": "...",
  "known_at": "2026-01-07T18:30:00Z",
  "scheduled_open": "2026-01-07T19:30:00Z",
  "requested_quantity": 100,
  "state": "EXIT_QUEUED",
  "evidence_hash": "sha256:..."
}
```

```json
{
  "stop_version_id": "...",
  "managed_position_id": "...",
  "client_order_id": "...",
  "known_at": "...",
  "quantity": 100,
  "adjusted_stop": "99.50",
  "adjustment_factor": "1",
  "raw_stop": "99.50",
  "tick_size": "0.01",
  "source_candle_id": "...",
  "source_revision": "sha256:...",
  "request_hash": "sha256:..."
}
```

```json
{
  "broker_action_id": "...",
  "managed_position_id": "...",
  "action_kind": "REPLACE_STOP",
  "event_type": "CALL_STARTED",
  "client_order_id": "...",
  "request_hash": "sha256:...",
  "occurred_at": "...",
  "detail": {}
}
```

Allowed exit reasons are the closed v1 set `STOP_HIT`, `STRUCTURAL_DAMAGE`, `OPPOSING_TRAP`,
`MAX_HOLD`, and `EMERGENCY_FLATTEN`. The last is operator authority, not a strategy signal. Unknown
strings cannot enter an order path.

## Proposed versioned operational configuration

The implementation would add a new immutable configuration rather than editing Phase 1 thresholds:

```json
{
  "phase_3d_version": "3D.1.0",
  "environment": "SANDBOX",
  "protective_stop": {
    "order_type": "STOP_LOSS",
    "time_in_force": "GTC",
    "extended_hours": false,
    "replace_only_when_monotonic": true
  },
  "queued_exit": {
    "order_type": "MARKET",
    "time_in_force": "DAY",
    "cancel_stop_first": true
  },
  "recovery": {
    "same_client_query_count": 1,
    "automatic_write_retry_count": 0,
    "max_inflight_actions_per_position": 1
  },
  "exit_environment_flag": "WEBULL_SANDBOX_EXIT_ENABLED",
  "flatten_environment_flag": "WEBULL_SANDBOX_FLATTEN_ENABLED",
  "live_smoke_required_adjustment_factor": 1
}
```

The Phase 1 `max_hold_bars=40`, trail thresholds, damage threshold, confidence threshold, slippage,
and collision policy remain sourced from the existing versioned Phase 1 configuration and are not
duplicated or overridden here.

## Price and quantity rules

- All strategy prices remain split-adjusted Decimal values.
- Broker stop prices must be raw executable prices derived from an exact causal adjustment factor:
  `raw_stop = adjusted_stop / adjustment_factor`.
- The factor, source revision, source candle ID, known-at time, and instrument tick metadata must be
  persisted with each stop version.
- Missing, changed, non-finite, nonpositive, or unverified adjustment/tick evidence blocks the broker
  action. V1 live smoke tests are limited to factor-one evidence until corporate-action handling is
  separately approved.
- No local tick rounding rule is invented. The proposed request must already align with verified
  instrument tick metadata; otherwise preview/action is rejected.
- Quantity is a positive integer and may never exceed the absolute reconciled position.
- Every official order side must reduce the known position. A request that could increase, cross
  through zero, or reverse exposure is rejected before transport construction.
- Fractional shares remain excluded.

## Fixed action precedence

At each causal processing timestamp:

1. persist incoming broker evidence;
2. reconcile account, mapped orders, cumulative executions, and positions;
3. apply confirmed stop fills and determine remaining quantity;
4. resolve previously ambiguous/call-started actions;
5. release an already-queued full exit if eligible;
6. replace a monotonic protective stop when no exit is being released;
7. record holds and reports;
8. consider new entry submission last, only in `PAPER_ENABLED`.

At most one broker write for one managed position may cross a call boundary at a time.

Cancel, replace, and placement resolution uses one immediate authenticated same-client-ID detail
query after the SDK response or exception. V1 performs no hidden polling and no time-based retry. If
that single query cannot prove the terminal or exact requested state, the action is `AMBIGUOUS` and
the runtime halts. A later operator recovery command may reconcile it; it may not replay the write.

## Append-only persistence proposal

One new paired migration will add:

- `webull_managed_positions`: immutable ownership identity and source entry mapping;
- `webull_position_events`: append-only state, quantity, stop, and reason transitions;
- `webull_exit_intents`: causal Phase 1 or operator exit evidence and scheduled release;
- `webull_protective_stop_versions`: adjusted/raw stop, quantity, adjustment, tick, and request hash;
- `webull_broker_action_events`: `PREPARED`, `CALL_STARTED`, `ACKNOWLEDGED`, `REJECTED`,
  `AMBIGUOUS`, `NOT_SUBMITTED`, and `RECOVERED` for place/replace/cancel;
- `webull_flatten_authorizations`: one-use explicit operator evidence;
- `webull_exit_authorizations`: exact session/config capability arming evidence;
- `webull_position_reconciliations`: exact expected/actual orders, fills, and positions.

Existing redacted envelopes, broker events, cumulative executions, incidents, configuration hash,
code version, and session identity remain authoritative dependencies. Credentials, account IDs,
tokens, headers, signatures, and unredacted SDK objects may not enter new payloads.

## CLI proposal

```text
trading-system webull arm-exits ...                  # explicit two-factor sandbox arming
trading-system webull preview-protection ...
trading-system webull reconcile-position ...
trading-system webull recover-actions ...
trading-system webull position-report ...            # offline
trading-system webull flatten-position ...           # explicit two-factor sandbox action
```

Normal stops, replacements, and queued exits are produced only by immutable lifecycle evidence; the
CLI cannot accept an arbitrary stop price, quantity, direction, or exit reason. A separate internal
fixture command may seed fake-transport tests but is not packaged as operator functionality.

## Required tests

- long/short mirror symmetry for stop and full-exit mapping;
- stop request uses exact actual filled quantity and reducing side;
- no protective order exists before a confirmed entry fill;
- entry submission fails before transport unless exact Phase 3D exit authorization is armed;
- partial entry fill cancels its remainder before protecting the final reconciled quantity;
- long stop never decreases and short stop never increases;
- stale, future, revised, or incomplete trail evidence cannot replace a stop;
- structural damage, opposing trap, and max hold create one deterministic next-open exit intent;
- stop fill wins over queued exit at the same open;
- partial stop fill reduces the remaining quantity without duplicate execution;
- cancel must be confirmed before market exit placement;
- ambiguous cancel/replace/exit is queried once and never blindly retried;
- storage failure before `CALL_STARTED` cannot reach transport;
- restart recovers each unresolved action exactly once;
- unknown orders, unknown positions, side/sign, quantity, broker-ID, stop-price, and position mismatch
  halt without adoption;
- `DRAINING` blocks entries, keeps protection, and stops only when flat;
- emergency flatten requires both gates, exact identity, fresh reconciliation, and one-use evidence;
- no action can increase or reverse reconciled exposure;
- account IDs and secrets never appear in payloads, reports, exceptions, or test output;
- production hosts, options, OCO/brackets, partial strategy exits, and arbitrary operator orders remain
  unreachable by architecture tests;
- fake-transport lifecycle, restart soak, migration parity, install, Ruff, strict mypy, pytest, and CI.

## Explicit exclusions

- production endpoints, production credentials, real-money orders, or autonomous live trading;
- options, futures, crypto, event contracts, multi-leg orders, or exercise/assignment;
- profit targets, scale-outs, partial strategy exits, pyramiding, or averaging;
- portfolio-wide flatten, cross-symbol risk, margin, short-locate, or borrow policy;
- OCO, bracket, trailing-stop order types, extended hours, MOO, MOC, limit, or fallback orders;
- adoption or liquidation of unknown/pre-existing account positions;
- discretionary CLI prices, quantities, symbols, directions, or reasons;
- changes to Phase 1 thresholds, signals, trail formulas, sizing, or precedence;
- model probability, learned confidence, outcome label, or future data in any action path;
- deployment as an unattended external service.

## Exit criteria

Phase 3D offline implementation is complete only when a fake-transport session can progress from
entry fill through protection, monotonic replacement, every approved Phase 1 exit reason, flat
reconciliation, drain, halt, and restart without duplicate side effects. All broker writes must be
persist-first, deterministic, exposure-reducing, recoverable, redacted, and sandbox-only.

Phase 3D operational sandbox review passes only after the separately invoked captures in 3D-5 prove
the exact official response and netting semantics. No Phase 3D criterion authorizes production.

## Approval decisions required

Approval would authorize only the bounded sandbox implementation above. Please approve or amend:

1. exact reuse of Phase 1 stop, trail, structural-damage, opposing-trap, max-hold, and adverse-first
   behavior;
2. two-factor exit-subsystem arming as a prerequisite to entry, followed by broker-native
   `STOP_LOSS/GTC` protection after confirmed fills and monotonic same-ID replace;
3. `SELL` to close long and `BUY` to cover short, subject to redacted sandbox proof;
4. cancel-confirm-reconcile before a queued full-quantity `MARKET/DAY` exit;
5. stop-fill precedence and no simultaneous OCO/bracket/fallback order;
6. strict ownership with no adoption of unknown positions or orders;
7. `DRAINING` keeps protection and does not automatically flatten;
8. two-factor, one-position emergency flatten with query-before-retry behavior;
9. factor-one live smoke-test restriction until corporate-action/tick metadata handling is approved;
10. staged fake-transport implementation followed by separately authorized sandbox smoke tests;
11. continued prohibition of production, options, partial exits, portfolio actions, and ML authority.
