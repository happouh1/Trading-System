"""Deterministic session-aware candle aggregation without forward filling."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from trading_system.domain import Candle, Timeframe
from trading_system.market_data.calendar import SessionCalendar
from trading_system.market_data.ingestion import IngestionError

_NEW_YORK = ZoneInfo("America/New_York")


def _validate_source(candles: list[Candle], calendar: SessionCalendar) -> None:
    if not candles:
        return
    prior: Candle | None = None
    for candle in candles:
        if not candle.is_complete:
            raise IngestionError("incomplete source candles cannot be aggregated")
        bounds = calendar.bounds(candle.session_date)
        if bounds is None or candle.open_time < bounds[0] or candle.close_time > bounds[1]:
            raise IngestionError("source candle is outside its exchange session")
        if prior is not None:
            if candle.symbol != prior.symbol or candle.timeframe != prior.timeframe:
                raise IngestionError("aggregate one symbol and source timeframe at a time")
            if candle.open_time <= prior.open_time:
                raise IngestionError("source candles must be strictly ordered")
            if candle.session_date == prior.session_date and candle.open_time != prior.close_time:
                raise IngestionError("missing or overlapping intraday source interval")
        prior = candle


def _aggregate_group(group: list[Candle], timeframe: Timeframe) -> Candle:
    first, last = group[0], group[-1]
    factors = {item.adjustment_factor for item in group}
    revisions = {item.source_revision for item in group}
    sources = {item.source for item in group}
    if len(factors) != 1 or len(revisions) != 1 or len(sources) != 1:
        raise IngestionError("aggregate group must have one factor, revision, and source")
    raw_values = (first.raw_open, last.raw_close)
    if any(value is None for value in raw_values):
        raise IngestionError("aggregation requires audited raw OHLCV fields")
    raw_highs = [item.raw_high for item in group]
    raw_lows = [item.raw_low for item in group]
    raw_volumes = [item.raw_volume for item in group]
    if any(value is None for value in (*raw_highs, *raw_lows, *raw_volumes)):
        raise IngestionError("aggregation requires complete raw OHLCV fields")
    assert first.raw_open is not None
    assert last.raw_close is not None
    return Candle(
        symbol=first.symbol,
        timeframe=timeframe,
        open_time=first.open_time,
        close_time=last.close_time,
        session_date=first.session_date,
        open=first.open,
        high=max(item.high for item in group),
        low=min(item.low for item in group),
        close=last.close,
        volume=sum((item.volume for item in group), Decimal(0)),
        is_complete=True,
        adjustment_factor=first.adjustment_factor,
        source=first.source,
        source_revision=first.source_revision,
        raw_open=first.raw_open,
        raw_high=max(value for value in raw_highs if value is not None),
        raw_low=min(value for value in raw_lows if value is not None),
        raw_close=last.raw_close,
        raw_volume=sum((value for value in raw_volumes if value is not None), Decimal(0)),
    )


def _session_groups(candles: list[Candle], calendar: SessionCalendar) -> list[list[Candle]]:
    groups: dict[date, list[Candle]] = defaultdict(list)
    for candle in candles:
        groups[candle.session_date].append(candle)
    result: list[list[Candle]] = []
    for session_date in sorted(groups):
        group = groups[session_date]
        bounds = calendar.bounds(session_date)
        assert bounds is not None
        if group[0].open_time != bounds[0] or group[-1].close_time != bounds[1]:
            raise IngestionError(f"source data does not cover full session {session_date}")
        result.append(group)
    return result


def aggregate_4h(candles: Iterable[Candle], calendar: SessionCalendar) -> list[Candle]:
    source = list(candles)
    _validate_source(source, calendar)
    if any(item.timeframe is not Timeframe.HOUR_1 for item in source):
        raise IngestionError("4H aggregation requires 1H source candles")
    result: list[Candle] = []
    for session_group in _session_groups(source, calendar):
        first_bucket: list[Candle] = []
        second_bucket: list[Candle] = []
        boundary = datetime.combine(
            session_group[0].session_date,
            time(13, 30),
            tzinfo=_NEW_YORK,
        )
        for candle in session_group:
            target = first_bucket if candle.open_time < boundary else second_bucket
            if candle.open_time < boundary < candle.close_time:
                raise IngestionError("source candle crosses the 13:30 ET 4H boundary")
            target.append(candle)
        for group in (first_bucket, second_bucket):
            if group:
                result.append(_aggregate_group(group, Timeframe.HOUR_4))
    return result


def aggregate_daily(candles: Iterable[Candle], calendar: SessionCalendar) -> list[Candle]:
    source = list(candles)
    _validate_source(source, calendar)
    if any(item.timeframe is not Timeframe.HOUR_1 for item in source):
        raise IngestionError("daily aggregation requires 1H source candles")
    return [_aggregate_group(group, Timeframe.DAY_1) for group in _session_groups(source, calendar)]


def aggregate_weekly(daily: Iterable[Candle], calendar: SessionCalendar) -> list[Candle]:
    source = list(daily)
    _validate_source(source, calendar)
    if any(item.timeframe is not Timeframe.DAY_1 for item in source):
        raise IngestionError("weekly aggregation requires daily source candles")
    for candle in source:
        bounds = calendar.bounds(candle.session_date)
        assert bounds is not None
        if (candle.open_time, candle.close_time) != bounds:
            raise IngestionError("weekly aggregation requires complete daily candles")
    groups: dict[date, list[Candle]] = defaultdict(list)
    for candle in source:
        monday = candle.session_date - timedelta(days=candle.session_date.weekday())
        groups[monday].append(candle)
    result: list[Candle] = []
    for monday in sorted(groups):
        group = groups[monday]
        expected = {
            current
            for offset in range(5)
            if calendar.bounds(current := monday + timedelta(days=offset)) is not None
        }
        actual = {item.session_date for item in group}
        if actual != expected:
            continue
        weekly = _aggregate_group(group, Timeframe.WEEK_1)
        result.append(replace(weekly, session_date=group[-1].session_date))
    return result


def aggregate(
    candles: Iterable[Candle],
    timeframe: Timeframe,
    calendar: SessionCalendar,
) -> list[Candle]:
    source = sorted(candles, key=lambda item: item.open_time)
    if timeframe is Timeframe.HOUR_1:
        _validate_source(source, calendar)
        return source
    if timeframe is Timeframe.HOUR_4:
        return aggregate_4h(source, calendar)
    if timeframe is Timeframe.DAY_1:
        return aggregate_daily(source, calendar)
    if timeframe is Timeframe.WEEK_1:
        return aggregate_weekly(source, calendar)
    raise IngestionError(f"unsupported target timeframe: {timeframe}")
