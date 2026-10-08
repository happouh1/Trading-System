# Phase 12G — one-click burn-in operator launch v1

Phase 12G upgrades the existing `Trading System.lnk` access path to refresh and open the Phase 12F
burn-in dashboard. The launcher validates its checked-in configuration and local prerequisites,
captures current Windows task state, renders the static dashboard from read-only SQLite evidence,
and opens that local HTML file.

The shortcut installer is explicit and operator-run. The launcher itself does not install, edit,
start, stop, or retry any scheduled task. It has no network, credential, database-write, broker,
order-API, sandbox-execution, live-trading, or promotion authority. It does not add an automatic
refresh cadence; each shortcut invocation creates one fresh snapshot.

Install or replace the existing desktop shortcut from the repository with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File `
  .\scripts\install-phase12g-burn-in-shortcut.ps1
```

Validate the complete local launch path without opening a browser with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File `
  .\scripts\start-phase12g-burn-in.ps1 -SelfTest
```
