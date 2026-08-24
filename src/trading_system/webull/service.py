"""Read-only verification and explicitly gated sandbox stock operations."""

from __future__ import annotations

import hmac
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal

from trading_system.domain import TradePlan
from trading_system.paper import PaperRegistry
from trading_system.risk import normalized_units
from trading_system.serialization import canonical_hash, deterministic_id
from trading_system.webull.contracts import AccountVerification, WebullCredentials, WebullStockOrder
from trading_system.webull.mapping import map_stock_order
from trading_system.webull.registry import WebullRegistry
from trading_system.webull.transport import WebullTransport


def _account_records(value: object) -> tuple[tuple[str, str | None, str | None], ...]:
    result: list[tuple[str, str | None, str | None]] = []
    if isinstance(value, Mapping):
        internal = value.get("account_id")
        number = value.get("account_number")
        if isinstance(internal, str):
            account_class = value.get("account_class")
            result.append((
                internal,
                number if isinstance(number, str) else None,
                account_class if isinstance(account_class, str) else None,
            ))
        for item in value.values():
            result.extend(_account_records(item))
    elif isinstance(value, (tuple, list)):
        for item in value:
            result.extend(_account_records(item))
    return tuple(dict.fromkeys(result))


class WebullSandboxService:
    def __init__(self, session_id: str, credentials: WebullCredentials,
                 transport: WebullTransport, registry: WebullRegistry,
                 paper_registry: PaperRegistry) -> None:
        self.session_id = session_id
        self.credentials = credentials
        self.transport = transport
        self.registry = registry
        self.paper_registry = paper_registry
        self._verified_account_id: str | None = None

    def discover_accounts(self, occurred_at: datetime) -> tuple[dict[str, str], ...]:
        response = self.transport.account_list()
        self.registry.insert_envelope(
            self.session_id, "ACCOUNT_DISCOVERY", occurred_at, response
        )
        if not 200 <= response.status_code < 300:
            raise ValueError("Webull sandbox account discovery failed")
        result: list[dict[str, str]] = []

        def visit(value: object) -> None:
            if isinstance(value, Mapping):
                number = value.get("account_number")
                if isinstance(number, str):
                    result.append({
                        "account_label": str(value.get("account_label", "UNKNOWN")),
                        "account_class": str(value.get("account_class", "UNKNOWN")),
                        "account_type": str(value.get("account_type", "UNKNOWN")),
                        "account_number_masked": f"****{number[-4:]}",
                    })
                for item in value.values():
                    visit(item)
            elif isinstance(value, (tuple, list)):
                for item in value:
                    visit(item)

        visit(response.payload)
        return tuple(result)

    def verify_account(
        self, occurred_at: datetime, account_class: str | None = None
    ) -> AccountVerification:
        response = self.transport.account_list()
        self.registry.insert_envelope(self.session_id, "ACCOUNT_LIST", occurred_at, response)
        if not 200 <= response.status_code < 300:
            raise ValueError("Webull sandbox account-list request failed")
        accounts = _account_records(response.payload)
        if account_class is None:
            matched = tuple(
                internal for internal, number, _class in accounts
                if hmac.compare_digest(internal, self.credentials.account_id)
                or (number is not None and hmac.compare_digest(number, self.credentials.account_id))
            )
        else:
            matched = tuple(
                internal for internal, _number, item_class in accounts
                if item_class == account_class
            )
        if len(matched) != 1:
            raise ValueError("Webull sandbox account selector did not resolve exactly one account")
        internal_account_id = matched[0]
        self._verified_account_id = internal_account_id
        account_hash = canonical_hash({"account_id": internal_account_id})
        item = AccountVerification(
            deterministic_id("webull_verification", (self.session_id, occurred_at, account_hash)),
            self.session_id, occurred_at, account_hash, len(accounts),
        )
        self.registry.insert_verification(item)
        for operation, response_item in (
            ("BALANCE", self.transport.balance(internal_account_id)),
            ("POSITIONS", self.transport.positions(internal_account_id)),
            ("OPEN_ORDERS", self.transport.open_orders(internal_account_id)),
        ):
            self.registry.insert_envelope(
                self.session_id, operation, occurred_at, response_item
            )
            if not 200 <= response_item.status_code < 300:
                raise ValueError(f"Webull read-only verification failed: {operation}")
        return item

    def preview(self, intent_id: str, order: WebullStockOrder,
                occurred_at: datetime) -> bool:
        if self._verified_account_id is None:
            raise ValueError("read-only Webull account verification is required before preview")
        intent = self.paper_registry.load_intent(intent_id)
        if intent.session_id != self.session_id:
            raise ValueError("Webull preview intent belongs to another paper session")
        plan = intent.payload.get("trade_plan")
        if not isinstance(plan, TradePlan):
            raise ValueError("Webull preview intent has no immutable trade plan")
        expected = map_stock_order(plan, intent_id, order.quantity)
        if order != expected:
            raise ValueError("Webull preview request does not match its Phase 1 plan")
        stored_status = self.registry.preview_status(
            self.session_id, intent_id, canonical_hash(order)
        )
        if stored_status is not None:
            return stored_status
        response = self.transport.preview(self._verified_account_id, order)
        self.registry.insert_envelope(
            self.session_id, "PREVIEW", occurred_at, response, order
        )
        response_order = response.payload.get("order")
        accepted = (
            200 <= response.status_code < 300
            and response.payload.get("accepted") is True
            and response.payload.get("account_id") == self._verified_account_id
            and isinstance(response_order, Mapping)
            and canonical_hash(response_order) == canonical_hash(order.sdk_payload())
        )
        self.registry.insert_preview(
            self.session_id, intent_id, occurred_at, order, response, accepted=accepted
        )
        return accepted

    def preview_intent(
        self, intent_id: str, normalized_risk_budget: Decimal, occurred_at: datetime
    ) -> tuple[WebullStockOrder, bool]:
        intent = self.paper_registry.load_intent(intent_id)
        plan = intent.payload.get("trade_plan")
        if not isinstance(plan, TradePlan):
            raise ValueError("Webull preview intent has no immutable trade plan")
        quantity_decimal = normalized_units(
            normalized_risk_budget, plan.risk_per_unit
        )
        if quantity_decimal <= 0:
            raise ValueError("Phase 1 normalized quantity is zero")
        quantity = int(quantity_decimal)
        order = map_stock_order(plan, intent_id, quantity)
        return order, self.preview(intent_id, order, occurred_at)

    def submit(self, intent_id: str, order: WebullStockOrder, occurred_at: datetime,
               *, environment_enabled: bool, cli_enabled: bool) -> None:
        raise ValueError("Webull sandbox submission is not authorized in Phase 3C-3")
