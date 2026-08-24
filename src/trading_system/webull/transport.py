"""Official-SDK and deterministic fake Webull transports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from trading_system.webull.config import WebullConfig
from trading_system.webull.contracts import WebullCredentials, WebullResponse, WebullStockOrder


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


class OfficialSdkWebullTransport:
    def __init__(self, config: WebullConfig, credentials: WebullCredentials) -> None:
        from webull.core.client import ApiClient  # type: ignore[import-untyped]
        from webull.trade.trade_client import TradeClient  # type: ignore[import-untyped]

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
        # TradeClient otherwise creates webull_trade_sdk.log and a console logger by default.
        client._stream_logger_set = True
        client._file_logger_set = True
        self._trade = TradeClient(client)

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


class FakeWebullTransport:
    def __init__(self, account_id: str, *, reject_preview: bool = False) -> None:
        self.account_id = account_id
        self.reject_preview = reject_preview
        self.preview_calls = 0
        self.place_calls = 0
        self.orders: dict[str, dict[str, object]] = {}

    def account_list(self) -> WebullResponse:
        return WebullResponse(200, {"accounts": ({
            "account_id": self.account_id, "account_number": self.account_id,
            "account_class": "INDIVIDUAL_MARGIN",
        },)})

    def balance(self, account_id: str) -> WebullResponse:
        return WebullResponse(200, {"account_id": account_id, "buying_power": "1000000"})

    def positions(self, account_id: str) -> WebullResponse:
        return WebullResponse(200, {"account_id": account_id, "positions": ()})

    def open_orders(self, account_id: str) -> WebullResponse:
        return WebullResponse(200, {"account_id": account_id,
                                    "orders": tuple(self.orders.values())})

    def order_detail(self, account_id: str, client_order_id: str) -> WebullResponse:
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
        item: dict[str, object] = {
            "account_id": account_id,
            "client_order_id": order.client_order_id,
            "status": "SUBMITTED",
            "order": order.sdk_payload(),
        }
        self.orders.setdefault(order.client_order_id, item)
        return WebullResponse(200, item)
