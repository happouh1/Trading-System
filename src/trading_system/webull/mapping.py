"""Exact Phase 1 plan to Webull sandbox stock mapping."""

from __future__ import annotations

import base64
import hashlib

from trading_system.domain import Direction, TradePlan
from trading_system.webull.contracts import WebullSide, WebullStockOrder


def client_order_id(intent_id: str) -> str:
    if not intent_id:
        raise ValueError("internal intent ID is required")
    digest = hashlib.sha256(intent_id.encode("utf-8")).digest()
    return base64.b32encode(digest).decode("ascii").rstrip("=")[:32]


def map_stock_order(plan: TradePlan, intent_id: str, quantity: int) -> WebullStockOrder:
    if plan.direction is Direction.LONG:
        side = WebullSide.BUY
    elif plan.direction is Direction.SHORT:
        side = WebullSide.SELL_SHORT
    else:
        raise ValueError("Webull stock order requires a directional plan")
    return WebullStockOrder(client_order_id(intent_id), plan.symbol, side, quantity)
