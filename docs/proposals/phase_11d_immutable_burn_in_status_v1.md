# Phase 11D proposal — immutable burn-in status

## Objective

Make the command-line status and desktop workstation evaluate the exact prospective burn-in plan
that was saved before the observation window opened.

## Problem corrected

The Phase 11A workstation rebuilt a plan from the current repository release audit and the original
request. Repository changes made after preregistration can legitimately change the release hash and
therefore produce a different plan identity. Displaying that reconstructed identity during a live
prospective window would break the preregistration boundary.

## Deterministic boundary

Phase 11D loads the plan path and evidence path from the fail-closed Phase 11C configuration. It
parses the saved plan, evaluates only observations known by the supplied UTC `as_of`, and hashes the
exact plan and evidence file contents. A missing evidence file is represented explicitly as an
empty observation set; a missing or invalid plan fails closed.

The workstation uses the same status operation and rejects a disagreement between its configured
evidence path and the collector evidence path.

## Authority

Status inspection is local and read-only. It does not write files, load credentials, use the
network, start a scheduler, submit sandbox orders, authorize production, promote a release, or
enable live trading.
