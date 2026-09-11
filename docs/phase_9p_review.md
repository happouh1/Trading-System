# Phase 9P Review — Signed Backup-Authorization Evidence

## Result

The repository can now create and independently verify cryptographically bound review evidence for
an exact Phase 9O backup manifest without producing an executable capability.

## Exit criteria

- Only review-ready manifests with exact source and target identities are accepted.
- Requests bind the complete manifest, proposed component, nonce, roles, and bounded window.
- Ed25519 signatures cover every material field and signing time.
- Credentials, time windows, required roles, and principal separation fail closed.
- Missing, invalid, modified, duplicate, and expired evidence are distinguished deterministically.
- Configuration weakening is rejected.
- Results are immutable canonical JSON with every operational action false.
- Focused and complete repository checks pass.

## Validation result

- Focused Phase 9P tests: 7 passed.
- Dependency check: passed.
- Ruff: passed.
- Strict mypy: passed for 504 source files.
- Pytest: 809 passed; 108 existing dependency deprecation warnings.
- Desktop launcher self-test: passed.

No backup, database, filesystem, process, network, broker, sandbox, or trading action was performed.
