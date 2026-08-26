"""Read-only verification and explicitly gated sandbox stock operations."""

from __future__ import annotations

import hmac
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal

from trading_system.domain import Direction, TradePlan
from trading_system.paper import (
    AdapterResult,
    IntentStatus,
    PaperRegistry,
    RuntimeState,
)
from trading_system.risk import normalized_units
from trading_system.serialization import canonical_hash, deterministic_id
from trading_system.webull.contracts import (
    AccountVerification,
    WebullCredentials,
    WebullEntryRelease,
    WebullOrderSnapshot,
    WebullOrderStatus,
    WebullReconciliation,
    WebullResponse,
    WebullSide,
    WebullStockOrder,
    WebullSubmissionEventType,
)
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


def _positive_integer(value: object, name: str, *, allow_zero: bool = False) -> int:
    if isinstance(value, bool):
        raise ValueError(f"Webull {name} is invalid")
    if isinstance(value, int):
        result = value
    elif isinstance(value, str) and value.isdigit():
        result = int(value)
    else:
        raise ValueError(f"Webull {name} is invalid")
    if result < 0 or (not allow_zero and result == 0):
        raise ValueError(f"Webull {name} is invalid")
    return result


def _signed_integer(value: object, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"Webull {name} is invalid")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.lstrip("-").isdigit():
        return int(value)
    raise ValueError(f"Webull {name} is invalid")


def _snapshot(
    response_payload: Mapping[str, object],
    account_id: str,
    expected: WebullStockOrder,
) -> WebullOrderSnapshot:
    if response_payload.get("account_id") != account_id:
        raise ValueError("Webull order response account mismatch")
    raw = response_payload.get("order")
    if not isinstance(raw, Mapping):
        raise ValueError("Webull order response lacks an order object")
    broker_order_id = raw.get("order_id", response_payload.get("order_id"))
    if not isinstance(broker_order_id, str) or not broker_order_id:
        raise ValueError("Webull order response lacks broker order identity")
    checks = {
        "client_order_id": expected.client_order_id,
        "symbol": expected.symbol,
        "side": expected.side.value,
        "order_type": expected.order_type,
        "time_in_force": expected.time_in_force,
    }
    if any(raw.get(key) != value for key, value in checks.items()):
        raise ValueError("Webull order response does not match the submitted order")
    quantity = _positive_integer(raw.get("quantity"), "order quantity")
    if quantity != expected.quantity:
        raise ValueError("Webull order response quantity mismatch")
    status = WebullOrderStatus(str(raw.get("status")))
    filled = _positive_integer(
        raw.get("filled_quantity"), "filled quantity", allow_zero=True
    )
    return WebullOrderSnapshot(
        account_id,
        broker_order_id,
        expected.client_order_id,
        expected.symbol,
        WebullSide(str(raw.get("side"))),
        quantity,
        filled,
        status,
    )


_ALLOWED_TRANSITIONS: dict[WebullOrderStatus | None, frozenset[WebullOrderStatus]] = {
    None: frozenset(WebullOrderStatus),
    WebullOrderStatus.ACKNOWLEDGED: frozenset({
        WebullOrderStatus.ACKNOWLEDGED,
        WebullOrderStatus.PARTIALLY_FILLED,
        WebullOrderStatus.FILLED,
        WebullOrderStatus.REJECTED,
        WebullOrderStatus.CANCELED,
    }),
    WebullOrderStatus.PARTIALLY_FILLED: frozenset({
        WebullOrderStatus.PARTIALLY_FILLED,
        WebullOrderStatus.FILLED,
        WebullOrderStatus.CANCELED,
    }),
    WebullOrderStatus.FILLED: frozenset({WebullOrderStatus.FILLED}),
    WebullOrderStatus.REJECTED: frozenset({WebullOrderStatus.REJECTED}),
    WebullOrderStatus.CANCELED: frozenset({WebullOrderStatus.CANCELED}),
}


