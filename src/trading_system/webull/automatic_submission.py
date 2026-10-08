"""Fail-closed automatic submission for due Webull sandbox intents."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType
from zoneinfo import ZoneInfo

from trading_system.domain import Direction, TradePlan
from trading_system.paper import PaperRegistry, RuntimeState
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id
from trading_system.webull.contracts import WebullResponse
from trading_system.webull.mapping import map_stock_order
from trading_system.webull.service import WebullSandboxService

_NEW_YORK = ZoneInfo("America/New_York")


class AutomaticSubmissionConfigError(ValueError):
    """The automatic sandbox submission policy is malformed or unsafe."""


@dataclass(frozen=True, slots=True)
class AutomaticSubmissionConfig:
    plan_id: str
    symbols: tuple[str, ...]
    blocked_symbols: tuple[str, ...]
    tick_seconds: int
    max_release_lateness_seconds: int
    config_hash: str
    version: str = "12A.1.0"


@dataclass(frozen=True, slots=True)
class AutomaticSubmissionResult:
    cycle_id: str
    session_id: str
    observed_at: datetime
    status: str
    reason: str
    intent_id: str | None
    client_order_id: str | None
    config_hash: str
    environment: str = "WEBULL_SANDBOX"
    quantity: int = 0
    network_used: bool = False
    broker_write_performed: bool = False
    live_trading_enabled: bool = False

    def __post_init__(self) -> None:
        if (
            not self.cycle_id
            or not self.session_id
            or self.observed_at.tzinfo is None
            or self.observed_at.utcoffset() != UTC.utcoffset(self.observed_at)
            or self.status not in {"NO_ACTION", "SUBMITTED", "BLOCKED"}
            or not self.reason
            or self.environment != "WEBULL_SANDBOX"
            or self.quantity not in {0, 1}
            or self.live_trading_enabled
            or self.broker_write_performed != (self.status == "SUBMITTED")
        ):
            raise ValueError("invalid automatic Webull sandbox submission result")


def load_automatic_submission_config(
    path: str | Path,
) -> AutomaticSubmissionConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "automatic_submission_version",
        "mode",
        "plan_id",
        "schedule",
        "universe",
        "order_policy",
        "authority",
    }
    schedule = raw.get("schedule") if isinstance(raw, dict) else None
    universe = raw.get("universe") if isinstance(raw, dict) else None
    order = raw.get("order_policy") if isinstance(raw, dict) else None
    authority = raw.get("authority") if isinstance(raw, dict) else None
    if (
        not isinstance(raw, dict)
        or set(raw) != expected
        or raw["automatic_submission_version"] != "12A.1.0"
        or raw["mode"] != "AUTOMATIC_WEBULL_SANDBOX_ONLY"
        or not isinstance(raw["plan_id"], str)
        or not raw["plan_id"]
        or schedule
        != {
            "timezone": "America/New_York",
            "weekdays": [1, 2, 3, 4, 5],
            "start": "04:00",
            "stop": "20:00",
            "tick_seconds": 30,
        }
        or not isinstance(universe, dict)
        or set(universe) != {"symbols", "blocked_symbols"}
        or order
        != {
            "direction": "LONG_ONLY",
            "quantity": 1,
            "whole_shares_only": True,
            "session": "CORE",
            "max_new_orders_per_market_day": 1,
            "max_active_trades_per_symbol": 1,
            "preview_required": True,
            "reconciliation_required": True,
            "max_release_lateness_seconds": 120,
        }
        or authority
        != {
            "network_read_enabled": True,
            "credential_loading_enabled": True,
            "sandbox_preview_enabled": True,
            "sandbox_order_submission_enabled": True,
            "production_endpoint_enabled": False,
            "live_trading_enabled": False,
            "automatic_promotion_enabled": False,
        }
    ):
        raise AutomaticSubmissionConfigError(
            "automatic Webull sandbox submission configuration is invalid or unsafe"
        )
    symbols = _symbols(universe["symbols"])
    blocked = _symbols(universe["blocked_symbols"])
    if not symbols or set(symbols) & set(blocked) or "AAPL" not in blocked:
        raise AutomaticSubmissionConfigError(
            "automatic submission universe must exclude and block legacy AAPL"
        )
    return AutomaticSubmissionConfig(
        str(raw["plan_id"]),
        symbols,
        blocked,
        30,
        120,
        canonical_hash(_freeze(raw)),
    )


def run_automatic_submission_cycle(
    repository: SQLiteRepository,
    service: WebullSandboxService,
    config: AutomaticSubmissionConfig,
    *,
    session_id: str,
    observed_at: datetime,
    snapshot: WebullResponse | None,
    environment_enabled: bool,
    cli_enabled: bool,
) -> AutomaticSubmissionResult:
    """Submit at most one due, one-share, long-only sandbox intent."""
    if observed_at.tzinfo is None or observed_at.utcoffset() != UTC.utcoffset(observed_at):
        raise ValueError("automatic submission observed_at must be UTC")
    paper = PaperRegistry(repository)
    network_used = snapshot is not None
    if paper.current_state(session_id) is not RuntimeState.PAPER_ENABLED:
        return _result(
            repository, config, session_id, observed_at,
            "BLOCKED", "PAPER_NOT_ENABLED", network_used,
        )
    binding = repository.connection.execute(
        "SELECT plan_id FROM paper_burn_in_session_bindings WHERE session_id=?",
        (session_id,),
    ).fetchone()
    if binding is None or str(binding[0]) != config.plan_id:
        return _result(
            repository, config, session_id, observed_at,
            "BLOCKED", "PLAN_NOT_BOUND", network_used,
        )
    local = observed_at.astimezone(_NEW_YORK)
    if local.isoweekday() not in {1, 2, 3, 4, 5} or not time(4) <= local.time() < time(20):
        return _result(
            repository, config, session_id, observed_at,
            "NO_ACTION", "OUTSIDE_SCHEDULE", network_used,
        )
    candidates = []
    for intent_id in paper.intent_ids(session_id):
        intent = paper.load_intent(intent_id)
        age = (observed_at - intent.scheduled_open).total_seconds()
        plan = intent.payload.get("trade_plan")
        if (
            0 <= age <= config.max_release_lateness_seconds
            and isinstance(plan, TradePlan)
            and plan.direction is Direction.LONG
            and plan.symbol in config.symbols
            and plan.symbol not in config.blocked_symbols
        ):
            candidates.append((intent.scheduled_open, intent_id, plan))
    if not candidates:
        return _result(
            repository, config, session_id, observed_at,
            "NO_ACTION", "NO_DUE_INTENT", network_used,
        )
    candidates.sort(key=lambda item: (item[0], item[1]))
    scheduled_open, intent_id, plan = candidates[0]
    day_start = scheduled_open.replace(hour=0, minute=0, second=0, microsecond=0)
    placed = repository.connection.execute(
        """SELECT COUNT(*) FROM webull_submission_events
           WHERE session_id=? AND event_type='ACKNOWLEDGED' AND occurred_at>=?""",
        (session_id, _time(day_start)),
    ).fetchone()
    if placed is not None and int(placed[0]) >= 1:
        return _result(
            repository, config, session_id, observed_at,
            "BLOCKED", "DAILY_ORDER_CAP", network_used,
        )
    positions = dict(service.sandbox_positions(observed_at))
    if positions.get(plan.symbol, 0) != 0:
        return _result(
            repository, config, session_id, observed_at,
            "BLOCKED", "SYMBOL_POSITION_EXISTS", network_used,
        )
    orders = service.sandbox_open_orders(observed_at)
    if any(item.symbol == plan.symbol for item in orders):
        return _result(
            repository, config, session_id, observed_at,
            "BLOCKED", "SYMBOL_ORDER_EXISTS", network_used,
        )
    if snapshot is None:
        return _result(
            repository, config, session_id, observed_at,
            "BLOCKED", "OPEN_SNAPSHOT_MISSING", network_used,
        )
    observed_open = _snapshot_open(
        snapshot,
        plan.symbol,
        scheduled_open=scheduled_open,
        received_at=observed_at,
    )
    adr20 = _prior_adr20(repository, plan.symbol, scheduled_open)
    if adr20 is None:
        return _result(
            repository, config, session_id, observed_at,
            "BLOCKED", "ADR20_NOT_WARM", network_used,
        )
    order = map_stock_order(plan, intent_id, 1)
    if not service.preview(intent_id, order, observed_at):
        return _result(
            repository, config, session_id, observed_at,
            "BLOCKED", "PREVIEW_REJECTED", network_used,
        )
    release = service.record_entry_release(
        intent_id, order, scheduled_open, observed_at, observed_open, adr20
    )
    if not release.approved:
        return _result(
            repository, config, session_id, observed_at,
            "BLOCKED", release.reason, network_used,
        )
    reconciliation = service.reconcile(Decimal("1"), observed_at)
    if not reconciliation.matched:
        return _result(
            repository, config, session_id, observed_at,
            "BLOCKED", "RECONCILIATION_MISMATCH", network_used,
        )
    item = service.submit(
        intent_id,
        order,
        observed_at,
        environment_enabled=environment_enabled,
        cli_enabled=cli_enabled,
    )
    result = AutomaticSubmissionResult(
        deterministic_id(
            "automatic_webull_submission_cycle",
            (session_id, observed_at, config.config_hash, intent_id),
        ),
        session_id,
        observed_at,
        "SUBMITTED",
        item.status.value,
        intent_id,
        item.client_order_id,
        config.config_hash,
        quantity=1,
        network_used=True,
        broker_write_performed=True,
    )
    _insert_result(repository, result)
    return result


def _result(
    repository: SQLiteRepository,
    config: AutomaticSubmissionConfig,
    session_id: str,
    observed_at: datetime,
    status: str,
    reason: str,
    network_used: bool,
) -> AutomaticSubmissionResult:
    item = AutomaticSubmissionResult(
        deterministic_id(
            "automatic_webull_submission_cycle",
            (session_id, observed_at, config.config_hash, status, reason),
        ),
        session_id,
        observed_at,
        status,
        reason,
        None,
        None,
        config.config_hash,
        network_used=network_used,
    )
    _insert_result(repository, item)
    return item


def _insert_result(repository: SQLiteRepository, item: AutomaticSubmissionResult) -> None:
    payload_json, payload_hash = canonical_json(item), canonical_hash(item)
    repository.connection.execute(
        """INSERT OR IGNORE INTO webull_automatic_submission_cycles
           (cycle_id,session_id,observed_at,status,reason,intent_id,client_order_id,
            quantity,config_hash,network_used,broker_write_performed,payload_json,payload_hash)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            item.cycle_id,
            item.session_id,
            _time(item.observed_at),
            item.status,
            item.reason,
            item.intent_id,
            item.client_order_id,
            item.quantity,
            item.config_hash,
            int(item.network_used),
            int(item.broker_write_performed),
            payload_json,
            payload_hash,
        ),
    )
    repository.connection.commit()


