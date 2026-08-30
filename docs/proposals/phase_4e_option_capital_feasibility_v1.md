# Phase 4E option capital-feasibility proposal v1

## Authority

Phase 4E is an offline research ledger over immutable Phase 4C cases and results. It answers one
narrow question: could the externally supplied, fixed-quantity cases have been funded by an
externally supplied starting-cash balance? It has no brokerage connectivity, execution authority,
allocation optimizer, quantity sizing, strategy promotion, or live decision path.

## Deterministic policy

For each completed case, entry cash required is Phase 4C `entry_debit + fees / 2`. Exit cash credit
is that entry cash plus Phase 4C `net_pnl`. Excluded cases are recorded without consuming cash.
The ledger uses exact decimal arithmetic and never permits negative cash or deployed capital.

Events are ordered by their exact timezone-aware timestamps. All entries sharing a timestamp form
one indivisible batch. If the batch exceeds available cash, every entry in that batch is rejected;
the engine never favors a case by symbol, input order, score, or ID. At a timestamp containing both
entries and exits, the entry batch is evaluated first, so same-time exit proceeds cannot finance an
entry whose causal ordering is otherwise unknown.

## Outputs and limitations

The append-only report includes starting and ending cash, realized net P&L, maximum deployed cash,
peak concurrent accepted positions, accepted/rejected/excluded counts, and canonical event IDs.
Intermediate option marks are unavailable. Consequently Phase 4E does not report mark-to-market
drawdown, CAGR, Sharpe, volatility, exposure percentages, margin utilization, or portfolio returns.

This proposal does not resolve buying-power treatment for spreads, short premium, assignment,
exercise, settlement timing, quote size, or margin. Those products remain unsupported.

## Exit criteria

- Strict configuration prevents authority expansion.
- Input permutations produce identical reports and event order.
- Simultaneous insufficient entry batches are rejected in full.
- Entries precede exit credits at identical timestamps.
- Cash and deployed balances reconcile exactly and never become negative.
- Excluded cases consume no capital.
- Runs, events, and reports are append-only, idempotent, and conflict detecting.
- Ruff, strict mypy, pytest, and architectural boundary checks pass.
