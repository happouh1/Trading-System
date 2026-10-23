"""Read-only Phase 12J research and evaluation dashboard."""

from __future__ import annotations

import hashlib
import html
import json
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

from trading_system.research.trend_stage_a import (
    StageAConfig,
    StageAObservation,
    assess_stage_a,
    load_stage_a_config,
)
from trading_system.serialization import canonical_hash, deterministic_id
from trading_system.webull.short_opportunities import load_short_opportunity_config


class ShadowResearchDashboardConfigError(ValueError):
    """The Phase 12J dashboard configuration is malformed or unsafe."""


@dataclass(frozen=True, slots=True)
class ShadowResearchDashboardConfig:
    database: str
    stage_a_config: str
    short_config: str
    output: str
    freshness_minutes: int
    config_hash: str
    dashboard_version: str = "12J.1.0"


@dataclass(frozen=True, slots=True)
class ShadowResearchDashboardArtifact:
    artifact_id: str
    snapshot_id: str
    output_path: str
    content_hash: str
    status: str
    dashboard_version: str = "12J.1.0"
    mode: str = "READ_ONLY_SHADOW_RESEARCH"
    database_write_performed: bool = False
    network_used: bool = False
    credentials_loaded: bool = False
    broker_write_performed: bool = False
    live_trading_enabled: bool = False
    automatic_promotion_enabled: bool = False


def load_shadow_research_dashboard_config(
    path: str | Path,
) -> ShadowResearchDashboardConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "dashboard_version",
        "mode",
        "database",
        "stage_a_config",
        "short_config",
        "output",
        "freshness_minutes",
        "authority",
    }
    authority = {
        "database_read_enabled": True,
        "artifact_write_enabled": True,
        "network_enabled": False,
        "credential_loading_enabled": False,
        "broker_writes_enabled": False,
        "live_trading_enabled": False,
        "automatic_promotion_enabled": False,
    }
    freshness = raw.get("freshness_minutes") if isinstance(raw, dict) else None
    if (
        not isinstance(raw, dict)
        or set(raw) != expected
        or raw["dashboard_version"] != "12J.1.0"
        or raw["mode"] != "READ_ONLY_SHADOW_RESEARCH"
        or raw["authority"] != authority
        or any(
            not _relative(raw.get(name))
            for name in ("database", "stage_a_config", "short_config", "output")
        )
        or not str(raw["output"]).endswith(".html")
        or isinstance(freshness, bool)
        or not isinstance(freshness, int)
        or not 1 <= freshness <= 10_080
    ):
        raise ShadowResearchDashboardConfigError(
            "Phase 12J dashboard configuration is invalid or unsafe"
        )
    return ShadowResearchDashboardConfig(
        str(raw["database"]),
        str(raw["stage_a_config"]),
        str(raw["short_config"]),
        str(raw["output"]),
        freshness,
        canonical_hash(_freeze(raw)),
    )


