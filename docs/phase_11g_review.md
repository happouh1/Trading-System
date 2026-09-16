# Phase 11G review — standalone read-only burn-in worker

## Outcome

Phase 11G supplies the previously missing bounded runtime cycle for independent local operation.
It is suitable for later invocation by Windows Task Scheduler and does not consume Codex tokens.

## Safety boundary

- Webull sandbox only.
- Market-data-only protocol: snapshot and historical-bar reads.
- Explicit dual gate for real network access: locked configuration plus CLI flag.
- No order, preview, submission, replacement, cancellation, position, or execution interface.
- No automatic cohort creation, evidence promotion, production release, or live trading.
- The checked-in configuration is `OFFLINE_VALIDATION_ONLY` and cannot make a network request.

## Determinism and recovery

- The worker accepts completed XNYS RTH M60 data only.
- Stable source revision hashes exclude local receipt time.
- Exact bars are deduplicated against persisted session evidence after restart.
- Every successful cycle appends a heartbeat and a canonical cycle receipt.
- Cycle identity binds session, UTC observation time, and configuration hash.

## Cohort disposition

The active `burn-in-20260914-01` cohort had zero observations and no continuously running worker by
the end of its first two eligible market days. Its preregistered minimum is all 20 XNYS market days
in the window. It therefore cannot pass prospectively without backfilling, which is prohibited.
The cohort remains immutable. A replacement must be preregistered only after the Phase 11G worker
is independently verified.

## Not yet satisfied

Phase 11G does not generate decisions, entries, exits, or completed trades. It does not classify
regime or attest strategy coverage. Those are required for the replacement burn-in and remain a
separate, explicitly reviewed build step.
