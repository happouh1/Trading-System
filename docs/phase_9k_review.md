# Phase 9K Review — Read-Only Database Upgrade Planning

## Result

The desktop operator home now checks the local SQLite schema and explains whether preparation is
needed before newer operational evidence can be recorded.

## Authority boundary

The inspector opens SQLite with `mode=ro`. It never creates a backup, runs a migration, writes to the
database, loads credentials, uses the network, contacts a broker, or enables sandbox or live trading.

## Exit criteria

- Missing, invalid, legacy, and current databases produce deterministic fail-closed plans.
- SQLite `quick_check` must pass before an upgrade can be classified as required.
- The database and schema are content hashed for later review.
- Every required Phase 9A–9F evidence table is identified explicitly.
- A required upgrade mandates a backup but does not create one.
- Inspection leaves the database byte-identical.
- The desktop dashboard remains local, static, script-free, and secret-free.
- Focused and complete repository checks pass.

## Validation result

- Real local database: `AVAILABLE`; SQLite integrity `ok`.
- Real plan: `REQUIRED`; all six newer evidence tables are absent and backup is required.
- Real inspection: source and schema hashes recorded; no migration or database write performed.
- Launcher self-test: passed.
- Focused desktop tests: 30 passed.
- Dependency check: passed.
- Ruff: passed.
- Strict mypy: passed for 494 source files.
- Pytest: 775 passed; 108 existing dependency deprecation warnings.

All Phase 9K exit criteria are satisfied. No database migration or trading authority was added.