def render_shadow_research_dashboard(
    config: ShadowResearchDashboardConfig,
    *,
    project_root: str | Path,
    as_of: datetime,
    database_override: str | Path | None = None,
) -> tuple[ShadowResearchDashboardArtifact, Mapping[str, object]]:
    """Render one deterministic HTML snapshot without mutating source evidence."""
    _utc(as_of)
    root = Path(project_root).resolve()
    database = _contained(root, config.database if database_override is None else database_override)
    stage_config = load_stage_a_config(_contained(root, config.stage_a_config))
    short_config = load_short_opportunity_config(_contained(root, config.short_config))
    if not database.is_file():
        raise FileNotFoundError(f"Phase 12J database does not exist: {database}")
    with sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True) as connection:
        tables = _tables(connection)
        freshness = _freshness(
            connection,
            tables,
            short_config.universe,
            as_of,
            config.freshness_minutes,
        )
        stage_a = _stage_a(connection, tables, short_config.universe, as_of, stage_config)
        short = _short_evidence(connection, tables, as_of)
    stale = sum(item["status"] != "CURRENT" for item in freshness)
    status = "GREEN" if stale == 0 else "AMBER"
    if short["unsafe_evidence"]:
        status = "RED"
    body = {
        "as_of": as_of,
        "status": status,
        "plan_id": short_config.plan_id,
        "universe": short_config.universe,
        "freshness": freshness,
        "stage_a": stage_a,
        "short_research": short,
        "safety": {
            "database_write_performed": False,
            "network_used": False,
            "credentials_loaded": False,
            "broker_write_performed": False,
            "live_trading_enabled": False,
            "automatic_promotion_enabled": False,
            "release_authorized": False,
        },
        "config_hash": config.config_hash,
        "database_sha256": _sha256_file(database),
    }
    snapshot_id = deterministic_id("shadow_research_dashboard_snapshot", body)
    snapshot: Mapping[str, object] = MappingProxyType({**body, "snapshot_id": snapshot_id})
    content = _html(snapshot)
    output = _contained(root, config.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(output)
    artifact = ShadowResearchDashboardArtifact(
        deterministic_id(
            "shadow_research_dashboard_artifact",
            (snapshot_id, config.config_hash, canonical_hash(content)),
        ),
        snapshot_id,
        str(output),
        canonical_hash(content),
        status,
    )
    return artifact, snapshot


def _sha256_file(path: Path, *, chunk_size: int = 8 * 1024 * 1024) -> str:
    """Hash a potentially large file without loading it into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _freshness(
    connection: sqlite3.Connection,
    tables: set[str],
    universe: tuple[str, ...],
    as_of: datetime,
    freshness_minutes: int,
) -> tuple[Mapping[str, object], ...]:
    if "candles" not in tables:
        return tuple(
            MappingProxyType({"symbol": symbol, "latest_1h_close": None, "status": "MISSING"})
            for symbol in universe
        )
    result: list[Mapping[str, object]] = []
    for symbol in universe:
        row = connection.execute(
            """SELECT MAX(close_time),COUNT(*) FROM candles
               WHERE symbol=? AND timeframe='1h' AND is_complete=1 AND close_time<=?""",
            (symbol, _time(as_of)),
        ).fetchone()
        latest = _parse_time(row[0]) if row and row[0] is not None else None
        status = "MISSING" if latest is None else "CURRENT"
        if latest is not None and (as_of - latest).total_seconds() > 60 * freshness_minutes:
            status = "STALE"
        result.append(
            MappingProxyType(
                {
                    "symbol": symbol,
                    "latest_1h_close": latest,
                    "bars": int(row[1]) if row else 0,
                    "status": status,
                }
            )
        )
    return tuple(result)


def _stage_a(
    connection: sqlite3.Connection,
    tables: set[str],
    universe: tuple[str, ...],
    as_of: datetime,
    config: StageAConfig,
) -> tuple[Mapping[str, object], ...]:
    if "candles" not in tables:
        return ()
    result: list[Mapping[str, object]] = []
    for symbol in universe:
        rows = connection.execute(
            """SELECT session_date,close_time,open,high,low,close,volume FROM candles
               WHERE symbol=? AND timeframe='1d' AND is_complete=1 AND close_time<=?
               ORDER BY close_time DESC,candle_id DESC LIMIT 60""",
            (symbol, _time(as_of)),
        ).fetchall()
        rows.reverse()
        if len(rows) < 50:
            result.append(MappingProxyType({"symbol": symbol, "state": "INSUFFICIENT_DAILY_DATA"}))
            continue
        closes = [Decimal(str(row[5])) for row in rows]
        volumes = [Decimal(str(row[6])) for row in rows]
        latest = rows[-1]
        average_volume = sum(volumes[-21:-1], Decimal(0)) / Decimal(20)
        recent_volume_surge = volumes[-1] / average_volume if average_volume > 0 else Decimal(0)
        high_20 = max(Decimal(str(row[3])) for row in rows[-20:])
        close = closes[-1]
        adr = sum(
            (Decimal(str(row[3])) - Decimal(str(row[4]))) / Decimal(str(row[5]))
            for row in rows[-20:]
        ) / Decimal(20) * Decimal(100)
        previous = closes[-2]
        gap = (Decimal(str(latest[2])) - previous) / previous * Decimal(100)
        observation = StageAObservation(
            symbol,
            date.fromisoformat(str(latest[0])),
            _parse_time(latest[1]),
            close,
            _ema(closes, 8),
            _ema(closes, 21),
            _ema(closes, 50),
            recent_volume_surge,
            (close - high_20) / high_20 * Decimal(100),
            adr,
            gap,
        )
        assessment = assess_stage_a(observation, config)
        result.append(
            MappingProxyType(
                {
                    "symbol": symbol,
                    "known_at": observation.known_at,
                    "state": assessment.state.value,
                    "entry_eligible": assessment.entry_eligible,
                    "volume_band": assessment.volume_band.value,
                    "vs_ema8_pct": assessment.vs_ema8_pct,
                    "reason_codes": assessment.reason_codes,
                }
            )
        )
    return tuple(result)


def _short_evidence(
    connection: sqlite3.Connection, tables: set[str], as_of: datetime
) -> Mapping[str, object]:
    states = {name: 0 for name in ("WATCH", "ARMED", "TRIGGER", "TOO_LATE")}
    latest_regime: Mapping[str, object] | None = None
    alerts: tuple[Mapping[str, object], ...] = ()
    outcomes: tuple[Mapping[str, object], ...] = ()
    if "short_regime_snapshots" in tables:
        row = connection.execute(
            """SELECT observed_at,regime_state,bearish_benchmarks,evaluated_benchmarks,
                      bearish_breadth FROM short_regime_snapshots WHERE observed_at<=?
               ORDER BY observed_at DESC,snapshot_id DESC LIMIT 1""",
            (_time(as_of),),
        ).fetchone()
        if row:
            latest_regime = MappingProxyType(
                {
                    "observed_at": _parse_time(row[0]),
                    "state": str(row[1]),
                    "bearish_benchmarks": int(row[2]),
                    "evaluated_benchmarks": int(row[3]),
                    "bearish_breadth": Decimal(str(row[4])),
                }
            )
    if "short_opportunity_alerts" in tables:
        for state, count in connection.execute(
            "SELECT state,COUNT(*) FROM short_opportunity_alerts WHERE known_at<=? GROUP BY state",
            (_time(as_of),),
        ):
            states[str(state)] = int(count)
        rows = connection.execute(
            """SELECT symbol,timeframe,known_at,state,setup_quality,entry_quality,
                      reason_codes_json FROM short_opportunity_alerts WHERE known_at<=?
               ORDER BY known_at DESC,alert_id DESC LIMIT 25""",
            (_time(as_of),),
        ).fetchall()
        alerts = tuple(
            MappingProxyType(
                {
                    "symbol": str(row[0]),
                    "timeframe": str(row[1]),
                    "known_at": _parse_time(row[2]),
                    "state": str(row[3]),
                    "setup_quality": Decimal(str(row[4])),
                    "entry_quality": Decimal(str(row[5])),
                    "reason_codes": tuple(json.loads(str(row[6]))),
                }
            )
            for row in rows
        )
    if {"short_opportunity_alerts", "short_opportunity_outcomes"} <= tables:
        rows = connection.execute(
            """SELECT a.state,o.horizon_bars,COUNT(*),AVG(CAST(o.forward_return AS REAL)),
                      AVG(CAST(o.mfe_return AS REAL)),AVG(CAST(o.mae_return AS REAL))
               FROM short_opportunity_outcomes o
               JOIN short_opportunity_alerts a ON a.alert_id=o.alert_id
               WHERE o.label_available_at<=? GROUP BY a.state,o.horizon_bars
               ORDER BY a.state,o.horizon_bars""",
            (_time(as_of),),
        ).fetchall()
        outcomes = tuple(
            MappingProxyType(
                {
                    "state": str(row[0]),
                    "horizon_bars": int(row[1]),
                    "samples": int(row[2]),
                    "average_forward_return": Decimal(str(row[3])),
                    "average_mfe_return": Decimal(str(row[4])),
                    "average_mae_return": Decimal(str(row[5])),
                }
            )
            for row in rows
        )
    return MappingProxyType(
        {
            "latest_regime": latest_regime,
            "state_counts": MappingProxyType(states),
            "latest_alerts": alerts,
            "outcomes": outcomes,
            "unsafe_evidence": False,
        }
    )


def _html(snapshot: Mapping[str, object]) -> str:
    freshness = snapshot["freshness"]
    stage_a = snapshot["stage_a"]
    short = snapshot["short_research"]
    assert isinstance(freshness, Sequence) and isinstance(stage_a, Sequence)
    assert isinstance(short, Mapping)
    counts = short["state_counts"]
    assert isinstance(counts, Mapping)
    cards = "".join(
        f"<article><b>{html.escape(str(name))}</b><strong>{int(counts[name])}</strong></article>"
        for name in ("WATCH", "ARMED", "TRIGGER", "TOO_LATE")
    )
    freshness_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item['symbol']))}</td>"
        f"<td>{html.escape(str(item.get('latest_1h_close') or '—'))}</td>"
        f"<td class='{str(item['status']).lower()}'>{html.escape(str(item['status']))}</td>"
        "</tr>"
        for item in freshness
        if isinstance(item, Mapping)
    )
    stage_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item['symbol']))}</td>"
        f"<td>{html.escape(str(item['state']))}</td>"
        f"<td>{'YES' if item.get('entry_eligible') else 'NO'}</td>"
        f"<td>{html.escape(', '.join(str(value) for value in item.get('reason_codes', ())))}</td>"
        "</tr>"
        for item in stage_a
        if isinstance(item, Mapping)
    )
    outcome_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item['state']))}</td><td>{int(item['horizon_bars'])}</td>"
        f"<td>{int(item['samples'])}</td>"
        f"<td>{_pct(item['average_forward_return'])}</td>"
        f"<td>{_pct(item['average_mfe_return'])}</td>"
        f"<td>{_pct(item['average_mae_return'])}</td></tr>"
        for item in short["outcomes"]
        if isinstance(item, Mapping)
    )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Trading System Research</title>
<style>
body{{font:15px system-ui;background:#0b1220;color:#e8eef9;margin:0;padding:28px}}
h1,h2{{margin:.2em 0}}
.muted{{color:#9aabc4}}
.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:20px 0}}
article{{background:#152238;border:1px solid #29405f;border-radius:12px;padding:16px}}
article strong{{display:block;font-size:30px;margin-top:8px}}
table{{width:100%;border-collapse:collapse;background:#111d30;margin:12px 0 28px}}
th,td{{padding:10px;border-bottom:1px solid #263a55;text-align:left}}
.green,.current{{color:#55d98d}}
.amber,.stale{{color:#ffd166}}
.red,.missing{{color:#ff6b6b}}
.safety{{padding:12px;background:#183125;border-radius:10px}}
</style></head><body>
<h1>Shadow Research Dashboard</h1>
<p class="muted">As of {html.escape(str(snapshot['as_of']))} · Phase 12J · read-only</p>
<h2 class="{str(snapshot['status']).lower()}">{html.escape(str(snapshot['status']))}</h2>
<div class="cards">{cards}</div>
<h2>Data freshness</h2>
<table><tr><th>Symbol</th><th>Latest completed 1H bar</th><th>Status</th></tr>
{freshness_rows}</table>
<h2>Stage A trend research</h2>
<table><tr><th>Symbol</th><th>State</th><th>Entry eligible</th><th>Reasons</th></tr>
{stage_rows}</table>
<h2>Short research outcomes</h2>
<table><tr><th>State</th><th>Horizon</th><th>Samples</th><th>Avg return</th>
<th>Avg MFE</th><th>Avg MAE</th></tr>{outcome_rows}</table>
<p class="safety">Research only. No credentials loaded, network used, broker write,
live trading, or automatic promotion.</p>
</body></html>"""


def _ema(values: list[Decimal], period: int) -> Decimal:
    alpha = Decimal(2) / Decimal(period + 1)
    result = values[0]
    for value in values[1:]:
        result = value * alpha + result * (Decimal(1) - alpha)
    return result


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }


def _relative(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and not Path(value).is_absolute()
        and ".." not in Path(value).parts
    )


def _contained(root: Path, value: str | Path) -> Path:
    candidate = (root / value).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("Phase 12J path escapes the project root")
    return candidate


def _utc(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("Phase 12J as_of must be UTC")


def _time(value: datetime) -> str:
    _utc(value)
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_time(value: object) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)


def _pct(value: object) -> str:
    return f"{Decimal(str(value)) * Decimal(100):.2f}%"


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value
