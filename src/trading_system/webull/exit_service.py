"""Deterministic, fake-transport-only Phase 3D exit lifecycle."""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import datetime, timedelta
from decimal import Decimal
from typing import NoReturn, Protocol

from trading_system.domain import Direction
from trading_system.serialization import canonical_hash, deterministic_id
from trading_system.webull.contracts import (
    WebullOrderSnapshot,
    WebullOrderStatus,
    WebullResponse,
    WebullSide,
)
from trading_system.webull.exit_config import WebullExitCapabilities, WebullExitConfig
from trading_system.webull.exit_contracts import (
    BrokerActionEvent,
    BrokerActionEventType,
    BrokerActionKind,
    ExitAuthorization,
    ExitIntent,
    ExitReason,
    FlattenAuthorization,
    ManagedPosition,
    PositionEvent,
    PositionLifecycleState,
    PositionReconciliation,
    ProtectiveStopVersion,
    WebullExitOrder,
)
from trading_system.webull.exit_registry import WebullExitRegistry


class WebullExitTransport(Protocol):
    def positions(self, account_id: str) -> WebullResponse: ...
    def open_orders(self, account_id: str) -> WebullResponse: ...
    def order_detail(self, account_id: str, client_order_id: str) -> WebullResponse: ...
    def place_exit(self, account_id: str, order: WebullExitOrder) -> WebullResponse: ...
    def replace_exit(self, account_id: str, order: WebullExitOrder) -> WebullResponse: ...
    def cancel_exit(self, account_id: str, client_order_id: str) -> WebullResponse: ...


def protective_client_id(session_id: str, managed_position_id: str) -> str:
    return canonical_hash(
        (session_id, managed_position_id, "protective-stop-v1")
    )[7:39]


def exit_client_id(session_id: str, exit_intent_id: str) -> str:
    return canonical_hash((session_id, exit_intent_id, "market-exit-v1"))[7:39]


def reducing_side(direction: Direction) -> WebullSide:
    if direction is Direction.LONG:
        return WebullSide.SELL
    if direction is Direction.SHORT:
        return WebullSide.BUY
    raise ValueError("Phase 3D requires a directional position")


def environment_gate(name: str, environment: Mapping[str, str] | None = None) -> bool:
    if name not in {"WEBULL_SANDBOX_EXIT_ENABLED", "WEBULL_SANDBOX_FLATTEN_ENABLED"}:
        raise ValueError("unsupported Phase 3D environment gate")
    source = os.environ if environment is None else environment
    return source.get(name, "") == "true"


def create_exit_authorization(
    registry: WebullExitRegistry,
    session_id: str,
    config: WebullExitConfig,
    capabilities: WebullExitCapabilities,
    occurred_at: datetime,
    reconciliation_id: str,
    *,
    environment_enabled: bool,
    cli_enabled: bool,
) -> ExitAuthorization:
    if not environment_enabled or not cli_enabled:
        raise ValueError("Phase 3D exit arming requires both explicit gates")
    if not capabilities.approved:
        raise ValueError("official Phase 3D capabilities have not passed 3D-5 review")
    latest = registry.latest_account_reconciliation(session_id)
    if latest is None or not latest[2]:
        raise ValueError("matched read-only reconciliation is required before exit arming")
    max_age = config.values["authorization_max_age_seconds"]
    if not isinstance(max_age, int):
        raise TypeError("validated Phase 3D authorization age must be an integer")
    if latest[1] > occurred_at or occurred_at - latest[1] > timedelta(seconds=max_age):
        raise ValueError("exit arming reconciliation is stale or future-dated")
    if reconciliation_id != latest[0]:
        raise ValueError("exit arming reconciliation identity does not match evidence")
    expires_at = occurred_at + timedelta(seconds=max_age)
    authorization_id = deterministic_id(
        "webull_exit_authorization",
        (
            session_id, config.config_hash, capabilities.capability_hash,
            reconciliation_id, occurred_at,
        ),
    )
    item = ExitAuthorization(
        authorization_id, session_id, config.config_hash,
        capabilities.capability_hash, reconciliation_id, occurred_at, expires_at,
    )
    registry.insert_exit_authorization(item)
    return item


def _positive_int(value: object, name: str, *, allow_zero: bool = False) -> int:
    if isinstance(value, bool):
        raise ValueError(f"invalid Webull {name}")
    if isinstance(value, int):
        result = value
    elif isinstance(value, str) and value.isdigit():
        result = int(value)
    else:
        raise ValueError(f"invalid Webull {name}")
    if result < 0 or (result == 0 and not allow_zero):
        raise ValueError(f"invalid Webull {name}")
    return result


