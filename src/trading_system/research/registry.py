"""Append-only SQLite experiment registry built on the shared migrations."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

from trading_system.persistence import SQLiteRepository
from trading_system.research.contracts import (
    ExperimentSpec,
    HumanReview,
    UniverseMembership,
    WalkForwardFold,
)
from trading_system.research.orchestration import (
    CohortSpec,
    ExperimentStage,
    ExperimentTransition,
    FoldAssignment,
)
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id


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

    def insert_lineage(
        self, experiment_id: str, parent_experiment_id: str, reason: str
    ) -> bool:
        if not reason:
            raise ValueError("lineage reason is required")
        payload = {
            "experiment_id": experiment_id,
            "parent_experiment_id": parent_experiment_id,
            "reason": reason,
        }
        return self._insert(
            "experiment_lineage",
            "experiment_id",
            experiment_id,
            ("experiment_id", "parent_experiment_id", "reason"),
            (experiment_id, parent_experiment_id, reason),
            payload,
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

    def current_stage(self, experiment_id: str) -> ExperimentStage:
        exists = self.repository.connection.execute(
            "SELECT 1 FROM experiments WHERE experiment_id = ?", (experiment_id,)
        ).fetchone()
        if exists is None:
            raise ValueError(f"unknown experiment: {experiment_id}")
        row = self.repository.connection.execute(
            """SELECT new_stage FROM experiment_transitions
               WHERE experiment_id = ?
               ORDER BY CASE new_stage
                 WHEN 'TRAIN_EVALUATED' THEN 1 WHEN 'VALIDATION_EVALUATED' THEN 2
                 WHEN 'FROZEN' THEN 3 WHEN 'TEST_EVALUATED' THEN 4 WHEN 'COMPLETE' THEN 5
                 ELSE 0 END DESC LIMIT 1""",
            (experiment_id,),
        ).fetchone()
        return ExperimentStage.DEFINED if row is None else ExperimentStage(str(row[0]))

    def folds(self, experiment_id: str) -> tuple[WalkForwardFold, ...]:
        rows = self.repository.connection.execute(
            """SELECT payload_json FROM experiment_folds WHERE experiment_id = ?
               ORDER BY ordinal""",
            (experiment_id,),
        ).fetchall()

        def decoded_date(value: object) -> date:
            if not isinstance(value, dict):
                raise ValueError("stored fold date is invalid")
            text = value.get("__date__")
            if not isinstance(text, str):
                raise ValueError("stored fold date is invalid")
            return date.fromisoformat(text)

        result: list[WalkForwardFold] = []
        for row in rows:
            payload = json.loads(str(row[0]))
            if not isinstance(payload, dict):
                raise ValueError("stored fold payload is invalid")
            result.append(
                WalkForwardFold(
                    str(payload["fold_id"]),
                    str(payload["experiment_id"]),
                    int(payload["ordinal"]),
                    decoded_date(payload["train_start"]),
                    decoded_date(payload["train_end"]),
                    decoded_date(payload["validation_start"]),
                    decoded_date(payload["validation_end"]),
                    decoded_date(payload["test_start"]),
                    decoded_date(payload["test_end"]),
                )
            )
        return tuple(result)

    def insert_transition(self, item: ExperimentTransition) -> bool:
        if self.current_stage(item.experiment_id) is not item.prior_stage:
            raise ValueError("transition prior stage does not match persisted stage")
        return self._insert(
            "experiment_transitions",
            "transition_id",
            item.transition_id,
            ("transition_id", "experiment_id", "prior_stage", "new_stage", "occurred_at"),
            (
                item.transition_id,
                item.experiment_id,
                item.prior_stage.value,
                item.new_stage.value,
                _time(item.occurred_at),
            ),
            item,
        )

    def insert_cohort(self, item: CohortSpec) -> bool:
        if self.current_stage(item.experiment_id) in {
            ExperimentStage.FROZEN,
            ExperimentStage.TEST_EVALUATED,
            ExperimentStage.COMPLETE,
        }:
            raise ValueError("cohorts cannot change after freeze")
        return self._insert(
            "experiment_cohorts",
            "cohort_id",
            item.cohort_id,
            ("cohort_id", "experiment_id", "specification_hash"),
            (item.cohort_id, item.experiment_id, item.specification_hash),
            item,
        )

    def insert_fold_assignment(self, item: FoldAssignment) -> bool:
        return self._insert(
            "fold_assignments",
            "assignment_id",
            item.assignment_id,
            ("assignment_id", "experiment_id", "fold_id", "row_id", "partition", "reason"),
            (
                item.assignment_id,
                item.experiment_id,
                item.fold_id,
                item.row_id,
                item.partition.value,
                item.reason,
            ),
            item,
        )

    def insert_holdout(self, experiment_id: str, symbol: str, bucket: int) -> bool:
        payload = {"experiment_id": experiment_id, "symbol": symbol, "bucket": bucket}
        return self._insert(
            "symbol_holdout_assignments",
            "experiment_id || ':' || symbol",
            f"{experiment_id}:{symbol}",
            ("experiment_id", "symbol", "bucket"),
            (experiment_id, symbol, bucket),
            payload,
        )

    def insert_exclusion(self, item: FoldAssignment) -> bool:
        if item.partition.value != "EXCLUDED":
            raise ValueError("only excluded assignments may be exclusion records")
        exclusion_id = deterministic_id(
            "experiment_exclusion",
            (item.experiment_id, item.fold_id, item.row_id, item.reason),
        )
        return self._insert(
            "experiment_exclusions",
            "exclusion_id",
            exclusion_id,
            ("exclusion_id", "experiment_id", "fold_id", "row_id", "reason"),
            (
                exclusion_id,
                item.experiment_id,
                item.fold_id,
                item.row_id,
                item.reason,
            ),
            item,
        )

    def insert_checkpoint(
        self, experiment_id: str, stage: ExperimentStage, payload: object
    ) -> bool:
        checkpoint_id = deterministic_id("experiment_checkpoint", (experiment_id, stage))
        return self._insert(
            "experiment_checkpoints",
            "checkpoint_id",
            checkpoint_id,
            ("checkpoint_id", "experiment_id", "stage"),
            (checkpoint_id, experiment_id, stage.value),
            payload,
        )

    def insert_report(
        self,
        experiment_id: str,
        stage: ExperimentStage,
        created_at: datetime,
        payload: object,
    ) -> bool:
        report_id = deterministic_id(
            "experiment_report", (experiment_id, stage, created_at, payload)
        )
        return self._insert(
            "experiment_reports",
            "report_id",
            report_id,
            ("report_id", "experiment_id", "stage", "created_at"),
            (report_id, experiment_id, stage.value, _time(created_at)),
            payload,
        )
