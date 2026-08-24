# Proposed Phase 3B paper-trading readiness v1

Status: **APPROVED AND IMPLEMENTED — VALIDATION PENDING**

## Purpose

Phase 3B prepares the deterministic Phase 1 engine to operate continuously against completed market
data while sending intents only to an internal simulated paper adapter. It validates operational
safety, causality, restart behavior, and auditability before any external paper-broker integration.

This phase does not authorize real-money trading, broker connectivity, options, model-driven
decisions, or changes to the approved strategy rules.

## Proposed bounded scope

1. Introduce immutable contracts for completed-bar envelopes, runtime sessions, heartbeats, order
   intents, adapter acknowledgements, paper orders, fills, cancellations, reconciliation records,
   incidents, and kill-switch events.
2. Add provider-neutral protocols for completed-bar input and paper execution. Implement only:

   - a deterministic fixture/file bar source;
   - the existing Phase 1 execution simulator behind a paper-adapter boundary;
   - a rejecting adapter used by safety and failure tests.

3. Run the existing causal pipeline only after a finalized candle closes. Preserve the established
   higher-timeframe availability ordering. Corrections to an already-consumed bar create a new source
   revision and a new runtime session; they never rewrite prior decisions or paper events.
4. Convert only an existing eligible Phase 1 `TradePlan` into an `OrderIntent`. Phase 3B cannot create
   a setup, alter confidence, change sizing, relax a gate, or reinterpret `NO_TRADE`.

   Implementation amendment: `paper stage-decision` performs this conversion only from an immutable
   persisted directional decision in an identity-matched SHADOW session. It uses an explicit causal
   as-of time, schedules the first XNYS open after the decision, rejects stale decisions, records the
   source decision ID, and never calls an adapter.
5. Persist every intent before adapter submission. Use deterministic client intent IDs so replay,
   retries, and restart cannot duplicate an order.
6. Add a runtime state machine:

   ```text
   CREATED -> STARTING -> SHADOW -> PAPER_ENABLED -> DRAINING -> STOPPED
                                  \-> HALTED
   ```

   `SHADOW` records the exact intents that would be submitted but cannot submit them. Enabling
   `PAPER_ENABLED` requires an explicit CLI flag and a validated paper configuration.
7. Add restart recovery. On startup, load the last committed completed-bar checkpoint, pending
   intents, simulated orders, fills, open positions, and kill-switch state. Resume only when the
   stored code/config/data/calendar identity matches.
8. Add deterministic reconciliation between internal intent/order/fill state and the simulated
   adapter. Any unknown order, impossible transition, quantity mismatch, or position mismatch halts
   new submissions and records an incident.
9. Add operational health and safety gates:

   - reject incomplete, duplicate, out-of-order, non-XNYS, or stale bars;
   - reject naive timestamps and mismatched symbol/timeframe identities;
   - halt on storage failure, state corruption, adapter ambiguity, or reconciliation mismatch;
   - support manual, startup, stale-data, reconciliation, and internal-error kill-switch reasons;
   - cancel only simulated pending orders when draining; never infer an unconfirmed cancellation;
   - permit no new intents while halted, but continue append-only audit recording.

10. Add `trading-system paper` commands for `start`, `resume`, `status`, `reconcile`, `halt`,
    `drain`, and `report`. Default mode is `SHADOW`.
11. Add SQLite migrations and repositories for sessions, checkpoints, heartbeats, intents, adapter
    messages, simulated orders/fills, reconciliation records, incidents, and kill-switch events.
12. Add deterministic fixture, unit, property, integration, persistence, restart, idempotency,
    causality, failure-injection, and architecture-boundary tests.

## Initial tunable operational defaults

- heartbeat interval: 30 seconds;
- heartbeat considered stale: 120 seconds;
- completed-bar arrival tolerance: 120 seconds after expected close;
- adapter acknowledgement timeout: 5 seconds;
- retry count for an unambiguously unsubmitted intent: 2;
- reconciliation interval: 60 seconds;
- maximum consecutive data-validation failures before halt: 1;
- default runtime mode: `SHADOW`;
- default adapter: internal deterministic simulator;
- paper risk budget and strategy thresholds: unchanged Phase 1E configuration.

These values control operations only. They do not alter pattern, entry, stop, trail, exit, scoring,
or sizing formulas.

## Deterministic intent and event rules

```text
intent_id = hash(runtime_session_id, trade_plan_id, scheduled_bar_open, intent_version)

persist intent -> commit -> submit once -> append acknowledgement -> append order/fill events
```

An identical intent is idempotent. A conflicting payload with the same identity is rejected and
halts the session. Timeout without definitive adapter state is `AMBIGUOUS`, not a failed order and
not permission to resubmit. All timestamps are timezone-aware UTC; exchange scheduling uses XNYS.

At a shared completed-candle timestamp, processing retains the existing deterministic order:
Weekly, Daily, 4H, 1H snapshot completion; signal evaluation; lifecycle updates; checkpoint commit.

## Model boundary

Phase 3A probabilities may be attached to a paper report as separately labeled `RESEARCH_ONLY`
evidence after their artifact and feature identity verifies. They cannot enter decision candidates,
gates, confidence, trade plans, quantities, order intents, exits, or kill-switch decisions. The paper
runtime and adapter packages cannot be imported by the Phase 1 decision engine.

## Required acceptance tests

- shadow mode can never invoke adapter submission;
- completed bars yield the same decisions and simulated events as deterministic replay;
- incomplete and future higher-timeframe candles remain unavailable;
- duplicate input and restart produce no duplicate intent, order, or fill;
- ambiguous acknowledgement never causes blind resubmission;
- reconciliation mismatch and stale data halt submissions;
- halted sessions cannot emit new intents until a separately recorded operator resume;
- state recovery reproduces the same hash and next event as uninterrupted execution;
- source/config/code/calendar changes require a new runtime session;
- storage failure cannot submit an intent that was not durably recorded;
- model data cannot influence any execution-authority package;
- reports distinguish shadow intents, paper orders, fills, rejected actions, and incidents;
- installation, Ruff, strict mypy, pytest, and CI all pass.

## Explicit exclusions

- Alpaca, Interactive Brokers, Tradier, or any other external API integration;
- credentials, secrets, OAuth, streaming vendor data, or network retry policy;
- real-money orders or a live execution mode;
- options chains, contracts, Greeks, volatility models, or multi-leg strategies;
- portfolio optimization, cross-symbol exposure limits, margin, borrow, or locate handling;
- model promotion, model-driven decisions, online learning, or automatic retraining;
- changes to strategy thresholds or historical records;
- production deployment, alert delivery, dashboards, or service-level guarantees.

## Exit criteria

Phase 3B is complete only when a fixture-driven session can run in shadow and simulated-paper modes,
restart without duplicated side effects, halt safely under every declared failure, reconcile exactly,
and reproduce the offline replay narrative for identical completed candles. All records must be
immutable, causal, versioned, and attributable to one runtime identity. Full CI must pass.

## Approval decisions required

Approval would authorize only the bounded internal paper-readiness layer above. Please approve or
amend:

1. internal simulator only, with external paper brokers deferred;
2. default `SHADOW` mode and explicit enablement for simulated paper submissions;
3. persist-before-submit, deterministic intent IDs, and no blind ambiguous retries;
4. fail-closed halt behavior and the initial tunable operational thresholds;
5. exact parity with existing Phase 1 decisions, plans, sizing, and execution rules;
6. restart/reconciliation/audit persistence and the proposed CLI surface;
7. continued absolute separation of Phase 3A probabilities from trading authority.
