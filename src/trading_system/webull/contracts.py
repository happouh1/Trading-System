"""Immutable Phase 3C Webull sandbox contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType


def _aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Webull timestamps must be timezone-aware")


class WebullSide(StrEnum):
    BUY = "BUY"
    SELL_SHORT = "SELL_SHORT"


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

    def __post_init__(self) -> None:
        if not 1 <= len(self.client_order_id) <= 32:
            raise ValueError("Webull client order ID must contain 1-32 characters")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("Webull stock symbol must be uppercase")
        if isinstance(self.quantity, bool) or self.quantity <= 0:
            raise ValueError("Webull stock quantity must be a positive integer")
        if self.order_type != "MARKET" or self.time_in_force != "DAY":
            raise ValueError("Phase 3C supports MARKET DAY stock orders only")

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
