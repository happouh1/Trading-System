"""Official-SDK and deterministic fake Webull transports."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any, Protocol

from trading_system.webull.case1_transport import case1_client_order_id, validate_case1_order
from trading_system.webull.config import WebullConfig
from trading_system.webull.contracts import WebullCredentials, WebullResponse, WebullStockOrder
from trading_system.webull.exit_contracts import WebullExitOrder


class WebullTransport(Protocol):
    def account_list(self) -> WebullResponse: ...
    def balance(self, account_id: str) -> WebullResponse: ...
    def positions(self, account_id: str) -> WebullResponse: ...
    def open_orders(self, account_id: str) -> WebullResponse: ...
    def order_detail(self, account_id: str, client_order_id: str) -> WebullResponse: ...
    def preview(self, account_id: str, order: WebullStockOrder) -> WebullResponse: ...
    def place(self, account_id: str, order: WebullStockOrder) -> WebullResponse: ...


def _normalized(response: Any) -> WebullResponse:
    status_code = getattr(response, "status_code", None)
    if not isinstance(status_code, int):
        raise ValueError("Webull SDK response lacks an HTTP status code")
    raw = response.json()
    if isinstance(raw, Mapping):
        payload = {str(key): item for key, item in raw.items()}
    elif isinstance(raw, list):
        payload = {"items": tuple(raw)}
    else:
        raise ValueError("Webull SDK response JSON must be an object or array")
    return WebullResponse(status_code, payload)


def _integer_config(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Webull {name} must be an integer")
    return value


def _trade_client(config: WebullConfig, credentials: WebullCredentials) -> Any:
    from webull.core.client import ApiClient  # type: ignore[import-untyped]
    from webull.trade.trade_client import TradeClient  # type: ignore[import-untyped]

    values = config.values
    client = ApiClient(
        credentials.app_key,
        credentials.app_secret,
        str(values["region_id"]),
        connect_timeout=_integer_config(values["connect_timeout_seconds"], "connect timeout"),
        timeout=_integer_config(values["request_timeout_seconds"], "request timeout"),
        auto_retry=False,
    )
    client.add_endpoint(str(values["region_id"]), str(values["api_endpoint"]))
    client._stream_logger_set = True
    client._file_logger_set = True
    return TradeClient(client)


class OfficialSdkWebullTransport:
    def __init__(self, config: WebullConfig, credentials: WebullCredentials) -> None:
        # TradeClient otherwise creates webull_trade_sdk.log and a console logger by default.
        self._trade = _trade_client(config, credentials)

    def account_list(self) -> WebullResponse:
        return _normalized(self._trade.account_v2.get_account_list())

    def balance(self, account_id: str) -> WebullResponse:
        return _normalized(self._trade.account_v2.get_account_balance(account_id))

    def positions(self, account_id: str) -> WebullResponse:
        return _normalized(self._trade.account_v2.get_account_position(account_id))

    def open_orders(self, account_id: str) -> WebullResponse:
        return _normalized(self._trade.order_v2.get_order_open(account_id))

    def order_detail(self, account_id: str, client_order_id: str) -> WebullResponse:
        return _normalized(self._trade.order_v2.get_order_detail(account_id, client_order_id))

    def preview(self, account_id: str, order: WebullStockOrder) -> WebullResponse:
        return _normalized(self._trade.order_v2.preview_order(account_id, [order.sdk_payload()]))

    def place(self, account_id: str, order: WebullStockOrder) -> WebullResponse:
        return _normalized(self._trade.order_v2.place_order(account_id, [order.sdk_payload()]))


class OfficialSdkWebullCase1Transport:
    """Exact Case-1 surface pinned to the SDK's non-deprecated V3 order API."""

    def __init__(
        self, session_id: str, config: WebullConfig, credentials: WebullCredentials
    ) -> None:
        self._session_id = session_id
        self._trade = _trade_client(config, credentials)

    def account_list(self) -> WebullResponse:
        return _normalized(self._trade.account_v2.get_account_list())

    def balance(self, account_id: str) -> WebullResponse:
        return _normalized(self._trade.account_v2.get_account_balance(account_id))

    def positions(self, account_id: str) -> WebullResponse:
        return _normalized(self._trade.account_v2.get_account_position(account_id))

    def open_orders(self, account_id: str) -> WebullResponse:
        return _normalized(self._trade.order_v3.get_order_open(account_id))

    def order_detail(self, account_id: str, client_order_id_value: str) -> WebullResponse:
        if client_order_id_value != case1_client_order_id(self._session_id):
            raise ValueError("Case-1 detail query requires the exact approved client ID")
        return _normalized(
            self._trade.order_v3.get_order_detail(account_id, client_order_id_value)
        )

    def preview_exact_stop(
        self, account_id: str, order: WebullExitOrder
    ) -> WebullResponse:
        validate_case1_order(self._session_id, order)
        return _normalized(
            self._trade.order_v3.preview_order(account_id, [order.sdk_payload()])
        )

    def place_exact_stop(
        self, account_id: str, order: WebullExitOrder
    ) -> WebullResponse:
        validate_case1_order(self._session_id, order)
        return _normalized(
            self._trade.order_v3.place_order(account_id, [order.sdk_payload()])
        )

    def cancel_exact_stop(
        self, account_id: str, order: WebullExitOrder
    ) -> WebullResponse:
        validate_case1_order(self._session_id, order)
        return _normalized(
            self._trade.order_v3.cancel_order(account_id, order.client_order_id)
        )


