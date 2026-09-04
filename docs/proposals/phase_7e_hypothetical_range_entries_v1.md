# Phase 7E Hypothetical Range Entries Proposal v1

## Purpose

Phase 7E converts Phase 7D evidence into a measurable research entry proxy without creating a
decision or order. It inherits the existing Phase 1 next-open execution assumptions so the system
does not maintain two incompatible fill models.

## Entry protocol

For each evidence record, select the earliest completed historical candle in the same symbol and
timeframe whose open is at or after the evidence `known_at`. ATR20 and ADR20 must be finite,
positive, and known no later than the evidence. If no later candle is present, emit nothing because
the record is not yet mature; do not infer that a future candle will never arrive.

The simulated adverse slippage is:

`max(open × 1 / 10,000, ATR20 × 0.02)`

Add it for a long and subtract it for a short. The adverse opening gap is measured from the matched
range boundary and divided by ADR20. If it is greater than 0.25 ADR, record
`CANCELLED_ADVERSE_GAP` with no fill; otherwise record `FILLED`.

The 1 bp, 2% ATR20, and 0.25 ADR20 values are initial tunable defaults inherited from the Phase 1
execution simulator. Any change requires a new configuration hash and versioned experiment.

## Limitations and authority

This is an OHLCV research proxy. It has no point-in-time bid/ask spread, depth, market impact,
currency fee, borrow cost, partial fill, or option-contract cost. It defines no exit, expectancy,
score, alert, recommendation, broker operation, or live behavior.
