"""Append-only SQLite experiment registry built on the shared migrations."""

from __future__ import annotations

from datetime import UTC, datetime

from trading_system.persistence import SQLiteRepository
from trading_system.research.contracts import (
    ExperimentSpec,
    HumanReview,
    UniverseMembership,
    WalkForwardFold,
)
from trading_system.serialization import canonical_hash, canonical_json


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("registry timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


class ExperimentRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def _insert(
        self,
        table: str,
        identity_column: str,
        identity: str,
        columns: tuple[str, ...],
        values: tuple[object, ...],
        payload: object,
    ) -> bool:
        payload_json = canonical_json(payload)
        payload_hash = canonical_hash(payload)
        names = (*columns, "payload_json", "payload_hash")
        placeholders = ",".join("?" for _ in names)
        cursor = self.repository.connection.execute(
            f"INSERT OR IGNORE INTO {table} ({','.join(names)}) VALUES ({placeholders})",
            (*values, payload_json, payload_hash),
        )
        if cursor.rowcount == 0:
            stored = self.repository.connection.execute(
                f"SELECT payload_hash FROM {table} WHERE {identity_column} = ?",
                (identity,),
            ).fetchone()
            if stored != (payload_hash,):
                raise ValueError(f"conflicting {table} payload: {identity}")
            return False
        self.repository.connection.commit()
        return True

    def insert_experiment(self, experiment: ExperimentSpec) -> bool:
        return self._insert(
            "experiments",
            "experiment_id",
            experiment.experiment_id,
            ("experiment_id", "created_at", "status"),
            (experiment.experiment_id, _time(experiment.created_at), experiment.status.value),
            experiment,
        )

    def insert_fold(self, fold: WalkForwardFold) -> bool:
        return self._insert(
            "experiment_folds",
            "fold_id",
            fold.fold_id,
            ("fold_id", "experiment_id", "ordinal"),
            (fold.fold_id, fold.experiment_id, fold.ordinal),
            fold,
        )

    def insert_membership(self, membership: UniverseMembership) -> bool:
        return self._insert(
            "universe_memberships",
            "membership_id",
            membership.membership_id,
            (
                "membership_id",
                "symbol",
                "effective_from",
                "effective_to",
                "source",
                "source_revision",
            ),
            (
                membership.membership_id,
                membership.symbol,
                membership.effective_from.isoformat(),
                membership.effective_to.isoformat() if membership.effective_to else None,
                membership.source,
                membership.source_revision,
            ),
            membership,
        )

    def insert_review(self, review: HumanReview) -> bool:
        return self._insert(
            "human_reviews",
            "review_id",
            review.review_id,
            (
                "review_id",
                "experiment_id",
                "observation_id",
                "reviewer_id",
                "reviewed_at",
                "verdict",
            ),
            (
                review.review_id,
                review.experiment_id,
                review.observation_id,
                review.reviewer_id,
                _time(review.reviewed_at),
                review.verdict.value,
            ),
            review,
        )

    def insert_result(
        self,
        *,
        table: str,
        result_id: str,
        experiment_id: str,
        fold_id: str,
        known_at: datetime,
        payload: object,
    ) -> bool:
        if table not in {"conditional_statistics", "calibration_results"}:
            raise ValueError("unsupported research result table")
        return self._insert(
            table,
            "result_id",
            result_id,
            ("result_id", "experiment_id", "fold_id", "known_at"),
            (result_id, experiment_id, fold_id, _time(known_at)),
            payload,
        )

    def insert_similarity_query(
        self,
        *,
        query_id: str,
        experiment_id: str,
        fold_id: str,
        known_at: datetime,
        payload: object,
    ) -> bool:
        return self._insert(
            "similarity_queries",
            "query_id",
            query_id,
            ("query_id", "experiment_id", "fold_id", "known_at"),
            (query_id, experiment_id, fold_id, _time(known_at)),
            payload,
        )

    def insert_similarity_result(
        self,
        *,
        query_id: str,
        candidate_id: str,
        rank: int,
        payload: object,
    ) -> bool:
        if rank < 1:
            raise ValueError("similarity rank must be positive")
        identity = f"{query_id}:{candidate_id}"
        return self._insert(
            "similarity_results",
            "query_id || ':' || candidate_id",
            identity,
            ("query_id", "candidate_id", "rank"),
            (query_id, candidate_id, rank),
            payload,
        )