class OfficialSdkWebullCase2Transport:
    """Exact Case-2 replacement surface pinned to the SDK V3 order API."""

    def __init__(
        self, session_id: str, config: WebullConfig, credentials: WebullCredentials
    ) -> None:
        self._session_id = session_id
        self._trade = _trade_client(config, credentials)

    def account_list(self) -> WebullResponse:
        return _normalized(self._trade.account_v2.get_account_list())

    def balance(self, account_id: str) -> WebullResponse:
        return _normalized(self._trade.account_v2.get_account_balance(account_id))

    def positions(self, account_id: str) -> WebullResponse:
        return _normalized(self._trade.account_v2.get_account_position(account_id))

    def open_orders(self, account_id: str) -> WebullResponse:
        return _normalized(self._trade.order_v3.get_order_open(account_id))

    def order_detail(self, account_id: str, client_order_id_value: str) -> WebullResponse:
        from trading_system.webull.case2 import exact_case2_order

        expected = exact_case2_order(self._session_id, Decimal("1.00"))
        if client_order_id_value != expected.client_order_id:
            raise ValueError("Case-2 detail query requires the exact approved client ID")
        return _normalized(
            self._trade.order_v3.get_order_detail(account_id, client_order_id_value)
        )

    def preview_initial_stop(
        self, account_id: str, order: WebullExitOrder
    ) -> WebullResponse:
        from trading_system.webull.case2 import INITIAL_STOP, exact_case2_order

        if order != exact_case2_order(self._session_id, INITIAL_STOP):
            raise ValueError("Case-2 seed requires the exact approved initial stop")
        return _normalized(
            self._trade.order_v3.preview_order(account_id, [order.sdk_payload()])
        )

    def place_initial_stop(
        self, account_id: str, order: WebullExitOrder
    ) -> WebullResponse:
        from trading_system.webull.case2 import INITIAL_STOP, exact_case2_order

        if order != exact_case2_order(self._session_id, INITIAL_STOP):
            raise ValueError("Case-2 seed requires the exact approved initial stop")
        return _normalized(
            self._trade.order_v3.place_order(account_id, [order.sdk_payload()])
        )

    def replace_exact_stop(
        self, account_id: str, order: WebullExitOrder
    ) -> WebullResponse:
        from trading_system.webull.case2 import (
            exact_case2_order,
            validate_case2_replacement,
        )

        before = exact_case2_order(self._session_id, Decimal("1.00"))
        validate_case2_replacement(self._session_id, before, order)
        return _normalized(
            self._trade.order_v3.replace_order(account_id, [order.sdk_payload()])
        )

