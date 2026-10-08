# Phase 12F — read-only burn-in operations dashboard v1

Phase 12F adds one static local page for observing the frozen Phase 12E replacement cohort.
It combines Windows task readiness with immutable SQLite evidence for the scheduled start,
post-close, and final audit stages. It also reports MSFT/SPY collection cycles, causal decision
cycles, staged shadow intents, incidents, and cohort progress.

The renderer opens SQLite with `mode=ro`. It may write only its task-state snapshot and HTML
artifact. It cannot load Webull credentials, use the network, mutate scheduled tasks, start or
retry a session, backfill evidence, call an order API, submit an order, enable live trading, or
promote a release. A green dashboard means the local observation controls are ready; it is not a
claim of strategy profitability or trading authorization.

Run it from the repository with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\render-phase12f-dashboard.ps1 -Open
```