def _snapshot_open(
    response: WebullResponse,
    symbol: str,
    *,
    scheduled_open: datetime,
    received_at: datetime,
) -> Decimal:
    values = response.payload.get("items")
    if not isinstance(values, (tuple, list)):
        raise ValueError("Webull opening snapshot lacks items")
    matches = [
        item
        for item in values
        if isinstance(item, Mapping) and item.get("symbol") == symbol
    ]
    if len(matches) != 1 or set(matches[0]) < {"symbol", "open", "quote_time"}:
        raise ValueError("Webull opening snapshot does not identify exactly one symbol")
    quote_value = matches[0]["quote_time"]
    if isinstance(quote_value, bool) or not isinstance(quote_value, (int, float)):
        raise ValueError("Webull opening snapshot quote time is invalid")
    quote_time = datetime.fromtimestamp(float(quote_value) / 1000, tz=UTC)
    if not scheduled_open <= quote_time <= received_at:
        raise ValueError("Webull opening snapshot is stale or future-known")
    try:
        value = Decimal(str(matches[0]["open"]))
    except InvalidOperation as exc:
        raise ValueError("Webull opening snapshot price is invalid") from exc
    if not value.is_finite() or value <= 0:
        raise ValueError("Webull opening snapshot price must be positive")
    return value