class OfficialSdkWebullMarketDataSource:
    """Read-only SDK client with no trade client or order methods."""

    def __init__(self, config: WebullConfig, credentials: WebullCredentials) -> None:
        from webull.core.client import ApiClient
        from webull.data.data_client import DataClient  # type: ignore[import-untyped]

        values = config.values
        client = ApiClient(
            credentials.app_key, credentials.app_secret, str(values["region_id"]),
            connect_timeout=_integer_config(
                values["connect_timeout_seconds"], "connect timeout"
            ),
            timeout=_integer_config(values["request_timeout_seconds"], "request timeout"),
            auto_retry=False,
        )
        client.add_endpoint(str(values["region_id"]), str(values["api_endpoint"]))
        client._stream_logger_set = True
        client._file_logger_set = True
        self._data = DataClient(client)

    def market_snapshot(self, symbols: tuple[str, ...]) -> WebullResponse:
        return _normalized(
            self._data.market_data.get_snapshot(
                ",".join(symbols), "US_STOCK", extend_hour_required=False,
                overnight_required=False,
            )
        )

    def historical_bars(
        self, symbol: str, timespan: str, count: int
    ) -> WebullResponse:
        return _normalized(
            self._data.market_data.get_history_bar(
                symbol, "US_STOCK", timespan, count=str(count),
                real_time_required=False, trading_sessions="RTH",
            )
        )


