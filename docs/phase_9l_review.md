# Phase 9L Review — Test-Only Upgrade Rehearsal

## Result

The repository can now rehearse the complete SQLite backup, copy migration, and restore-verification
sequence on explicitly test-only fixtures.

## Authority boundary

The real database is not an accepted input. Production migration, source writes, restore promotion,
credentials, network access, broker writes, sandbox execution, and live trading remain disabled.

## Exit criteria

- Only contained test-fixture paths and `TEST_ONLY_` revisions are accepted.
- The source is opened read-only and remains byte-identical.
- Backup and restored copies have identical hashes.
- The migrated copy contains the current required evidence tables.
- Existing table row counts survive migration unchanged.
- Upgraded and restored copies pass SQLite integrity and foreign-key checks.
- Repeated identical rehearsals are deterministic and do not overwrite artifacts.
- Tampered existing artifacts fail closed.
- CLI output is canonical machine-readable evidence.
- Focused and complete repository checks pass.

## Validation result

- Focused Phase 9K/9L tests: 12 passed.
- Dependency check: passed.
- Ruff: passed.
- Strict mypy: passed for 496 source files.
- Pytest: 781 passed; 108 existing dependency deprecation warnings.

All Phase 9L exit criteria are satisfied. No real database, broker, or trading action was performed.
