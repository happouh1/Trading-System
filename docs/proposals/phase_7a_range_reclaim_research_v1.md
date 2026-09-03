# Phase 7A Range-Reclaim Research Proposal v1

## Purpose

Phase 7A translates the useful, testable portion of the discretionary “Potter Box” concept into a
deterministic research contract named `RANGE_RECLAIM_CONTINUATION_V1`. It does not assert that the
strategy is profitable and does not alter decisions, scoring, options selection, paper orders, or
broker authority.

## Mechanical interpretation

A range box begins with an existing accepted `BaseCandidate`. Phase 7A then requires distinct
boundary rotations rather than raw touch counts. A lower-boundary episode begins when a completed
candle trades within `contact_tolerance_adr * ADR20` of the box floor. Consecutive lower contacts,
including contacts separated only by neutral candles, remain one episode until an upper contact
occurs. Upper episodes use the symmetric rule. A candle contacting both boundary bands is
ambiguous and rejects the candidate. Initial tunable defaults require two lower and two upper
episodes.

The geometric midpoint is exactly `(upper + lower) / 2`. It is not called cost basis. An optional
volume point of control is a separate observed input carrying a source revision, method version,
and `known_at`; it is never inferred from aggregate OHLCV.

## Causality and nesting

Only completed, strictly chronological, nonoverlapping candles from one symbol and timeframe are
accepted. The box becomes known at the final candle close. Optional volume evidence must already
be known. A parent box must be a strictly wider containing box for the same symbol, use the same or
higher timeframe, and be known strictly before the child. The narrowest qualifying parent wins;
its deterministic ID breaks ties.

## Authority boundary

Phase 7A is an isolated research primitive. It adds no database migration or CLI, does not enter
the replay pipeline, does not emit a `Decision`, and cannot submit, preview, replace, or cancel a
broker order. Breakout, reclaim, acceptance, runway, scoring, and trade management remain the
responsibility of their existing independently versioned engines until a later approved phase.

## Unsupported claims

No promise of a new high, high win rate, mandatory gap fill, institutional cost basis, or causal
edge is encoded. Those are hypotheses requiring chronological out-of-sample evaluation.
