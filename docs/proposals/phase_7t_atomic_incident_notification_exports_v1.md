# Phase 7T — Atomic incident notification exports v1

## Purpose

Phase 7T creates a deterministic local file handoff for the complete Phase 7S notification-intent
set. It separates stable artifact creation from any future delivery adapter.

## Export and verification

The exporter revalidates Phase 7S, Phase 7R, and referenced Phase 7Q evidence, renders the exact
ordered intents as canonical JSON, and writes with atomic same-directory replacement. The receipt
binds the incident, opening event, source export, absolute path, exact bytes, intent count, and
configuration hashes. Verification reloads the receipt, revalidates all source evidence,
regenerates expected bytes, and compares content, size, and SHA-256.

The payload inherits Phase 7S's minimal-content rule: it contains no actor ID or operator note.

## Authority boundary

Creating, storing, or verifying the file is not message delivery. Phase 7T has no network,
recipient, credentials, delivery attempt, retry, escalation, signature, trusted timestamp,
quarantine enforcement, approval, efficacy, promotion, scoring, options, brokerage, or trading
authority.

## Exit criteria

- Complete validated Phase 7S intent sets produce deterministic canonical bytes.
- Atomic retries are idempotent and persist one exact receipt.
- Verification detects missing, changed, or source-inconsistent artifacts.
- Exports contain no operator identity or note.
- No delivery or authority can be represented as successful.
- Full lint, strict typing, and test suites pass.
