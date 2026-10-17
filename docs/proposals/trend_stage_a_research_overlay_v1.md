# Stage A trend research overlay v1

## Objective

Add the useful portion of the transferred MRNA-pattern scanner as a deterministic,
causal, research-only setup classifier. This overlay has no decision, portfolio,
execution, promotion, or broker authority.

## Base setup

A Stage A setup requires all information to be known at the observation timestamp:

- close above EMA8, EMA8 above EMA21, and EMA21 above EMA50;
- maximum observed volume surge in the current and prior ten sessions of at least 2x
  the prior 20-session average;
- close strictly within 3% of the observed 20-session high;
- 20-session ADR of at least 3.5%; and
- close of at least $5.

## Entry-quality separation

The setup and entry decision are deliberately separate. A qualifying setup is:

- `QUALIFIED` below 6% over EMA8;
- `EXTENDED_WATCH` from 6% through 8% over EMA8; or
- `OVEREXTENDED` above 8% over EMA8.

A gap of at least 3% adds a chase warning and prevents entry eligibility without
erasing setup quality. Time-of-day and volume bands are retained as research
metadata, not hard filters.

## Evaluation contract

The stable observation identity is one symbol per market session. Repeated alerts
must not create additional independent votes. Outcomes are evaluated after eight
completed sessions with forward close return, MFE, MAE, and time-to-peak. Threshold
changes require a new config version and prospective validation.

## Authority boundary

Stage A can annotate research candidates only. It cannot alter the frozen burn-in,
send broker orders, promote itself automatically, or enter the production decision
engine.
