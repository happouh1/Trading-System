# Phase 9K Proposal — Read-Only Database Upgrade Planning

Phase 9K adds a deterministic, offline inspection step for the local operator database. It verifies
SQLite integrity, inventories the existing schema, and compares it with the six evidence tables used
by the Phase 9I and 9J dashboard. The result is `NOT_REQUIRED`, `REQUIRED`, or `BLOCKED`.

The plan hashes both the database file and its canonical schema inventory. When an upgrade is
required, it says that a backup is mandatory and lists the missing tables. It does not create that
backup, execute migrations, open a writable connection, load credentials, contact Webull, start a
process, or enable trading.

This phase deliberately separates discovery from mutation. A later reviewed phase must define the
backup destination, recovery procedure, exclusive-access requirement, and explicit operator
confirmation before the real database can be changed.
