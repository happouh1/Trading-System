# Phase 3D-5 disposable-sandbox validation runbook

Status: **CASE-1 EXACT TRANSACTION AUTHORIZED; GENERAL EXIT ROUTING LOCKED**

## Safety boundary

The plan/import/review commands are offline. One separate script is authorized only for the exact
Case-1 transaction: `SELL 1 AAPL STOP_LOSS/GTC @ 1.00`, `CORE`, followed by detail, cancel, and final
detail. It cannot accept alternate order fields and does not expose replacement, market exit,
cover, flatten, live, or general routing methods. Use only a disposable Webull `SANDBOX` position,
SDK `2.0.17`, and adjustment factor one.

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

Complete and review one case before the next. Only the separately invoked Case-1 script performs a
broker write; all other smoke operations remain unavailable.

Before case 1, run the separately gated read-only inventory:

First initialize the exact evidence session if it does not already exist:

```powershell
python -m trading_system.cli paper start `
  --database webull-sandbox.sqlite `
  --session-id DISPOSABLE_SANDBOX_SESSION `
  --config config/paper.phase3b.v1.yaml `
  --data-revision WEBULL_SANDBOX_PHASE3D5 `
  --calendar-version exchange-calendars-4
```

This creates the required immutable parent and does not contact Webull. Reusing the same session ID
with conflicting provenance is rejected. Then run the inventory:

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

When `case1_ready=true` and the operator has approved the exact transaction, run only during the
open XNYS regular session:

```powershell
python .\scripts\webull-case1-stop.py `
  --database webull-sandbox.sqlite `
  --session-id DISPOSABLE_SANDBOX_SESSION `
  --config config/webull.sandbox.v1.yaml `
  --smoke-config config/webull.phase3d5.smoke.v1.json `
  --confirmation PLACE-CANCEL-SELL-1-AAPL-STOP-1.00-GTC-CORE-WEBULL-SANDBOX
```

The script journals `PREPARED` and `CALL_STARTED` before placement and cancellation. An exception
causes exactly one same-client detail query and a halt; the write is never retried. A prior
`CALL_STARTED` for this session/case blocks rerunning the script. Successful completion stores the
five ordered redacted evidence items and returns a `PENDING_REVIEW` capture ID. General exit routing
and automatic manifest promotion remain false.

### Inspect and recover an ambiguous Case-1 cancellation

The general WebTrade paper account is not the OpenAPI Sandbox account. Inspect OpenAPI Sandbox
orders only through the read-only command below:

```powershell
python -m trading_system.cli webull open-orders `
  --database webull-sandbox.sqlite `
  --session-id DISPOSABLE_SANDBOX_SESSION `
  --config config/webull.sandbox.v1.yaml `
  --account-class INDIVIDUAL_MARGIN `
  --allow-network-read
```

The output normalizes grouped SDK orders, reports no credential or account identifier, and prints
`case1_exact_match=true` only when one open order matches the immutable Case-1 identity. It also
prints the exact cancellation confirmation string for that match.

If the original Case-1 cancellation was ambiguous and the exact order is still open, a human may
authorize one separately journaled recovery cancellation. Set the short-lived process flag, copy
the confirmation string from `open-orders`, and run:

```powershell
$env:WEBULL_SANDBOX_CANCEL_ENABLED = "true"

python -m trading_system.cli webull cancel-case1-order `
  --database webull-sandbox.sqlite `
  --session-id DISPOSABLE_SANDBOX_SESSION `
  --config config/webull.sandbox.v1.yaml `
  --confirmation EXACT_STRING_FROM_OPEN_ORDERS `
  --allow-network-read `
  --enable-sandbox-cancel

Remove-Item Env:WEBULL_SANDBOX_CANCEL_ENABLED
```

This path is fixed to the deterministic `SELL 1 AAPL STOP_LOSS/GTC @ 1.00 CORE` order. Before the
write it verifies the complete open-order identity and an authenticated detail status. It commits
`PREPARED` and `CALL_STARTED`, sends at most one cancellation request, queries final detail once,
and refuses automatic replay. It cannot cancel another order and does not enable general exits.

When `open-orders` returns zero, do not send another cancellation. Diagnose the exact historical
order and current AAPL position with a read-only request:

```powershell
python -m trading_system.cli webull case1-status `
  --database webull-sandbox.sqlite `
  --session-id DISPOSABLE_SANDBOX_SESSION `
  --config config/webull.sandbox.v1.yaml `
  --allow-network-read
```

The result reports broker detail status, AAPL quantity, open-order count, exact-open match, and a
deterministic assessment. Zero open orders alone is never accepted as cancellation evidence.

After exact detail reports `CANCELED` or `CANCELLED`, package the already-persisted sequence for
human review without contacting Webull:

```powershell
python -m trading_system.cli webull finalize-case1-recovery `
  --database webull-sandbox.sqlite `
  --session-id DISPOSABLE_SANDBOX_SESSION `
  --config config/webull.sandbox.v1.yaml `
  --smoke-config config/webull.phase3d5.smoke.v1.json
```

The deterministic capture remains `PENDING_REVIEW`; this command cannot create a PASS review or
promote broker capabilities.

All US-stock entry and exit requests include Webull's required
`support_trading_session="CORE"`. This is derived from the repository's existing RTH-only policy;
extended-hours values `ALL` and `NIGHT` are rejected by immutable contracts.
The disposable-position seed helper checks the authoritative XNYS calendar before loading
credentials or making any network request and refuses to preview or place outside the open regular
session. Run it only between the session's actual open and close, including holiday/early-close
handling.

The exact Case-1 helper is pinned to the SDK's `OrderOperationV3` surface. The SDK marks
`OrderOperationV2` deprecated; do not repeat Case 1 with a build that still routes exact stop calls
through V2.

## Case 2 preparation boundary

Case 2 has an offline-tested runner but intentionally has no operator command or official SDK write
transport. Its fixed validation sequence requires one AAPL long share and one exact SELL
STOP_LOSS/GTC CORE stop at `1.00`, then models a same-client replacement to `1.01`. The prices are
disposable validation constants, not a stop policy. Do not attempt Case 2 until a fresh V3 Case-1
capture has been reviewed and a separate change approves the exact initial-stop setup and V3
replacement request/response contract.

## Case 3 preparation boundary

Case 3 has an offline-tested runner but no official SDK or operator write surface. Its disposable
fixture requires exactly one AAPL long share, no working orders, and one SELL MARKET/DAY CORE exit
for quantity one. Completion requires matching cumulative fill quantity and an authenticated flat
position. Do not execute it at Webull until Cases 1 and 2 have reviewed captures and a separate
change approves the exact V3 exit request/response contract.

## Case 4 preparation boundary

Case 4 has an offline-tested runner and no official SDK or operator write surface. Its disposable
fixture requires exactly one short AAPL share, no working orders, and one BUY MARKET/DAY CORE cover
for quantity one. A valid capture requires preview evidence, exact cumulative fill, and a flat final
position proving reduction without reversal. Execute no sandbox cover until Cases 1–3 have reviewed
captures and a separate change authorizes the exact V3 cover contract.

## Case 5 preparation boundary

Case 5 currently accepts only already-collected, redacted evidence and invokes no transport. Its
fixed schema uses a four-share entry with cumulative fill two, terminal cancellation retaining two,
and separate two-share stop and exit examples with cumulative fill one. These are disposable schema
fixtures, not trading sizes or one executable sequence. Collection remains unavailable until Cases
1–4 are reviewed and separate safe seeding procedures are approved.

## 2. Build a redacted capture manually (non-Case-1 cases)

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
