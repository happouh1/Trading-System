"""Phase 3A model research CLI."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from trading_system.modeling.artifacts import load_artifact
from trading_system.modeling.config import ModelConfig, load_model_config
from trading_system.modeling.contracts import ModelExperiment, ModelRow, ModelStage
from trading_system.modeling.dataset import prepare_rows
from trading_system.modeling.registry import ModelRegistry
from trading_system.modeling.workflow import ModelWorkflow
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


def configure_model_parser(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    model = commands.add_parser("model")
    actions = model.add_subparsers(dest="model_command", required=True)
    define = actions.add_parser("define")
    define.add_argument("--database", required=True)
    define.add_argument("--manifest", required=True)
    define.add_argument("--config", required=True)
    define.add_argument("--dataset", required=True)
    for name in ("status", "complete"):
        parser = actions.add_parser(name)
        parser.add_argument("--database", required=True)
        parser.add_argument("--model-experiment-id", required=True)
    train = actions.add_parser("train")
    train.add_argument("--database", required=True)
    train.add_argument("--model-experiment-id", required=True)
    train.add_argument("--config", required=True)
    train.add_argument("--dataset", required=True)
    train.add_argument("--cutoff", required=True)
    train.add_argument("--artifacts", required=True)
    evaluate = actions.add_parser("evaluate")
    evaluate.add_argument("--database", required=True)
    evaluate.add_argument("--model-experiment-id", required=True)
    evaluate.add_argument("--config", required=True)
    evaluate.add_argument("--dataset", required=True)
    evaluate.add_argument("--cutoff", required=True)
    evaluate.add_argument("--partition", choices=("VALIDATION", "TEST"), required=True)
    freeze = actions.add_parser("freeze")
    freeze.add_argument("--database", required=True)
    freeze.add_argument("--model-experiment-id", required=True)
    freeze.add_argument("--manifest-hash", required=True)
    verify = actions.add_parser("verify-artifacts")
    verify.add_argument("--database", required=True)
    verify.add_argument("--model-experiment-id", required=True)
    report = actions.add_parser("report")
    report.add_argument("--database", required=True)
    report.add_argument("--model-experiment-id", required=True)
    report.add_argument("--output", required=True)
    explain = actions.add_parser("explain")
    explain.add_argument("--database", required=True)
    explain.add_argument("--prediction-id", required=True)


def _object(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("model manifest must be an object")
    return value


def _file_hash(path: str | Path) -> str:
    return f"sha256:{hashlib.sha256(Path(path).read_bytes()).hexdigest()}"


def _features(config: ModelConfig) -> tuple[tuple[str, ...], tuple[str, ...]]:
    numeric = config.values["numeric_features"]
    categorical = config.values["categorical_features"]
    if not isinstance(numeric, list) or not isinstance(categorical, list):
        raise ValueError("validated feature configuration is invalid")
    return tuple(str(item) for item in numeric), tuple(str(item) for item in categorical)


def _target_labels(config: ModelConfig) -> tuple[tuple[str, ...], tuple[str, ...]]:
    target = config.values["target"]
    if not isinstance(target, dict):
        raise ValueError("validated target configuration is invalid")
    positive = target.get("positive_labels")
    negative = target.get("negative_labels")
    if not isinstance(positive, list) or not isinstance(negative, list):
        raise ValueError("validated target labels are invalid")
    return tuple(str(item) for item in positive), tuple(str(item) for item in negative)


def _seed(config: ModelConfig) -> int:
    value = config.values["determinism"]
    if not isinstance(value, dict) or not isinstance(value.get("seed"), int):
        raise ValueError("validated model seed is invalid")
    return int(value["seed"])


def _estimator_settings(config: ModelConfig) -> tuple[float, int, int]:
    estimator = config.values["estimator"]
    calibration = config.values["calibration"]
    if not isinstance(estimator, dict) or not isinstance(calibration, dict):
        raise ValueError("validated estimator configuration is invalid")
    c_value = estimator.get("c")
    max_iter = estimator.get("max_iter")
    minimum = calibration.get("minimum_class_count")
    if isinstance(c_value, bool) or not isinstance(c_value, (int, float)) or c_value <= 0:
        raise ValueError("logistic C must be positive")
    if isinstance(max_iter, bool) or not isinstance(max_iter, int) or max_iter <= 0:
        raise ValueError("logistic max_iter must be positive")
    if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 2:
        raise ValueError("calibration class count must be at least two")
    return float(c_value), max_iter, minimum


def _bootstrap_samples(config: ModelConfig) -> int:
    value = config.values["bootstrap_samples"]
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("validated bootstrap sample count is invalid")
    return value


def _load_rows(path: str | Path) -> tuple[ModelRow, ...]:
    result: list[ModelRow] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if not isinstance(item, dict) or not isinstance(item.get("features"), dict):
            raise ValueError("model dataset rows and features must be objects")
        result.append(
            ModelRow(
                str(item["row_id"]),
                str(item["observation_id"]),
                str(item["fold_id"]),
                str(item["partition"]),
                datetime.fromisoformat(str(item["label_available_at"]).replace("Z", "+00:00")),
                str(item["outcome_label"]),
                {str(key): value for key, value in item["features"].items()},
            )
        )
    row_ids: set[str] = set()
    observation_partitions: dict[tuple[str, str], str] = {}
    for row in result:
        if row.row_id in row_ids:
            raise ValueError(f"duplicate model row_id: {row.row_id}")
        row_ids.add(row.row_id)
        key = (row.fold_id, row.observation_id)
        prior_partition = observation_partitions.setdefault(key, row.partition)
        if prior_partition != row.partition:
            raise ValueError(
                f"observation crosses partitions in fold {row.fold_id}: {row.observation_id}"
            )
    return tuple(result)


def _define(args: argparse.Namespace, registry: ModelRegistry) -> dict[str, object]:
    manifest = _object(args.manifest)
    config = load_model_config(args.config)
    dependencies = manifest.get("dependency_versions")
    if not isinstance(dependencies, dict):
        raise ValueError("dependency versions are required")
    numeric, categorical = _features(config)
    item = ModelExperiment(
        str(manifest["model_experiment_id"]),
        str(manifest["research_experiment_id"]),
        datetime.fromisoformat(str(manifest["created_at"]).replace("Z", "+00:00")),
        _file_hash(args.dataset),
        canonical_hash({"numeric": numeric, "categorical": categorical}),
        canonical_hash(config.values["target"]),
        canonical_hash(config.values["estimator"]),
        config.config_hash,
        str(manifest["code_version"]),
        {str(key): str(value) for key, value in dependencies.items()},
        _seed(config),
    )
    registry.insert_experiment(item)
    parent_id = manifest.get("parent_model_experiment_id")
    if parent_id is not None:
        registry.insert_lineage(
            item.model_experiment_id,
            str(parent_id),
            str(manifest.get("lineage_reason", "VALIDATION_DERIVED_REVISION")),
        )
    return {"model_experiment_id": item.model_experiment_id, "dataset_hash": item.dataset_hash}


def _validate_identity(
    registry: ModelRegistry,
    model_experiment_id: str,
    config: ModelConfig,
    dataset: str | Path,
) -> None:
    manifest = registry.experiment_manifest(model_experiment_id)
    if manifest.get("dataset_hash") != _file_hash(dataset):
        raise ValueError("model dataset hash does not match experiment definition")
    if manifest.get("config_hash") != config.config_hash:
        raise ValueError("model config hash does not match experiment definition")


def _prepared_by_fold(
    rows: tuple[ModelRow, ...],
    partition: str,
    config: ModelConfig,
    cutoff: datetime,
) -> dict[str, tuple[tuple[ModelRow, ...], tuple[int, ...], tuple[tuple[str, str], ...]]]:
    numeric, categorical = _features(config)
    positive, negative = _target_labels(config)
    result: dict[
        str,
        tuple[tuple[ModelRow, ...], tuple[int, ...], tuple[tuple[str, str], ...]],
    ] = {}
    fold_ids = sorted({row.fold_id for row in rows if row.partition == partition})
    for fold_id in fold_ids:
        source = tuple(
            row for row in rows if row.fold_id == fold_id and row.partition == partition
        )
        prepared = prepare_rows(
            source,
            numeric_features=numeric,
            categorical_features=categorical,
            positive_labels=positive,
            negative_labels=negative,
            cutoff=cutoff,
        )
        result[fold_id] = (prepared.rows, prepared.targets, prepared.excluded)
    return result


def _train(args: argparse.Namespace, registry: ModelRegistry) -> dict[str, object]:
    config = load_model_config(args.config)
    _validate_identity(registry, args.model_experiment_id, config, args.dataset)
    numeric, categorical = _features(config)
    cutoff = datetime.fromisoformat(str(args.cutoff).replace("Z", "+00:00"))
    groups = _prepared_by_fold(_load_rows(args.dataset), "TRAIN", config, cutoff)
    if not groups:
        raise ValueError("model training dataset has no TRAIN rows")
    workflow = ModelWorkflow(registry, args.model_experiment_id)
    c_value, max_iter, calibration_minimum = _estimator_settings(config)
    experiment_manifest = registry.experiment_manifest(args.model_experiment_id)
    for fold_id, (rows, targets, excluded) in groups.items():
        for row_id, reason in excluded:
            registry.insert_exclusion(args.model_experiment_id, row_id, reason)
        manifest = {
            "model_experiment_id": args.model_experiment_id,
            "fold_id": fold_id,
            "config_hash": config.config_hash,
            "dataset_hash": _file_hash(args.dataset),
            "numeric_features": numeric,
            "categorical_features": categorical,
            "code_version": experiment_manifest["code_version"],
            "dependency_versions": experiment_manifest["dependency_versions"],
        }
        workflow.train_fold(
            fold_id,
            rows,
            targets,
            numeric_features=numeric,
            categorical_features=categorical,
            seed=_seed(config),
            c_value=c_value,
            max_iter=max_iter,
            calibration_minimum_class_count=calibration_minimum,
            bootstrap_samples=_bootstrap_samples(config),
            artifact_directory=args.artifacts,
            manifest=manifest,
            known_at=cutoff,
        )
    registry.transition(args.model_experiment_id, ModelStage.TRAINED, cutoff)
    return {"model_experiment_id": args.model_experiment_id, "trained_folds": len(groups)}


def _evaluate(args: argparse.Namespace, registry: ModelRegistry) -> dict[str, object]:
    config = load_model_config(args.config)
    _validate_identity(registry, args.model_experiment_id, config, args.dataset)
    cutoff = datetime.fromisoformat(str(args.cutoff).replace("Z", "+00:00"))
    groups = _prepared_by_fold(_load_rows(args.dataset), args.partition, config, cutoff)
    if not groups:
        raise ValueError(f"model dataset has no {args.partition} rows")
    workflow = ModelWorkflow(registry, args.model_experiment_id)
    predictions = 0
    for fold_id, (rows, targets, excluded) in groups.items():
        for row_id, reason in excluded:
            registry.insert_exclusion(args.model_experiment_id, row_id, reason)
        predictions += workflow.evaluate_fold(
            fold_id,
            args.partition,
            rows,
            targets,
            known_at=cutoff,
            seed=_seed(config),
            bootstrap_samples=_bootstrap_samples(config),
        )
    target = (
        ModelStage.VALIDATION_EVALUATED
        if args.partition == "VALIDATION"
        else ModelStage.TEST_EVALUATED
    )
    registry.transition(args.model_experiment_id, target, cutoff)
    return {"model_experiment_id": args.model_experiment_id, "predictions": predictions}


def handle_model(args: argparse.Namespace) -> int:
    with SQLiteRepository(args.database) as repository:
        repository.migrate()
        registry = ModelRegistry(repository)
        command = args.model_command
        if command == "define":
            result = _define(args, registry)
        elif command == "status":
            result = {
                "model_experiment_id": args.model_experiment_id,
                "stage": registry.current_stage(args.model_experiment_id),
            }
        elif command == "train":
            result = _train(args, registry)
        elif command == "evaluate":
            result = _evaluate(args, registry)
        elif command == "freeze":
            expected_hash = canonical_hash(
                registry.experiment_manifest(args.model_experiment_id)
            )
            if args.manifest_hash != expected_hash:
                raise ValueError("freeze hash does not match model experiment manifest")
            registry.transition(
                args.model_experiment_id,
                ModelStage.FROZEN,
                datetime.now(UTC),
                frozen_manifest_hash=args.manifest_hash,
            )
            result = {"model_experiment_id": args.model_experiment_id, "stage": ModelStage.FROZEN}
        elif command == "complete":
            registry.transition(
                args.model_experiment_id, ModelStage.COMPLETE, datetime.now(UTC)
            )
            result = {"model_experiment_id": args.model_experiment_id, "stage": ModelStage.COMPLETE}
        elif command == "verify-artifacts":
            rows = repository.connection.execute(
                """SELECT artifact_id FROM model_fold_artifacts
                   WHERE model_experiment_id = ? ORDER BY artifact_id""",
                (args.model_experiment_id,),
            ).fetchall()
            for row in rows:
                artifact_id = str(row[0])
                manifest = registry.artifact_manifest(artifact_id)
                fold_id = str(manifest["fold_id"])
                load_artifact(registry.artifact(args.model_experiment_id, fold_id), manifest)
            result = {"model_experiment_id": args.model_experiment_id, "verified": len(rows)}
        elif command == "report":
            counts = repository.connection.execute(
                """SELECT COUNT(*) FROM model_predictions
                   WHERE model_experiment_id = ?""",
                (args.model_experiment_id,),
            ).fetchone()
            prediction_count = 0 if counts is None else int(counts[0])
            body = (
                f"# Model research report: {args.model_experiment_id}\n\n"
                f"- predictions: `{prediction_count}`\n"
                "- authority: `RESEARCH_ONLY`\n"
                "- profitability: historical evaluation is not proof of future performance\n"
            )
            Path(args.output).write_text(body, encoding="utf-8", newline="\n")
            registry.insert_report(
                args.model_experiment_id,
                registry.current_stage(args.model_experiment_id),
                datetime.now(UTC),
                {"output": str(args.output), "body_hash": canonical_hash(body)},
            )
            result = {"model_experiment_id": args.model_experiment_id, "output": args.output}
        elif command == "explain":
            row = repository.connection.execute(
                "SELECT payload_json FROM model_predictions WHERE prediction_id = ?",
                (args.prediction_id,),
            ).fetchone()
            if row is None:
                return 1
            print(str(row[0]))
            return 0
        else:
            raise ValueError(f"unsupported model command: {command}")
    print(canonical_json(result))
    return 0
