"""Exact request identity for the approved Case-1 smoke test."""

from __future__ import annotations

from decimal import Decimal

from trading_system.webull.exit_contracts import WebullExitOrder
from trading_system.webull.mapping import client_order_id


def case1_client_order_id(session_id: str) -> str:
    return client_order_id(f"{session_id}:phase3d5:case1:stop:AAPL:1.00")


def validate_case1_order(session_id: str, order: WebullExitOrder) -> None:
    expected = {
        "client_order_id": case1_client_order_id(session_id),
        "symbol": "AAPL",
        "side": "SELL",
        "quantity": 1,
        "order_type": "STOP_LOSS",
        "time_in_force": "GTC",
        "stop_price": Decimal("1.00"),
        "extended_hours": False,
        "support_trading_session": "CORE",
    }
    actual = {
        "client_order_id": order.client_order_id,
        "symbol": order.symbol,
        "side": order.side.value,
        "quantity": order.quantity,
        "order_type": order.order_type,
        "time_in_force": order.time_in_force,
        "stop_price": order.stop_price,
        "extended_hours": order.extended_hours,
        "support_trading_session": order.support_trading_session,
    }
    if actual != expected:
        raise ValueError("order does not match the exact approved Case-1 transaction")
