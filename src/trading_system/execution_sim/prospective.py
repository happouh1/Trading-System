"""Offline prospective entry boundary; no broker or cohort activation capability."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, localcontext

from trading_system.domain import Candle, Direction, Timeframe, TradePlan
from trading_system.execution_sim.entries import execute_next_open
from trading_system.market_data.calendar import SessionCalendar
from trading_system.serialization import canonical_hash, deterministic_id

VERSION = "PROSPECTIVE_ENTRY.1.0"


def _utc(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("UTC timestamps required")


@dataclass(frozen=True, slots=True)
class ProspectiveEntry:
    decision_id: str
    plan: TradePlan
    recorded_at: datetime
    feature_known_at: datetime
    atr20: Decimal
    adr20: Decimal
    adjustment_factor: Decimal
    config_hash: str
    code_version: str

    def __post_init__(self) -> None:
        _utc(self.recorded_at)
        _utc(self.feature_known_at)
        if not self.decision_id or not self.config_hash or not self.code_version:
            raise ValueError("decision and version provenance required")
        if self.plan.direction is not Direction.LONG or self.plan.symbol == "AAPL":
            raise ValueError("long-only entries excluding legacy AAPL holding")
        if self.plan.timeframe not in {Timeframe.HOUR_1, Timeframe.HOUR_4}:
            raise ValueError("intraday signal timeframe required")
        if not self.feature_known_at <= self.plan.created_at <= self.recorded_at:
            raise ValueError("noncausal decision or feature timestamp")
        if any(not x.is_finite() or x <= 0 for x in (
            self.atr20, self.adr20, self.adjustment_factor,
        )):
            raise ValueError("positive finite inputs required")


@dataclass(frozen=True, slots=True)
class EntryAssessment:
    assessment_id: str
    decision_id: str
    model_hash: str
    status: str
    event_time: datetime
    known_at: datetime
    source_candle_id: str | None
    fill_price: Decimal | None
    quantity: Decimal
    source: str = field(default="SHADOW_SIMULATED", init=False)
    fees_status: str = field(default="NOT_MODELLED", init=False)
    spread_status: str = field(default="NOT_SEPARATELY_MODELLED", init=False)
    qualifying_completed_trade: bool = field(default=False, init=False)
    broker_write_performed: bool = field(default=False, init=False)


def eligible_slot(
    entry: ProspectiveEntry, calendar: SessionCalendar,
) -> tuple[datetime, datetime]:
    """Find the immediate session-aligned bar, not a later convenient observation."""
    if calendar.name != "XNYS":
        raise ValueError("XNYS required")
    step = timedelta(hours=1 if entry.plan.timeframe is Timeframe.HOUR_1 else 4)
    for offset in range(15):
        bounds = calendar.bounds(entry.plan.created_at.date() + timedelta(days=offset))
        if bounds is None:
            continue
        start, end = bounds
        while start < end:
            close = min(start + step, end)
            if start >= entry.plan.created_at:
                return start, close
            start = close
    raise ValueError("next eligible session unavailable in calendar")


def assess_entry(
    entry: ProspectiveEntry, *, calendar: SessionCalendar, as_of: datetime,
    candle: Candle | None = None, received_at: datetime | None = None,
) -> EntryAssessment:
    """Pure evaluation; caller must persist the receipt before production use.

    No position allocation, lifecycle, or burn-in registry is invoked here.
    """
    _utc(as_of)
    if as_of < entry.recorded_at:
        raise ValueError("decision unavailable at cutoff")
    start, end = eligible_slot(entry, calendar)
    model_hash = canonical_hash((VERSION, calendar.name, calendar.version,
                                 "LONG_ONE_SHARE", "AAPL_EXCLUDED", "FEES_NOT_MODELLED",
                                 "COMBINED_FRICTION", "1bps", "0.02ATR", "0.25ADR"))
    status = "WAITING"
    fill: Decimal | None = None
    source_id: str | None = None
    known = as_of
    if entry.recorded_at > start:
        status = "REJECTED_LATE_DECISION"
    elif candle is None:
        if received_at is not None:
            raise ValueError("receipt requires candle")
        if as_of >= end:
            status = "EXPIRED_MISSING_ELIGIBLE_BAR"
    else:
        if received_at is None:
            raise ValueError("receipt timestamp required")
        _utc(received_at)
        if received_at > as_of or received_at < candle.close_time:
            raise ValueError("completed candle unavailable at cutoff")
        if (
            candle.symbol != entry.plan.symbol or candle.timeframe is not entry.plan.timeframe
            or candle.open_time != start or candle.close_time != end or not candle.is_complete
        ):
            raise ValueError("must supply the exact completed eligible bar")
        if candle.adjustment_factor != entry.adjustment_factor:
            raise ValueError("unsupported adjustment transition")
        if entry.feature_known_at > start:
            raise ValueError("future execution features")
        with localcontext() as context:
            context.prec = 50
            result = execute_next_open(
                run_id="offline-prospective", trade_id=entry.decision_id, plan=entry.plan,
                next_candle=candle, atr20=entry.atr20, adr20=entry.adr20, quantity=Decimal(1),
            )
        fill = result.fill_price
        if fill is not None and (not fill.is_finite() or fill <= entry.plan.initial_stop):
            status, fill = "REJECTED_INVALID_FILL_RISK", None
        else:
            status = "ENTRY_MODELLED" if fill is not None else "ENTRY_GAP_TOO_LARGE"
        known, source_id = received_at, candle.candle_id
    identity = (entry, model_hash, status, start, known, source_id, fill)
    return EntryAssessment(
        deterministic_id("sim_entry_assessment", identity), entry.decision_id, model_hash,
        status, start, known, source_id, fill, Decimal(1) if fill is not None else Decimal(0),
    )
