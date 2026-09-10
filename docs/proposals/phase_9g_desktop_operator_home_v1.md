# Phase 9G Proposal — Desktop Operator Home

Phase 9G provides a Windows desktop entry point for non-technical operation. The shortcut targets a
repository-owned PowerShell launcher, which locates the project relative to itself, verifies the
Python environment and required configurations, and opens a plain-language operator home screen.

The default screen is deliberately read-only. It loads no Webull credentials, starts no scheduler,
uses no network, submits no orders, and enables neither sandbox nor live trading. Missing files cause
`NEEDS ATTENTION` and a nonzero exit code. Later execution controls may be added behind separate,
explicitly reviewed commands; they must not silently change this safe default.

The shortcut installer contains no credentials and uses the current Windows Desktop location. The
shortcut may be installed or refreshed without changing trading configuration or persisted evidence.
