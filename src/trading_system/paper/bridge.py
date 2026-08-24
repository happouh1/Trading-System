"""Causal Phase 1 decision to Phase 3B shadow-intent bridge."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from trading_system.market_data.calendar import SessionCalendar
from trading_system.paper.adapters import InternalSimulatorAdapter
from trading_system.paper.contracts import OrderIntent, PaperMode, RuntimeState
from trading_system.paper.registry import PaperRegistry
from trading_system.paper.runtime import PaperRuntime
from trading_system.persistence import SQLiteRepository


def _next_session_open(known_at: datetime, calendar: SessionCalendar) -> datetime:
    session_date: date = known_at.date()
    for offset in range(15):
        bounds = calendar.bounds(session_date + timedelta(days=offset))
        if bounds is not None and bounds[0] > known_at:
            return bounds[0]
    raise ValueError("no eligible XNYS session open found within 15 calendar days")


def stage_shadow_decision(
    repository: SQLiteRepository,
    session_id: str,
    decision_id: str,
    occurred_at: datetime,
    calendar: SessionCalendar,
) -> OrderIntent:
    if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
        raise ValueError("paper bridge timestamp must be timezone-aware")
    registry = PaperRegistry(repository)
    if registry.current_state(session_id) is not RuntimeState.SHADOW:
        raise ValueError("decision staging requires an active SHADOW paper session")
    session = registry.session_payload(session_id)
    plan, known_at, _action, run_id = repository.load_decision_plan(decision_id)
    run = repository.run_metadata(run_id)
    if run is None:
        raise ValueError("decision run metadata is missing")
    code_version, _strategy_config_hash, data_revision, calendar_version, _seed = run
    expected = {
        "code_version": code_version,
        "data_revision": data_revision,
        "calendar_version": calendar_version,
    }
    if any(session.get(key) != value for key, value in expected.items()):
        raise ValueError("decision and paper runtime identities do not match")
    if calendar.version != calendar_version:
        raise ValueError("runtime calendar version does not match the decision run")
    if occurred_at < known_at:
        raise ValueError("decision cannot be staged before it is known")
    scheduled_open = _next_session_open(known_at, calendar)
    if occurred_at >= scheduled_open:
        raise ValueError("decision is stale for its next eligible XNYS open")
    return PaperRuntime(
        registry, session_id, PaperMode.SHADOW, InternalSimulatorAdapter()
    ).record_plan(plan, scheduled_open, occurred_at, source_decision_id=decision_id)
