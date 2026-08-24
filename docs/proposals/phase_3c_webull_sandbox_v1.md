# Proposed Phase 3C Webull sandbox adapter v1

Status: **APPROVED — 3C-1 PASSED; 3C-2 PASSED; 3C-3 IMPLEMENTED, SANDBOX REVIEW PENDING**

## Purpose

Phase 3C connects the provider-neutral Phase 3B runtime to Webull's official sandbox. It begins with
read-only identity and account checks, then shadow market-data verification, order preview, and only
after those gates pass, explicitly enabled sandbox stock orders. Production endpoints and real-money
orders remain structurally prohibited.

## Verified dependency and SDK surface

- official package: `webull-openapi-python-sdk==2.0.17`;
- supported repository runtime: Python 3.12;
- verified local SDK entry points: `ApiClient`, `TradeClient.account_v2`, and
  `TradeClient.order_v2`;
- verified read methods: account list, balance, positions, open orders, order history, and order detail;
- verified write methods: preview, place, replace, and cancel;
- authentication uses an App Key/App Secret and an optional access token when required by 2FA.

The SDK is an untrusted transport dependency. Its response objects are validated and converted to
immutable internal contracts before entering the paper registry.

## Bounded implementation stages

### 3C-1 — Offline contracts and read-only authentication

1. Add strict Webull sandbox configuration, credential-provider protocol, redaction utilities,
   response schemas, error taxonomy, rate-limit policy, and transport protocol.
2. Implement an official-SDK transport and deterministic fake/rejecting transports.
3. Permit only the sandbox API and sandbox events hostname allowlist.
4. Add `trading-system webull verify-config` with no network access.
5. Add `trading-system webull verify-account` as the first network action. It may call only account
   list, balance, positions, open orders, and order detail. It cannot preview or submit an order.
6. Match the returned account ID to `WEBULL_ACCOUNT_ID`; mismatch fails closed.

### 3C-2 — Market-data shadow ingestion

1. Implement a separate `WebullMarketDataSource` for snapshots, historical bars, and streaming data.
2. Preserve raw payload hash, receipt time, source revision, provider timestamp, and known-at time.
3. Normalize through existing XNYS validation and completed-candle contracts.
4. Compare Webull bars and resulting decisions against fixed offline replay fixtures.
5. Reject revised, incomplete, duplicate, out-of-order, stale, extended-hours, or timezone-ambiguous
   bars under the approved Phase 3B controls.

Implementation note: SDK `2.0.17` exposes stock `get_snapshot` and `get_history_bar`. The adapter
forces `US_STOCK`, `RTH`, `real_time_required=False`, and disables extended/overnight snapshots.
Because the SDK does not publish a typed response schema, raw responses are persisted and hashed,
then must match the repository's strict `shadow-v1` bar schema before normalization. Unknown live
shapes fail closed; no field aliases, timestamp units, adjustment factors, or completeness flags are
inferred. The first decoder accepts completed 1H RTH bars only; the existing session-aware aggregator
remains authoritative for 4H, Daily, and Weekly candles. Deterministic fake payloads validate the
causal pipeline in ordinary CI.

Redacted sandbox captures with five and ten M60 items established the v1 provider mapping. SDK items
arrive newest-first and `time` is the bar start. The next captured start is the causal close boundary;
the final bar closes at the authoritative XNYS session close. A session must already be complete at
receipt, and every derived duration must be positive and no longer than one hour. Intraday SDK bars
are unadjusted, so v1 records identical raw/adjusted OHLCV with adjustment factor one.

Historical backfills are immutable revisioned comparison evidence and do not advance operational
paper checkpoints. Only completed streaming-bar envelopes enter the Phase 3B runtime, where the
configured lateness gate applies. Both paths preserve receipt and provider timestamps and reject
duplicates, revisions, ordering violations, ambiguous timezones, and non-RTH bars.

