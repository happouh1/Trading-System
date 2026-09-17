"""Fail-closed candidate-evidence coverage for the future replacement burn-in."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from trading_system.desktop.dual_source_trade_evidence import (
    TradeEvidenceCandidate,
    TradeEvidenceCandidateRegistry,
    TradeEvidenceSource,
)
from trading_system.paper import PaperMode, PaperRegistry, PaperSession
from trading_system.persistence import SQLiteRepository

START = datetime(2026, 10, 12, 13, 30, tzinfo=UTC)
SHA = "sha256:" + "a" * 64
MODEL = "sha256:" + "b" * 64
PLAN = "replacement-plan-not-yet-approved"


def _candidate(
    source: str = "WEBULL_SANDBOX", *, trade_id: str = "trade-1"
) -> TradeEvidenceCandidate:
    return TradeEvidenceCandidate(
        plan_id=PLAN,
        session_id="candidate-session",
        decision_id="decision-1",
        source=source,  # type: ignore[arg-type]
        source_trade_id=trade_id,
        entry_known_at=START + timedelta(hours=1),
        exit_known_at=START + timedelta(hours=2),
        recorded_at=START + timedelta(hours=3),
        source_record_hash=SHA,
        config_hash=SHA,
        code_version="git:test",
        simulation_model_hash=MODEL if source == "SHADOW_SIMULATED" else None,
    )


def _repository(tmp_path: Path) -> SQLiteRepository:
    repository = SQLiteRepository(tmp_path / "candidates.sqlite")
    repository.migrate()
    PaperRegistry(repository).insert_session(
        PaperSession(
            "candidate-session", START, PaperMode.SHADOW, "git:test", SHA,
            "fixture", "exchange-calendars-4",
        )
    )
    return repository


def test_candidate_identity_is_source_specific_and_cannot_qualify(tmp_path: Path) -> None:
    with _repository(tmp_path) as repository:
        registry = TradeEvidenceCandidateRegistry(repository)
        broker = _candidate()
        simulated = _candidate("SHADOW_SIMULATED")
        assert broker.candidate_id != simulated.candidate_id
        assert registry.insert(broker)
        assert registry.insert(simulated)
        assert not registry.insert(broker)
        before = registry.candidate_counts(PLAN, as_of=START + timedelta(hours=2))
        assert (before.webull_sandbox_candidates, before.shadow_simulated_candidates) == (0, 0)
        after = registry.candidate_counts(PLAN, as_of=START + timedelta(hours=3))
        assert (after.webull_sandbox_candidates, after.shadow_simulated_candidates) == (1, 1)
        assert after.required_webull_sandbox_trades == 10
        assert after.required_shadow_simulated_trades == 10
        assert not after.qualification_performed
        with pytest.raises(ValueError, match="invalid unqualified candidate counts"):
            replace(after, qualification_performed=True)


def test_candidate_restart_is_idempotent_and_conflict_fails(tmp_path: Path) -> None:
    path = tmp_path / "candidates.sqlite"
    with _repository(tmp_path) as repository:
        assert TradeEvidenceCandidateRegistry(repository).insert(_candidate())
    with SQLiteRepository(path) as repository:
        registry = TradeEvidenceCandidateRegistry(repository)
        assert not registry.insert(_candidate())
        with pytest.raises(ValueError, match="conflicting"):
            registry.insert(replace(_candidate(), decision_id="changed-decision"))
        report = registry.candidate_counts(PLAN, as_of=START + timedelta(days=1))
        assert report.webull_sandbox_candidates == 1


def test_invalid_candidate_is_rejected() -> None:
    with pytest.raises(ValueError, match="invalid unqualified"):
        replace(_candidate(), source=cast(TradeEvidenceSource, "UNKNOWN"))
    with pytest.raises(ValueError, match="invalid unqualified"):
        replace(_candidate(), exit_known_at=START)
    with pytest.raises(ValueError, match="invalid unqualified"):
        replace(_candidate(), recorded_at=START)
    with pytest.raises(ValueError, match="invalid unqualified"):
        replace(_candidate(), source_record_hash="not-a-hash")
    with pytest.raises(ValueError, match="invalid unqualified"):
        replace(_candidate(), simulation_model_hash=MODEL)
    with pytest.raises(ValueError, match="invalid unqualified"):
        replace(_candidate(), schema_version="wrong")
    with pytest.raises(ValueError, match="invalid unqualified"):
        replace(_candidate("SHADOW_SIMULATED"), simulation_model_hash=None)


def test_orphan_session_and_future_session_are_rejected(tmp_path: Path) -> None:
    with _repository(tmp_path) as repository:
        registry = TradeEvidenceCandidateRegistry(repository)
        with pytest.raises(ValueError, match="existing causal"):
            registry.insert(replace(_candidate(), session_id="missing"))
        PaperRegistry(repository).insert_session(
            PaperSession(
                "future-session", START + timedelta(days=1), PaperMode.SHADOW,
                "git:test", SHA, "fixture", "exchange-calendars-4",
            )
        )
        with pytest.raises(ValueError, match="existing causal"):
            registry.insert(replace(_candidate(), session_id="future-session"))


def test_counts_are_plan_scoped_and_never_prove_completed_trades(tmp_path: Path) -> None:
    with _repository(tmp_path) as repository:
        registry = TradeEvidenceCandidateRegistry(repository)
        for index in range(12):
            assert registry.insert(_candidate(trade_id=f"broker-{index}"))
        report = registry.candidate_counts(PLAN, as_of=START + timedelta(days=1))
        assert report.webull_sandbox_candidates == 12
        assert report.shadow_simulated_candidates == 0
        assert not report.qualification_performed
        for index in range(10):
            assert registry.insert(_candidate("SHADOW_SIMULATED", trade_id=f"sim-{index}"))
        both = registry.candidate_counts(PLAN, as_of=START + timedelta(days=1))
        assert (both.webull_sandbox_candidates, both.shadow_simulated_candidates) == (12, 10)
        assert not both.qualification_performed
        other = registry.candidate_counts("other-plan", as_of=START + timedelta(days=1))
        assert (other.webull_sandbox_candidates, other.shadow_simulated_candidates) == (0, 0)


def test_migration_mirrors_match() -> None:
    root = Path(__file__).parents[2]
    relative = Path("090_dual_source_trade_candidates.sql")
    assert (root / "migrations" / relative).read_bytes() == (
        root / "src/trading_system/persistence/migrations" / relative
    ).read_bytes()
