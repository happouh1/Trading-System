"""Internal-only Phase 3B paper adapters."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from trading_system.paper.contracts import AdapterResult, IntentStatus, OrderIntent
from trading_system.serialization import deterministic_id


class PaperAdapter(Protocol):
    def submit(self, intent: OrderIntent, occurred_at: datetime) -> AdapterResult: ...

    def order_ids(self) -> frozenset[str]: ...


class InternalSimulatorAdapter:
    def __init__(self) -> None:
        self._orders: dict[str, str] = {}

    def submit(self, intent: OrderIntent, occurred_at: datetime) -> AdapterResult:
        order_id = self._orders.setdefault(
            intent.intent_id, deterministic_id("paper_order", intent.intent_id)
        )
        return AdapterResult(intent.intent_id, IntentStatus.ACKNOWLEDGED, occurred_at, order_id)

    def order_ids(self) -> frozenset[str]:
        return frozenset(self._orders.values())


class RejectingAdapter:
    def submit(self, intent: OrderIntent, occurred_at: datetime) -> AdapterResult:
        return AdapterResult(
            intent.intent_id, IntentStatus.REJECTED, occurred_at, reason="ADAPTER_REJECTED"
        )

    def order_ids(self) -> frozenset[str]:
        return frozenset()
