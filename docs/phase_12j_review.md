# Phase 12J review

Phase 12J is the evaluation layer that follows the Phase 12I signal expansion.

Acceptance criteria:

1. Configuration rejects broker, network, credential, live-trading, and promotion authority.
2. SQLite evidence is opened read-only and remains byte-for-byte unchanged after rendering.
3. All configured symbols appear in the freshness table, including missing symbols.
4. Stage A is derived only from completed daily candles available by `as_of`.
5. Phase 12I results are grouped without changing their original state or reason codes.
6. Outcome summaries include sample counts so small samples cannot look conclusive.
7. Output is static local HTML with no remote resources or executable scripts.

Phase 12J does not authorize parameter tuning. The dashboard must accumulate prospective
sessions before any threshold change is proposed.
