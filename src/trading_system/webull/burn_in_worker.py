"""Phase 11G bounded, read-only Webull sandbox burn-in worker."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType

from trading_system.market_data import XNYSCalendar
from trading_system.paper import PaperRegistry, RuntimeState
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id
from trading_system.webull.contracts import WebullResponse
from trading_system.webull.market_data import (
    MarketDataKind,
    WebullMarketDataNormalizer,
    WebullMarketDataSource,
    decode_sdk_history,
)
from trading_system.webull.registry import WebullRegistry


class BurnInWorkerConfigError(ValueError):
    """Raised when Phase 11G configuration grants unsafe authority."""


@dataclass(frozen=True, slots=True)
class BurnInWorkerConfig:
    plan_id: str
    symbols: tuple[str, ...]
    timespan: str
    history_count: int
    network_read_enabled: bool
    credential_loading_enabled: bool
    config_hash: str
    worker_version: str = "11G.1.0"


@dataclass(frozen=True, slots=True)
class BurnInWorkerResult:
    cycle_id: str
    session_id: str
    observed_at: datetime
    symbols: tuple[str, ...]
    history_responses: int
    completed_bars_seen: int
    new_bars_persisted: int
    heartbeat_inserted: bool
    config_hash: str
    worker_version: str = "11G.1.0"
    environment: str = "WEBULL_SANDBOX"
    network_used: bool = False
    credentials_loaded: bool = False
    broker_write_performed: bool = False
    order_api_available: bool = False
    live_trading_enabled: bool = False
    automatic_promotion_enabled: bool = False

    def __post_init__(self) -> None:
        if (
            not all((self.cycle_id, self.session_id, self.symbols, self.config_hash))
            or self.observed_at.tzinfo is None
            or self.observed_at.utcoffset() != UTC.utcoffset(self.observed_at)
            or min(
                self.history_responses,
                self.completed_bars_seen,
                self.new_bars_persisted,
            )
            < 0
            or self.new_bars_persisted > self.completed_bars_seen
            or self.worker_version != "11G.1.0"
            or self.environment != "WEBULL_SANDBOX"
            or self.credentials_loaded != self.network_used
            or any(
                (
                    self.broker_write_performed,
                    self.order_api_available,
                    self.live_trading_enabled,
                    self.automatic_promotion_enabled,
                )
            )
        ):
            raise ValueError("invalid Phase 11G burn-in worker result")


def load_burn_in_worker_config(path: str | Path) -> BurnInWorkerConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "worker_version",
        "mode",
        "plan_id",
        "market_data",
        "authority",
    }
    market_data = raw.get("market_data") if isinstance(raw, dict) else None
    authority = raw.get("authority") if isinstance(raw, dict) else None
    if (
        not isinstance(raw, dict)
        or set(raw) != expected
        or raw["worker_version"] != "11G.1.0"
        or raw["mode"]
        not in {
            "OFFLINE_VALIDATION_ONLY",
            "PROSPECTIVE_WEBULL_SANDBOX_READ_ONLY",
        }
        or not isinstance(raw["plan_id"], str)
        or not raw["plan_id"]
        or not isinstance(market_data, dict)
        or set(market_data) != {"symbols", "timespan", "history_count"}
        or not isinstance(authority, dict)
        or set(authority)
        != {
            "database_read_enabled",
            "database_write_enabled",
            "network_read_enabled",
            "credential_loading_enabled",
            "broker_writes_enabled",
            "order_api_enabled",
            "sandbox_execution_enabled",
            "live_trading_enabled",
            "automatic_promotion_enabled",
        }
    ):
        raise BurnInWorkerConfigError("Phase 11G configuration keys are invalid")
    symbols = market_data["symbols"]
    history_count = market_data["history_count"]
    network = authority["network_read_enabled"]
    credentials = authority["credential_loading_enabled"]
    forbidden = (
        authority["broker_writes_enabled"],
        authority["order_api_enabled"],
        authority["sandbox_execution_enabled"],
        authority["live_trading_enabled"],
        authority["automatic_promotion_enabled"],
    )
    if (
        not isinstance(symbols, list)
        or not symbols
        or any(not isinstance(item, str) or item != item.upper() for item in symbols)
        or tuple(symbols) != tuple(sorted(set(symbols)))
        or market_data["timespan"] != "M60"
        or isinstance(history_count, bool)
        or not isinstance(history_count, int)
        or not 1 <= history_count <= 1200
        or authority["database_read_enabled"] is not True
        or authority["database_write_enabled"] is not True
        or not isinstance(network, bool)
        or not isinstance(credentials, bool)
        or network != credentials
        or any(value is not False for value in forbidden)
        or (raw["mode"] == "OFFLINE_VALIDATION_ONLY" and network)
        or (
            raw["mode"] == "PROSPECTIVE_WEBULL_SANDBOX_READ_ONLY"
            and not network
        )
    ):
        raise BurnInWorkerConfigError("Phase 11G configuration is invalid or unsafe")
    return BurnInWorkerConfig(
        str(raw["plan_id"]),
        tuple(symbols),
        str(market_data["timespan"]),
        history_count,
        network,
        credentials,
        canonical_hash(_freeze(raw)),
    )


def run_burn_in_worker_cycle(
    repository: SQLiteRepository,
    config: BurnInWorkerConfig,
    source: WebullMarketDataSource,
    *,
    session_id: str,
    observed_at: datetime,
    network_used: bool,
) -> BurnInWorkerResult:
    """Run one bounded acquisition cycle through a market-data-only protocol."""
    if observed_at.tzinfo is None or observed_at.utcoffset() != UTC.utcoffset(observed_at):
        raise ValueError("Phase 11G observed_at must be UTC")
    if network_used != config.network_read_enabled:
        raise ValueError("Phase 11G network use does not match locked worker authority")
    _validate_session(repository, config, session_id, observed_at)
    webull = WebullRegistry(repository)
    paper = PaperRegistry(repository)
    snapshot = source.market_snapshot(config.symbols)
    webull.insert_envelope(
        session_id,
        "BURN_IN_MARKET_SNAPSHOT",
        observed_at,
        snapshot,
        {"symbols": config.symbols},
    )
    if not 200 <= snapshot.status_code < 300:
        raise ValueError("Phase 11G Webull market snapshot failed")

    completed_seen = 0
    inserted = 0
    calendar = XNYSCalendar()
    normalizer = WebullMarketDataNormalizer(calendar)
    for symbol in config.symbols:
        response = source.historical_bars(symbol, config.timespan, config.history_count)
        webull.insert_envelope(
            session_id,
            "BURN_IN_HISTORICAL_RAW",
            observed_at,
            response,
            {
                "symbol": symbol,
                "timespan": config.timespan,
                "count": config.history_count,
            },
        )
        if not 200 <= response.status_code < 300:
            raise ValueError(f"Phase 11G Webull history failed for {symbol}")
        completed = _completed_history(response, observed_at, calendar)
        decoded = decode_sdk_history(completed, observed_at, calendar)
        raw_bars = decoded.payload.get("bars")
        if not isinstance(raw_bars, (tuple, list)):
            raise ValueError("Phase 11G decoded history is invalid")
        completed_seen += len(raw_bars)
        for raw_bar in raw_bars:
            if not isinstance(raw_bar, Mapping):
                raise ValueError("Phase 11G decoded bar is invalid")
            payload = {str(key): value for key, value in raw_bar.items()}
            stable_payload = {
                key: value for key, value in payload.items() if key != "provider_timestamp"
            }
            revision = canonical_hash(
                {
                    "provider": "WEBULL_SANDBOX",
                    "sdk_schema": "2.0.17-M60-RTH",
                    "bar": stable_payload,
                }
            )
            if _bar_exists(repository, session_id, symbol, payload, revision):
                continue
            item = normalizer.normalize(
                payload,
                received_at=observed_at,
                source_revision=revision,
                kind=MarketDataKind.HISTORICAL,
            )
            inserted += int(webull.insert_shadow_bar(session_id, item))
    heartbeat_inserted = paper.insert_heartbeat(session_id, observed_at)
    cycle_id = deterministic_id(
        "webull_burn_in_worker_cycle",
        (session_id, observed_at, config.config_hash),
    )
    result = BurnInWorkerResult(
        cycle_id,
        session_id,
        observed_at,
        config.symbols,
        len(config.symbols),
        completed_seen,
        inserted,
        heartbeat_inserted,
        config.config_hash,
        network_used=network_used,
        credentials_loaded=network_used,
    )
    _insert_cycle(repository, result)
    return result


def _validate_session(
    repository: SQLiteRepository,
    config: BurnInWorkerConfig,
    session_id: str,
    observed_at: datetime,
) -> None:
    state = PaperRegistry(repository).current_state(session_id)
    if state is not RuntimeState.SHADOW:
        raise ValueError("Phase 11G requires a SHADOW paper session")
    binding = repository.connection.execute(
        """SELECT plan_id,started_at FROM paper_burn_in_session_bindings
           WHERE session_id = ?""",
        (session_id,),
    ).fetchone()
    if binding is None or str(binding[0]) != config.plan_id:
        raise ValueError("Phase 11G session is not bound to the configured burn-in plan")
    started_at = _parse_time(binding[1])
    if started_at > observed_at:
        raise ValueError("Phase 11G session binding is future-known")
    verification = repository.connection.execute(
        """SELECT occurred_at FROM webull_connection_verifications
           WHERE session_id = ? AND occurred_at <= ?
           ORDER BY occurred_at DESC LIMIT 1""",
        (session_id, _time(observed_at)),
    ).fetchone()
    if verification is None:
        raise ValueError("Phase 11G requires same-session Webull sandbox verification")


def _completed_history(
    response: WebullResponse,
    observed_at: datetime,
    calendar: XNYSCalendar,
) -> WebullResponse:
    items = response.payload.get("items")
    if not isinstance(items, (tuple, list)):
        raise ValueError("Phase 11G Webull history response lacks items")
    completed: list[object] = []
    for item in items:
        if not isinstance(item, Mapping) or "time" not in item:
            raise ValueError("Phase 11G Webull history item is invalid")
        opened = _parse_time(item["time"])
        bounds = calendar.bounds(opened.date())
        if bounds is None:
            raise ValueError("Phase 11G Webull history item is outside XNYS")
        if bounds[1] <= observed_at:
            completed.append(item)
    return WebullResponse(response.status_code, {"items": tuple(completed)})


def _bar_exists(
    repository: SQLiteRepository,
    session_id: str,
    symbol: str,
    payload: Mapping[str, object],
    revision: str,
) -> bool:
    row = repository.connection.execute(
        """SELECT 1 FROM webull_shadow_bars w
           JOIN candles c ON c.candle_id = w.candle_id
           WHERE w.session_id = ? AND c.symbol = ? AND c.open_time = ?
             AND c.source_revision = ? LIMIT 1""",
        (session_id, symbol, _time(_parse_time(payload["open_time"])), revision),
    ).fetchone()
    return bool(row == (1,))


def _insert_cycle(repository: SQLiteRepository, item: BurnInWorkerResult) -> bool:
    payload_json = canonical_json(item)
    payload_hash = canonical_hash(item)
    values = (
        item.cycle_id,
        item.session_id,
        _time(item.observed_at),
        item.config_hash,
        item.history_responses,
        item.completed_bars_seen,
        item.new_bars_persisted,
        int(item.heartbeat_inserted),
        int(item.network_used),
        payload_json,
        payload_hash,
    )
    cursor = repository.connection.execute(
        """INSERT OR IGNORE INTO webull_burn_in_worker_cycles
           (cycle_id,session_id,observed_at,config_hash,history_responses,
            completed_bars_seen,new_bars_persisted,heartbeat_inserted,network_used,
            payload_json,payload_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        values,
    )
    if cursor.rowcount == 0:
        stored = repository.connection.execute(
            """SELECT cycle_id,session_id,observed_at,config_hash,history_responses,
                      completed_bars_seen,new_bars_persisted,heartbeat_inserted,network_used,
                      payload_json,payload_hash
               FROM webull_burn_in_worker_cycles WHERE cycle_id = ?""",
            (item.cycle_id,),
        ).fetchone()
        if stored != values:
            raise ValueError(f"conflicting Phase 11G worker cycle: {item.cycle_id}")
        return False
    repository.connection.commit()
    return True


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Phase 11G timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_time(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Phase 11G provider timestamps must be timezone-aware")
    return parsed.astimezone(UTC)


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value
