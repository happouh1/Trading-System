# Phase 4D Review

## Scope

Phase 4D adds deterministic expanding walk-forward evaluation for supplied Phase 4C option cases.
It separates development from test access and has no optimization, strategy-promotion, portfolio,
or execution authority.

## Implemented

- Strict research-only Phase 4D configuration and deterministic experiment identity.
- Expanding train/validation/test folds with separate embargoes.
- UTC screening-date assignment and exit-label availability checks at each cutoff.
- Case-level fold metrics with minimum-sample and overlapping-capital disclosures.
- `DEFINED -> DEVELOPMENT_EVALUATED -> FROZEN -> TEST_EVALUATED -> COMPLETE` lifecycle.
- Freeze hash binding definition, folds, and development evaluations before test access.
- Migration 020 and append-only definitions, folds, assignments, evaluations, and transitions.
- Offline CLI configuration, definition, development, freeze, test, completion, and status commands.
- Unit, integration, determinism, anti-lookahead, restart, conflict, migration, and architecture tests.

## Explicitly unavailable

Automatic parameter selection, strategy exits, portfolio capital allocation, performance claims,
expiration/exercise/assignment, multi-leg options, and broker operations remain unavailable.

## Review status

Local implementation is complete and ready for review. Validation on Python 3.12.13:

- Phase 4D configuration validation passed;
- `python -m ruff check .` passed;
- strict `python -m mypy` passed for 193 source files;
- `python -m pytest` passed all 325 tests;
- `git diff --check` passed with Windows LF-to-CRLF notices only.

The 108 pytest warnings are existing scikit-learn/joblib deprecation notices. The active editable
package imports from this repository. A fresh isolated editable reinstall could not finish locally
because this virtual environment lacks setuptools and its build-dependency download stalled; CI's
clean installation remains the authoritative post-commit installation check.
