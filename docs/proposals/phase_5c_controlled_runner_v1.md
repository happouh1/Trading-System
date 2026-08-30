# Phase 5C controlled runner proposal

## Objective

Phase 5C executes one explicitly requested, already-due offline/shadow maintenance action and stores
durable evidence. It is not a general scheduler, shell wrapper, workflow engine, or trading runtime.

## Authorization chain

1. Phase 5B persists a schedule definition and a plan containing a due job.
2. A Phase 5C request references that exact plan ID, job ID, and due timestamp.
3. The registry verifies all three values against durable evidence.
4. The action must be in the immutable runner configuration allowlist.
5. The target, when required, must resolve beneath the configured workspace.
6. The runner acquires a single-instance lease and invokes one packaged worker attempt.

Missing, conflicting, future, exhausted, premature-retry, or concurrently leased requests fail
closed.

The request ID uses only scheduled job ID and due timestamp. This creates one durable execution
identity per schedule boundary. Changing the plan, action, target, request time, source revision, or
runner configuration for that boundary becomes a conflicting payload rather than a second run.

## Process boundary

The only executable is the current Python interpreter. The module is fixed to
`trading_system.operations.worker`; the user cannot supply a module, script, shell, executable,
argument vector, working directory, or environment. `shell=False` prevents command interpretation.
Network and credential variables are not passed to the child.

## Initial packaged actions

- `EVIDENCE_NOOP`: emits deterministic proof that the packaged worker boundary launched.
- `SQLITE_QUICK_CHECK`: opens one contained existing file using SQLite `mode=ro` plus
  `PRAGMA query_only=ON`, runs `PRAGMA quick_check`, and returns the result.

Both actions are operational diagnostics. They do not ingest data, calculate signals, retrain
models, alter portfolios, contact Webull, preview orders, or submit trades.

## Failure, timeout, and retry

The subprocess has a hard tunable timeout, initially 30 seconds. Output is bounded to 65,536 bytes.
A failure or timeout receives a retry timestamp using:

```text
retry_delay = base_backoff_seconds * 2 ** (attempt_number - 1)
```

The initial base is 60 seconds and maximum attempts is three. These are tunable operational
assumptions. The runner never sleeps and never launches the next attempt automatically.

## Persistence and recovery

Requests and attempts are append-only and content-addressed. Standard output and error are retained
only as SHA-256 hashes; the structured packaged result is stored canonically. A successful replay of
the same request returns its existing successful attempt without invoking the worker again.

An ephemeral SQLite lease coordinates concurrency. Its expiration is timeout plus lease grace.
Normal completion removes it; a later invocation may replace an expired crash residue. The attempt
journal, not the lease table, is the historical record.

## Deliberately unavailable

- Arbitrary commands, scripts, executables, environment variables, or shell operators.
- Background daemon, cron installation, task queue, or automatic retry loop.
- Network access, external notification, credential loading, or remote health checks.
- Market-data retrieval, signal generation, model promotion, portfolio mutation, or options logic.
- Brokerage APIs, order preview/submission/cancellation, or live trading.
