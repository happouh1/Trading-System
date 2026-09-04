# Phase 7B Range Research Replay Proposal v1

## Purpose

Phase 7B makes Phase 7A range boxes measurable in chronological offline experiments. It detects
boxes on successively completed prefixes, persists immutable box evidence, and creates descriptive
future-path records only after each configured horizon has closed.

## Inputs and causality

The replay accepts explicit `BaseBar` inputs containing a completed candle, causal ADR20, and
causal ATR10. It does not substitute the main feature engine's ATR20 for ATR10. Inputs must be one
strictly chronological symbol/timeframe series. Each prefix is evaluated independently, so later
candles cannot change whether an earlier box was known. Optional volume POC evidence is keyed to
the box-ending candle and remains subject to Phase 7A point-in-time validation.

## Descriptive outcomes

For each available configured horizon, `RangeBoxOutcome` records:

- close-to-close forward return from the box-ending close;
- maximum upside and downside excursions divided by box width;
- terminal close location strictly above, strictly below, or inside the box; and
- the exact future completed-candle IDs and label-availability time.

The standard specification horizons are 1/3/6/12/24/48 bars for 1H, 1/3/6/12/24 for 4H, and
1/3/5/10/20/60 for Daily. Weekly labels remain unresolved and are not emitted. These records do
not assume long or short direction and do not define success, failure, expectancy, or an entry.

## Persistence and restart behavior

Migration 053 adds append-only `range_boxes` and `range_box_outcomes`. Canonical payload hashes
make exact reruns idempotent and conflicting deterministic identities fail closed. Outcomes refer
to an already persisted box, and all records refer to an existing run.

## Authority boundary

Phase 7B is not wired into `CausalNarrativePipeline` or `ReplayOrchestrator`. It does not emit
pattern events, scores, decisions, alerts, options selections, trade plans, or broker operations.
Promotion requires an independently approved chronological experiment phase.
