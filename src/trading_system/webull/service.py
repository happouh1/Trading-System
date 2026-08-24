"""Read-only verification and explicitly gated sandbox stock operations."""

from __future__ import annotations

import hmac
from collections.abc import Mapping
from datetime import datetime

from trading_system.paper import PaperRegistry, RuntimeState
from trading_system.serialization import canonical_hash, deterministic_id
from trading_system.webull.contracts import AccountVerification, WebullCredentials, WebullStockOrder
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
        response = self.transport.preview(self._verified_account_id, order)
        self.registry.insert_envelope(
            self.session_id, "PREVIEW", occurred_at, response, order
        )
        self.registry.insert_preview(self.session_id, intent_id, occurred_at, order, response)
        return 200 <= response.status_code < 300

    def submit(self, intent_id: str, order: WebullStockOrder, occurred_at: datetime,
               *, environment_enabled: bool, cli_enabled: bool) -> None:
        if not environment_enabled or not cli_enabled:
            raise ValueError("Webull sandbox submission requires two independent enablement gates")
        if self.paper_registry.current_state(self.session_id) is not RuntimeState.PAPER_ENABLED:
            raise ValueError("paper session is not enabled for simulated submission")
        request_hash = canonical_hash(order)
        if not self.registry.accepted_preview(self.session_id, intent_id, request_hash):
            raise ValueError("identical accepted Webull preview is required before submission")
        if self.registry.has_mapping(self.session_id, intent_id, request_hash):
            return
        if self._verified_account_id is None:
            raise ValueError("read-only Webull account verification is required before submission")
        response = self.transport.place(self._verified_account_id, order)
        self.registry.insert_envelope(
            self.session_id, "PLACE", occurred_at, response, order
        )
        if not 200 <= response.status_code < 300:
            raise ValueError("Webull sandbox order placement failed")
        self.registry.insert_mapping(self.session_id, intent_id, order, response)
