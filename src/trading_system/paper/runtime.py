"""Fail-closed provider-neutral Phase 3B runtime."""

from __future__ import annotations

from datetime import datetime

from trading_system.domain import TradePlan
from trading_system.paper.adapters import PaperAdapter
from trading_system.paper.contracts import (
    CompletedBarEnvelope,
    IntentStatus,
    OrderIntent,
    PaperMode,
    ReconciliationResult,
    RuntimeState,
)
from trading_system.paper.registry import PaperRegistry
from trading_system.serialization import deterministic_id


class PaperRuntime:
    def __init__(self, registry: PaperRegistry, session_id: str,
                 mode: PaperMode, adapter: PaperAdapter,
                 completed_bar_lateness_seconds: int = 120) -> None:
        self.registry = registry
        self.session_id = session_id
        self.mode = mode
        self.adapter = adapter
        self.completed_bar_lateness_seconds = completed_bar_lateness_seconds

    def start(self, occurred_at: datetime) -> RuntimeState:
        self.registry.transition(self.session_id, RuntimeState.STARTING, occurred_at, "START")
        target = (RuntimeState.SHADOW if self.mode is PaperMode.SHADOW
                  else RuntimeState.PAPER_ENABLED)
        self.registry.transition(self.session_id, target, occurred_at, "IDENTITY_VALIDATED")
        return target

    def record_plan(self, plan: TradePlan, scheduled_open: datetime,
                    occurred_at: datetime, source_decision_id: str | None = None) -> OrderIntent:
        state = self.registry.current_state(self.session_id)
        if state not in (RuntimeState.SHADOW, RuntimeState.PAPER_ENABLED):
            raise ValueError("paper session is not accepting intents")
        intent_id = deterministic_id(
            "paper_intent", (self.session_id, plan.plan_id, scheduled_open, "3B.1.0")
        )
        initial_status = (IntentStatus.SHADOWED if state is RuntimeState.SHADOW
                          else IntentStatus.RECORDED)
        payload: dict[str, object] = {"trade_plan": plan}
        if source_decision_id is not None:
            payload["source_decision_id"] = source_decision_id
        intent = OrderIntent(
            intent_id, self.session_id, plan.plan_id, scheduled_open, plan.created_at,
            initial_status, payload,
        )
        inserted = self.registry.insert_intent(intent)
        if state is RuntimeState.SHADOW or not inserted:
            return intent
        result = self.adapter.submit(intent, occurred_at)
        self.registry.insert_adapter_result(self.session_id, result)
        if result.status is IntentStatus.AMBIGUOUS:
            self.halt(occurred_at, "AMBIGUOUS_ADAPTER_STATE")
        return intent

    def process_completed_bar(self, envelope: CompletedBarEnvelope,
                              occurred_at: datetime) -> str:
        state = self.registry.current_state(self.session_id)
        if state not in (RuntimeState.SHADOW, RuntimeState.PAPER_ENABLED):
            raise ValueError("paper session is not accepting bars")
        lateness = (envelope.received_at - envelope.candle.close_time).total_seconds()
        if lateness > self.completed_bar_lateness_seconds:
            self.registry.insert_incident(
                self.session_id, occurred_at, "STALE_COMPLETED_BAR",
                (envelope.candle.candle_id,),
            )
            self.halt(occurred_at, "STALE_COMPLETED_BAR")
            raise ValueError("completed candle is stale")
        prior = self.registry.latest_checkpoint(self.session_id)
        order = {"1w": 0, "1d": 1, "4h": 2, "1h": 3}
        if prior is not None and envelope.candle.close_time < prior[0]:
            raise ValueError("out-of-order completed candle")
        if (prior is not None and envelope.candle.close_time == prior[0]
                and order[envelope.candle.timeframe.value] <= order[prior[2]]):
            raise ValueError("completed candle violates fixed timeframe order")
        state_hash = deterministic_id(
            "paper_state", (prior[1] if prior else "GENESIS", envelope)
        )
        self.registry.insert_checkpoint(
            self.session_id, envelope.candle.candle_id, envelope.candle.timeframe.value,
            envelope.candle.close_time, state_hash,
            {"candle_id": envelope.candle.candle_id,
             "source_revision": envelope.source_revision},
        )
        return state_hash

    def heartbeat(self, occurred_at: datetime) -> None:
        self.registry.insert_heartbeat(self.session_id, occurred_at)

    def reconcile(self, occurred_at: datetime) -> ReconciliationResult:
        expected = self.registry.acknowledged_order_ids(self.session_id)
        actual = self.adapter.order_ids()
        differences = tuple(
            [*(f"MISSING:{item}" for item in sorted(expected - actual)),
             *(f"UNKNOWN:{item}" for item in sorted(actual - expected))]
        )
        result = ReconciliationResult(
            deterministic_id("paper_reconciliation", (self.session_id, occurred_at, differences)),
            self.session_id, occurred_at, not differences, differences,
        )
        self.registry.insert_reconciliation(result)
        if differences:
            self.registry.insert_incident(
                self.session_id, occurred_at, "RECONCILIATION_MISMATCH", differences
            )
            self.halt(occurred_at, "RECONCILIATION_MISMATCH")
        return result

    def halt(self, occurred_at: datetime, reason: str) -> None:
        if self.registry.current_state(self.session_id) is RuntimeState.HALTED:
            return
        self.registry.transition(self.session_id, RuntimeState.HALTED, occurred_at, reason)

    def drain(self, occurred_at: datetime) -> None:
        self.registry.transition(self.session_id, RuntimeState.DRAINING, occurred_at, "DRAIN")
        self.registry.transition(self.session_id, RuntimeState.STOPPED, occurred_at, "DRAINED")
