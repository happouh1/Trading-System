# Phase 4C Review

## Scope

Phase 4C adds point-in-time validation of Phase 4B long-premium selections using later supplied
quotes and externally supplied exit boundaries. It does not generate trading exits or communicate
with a broker.

## Implemented

- Versioned validation configuration with locked research-only authority.
- Immutable marks, validation cases/results, metrics, and reports.
- Strict post-signal entry, post-entry exit, quote-known-at, metadata, and expiration guards.
- Ask-plus-slippage entry and bid-minus-slippage exit with nonnegative exit floor.
- Explicit stale-quote exclusions and deterministic aggregate metrics.
- Offline CLI validation/backtest commands.
- Migration 019 with append-only, restart-safe persistence and Phase 4B foreign keys.
- Unit, integration, persistence, conflict, chronology, migration-parity, and architecture coverage.

## Explicitly unavailable

Automatic exit rules, expiry settlement, exercise, assignment, underlying delivery, option pricing,
volatility surfaces, contract rolls, multi-leg positions, portfolio capital, and broker operations
remain outside scope.

## Review status

Local implementation is complete and ready for review. Validation on Python 3.12.13:

- editable package build/install passed against the existing dependency environment;
- Phase 4C configuration validation passed;
- `python -m ruff check .` passed;
- strict `python -m mypy` passed for 189 source files;
- `python -m pytest` passed all 316 tests;
- `git diff --check` passed with Windows LF-to-CRLF notices only.

The 108 pytest warnings are existing scikit-learn/joblib deprecation notices. Remote CI remains a
post-commit review step.
