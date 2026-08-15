# Phase 0 methodology

Phase 0 establishes contracts only. It validates local invariants, produces canonical JSON and hashes,
and validates the versioned threshold configuration. It contains no signal, feature, state-transition,
execution, outcome-label, or backtest algorithms.

Canonical serialization sorts object keys, uses compact UTF-8 JSON, tags Decimal/date/datetime values,
rejects non-finite numbers and naive datetimes, and normalizes datetimes to UTC. Content identifiers use
SHA-256 over this representation with an explicit namespace.

