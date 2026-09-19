# Sandbox diagnostic reconciliation — 2026-09-18

Status: diagnostic only; not a qualified completed trade or burn-in PASS.

## Evidence and observations

Read-only sandbox requests selected the unique INDIVIDUAL_MARGIN account. The configured
account identifier did not match the returned account list; credentials were not changed.
Exact response bytes were retained locally under ignored `.tmp/broker-evidence/` directories
`20260917T205717948565Z` and `20260918T042522163469Z`. These private operational files are not
committed. Retain them securely before cleaning temporary directories.

- August 24–31 history returned five order groups: two filled one-share AAPL buys, one filled
  two-share sell, and two cancelled unfilled orders. The returned fills net to zero shares.
- August 31–September 7 returned a September 2 one-share AAPL buy at 325.81 and an unfilled,
  cancelled sell stop. The buy matches a local SMOKE_SEED_PLACE envelope in sandbox session 005;
  the stop matches that session's smoke-test envelopes.
- September 7–14 and September 14–18 queries returned empty arrays.
- The September 18 position response reports one AAPL share at cost price 325.81, consistent
  with the September 2 test purchase remaining open. This is not proof of complete account history.
- Local `webull-sandbox.sqlite` contains zero managed positions, execution rows, and position-event
  rows. Smoke-test evidence is not a managed strategy trade lifecycle.

## Integrity references

SHA-256 of exact September 18 response bytes:

| Response | SHA-256 |
|---|---|
| August 31–September 7 history | 816282e646f9ec90d465672a62cffb3806dedb446c8dee9da243065ec2058416 |
| Each empty September history response | 4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945 |
| Current positions | 9bc25bafc0e1b1402993fb774fc813cc725a1af68ba7c4b4e17f31c852a83435 |
| Case 1 cancelled-stop detail | fafb8f12f164885acf5e932028a3a3a0bdcffc175b041efa7dcace2c86e8b49d |

Hashes establish byte integrity, not independent provider authentication. Requests used page size
10 and returned fewer groups; pagination completeness was not independently certified. Position
snapshots are current observations, not historical before/after evidence. Individual execution
identities were not found in these order-level responses. No missing fill IDs are synthesized.

## Burn-in consequence and next decisions

No records were imported as qualified trades, no trading database rows changed, and no broker
orders were submitted, modified, or cancelled. The open test holding remains untouched.
The original September 14 plan is unchanged. The operator-approved minimum remains ten qualifying
trades in each of two separate sources, not ten combined.

Before a replacement cohort can start, review and approve:

1. An executable strategy/configuration/code lock and a future window; no retrospective inclusion
   of these smoke tests.
2. A simulated execution model covering fills, spread, slippage, fees, session timing, expiration,
   and exits. Existing historical replay results alone cannot qualify prospective shadow trades.
3. Broker evidence requirements and reviewer authority, including unavailable execution identities,
   corrections, partial fills, and historical position baselines.
4. Handling of the pre-existing sandbox test holding: preserve and segregate it, or obtain separate
   explicit authorization for any cleanup order. No cleanup action is authorized by this report.

These are approval gates, not additional phase labels. Questions 567–580 remain open except for
the already approved source selection and independent ten-trade minima.