def _snapshot(
    response: WebullResponse, account_id: str, expected: WebullExitOrder
) -> WebullOrderSnapshot:
    if response.payload.get("account_id") != account_id:
        raise ValueError("Webull exit response account mismatch")
    raw = response.payload.get("order")
    if not isinstance(raw, Mapping):
        raise ValueError("Webull exit response lacks an order")
    order_id = raw.get("order_id", response.payload.get("order_id"))
    if not isinstance(order_id, str) or not order_id:
        raise ValueError("Webull exit response lacks broker order identity")
    checks: dict[str, object] = {
        "client_order_id": expected.client_order_id,
        "symbol": expected.symbol,
        "side": expected.side.value,
        "order_type": expected.order_type,
        "time_in_force": expected.time_in_force,
    }
    if any(raw.get(key) != value for key, value in checks.items()):
        raise ValueError("Webull exit response differs from the persisted request")
    if expected.stop_price is not None and raw.get("stop_price") != format(
        expected.stop_price, "f"
    ):
        raise ValueError("Webull stop response differs from the persisted stop price")
    quantity = _positive_int(raw.get("quantity"), "exit quantity")
    if quantity != expected.quantity:
        raise ValueError("Webull exit response quantity mismatch")
    return WebullOrderSnapshot(
        account_id=account_id,
        broker_order_id=order_id,
        client_order_id=expected.client_order_id,
        symbol=expected.symbol,
        side=expected.side,
        quantity=quantity,
        filled_quantity=_positive_int(
            raw.get("filled_quantity"), "filled quantity", allow_zero=True
        ),
        status=WebullOrderStatus(str(raw.get("status"))),
    )


def _position_quantities(payload: Mapping[str, object]) -> dict[str, int]:
    raw = payload.get("positions")
    if not isinstance(raw, (tuple, list)):
        raise ValueError("Webull position response lacks a positions array")
    result: dict[str, int] = {}
    for item in raw:
        if not isinstance(item, Mapping):
            raise ValueError("Webull position item is invalid")
        symbol = item.get("symbol")
        quantity = item.get("quantity")
        if not isinstance(symbol, str) or symbol != symbol.upper():
            raise ValueError("Webull position symbol is invalid")
        if isinstance(quantity, bool):
            raise ValueError("Webull position quantity is invalid")
        if isinstance(quantity, int):
            parsed = quantity
        elif isinstance(quantity, str) and quantity.lstrip("-").isdigit():
            parsed = int(quantity)
        else:
            raise ValueError("Webull position quantity is invalid")
        if parsed == 0 or symbol in result:
            raise ValueError("Webull position response is contradictory")
        result[symbol] = parsed
    return result


