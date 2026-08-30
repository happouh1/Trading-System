# Phase 4C — Point-in-Time Options Validation v1

## Purpose and authority

Phase 4C evaluates Phase 4B long-premium selections against later, point-in-time quotes. It is a
research backtest foundation, not an options strategy, recommendation, pricing model, or execution
system. Exit timing and reason are supplied by the research dataset; the engine does not invent an
exit signal. Broker access, order operations, exercise, assignment, and theoretical pricing remain
unavailable.

## Market constraints

Options Industry Council education notes that the bid/ask spread is a material part of an option
quote. The conservative fill model therefore enters a long option at ask plus configured slippage
and exits at bid minus configured slippage. It never uses midpoint as an executable fill.

Cboe states that single-stock options are American style and physically settled, while OCC's
options disclosure explains that standardized options can lose the entire premium and have
material exercise/expiration risks. Because Phase 4C does not model physical delivery, early
exercise, or assignment, it rejects expiration-day and post-expiration valuations.

References:

- Options Industry Council, bid and ask: https://www.optionseducation.org/news/understanding-the-bid-and-ask-prices-for-options
- Cboe stock options: https://www.cboe.com/exchange-traded-stock
- Cboe settlement discussion: https://www.cboe.com/insights/posts/why-option-settlement-style-matters
- OCC options disclosure: https://www.theocc.com/company-information/documents-and-archives/options-disclosure-document

## Input and causal rules

Each `OptionValidationCase` references one persisted Phase 4B result and its selected contract. It
contains an entry mark and a later exit mark with exact timestamps, source revisions, and identical
contract metadata.

Required chronology:

```text
screen_known_at < entry_quote.observed_at <= entry_mark.as_of
entry_mark.as_of < exit_quote.observed_at <= exit_mark.as_of
UTC_DATE(exit_mark.as_of) < expiration
```

Entry and exit snapshots must differ. Direction must still map `LONG` to call and `SHORT` to put.
Missing values are never filled, quotes are never interpolated, and provider Greeks have no role in
valuation. Unknown JSON fields fail ingestion.

## Fill and return model

For quantity `q`, multiplier `m`, configured premium slippage `s`, and fee per contract per side
`f`:

```text
entry_fill = entry_ask + s
exit_fill = max(0, exit_bid - s)
entry_debit = entry_fill * m * q
gross_pnl = (exit_fill - entry_fill) * m * q
fees = 2 * f * q
net_pnl = gross_pnl - fees
return_on_debit = net_pnl / entry_debit
```

The initial slippage of 0.01 premium points and zero fee are **TUNABLE RESEARCH HYPOTHESES**. The
bid/ask sides and exclusion policies are locked for Phase 4C. A stale entry or exit quote is an
`EXCLUDED` result with a reason code, not a manufactured loss, win, or price. A valid zero bid exits
at zero and realizes the full debit loss before fees.

## Aggregate metrics

Completed cases produce count, wins/losses/breakeven, win rate, total and mean net P&L, mean and
median return on debit, and maximum drawdown over chronologically ordered case exits. Exclusions are
counted separately. Undefined rates remain null. Results and reports use deterministic IDs,
canonical JSON, configuration hashes, and source revisions.

This phase does not claim portfolio performance. Different cases may overlap in time, capital is not
allocated, and CAGR, Sharpe, exposure, margin, and buying power are intentionally absent.

## Persistence and safety

Migration 019 adds append-only validation-case, validation-result, and backtest-report tables.
Database-backed validation requires the referenced Phase 4B result to exist. Repeated identical
inserts are idempotent; conflicting identity reuse fails.

The package continues to be barred from Webull, paper, decisions, learning, and modeling imports.
There is no options order schema, transport, credential, or broker response in Phase 4C.

## Exit criteria

- Conservative fill formulas and full-premium-loss behavior are exact and tested.
- Causal chronology, immutable contract identity, and pre-expiration boundaries are enforced.
- Stale observations are excluded with explicit reasons.
- Metrics are deterministic, chronological, and null-safe.
- CLI and SQLite persistence are offline, restart-safe, and append-only.
- Unit, integration, anti-lookahead, migration, architecture, lint, typing, and full tests pass.

