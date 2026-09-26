"""Strict point-in-time evidence boundary for offline prospective controls."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from typing import Literal, cast

from trading_system.domain import Direction
from trading_system.execution_sim.prospective import EntryAssessment, ProspectiveEntry
from trading_system.portfolio import (
    PortfolioCandidate,
    PortfolioPosition,
    PortfolioState,
    StrategyClass,
)
from trading_system.serialization import canonical_hash, deterministic_id

EvidenceKind = Literal["PORTFOLIO", "MARKET"]
SCHEMA_VERSION = "PROSPECTIVE_POINT_IN_TIME_EVIDENCE.1.0"


def _utc(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be UTC")


def _decimal(value: object, name: str, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"{name} must be numeric")
    try:
        result = Decimal(str(value))
    except ArithmeticError as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not result.is_finite() or result < 0 or (positive and result == 0):
        raise ValueError(f"{name} must be finite and {'positive' if positive else 'nonnegative'}")
    return result


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonempty text")
    return value.strip()


def _timestamp(value: object, name: str) -> datetime:
    text = _text(value, name)
    try:
        result = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO timestamp") from exc
    _utc(result, name)
    return result


@dataclass(frozen=True, slots=True)
class PointInTimeEvidence:
    evidence_kind: EvidenceKind
    source_id: str
    source_authority: str
    source_revision: str
    known_at: datetime
    normalized_payload: Mapping[str, object]
    source_bytes_hash: str
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _utc(self.known_at, "evidence known_at")
        if (
            self.evidence_kind not in {"PORTFOLIO", "MARKET"}
            or not all((self.source_id, self.source_authority, self.source_revision))
            or not self.source_bytes_hash.startswith("sha256:")
            or len(self.source_bytes_hash) != 71
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("invalid point-in-time evidence identity")
        object.__setattr__(self, "normalized_payload", _freeze(self.normalized_payload))

    @property
    def evidence_id(self) -> str:
        return deterministic_id(
            "prospective_point_in_time_evidence",
            (self.evidence_kind, self.source_id, self.source_revision, self.known_at),
        )

    @property
    def normalized_hash(self) -> str:
        return canonical_hash(self.normalized_payload)


def load_point_in_time_evidence(raw_bytes: bytes) -> PointInTimeEvidence:
    """Parse exact source bytes; no source-authenticity claim is made."""
    try:
        raw = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("evidence must be UTF-8 JSON") from exc
    common = {
        "schema_version", "evidence_kind", "source_id", "source_authority",
        "source_revision", "known_at", "payload",
    }
    if not isinstance(raw, dict) or set(raw) != common:
        raise ValueError("evidence envelope keys are invalid")
    if raw["schema_version"] != SCHEMA_VERSION:
        raise ValueError("unsupported evidence schema")
    kind = raw["evidence_kind"]
    if kind not in {"PORTFOLIO", "MARKET"}:
        raise ValueError("unsupported evidence kind")
    payload = raw["payload"]
    if not isinstance(payload, dict):
        raise ValueError("evidence payload must be an object")
    normalized = (
        _normalize_portfolio(payload) if kind == "PORTFOLIO" else _normalize_market(payload)
    )
    return PointInTimeEvidence(
        cast(EvidenceKind, kind), _text(raw["source_id"], "source_id"),
        _text(raw["source_authority"], "source_authority"),
        _text(raw["source_revision"], "source_revision"),
        _timestamp(raw["known_at"], "known_at"), normalized,
        "sha256:" + hashlib.sha256(raw_bytes).hexdigest(),
    )


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _normalize_portfolio(payload: dict[str, object]) -> dict[str, object]:
    if set(payload) != {"portfolio_id", "equity", "positions", "pending_symbols"}:
        raise ValueError("portfolio evidence keys are invalid")
    positions = payload["positions"]
    pending = payload["pending_symbols"]
    if not isinstance(positions, list) or not isinstance(pending, list):
        raise ValueError("portfolio positions and pending_symbols must be arrays")
    normalized_positions: list[dict[str, object]] = []
    required = {
        "position_id", "symbol", "direction", "quantity", "mark_price",
        "stop_price", "sector", "strategy_class",
    }
    for item in positions:
        if not isinstance(item, dict) or set(item) != required:
            raise ValueError("portfolio position keys are invalid")
        symbol = _text(item["symbol"], "position symbol").upper()
        normalized_positions.append({
            "position_id": _text(item["position_id"], "position_id"),
            "symbol": symbol,
            "direction": Direction(_text(item["direction"], "direction")).value,
            "quantity": format(_decimal(item["quantity"], "quantity", positive=True), "f"),
            "mark_price": format(_decimal(item["mark_price"], "mark_price", positive=True), "f"),
            "stop_price": format(_decimal(item["stop_price"], "stop_price", positive=True), "f"),
            "sector": _text(item["sector"], "sector"),
            "strategy_class": StrategyClass(
                _text(item["strategy_class"], "strategy_class")
            ).value,
        })
    normalized_positions.sort(key=lambda item: (str(item["symbol"]), str(item["position_id"])))
    symbols = sorted(_text(value, "pending symbol").upper() for value in pending)
    return {
        "portfolio_id": _text(payload["portfolio_id"], "portfolio_id"),
        "equity": format(_decimal(payload["equity"], "equity", positive=True), "f"),
        "positions": normalized_positions,
        "pending_symbols": symbols,
    }


def _normalize_market(payload: dict[str, object]) -> dict[str, object]:
    if set(payload) != {"symbol", "average_daily_dollar_volume", "sector"}:
        raise ValueError("market evidence keys are invalid")
    return {
        "symbol": _text(payload["symbol"], "symbol").upper(),
        "average_daily_dollar_volume": format(
            _decimal(payload["average_daily_dollar_volume"], "average_daily_dollar_volume"),
            "f",
        ),
        "sector": _text(payload["sector"], "sector"),
    }


@dataclass(frozen=True, slots=True)
class CorroboratedProspectiveInputs:
    receipt_id: str
    decision_id: str
    known_at: datetime
    portfolio_state: PortfolioState
    candidate: PortfolioCandidate
    evidence_ids: tuple[str, ...]
    source_bytes_hashes: tuple[str, ...]
    normalized_hashes: tuple[str, str]
    status: str = "EVIDENCE_CORROBORATED"
    source_authenticity_verified: bool = field(default=False, init=False)
    broker_write_performed: bool = field(default=False, init=False)
    qualifying_completed_trade: bool = field(default=False, init=False)


def corroborate_prospective_inputs(
    *, entry: ProspectiveEntry, entry_assessment: EntryAssessment,
    portfolio_evidence: tuple[PointInTimeEvidence, PointInTimeEvidence],
    market_evidence: tuple[PointInTimeEvidence, PointInTimeEvidence],
    planned_hold_sessions: int,
) -> CorroboratedProspectiveInputs:
    """Require exact agreement between two distinct authorities for each evidence kind."""
    if (
        entry_assessment.decision_id != entry.decision_id
        or entry_assessment.status != "ENTRY_MODELLED"
        or entry_assessment.fill_price is None
        or not isinstance(planned_hold_sessions, int)
        or isinstance(planned_hold_sessions, bool)
        or planned_hold_sessions <= 0
    ):
        raise ValueError("corroboration requires a modelled entry and positive hold horizon")
    all_evidence = (*portfolio_evidence, *market_evidence)
    if any(item.known_at != entry_assessment.known_at for item in all_evidence):
        raise ValueError("all evidence must share the exact entry receipt known_at")
    if any(item.evidence_kind != "PORTFOLIO" for item in portfolio_evidence):
        raise ValueError("two portfolio evidence records are required")
    if any(item.evidence_kind != "MARKET" for item in market_evidence):
        raise ValueError("two market evidence records are required")
    for pair in (portfolio_evidence, market_evidence):
        if len({item.source_id for item in pair}) != 2:
            raise ValueError("corroborating source IDs must be distinct")
        if len({item.source_authority for item in pair}) != 2:
            raise ValueError("corroborating source authorities must be distinct")
        if pair[0].normalized_hash != pair[1].normalized_hash:
            raise ValueError("point-in-time evidence sources disagree")
    portfolio_payload = portfolio_evidence[0].normalized_payload
    market_payload = market_evidence[0].normalized_payload
    if market_payload["symbol"] != entry.plan.symbol:
        raise ValueError("market evidence symbol does not match entry")
    position_payloads = cast(tuple[Mapping[str, object], ...], portfolio_payload["positions"])
    positions = tuple(_position(item) for item in position_payloads)
    state = PortfolioState(
        str(portfolio_payload["portfolio_id"]), entry_assessment.known_at,
        Decimal(str(portfolio_payload["equity"])), positions,
        tuple(cast(list[str], portfolio_payload["pending_symbols"])),
    )
    revisions = tuple(
        (item.evidence_id, item.source_revision, item.source_bytes_hash)
        for item in sorted(all_evidence, key=lambda item: item.evidence_id)
    )
    candidate = PortfolioCandidate(
        entry.decision_id, entry.plan.plan_id, entry.plan.symbol, entry.plan.direction,
        entry_assessment.known_at, planned_hold_sessions, entry_assessment.fill_price,
        entry.plan.initial_stop, Decimal(1),
        Decimal(str(market_payload["average_daily_dollar_volume"])),
        str(market_payload["sector"]), canonical_hash(revisions),
    )
    ordered_evidence = sorted(all_evidence, key=lambda item: item.evidence_id)
    evidence_ids = tuple(item.evidence_id for item in ordered_evidence)
    byte_hashes = tuple(item.source_bytes_hash for item in ordered_evidence)
    normalized_hashes = (portfolio_evidence[0].normalized_hash, market_evidence[0].normalized_hash)
    identity = (
        entry.decision_id, entry_assessment.known_at, evidence_ids, byte_hashes,
        normalized_hashes,
    )
    return CorroboratedProspectiveInputs(
        deterministic_id("prospective_evidence_receipt", identity), entry.decision_id,
        entry_assessment.known_at, state, candidate, evidence_ids, byte_hashes,
        normalized_hashes,
    )


def _position(item: Mapping[str, object]) -> PortfolioPosition:
    return PortfolioPosition(
        str(item["position_id"]), str(item["symbol"]), Direction(str(item["direction"])),
        Decimal(str(item["quantity"])), Decimal(str(item["mark_price"])),
        Decimal(str(item["stop_price"])), str(item["sector"]),
        StrategyClass(str(item["strategy_class"])),
    )
