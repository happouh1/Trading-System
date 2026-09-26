from __future__ import annotations

import json
from dataclasses import replace

import pytest

from tests.unit.test_prospective_controls import inputs
from trading_system.execution_sim.prospective_evidence import (
    SCHEMA_VERSION,
    PointInTimeEvidence,
    corroborate_prospective_inputs,
    load_point_in_time_evidence,
)


def evidence_bytes(
    kind: str, source: str, authority: str, known_at: str, *,
    equity: str = "100000", adv: str = "10000000",
) -> bytes:
    payload: dict[str, object]
    if kind == "PORTFOLIO":
        payload = {
            "portfolio_id": "prospective-portfolio", "equity": equity,
            "positions": [], "pending_symbols": [],
        }
    else:
        payload = {
            "symbol": "MSFT", "average_daily_dollar_volume": adv,
            "sector": "TECHNOLOGY",
        }
    return json.dumps({
        "schema_version": SCHEMA_VERSION, "evidence_kind": kind,
        "source_id": source, "source_authority": authority,
        "source_revision": f"{source}-r1", "known_at": known_at,
        "payload": payload,
    }, separators=(",", ":")).encode()


def records() -> tuple[
    PointInTimeEvidence, PointInTimeEvidence, PointInTimeEvidence, PointInTimeEvidence,
]:
    _, assessment, _, _ = inputs()
    known = assessment.known_at.isoformat()
    values = tuple(load_point_in_time_evidence(evidence_bytes(*args, known)) for args in (
        ("PORTFOLIO", "broker-export", "broker"),
        ("PORTFOLIO", "local-ledger", "operator-ledger"),
        ("MARKET", "feed-primary", "vendor-a"),
        ("MARKET", "feed-secondary", "vendor-b"),
    ))
    return values[0], values[1], values[2], values[3]


def test_exact_distinct_sources_materialize_causal_inputs() -> None:
    entry, assessment, _, _ = inputs()
    p1, p2, m1, m2 = records()
    result = corroborate_prospective_inputs(
        entry=entry, entry_assessment=assessment,
        portfolio_evidence=(p1, p2), market_evidence=(m1, m2),
        planned_hold_sessions=10,
    )
    assert result.status == "EVIDENCE_CORROBORATED"
    assert result.portfolio_state.equity == 100000
    assert result.candidate.average_daily_dollar_volume == 10000000
    assert len(result.evidence_ids) == 4
    assert not result.source_authenticity_verified
    assert not result.broker_write_performed and not result.qualifying_completed_trade


def test_disagreement_alias_and_future_known_evidence_fail_closed() -> None:
    entry, assessment, _, _ = inputs()
    p1, p2, m1, m2 = records()
    changed = load_point_in_time_evidence(evidence_bytes(
        "MARKET", "feed-secondary", "vendor-b", assessment.known_at.isoformat(),
        adv="9999999",
    ))
    with pytest.raises(ValueError, match="sources disagree"):
        corroborate_prospective_inputs(
            entry=entry, entry_assessment=assessment,
            portfolio_evidence=(p1, p2), market_evidence=(m1, changed),
            planned_hold_sessions=10,
        )
    with pytest.raises(ValueError, match="authorities must be distinct"):
        corroborate_prospective_inputs(
            entry=entry, entry_assessment=assessment,
            portfolio_evidence=(p1, replace(p2, source_authority=p1.source_authority)),
            market_evidence=(m1, m2), planned_hold_sessions=10,
        )
    with pytest.raises(ValueError, match="exact entry receipt"):
        corroborate_prospective_inputs(
            entry=entry, entry_assessment=assessment,
            portfolio_evidence=(p1, replace(p2, known_at=entry.recorded_at)),
            market_evidence=(m1, m2), planned_hold_sessions=10,
        )


def test_parser_is_strict_and_hashes_exact_source_bytes() -> None:
    _, assessment, _, _ = inputs()
    raw = evidence_bytes(
        "MARKET", "feed-primary", "vendor-a", assessment.known_at.isoformat(),
    )
    parsed = load_point_in_time_evidence(raw)
    assert parsed.source_bytes_hash.startswith("sha256:")
    changed = json.loads(raw)
    changed["extra"] = True
    with pytest.raises(ValueError, match="envelope keys"):
        load_point_in_time_evidence(json.dumps(changed).encode())
