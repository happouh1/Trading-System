# Phase 9L Proposal — Test-Only Upgrade Rehearsal

Phase 9L proves the mechanical backup, migration, integrity-check, and restore sequence on disposable
SQLite fixtures. Inputs must be contained beneath `fixtures/upgrade-rehearsal` and carry a
`TEST_ONLY_` source revision. The real operator database is rejected by construction.

The rehearsal opens its source read-only, creates an online SQLite backup in an ignored local
workspace, migrates a separate copy through the repository's current migration set, and restores a
third copy from the backup. It verifies source-hash preservation, existing table row counts, all six
Phase 9A–9F evidence tables, SQLite integrity, foreign keys, and byte-identical backup restoration.

Outputs are content-bound, restart-safe evidence. They cannot be promoted over the source or used to
authorize a real migration, process launch, Webull access, sandbox execution, or live trading.
