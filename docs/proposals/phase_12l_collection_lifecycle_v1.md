# Phase 12L — collection and audit lifecycle evidence

## Purpose

Phase 12L makes long post-close collection and daily-audit work observable without
adding trading authority. It appends local `STARTED`, `PROGRESS`, `COMPLETED`, or
`FAILED` evidence for `POST_CLOSE` and `AUDIT` operations. The watchdog treats an
active bounded operation as running rather than immediately reporting a missing
receipt.

## Late audit policy

A missed historical audit may be closed only from immutable start and post-close
receipts. Its real observation time is retained and its status is suffixed
`_LATE_AUDIT`. A late audit never qualifies as an on-time, zero-incident cohort
session and never backdates or retries collection.

## Authority

The lifecycle writer can read the frozen schedule and append local SQLite evidence.
It cannot load credentials, access the network, submit broker orders, retry a
session, enable live trading, or promote a release.
