# Phase 5A unified operations proposal v1

## Purpose and authority

Phase 5A provides one offline control plane for inspecting evidence produced by the completed
research, modeling, paper, Webull Sandbox, portfolio, and options subsystems. It does not invoke
those subsystems, execute a workflow, load broker credentials, make a trading decision, promote a
model, or submit an order.

## Readiness model

The strict configuration declares seven required components and the append-only SQLite tables that
constitute minimum durable evidence for each one. An inspection request binds every component to an
explicit database label and path, a timezone-aware `known_at`, and a source revision.

Source databases are opened with SQLite read-only mode. For every required table the inspector
records existence, row count, and a monotonic `(count, maximum rowid)` marker. Missing databases,
missing tables, and empty required tables fail closed. Paper and Webull Sandbox also require their
latest persisted reconciliation to be matched. No row is created or repaired in a source database.

All seven component records are required. The overall manifest is `READY` only when every component
is `READY`; otherwise it is `NOT_READY` and contains namespaced reasons. Readiness means only that
minimum persisted operational evidence exists. It does not mean profitable, safe for live trading,
or approved for capital deployment.

## Persistence and replay

The registry database stores immutable manifests and their component evidence under deterministic
IDs and canonical payload hashes. Repeating the same inspection is idempotent. A conflicting payload
under an existing identity fails rather than overwriting evidence. Physical source paths are not
stored in the manifest; database labels and evidence fingerprints are stored instead.

## Exit criteria

- Configuration cannot enable workflows, broker writes, live trading, or automatic promotion.
- Source databases are opened read-only.
- Every configured component is required exactly once.
- Missing or empty evidence and unmatched latest reconciliations fail closed.
- Input ordering cannot change evidence or manifest identities.
- Persistence is append-only, restart-safe, idempotent, and conflict detecting.
- The operations package has no strategy, broker, model, paper, portfolio, or options dependency.
- Ruff, strict mypy, architectural tests, migrations, and the full pytest suite pass.
