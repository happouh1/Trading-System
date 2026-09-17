"""Strict offline, normalized broker captures; importing is not authentication."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from trading_system.serialization import canonical_hash, canonical_json, deterministic_id

VERSION = "WEBULL_TRADE_EVIDENCE.1.0"
MAX_BYTES = 5 * 1024 * 1024


def timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be an explicit UTC string")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() != UTC.utcoffset(result):
        raise ValueError("timestamp must be UTC")
    return result


def utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("timestamp must be UTC")
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _text(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 200 or value.strip() != value:
        raise ValueError("nonempty bounded text required")
    if any(ord(char) < 32 for char in value):
        raise ValueError("control characters are forbidden")
    return value


def _hash(value: object) -> str:
    result = _text(value)
    if re.fullmatch(r"sha256:[0-9a-f]{64}", result) is None:
        raise ValueError("SHA-256 reference required")
    return result


def _integer(value: object, minimum: int | None = None) -> int:
    if type(value) is not int or (minimum is not None and value < minimum):
        raise ValueError("invalid integer quantity")
    return value


def _money(value: object, *, positive: bool) -> Decimal:
    # Decimal strings prevent a JSON binary float from changing source money values.
    raw = _text(value)
    if re.fullmatch(r"[0-9]{1,18}(\.[0-9]{1,8})?", raw) is None:
        raise ValueError("money requires a nonnegative fixed-point decimal string")
    try:
        result = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError("invalid money") from exc
    if not result.is_finite() or (positive and result <= 0):
        raise ValueError("invalid money")
    return result


def _object(value: object, fields: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != set(fields.split()):
        raise ValueError("evidence fields do not match the versioned contract")
    return {str(key): item for key, item in value.items()}


def _records(value: object) -> list[object]:
    if not isinstance(value, list) or not 1 <= len(value) <= 1000:
        raise ValueError("evidence arrays require 1 to 1000 records")
    return list(value)


def _unique(values: list[str]) -> None:
    if len(values) != len(set(values)):
        raise ValueError("duplicate evidence identity")


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    _unique([key for key, _ in pairs])
    return dict(pairs)


def _wire(value: object) -> object:
    if isinstance(value, datetime):
        return utc_text(value)
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return {str(key): _wire(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_wire(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class EvidenceOrder:
    broker_order_id: str
    client_order_id: str
    account_id_hash: str
    symbol: str
    role: str
    side: str
    quantity: int
    filled_quantity: int
    status: str
    known_at: datetime


@dataclass(frozen=True, slots=True)
class EvidenceFill:
    execution_id: str
    broker_order_id: str
    account_id_hash: str
    quantity: int
    price: Decimal
    fee: Decimal
    currency: str
    executed_at: datetime
    known_at: datetime


@dataclass(frozen=True, slots=True)
class EvidencePosition:
    record_id: str
    account_id_hash: str
    symbol: str
    role: str
    signed_quantity: int
    observed_at: datetime
    known_at: datetime


@dataclass(frozen=True, slots=True)
class TradeEvidenceCapture:
    capture_id: str
    candidate_id: str
    account_id_hash: str
    source_sha256: str
    captured_at: datetime
    orders: tuple[EvidenceOrder, ...]
    fills: tuple[EvidenceFill, ...]
    positions: tuple[EvidencePosition, ...]
    schema_version: str = VERSION
    environment: str = "SANDBOX"

    @property
    def payload_json(self) -> str:
        return canonical_json(_wire(asdict(self)))

    @property
    def payload_hash(self) -> str:
        return canonical_hash(json.loads(self.payload_json))

    @property
    def import_id(self) -> str:
        return deterministic_id("webull_trade_import", (self.account_id_hash, self.capture_id))


def parse_capture(text: str) -> TradeEvidenceCapture:
    """Validate our normalized schema, without guessing vendor field aliases."""
    raw: object = json.loads(text, object_pairs_hook=_pairs)
    root = _object(raw, "capture_id candidate_id account_id_hash source_sha256 captured_at "
                   "orders fills positions schema_version environment")
    if root["schema_version"] != VERSION or root["environment"] != "SANDBOX":
        raise ValueError("only versioned SANDBOX evidence is accepted")
    account = _hash(root["account_id_hash"])
    captured_at = timestamp(root["captured_at"])
    orders: list[EvidenceOrder] = []
    for value in _records(root["orders"]):
        row = _object(value, "broker_order_id client_order_id account_id_hash symbol role side "
                      "quantity filled_quantity status known_at")
        order = EvidenceOrder(
            _text(row["broker_order_id"]), _text(row["client_order_id"]),
            _hash(row["account_id_hash"]), _text(row["symbol"]), _text(row["role"]),
            _text(row["side"]), _integer(row["quantity"], 1),
            _integer(row["filled_quantity"], 0), _text(row["status"]), timestamp(row["known_at"]),
        )
        if (
            order.account_id_hash != account or order.known_at > captured_at
            or order.symbol != order.symbol.upper() or order.role not in {"ENTRY", "EXIT"}
            or order.side not in {"BUY", "SELL"} or order.status not in {"FILLED", "CANCELLED"}
            or order.filled_quantity > order.quantity
            or (order.status == "FILLED" and order.filled_quantity != order.quantity)
        ):
            raise ValueError("invalid terminal order evidence")
        orders.append(order)
    _unique([item.broker_order_id for item in orders])
    _unique([item.client_order_id for item in orders])
    if sum(item.role == "ENTRY" for item in orders) != 1:
        raise ValueError("capture requires exactly one entry order")
    by_order = {item.broker_order_id: item for item in orders}
    fills: list[EvidenceFill] = []
    for value in _records(root["fills"]):
        row = _object(value, "execution_id broker_order_id account_id_hash quantity price fee "
                      "currency executed_at known_at")
        fill = EvidenceFill(
            _text(row["execution_id"]), _text(row["broker_order_id"]),
            _hash(row["account_id_hash"]), _integer(row["quantity"], 1),
            _money(row["price"], positive=True), _money(row["fee"], positive=False),
            _text(row["currency"]), timestamp(row["executed_at"]), timestamp(row["known_at"]),
        )
        if (
            fill.account_id_hash != account or fill.currency != "USD"
            or not fill.executed_at <= fill.known_at <= captured_at
            or fill.broker_order_id not in by_order
            or fill.known_at > by_order[fill.broker_order_id].known_at
        ):
            raise ValueError("invalid incremental fill evidence")
        fills.append(fill)
    _unique([item.execution_id for item in fills])
    positions: list[EvidencePosition] = []
    for value in _records(root["positions"]):
        row = _object(value, "record_id account_id_hash symbol role signed_quantity "
                      "observed_at known_at")
        position = EvidencePosition(
            _text(row["record_id"]), _hash(row["account_id_hash"]), _text(row["symbol"]),
            _text(row["role"]), _integer(row["signed_quantity"]),
            timestamp(row["observed_at"]), timestamp(row["known_at"]),
        )
        if (
            position.account_id_hash != account
            or not position.observed_at <= position.known_at <= captured_at
            or position.symbol != position.symbol.upper()
        ):
            raise ValueError("invalid position evidence")
        positions.append(position)
    _unique([item.record_id for item in positions])
    if sorted(item.role for item in positions) != ["AFTER", "BEFORE"]:
        raise ValueError("capture requires BEFORE and AFTER positions")
    return TradeEvidenceCapture(
        _text(root["capture_id"]), _text(root["candidate_id"]), account,
        _hash(root["source_sha256"]), captured_at,
        tuple(sorted(orders, key=lambda item: item.broker_order_id)),
        tuple(sorted(fills, key=lambda item: item.execution_id)),
        tuple(sorted(positions, key=lambda item: item.role)),
    )


def read_bounded(path: str | Path) -> bytes:
    with Path(path).open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if not data or len(data) > MAX_BYTES:
        raise ValueError("evidence files must contain 1 byte to 5 MiB")
    return data


def load_capture(evidence: str | Path, source_document: str | Path) -> TradeEvidenceCapture:
    capture = parse_capture(read_bounded(evidence).decode("utf-8-sig"))
    digest = "sha256:" + hashlib.sha256(read_bounded(source_document)).hexdigest()
    if digest != capture.source_sha256:
        raise ValueError("source document SHA-256 mismatch")
    return capture
