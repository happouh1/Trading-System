# Phase 4B — Options Research and Contract Screening v1

## Status and authority

Phase 4B is a deterministic, point-in-time research layer. It converts an existing directional
candidate into either a ranked long-premium equity-option research result or an explicit rejection.
It cannot place, preview, replace, cancel, or simulate an option order. It does not import the
Webull adapter, paper runtime, decision engine, modeling, or learning packages.

Only two mappings are permitted: an upstream `LONG` candidate may screen standard equity calls,
and an upstream `SHORT` candidate may screen standard equity puts. Short option positions, spreads,
combinations, assignment decisions, exercise decisions, and broker connectivity are outside scope.

## Authoritative product constraints

Cboe describes stock and ETP options as physically settled and American style, and its equity
LEAPS material describes standard equity LEAPS as generally representing 100 shares. OCC product
and series reference files identify exercise style, classification, settlement, expiration, and
strike. Phase 4B accepts only records explicitly identified by the source as standard US equity,
multiplier 100, American exercise, and physical settlement. It does not infer missing attributes.
Adjusted/nonstandard deliverables are rejected. `LEAPS` is a system screening horizon, not an
exchange-listing classification.

References:

- Cboe Equity LEAPS: https://www.cboe.com/tradable_products/equity_indices/leaps_options/specifications
- Cboe Exchange Traded Stock: https://www.cboe.com/exchange-traded-stock
- OCC reference data: https://www.theocc.com/market-data/market-data-reports/other-market-data-info/data-sales

## Causal input contract

An `OptionChainSnapshot` contains one underlying, a timezone-aware `as_of`, underlying price,
canonical contract ordering, source, source revision, and at least one `OptionSeries`. Every quote
has an `observed_at` no later than snapshot `as_of`. A request and snapshot must share the exact
underlying and timestamp. Unknown JSON fields are rejected. Input order must already be canonical
by expiration, right, strike, and contract ID. IDs must be unique. Values are never forward-filled.
Provider IV and Greeks are observations only; Phase 4B does not calculate or interpolate them.

## Deterministic screening

```text
DTE = expiration - UTC_DATE(request.as_of)
midpoint = (bid + ask) / 2
spread = ask - bid
relative_spread = spread / midpoint
maximum_debit = ask * multiplier
```

A contract receives stable rejection codes for every failed product, direction, DTE, freshness,
bid, volume, open-interest, spread, IV, delta, sign, or debit gate. All values in
`config/options.phase4b.v1.yaml` are **TUNABLE RESEARCH HYPOTHESES**, not validated edges:

- quote age at most 900 seconds;
- bid at least 0.05, volume at least 10, open interest at least 100;
- absolute spread at most 0.50 and relative spread at most 0.15;
- 45-DTE: 35–55 DTE, target 45, absolute delta 0.55–0.75, target 0.65;
- LEAPS: 365–1,095 DTE, target 730, absolute delta 0.70–0.90, target 0.80.

Eligible contracts rank by target-DTE deviation, target-delta deviation, relative spread,
descending open interest, then contract ID. The first is the research selection. Results preserve
per-contract reasons, configuration hash, request ID, snapshot ID, and known-at timestamp.

## Persistence and omissions

Migration 018 adds append-only chain, series, and result tables. Canonical payloads and hashes make
repeated insertion idempotent and conflicting identity reuse an error. No credential, account ID,
order ID, or broker response belongs in these tables.

Phase 4B has no pricing model, theoretical Greeks, earnings/dividend/rate adjustments, volatility
surface, options trade simulation, P&L, exercise/assignment, rolls, recommendations, or routing.
Historical validation requires a separately approved phase and point-in-time licensed data.

## Exit criteria

- Immutable contracts enforce causal timestamps, canonical ordering, and deterministic identity.
- Strict versioned configuration cannot enable broker writes or options execution.
- Both horizons and every screening gate have tests and explicit reasons.
- Append-only persistence survives restart and detects conflicts.
- The CLI is offline, strict, deterministic, and optionally persistent.
- Architecture tests prevent imports of authority-bearing packages.
- Documentation is updated and the complete quality suite passes.

