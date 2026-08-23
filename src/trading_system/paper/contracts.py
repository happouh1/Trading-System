"""Immutable provider-neutral Phase 3B paper-runtime contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType

from trading_system.domain import Candle


class PaperMode(StrEnum):
    SHADOW = "SHADOW"
    SIMULATED = "SIMULATED"


class RuntimeState(StrEnum):
    CREATED = "CREATED"
    STARTING = "STARTING"
    SHADOW = "SHADOW"
    PAPER_ENABLED = "PAPER_ENABLED"
    DRAINING = "DRAINING"
    STOPPED = "STOPPED"
    HALTED = "HALTED"


class IntentStatus(StrEnum):
    RECORDED = "RECORDED"
    SHADOWED = "SHADOWED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    REJECTED = "REJECTED"
    AMBIGUOUS = "AMBIGUOUS"


def _aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("paper-runtime timestamps must be timezone-aware")


@dataclass(frozen=True, slots=True)
class PaperSession:
    session_id: str
    created_at: datetime
    mode: PaperMode
    code_version: str
    config_hash: str
    data_revision: str
    calendar_version: str

    def __post_init__(self) -> None:
        _aware(self.created_at)
        if not all(
            (self.session_id, self.code_version, self.config_hash,
             self.data_revision, self.calendar_version)
        ):
            raise ValueError("paper session identity fields are required")


@dataclass(frozen=True, slots=True)
class OrderIntent:
    intent_id: str
    session_id: str
    trade_plan_id: str
    scheduled_open: datetime
    created_at: datetime
    status: IntentStatus
    payload: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _aware(self.scheduled_open)
        _aware(self.created_at)
        if not self.intent_id or not self.trade_plan_id:
            raise ValueError("intent and trade-plan identities are required")
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


@dataclass(frozen=True, slots=True)
class AdapterResult:
    intent_id: str
    status: IntentStatus
    occurred_at: datetime
    adapter_order_id: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        _aware(self.occurred_at)
        if self.status is IntentStatus.ACKNOWLEDGED and not self.adapter_order_id:
            raise ValueError("acknowledged intent requires adapter order identity")


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    reconciliation_id: str
    session_id: str
    occurred_at: datetime
    matched: bool
    differences: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _aware(self.occurred_at)
        if self.matched and self.differences:
            raise ValueError("matched reconciliation cannot contain differences")


@dataclass(frozen=True, slots=True)
class CompletedBarEnvelope:
    candle: Candle
    received_at: datetime
    source_revision: str

    def __post_init__(self) -> None:
        _aware(self.received_at)
        if not self.candle.is_complete:
            raise ValueError("paper runtime accepts completed candles only")
        if self.received_at < self.candle.close_time:
            raise ValueError("completed candle cannot arrive before its close")
        if self.source_revision != self.candle.source_revision:
            raise ValueError("bar envelope source revision mismatch")
