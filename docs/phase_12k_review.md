# Phase 12K review

Phase 12K is the storage-capacity safety layer following the Phase 12J evaluation dashboard.

Acceptance criteria:

1. Configuration rejects evidence-deletion, broker, network, credential, live-trading, and
   promotion authority.
2. SQLite is opened read-only and retained database bytes remain unchanged.
3. Database and SQLite page allocation are measured without reading the full database into memory.
4. Sidecar sizes, filesystem free space, and current-size backup-copy headroom are reported.
5. Threshold ordering is validated and status reason codes are deterministic.
6. The local JSON artifact is written by same-directory atomic replacement.
7. No capacity result changes signals, decisions, schedules, broker state, or retained evidence.

Phase 12K does not implement retention or evidence deletion. Those require a separate reviewed
policy that preserves the immutable prediction and audit contracts.