class WebullExitLifecycleService:
    """An offline sandbox lifecycle; official SDK transport intentionally cannot satisfy it."""

    def __init__(
        self,
        session_id: str,
        account_id: str,
        transport: WebullExitTransport,
        registry: WebullExitRegistry,
        config: WebullExitConfig,
        capabilities: WebullExitCapabilities,
    ) -> None:
        if not session_id or not account_id:
            raise ValueError("Phase 3D session and account identities are required")
        self.session_id = session_id
        self._account_id = account_id
        self.transport = transport
        self.registry = registry
        self.config = config
        self.capabilities = capabilities

    def arm(
        self,
        occurred_at: datetime,
        reconciliation_id: str,
        *,
        environment_enabled: bool,
        cli_enabled: bool,
    ) -> ExitAuthorization:
        return create_exit_authorization(
            self.registry, self.session_id, self.config, self.capabilities,
            occurred_at, reconciliation_id,
            environment_enabled=environment_enabled, cli_enabled=cli_enabled,
        )

    def register_position(
        self,
        entry: WebullOrderSnapshot,
        *,
        entry_intent_id: str,
        direction: Direction,
        entry_price: Decimal,
        initial_stop_adjusted: Decimal,
        occurred_at: datetime,
        code_version: str,
    ) -> ManagedPosition:
        expected_entry_side = (
            WebullSide.BUY if direction is Direction.LONG else WebullSide.SELL_SHORT
        )
        if (
            direction not in {Direction.LONG, Direction.SHORT}
            or entry.side is not expected_entry_side
        ):
            raise ValueError("entry side does not match the managed-position direction")
        if entry.account_id != self._account_id:
            raise ValueError("entry account does not match the verified sandbox account")
        if entry.status not in {
            WebullOrderStatus.FILLED,
            WebullOrderStatus.PARTIALLY_FILLED,
            WebullOrderStatus.CANCELED,
        } or entry.filled_quantity <= 0:
            raise ValueError("confirmed entry exposure is required before position ownership")
        managed_position_id = deterministic_id(
            "webull_managed_position",
            (self.session_id, entry_intent_id, entry.client_order_id),
        )
        item = ManagedPosition(
            managed_position_id, self.session_id, entry_intent_id,
            entry.client_order_id, entry.broker_order_id, entry.symbol, direction,
            entry.filled_quantity, entry.filled_quantity, entry_price,
            initial_stop_adjusted, occurred_at, self.config.config_hash, code_version,
        )
        self.registry.insert_managed_position(item)
        if entry.status is WebullOrderStatus.PARTIALLY_FILLED:
            self._position_event(
                item, occurred_at, PositionLifecycleState.PARTIALLY_OPEN,
                entry.filled_quantity, "ENTRY_PARTIALLY_FILLED", entry,
            )
            canceled = self._cancel(
                item, entry.client_order_id, canonical_hash(entry), occurred_at,
                BrokerActionKind.CANCEL_ENTRY,
            )
            if canceled.status not in {WebullOrderStatus.CANCELED, WebullOrderStatus.FILLED}:
                self._halt(item, occurred_at, "ENTRY_CANCEL_NOT_TERMINAL")
                raise ValueError("partial entry remainder was not proven terminal")
            entry = canceled
        self.registry.insert_broker_event(self.session_id, occurred_at, entry)
        self.registry.insert_execution(self.session_id, occurred_at, entry)
        self._position_event(
            item, occurred_at, PositionLifecycleState.OPEN, entry.filled_quantity,
            "ENTRY_TERMINAL_FILL_CONFIRMED", entry,
        )
        return item

    def reconcile_position(
        self, managed_position_id: str, occurred_at: datetime, *, halt_on_mismatch: bool = True
    ) -> PositionReconciliation:
        item = self.registry.managed_position(managed_position_id)
        latest = self.registry.latest_position_event(managed_position_id)
        if latest is None:
            raise ValueError("managed position has no lifecycle evidence")
        response = self.transport.positions(self._account_id)
        self.registry.insert_envelope(
            self.session_id, "PHASE_3D_POSITIONS", occurred_at, response
        )
        if not 200 <= response.status_code < 300:
            raise ValueError("Phase 3D position reconciliation failed")
        if response.payload.get("account_id") != self._account_id:
            raise ValueError("Phase 3D position reconciliation account mismatch")
        actual = _position_quantities(response.payload)
        expected_signed = (
            latest.remaining_quantity
            if item.direction is Direction.LONG
            else -latest.remaining_quantity
        )
        expected = {} if expected_signed == 0 else {item.symbol: expected_signed}
        differences = tuple(
            ["POSITION_QUANTITY_MISMATCH"] if actual != expected else []
        )
        reconciliation_id = deterministic_id(
            "webull_position_reconciliation",
            (self.session_id, managed_position_id, occurred_at, expected, actual),
        )
        result = PositionReconciliation(
            reconciliation_id, self.session_id, managed_position_id, occurred_at,
            latest.remaining_quantity, abs(actual.get(item.symbol, 0)),
            not differences, differences,
        )
        self.registry.insert_position_reconciliation(result)
        if differences and halt_on_mismatch:
            self.registry.insert_incident(
                self.session_id, occurred_at, "PHASE_3D_POSITION_MISMATCH", differences
            )
            self._halt(item, occurred_at, differences[0])
        return result

    def protect(
        self,
        managed_position_id: str,
        adjusted_stop: Decimal,
        adjustment_factor: Decimal,
        tick_size: Decimal,
        source_candle_id: str,
        source_revision: str,
        known_at: datetime,
        occurred_at: datetime,
    ) -> WebullOrderSnapshot:
        item = self.registry.managed_position(managed_position_id)
        latest = self._require_state(item, {PositionLifecycleState.OPEN})
        if known_at > occurred_at:
            raise ValueError("future stop evidence cannot reach the broker path")
        reconciliation = self.reconcile_position(managed_position_id, occurred_at)
        if not reconciliation.matched or reconciliation.actual_quantity <= 0:
            raise ValueError("exact nonzero position reconciliation is required for protection")
        order, version = self._stop_request(
            item, latest.remaining_quantity, adjusted_stop, adjustment_factor, tick_size,
            source_candle_id, source_revision, known_at,
        )
        self.registry.insert_stop_version(version)
        self._position_event(
            item, occurred_at, PositionLifecycleState.PROTECTING,
            latest.remaining_quantity, "PROTECTIVE_STOP_PREPARED", version,
        )
        snapshot = self._write(item, order, BrokerActionKind.PLACE_STOP, occurred_at)
        if snapshot.status not in {
            WebullOrderStatus.ACKNOWLEDGED, WebullOrderStatus.PARTIALLY_FILLED,
            WebullOrderStatus.FILLED,
        }:
            self._halt(item, occurred_at, "PROTECTIVE_STOP_NOT_ACTIVE")
            raise ValueError("protective stop was not acknowledged")
        state = (
            PositionLifecycleState.STOP_FILLED
            if snapshot.status is WebullOrderStatus.FILLED
            else PositionLifecycleState.PROTECTED
        )
        remaining = latest.remaining_quantity - snapshot.filled_quantity
        self._position_event(item, occurred_at, state, remaining, "PROTECTIVE_STOP_ACK", snapshot)
        return snapshot

    def replace_stop(
        self,
        managed_position_id: str,
        adjusted_stop: Decimal,
        adjustment_factor: Decimal,
        tick_size: Decimal,
        source_candle_id: str,
        source_revision: str,
        known_at: datetime,
        occurred_at: datetime,
    ) -> WebullOrderSnapshot:
        item = self.registry.managed_position(managed_position_id)
        latest_event = self._require_state(item, {PositionLifecycleState.PROTECTED})
        prior = self.registry.latest_stop(managed_position_id)
        if prior is None:
            raise ValueError("stop replacement requires a persisted protective stop")
        if known_at <= prior.known_at or known_at > occurred_at:
            raise ValueError("stop replacement evidence must be new and causal")
        if (
            item.direction is Direction.LONG and adjusted_stop < prior.adjusted_stop
        ) or (
            item.direction is Direction.SHORT and adjusted_stop > prior.adjusted_stop
        ):
            raise ValueError("Phase 1 stop monotonicity violation")
        if adjusted_stop == prior.adjusted_stop:
            raise ValueError("unchanged stop cannot create a replacement write")
        reconciliation = self.reconcile_position(managed_position_id, occurred_at)
        if (
            not reconciliation.matched
            or reconciliation.actual_quantity != latest_event.remaining_quantity
        ):
            raise ValueError("exact position reconciliation is required for stop replacement")
        order, version = self._stop_request(
            item, latest_event.remaining_quantity, adjusted_stop, adjustment_factor,
            tick_size, source_candle_id, source_revision, known_at,
        )
        if order.client_order_id != prior.client_order_id:
            raise ValueError("protective replacement must retain the same client identity")
        self.registry.insert_stop_version(version)
        self._position_event(
            item, occurred_at, PositionLifecycleState.REPLACING_STOP,
            latest_event.remaining_quantity, "MONOTONIC_STOP_REPLACEMENT_PREPARED", version,
        )
        snapshot = self._write(
            item, order, BrokerActionKind.REPLACE_STOP, occurred_at, replace=True
        )
        if snapshot.status is not WebullOrderStatus.ACKNOWLEDGED:
            self._halt(item, occurred_at, "STOP_REPLACEMENT_NOT_ACKNOWLEDGED")
            raise ValueError("stop replacement was not acknowledged")
        self._position_event(
            item, occurred_at, PositionLifecycleState.PROTECTED,
            latest_event.remaining_quantity, "MONOTONIC_STOP_REPLACED", snapshot,
        )
        return snapshot

    def queue_exit(
        self,
        managed_position_id: str,
        reason: ExitReason,
        signal_candle_id: str,
        known_at: datetime,
        scheduled_open: datetime,
        evidence: object,
    ) -> ExitIntent:
        item = self.registry.managed_position(managed_position_id)
        latest = self._require_state(item, {PositionLifecycleState.PROTECTED})
        if reason not in {
            ExitReason.STRUCTURAL_DAMAGE, ExitReason.OPPOSING_TRAP, ExitReason.MAX_HOLD,
        }:
            raise ValueError("unsupported strategy exit reason")
        evidence_hash = canonical_hash(evidence)
        exit_intent_id = deterministic_id(
            "webull_exit_intent",
            (self.session_id, managed_position_id, reason, known_at),
        )
        intent = ExitIntent(
            exit_intent_id, self.session_id, managed_position_id, reason,
            signal_candle_id, known_at, scheduled_open, latest.remaining_quantity,
            evidence_hash,
        )
        self.registry.insert_exit_intent(intent)
        self._position_event(
            item, known_at, PositionLifecycleState.EXIT_QUEUED,
            latest.remaining_quantity, reason.value, intent,
        )
        return intent

    def release_exit(self, intent: ExitIntent, occurred_at: datetime) -> WebullOrderSnapshot | None:
        if intent.session_id != self.session_id or occurred_at < intent.scheduled_open:
            raise ValueError("queued exit is not eligible for release")
        item = self.registry.managed_position(intent.managed_position_id)
        latest = self._require_state(item, {PositionLifecycleState.EXIT_QUEUED})
        self._position_event(
            item, occurred_at, PositionLifecycleState.EXIT_RELEASING,
            latest.remaining_quantity, intent.reason.value, intent,
        )
        stop = self.registry.latest_stop(item.managed_position_id)
        if stop is None:
            self._halt(item, occurred_at, "QUEUED_EXIT_HAS_NO_PROTECTIVE_STOP")
            raise ValueError("queued exit requires known protective-stop ownership")
        stop_order = self._stop_order(item, stop.quantity, stop.raw_stop)
        detail = self.transport.order_detail(self._account_id, stop.client_order_id)
        try:
            stop_snapshot = _snapshot(detail, self._account_id, stop_order)
        except (TypeError, ValueError) as error:
            self._halt(item, occurred_at, f"STOP_RECONCILIATION_{type(error).__name__}")
            raise ValueError("protective stop could not be reconciled") from error
        self._record_fill(item, stop_snapshot, occurred_at, ExitReason.STOP_HIT)
        reconciliation = self.reconcile_position(
            item.managed_position_id, occurred_at, halt_on_mismatch=False
        )
        if reconciliation.actual_quantity == 0:
            self._position_event(
                item, occurred_at, PositionLifecycleState.FLAT, 0,
                ExitReason.STOP_HIT.value, stop_snapshot,
            )
            return None
        if reconciliation.actual_quantity > latest.remaining_quantity:
            self._halt(item, occurred_at, "EXIT_RELEASE_POSITION_EXCEEDS_OWNERSHIP")
            raise ValueError("queued exit cannot increase or adopt exposure")
        self._position_event(
            item, occurred_at, PositionLifecycleState.CANCELING_STOP,
            reconciliation.actual_quantity, "CANCEL_STOP_BEFORE_MARKET_EXIT", intent,
        )
        canceled = self._cancel(
            item, stop.client_order_id, stop.request_hash, occurred_at,
            BrokerActionKind.CANCEL_STOP, expected=stop_order,
        )
        self._record_fill(item, canceled, occurred_at, ExitReason.STOP_HIT)
        remaining_position = self._actual_position(item, occurred_at)
        if remaining_position == 0:
            self._position_event(
                item, occurred_at, PositionLifecycleState.FLAT, 0,
                ExitReason.STOP_HIT.value, canceled,
            )
            return None
        if canceled.status is not WebullOrderStatus.CANCELED:
            self._halt(item, occurred_at, "STOP_CANCEL_NOT_PROVEN")
            raise ValueError("market exit is prohibited until stop cancellation is proven")
        if remaining_position > latest.remaining_quantity:
            self._halt(item, occurred_at, "EXIT_RELEASE_QUANTITY_MISMATCH")
            raise ValueError("queued exit quantity exceeds managed exposure")
        order = WebullExitOrder(
            exit_client_id(self.session_id, intent.exit_intent_id), item.symbol,
            reducing_side(item.direction), remaining_position, "MARKET", "DAY",
        )
        self._position_event(
            item, occurred_at, PositionLifecycleState.EXIT_SUBMITTING,
            remaining_position, intent.reason.value, order,
        )
        snapshot = self._write(item, order, BrokerActionKind.PLACE_EXIT, occurred_at)
        self._record_fill(item, snapshot, occurred_at, intent.reason)
        remaining = max(0, remaining_position - snapshot.filled_quantity)
        self._position_event(
            item, occurred_at,
            PositionLifecycleState.FLAT if remaining == 0 else PositionLifecycleState.EXIT_WORKING,
            remaining, intent.reason.value, snapshot,
        )
        return snapshot

    def recover(self, occurred_at: datetime) -> tuple[str, ...]:
        recovered: list[str] = []
        for managed_id, kind_text, client_id, request_hash in self.registry.unresolved_actions(
            self.session_id
        ):
            item = self.registry.managed_position(managed_id)
            response = self.transport.order_detail(self._account_id, client_id)
            raw = response.payload.get("order")
            if response.status_code != 200 or not isinstance(raw, Mapping):
                self._halt(item, occurred_at, "UNRESOLVED_BROKER_ACTION")
                continue
            self._action(
                item, BrokerActionKind(kind_text), BrokerActionEventType.RECOVERED,
                client_id, request_hash, occurred_at,
                {"status": str(raw.get("status", "UNKNOWN"))},
            )
            recovered.append(client_id)
        return tuple(recovered)

    def observe_order(
        self,
        managed_position_id: str,
        order: WebullExitOrder,
        reason: ExitReason,
        occurred_at: datetime,
    ) -> WebullOrderSnapshot:
        """Persist one authenticated cumulative snapshot without issuing a broker write."""
        item = self.registry.managed_position(managed_position_id)
        if order.symbol != item.symbol or order.side is not reducing_side(item.direction):
            raise ValueError("observed order is not exposure-reducing for this position")
        response = self.transport.order_detail(self._account_id, order.client_order_id)
        snapshot = _snapshot(response, self._account_id, order)
        self._record_fill(item, snapshot, occurred_at, reason)
        remaining = self._actual_position(item, occurred_at)
        if snapshot.status is WebullOrderStatus.FILLED and remaining == 0:
            self._position_event(
                item, occurred_at, PositionLifecycleState.FLAT, 0, reason.value, snapshot
            )
        elif remaining > self._remaining(item):
            self._halt(item, occurred_at, "OBSERVED_POSITION_EXCEEDS_OWNERSHIP")
            raise ValueError("observed broker position exceeds managed ownership")
        return snapshot

    def drain_ready(self, occurred_at: datetime) -> bool:
        """Report drain readiness without canceling protection or flattening exposure."""
        positions = self.registry.positions(self.session_id)
        owned_clients = {position.entry_client_order_id for position in positions}
        for position in positions:
            stop = self.registry.latest_stop(position.managed_position_id)
            if stop is not None:
                owned_clients.add(stop.client_order_id)
            event = self.registry.latest_position_event(position.managed_position_id)
            if event is None:
                raise ValueError("managed position lacks lifecycle evidence during drain")
            if event.state is not PositionLifecycleState.FLAT:
                if stop is None and event.remaining_quantity > 0:
                    self._halt(position, occurred_at, "DRAINING_POSITION_UNPROTECTED")
                    raise ValueError("draining position has no owned protective stop")
                return False
        response = self.transport.open_orders(self._account_id)
        self.registry.insert_envelope(
            self.session_id, "PHASE_3D_DRAIN_OPEN_ORDERS", occurred_at, response
        )
        if response.payload.get("account_id") != self._account_id:
            raise ValueError("drain open-order account mismatch")
        raw_orders = response.payload.get("orders")
        if not isinstance(raw_orders, (tuple, list)):
            raise ValueError("drain open-order response is invalid")
        open_clients: set[str] = set()
        for raw in raw_orders:
            if not isinstance(raw, Mapping):
                raise ValueError("drain open-order item is invalid")
            client_id = raw.get("client_order_id")
            if not isinstance(client_id, str) or not client_id:
                raise ValueError("drain open-order client identity is invalid")
            open_clients.add(client_id)
        unknown = open_clients - owned_clients
        if unknown:
            for position in positions:
                self._halt(position, occurred_at, "DRAINING_UNKNOWN_OPEN_ORDER")
            raise ValueError("unknown open orders prohibit drain completion")
        return not open_clients

    def authorize_flatten(
        self,
        managed_position_id: str,
        reconciliation_id: str,
        occurred_at: datetime,
        *,
        symbol: str,
        direction: Direction,
        environment_enabled: bool,
        cli_enabled: bool,
    ) -> FlattenAuthorization:
        if not environment_enabled or not cli_enabled:
            raise ValueError("emergency flatten requires both explicit gates")
        item = self.registry.managed_position(managed_position_id)
        latest_event = self.registry.latest_position_event(managed_position_id)
        prohibited_halts = {
            "ACCOUNT_IDENTITY_MISMATCH",
            "UNKNOWN_ACCOUNT_EXPOSURE",
            "POSITION_SIGN_MISMATCH",
            "POSITION_QUANTITY_MISMATCH",
        }
        if (
            latest_event is not None
            and latest_event.state is PositionLifecycleState.HALTED
            and latest_event.reason in prohibited_halts
        ):
            raise ValueError("this halt class requires manual broker intervention")
        if item.symbol != symbol or item.direction is not direction:
            raise ValueError("emergency flatten identity does not match managed ownership")
        reconciliation = self.registry.latest_position_reconciliation(managed_position_id)
        if (
            reconciliation is None
            or reconciliation.reconciliation_id != reconciliation_id
            or not reconciliation.matched
            or reconciliation.occurred_at != occurred_at
        ):
            raise ValueError("fresh exact reconciliation is required for flatten authorization")
        flatten_auth_id = deterministic_id(
            "webull_flatten_authorization",
            (self.session_id, managed_position_id, reconciliation_id, occurred_at),
        )
        authorization = FlattenAuthorization(
            flatten_auth_id, self.session_id, managed_position_id, reconciliation_id,
            symbol, direction, occurred_at,
        )
        self.registry.insert_flatten_authorization(authorization)
        return authorization

    def flatten_position(
        self,
        authorization: FlattenAuthorization,
        occurred_at: datetime,
    ) -> WebullOrderSnapshot | None:
        if authorization.session_id != self.session_id:
            raise ValueError("flatten authorization belongs to another session")
        if self.registry.flatten_consumed(authorization.flatten_auth_id):
            raise ValueError("flatten authorization has already crossed a broker boundary")
        item = self.registry.managed_position(authorization.managed_position_id)
        latest_reconciliation = self.registry.latest_position_reconciliation(
            item.managed_position_id
        )
        if (
            latest_reconciliation is None
            or latest_reconciliation.reconciliation_id != authorization.reconciliation_id
            or not latest_reconciliation.matched
        ):
            raise ValueError("flatten authorization no longer matches exact reconciliation")
        stop = self.registry.latest_stop(item.managed_position_id)
        if stop is None:
            self._halt(item, occurred_at, "FLATTEN_HAS_NO_OWNED_STOP")
            raise ValueError("flatten cannot cancel an unknown protective stop")
        expected_stop = self._stop_order(item, stop.quantity, stop.raw_stop)
        canceled = self._cancel(
            item, stop.client_order_id, stop.request_hash, occurred_at,
            BrokerActionKind.CANCEL_STOP, expected=expected_stop,
        )
        self._record_fill(item, canceled, occurred_at, ExitReason.STOP_HIT)
        remaining = self._actual_position(item, occurred_at)
        if remaining == 0:
            self._position_event(
                item, occurred_at, PositionLifecycleState.FLAT, 0,
                ExitReason.STOP_HIT.value, canceled,
            )
            return None
        if canceled.status is not WebullOrderStatus.CANCELED:
            self._halt(item, occurred_at, "FLATTEN_STOP_CANCEL_NOT_PROVEN")
            raise ValueError("flatten placement requires a proven stop cancellation")
        order = WebullExitOrder(
            canonical_hash(
                (self.session_id, authorization.flatten_auth_id, "flatten-v1")
            )[7:39],
            item.symbol, reducing_side(item.direction), remaining, "MARKET", "DAY",
        )
        self._position_event(
            item, occurred_at, PositionLifecycleState.FLATTEN_AUTHORIZED,
            remaining, ExitReason.EMERGENCY_FLATTEN.value, authorization,
        )
        snapshot = self._write(
            item, order, BrokerActionKind.PLACE_EXIT, occurred_at,
            action_detail={"flatten_auth_id": authorization.flatten_auth_id},
        )
        self._record_fill(item, snapshot, occurred_at, ExitReason.EMERGENCY_FLATTEN)
        return snapshot

    def _stop_request(
        self,
        item: ManagedPosition,
        quantity: int,
        adjusted_stop: Decimal,
        adjustment_factor: Decimal,
        tick_size: Decimal,
        source_candle_id: str,
        source_revision: str,
        known_at: datetime,
    ) -> tuple[WebullExitOrder, ProtectiveStopVersion]:
        raw_stop = adjusted_stop / adjustment_factor
        order = self._stop_order(item, quantity, raw_stop)
        request_hash = canonical_hash(order)
        version = ProtectiveStopVersion(
            deterministic_id(
                "webull_stop_version",
                (item.managed_position_id, known_at, request_hash),
            ),
            self.session_id, item.managed_position_id, order.client_order_id, known_at,
            quantity, adjusted_stop, adjustment_factor, raw_stop, tick_size,
            source_candle_id, source_revision, request_hash,
        )
        return order, version

    def _stop_order(
        self, item: ManagedPosition, quantity: int, raw_stop: Decimal
    ) -> WebullExitOrder:
        return WebullExitOrder(
            protective_client_id(self.session_id, item.managed_position_id),
            item.symbol, reducing_side(item.direction), quantity, "STOP_LOSS", "GTC",
            raw_stop,
        )

    def _write(
        self,
        item: ManagedPosition,
        order: WebullExitOrder,
        kind: BrokerActionKind,
        occurred_at: datetime,
        *,
        replace: bool = False,
        action_detail: Mapping[str, object] | None = None,
    ) -> WebullOrderSnapshot:
        request_hash = canonical_hash(order)
        self._action(
            item, kind, BrokerActionEventType.PREPARED,
            order.client_order_id, request_hash, occurred_at, action_detail,
        )
        self._action(
            item, kind, BrokerActionEventType.CALL_STARTED,
            order.client_order_id, request_hash, occurred_at, action_detail,
        )
        try:
            response = (
                self.transport.replace_exit(self._account_id, order)
                if replace else self.transport.place_exit(self._account_id, order)
            )
        except Exception as error:
            return self._resolve_once(item, order, kind, occurred_at, error)
        detail = self.transport.order_detail(self._account_id, order.client_order_id)
        try:
            snapshot = _snapshot(detail, self._account_id, order)
        except (TypeError, ValueError) as error:
            self._ambiguous(
                item, kind, order.client_order_id, request_hash, occurred_at, error
            )
        if not 200 <= response.status_code < 300:
            self._action(
                item, kind, BrokerActionEventType.REJECTED,
                order.client_order_id, request_hash, occurred_at,
                {"status_code": response.status_code},
            )
            return snapshot
        self.registry.insert_broker_event(self.session_id, occurred_at, snapshot)
        self._action(
            item, kind, BrokerActionEventType.ACKNOWLEDGED,
            order.client_order_id, request_hash, occurred_at,
            {"broker_order_id": snapshot.broker_order_id, "status": snapshot.status.value},
        )
        return snapshot

    def _cancel(
        self,
        item: ManagedPosition,
        client_order_id: str,
        request_hash: str,
        occurred_at: datetime,
        kind: BrokerActionKind,
        expected: WebullExitOrder | None = None,
    ) -> WebullOrderSnapshot:
        self._action(
            item, kind, BrokerActionEventType.PREPARED,
            client_order_id, request_hash, occurred_at,
        )
        self._action(
            item, kind, BrokerActionEventType.CALL_STARTED,
            client_order_id, request_hash, occurred_at,
        )
        try:
            self.transport.cancel_exit(self._account_id, client_order_id)
        except Exception as error:
            detail = self.transport.order_detail(self._account_id, client_order_id)
            if expected is None:
                snapshot = self._entry_snapshot(detail, item)
            else:
                snapshot = _snapshot(detail, self._account_id, expected)
            if snapshot.status not in {WebullOrderStatus.CANCELED, WebullOrderStatus.FILLED}:
                self._ambiguous(item, kind, client_order_id, request_hash, occurred_at, error)
            else:
                self._action(
                    item, kind, BrokerActionEventType.RECOVERED,
                    client_order_id, request_hash, occurred_at,
                    {"status": snapshot.status.value},
                )
            return snapshot
        detail = self.transport.order_detail(self._account_id, client_order_id)
        snapshot = (
            self._entry_snapshot(detail, item)
            if expected is None else _snapshot(detail, self._account_id, expected)
        )
        if snapshot.status not in {WebullOrderStatus.CANCELED, WebullOrderStatus.FILLED}:
            self._ambiguous(
                item, kind, client_order_id, request_hash, occurred_at,
                ValueError("cancel not terminal"),
            )
        self.registry.insert_broker_event(self.session_id, occurred_at, snapshot)
        self._action(
            item, kind, BrokerActionEventType.ACKNOWLEDGED,
            client_order_id, request_hash, occurred_at,
            {"status": snapshot.status.value},
        )
        return snapshot

    def _entry_snapshot(
        self, response: WebullResponse, item: ManagedPosition
    ) -> WebullOrderSnapshot:
        raw = response.payload.get("order")
        if response.payload.get("account_id") != self._account_id or not isinstance(raw, Mapping):
            raise ValueError("entry cancel detail is invalid")
        return WebullOrderSnapshot(
            self._account_id, str(raw.get("order_id")), item.entry_client_order_id,
            item.symbol, WebullSide(str(raw.get("side"))),
            _positive_int(raw.get("quantity"), "entry quantity"),
            _positive_int(raw.get("filled_quantity"), "entry fill", allow_zero=True),
            WebullOrderStatus(str(raw.get("status"))),
        )

    def _resolve_once(
        self,
        item: ManagedPosition,
        order: WebullExitOrder,
        kind: BrokerActionKind,
        occurred_at: datetime,
        error: Exception,
    ) -> WebullOrderSnapshot:
        detail = self.transport.order_detail(self._account_id, order.client_order_id)
        try:
            snapshot = _snapshot(detail, self._account_id, order)
        except (TypeError, ValueError) as query_error:
            self._ambiguous(item, kind, order.client_order_id, canonical_hash(order),
                            occurred_at, query_error)
        self.registry.insert_broker_event(self.session_id, occurred_at, snapshot)
        self._action(
            item, kind, BrokerActionEventType.RECOVERED,
            order.client_order_id, canonical_hash(order), occurred_at,
            {"error_type": type(error).__name__, "status": snapshot.status.value},
        )
        return snapshot

    def _ambiguous(
        self,
        item: ManagedPosition,
        kind: BrokerActionKind,
        client_order_id: str,
        request_hash: str,
        occurred_at: datetime,
        error: Exception,
    ) -> NoReturn:
        self._action(
            item, kind, BrokerActionEventType.AMBIGUOUS,
            client_order_id, request_hash, occurred_at,
            {"error_type": type(error).__name__},
        )
        self._position_event(
            item, occurred_at, PositionLifecycleState.AMBIGUOUS,
            self._remaining(item), "BROKER_ACTION_AMBIGUOUS", {"kind": kind.value},
        )
        self._halt(item, occurred_at, "BROKER_ACTION_AMBIGUOUS")
        raise ValueError("Phase 3D broker action is ambiguous; automatic retry is prohibited")

    def _action(
        self,
        item: ManagedPosition,
        kind: BrokerActionKind,
        event_type: BrokerActionEventType,
        client_order_id: str,
        request_hash: str,
        occurred_at: datetime,
        detail: Mapping[str, object] | None = None,
    ) -> None:
        body = {} if detail is None else dict(detail)
        action_id = deterministic_id(
            "webull_broker_action",
            (
                self.session_id, kind, client_order_id, request_hash,
                event_type, occurred_at, body,
            ),
        )
        self.registry.insert_action_event(BrokerActionEvent(
            action_id, self.session_id, item.managed_position_id, kind, event_type,
            client_order_id, request_hash, occurred_at, body,
        ))

    def _position_event(
        self,
        item: ManagedPosition,
        occurred_at: datetime,
        state: PositionLifecycleState,
        remaining: int,
        reason: str,
        evidence: object,
    ) -> None:
        evidence_hash = canonical_hash(evidence)
        event_id = deterministic_id(
            "webull_position_event",
            (item.managed_position_id, occurred_at, state, remaining, reason, evidence_hash),
        )
        self.registry.insert_position_event(PositionEvent(
            event_id, item.managed_position_id, self.session_id, occurred_at,
            state, remaining, reason, evidence_hash,
        ))

    def _halt(self, item: ManagedPosition, occurred_at: datetime, reason: str) -> None:
        self._position_event(
            item, occurred_at, PositionLifecycleState.HALTED,
            self._remaining(item), reason, {"reason": reason},
        )

    def _remaining(self, item: ManagedPosition) -> int:
        latest = self.registry.latest_position_event(item.managed_position_id)
        return item.remaining_quantity if latest is None else latest.remaining_quantity

    def _require_state(
        self, item: ManagedPosition, states: set[PositionLifecycleState]
    ) -> PositionEvent:
        latest = self.registry.latest_position_event(item.managed_position_id)
        if latest is None or latest.state not in states:
            allowed = ",".join(sorted(state.value for state in states))
            raise ValueError(f"managed position is not in an allowed state: {allowed}")
        return latest

    def _record_fill(
        self,
        item: ManagedPosition,
        snapshot: WebullOrderSnapshot,
        occurred_at: datetime,
        reason: ExitReason,
    ) -> None:
        self.registry.insert_broker_event(self.session_id, occurred_at, snapshot)
        prior_quantity = self.registry.latest_execution_quantity(
            self.session_id, snapshot.client_order_id
        )
        self.registry.insert_execution(self.session_id, occurred_at, snapshot)
        fill_delta = max(0, snapshot.filled_quantity - prior_quantity)
        if fill_delta > 0:
            remaining = max(0, self._remaining(item) - fill_delta)
            state = (
                PositionLifecycleState.STOP_FILLED
                if remaining == 0 and reason is ExitReason.STOP_HIT
                else PositionLifecycleState.STOP_PARTIALLY_FILLED
                if reason is ExitReason.STOP_HIT
                else PositionLifecycleState.FLAT
                if remaining == 0
                else PositionLifecycleState.EXIT_WORKING
            )
            self._position_event(item, occurred_at, state, remaining, reason.value, snapshot)

    def _actual_position(self, item: ManagedPosition, occurred_at: datetime) -> int:
        response = self.transport.positions(self._account_id)
        self.registry.insert_envelope(
            self.session_id, "PHASE_3D_POSITIONS", occurred_at, response
        )
        actual = _position_quantities(response.payload)
        unknown = set(actual) - {item.symbol}
        if unknown:
            self._halt(item, occurred_at, "UNKNOWN_ACCOUNT_EXPOSURE")
            raise ValueError("unknown account exposure cannot be adopted")
        signed = actual.get(item.symbol, 0)
        if (item.direction is Direction.LONG and signed < 0) or (
            item.direction is Direction.SHORT and signed > 0
        ):
            self._halt(item, occurred_at, "POSITION_SIGN_MISMATCH")
            raise ValueError("managed position sign mismatch")
        return abs(signed)
