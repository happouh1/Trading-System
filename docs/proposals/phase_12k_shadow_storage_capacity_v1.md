# Phase 12K shadow-evidence storage capacity

Status: implemented as a read-only operational safeguard.

## Purpose

The prospective shadow database is append-only and now contains multi-timeframe evidence for an
expanded universe. Phase 12K makes local storage exhaustion visible before it can interrupt a
scheduled collection or prevent a recoverable database copy.

The monitor opens SQLite in read-only mode and records:

- database, WAL, shared-memory, and rollback-journal byte counts;
- SQLite page size, allocated page count, and freelist count;
- filesystem total, used, and free bytes;
- the number of whole current-size database copies that fit in free space; and
- deterministic GREEN, AMBER, or RED reason codes against a versioned configuration.

The initial thresholds are operational hypotheses, not strategy parameters. AMBER begins at an
8 GiB database, less than 50 GiB free, or fewer than five database copies of headroom. RED begins
at 16 GiB, less than 20 GiB free, or fewer than three copies. Changing a threshold requires a new
versioned configuration.

## Safety boundary

Phase 12K cannot delete, vacuum, compact, archive, truncate, rewrite, or migrate evidence. It cannot
load credentials, contact Webull, submit an order, enable live trading, or promote any strategy.
Its only write is an atomically replaced local JSON status artifact outside SQLite. A RED result is
an operator halt/escalation signal; it is not authority to remove data automatically.

## Command

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File `
  .\scripts\inspect-phase12k-storage-capacity.ps1
```

The command exits `0` for GREEN, `1` for AMBER, and `2` for RED.
