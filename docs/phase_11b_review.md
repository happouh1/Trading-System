# Phase 11B review

Phase 11B adds a local, read-only decision-alert feed to the existing multi-timeframe workstation.

The alert feed is a view over persisted `decisions`, joined causally through `feature_snapshots` to `candles`. It selects the latest decision for each symbol/timeframe with `known_at <= as_of`, verifies the stored payload hash, and exposes the engine's existing action and reasons without changing any strategy logic.

Safety remains unchanged: the UI cannot use the network, load credentials, write the database, send an external notification, submit or cancel an order, run the sandbox, or enable live trading.

Open design choices deferred to a later phase:

- whether alerts should support desktop sound or operating-system notifications;
- whether acknowledgments should be persisted and, if so, in which separate operator database;
- delivery channels, quiet hours, throttling, and escalation policy;
- notification retention and redaction requirements.