class WebullSandboxService:
    def __init__(self, session_id: str, credentials: WebullCredentials,
                 transport: WebullTransport, registry: WebullRegistry,
                 paper_registry: PaperRegistry,
                 reconciliation_max_age_seconds: int = 60,
                 max_gap_adr: Decimal = Decimal("0.25"),
                 max_release_lateness_seconds: int = 120) -> None:
        self.session_id = session_id
        self.credentials = credentials
        self.transport = transport
        self.registry = registry
        self.paper_registry = paper_registry
        self.reconciliation_max_age_seconds = reconciliation_max_age_seconds
        self.max_gap_adr = max_gap_adr
        self.max_release_lateness_seconds = max_release_lateness_seconds
        self._verified_account_id: str | None = None
        self._verified_at: datetime | None = None

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
        self._verified_at = occurred_at
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
               *, environment_enabled: bool, cli_enabled: bool) -> WebullOrderSnapshot:
        account_id = self._require_submission_gates(
            intent_id, order, occurred_at, environment_enabled, cli_enabled
        )
        request_hash = canonical_hash(order)
        mapping = self.registry.mapping_for_intent(
            self.session_id, intent_id, request_hash
        )
        if mapping is not None:
            response = self.transport.order_detail(account_id, order.client_order_id)
            self.registry.insert_envelope(
                self.session_id, "ORDER_DETAIL_IDEMPOTENT", occurred_at, response, order
            )
            return self._record_snapshot(response, order, occurred_at)
        prior = self.registry.submission_event_types(
            self.session_id, intent_id, request_hash
        )
        if WebullSubmissionEventType.CALL_STARTED in prior:
            raise ValueError("unresolved Webull submission requires recovery")
        self.registry.insert_submission_event(
            self.session_id,
            intent_id,
            order,
            occurred_at,
            WebullSubmissionEventType.PREPARED,
        )
        self.registry.insert_submission_event(
            self.session_id,
            intent_id,
            order,
            occurred_at,
            WebullSubmissionEventType.CALL_STARTED,
        )
        try:
            response = self.transport.place(account_id, order)
        except Exception as error:
            return self._resolve_ambiguity(
                intent_id,
                order,
                occurred_at,
                {"error_type": type(error).__name__},
            )
        self.registry.insert_envelope(
            self.session_id, "PLACE", occurred_at, response, order
        )
        try:
            item = self._record_snapshot(response, order, occurred_at)
        except (TypeError, ValueError):
            return self._resolve_ambiguity(
                intent_id,
                order,
                occurred_at,
                {"response_status": response.status_code, "reason": "INVALID_RESPONSE"},
            )
        accepted = (
            200 <= response.status_code < 300
            and response.payload.get("accepted") is True
            and item.status is not WebullOrderStatus.REJECTED
        )
        rejected = (
            200 <= response.status_code < 500
            and response.payload.get("accepted") is False
            and item.status is WebullOrderStatus.REJECTED
        )
        if not accepted and not rejected:
            return self._resolve_ambiguity(
                intent_id,
                order,
                occurred_at,
                {"response_status": response.status_code, "reason": "CONTRADICTORY_RESPONSE"},
            )
        self.registry.insert_mapping(self.session_id, intent_id, order, response)
        self.registry.insert_submission_event(
            self.session_id,
            intent_id,
            order,
            occurred_at,
            (
                WebullSubmissionEventType.ACKNOWLEDGED
                if accepted else WebullSubmissionEventType.REJECTED
            ),
            {"broker_order_id": item.broker_order_id, "status": item.status},
        )
        self.paper_registry.insert_adapter_result(
            self.session_id,
            AdapterResult(
                intent_id,
                IntentStatus.ACKNOWLEDGED if accepted else IntentStatus.REJECTED,
                occurred_at,
                item.broker_order_id if accepted else None,
                None if accepted else "WEBULL_REJECTED",
            ),
        )
        return item

    def record_entry_release(
        self,
        intent_id: str,
        order: WebullStockOrder,
        provider_timestamp: datetime,
        received_at: datetime,
        observed_open: Decimal,
        adr20: Decimal,
    ) -> WebullEntryRelease:
        if provider_timestamp.tzinfo is None or received_at.tzinfo is None:
            raise ValueError("entry release timestamps must be timezone-aware")
        intent = self.paper_registry.load_intent(intent_id)
        if intent.session_id != self.session_id:
            raise ValueError("Webull entry release belongs to another paper session")
        plan = intent.payload.get("trade_plan")
        if not isinstance(plan, TradePlan):
            raise ValueError("Webull entry release has no immutable trade plan")
        if order != map_stock_order(plan, intent_id, order.quantity):
            raise ValueError("Webull entry release order does not match its Phase 1 plan")
        if provider_timestamp != intent.scheduled_open:
            raise ValueError("entry release timestamp must equal the scheduled XNYS open")
        if (
            not observed_open.is_finite()
            or not adr20.is_finite()
            or observed_open <= 0
            or adr20 <= 0
        ):
            raise ValueError("entry release open and ADR20 must be positive")
        lateness = (received_at - provider_timestamp).total_seconds()
        if lateness < 0:
            raise ValueError("entry release cannot arrive before the scheduled open")
        adverse_gap = (
            observed_open - plan.planned_entry
            if plan.direction is Direction.LONG
            else plan.planned_entry - observed_open
        )
        gap_adr = max(Decimal(0), adverse_gap) / adr20
        if lateness > self.max_release_lateness_seconds:
            approved, reason = False, "STALE_OPEN_EVIDENCE"
        elif gap_adr > self.max_gap_adr:
            approved, reason = False, "ENTRY_GAP_TOO_LARGE"
        else:
            approved, reason = True, "ENTRY_RELEASED"
        request_hash = canonical_hash(order)
        item = WebullEntryRelease(
            deterministic_id(
                "webull_entry_release", (self.session_id, intent_id, request_hash)
            ),
            self.session_id,
            intent_id,
            request_hash,
            provider_timestamp,
            received_at,
            observed_open,
            adr20,
            gap_adr,
            approved,
            reason,
        )
        self.registry.insert_entry_release(item)
        return item

    def reconcile(
        self, normalized_risk_budget: Decimal, occurred_at: datetime
    ) -> WebullReconciliation:
        account_id = self._require_verified()
        open_response = self.transport.open_orders(account_id)
        position_response = self.transport.positions(account_id)
        self.registry.insert_envelope(
            self.session_id, "RECONCILE_OPEN_ORDERS", occurred_at, open_response
        )
        self.registry.insert_envelope(
            self.session_id, "RECONCILE_POSITIONS", occurred_at, position_response
        )
        differences: list[str] = []
        if not 200 <= open_response.status_code < 300:
            differences.append(f"OPEN_ORDERS_HTTP:{open_response.status_code}")
            open_clients: set[str] = set()
        else:
            try:
                open_clients = self._open_client_ids(open_response, account_id)
            except (TypeError, ValueError):
                differences.append("OPEN_ORDERS_INVALID")
                open_clients = set()
        mappings = self.registry.mappings(self.session_id)
        expected_clients = {client_id for _intent, client_id, _hash, _broker in mappings}
        differences.extend(
            f"UNKNOWN_ORDER:{item}" for item in sorted(open_clients - expected_clients)
        )
        expected_open: set[str] = set()
        for intent_id, client_id, request_hash, broker_order_id in mappings:
            order = self.order_for_intent(intent_id, normalized_risk_budget)
            if canonical_hash(order) != request_hash or order.client_order_id != client_id:
                differences.append(f"INTERNAL_MAPPING_MISMATCH:{client_id}")
                continue
            try:
                detail = self.transport.order_detail(account_id, client_id)
            except Exception as error:
                differences.append(
                    f"ORDER_QUERY_FAILED:{client_id}:{type(error).__name__}"
                )
                continue
            self.registry.insert_envelope(
                self.session_id, "RECONCILE_ORDER_DETAIL", occurred_at, detail, order
            )
            if detail.status_code == 404:
                differences.append(f"MISSING_ORDER:{client_id}")
                continue
            if not 200 <= detail.status_code < 300:
                differences.append(f"ORDER_DETAIL_HTTP:{client_id}:{detail.status_code}")
                continue
            try:
                item = self._record_snapshot(detail, order, occurred_at)
            except (TypeError, ValueError):
                differences.append(f"ORDER_MISMATCH:{client_id}")
                continue
            if broker_order_id is not None and item.broker_order_id != broker_order_id:
                differences.append(f"BROKER_ID_MISMATCH:{client_id}")
            if item.status in {
                WebullOrderStatus.ACKNOWLEDGED,
                WebullOrderStatus.PARTIALLY_FILLED,
            }:
                expected_open.add(client_id)
        differences.extend(
            f"MISSING_OPEN_ORDER:{item}" for item in sorted(expected_open - open_clients)
        )
        if not 200 <= position_response.status_code < 300:
            differences.append(f"POSITIONS_HTTP:{position_response.status_code}")
            actual_positions: dict[str, int] = {}
        else:
            try:
                actual_positions = self._positions(position_response, account_id)
            except (TypeError, ValueError):
                differences.append("POSITIONS_INVALID")
                actual_positions = {}
        expected_positions = self.registry.expected_positions(self.session_id)
        for symbol in sorted(set(actual_positions) | set(expected_positions)):
            if actual_positions.get(symbol, 0) != expected_positions.get(symbol, 0):
                differences.append(
                    f"POSITION_MISMATCH:{symbol}:"
                    f"{expected_positions.get(symbol, 0)}:{actual_positions.get(symbol, 0)}"
                )
        result = WebullReconciliation(
            deterministic_id(
                "webull_reconciliation", (self.session_id, occurred_at, tuple(differences))
            ),
            self.session_id,
            occurred_at,
            not differences,
            tuple(differences),
        )
        self.registry.insert_reconciliation(result)
        if differences:
            self._halt(occurred_at, "WEBULL_RECONCILIATION_MISMATCH", tuple(differences))
        return result
    def recover(
        self, normalized_risk_budget: Decimal, occurred_at: datetime
    ) -> tuple[WebullOrderSnapshot, ...]:
        account_id = self._require_verified()
        recovered: list[WebullOrderSnapshot] = []
        for intent_id in self.registry.unresolved_submission_intents(self.session_id):
            order = self.order_for_intent(intent_id, normalized_risk_budget)
            events = self.registry.submission_event_types(
                self.session_id, intent_id, canonical_hash(order)
            )
            if WebullSubmissionEventType.CALL_STARTED not in events:
                self.registry.insert_submission_event(
                    self.session_id,
                    intent_id,
                    order,
                    occurred_at,
                    WebullSubmissionEventType.NOT_SUBMITTED,
                )
                continue
            try:
                response = self.transport.order_detail(account_id, order.client_order_id)
            except Exception as error:
                self._halt(
                    occurred_at,
                    "WEBULL_RECOVERY_QUERY_FAILED",
                    (order.client_order_id, type(error).__name__),
                )
                continue
            self.registry.insert_envelope(
                self.session_id, "RECOVERY_ORDER_DETAIL", occurred_at, response, order
            )
            if response.status_code == 404:
                self.registry.insert_submission_event(
                    self.session_id,
                    intent_id,
                    order,
                    occurred_at,
                    WebullSubmissionEventType.AMBIGUOUS,
                    {"query_status": 404},
                )
                self._halt(
                    occurred_at,
                    "WEBULL_UNRESOLVED_SUBMISSION",
                    (order.client_order_id,),
                )
                continue
            item = self._record_snapshot(response, order, occurred_at)
            self.registry.insert_mapping(self.session_id, intent_id, order, response)
            self.registry.insert_submission_event(
                self.session_id,
                intent_id,
                order,
                occurred_at,
                WebullSubmissionEventType.RECOVERED,
                {"broker_order_id": item.broker_order_id, "status": item.status},
            )
            recovered.append(item)
        return tuple(recovered)

    def ingest_order_notification(
        self,
        intent_id: str,
        normalized_risk_budget: Decimal,
        occurred_at: datetime,
        response: WebullResponse,
    ) -> WebullOrderSnapshot:
        self._require_verified()
        verified_at = self._verified_at
        if verified_at is None:
            raise ValueError("read-only Webull account verification is required")
        latest = self.registry.latest_reconciliation(self.session_id)
        if latest is None or not latest[1] or latest[0] < verified_at:
            raise ValueError(
                "successful REST reconciliation is required before order notifications"
            )
        order = self.order_for_intent(intent_id, normalized_risk_budget)
        if self.registry.mapping_for_intent(
            self.session_id, intent_id, canonical_hash(order)
        ) is None:
            self.registry.insert_envelope(
                self.session_id, "ORDER_NOTIFICATION", occurred_at, response, order
            )
            self._halt(
                occurred_at,
                "WEBULL_UNEXPECTED_ORDER_NOTIFICATION",
                (order.client_order_id,),
            )
            raise ValueError("Webull order notification has no internal mapping")
        self.registry.insert_envelope(
            self.session_id, "ORDER_NOTIFICATION", occurred_at, response, order
        )
        return self._record_snapshot(response, order, occurred_at)

    def _require_verified(self) -> str:
        if self._verified_account_id is None or self._verified_at is None:
            raise ValueError("read-only Webull account verification is required")
        return self._verified_account_id

    def _require_submission_gates(
        self,
        intent_id: str,
        order: WebullStockOrder,
        occurred_at: datetime,
        environment_enabled: bool,
        cli_enabled: bool,
    ) -> str:
        account_id = self._require_verified()
        verified_at = self._verified_at
        if verified_at is None:
            raise ValueError("read-only Webull account verification is required")
        if not environment_enabled or not cli_enabled:
            raise ValueError("Webull sandbox submission requires both independent enablement gates")
        unresolved = self.registry.unresolved_submission_intents(self.session_id)
        if unresolved:
            raise ValueError("all unresolved Webull submissions must be recovered first")
        if self.paper_registry.current_state(self.session_id) is not RuntimeState.PAPER_ENABLED:
            raise ValueError("Webull submission requires PAPER_ENABLED state")
        intent = self.paper_registry.load_intent(intent_id)
        if intent.session_id != self.session_id:
            raise ValueError("Webull submission intent belongs to another paper session")
        plan = intent.payload.get("trade_plan")
        if not isinstance(plan, TradePlan):
            raise ValueError("Webull submission intent has no immutable trade plan")
        if order != map_stock_order(plan, intent_id, order.quantity):
            raise ValueError("Webull submission request does not match its Phase 1 plan")
        request_hash = canonical_hash(order)
        if not self.registry.accepted_preview(self.session_id, intent_id, request_hash):
            raise ValueError("identical accepted Webull preview is required")
        release = self.registry.entry_release_status(
            self.session_id, intent_id, request_hash
        )
        if release is None or not release[1]:
            raise ValueError("approved next-open entry release is required")
        release_received_at = release[0]
        if release_received_at > occurred_at:
            raise ValueError("Webull submission cannot precede its entry release")
        if occurred_at < intent.scheduled_open:
            raise ValueError("Webull submission cannot precede its scheduled open")
        open_age = (occurred_at - intent.scheduled_open).total_seconds()
        if open_age > self.max_release_lateness_seconds:
            raise ValueError("Webull next-open entry release is stale")
        latest = self.registry.latest_reconciliation(self.session_id)
        if latest is None or not latest[1] or latest[0] < verified_at:
            raise ValueError("current successful Webull reconciliation is required")
        last_activity = self.registry.latest_order_activity(self.session_id)
        if last_activity is not None and latest[0] < last_activity:
            raise ValueError("Webull reconciliation predates order activity")
        age = (occurred_at - latest[0]).total_seconds()
        if age < 0 or age > self.reconciliation_max_age_seconds:
            raise ValueError("current successful Webull reconciliation is stale")
        return account_id

    def order_for_intent(
        self, intent_id: str, normalized_risk_budget: Decimal
    ) -> WebullStockOrder:
        intent = self.paper_registry.load_intent(intent_id)
        plan = intent.payload.get("trade_plan")
        if not isinstance(plan, TradePlan):
            raise ValueError("Webull intent has no immutable trade plan")
        quantity = int(normalized_units(normalized_risk_budget, plan.risk_per_unit))
        if quantity <= 0:
            raise ValueError("Phase 1 normalized quantity is zero")
        return map_stock_order(plan, intent_id, quantity)

    def _record_snapshot(
        self, response: WebullResponse, order: WebullStockOrder, occurred_at: datetime
    ) -> WebullOrderSnapshot:
        response_payload = response.payload
        item = _snapshot(response_payload, self._require_verified(), order)
        prior_raw = self.registry.latest_broker_status(
            self.session_id, item.client_order_id
        )
        prior = None if prior_raw is None else WebullOrderStatus(prior_raw)
        if item.status not in _ALLOWED_TRANSITIONS[prior]:
            self._halt(
                occurred_at,
                "WEBULL_IMPOSSIBLE_ORDER_TRANSITION",
                (str(prior), item.status.value, item.client_order_id),
            )
            raise ValueError("impossible Webull order status transition")
        self.registry.insert_broker_event(self.session_id, occurred_at, item)
        self.registry.insert_execution(self.session_id, occurred_at, item)
        return item

    def _resolve_ambiguity(
        self,
        intent_id: str,
        order: WebullStockOrder,
        occurred_at: datetime,
        detail: object = (),
    ) -> WebullOrderSnapshot:
        account_id = self._require_verified()
        self.registry.insert_submission_event(
            self.session_id,
            intent_id,
            order,
            occurred_at,
            WebullSubmissionEventType.AMBIGUOUS,
            detail,
        )
        self._halt(
            occurred_at, "WEBULL_AMBIGUOUS_SUBMISSION", (order.client_order_id,)
        )
        try:
            detail = self.transport.order_detail(account_id, order.client_order_id)
        except Exception as error:
            self.registry.insert_incident(
                self.session_id,
                occurred_at,
                "WEBULL_AMBIGUITY_QUERY_FAILED",
                (type(error).__name__, order.client_order_id),
            )
            raise ValueError("Webull ambiguity query failed") from error
        self.registry.insert_envelope(
            self.session_id, "AMBIGUITY_ORDER_DETAIL", occurred_at, detail, order
        )
        if detail.status_code == 404:
            raise ValueError("Webull submission remains ambiguous after query")
        item = self._record_snapshot(detail, order, occurred_at)
        self.registry.insert_mapping(self.session_id, intent_id, order, detail)
        self.registry.insert_submission_event(
            self.session_id,
            intent_id,
            order,
            occurred_at,
            WebullSubmissionEventType.RECOVERED,
            {"broker_order_id": item.broker_order_id, "status": item.status},
        )
        return item

    def _halt(
        self, occurred_at: datetime, reason: str, details: tuple[str, ...]
    ) -> None:
        self.registry.insert_incident(self.session_id, occurred_at, reason, details)
        self.paper_registry.insert_incident(
            self.session_id, occurred_at, reason, details
        )
        if self.paper_registry.current_state(self.session_id) is not RuntimeState.HALTED:
            self.paper_registry.transition(
                self.session_id, RuntimeState.HALTED, occurred_at, reason
            )

    @staticmethod
    def _open_client_ids(response: WebullResponse, account_id: str) -> set[str]:
        payload = response.payload
        if payload.get("account_id") != account_id:
            raise ValueError("Webull open-order account mismatch")
        raw = payload.get("orders")
        if not isinstance(raw, (tuple, list)):
            raise ValueError("Webull open-order response lacks an orders array")
        result: set[str] = set()
        for item in raw:
            if not isinstance(item, Mapping):
                raise ValueError("Webull open-order item is invalid")
            client_id = item.get("client_order_id")
            if not isinstance(client_id, str) or not client_id:
                raise ValueError("Webull open-order item lacks client identity")
            result.add(client_id)
        return result

    @staticmethod
    def _positions(response: WebullResponse, account_id: str) -> dict[str, int]:
        payload = response.payload
        if payload.get("account_id") != account_id:
            raise ValueError("Webull position account mismatch")
        raw = payload.get("positions")
        if not isinstance(raw, (tuple, list)):
            raise ValueError("Webull position response lacks a positions array")
        result: dict[str, int] = {}
        for item in raw:
            if not isinstance(item, Mapping):
                raise ValueError("Webull position item is invalid")
            symbol = item.get("symbol")
            if not isinstance(symbol, str) or symbol != symbol.upper():
                raise ValueError("Webull position symbol is invalid")
            if symbol in result:
                raise ValueError("duplicate Webull position symbol")
            result[symbol] = _signed_integer(item.get("quantity"), "position quantity")
        return result
