"""Immutable Phase 3C Webull sandbox contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType


def _aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Webull timestamps must be timezone-aware")


class WebullSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    SELL_SHORT = "SELL_SHORT"


class WebullOrderStatus(StrEnum):
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELED = "CANCELED"


class WebullSubmissionEventType(StrEnum):
    PREPARED = "PREPARED"
    CALL_STARTED = "CALL_STARTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    REJECTED = "REJECTED"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_SUBMITTED = "NOT_SUBMITTED"
    RECOVERED = "RECOVERED"


@dataclass(frozen=True, slots=True)
class WebullCredentials:
    app_key: str = field(repr=False)
    app_secret: str = field(repr=False)
    account_id: str = field(repr=False)

    def __post_init__(self) -> None:
        if not self.app_key or not self.app_secret or not self.account_id:
            raise ValueError("complete Webull sandbox credentials are required")


@dataclass(frozen=True, slots=True)
class WebullStockOrder:
    client_order_id: str
    symbol: str
    side: WebullSide
    quantity: int
    order_type: str = "MARKET"
    time_in_force: str = "DAY"
    support_trading_session: str = "CORE"

    def __post_init__(self) -> None:
        if not 1 <= len(self.client_order_id) <= 32:
            raise ValueError("Webull client order ID must contain 1-32 characters")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("Webull stock symbol must be uppercase")
        if isinstance(self.quantity, bool) or self.quantity <= 0:
            raise ValueError("Webull stock quantity must be a positive integer")
        if self.order_type != "MARKET" or self.time_in_force != "DAY":
            raise ValueError("Phase 3C supports MARKET DAY stock orders only")
        if self.support_trading_session != "CORE":
            raise ValueError("Phase 3C supports CORE regular-session orders only")

    def sdk_payload(self) -> dict[str, object]:
        return {
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
            "support_trading_session": self.support_trading_session,
        }


@dataclass(frozen=True, slots=True)
class WebullResponse:
    status_code: int
    payload: Mapping[str, object]

    def __post_init__(self) -> None:
        if not 100 <= self.status_code <= 599:
            raise ValueError("invalid Webull HTTP status code")
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


@dataclass(frozen=True, slots=True)
class WebullOpenOrder:
    client_order_id: str
    broker_order_id: str
    symbol: str
    side: WebullSide
    quantity: int
    filled_quantity: int
    order_type: str
    time_in_force: str
    support_trading_session: str
    status: str
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None

    def __post_init__(self) -> None:
        if not 1 <= len(self.client_order_id) <= 32 or not self.broker_order_id:
            raise ValueError("Webull open-order identities are invalid")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("Webull open-order symbol must be uppercase")
        if isinstance(self.quantity, bool) or self.quantity <= 0:
            raise ValueError("Webull open-order quantity must be positive")
        if (
            isinstance(self.filled_quantity, bool)
            or self.filled_quantity < 0
            or self.filled_quantity > self.quantity
        ):
            raise ValueError("Webull open-order filled quantity is invalid")
        for name in (
            "order_type", "time_in_force", "support_trading_session", "status"
        ):
            value = getattr(self, name)
            if not value or value != value.upper():
                raise ValueError(f"Webull open-order {name} must be uppercase")
        for name in ("limit_price", "stop_price"):
            value = getattr(self, name)
            if value is not None and (not value.is_finite() or value <= 0):
                raise ValueError(f"Webull open-order {name} is invalid")


@dataclass(frozen=True, slots=True)
class AccountVerification:
    verification_id: str
    session_id: str
    occurred_at: datetime
    account_id_hash: str
    account_count: int

    def __post_init__(self) -> None:
        _aware(self.occurred_at)
        if self.account_count <= 0:
            raise ValueError("account verification requires at least one account")


@dataclass(frozen=True, slots=True)
class WebullOrderSnapshot:
    account_id: str = field(repr=False)
    broker_order_id: str
    client_order_id: str
    symbol: str
    side: WebullSide
    quantity: int
    filled_quantity: int
    status: WebullOrderStatus

    def __post_init__(self) -> None:
        if not self.account_id or not self.broker_order_id or not self.client_order_id:
            raise ValueError("Webull order identities are required")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("Webull order symbol must be uppercase")
        if isinstance(self.quantity, bool) or self.quantity <= 0:
            raise ValueError("Webull order quantity must be positive")
        if (
            isinstance(self.filled_quantity, bool)
            or self.filled_quantity < 0
            or self.filled_quantity > self.quantity
        ):
            raise ValueError("Webull filled quantity is invalid")
        if self.status is WebullOrderStatus.PARTIALLY_FILLED and not (
            0 < self.filled_quantity < self.quantity
        ):
            raise ValueError("partial-fill status requires a partial quantity")
        if self.status is WebullOrderStatus.FILLED and self.filled_quantity != self.quantity:
            raise ValueError("filled status requires the full quantity")
        if self.status in {
            WebullOrderStatus.ACKNOWLEDGED,
            WebullOrderStatus.REJECTED,
        } and self.filled_quantity != 0:
            raise ValueError("unfilled Webull status requires zero filled quantity")


@dataclass(frozen=True, slots=True)
class WebullReconciliation:
    reconciliation_id: str
    session_id: str
    occurred_at: datetime
    matched: bool
    differences: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _aware(self.occurred_at)
        if not self.reconciliation_id or not self.session_id:
            raise ValueError("Webull reconciliation identity is required")
        if self.matched and self.differences:
            raise ValueError("matched Webull reconciliation cannot contain differences")


@dataclass(frozen=True, slots=True)
class WebullEntryRelease:
    release_id: str
    session_id: str
    intent_id: str
    request_hash: str
    provider_timestamp: datetime
    received_at: datetime
    observed_open: Decimal
    adr20: Decimal
    gap_adr: Decimal
    approved: bool
    reason: str

    def __post_init__(self) -> None:
        _aware(self.provider_timestamp)
        _aware(self.received_at)
        if self.received_at < self.provider_timestamp:
            raise ValueError("entry release cannot arrive before its provider timestamp")
        if (
            not self.observed_open.is_finite()
            or not self.adr20.is_finite()
            or not self.gap_adr.is_finite()
            or self.observed_open <= 0
            or self.adr20 <= 0
            or self.gap_adr < 0
        ):
            raise ValueError("entry release prices and distances are invalid")
        if (
            not self.release_id
            or not self.session_id
            or not self.intent_id
            or not self.request_hash
            or not self.reason
        ):
            raise ValueError("entry release identity and reason are required")