def _prior_adr20(
    repository: SQLiteRepository, symbol: str, scheduled_open: datetime
) -> Decimal | None:
    rows = repository.connection.execute(
        """SELECT session_date,high,low FROM candles
           WHERE symbol=? AND timeframe='1d' AND close_time<? AND is_complete=1
           ORDER BY close_time DESC,candle_id DESC""",
        (symbol, _time(scheduled_open)),
    ).fetchall()
    sessions: dict[str, tuple[Decimal, Decimal]] = {}
    for session_date, high, low in rows:
        key = str(session_date)
        values = (Decimal(str(high)), Decimal(str(low)))
        prior = sessions.setdefault(key, values)
        if prior != values:
            raise ValueError("conflicting prior daily candle revisions")
    selected = tuple(sessions[key] for key in sorted(sessions, reverse=True)[:20])
    if len(selected) != 20:
        return None
    total = sum(
        (high - low for high, low in selected),
        Decimal(0),
    )
    return total / Decimal(20)


def _symbols(value: object) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or item != item.upper() for item in value)
    ):
        raise AutomaticSubmissionConfigError("automatic submission symbols are invalid")
    result = tuple(value)
    if result != tuple(sorted(set(result))):
        raise AutomaticSubmissionConfigError(
            "automatic submission symbols must be sorted and unique"
        )
    return result


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _time(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