Stage 3C-2 live review passed with a read-only AAPL M60 sandbox response: ten provider rows decoded
to ten distinct canonical candles under one raw-response revision, every `known_at` followed its
derived close, raw/adjusted factor-one provenance matched, and the persisted audit found zero secret-
redaction violations. This validates historical shadow ingestion only; opening the long-running
stream remains governed by open question 67.

### 3C-3 — Preview-only stock adapter

1. Map an existing eligible Phase 1 stock plan to a Webull preview request.
2. Use a stable Webull `client_order_id` of at most 32 characters derived from the internal intent ID.
3. Persist the exact request hash and redacted response before returning preview evidence.
4. Validate symbol, side, quantity, account, buying power, session, and order-type parity.
5. Preview rejection never modifies the Phase 1 plan and never falls back to another order type.

Implementation status: `preview-stock` loads an immutable Phase 3B intent, reconstructs and validates
its Phase 1 `TradePlan`, derives integer quantity from the versioned normalized risk budget, and
requires its scheduled release to equal an authoritative XNYS regular-session open. Account identity
is verified through the read-only workflow before preview. An accepted preview must return HTTP 2xx,
explicit `accepted=true`, the verified account ID, and an exact echo of the canonical MARKET/DAY
stock request. Both accepted and rejected responses are redacted and persisted with the exact request
hash. No local short-margin formula is inferred: Webull preview acceptance is the buying-power gate.
The sandbox submission method is explicitly fail-closed during 3C-3 and no CLI submission command
exists.

### 3C-4 — Explicit sandbox stock submission

1. Submission requires all of:

   - sandbox host verification;
   - `WEBULL_SANDBOX_SUBMISSION_ENABLED=true`;
   - a CLI `--enable-sandbox-submission` flag;
   - persisted successful preview for the identical request hash;
   - active Phase 3B `PAPER_ENABLED` state;
   - current successful account/order/position reconciliation.

2. Persist intent and request before calling Webull.
3. Timeout or transport ambiguity triggers query-by-client-ID and halts new submissions. It never
   creates a replacement client ID or blindly resubmits.
4. Append acknowledgements, broker order IDs, status changes, partial fills, fills, rejections, and
   cancellations without rewriting prior records.

### 3C-5 — Events, recovery, and reconciliation

1. Subscribe to official sandbox trade events only after read-only reconciliation succeeds.
2. Treat the event stream as notification, not sole truth; reconcile through authenticated queries.
3. On restart, query every unresolved client order ID before accepting new intents.
4. Unknown orders, missing orders, account mismatch, side/symbol/quantity mismatch, impossible status
   transition, unexpected fill, or position mismatch records an incident and halts submission.

### Approved 3C-2 streaming control amendment

The bounded streaming stage is notification-only and read-only. Every callback is written to the
append-only registry before semantic validation. Only uppercase-symbol, regular-session `snapshot`
notifications with an epoch-millisecond provider timestamp are accepted. Exact duplicates are
idempotent; stale, malformed, unsupported, or out-of-order callbacks halt the Phase 3B runtime.

Disconnects enter `RECONCILING` and use the fixed retry delays `1, 2, 4` seconds. Reconnection is
not permitted to become active until a REST comparison succeeds. A mismatch or exhausted retry
budget halts. The per-symbol provider timestamp and payload-hash cursor is restored from SQLite on
restart.

The pinned SDK may auto-resolve a production-capable MQTT hostname when none is supplied. Because
the approved configuration does not contain an independently verified Webull sandbox MQTT hostname,
`socket_enabled` is fixed to `false`. This amendment therefore implements and verifies the complete
provider-neutral control boundary but does not instantiate `DataStreamingClient`, open a socket,
construct candles from quote snapshots, or authorize any order action.

## Proposed initial stock-order mapping

The existing Phase 1 next-open rule remains authoritative. Proposed sandbox representation:

```text
LONG  -> BUY
SHORT -> SELL_SHORT
entry -> regular-session MARKET order released after the eligible XNYS opening event
TIF   -> DAY
qty   -> exact approved Phase 1 integer quantity
```

