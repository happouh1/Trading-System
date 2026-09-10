# Phase 9H Proposal — Local Operator Dashboard

Phase 9H upgrades the Phase 9G desktop entry point from a console-only readiness message to a
deterministically rendered local HTML dashboard. The existing desktop shortcut continues to target
the repository-owned launcher. The launcher creates the dashboard inside the repository and opens
that local file with the user's default browser.

The page contains no JavaScript, remote resources, forms, trading controls, credentials, or broker
data. Rendering performs no network request and starts no scheduler. All execution authority remains
false. Missing installation files produce `NEEDS ATTENTION`, a nonzero command result, and no browser
launch.

This phase does not decide which supervised sandbox command may eventually be started. Adding any
such control requires a separate reviewed phase with local authentication, explicit confirmation,
active supervision, reconciliation, and fail-closed capital limits.
