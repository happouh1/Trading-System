"""Strict historical market-data ingestion, calendars, and aggregation."""

from trading_system.market_data.aggregation import aggregate
from trading_system.market_data.calendar import StaticSessionCalendar, XNYSCalendar
from trading_system.market_data.ingestion import IngestionError, read_ohlcv

__all__ = ["IngestionError", "StaticSessionCalendar", "XNYSCalendar", "aggregate", "read_ohlcv"]
