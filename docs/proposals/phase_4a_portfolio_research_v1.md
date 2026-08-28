# Phase 4A portfolio and strategy-classification proposal v1

Status: **AUTHORIZED FOR DETERMINISTIC RESEARCH IMPLEMENTATION**

## Purpose and authority

Phase 4A evaluates immutable equity trade candidates in portfolio context. It does not alter Phase 1
signals or sizing, contact a broker, route an order, price an option, select an option contract, or
authorize long-term investment decisions. Results are append-only research assessments.

## Inputs and classification

Every assessment uses one explicit `PortfolioState` and one `PortfolioCandidate` with the same
timezone-aware timestamp. Candidates carry the upstream plan ID, direction, entry, stop, quantity,
planned holding sessions, point-in-time average daily dollar volume, sector, and source revision.
Missing liquidity or sector evidence fails closed.

Initial holding boundaries are **TUNABLE**: `INTRADAY` is at most 1 session, `SWING` is 2–20,
`POSITION` is 21–126, and `LONG_TERM_RESEARCH` is more than 126 sessions. Long-term classification
is research only. Its risk budget is zero because no point-in-time fundamental model exists.

## Mandatory gates

Candidates are evaluated in canonical `(known_at, candidate_id)` order. The engine rejects duplicate
open or pending symbols; position-count breaches; price, dollar-volume, or participation failures;
gross, absolute-net, position, sector, or strategy-risk breaches; and every long-term classification.

Checked-in **TUNABLE** defaults are: minimum price `$2`, minimum average daily dollar volume
`$5,000,000`, maximum participation `1%`, 10 positions, 100% gross exposure, 60% absolute net
exposure, 10% single-position exposure, and 25% sector exposure. Risk budgets are 0.5% intraday,
1.0% swing, 0.75% position, and zero long-term. They are research fixtures, not validated edge.

Exposure uses absolute marked notional divided by explicit equity. Net exposure is signed long minus
short notional divided by equity. Candidate risk is absolute entry-stop distance times quantity
divided by equity. Phase 4A does not model leverage, borrow, margin, taxes, correlation, or Greeks.

## Determinism, persistence, and exit

Assessments use content-derived IDs, sorted reason codes, exact configuration hashes, and canonical
JSON. SQLite stores states and assessments append-only; identical replays are idempotent and conflicts
fail. Exit requires strict-config, classification, symmetry, every mandatory gate, ordering,
persistence/restart, CLI, architecture, Ruff, mypy, and pytest coverage.

Phase 4B options research requires a separate proposal and is not authorized by Phase 4A.
