# Phase 8H Review — Test-Only Replication Collection

## Decision

Phase 8H implements an offline, synthetic-data reference for collecting prospective predictions,
recording outcomes after their availability, and freezing a deterministic dataset manifest. It does
not establish real blinding, independent replication, statistical efficacy, or production authority.

## Implemented scope

- strict immutable configuration with every authority flag disabled;
- immutable collection, prediction, outcome, and freeze-manifest contracts;
- a forward-only lifecycle from registration through collection, outcome completion, and freeze;
- causal time gates for prediction capture and outcome availability;
- exact Decimal net-return calculation from gross return and itemized costs;
- append-only SQLite tables, lifecycle events, deterministic identifiers, and payload hashes;
- restart, mutation, ordering, and tamper checks; and
- an architecture boundary preventing Phase 8 research components from entering authority packages.

Only dataset identifiers beginning with `TEST_ONLY_` are accepted. A frozen test manifest remains
nonreleased and cannot be presented as a real replication result.

## Deliberately excluded

- real market-data or point-in-time universe providers;
- real prospective collection or a CLI for operating it;
- authenticated collector, outcome-steward, or reviewer roles;
- encrypted outcome storage, trusted timestamps, signatures, or access attestations;
- an outcome-reading or Phase 8G analysis adapter;
- efficacy, strategy selection, parameter changes, alerts, brokerage, or live trading.

SQLite separation is an integrity aid for tests, not a security or blinding boundary.

## Exit assessment

The test-only reference exits when strict configuration, causal lifecycle, persistence, restart,
tamper, architecture, lint, type-check, and complete test suites pass. Real Phase 8H remains blocked
until the provider, universe, access-control, encryption, role, timestamp, retention, and missing-data
questions in `docs/open_questions.md` receive independent approval.
