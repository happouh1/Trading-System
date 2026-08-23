"""Append-only Phase 3A SQLite model registry."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from trading_system.modeling.artifacts import ArtifactRecord
from trading_system.modeling.contracts import ModelExperiment, ModelPrediction, ModelStage
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id

_NEXT = {
    ModelStage.DEFINED: ModelStage.TRAINED,
    ModelStage.TRAINED: ModelStage.VALIDATION_EVALUATED,
    ModelStage.VALIDATION_EVALUATED: ModelStage.FROZEN,
    ModelStage.FROZEN: ModelStage.TEST_EVALUATED,
    ModelStage.TEST_EVALUATED: ModelStage.COMPLETE,
}


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("model registry times must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


class ModelRegistry:
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
                f"SELECT payload_hash FROM {table} WHERE {identity_column} = ?", (identity,)
            ).fetchone()
            if stored != (payload_hash,):
                raise ValueError(f"conflicting {table} payload: {identity}")
            return False
        self.repository.connection.commit()
        return True

    def insert_experiment(self, item: ModelExperiment) -> bool:
        return self._insert(
            "model_experiments",
            "model_experiment_id",
            item.model_experiment_id,
            ("model_experiment_id", "research_experiment_id", "created_at"),
            (item.model_experiment_id, item.research_experiment_id, _time(item.created_at)),
            item,
        )

    def insert_lineage(
        self, model_experiment_id: str, parent_model_experiment_id: str, reason: str
    ) -> bool:
        if not reason:
            raise ValueError("model lineage reason is required")
        payload = {
            "model_experiment_id": model_experiment_id,
            "parent_model_experiment_id": parent_model_experiment_id,
            "reason": reason,
        }
        return self._insert(
            "model_experiment_lineage",
            "model_experiment_id",
            model_experiment_id,
            ("model_experiment_id", "parent_model_experiment_id", "reason"),
            (model_experiment_id, parent_model_experiment_id, reason),
            payload,
        )

    def experiment_manifest(self, model_experiment_id: str) -> dict[str, object]:
        row = self.repository.connection.execute(
            "SELECT payload_json FROM model_experiments WHERE model_experiment_id = ?",
            (model_experiment_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown model experiment: {model_experiment_id}")
        value = json.loads(str(row[0]))
        if not isinstance(value, dict):
            raise ValueError("stored model experiment is invalid")
        return {str(key): item for key, item in value.items()}

    def current_stage(self, model_experiment_id: str) -> ModelStage:
        exists = self.repository.connection.execute(
            "SELECT 1 FROM model_experiments WHERE model_experiment_id = ?",
            (model_experiment_id,),
        ).fetchone()
        if exists is None:
            raise ValueError(f"unknown model experiment: {model_experiment_id}")
        row = self.repository.connection.execute(
            """SELECT new_stage FROM model_transitions WHERE model_experiment_id = ?
               ORDER BY CASE new_stage WHEN 'TRAINED' THEN 1
                 WHEN 'VALIDATION_EVALUATED' THEN 2 WHEN 'FROZEN' THEN 3
                 WHEN 'TEST_EVALUATED' THEN 4 WHEN 'COMPLETE' THEN 5 ELSE 0 END DESC LIMIT 1""",
            (model_experiment_id,),
        ).fetchone()
        return ModelStage.DEFINED if row is None else ModelStage(str(row[0]))

    def transition(
        self,
        model_experiment_id: str,
        new_stage: ModelStage,
        occurred_at: datetime,
        *,
        frozen_manifest_hash: str | None = None,
    ) -> bool:
        prior = self.current_stage(model_experiment_id)
        if _NEXT.get(prior) is not new_stage:
            raise ValueError("invalid model lifecycle transition")
        if new_stage is ModelStage.FROZEN and not frozen_manifest_hash:
            raise ValueError("model freeze requires a manifest hash")
        identity = (model_experiment_id, prior, new_stage, occurred_at, frozen_manifest_hash)
        transition_id = deterministic_id("model_transition", identity)
        payload = {
            "transition_id": transition_id,
            "model_experiment_id": model_experiment_id,
            "prior_stage": prior,
            "new_stage": new_stage,
            "occurred_at": occurred_at,
            "frozen_manifest_hash": frozen_manifest_hash,
        }
        return self._insert(
            "model_transitions",
            "transition_id",
            transition_id,
            (
                "transition_id",
                "model_experiment_id",
                "prior_stage",
                "new_stage",
                "occurred_at",
                "frozen_manifest_hash",
            ),
            (
                transition_id,
                model_experiment_id,
                prior.value,
                new_stage.value,
                _time(occurred_at),
                frozen_manifest_hash,
            ),
            payload,
        )

    def insert_artifact(
        self,
        model_experiment_id: str,
        fold_id: str,
        estimator_kind: str,
        record: ArtifactRecord,
        manifest: dict[str, object],
    ) -> bool:
        payload = {
            "model_experiment_id": model_experiment_id,
            "fold_id": fold_id,
            "estimator_kind": estimator_kind,
            "record": record,
            "manifest": manifest,
        }
        return self._insert(
            "model_fold_artifacts",
            "artifact_id",
            record.artifact_id,
            (
                "artifact_id",
                "model_experiment_id",
                "fold_id",
                "estimator_kind",
                "artifact_path",
                "artifact_hash",
                "manifest_json",
            ),
            (
                record.artifact_id,
                model_experiment_id,
                fold_id,
                estimator_kind,
                record.path,
                record.artifact_hash,
                canonical_json(manifest),
            ),
            payload,
        )

    def artifact(self, model_experiment_id: str, fold_id: str) -> ArtifactRecord:
        row = self.repository.connection.execute(
            """SELECT artifact_id, artifact_path, artifact_hash, manifest_json
               FROM model_fold_artifacts
               WHERE model_experiment_id = ? AND fold_id = ?
                 AND estimator_kind = 'L2_LOGISTIC_REGRESSION'""",
            (model_experiment_id, fold_id),
        ).fetchone()
        if row is None:
            raise ValueError(f"model artifact not found for fold: {fold_id}")
        return ArtifactRecord(
            str(row[0]),
            str(row[1]),
            str(row[2]),
            canonical_hash(json.loads(str(row[3]))),
        )

    def artifact_manifest(self, artifact_id: str) -> dict[str, object]:
        row = self.repository.connection.execute(
            "SELECT manifest_json FROM model_fold_artifacts WHERE artifact_id = ?",
            (artifact_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown artifact: {artifact_id}")
        value = json.loads(str(row[0]))
        if not isinstance(value, dict):
            raise ValueError("stored artifact manifest is invalid")
        return {str(key): item for key, item in value.items()}

    def insert_prediction(self, item: ModelPrediction) -> bool:
        return self._insert(
            "model_predictions",
            "prediction_id",
            item.prediction_id,
            (
                "prediction_id",
                "model_experiment_id",
                "artifact_id",
                "observation_id",
                "fold_id",
                "partition",
                "known_at",
                "probability",
            ),
            (
                item.prediction_id,
                item.model_experiment_id,
                item.artifact_id,
                item.observation_id,
                item.fold_id,
                item.partition,
                _time(item.known_at),
                item.probability,
            ),
            item,
        )

    def insert_metric(
        self,
        model_experiment_id: str,
        fold_id: str,
        partition: str,
        estimator_kind: str,
        known_at: datetime,
        payload: object,
    ) -> bool:
        metric_id = deterministic_id(
            "model_metric", (model_experiment_id, fold_id, partition, estimator_kind)
        )
        return self._insert(
            "model_metrics",
            "metric_id",
            metric_id,
            (
                "metric_id",
                "model_experiment_id",
                "fold_id",
                "partition",
                "estimator_kind",
                "known_at",
            ),
            (
                metric_id,
                model_experiment_id,
                fold_id,
                partition,
                estimator_kind,
                _time(known_at),
            ),
            payload,
        )

    def insert_exclusion(
        self, model_experiment_id: str, row_id: str, reason: str
    ) -> bool:
        exclusion_id = deterministic_id("model_exclusion", (model_experiment_id, row_id, reason))
        payload = {
            "model_experiment_id": model_experiment_id,
            "row_id": row_id,
            "reason": reason,
        }
        return self._insert(
            "model_exclusions",
            "exclusion_id",
            exclusion_id,
            ("exclusion_id", "model_experiment_id", "row_id", "reason"),
            (exclusion_id, model_experiment_id, row_id, reason),
            payload,
        )

    def insert_report(
        self,
        model_experiment_id: str,
        stage: ModelStage,
        created_at: datetime,
        payload: object,
    ) -> bool:
        report_id = deterministic_id(
            "model_report", (model_experiment_id, stage, created_at, payload)
        )
        return self._insert(
            "model_reports",
            "report_id",
            report_id,
            ("report_id", "model_experiment_id", "stage", "created_at"),
            (report_id, model_experiment_id, stage.value, _time(created_at)),
            payload,
        )
