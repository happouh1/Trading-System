"""Strict CSV and Parquet OHLCV ingestion."""

from __future__ import annotations

import csv
import importlib
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from trading_system.domain import Candle, Timeframe
from trading_system.market_data.calendar import SessionCalendar

REQUIRED_COLUMNS = (
    "symbol",
    "timeframe",
    "open_time",
    "close_time",
    "session_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "raw_open",
    "raw_high",
    "raw_low",
    "raw_close",
    "raw_volume",
    "adjustment_factor",
    "is_complete",
    "source",
    "source_revision",
)


class IngestionError(ValueError):
    """Source data is missing, ambiguous, or violates its declared contract."""


def _datetime(value: object, field: str) -> datetime:
    text = str(value)
    try:
        result = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IngestionError(f"invalid {field}: {text!r}") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise IngestionError(f"{field} must include a UTC offset")
    return result.astimezone(UTC)


def _decimal(value: object, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise IngestionError(f"invalid {field}: {value!r}") from exc
    if not result.is_finite():
        raise IngestionError(f"{field} must be finite")
    return result


def _boolean(value: object) -> bool:
    if value in (True, "true", "True", "1", 1):
        return True
    if value in (False, "false", "False", "0", 0):
        return False
    raise IngestionError(f"invalid is_complete: {value!r}")


def _row_to_candle(row: Mapping[str, object], calendar: SessionCalendar) -> Candle:
    missing = set(REQUIRED_COLUMNS) - row.keys()
    extra = row.keys() - set(REQUIRED_COLUMNS)
    if missing or extra:
        raise IngestionError(f"column mismatch; missing={sorted(missing)}, extra={sorted(extra)}")
    try:
        session_date = date.fromisoformat(str(row["session_date"]))
        timeframe = Timeframe(str(row["timeframe"]))
    except ValueError as exc:
        raise IngestionError(f"invalid session_date/timeframe: {exc}") from exc
    open_time = _datetime(row["open_time"], "open_time")
    close_time = _datetime(row["close_time"], "close_time")
    session = calendar.bounds(session_date)
    if session is None:
        raise IngestionError(f"{session_date} is not an {calendar.name} session")
    session_open, session_close = session
    if open_time < session_open or close_time > session_close:
        raise IngestionError("candle lies outside the declared regular session")
    factor = _decimal(row["adjustment_factor"], "adjustment_factor")
    raw = {name: _decimal(row[name], name) for name in REQUIRED_COLUMNS if name.startswith("raw_")}
    adjusted = {name: _decimal(row[name], name) for name in ("open", "high", "low", "close")}
    for name in ("open", "high", "low", "close"):
        if adjusted[name] != raw[f"raw_{name}"] * factor:
            raise IngestionError(f"{name} does not equal raw_{name} * adjustment_factor")
    volume = _decimal(row["volume"], "volume")
    if volume != raw["raw_volume"]:
        raise IngestionError("Phase 1A requires volume to equal raw_volume")
    try:
        return Candle(
            symbol=str(row["symbol"]),
            timeframe=timeframe,
            open_time=open_time,
            close_time=close_time,
            session_date=session_date,
            open=adjusted["open"],
            high=adjusted["high"],
            low=adjusted["low"],
            close=adjusted["close"],
            volume=volume,
            is_complete=_boolean(row["is_complete"]),
            adjustment_factor=factor,
            source=str(row["source"]),
            source_revision=str(row["source_revision"]),
            raw_open=raw["raw_open"],
            raw_high=raw["raw_high"],
            raw_low=raw["raw_low"],
            raw_close=raw["raw_close"],
            raw_volume=raw["raw_volume"],
        )
    except ValueError as exc:
        raise IngestionError(str(exc)) from exc


def normalize_rows(rows: Iterable[Mapping[str, object]], calendar: SessionCalendar) -> list[Candle]:
    candles = [_row_to_candle(row, calendar) for row in rows]
    candles.sort(key=lambda item: (item.symbol, item.timeframe.value, item.open_time))
    seen: dict[tuple[str, Timeframe, datetime], Candle] = {}
    for candle in candles:
        key = (candle.symbol, candle.timeframe, candle.open_time)
        prior = seen.get(key)
        if prior is not None:
            if prior.to_json() != candle.to_json():
                raise IngestionError(f"conflicting duplicate candle: {key}")
            raise IngestionError(f"duplicate candle: {key}")
        seen[key] = candle
    return candles


def read_csv(path: str | Path, calendar: SessionCalendar) -> list[Candle]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != REQUIRED_COLUMNS:
            raise IngestionError("CSV columns or column order do not match the v1 contract")
        rows: list[Mapping[str, object]] = [dict(row) for row in reader]
    return normalize_rows(rows, calendar)


def read_parquet(path: str | Path, calendar: SessionCalendar) -> list[Candle]:
    parquet = importlib.import_module("pyarrow.parquet")
    table = parquet.read_table(Path(path))
    if tuple(table.column_names) != REQUIRED_COLUMNS:
        raise IngestionError("Parquet columns or column order do not match the v1 contract")
    rows: list[dict[str, Any]] = table.to_pylist()
    return normalize_rows(rows, calendar)


def read_ohlcv(path: str | Path, calendar: SessionCalendar) -> list[Candle]:
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix == ".csv":
        return read_csv(source, calendar)
    if suffix in (".parquet", ".pq"):
        return read_parquet(source, calendar)
    raise IngestionError(f"unsupported file extension: {suffix}")

