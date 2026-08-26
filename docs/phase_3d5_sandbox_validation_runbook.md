# Phase 3D-5 disposable-sandbox validation runbook

Status: **CAPTURE PREPARATION COMPLETE; BROKER WRITES NOT YET INVOKED**

## Safety boundary

The repository commands in this runbook are offline. They do not preview, place, replace, cancel,
cover, or flatten an order. Collect operational evidence only with a disposable Webull `SANDBOX`
position, SDK `2.0.17`, adjustment factor one, and separate operator authorization for that one
bounded case.

Never put credentials, account IDs, tokens, headers, signatures, or unredacted SDK objects in a
capture. Do not edit `config/webull.exit_capabilities.pending.v1.json` during collection.

## 1. Generate the immutable plan

```powershell
python -m trading_system.cli webull smoke-plan `
  --config config/webull.sandbox.v1.yaml `
  --smoke-config config/webull.phase3d5.smoke.v1.json
```

The cases are fixed in this order:

1. long protective-stop preview/place/detail/cancel;
2. monotonic long stop replacement under the same client identity;
3. long MARKET/DAY reducing exit and flat reconciliation;
4. short BUY cover and proof of reduction without reversal;
5. partial entry and partial stop/exit cumulative fills;
6. ambiguity plus one same-client detail query and recovery;
7. restart with an existing managed position and protective stop.

Complete and review one case before the next. No harness command performs these operations because
their exact official response semantics are the evidence being validated.

Before case 1, run the separately gated read-only inventory:

```powershell
python -m trading_system.cli webull smoke-case1-preflight `
  --database webull-sandbox.sqlite `
  --session-id DISPOSABLE_SANDBOX_SESSION `
  --config config/webull.sandbox.v1.yaml `
  --smoke-config config/webull.phase3d5.smoke.v1.json `
  --account-class INDIVIDUAL_MARGIN `
  --allow-network-read
```

`case1_ready` is true only for exactly one positive sandbox stock position and zero open orders.
The command persists redacted read evidence and performs no preview, placement, or cancellation.

All US-stock entry and exit requests include Webull's required
`support_trading_session="CORE"`. This is derived from the repository's existing RTH-only policy;
extended-hours values `ALL` and `NIGHT` are rejected by immutable contracts.
The disposable-position seed helper checks the authoritative XNYS calendar before loading
credentials or making any network request and refuses to preview or place outside the open regular
session. Run it only between the session's actual open and close, including holiday/early-close
handling.

## 2. Build a redacted capture

Use this exact top-level JSON shape. The case-specific evidence labels come from `smoke-plan`.

```json
{
  "capture_version": "3D-SMOKE-CAPTURE.1.0",
  "session_id": "DISPOSABLE_SANDBOX_SESSION",
  "case_id": "LONG_STOP_PLACE_DETAIL_CANCEL",
  "case_sequence": 1,
  "environment": "SANDBOX",
  "sdk_version": "2.0.17",
  "captured_at": "2026-01-05T15:00:00Z",
  "adjustment_factor": "1",
  "disposable_position_attested": true,
  "explicit_write_invocation_attested": true,
  "evidence": [
    {
      "operation": "STOP_PREVIEW",
      "occurred_at": "2026-01-05T14:31:00Z",
      "client_order_id": "SAFE_NONSECRET_CLIENT_ID",
      "request": {"account_id": "[REDACTED]"},
      "response": {"provider_fields": "REDACTED_CAPTURE"},
      "observation": {"semantic_review_required": true}
    }
  ]
}
```

This abbreviated example does not satisfy case 1 until every required evidence label is present.

## 3. Import without network access

```powershell
python -m trading_system.cli webull import-smoke-capture `
  --database webull-sandbox.sqlite `
  --session-id DISPOSABLE_SANDBOX_SESSION `
  --config config/webull.sandbox.v1.yaml `
  --smoke-config config/webull.phase3d5.smoke.v1.json `
  --capture redacted-capture.json
```

The result is `PENDING_REVIEW`. Repeating the exact import is idempotent; conflicting content under
an existing identity is rejected.

## 4. Review append-only evidence

Use the returned `capture_id` in a separate review document:

```json
{
  "review_version": "3D-SMOKE-REVIEW.1.0",
  "capture_id": "webull_smoke_capture_...",
  "reviewed_at": "2026-01-06T12:00:00Z",
  "reviewer_id": "OPERATOR_REVIEWER",
  "verdict": "INCONCLUSIVE",
  "reason_codes": ["PROVIDER_STATUS_SEMANTICS_UNPROVEN"],
  "notes": "Record exact redacted findings; do not infer aliases."
}
```

Import it with `webull import-smoke-review`, then inspect `webull smoke-status`. Allowed verdicts are
`PASS`, `FAIL`, and `INCONCLUSIVE`.

## 5. Promotion boundary

Even when all seven latest reviews are `PASS`, status reports
`official_exit_transport_enabled=false` and `automatic_manifest_promotion=false`. A later change
must review the captures, answer open questions 74–85, define exact official response adapters,
update the capability manifest explicitly, and rerun the full offline suite. Production endpoints,
live capital, options, arbitrary orders, and unattended operation remain prohibited.