The existing gap-cancellation rule runs before request construction. If Webull cannot represent the
plan exactly, the adapter rejects it. No market-on-open, limit-price approximation, fractional share,
extended-hours, bracket, replacement, or fallback behavior is authorized initially.

## Secrets and logging

- Read `WEBULL_APP_KEY`, `WEBULL_APP_SECRET`, and `WEBULL_ACCOUNT_ID` through a credential provider.
- Never store secrets in SQLite, canonical payloads, configuration, reports, exceptions, test output,
  command arguments, or Git.
- Disable the SDK's default local file logger and replace it with a redacting logger before creating
  `TradeClient`; the inspected SDK otherwise defaults to `webull_trade_sdk.log`.
- Redact authentication/signature/token headers and secrets from all HTTP diagnostics.
- Configuration stores environment-variable names, never values.

## Network and environment safeguards

- Sandbox is the only permitted environment in Phase 3C.
- DNS/URL validation uses exact HTTPS hostname matching, not substring matching.
- Redirects to non-allowlisted hosts fail.
- Production Webull hosts are explicitly denied even if credentials are valid.
- Network access is isolated in `webull/transport.py`; tests use fake transports by default.
- Live integration tests require an explicit marker and environment flag and never run in ordinary CI.

## Persistence additions

Migration `010_phase_3c.sql` will add append-only records for:

- Webull connection verifications;
- redacted request/response envelopes and hashes;
- account snapshots and permission snapshots;
- order previews;
- client-order mappings;
- broker order events and executions;
- reconciliation checkpoints;
- rate-limit observations and transport incidents.

No credential or unredacted authentication payload may enter the database.

## Required tests

- SDK version and Python compatibility enforcement;
- missing/malformed credentials and secret-redaction tests;
- exact sandbox-host allowlist and production-host denial;
- SDK default file logging disabled;
- account-ID and environment mismatch rejection;
- no-network config verification;
- read-only command cannot reach preview/place/replace/cancel methods;
- deterministic client-order ID length, stability, and collision handling;
- exact plan-to-preview mapping and unsupported-plan rejection;
- preview hash required before submission;
- two-factor submission enablement gates;
- timeout ambiguity query-before-halt behavior with no duplicate placement;
- partial-fill, cancellation, rejection, reconnect, and out-of-order event cases;
- account/order/position reconciliation mismatch halts;
- restart resolves all outstanding orders before new submission;
- causal bar normalization and replay-parity fixtures;
- append-only persistence, migration parity, Ruff, strict mypy, pytest, and CI.

## Explicit exclusions

- production endpoints, real-money orders, or production credentials;
- Robinhood or Interactive Brokers adapters;
- options, multi-leg orders, futures, crypto, or event contracts;
- fractional shares, margin-policy decisions, borrow/locate assumptions, and portfolio allocation;
- extended-hours or overnight trading;
- model-driven decisions, parameter changes, or learned confidence promotion;
- automatic credential creation, account opening, deposits, withdrawals, or transfers;
- deployment as a continuously running external service.

## Exit criteria

Phase 3C completes only after read-only account verification, causal shadow data validation,
preview-only mapping, explicitly gated sandbox stock submission, restart recovery, and exact
reconciliation pass with fake transports and separately invoked sandbox smoke tests. Ordinary CI must
remain offline and deterministic. No production order path may exist.

## Approval decisions required

Approval would authorize only this bounded Webull sandbox integration. Please approve or amend:

1. SDK version `2.0.17` and strict sandbox-only host policy;
2. staged read-only, shadow-data, preview-only, then explicitly gated submission rollout;
3. proposed next-open stock market-order mapping and `DAY` time in force;
4. deterministic 32-character client-order mapping and query-before-retry policy;
5. credential isolation, SDK logger suppression, and mandatory redaction;
6. reconciliation and fail-closed incident policy;
7. stocks-only scope with options and production trading deferred.