class FakeWebullTransport:
    def __init__(
        self,
        account_id: str,
        *,
        reject_preview: bool = False,
        reject_place: bool = False,
        ambiguous_place: bool = False,
        accept_before_ambiguity: bool = False,
        ambiguous_exit_action: str | None = None,
        accept_exit_before_ambiguity: bool = False,
    ) -> None:
        self.account_id = account_id
        self.reject_preview = reject_preview
        self.reject_place = reject_place
        self.ambiguous_place = ambiguous_place
        self.accept_before_ambiguity = accept_before_ambiguity
        self.ambiguous_exit_action = ambiguous_exit_action
        self.accept_exit_before_ambiguity = accept_exit_before_ambiguity
        self.preview_calls = 0
        self.place_calls = 0
        self.exit_place_calls = 0
        self.exit_replace_calls = 0
        self.exit_cancel_calls = 0
        self.order_detail_calls = 0
        self.account_list_calls = 0
        self.orders: dict[str, dict[str, object]] = {}
        self.position_items: tuple[dict[str, object], ...] = ()
        self.market_responses: dict[str, WebullResponse] = {}

    def account_list(self) -> WebullResponse:
        self.account_list_calls += 1
        return WebullResponse(200, {"accounts": ({
            "account_id": self.account_id, "account_number": self.account_id,
            "account_class": "INDIVIDUAL_MARGIN",
        },)})

    def balance(self, account_id: str) -> WebullResponse:
        return WebullResponse(200, {"account_id": account_id, "buying_power": "1000000"})

    def positions(self, account_id: str) -> WebullResponse:
        return WebullResponse(
            200, {"account_id": account_id, "positions": self.position_items}
        )

    def open_orders(self, account_id: str) -> WebullResponse:
        open_items = tuple(
            item
            for item in self.orders.values()
            if item.get("status") in {"ACKNOWLEDGED", "PARTIALLY_FILLED"}
        )
        return WebullResponse(
            200, {"account_id": account_id, "orders": open_items}
        )

    def order_detail(self, account_id: str, client_order_id: str) -> WebullResponse:
        self.order_detail_calls += 1
        item = self.orders.get(client_order_id)
        return WebullResponse(404 if item is None else 200,
                              {"account_id": account_id, "order": item})

    def preview(self, account_id: str, order: WebullStockOrder) -> WebullResponse:
        self.preview_calls += 1
        return WebullResponse(422 if self.reject_preview else 200,
                              {"account_id": account_id, "accepted": not self.reject_preview,
                               "order": order.sdk_payload()})

    def place(self, account_id: str, order: WebullStockOrder) -> WebullResponse:
        self.place_calls += 1
        broker_order_id = f"sandbox-{order.client_order_id[:16]}"
        item = {
            **order.sdk_payload(),
            "account_id": account_id,
            "order_id": broker_order_id,
            "status": "REJECTED" if self.reject_place else "ACKNOWLEDGED",
            "filled_quantity": "0",
        }
        if not self.ambiguous_place or self.accept_before_ambiguity:
            self.orders[order.client_order_id] = item
        if self.ambiguous_place:
            raise TimeoutError("deterministic ambiguous Webull placement")
        return WebullResponse(
            422 if self.reject_place else 200,
            {
                "account_id": account_id,
                "accepted": not self.reject_place,
                "order_id": broker_order_id,
                "order": item,
            },
        )

    def set_order_state(
        self, client_order_id: str, status: str, filled_quantity: int
    ) -> None:
        item = self.orders[client_order_id]
        item["status"] = status
        item["filled_quantity"] = str(filled_quantity)

    def set_position(self, symbol: str, signed_quantity: int) -> None:
        self.position_items = () if signed_quantity == 0 else ({
            "symbol": symbol,
            "quantity": str(signed_quantity),
        },)

    def place_exit(self, account_id: str, order: WebullExitOrder) -> WebullResponse:
        self.exit_place_calls += 1
        broker_order_id = f"sandbox-exit-{order.client_order_id[:11]}"
        item = {
            **order.sdk_payload(),
            "account_id": account_id,
            "order_id": broker_order_id,
            "status": "ACKNOWLEDGED",
            "filled_quantity": "0",
        }
        if (
            self.ambiguous_exit_action != "place"
            or self.accept_exit_before_ambiguity
        ):
            self.orders[order.client_order_id] = item
        if self.ambiguous_exit_action == "place":
            raise TimeoutError("deterministic ambiguous Webull exit placement")
        return WebullResponse(200, {
            "account_id": account_id,
            "accepted": True,
            "order_id": broker_order_id,
            "order": item,
        })

    def replace_exit(self, account_id: str, order: WebullExitOrder) -> WebullResponse:
        self.exit_replace_calls += 1
        current = self.orders.get(order.client_order_id)
        if current is None:
            return WebullResponse(404, {"account_id": account_id, "order": None})
        replacement = {
            **order.sdk_payload(),
            "account_id": account_id,
            "order_id": current["order_id"],
            "status": "ACKNOWLEDGED",
            "filled_quantity": current["filled_quantity"],
        }
        if (
            self.ambiguous_exit_action != "replace"
            or self.accept_exit_before_ambiguity
        ):
            self.orders[order.client_order_id] = replacement
        if self.ambiguous_exit_action == "replace":
            raise TimeoutError("deterministic ambiguous Webull stop replacement")
        return WebullResponse(200, {
            "account_id": account_id,
            "accepted": True,
            "order_id": replacement["order_id"],
            "order": replacement,
        })

    def cancel_exit(self, account_id: str, client_order_id: str) -> WebullResponse:
        self.exit_cancel_calls += 1
        current = self.orders.get(client_order_id)
        if current is None:
            return WebullResponse(404, {"account_id": account_id, "order": None})
        canceled = dict(current)
        if canceled["status"] not in {"FILLED", "CANCELED"}:
            canceled["status"] = "CANCELED"
        if (
            self.ambiguous_exit_action != "cancel"
            or self.accept_exit_before_ambiguity
        ):
            self.orders[client_order_id] = canceled
        if self.ambiguous_exit_action == "cancel":
            raise TimeoutError("deterministic ambiguous Webull cancellation")
        return WebullResponse(200, {
            "account_id": account_id,
            "accepted": True,
            "order_id": canceled["order_id"],
            "order": canceled,
        })

    def market_snapshot(self, symbols: tuple[str, ...]) -> WebullResponse:
        return self.market_responses.get(
            "snapshot", WebullResponse(200, {"symbols": symbols})
        )

    def historical_bars(
        self, symbol: str, timespan: str, count: int
    ) -> WebullResponse:
        return self.market_responses.get(
            "historical",
            WebullResponse(200, {"symbol": symbol, "timespan": timespan, "count": count}),
        )
