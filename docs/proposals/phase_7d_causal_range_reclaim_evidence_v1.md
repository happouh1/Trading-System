# Phase 7D Causal Range-Reclaim Evidence Proposal v1

## Purpose

Phase 7D defines the smallest causal link between an already-known Phase 7A range box and the
existing deterministic reclaim state machine. The link is a research evidence record, not a trade
signal, entry, recommendation, or performance claim.

## Exact matching rule

A link is emitted only when all conditions are true:

1. The box and event have the same symbol and timeframe.
2. The reclaim event is known strictly after the box.
3. The event family is `RECLAIM`, its state is `ACCEPTED`, and its sole reason code is
   `RECLAIM_ACCEPTED`.
4. A `BULLISH_RECLAIM`/`LONG` event exactly equals the box's lower boundary, or a
   `BEARISH_RECLAIM`/`SHORT` event exactly equals the box's upper boundary.
5. The event retains at least one causal evidence-candle ID.

No price tolerance is used. Every matching overlapping box is retained; the system does not select
the most favorable box. Input order is normalized and duplicate identities fail closed.

## Provenance and persistence

Each immutable record preserves the box, event, observation, series, direction, boundary,
reference price, both known-at times, event version, three configuration hashes, code version, and
candle evidence. Migration 055 stores it append-only with foreign keys to the source box, pattern
event, and run.

## Authority boundary

Phase 7D defines no entry time or price, stop, target, exit, holding period, costs, score, alert,
option contract, broker route, or live behavior. Any such use requires a later separately reviewed
phase and successful Phase 7C chronological evidence gates.
