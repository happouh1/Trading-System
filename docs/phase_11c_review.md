# Phase 11C review

Phase 11C adds deterministic post-close collection for the active prospective sandbox burn-in.

The collector reads immutable session evidence from SQLite in read-only mode, requires prior
same-session Webull verification, enforces the XNYS close and Phase 9Y window, derives operational
counts, requires causal runtime evidence beyond session creation and verification, and atomically
appends one content-hashed observation. Duplicate identical collection is idempotent; conflicting
recollection fails closed.

Operators must explicitly classify regime, symbols, timeframes, and strategy categories. Phase 11C
does not infer these labels, contact Webull, schedule itself, alter trading rules, promote a release,
or enable sandbox or live order submission.

The first real observation cannot be collected until the relevant XNYS session has completed.

## Validation

- Editable installation: unchanged packaging; the local recheck was blocked because the existing
  virtual environment lacks `setuptools.build_meta` and network access is disabled. The preceding
  Phase 11B GitHub CI installation passed.
- Ruff: passed.
- Strict mypy: passed across 530 source files.
- Pytest: 904 passed, with 108 upstream deprecation/future warnings.
- Real pre-close guard: rejected collection before the 2026-09-14 XNYS close without changing the
  burn-in observation file.
