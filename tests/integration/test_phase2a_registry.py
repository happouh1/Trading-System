from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from trading_system.persistence import SQLiteRepository
from trading_system.research.contracts import (
    ExperimentSpec,
    HumanReview,
    ReviewVerdict,
    UniverseMembership,
    WalkForwardSpec,
)
from trading_system.research.folds import build_walk_forward_folds
from trading_system.research.registry import ExperimentRegistry


def experiment() -> ExperimentSpec:
    return ExperimentSpec(
        experiment_id="experiment-1",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        source_run_ids=("run-1",),
        code_version="code-1",
        config_hashes=("sha256:phase1",),
        data_revisions=("sha256:data",),
        calendar_versions=("XNYS-1",),
        universe_revision="sha256:universe",
        folds=WalkForwardSpec(4, 2, 2, 2, 1),
        metric_version="1.0.0",
        similarity_config_hash="sha256:similarity",
        seed=7,
    )


def test_registry_is_append_only_idempotent_and_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "research.sqlite"
    source = experiment()
    sessions = tuple(date(2026, 1, 1) + timedelta(days=index) for index in range(12))
    fold = build_walk_forward_folds(source.experiment_id, sessions, source.folds)[0]
    membership = UniverseMembership.create("AAPL", sessions[0], None, "fixture", "revision-1")
    review = HumanReview(
        "review-1",
        source.experiment_id,
        "observation-1",
        "reviewer-1",
        datetime(2026, 2, 1, tzinfo=UTC),
        ReviewVerdict.CONFIRMED,
    )
    with SQLiteRepository(database) as repository:
        repository.migrate()
        registry = ExperimentRegistry(repository)
        assert registry.insert_experiment(source)
        assert not registry.insert_experiment(source)
        assert registry.insert_fold(fold)
        assert registry.insert_membership(membership)
        assert registry.insert_review(review)
        known_at = datetime(2026, 2, 2, tzinfo=UTC)
        assert registry.insert_result(
            table="conditional_statistics",
            result_id="stat-1",
            experiment_id=source.experiment_id,
            fold_id=fold.fold_id,
            known_at=known_at,
            payload={"count": 10},
        )
        assert registry.insert_similarity_query(
            query_id="query-1",
            experiment_id=source.experiment_id,
            fold_id=fold.fold_id,
            known_at=known_at,
            payload={"observation_id": "observation-1"},
        )
        assert registry.insert_similarity_result(
            query_id="query-1",
            candidate_id="candidate-1",
            rank=1,
            payload={"distance": "0.25"},
        )
        with pytest.raises(ValueError, match="conflicting"):
            registry.insert_experiment(replace(source, seed=8))
    with SQLiteRepository(database) as repository:
        repository.migrate()
        counts = {
            table: repository.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            for table in (
                "experiments",
                "experiment_folds",
                "universe_memberships",
                "human_reviews",
                "conditional_statistics",
                "similarity_queries",
                "similarity_results",
            )
        }
    assert all(value == (1,) for value in counts.values())


def test_registry_foreign_keys_reject_orphan_fold(tmp_path: Path) -> None:
    database = tmp_path / "orphan.sqlite"
    sessions = tuple(date(2026, 1, 1) + timedelta(days=index) for index in range(12))
    fold = build_walk_forward_folds("missing", sessions, WalkForwardSpec(4, 2, 2, 2, 1))[0]
    with SQLiteRepository(database) as repository:
        repository.migrate()
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            ExperimentRegistry(repository).insert_fold(fold)
