# Phase 1E golden scenario matrix

This matrix maps Specification §23.3 to deterministic automated coverage. Test names are the
normative executable references; related tests supplement the primary reference.

| # | Required narrative | Primary automated coverage |
|---:|---|---|
| 1 | Valid base and deterministic tie-break | `test_valid_base_uses_only_prior_compression_history`; `test_multiple_valid_windows_select_highest_quality_then_longest` |
| 2 | Breakout candidate → pending → accepted | `test_breakout_candidate_becomes_pending_then_accepted_causally` |
| 3 | Failed breakout → bull trap | `test_failed_breakout_confirms_bull_trap_on_lower_low` |
| 4 | Breakdown → bear trap | `test_failed_breakdown_confirms_bear_trap_symmetrically` |
| 5 | Bullish and bearish liquidity sweeps | `test_bullish_sweep_waits_for_two_closed_confirmation_bars`; `test_bearish_sweep_is_symmetric` |
| 6 | Reclaim, accepted reclaim, failed reclaim | `test_reclaim_accepts_and_preserves_sweep_parent_link`; `test_reclaim_failure_is_known_only_on_failure_close` |
| 7 | Wick beyond level without acceptance | `test_wick_beyond_level_is_not_a_breakout_candidate` |
| 8 | Gap beyond level and next-bar cancellation | `test_excessive_directional_gap_cancels_entry` |
| 9 | Multi-timeframe conflict → WATCH/NO_TRADE | `test_equal_priority_opposites_within_five_points_conflict`; `test_pending_trigger_with_sufficient_confidence_produces_watch` |
| 10 | Good setup but poor entry/runway | `test_invalid_runway_is_explained_no_trade`; `test_invalid_stop_is_rejected_not_arbitrarily_tightened` |
| 11 | Countertrend tactical reversal label | `test_confirmed_trap_is_labeled_countertrend` |
| 12 | Missing-volume confidence cap | `test_location_and_confidence_caps_are_deterministic` |
| 13 | Ambiguous stop/target adverse-first | `test_stop_wins_ambiguous_stop_target_bar` |
| 14 | Monotonic trailing stop | `test_long_trail_never_decreases` |
| 15 | Sweep/reclaim does not create two trades | `test_reclaim_accepts_and_preserves_sweep_parent_link`; `test_lifecycle_rejects_a_second_plan_for_same_series` |

## Cross-cutting Phase 1E validation

- Next-open causality: `test_entry_fills_only_at_later_bar_open_with_adverse_slippage`.
- Pending/open recovery equivalence:
  `test_lifecycle_warm_replay_matches_uninterrupted_pending_trade` and
  `test_replay_resume_rebuilds_causal_feature_warmup`.
- Future truncation invariance:
  `test_removing_later_future_bars_cannot_change_available_outcome`,
  `test_future_bar_does_not_retroactively_stamp_acceptance`, and
  `test_future_candles_do_not_change_prior_snapshots`.
- Append-only persistence: `test_checkpoint_restart_and_outcome_idempotence` and
  `test_phase1c_decisions_and_trade_events_are_restart_safe`.

The matrix asserts coverage, not profitability. Passing these fixtures establishes deterministic
behavior for the approved rules only.
