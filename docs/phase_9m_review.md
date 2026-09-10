# Phase 9M Review — Signed Database-Upgrade Review Evidence

## Result

The repository can now build and independently verify a cryptographically bound database-upgrade
review package without performing the proposed operation.

## Authority boundary

Verified signatures demonstrate review evidence only. They do not authorize or perform a real
backup, migration, restore promotion, process launch, Webull access, or trading.

## Exit criteria

- Requests require a backup-required Phase 9K plan and verified Phase 9L rehearsal.
- Plan and rehearsal required-table inventories must match.
- Backup, recovery, and quiescence procedures are operator-supplied content hashes.
- Maintenance windows and reviewer roles have no repository defaults.
- Ed25519 signatures bind every material request field.
- Reviewer principals must remain distinct across roles.
- Missing evidence is `INCOMPLETE`; invalid or out-of-window evidence is `BLOCKED`.
- Complete valid evidence is only `REVIEW_EVIDENCE_VERIFIED` and grants no authority.
- Configuration weakening fails closed.
- Focused and complete repository checks pass.

## Validation result

- Focused Phase 9K–9M tests: 19 passed.
- Dependency check: passed.
- Ruff: passed.
- Strict mypy: passed for 498 source files.
- Pytest: 788 passed; 108 existing dependency deprecation warnings.

All Phase 9M exit criteria are satisfied. No database, network, broker, or trading action was
performed.
