"""Immutable Phase 3D sandbox exit-lifecycle contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType

from trading_system.domain import Direction
from trading_system.webull.contracts import WebullSide


def _aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Phase 3D timestamps must be timezone-aware")


def _identity(*values: str) -> None:
    if any(not value for value in values):
        raise ValueError("Phase 3D identities must be non-empty")


def _positive(value: Decimal, name: str) -> None:
    if not value.is_finite() or value <= 0:
        raise ValueError(f"{name} must be a positive finite Decimal")


class PositionLifecycleState(StrEnum):
    ENTRY_PENDING = "ENTRY_PENDING"
    PARTIALLY_OPEN = "PARTIALLY_OPEN"
    CANCELING_ENTRY = "CANCELING_ENTRY"
    OPEN = "OPEN"
    PROTECTING = "PROTECTING"
    PROTECTED = "PROTECTED"
    REPLACING_STOP = "REPLACING_STOP"
    EXIT_QUEUED = "EXIT_QUEUED"
    EXIT_RELEASING = "EXIT_RELEASING"
    CANCELING_STOP = "CANCELING_STOP"
    EXIT_SUBMITTING = "EXIT_SUBMITTING"
    EXIT_WORKING = "EXIT_WORKING"
    STOP_PARTIALLY_FILLED = "STOP_PARTIALLY_FILLED"
    STOP_FILLED = "STOP_FILLED"
    FLATTEN_AUTHORIZED = "FLATTEN_AUTHORIZED"
    FLAT = "FLAT"
    AMBIGUOUS = "AMBIGUOUS"
    HALTED = "HALTED"


class ExitReason(StrEnum):
    STOP_HIT = "STOP_HIT"
    STRUCTURAL_DAMAGE = "STRUCTURAL_DAMAGE"
    OPPOSING_TRAP = "OPPOSING_TRAP"
    MAX_HOLD = "MAX_HOLD"
    EMERGENCY_FLATTEN = "EMERGENCY_FLATTEN"


class BrokerActionKind(StrEnum):
    PLACE_STOP = "PLACE_STOP"
    REPLACE_STOP = "REPLACE_STOP"
    CANCEL_ENTRY = "CANCEL_ENTRY"
    CANCEL_STOP = "CANCEL_STOP"
    PLACE_EXIT = "PLACE_EXIT"


class BrokerActionEventType(StrEnum):
    PREPARED = "PREPARED"
    CALL_STARTED = "CALL_STARTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    REJECTED = "REJECTED"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_SUBMITTED = "NOT_SUBMITTED"
    RECOVERED = "RECOVERED"


@dataclass(frozen=True, slots=True)
class WebullExitOrder:
    client_order_id: str
    symbol: str
    side: WebullSide
    quantity: int
    order_type: str
    time_in_force: str
    stop_price: Decimal | None = None
    extended_hours: bool = False

    def __post_init__(self) -> None:
        if not 1 <= len(self.client_order_id) <= 32:
            raise ValueError("Webull exit client order ID must contain 1-32 characters")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("Webull exit symbol must be uppercase")
        if self.side not in {WebullSide.BUY, WebullSide.SELL}:
            raise ValueError("Webull exit side must reduce a long or short position")
        if isinstance(self.quantity, bool) or self.quantity <= 0:
            raise ValueError("Webull exit quantity must be a positive integer")
        if self.extended_hours:
            raise ValueError("Phase 3D extended-hours exits are prohibited")
        if self.order_type == "STOP_LOSS":
            if self.time_in_force != "GTC" or self.stop_price is None:
                raise ValueError("protective stops require STOP_LOSS/GTC and a stop price")
            _positive(self.stop_price, "raw stop")
        elif self.order_type == "MARKET":
            if self.time_in_force != "DAY" or self.stop_price is not None:
                raise ValueError("queued exits require MARKET/DAY without a stop price")
        else:
            raise ValueError("unsupported Phase 3D exit order type")

    def sdk_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "client_order_id": self.client_order_id,
            "combo_type": "NORMAL",
            "order_type": self.order_type,
            "quantity": str(self.quantity),
            "side": self.side.value,
            "time_in_force": self.time_in_force,
            "entrust_type": "QTY",
            "instrument_type": "EQUITY",
            "market": "US",
            "symbol": self.symbol,
            "extended_hours_trading": False,
        }
        if self.stop_price is not None:
            payload["stop_price"] = format(self.stop_price, "f")
        return payload


@dataclass(frozen=True, slots=True)
class ManagedPosition:
    managed_position_id: str
    session_id: str
    entry_intent_id: str
    entry_client_order_id: str
    entry_broker_order_id: str
    symbol: str
    direction: Direction
    filled_quantity: int
    remaining_quantity: int
    entry_price: Decimal
    initial_stop_adjusted: Decimal
    opened_at: datetime
    config_hash: str
    code_version: str

    def __post_init__(self) -> None:
        _identity(
            self.managed_position_id,
            self.session_id,
            self.entry_intent_id,
            self.entry_client_order_id,
            self.entry_broker_order_id,
            self.config_hash,
            self.code_version,
        )
        _aware(self.opened_at)
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("managed-position symbol must be uppercase")
        if self.direction not in {Direction.LONG, Direction.SHORT}:
            raise ValueError("managed position requires a directional side")
        if (
            isinstance(self.filled_quantity, bool)
            or isinstance(self.remaining_quantity, bool)
            or self.filled_quantity <= 0
            or not 0 <= self.remaining_quantity <= self.filled_quantity
        ):
            raise ValueError("managed-position quantities are invalid")
        _positive(self.entry_price, "entry price")
        _positive(self.initial_stop_adjusted, "initial adjusted stop")


@dataclass(frozen=True, slots=True)
class PositionEvent:
    position_event_id: str
    managed_position_id: str
    session_id: str
    occurred_at: datetime
    state: PositionLifecycleState
    remaining_quantity: int
    reason: str
    evidence_hash: str

    def __post_init__(self) -> None:
        _identity(
            self.position_event_id,
            self.managed_position_id,
            self.session_id,
            self.reason,
            self.evidence_hash,
        )
        _aware(self.occurred_at)
        if isinstance(self.remaining_quantity, bool) or self.remaining_quantity < 0:
            raise ValueError("position-event quantity cannot be negative")
        if self.state is PositionLifecycleState.FLAT and self.remaining_quantity != 0:
            raise ValueError("FLAT position event requires zero remaining quantity")


@dataclass(frozen=True, slots=True)
class ExitIntent:
    exit_intent_id: str
    session_id: str
    managed_position_id: str
    reason: ExitReason
    signal_candle_id: str
    known_at: datetime
    scheduled_open: datetime
    requested_quantity: int
    evidence_hash: str

    def __post_init__(self) -> None:
        _identity(
            self.exit_intent_id,
            self.session_id,
            self.managed_position_id,
            self.signal_candle_id,
            self.evidence_hash,
        )
        _aware(self.known_at)
        _aware(self.scheduled_open)
        if self.scheduled_open <= self.known_at:
            raise ValueError("exit must be scheduled after its causal signal")
        if isinstance(self.requested_quantity, bool) or self.requested_quantity <= 0:
            raise ValueError("exit intent requires a positive full-position quantity")
        if self.reason in {ExitReason.STOP_HIT, ExitReason.EMERGENCY_FLATTEN}:
            raise ValueError("operator and stop outcomes are not strategy exit intents")


@dataclass(frozen=True, slots=True)
class ProtectiveStopVersion:
    stop_version_id: str
    session_id: str
    managed_position_id: str
    client_order_id: str
    known_at: datetime
    quantity: int
    adjusted_stop: Decimal
    adjustment_factor: Decimal
    raw_stop: Decimal
    tick_size: Decimal
    source_candle_id: str
    source_revision: str
    request_hash: str

    def __post_init__(self) -> None:
        _identity(
            self.stop_version_id,
            self.session_id,
            self.managed_position_id,
            self.client_order_id,
            self.source_candle_id,
            self.source_revision,
            self.request_hash,
        )
        _aware(self.known_at)
        if not 1 <= len(self.client_order_id) <= 32:
            raise ValueError("protective client order ID must contain 1-32 characters")
        if isinstance(self.quantity, bool) or self.quantity <= 0:
            raise ValueError("protective stop quantity must be positive")
        for value, name in (
            (self.adjusted_stop, "adjusted stop"),
            (self.adjustment_factor, "adjustment factor"),
            (self.raw_stop, "raw stop"),
            (self.tick_size, "tick size"),
        ):
            _positive(value, name)
        if self.raw_stop != self.adjusted_stop / self.adjustment_factor:
            raise ValueError("raw stop must equal adjusted stop divided by adjustment factor")
        if self.raw_stop % self.tick_size != 0:
            raise ValueError("raw stop must align exactly with verified tick metadata")


@dataclass(frozen=True, slots=True)
class BrokerActionEvent:
    broker_action_id: str
    session_id: str
    managed_position_id: str
    action_kind: BrokerActionKind
    event_type: BrokerActionEventType
    client_order_id: str
    request_hash: str
    occurred_at: datetime
    detail: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _identity(
            self.broker_action_id,
            self.session_id,
            self.managed_position_id,
            self.client_order_id,
            self.request_hash,
        )
        _aware(self.occurred_at)
        object.__setattr__(self, "detail", MappingProxyType(dict(self.detail)))


@dataclass(frozen=True, slots=True)
class ExitAuthorization:
    authorization_id: str
    session_id: str
    config_hash: str
    capability_hash: str
    reconciliation_id: str
    created_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        _identity(
            self.authorization_id,
            self.session_id,
            self.config_hash,
            self.capability_hash,
            self.reconciliation_id,
        )
        _aware(self.created_at)
        _aware(self.expires_at)
        if self.expires_at <= self.created_at:
            raise ValueError("exit authorization expiry must follow creation")


@dataclass(frozen=True, slots=True)
class FlattenAuthorization:
    flatten_auth_id: str
    session_id: str
    managed_position_id: str
    reconciliation_id: str
    symbol: str
    direction: Direction
    created_at: datetime
    used_at: datetime | None = None

    def __post_init__(self) -> None:
        _identity(
            self.flatten_auth_id,
            self.session_id,
            self.managed_position_id,
            self.reconciliation_id,
        )
        _aware(self.created_at)
        if self.used_at is not None:
            _aware(self.used_at)
            if self.used_at < self.created_at:
                raise ValueError("flatten authorization cannot be used before creation")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("flatten symbol must be uppercase")
        if self.direction not in {Direction.LONG, Direction.SHORT}:
            raise ValueError("flatten authorization requires a direction")


@dataclass(frozen=True, slots=True)
class PositionReconciliation:
    reconciliation_id: str
    session_id: str
    managed_position_id: str
    occurred_at: datetime
    expected_quantity: int
    actual_quantity: int
    matched: bool
    differences: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _identity(self.reconciliation_id, self.session_id, self.managed_position_id)
        _aware(self.occurred_at)
        if any(isinstance(item, bool) for item in (self.expected_quantity, self.actual_quantity)):
            raise ValueError("reconciliation quantities must be integers")
        if self.expected_quantity < 0:
            raise ValueError("expected managed quantity cannot be negative")
        if self.matched and (
            self.expected_quantity != self.actual_quantity or self.differences
        ):
            raise ValueError("matched position reconciliation cannot contain differences")
