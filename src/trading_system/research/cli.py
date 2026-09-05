"""Phase 2B research command parsing and append-only orchestration."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from trading_system.patterns import RangeEvaluationReportRegistry
from trading_system.persistence import SQLiteRepository
from trading_system.reporting import (
    RangeBundleReviewRegistry,
    RangeBundleReviewVerdict,
    RangeEvidenceBundleRegistry,
    RangeReportExportRegistry,
    ReviewedRangeBundleAuditRegistry,
    ReviewedRangeBundleRegistry,
    ReviewedRangeCatalogExportAuditRegistry,
    ReviewedRangeCatalogExportIncidentRegistry,
    ReviewedRangeCatalogExportRegistry,
    ReviewedRangeCatalogIncidentNotificationExportAuditRegistry,
    ReviewedRangeCatalogIncidentNotificationExportRegistry,
    ReviewedRangeCatalogIncidentNotificationRegistry,
    ReviewedRangeCatalogRegistry,
    build_range_bundle_review,
    load_range_bundle_review_config,
    load_range_evidence_bundle_config,
    load_range_report_export_config,
    load_range_report_receipt_config,
    load_reviewed_range_bundle_audit_config,
    load_reviewed_range_bundle_config,
    load_reviewed_range_catalog_config,
    load_reviewed_range_catalog_export_audit_config,
    load_reviewed_range_catalog_export_config,
    load_reviewed_range_catalog_export_incident_config,
    load_reviewed_range_catalog_incident_notification_config,
    load_reviewed_range_catalog_incident_notification_export_audit_config,
    load_reviewed_range_catalog_incident_notification_export_config,
    render_persisted_range_evaluation,
    verify_range_evidence_bundle,
    verify_reviewed_range_bundle,
    write_atomic_range_report,
    write_range_evidence_bundle,
    write_reviewed_range_bundle,
    write_reviewed_range_catalog_incident_notification_export,
    write_reviewed_range_catalog_manifest,
)
from trading_system.research.contracts import (
    ExperimentSpec,
    HumanReview,
    ResearchRow,
    ReviewVerdict,
    WalkForwardSpec,
)
from trading_system.research.evaluation import evaluate_cohort
from trading_system.research.exports import export_jsonl, research_markdown
from trading_system.research.folds import build_walk_forward_folds
from trading_system.research.orchestration import (
    CohortSpec,
    DatasetPartition,
    ExperimentStage,
    assign_fold_rows,
)
from trading_system.research.registry import ExperimentRegistry
from trading_system.research.workflow import ExperimentWorkflow
from trading_system.serialization import canonical_json, deterministic_id


def configure_research_parser(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    research = commands.add_parser("research")
    actions = research.add_subparsers(dest="research_command", required=True)
    define = actions.add_parser("define")
    define.add_argument("--database", required=True)
    define.add_argument("--manifest", required=True)
    for name in ("validate", "status"):
        parser = actions.add_parser(name)
        parser.add_argument("--database", required=True)
        parser.add_argument("--experiment-id", required=True)
    run = actions.add_parser("run")
    run.add_argument("--database", required=True)
    run.add_argument("--experiment-id", required=True)
    run.add_argument("--stage", choices=("train", "validation", "test"), required=True)
    run.add_argument("--dataset", required=True)
    freeze = actions.add_parser("freeze")
    freeze.add_argument("--database", required=True)
    freeze.add_argument("--experiment-id", required=True)
    freeze.add_argument("--definition-hash", required=True)
    complete = actions.add_parser("complete")
    complete.add_argument("--database", required=True)
    complete.add_argument("--experiment-id", required=True)
    report = actions.add_parser("report")
    report.add_argument("--database", required=True)
    report.add_argument("--experiment-id", required=True)
    report.add_argument("--output", required=True)
    explain = actions.add_parser("explain")
    explain.add_argument("--database", required=True)
    explain.add_argument("--result-id", required=True)
    review_import = actions.add_parser("import-reviews")
    review_import.add_argument("--database", required=True)
    review_import.add_argument("--input", required=True)
    review_export = actions.add_parser("export-reviews")
    review_export.add_argument("--database", required=True)
    review_export.add_argument("--experiment-id", required=True)
    review_export.add_argument("--output", required=True)
    range_report = actions.add_parser("range-report")
    range_report.add_argument("--database", required=True)
    range_report.add_argument("--report-id", required=True)
    range_report.add_argument("--config", required=True)
    range_report.add_argument("--output", required=True)
    range_export = actions.add_parser("range-report-export")
    range_export.add_argument("--database", required=True)
    range_export.add_argument("--report-id", required=True)
    range_export.add_argument("--config", required=True)
    range_export.add_argument("--receipt-config", required=True)
    range_export.add_argument("--output", required=True)
    range_status = actions.add_parser("range-report-export-status")
    range_status.add_argument("--database", required=True)
    range_status.add_argument("--export-id", required=True)
    range_status.add_argument("--receipt-config", required=True)
    range_bundle = actions.add_parser("range-bundle-export")
    range_bundle.add_argument("--database", required=True)
    range_bundle.add_argument("--report-id", required=True)
    range_bundle.add_argument("--config", required=True)
    range_bundle.add_argument("--output", required=True)
    range_bundle_verify = actions.add_parser("range-bundle-verify")
    range_bundle_verify.add_argument("--bundle", required=True)
    range_bundle_verify.add_argument("--config", required=True)
    range_bundle_review = actions.add_parser("range-bundle-review")
    range_bundle_review.add_argument("--database", required=True)
    range_bundle_review.add_argument("--bundle", required=True)
    range_bundle_review.add_argument("--bundle-config", required=True)
    range_bundle_review.add_argument("--review-config", required=True)
    range_bundle_review.add_argument("--input", required=True)
    range_bundle_review_status = actions.add_parser("range-bundle-review-status")
    range_bundle_review_status.add_argument("--database", required=True)
    range_bundle_review_status.add_argument("--bundle", required=True)
    range_bundle_review_status.add_argument("--bundle-config", required=True)
    range_bundle_review_status.add_argument("--review-config", required=True)
    reviewed_bundle = actions.add_parser("range-reviewed-bundle-export")
    reviewed_bundle.add_argument("--database", required=True)
    reviewed_bundle.add_argument("--bundle", required=True)
    reviewed_bundle.add_argument("--bundle-config", required=True)
    reviewed_bundle.add_argument("--review-config", required=True)
    reviewed_bundle.add_argument("--config", required=True)
    reviewed_bundle.add_argument("--output", required=True)
    reviewed_bundle_verify = actions.add_parser("range-reviewed-bundle-verify")
    reviewed_bundle_verify.add_argument("--bundle", required=True)
    reviewed_bundle_verify.add_argument("--config", required=True)
    reviewed_bundle_verify.add_argument("--source-config", required=True)
    reviewed_bundle_audit = actions.add_parser("range-reviewed-bundle-audit")
    reviewed_bundle_audit.add_argument("--database", required=True)
    reviewed_bundle_audit.add_argument("--export-id", required=True)
    reviewed_bundle_audit.add_argument("--verified-at", required=True)
    reviewed_bundle_audit.add_argument("--audit-config", required=True)
    reviewed_bundle_audit.add_argument("--bundle-config", required=True)
    reviewed_bundle_audit.add_argument("--source-config", required=True)
    reviewed_bundle_audit_status = actions.add_parser("range-reviewed-bundle-audit-status")
    reviewed_bundle_audit_status.add_argument("--database", required=True)
    reviewed_bundle_audit_status.add_argument("--export-id", required=True)
    reviewed_catalog = actions.add_parser("range-reviewed-bundle-catalog-create")
    reviewed_catalog.add_argument("--database", required=True)
    reviewed_catalog.add_argument("--config", required=True)
    reviewed_catalog.add_argument("--bundle-config", required=True)
    reviewed_catalog.add_argument("--source-config", required=True)
    reviewed_catalog.add_argument("--input", required=True)
    reviewed_catalog_status = actions.add_parser("range-reviewed-bundle-catalog-status")
    reviewed_catalog_status.add_argument("--database", required=True)
    reviewed_catalog_status.add_argument("--config", required=True)
    reviewed_catalog_status.add_argument("--bundle-config", required=True)
    reviewed_catalog_status.add_argument("--source-config", required=True)
    reviewed_catalog_status.add_argument("--catalog-id", required=True)
    reviewed_catalog_export = actions.add_parser("range-reviewed-bundle-catalog-export")
    reviewed_catalog_export.add_argument("--database", required=True)
    reviewed_catalog_export.add_argument("--catalog-id", required=True)
    reviewed_catalog_export.add_argument("--config", required=True)
    reviewed_catalog_export.add_argument("--catalog-config", required=True)
    reviewed_catalog_export.add_argument("--bundle-config", required=True)
    reviewed_catalog_export.add_argument("--source-config", required=True)
    reviewed_catalog_export.add_argument("--output", required=True)
    reviewed_catalog_export_status = actions.add_parser(
        "range-reviewed-bundle-catalog-export-status"
    )
    reviewed_catalog_export_status.add_argument("--database", required=True)
    reviewed_catalog_export_status.add_argument("--export-id", required=True)
    reviewed_catalog_export_status.add_argument("--config", required=True)
    reviewed_catalog_export_status.add_argument("--catalog-config", required=True)
    reviewed_catalog_export_status.add_argument("--bundle-config", required=True)
    reviewed_catalog_export_status.add_argument("--source-config", required=True)
    reviewed_catalog_export_audit = actions.add_parser(
        "range-reviewed-bundle-catalog-export-audit"
    )
    reviewed_catalog_export_audit.add_argument("--database", required=True)
    reviewed_catalog_export_audit.add_argument("--export-id", required=True)
    reviewed_catalog_export_audit.add_argument("--verified-at", required=True)
    reviewed_catalog_export_audit.add_argument("--audit-config", required=True)
    reviewed_catalog_export_audit.add_argument("--export-config", required=True)
    reviewed_catalog_export_audit.add_argument("--catalog-config", required=True)
    reviewed_catalog_export_audit.add_argument("--bundle-config", required=True)
    reviewed_catalog_export_audit.add_argument("--source-config", required=True)
    reviewed_catalog_export_audit_status = actions.add_parser(
        "range-reviewed-bundle-catalog-export-audit-status"
    )
    reviewed_catalog_export_audit_status.add_argument("--database", required=True)
    reviewed_catalog_export_audit_status.add_argument("--export-id", required=True)
    reviewed_catalog_incident_open = actions.add_parser(
        "range-reviewed-bundle-catalog-export-incident-open"
    )
    reviewed_catalog_incident_open.add_argument("--database", required=True)
    reviewed_catalog_incident_open.add_argument("--verification-id", required=True)
    reviewed_catalog_incident_open.add_argument("--occurred-at", required=True)
    reviewed_catalog_incident_open.add_argument("--actor-id", required=True)
    reviewed_catalog_incident_open.add_argument("--note", default="")
    reviewed_catalog_incident_open.add_argument("--config", required=True)
    reviewed_catalog_incident_ack = actions.add_parser(
        "range-reviewed-bundle-catalog-export-incident-acknowledge"
    )
    reviewed_catalog_incident_ack.add_argument("--database", required=True)
    reviewed_catalog_incident_ack.add_argument("--incident-id", required=True)
    reviewed_catalog_incident_ack.add_argument("--occurred-at", required=True)
    reviewed_catalog_incident_ack.add_argument("--actor-id", required=True)
    reviewed_catalog_incident_ack.add_argument("--note", default="")
    reviewed_catalog_incident_ack.add_argument("--config", required=True)
    reviewed_catalog_incident_resolve = actions.add_parser(
        "range-reviewed-bundle-catalog-export-incident-resolve"
    )
    reviewed_catalog_incident_resolve.add_argument("--database", required=True)
    reviewed_catalog_incident_resolve.add_argument("--incident-id", required=True)
    reviewed_catalog_incident_resolve.add_argument("--recovery-verification-id", required=True)
    reviewed_catalog_incident_resolve.add_argument("--occurred-at", required=True)
    reviewed_catalog_incident_resolve.add_argument("--actor-id", required=True)
    reviewed_catalog_incident_resolve.add_argument("--note", default="")
    reviewed_catalog_incident_resolve.add_argument("--config", required=True)
    reviewed_catalog_incident_status = actions.add_parser(
        "range-reviewed-bundle-catalog-export-incident-status"
    )
    reviewed_catalog_incident_status.add_argument("--database", required=True)
    reviewed_catalog_incident_status.add_argument("--incident-id", required=True)
    reviewed_catalog_incident_notify = actions.add_parser(
        "range-reviewed-bundle-catalog-export-incident-notification-materialize"
    )
    reviewed_catalog_incident_notify.add_argument("--database", required=True)
    reviewed_catalog_incident_notify.add_argument("--incident-id", required=True)
    reviewed_catalog_incident_notify.add_argument("--config", required=True)
    reviewed_catalog_incident_notify_status = actions.add_parser(
        "range-reviewed-bundle-catalog-export-incident-notification-status"
    )
    reviewed_catalog_incident_notify_status.add_argument("--database", required=True)
    reviewed_catalog_incident_notify_status.add_argument("--incident-id", required=True)
    reviewed_catalog_incident_notify_status.add_argument("--config", required=True)
    reviewed_catalog_incident_notify_export = actions.add_parser(
        "range-reviewed-bundle-catalog-export-incident-notification-export"
    )
    reviewed_catalog_incident_notify_export.add_argument("--database", required=True)
    reviewed_catalog_incident_notify_export.add_argument("--incident-id", required=True)
    reviewed_catalog_incident_notify_export.add_argument("--config", required=True)
    reviewed_catalog_incident_notify_export.add_argument("--source-config", required=True)
    reviewed_catalog_incident_notify_export.add_argument("--output", required=True)
    reviewed_catalog_incident_notify_export_status = actions.add_parser(
        "range-reviewed-bundle-catalog-export-incident-notification-export-status"
    )
    reviewed_catalog_incident_notify_export_status.add_argument("--database", required=True)
    reviewed_catalog_incident_notify_export_status.add_argument("--export-id", required=True)
    reviewed_catalog_incident_notify_export_status.add_argument("--config", required=True)
    reviewed_catalog_incident_notify_export_status.add_argument("--source-config", required=True)
    reviewed_catalog_incident_notify_export_audit = actions.add_parser(
        "range-reviewed-bundle-catalog-export-incident-notification-export-audit"
    )
    reviewed_catalog_incident_notify_export_audit.add_argument("--database", required=True)
    reviewed_catalog_incident_notify_export_audit.add_argument("--export-id", required=True)
    reviewed_catalog_incident_notify_export_audit.add_argument("--verified-at", required=True)
    reviewed_catalog_incident_notify_export_audit.add_argument("--config", required=True)
    reviewed_catalog_incident_notify_export_audit.add_argument("--export-config", required=True)
    reviewed_catalog_incident_notify_export_audit.add_argument("--source-config", required=True)
    reviewed_catalog_incident_notify_export_audit_status = actions.add_parser(
        "range-reviewed-bundle-catalog-export-incident-notification-export-audit-status"
    )
    reviewed_catalog_incident_notify_export_audit_status.add_argument("--database", required=True)
    reviewed_catalog_incident_notify_export_audit_status.add_argument("--export-id", required=True)


def _load_object(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("research manifest must be an object")
    return value


def _strings(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be a nonempty string list")
    return tuple(str(item) for item in value)


def _catalog_sources(value: object) -> tuple[tuple[str, str], ...]:
    keys = {"reviewed_bundle_export_id", "verification_id"}
    if not isinstance(value, list) or not value:
        raise ValueError("Phase 7O catalog sources are invalid")
    result: list[tuple[str, str]] = []
    for item in value:
        if (
            not isinstance(item, dict)
            or set(item) != keys
            or not all(isinstance(item[key], str) for key in keys)
        ):
            raise ValueError("Phase 7O catalog sources are invalid")
        result.append((str(item["reviewed_bundle_export_id"]), str(item["verification_id"])))
    return tuple(result)


def _define(args: argparse.Namespace, registry: ExperimentRegistry) -> dict[str, object]:
    raw = _load_object(args.manifest)
    folds_raw = raw.get("folds")
    sessions_raw = raw.get("sessions")
    if not isinstance(folds_raw, dict) or not isinstance(sessions_raw, list):
        raise ValueError("manifest folds and sessions are required")
    fold_keys = {
        "minimum_train_sessions",
        "validation_sessions",
        "test_sessions",
        "step_sessions",
        "embargo_sessions",
    }
    if set(folds_raw) != fold_keys or any(
        isinstance(folds_raw[key], bool) or not isinstance(folds_raw[key], int)
        for key in fold_keys
    ):
        raise ValueError("manifest fold specification is invalid")
    fold_spec = WalkForwardSpec(
        folds_raw["minimum_train_sessions"],
        folds_raw["validation_sessions"],
        folds_raw["test_sessions"],
        folds_raw["step_sessions"],
        folds_raw["embargo_sessions"],
    )
    experiment = ExperimentSpec(
        experiment_id=str(raw["experiment_id"]),
        created_at=datetime.fromisoformat(str(raw["created_at"]).replace("Z", "+00:00")),
        source_run_ids=_strings(raw["source_run_ids"], "source_run_ids"),
        code_version=str(raw["code_version"]),
        config_hashes=_strings(raw["config_hashes"], "config_hashes"),
        data_revisions=_strings(raw["data_revisions"], "data_revisions"),
        calendar_versions=_strings(raw["calendar_versions"], "calendar_versions"),
        universe_revision=str(raw["universe_revision"]),
        folds=fold_spec,
        metric_version=str(raw["metric_version"]),
        similarity_config_hash=str(raw["similarity_config_hash"]),
        seed=int(raw["seed"]),
    )
    registry.insert_experiment(experiment)
    parent_id = raw.get("parent_experiment_id")
    if parent_id is not None:
        registry.insert_lineage(
            experiment.experiment_id,
            str(parent_id),
            str(raw.get("lineage_reason", "VALIDATION_DERIVED_REVISION")),
        )
    sessions = tuple(date.fromisoformat(str(item)) for item in sessions_raw)
    folds = build_walk_forward_folds(experiment.experiment_id, sessions, fold_spec)
    if not folds:
        raise ValueError("manifest sessions do not produce any complete fold")
    for fold in folds:
        registry.insert_fold(fold)
    cohorts_raw = raw.get("cohorts", [{"name": "all", "filters": {}}])
    if not isinstance(cohorts_raw, list):
        raise ValueError("cohorts must be a list")
    for item in cohorts_raw:
        if not isinstance(item, dict):
            raise ValueError("cohort definitions must be objects")
        filters_raw = item.get("filters", {})
        if not isinstance(filters_raw, dict):
            raise ValueError("cohort filters must be an object")
        name = str(item["name"])
        identity = (experiment.experiment_id, name, filters_raw)
        registry.insert_cohort(
            CohortSpec(
                deterministic_id("experiment_cohort", identity),
                experiment.experiment_id,
                name,
                {str(key): str(value) for key, value in filters_raw.items()},
                int(item.get("minimum_sample", 30)),
            )
        )
    return {"experiment_id": experiment.experiment_id, "folds": len(folds)}


def _validate(registry: ExperimentRegistry, experiment_id: str) -> dict[str, object]:
    connection = registry.repository.connection
    def count(table: str) -> int:
        row = connection.execute(
            f"SELECT COUNT(*) FROM {table} WHERE experiment_id = ?", (experiment_id,)
        ).fetchone()
        if row is None:
            raise RuntimeError(f"count query failed for {table}")
        return int(row[0])

    run_count = count("experiments")
    fold_count = count("experiment_folds")
    cohort_count = count("experiment_cohorts")
    if run_count != 1 or fold_count == 0 or cohort_count == 0:
        raise ValueError("experiment is incomplete or unknown")
    return {"experiment_id": experiment_id, "folds": fold_count, "cohorts": cohort_count}


def _load_rows(path: str | Path) -> tuple[ResearchRow, ...]:
    rows: list[ResearchRow] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if not isinstance(item, dict):
            raise ValueError("research dataset rows must be objects")
        features = item.get("features", {})
        if not isinstance(features, dict):
            raise ValueError("research dataset features must be an object")
        available = item.get("label_available_at")
        net_r = item.get("net_r")
        rows.append(
            ResearchRow(
                str(item["row_id"]),
                str(item["observation_id"]),
                str(item["symbol"]),
                date.fromisoformat(str(item["session_date"])),
                None
                if available is None
                else datetime.fromisoformat(str(available).replace("Z", "+00:00")),
                None if item.get("outcome_label") is None else str(item["outcome_label"]),
                None if net_r is None else Decimal(str(net_r)),
                {str(key): value for key, value in features.items()},
            )
        )
    ordered = tuple(sorted(rows, key=lambda item: (item.session_date, item.row_id)))
    if len({row.row_id for row in ordered}) != len(ordered):
        raise ValueError("research dataset row IDs must be unique")
    return ordered


def _cohorts(registry: ExperimentRegistry, experiment_id: str) -> tuple[CohortSpec, ...]:
    rows = registry.repository.connection.execute(
        """SELECT payload_json FROM experiment_cohorts WHERE experiment_id = ?
           ORDER BY cohort_id""",
        (experiment_id,),
    ).fetchall()
    result: list[CohortSpec] = []
    for row in rows:
        payload = json.loads(str(row[0]))
        if not isinstance(payload, dict) or not isinstance(payload.get("filters"), dict):
            raise ValueError("stored cohort payload is invalid")
        result.append(
            CohortSpec(
                str(payload["cohort_id"]),
                str(payload["experiment_id"]),
                str(payload["name"]),
                {str(key): str(value) for key, value in payload["filters"].items()},
                int(payload["minimum_sample"]),
            )
        )
    return tuple(result)


def _experiment_seed(registry: ExperimentRegistry, experiment_id: str) -> int:
    row = registry.repository.connection.execute(
        "SELECT payload_json FROM experiments WHERE experiment_id = ?", (experiment_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown experiment: {experiment_id}")
    payload = json.loads(str(row[0]))
    if not isinstance(payload, dict) or not isinstance(payload.get("seed"), int):
        raise ValueError("stored experiment seed is invalid")
    return int(payload["seed"])


def _run_stage(
    registry: ExperimentRegistry,
    experiment_id: str,
    stage_name: str,
    dataset: str | Path,
) -> dict[str, object]:
    targets = {
        "train": ExperimentStage.TRAIN_EVALUATED,
        "validation": ExperimentStage.VALIDATION_EVALUATED,
        "test": ExperimentStage.TEST_EVALUATED,
    }
    workflow = ExperimentWorkflow(registry, experiment_id)
    target = targets[stage_name]
    rows = _load_rows(dataset)
    partition = {
        "train": DatasetPartition.TRAIN,
        "validation": DatasetPartition.VALIDATION,
        "test": DatasetPartition.TEST,
    }[stage_name]
    result_count = 0
    seed = _experiment_seed(registry, experiment_id)
    for fold in registry.folds(experiment_id):
        workflow.assign(fold, rows)
        assignments = assign_fold_rows(experiment_id, fold, rows)
        for cohort in _cohorts(registry, experiment_id):
            result = evaluate_cohort(cohort, partition, assignments, rows, seed=seed)
            result_id = deterministic_id(
                "conditional_statistic", (experiment_id, fold.fold_id, cohort.cohort_id, partition)
            )
            result_count += int(
                registry.insert_result(
                    table="conditional_statistics",
                    result_id=result_id,
                    experiment_id=experiment_id,
                    fold_id=fold.fold_id,
                    known_at=datetime.now(UTC),
                    payload=result,
                )
            )
    now = datetime.now(UTC)
    workflow.advance(target, occurred_at=now)
    counts = _validate(registry, experiment_id)
    payload = {**counts, "stage": target.value, "results": result_count}
    registry.insert_checkpoint(experiment_id, target, payload)
    registry.insert_report(experiment_id, target, now, payload)
    return payload


def _result_payload(registry: ExperimentRegistry, result_id: str) -> str | None:
    for table, identity in (
        ("conditional_statistics", "result_id"),
        ("calibration_results", "result_id"),
        ("experiment_reports", "report_id"),
    ):
        row = registry.repository.connection.execute(
            f"SELECT payload_json FROM {table} WHERE {identity} = ?", (result_id,)
        ).fetchone()
        if row is not None:
            return str(row[0])
    return None


def _import_reviews(args: argparse.Namespace, registry: ExperimentRegistry) -> dict[str, object]:
    inserted = 0
    for line in Path(args.input).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if not isinstance(item, dict):
            raise ValueError("review rows must be objects")
        review = HumanReview(
            str(item["review_id"]),
            str(item["experiment_id"]),
            str(item["observation_id"]),
            str(item["reviewer_id"]),
            datetime.fromisoformat(str(item["reviewed_at"]).replace("Z", "+00:00")),
            ReviewVerdict(str(item["verdict"])),
            str(item.get("notes", "")),
        )
        inserted += int(registry.insert_review(review))
    return {"inserted": inserted}


def handle_research(args: argparse.Namespace) -> int:
    if args.research_command == "range-bundle-verify":
        verification = verify_range_evidence_bundle(
            args.bundle, load_range_evidence_bundle_config(args.config)
        )
        print(canonical_json(verification))
        return 0
    if args.research_command == "range-reviewed-bundle-verify":
        reviewed_verification = verify_reviewed_range_bundle(
            args.bundle,
            load_reviewed_range_bundle_config(args.config),
            load_range_evidence_bundle_config(args.source_config),
        )
        print(canonical_json(reviewed_verification))
        return 0
    with SQLiteRepository(args.database) as repository:
        repository.migrate()
        registry = ExperimentRegistry(repository)
        command = args.research_command
        if command == "define":
            result = _define(args, registry)
        elif command == "validate":
            result = _validate(registry, args.experiment_id)
        elif command == "status":
            result = {
                "experiment_id": args.experiment_id,
                "stage": registry.current_stage(args.experiment_id),
            }
        elif command == "run":
            result = _run_stage(registry, args.experiment_id, args.stage, args.dataset)
        elif command == "freeze":
            workflow = ExperimentWorkflow(registry, args.experiment_id)
            workflow.advance(ExperimentStage.FROZEN, frozen_definition_hash=args.definition_hash)
            result = {"experiment_id": args.experiment_id, "stage": ExperimentStage.FROZEN}
        elif command == "complete":
            workflow = ExperimentWorkflow(registry, args.experiment_id)
            workflow.advance(ExperimentStage.COMPLETE)
            result = {"experiment_id": args.experiment_id, "stage": ExperimentStage.COMPLETE}
        elif command == "report":
            result = _validate(registry, args.experiment_id)
            Path(args.output).write_text(
                research_markdown(args.experiment_id, result), encoding="utf-8", newline="\n"
            )
            result = {**result, "output": args.output}
        elif command == "explain":
            payload = _result_payload(registry, args.result_id)
            if payload is None:
                return 1
            print(payload)
            return 0
        elif command == "import-reviews":
            result = _import_reviews(args, registry)
        elif command == "export-reviews":
            rows = repository.connection.execute(
                """SELECT review_id, experiment_id, observation_id, reviewer_id,
                          reviewed_at, verdict, payload_json
                   FROM human_reviews WHERE experiment_id = ?
                   ORDER BY reviewed_at, review_id""",
                (args.experiment_id,),
            ).fetchall()
            exported: list[dict[str, object]] = []
            for row in rows:
                payload = json.loads(str(row[6]))
                notes = payload.get("notes", "") if isinstance(payload, dict) else ""
                exported.append(
                    {
                        "review_id": str(row[0]),
                        "experiment_id": str(row[1]),
                        "observation_id": str(row[2]),
                        "reviewer_id": str(row[3]),
                        "reviewed_at": str(row[4]),
                        "verdict": str(row[5]),
                        "notes": str(notes),
                    }
                )
            export_jsonl(tuple(exported), args.output)
            result = {"experiment_id": args.experiment_id, "rows": len(rows), "output": args.output}
        elif command == "range-report":
            export_config = load_range_report_export_config(args.config)
            report, summaries = RangeEvaluationReportRegistry(
                repository
            ).load_verified_payloads(args.report_id)
            Path(args.output).write_text(
                render_persisted_range_evaluation(export_config, report, summaries),
                encoding="utf-8",
                newline="\n",
            )
            result = {
                "report_id": args.report_id,
                "output": args.output,
                "config_hash": export_config.config_hash,
                "network_used": False,
                "broker_write_performed": False,
            }
        elif command == "range-report-export":
            export_config = load_range_report_export_config(args.config)
            receipt_config = load_range_report_receipt_config(args.receipt_config)
            report, summaries = RangeEvaluationReportRegistry(
                repository
            ).load_verified_payloads(args.report_id)
            receipt = write_atomic_range_report(
                body=render_persisted_range_evaluation(export_config, report, summaries),
                output=args.output,
                report=report,
                rendering_config_hash=export_config.config_hash,
                config=receipt_config,
            )
            inserted = RangeReportExportRegistry(repository).persist(receipt)
            result = {
                "export_id": receipt.export_id,
                "report_id": receipt.report_id,
                "output": receipt.output_path,
                "content_hash": receipt.content_hash,
                "byte_count": receipt.byte_count,
                "receipt_inserted": inserted,
                "network_used": False,
                "broker_write_performed": False,
            }
        elif command == "range-report-export-status":
            receipt = RangeReportExportRegistry(repository).verify(
                args.export_id, load_range_report_receipt_config(args.receipt_config)
            )
            result = {
                "export_id": receipt.export_id,
                "report_id": receipt.report_id,
                "output": receipt.output_path,
                "content_hash": receipt.content_hash,
                "byte_count": receipt.byte_count,
                "verified": True,
                "network_used": False,
                "broker_write_performed": False,
            }
        elif command == "range-bundle-export":
            bundle_config = load_range_evidence_bundle_config(args.config)
            report, assignments, summaries = RangeEvaluationReportRegistry(
                repository
            ).load_verified_evidence(args.report_id)
            record = write_range_evidence_bundle(
                output=args.output,
                report=report,
                assignments=assignments,
                summaries=summaries,
                config=bundle_config,
            )
            inserted = RangeEvidenceBundleRegistry(repository).persist(record)
            result = {
                "bundle_export_id": record.bundle_export_id,
                "bundle_id": record.bundle_id,
                "report_id": record.report_id,
                "output": record.output_path,
                "artifact_hash": record.artifact_hash,
                "artifact_bytes": record.artifact_bytes,
                "record_inserted": inserted,
                "signed": False,
                "trusted_timestamp": False,
                "network_used": False,
                "broker_write_performed": False,
            }
        elif command == "range-bundle-review":
            bundle_config = load_range_evidence_bundle_config(args.bundle_config)
            review_config = load_range_bundle_review_config(args.review_config)
            verification = verify_range_evidence_bundle(args.bundle, bundle_config)
            review_input = _load_object(args.input)
            required = {"reviewer_id", "reviewed_at", "verdict", "reason_codes", "notes"}
            if set(review_input) != required:
                raise ValueError("Phase 7L review input keys are invalid")
            reasons = review_input["reason_codes"]
            if not all(
                isinstance(review_input[key], str)
                for key in ("reviewer_id", "reviewed_at", "verdict", "notes")
            ):
                raise ValueError("Phase 7L review scalar values must be strings")
            if not isinstance(reasons, list) or not all(
                isinstance(item, str) for item in reasons
            ):
                raise ValueError("Phase 7L reason_codes must be a string list")
            review_registry = RangeBundleReviewRegistry(repository)
            assertion = build_range_bundle_review(
                verification=verification,
                bundle_export_id=review_registry.source_export(verification),
                reviewer_id=review_input["reviewer_id"],
                reviewed_at=datetime.fromisoformat(
                    review_input["reviewed_at"].replace("Z", "+00:00")
                ),
                verdict=RangeBundleReviewVerdict(review_input["verdict"]),
                reason_codes=tuple(reasons),
                notes=review_input["notes"],
                config=review_config,
            )
            inserted = review_registry.persist(assertion)
            result = {
                "annotation_id": assertion.annotation_id,
                "bundle_id": assertion.bundle_id,
                "verdict": assertion.verdict,
                "record_inserted": inserted,
                "reviewer_identity_authenticated": False,
                "approval_granted": False,
                "promotion_authority": False,
                "network_used": False,
                "broker_write_performed": False,
            }
        elif command == "range-bundle-review-status":
            verification = verify_range_evidence_bundle(
                args.bundle, load_range_evidence_bundle_config(args.bundle_config)
            )
            assertions = RangeBundleReviewRegistry(repository).load_verified(
                verification, load_range_bundle_review_config(args.review_config)
            )
            result = {
                "bundle_id": verification.bundle_id,
                "report_id": verification.report_id,
                "assertion_count": len(assertions),
                "assertions": assertions,
                "aggregation_performed": False,
                "approval_granted": False,
                "promotion_authority": False,
                "network_used": False,
                "broker_write_performed": False,
            }
        elif command == "range-reviewed-bundle-export":
            source = verify_range_evidence_bundle(
                args.bundle, load_range_evidence_bundle_config(args.bundle_config)
            )
            review_registry = RangeBundleReviewRegistry(repository)
            review_registry.source_export(source)
            reviews = review_registry.load_verified(
                source, load_range_bundle_review_config(args.review_config)
            )
            reviewed_record = write_reviewed_range_bundle(
                output=args.output,
                source_bundle=args.bundle,
                source=source,
                reviews=reviews,
                config=load_reviewed_range_bundle_config(args.config),
            )
            inserted = ReviewedRangeBundleRegistry(repository).persist(reviewed_record)
            result = {
                "reviewed_bundle_export_id": reviewed_record.reviewed_bundle_export_id,
                "reviewed_bundle_id": reviewed_record.reviewed_bundle_id,
                "source_bundle_id": reviewed_record.source_bundle_id,
                "review_count": reviewed_record.review_count,
                "artifact_hash": reviewed_record.artifact_hash,
                "record_inserted": inserted,
                "signed": False,
                "consensus_established": False,
                "approval_granted": False,
                "promotion_authority": False,
                "network_used": False,
                "broker_write_performed": False,
            }
        elif command == "range-reviewed-bundle-audit":
            audit_receipt = ReviewedRangeBundleAuditRegistry(repository).audit(
                export_id=args.export_id,
                verified_at=datetime.fromisoformat(args.verified_at.replace("Z", "+00:00")),
                audit_config=load_reviewed_range_bundle_audit_config(args.audit_config),
                bundle_config=load_reviewed_range_bundle_config(args.bundle_config),
                source_config=load_range_evidence_bundle_config(args.source_config),
            )
            result = {
                "verification_id": audit_receipt.verification_id,
                "reviewed_bundle_export_id": audit_receipt.reviewed_bundle_export_id,
                "status": audit_receipt.status,
                "reasons": audit_receipt.reasons,
                "trusted_timestamp": False,
                "signed": False,
                "approval_granted": False,
                "promotion_authority": False,
                "network_used": False,
                "broker_write_performed": False,
            }
        elif command == "range-reviewed-bundle-audit-status":
            latest_status, verification_count = ReviewedRangeBundleAuditRegistry(
                repository
            ).status(args.export_id)
            result = {
                "reviewed_bundle_export_id": args.export_id,
                "latest_status": latest_status,
                "verification_count": verification_count,
                "approval_granted": False,
                "promotion_authority": False,
                "network_used": False,
                "broker_write_performed": False,
            }
        elif command == "range-reviewed-bundle-catalog-create":
            catalog_input = _load_object(args.input)
            required = {"catalog_name", "cataloged_at", "source_revision", "sources"}
            if set(catalog_input) != required or not all(
                isinstance(catalog_input[key], str)
                for key in ("catalog_name", "cataloged_at", "source_revision")
            ):
                raise ValueError("Phase 7O catalog input keys are invalid")
            sources = _catalog_sources(catalog_input["sources"])
            catalog_registry = ReviewedRangeCatalogRegistry(
                repository,
                load_reviewed_range_catalog_config(args.config),
                load_reviewed_range_bundle_config(args.bundle_config),
                load_range_evidence_bundle_config(args.source_config),
            )
            catalog = catalog_registry.create(
                catalog_name=catalog_input["catalog_name"],
                cataloged_at=datetime.fromisoformat(
                    catalog_input["cataloged_at"].replace("Z", "+00:00")
                ),
                source_revision=catalog_input["source_revision"],
                sources=sources,
            )
            inserted = catalog_registry.persist(catalog)
            result = {
                "catalog_id": catalog.catalog_id,
                "catalog_root": catalog.catalog_root,
                "entry_count": catalog.entry_count,
                "record_inserted": inserted,
                "membership_complete": False,
                "ranking_performed": False,
                "approval_granted": False,
                "promotion_authority": False,
                "network_used": False,
                "broker_write_performed": False,
            }
        elif command == "range-reviewed-bundle-catalog-status":
            catalog_registry = ReviewedRangeCatalogRegistry(
                repository,
                load_reviewed_range_catalog_config(args.config),
                load_reviewed_range_bundle_config(args.bundle_config),
                load_range_evidence_bundle_config(args.source_config),
            )
            catalog_root, entry_count = catalog_registry.status(args.catalog_id)
            result = {
                "catalog_id": args.catalog_id,
                "catalog_root": catalog_root,
                "entry_count": entry_count,
                "verified": True,
                "membership_complete": False,
                "ranking_performed": False,
                "approval_granted": False,
                "promotion_authority": False,
                "network_used": False,
                "broker_write_performed": False,
            }
        elif command in {
            "range-reviewed-bundle-catalog-export",
            "range-reviewed-bundle-catalog-export-status",
        }:
            catalog_registry = ReviewedRangeCatalogRegistry(
                repository,
                load_reviewed_range_catalog_config(args.catalog_config),
                load_reviewed_range_bundle_config(args.bundle_config),
                load_range_evidence_bundle_config(args.source_config),
            )
            catalog_export_config = load_reviewed_range_catalog_export_config(args.config)
            export_registry = ReviewedRangeCatalogExportRegistry(
                repository, catalog_registry
            )
            if command == "range-reviewed-bundle-catalog-export":
                catalog = catalog_registry.load(args.catalog_id)
                export_receipt = write_reviewed_range_catalog_manifest(
                    catalog=catalog, output=args.output, config=catalog_export_config
                )
                inserted = export_registry.persist(export_receipt)
            else:
                export_receipt = export_registry.verify(args.export_id, catalog_export_config)
                inserted = False
            result = {
                "catalog_export_id": export_receipt.catalog_export_id,
                "catalog_id": export_receipt.catalog_id,
                "content_hash": export_receipt.content_hash,
                "byte_count": export_receipt.byte_count,
                "entry_count": export_receipt.entry_count,
                "record_inserted": inserted,
                "verified": command.endswith("-status"),
                "portable_evidence_archive": False,
                "membership_complete": False,
                "ranking_performed": False,
                "approval_granted": False,
                "promotion_authority": False,
                "network_used": False,
                "broker_write_performed": False,
            }
        elif command == "range-reviewed-bundle-catalog-export-audit":
            phase7q_bundle_config = load_reviewed_range_bundle_config(args.bundle_config)
            phase7q_source_config = load_range_evidence_bundle_config(args.source_config)
            phase7q_catalog_config = load_reviewed_range_catalog_config(args.catalog_config)
            phase7p_config = load_reviewed_range_catalog_export_config(args.export_config)
            catalog_registry = ReviewedRangeCatalogRegistry(
                repository,
                phase7q_catalog_config,
                phase7q_bundle_config,
                phase7q_source_config,
            )
            phase7p_registry = ReviewedRangeCatalogExportRegistry(
                repository, catalog_registry
            )
            phase7q_receipt = ReviewedRangeCatalogExportAuditRegistry(
                repository, phase7p_registry
            ).audit(
                export_id=args.export_id,
                verified_at=datetime.fromisoformat(args.verified_at.replace("Z", "+00:00")),
                audit_config=load_reviewed_range_catalog_export_audit_config(args.audit_config),
                export_config=phase7p_config,
                catalog_config=phase7q_catalog_config,
                bundle_config=phase7q_bundle_config,
                source_config=phase7q_source_config,
            )
            result = {
                "verification_id": phase7q_receipt.verification_id,
                "catalog_export_id": phase7q_receipt.catalog_export_id,
                "catalog_id": phase7q_receipt.catalog_id,
                "status": phase7q_receipt.status,
                "reasons": phase7q_receipt.reasons,
                "trusted_timestamp": False,
                "signed": False,
                "membership_complete": False,
                "ranking_performed": False,
                "approval_granted": False,
                "promotion_authority": False,
                "network_used": False,
                "broker_write_performed": False,
            }
        elif command == "range-reviewed-bundle-catalog-export-audit-status":
            latest_status, verification_count = ReviewedRangeCatalogExportAuditRegistry(
                repository
            ).status(args.export_id)
            result = {
                "catalog_export_id": args.export_id,
                "latest_status": latest_status,
                "verification_count": verification_count,
                "approval_granted": False,
                "promotion_authority": False,
                "network_used": False,
                "broker_write_performed": False,
            }
        elif command in {
            "range-reviewed-bundle-catalog-export-incident-open",
            "range-reviewed-bundle-catalog-export-incident-acknowledge",
            "range-reviewed-bundle-catalog-export-incident-resolve",
        }:
            incident_registry = ReviewedRangeCatalogExportIncidentRegistry(repository)
            incident_config = load_reviewed_range_catalog_export_incident_config(args.config)
            occurred_at = datetime.fromisoformat(args.occurred_at.replace("Z", "+00:00"))
            if command.endswith("-open"):
                incident_event = incident_registry.open(
                    verification_id=args.verification_id,
                    occurred_at=occurred_at,
                    actor_id=args.actor_id,
                    note=args.note,
                    config=incident_config,
                )
            elif command.endswith("-acknowledge"):
                incident_event = incident_registry.acknowledge(
                    incident_id=args.incident_id,
                    occurred_at=occurred_at,
                    actor_id=args.actor_id,
                    note=args.note,
                    config=incident_config,
                )
            else:
                incident_event = incident_registry.resolve(
                    incident_id=args.incident_id,
                    recovery_verification_id=args.recovery_verification_id,
                    occurred_at=occurred_at,
                    actor_id=args.actor_id,
                    note=args.note,
                    config=incident_config,
                )
            result = {
                "incident_event_id": incident_event.incident_event_id,
                "incident_id": incident_event.incident_id,
                "catalog_export_id": incident_event.catalog_export_id,
                "source_verification_id": incident_event.source_verification_id,
                "event_type": incident_event.event_type,
                "prior_state": incident_event.prior_state,
                "new_state": incident_event.new_state,
                "trusted_timestamp": False,
                "authenticated_actor": False,
                "artifact_mutated": False,
                "quarantine_enforced": False,
                "approval_granted": False,
                "promotion_authority": False,
                "network_used": False,
                "broker_write_performed": False,
            }
        elif command == "range-reviewed-bundle-catalog-export-incident-status":
            incident = ReviewedRangeCatalogExportIncidentRegistry(repository).status(
                args.incident_id
            )
            result = {
                "incident_id": incident.incident_id,
                "catalog_export_id": incident.catalog_export_id,
                "state": incident.state,
                "event_count": incident.event_count,
                "opened_at": incident.opened_at,
                "latest_at": incident.latest_at,
                "failed_verification_id": incident.failed_verification_id,
                "recovery_verification_id": incident.recovery_verification_id,
                "approval_granted": False,
                "promotion_authority": False,
                "network_used": False,
                "broker_write_performed": False,
            }
        elif command in {
            "range-reviewed-bundle-catalog-export-incident-notification-materialize",
            "range-reviewed-bundle-catalog-export-incident-notification-status",
        }:
            notification_config = load_reviewed_range_catalog_incident_notification_config(
                args.config
            )
            notification_registry = ReviewedRangeCatalogIncidentNotificationRegistry(repository)
            if command.endswith("-materialize"):
                intents = notification_registry.materialize(args.incident_id, notification_config)
                incident_summary = notification_registry.status(
                    args.incident_id, notification_config
                )
                materialized = len(intents)
            else:
                incident_summary = notification_registry.status(
                    args.incident_id, notification_config
                )
                materialized = 0
            result = {
                "incident_id": incident_summary.incident_id,
                "catalog_export_id": incident_summary.catalog_export_id,
                "intent_count": incident_summary.intent_count,
                "event_types": incident_summary.event_types,
                "materialized_count": materialized,
                "route": "LOCAL_OPERATOR_OUTBOX",
                "delivery_attempt_count": incident_summary.delivery_attempt_count,
                "network_used": False,
                "delivery_attempted": False,
                "recipient_authenticated": False,
                "quarantine_enforced": False,
                "approval_granted": False,
                "promotion_authority": False,
                "broker_write_performed": False,
            }
        elif command in {
            "range-reviewed-bundle-catalog-export-incident-notification-export",
            "range-reviewed-bundle-catalog-export-incident-notification-export-status",
        }:
            phase7t_source_config = load_reviewed_range_catalog_incident_notification_config(
                args.source_config
            )
            phase7t_export_config = (
                load_reviewed_range_catalog_incident_notification_export_config(args.config)
            )
            notification_registry = ReviewedRangeCatalogIncidentNotificationRegistry(repository)
            notification_export_registry = (
                ReviewedRangeCatalogIncidentNotificationExportRegistry(
                    repository, notification_registry
                )
            )
            if command.endswith("-export"):
                intents = notification_registry.load(args.incident_id, phase7t_source_config)
                notification_export = (
                    write_reviewed_range_catalog_incident_notification_export(
                        intents=intents, output=args.output, config=phase7t_export_config
                    )
                )
                inserted = notification_export_registry.persist(
                    notification_export, phase7t_source_config
                )
            else:
                notification_export = notification_export_registry.verify(
                    args.export_id, phase7t_export_config, phase7t_source_config
                )
                inserted = False
            result = {
                "notification_export_id": notification_export.notification_export_id,
                "incident_id": notification_export.incident_id,
                "catalog_export_id": notification_export.catalog_export_id,
                "content_hash": notification_export.content_hash,
                "byte_count": notification_export.byte_count,
                "intent_count": notification_export.intent_count,
                "record_inserted": inserted,
                "verified": command.endswith("-status"),
                "network_used": False,
                "delivery_attempted": False,
                "recipient_authenticated": False,
                "quarantine_enforced": False,
                "approval_granted": False,
                "promotion_authority": False,
                "broker_write_performed": False,
            }
        elif command in {
            "range-reviewed-bundle-catalog-export-incident-notification-export-audit",
            "range-reviewed-bundle-catalog-export-incident-notification-export-audit-status",
        }:
            audit_registry = ReviewedRangeCatalogIncidentNotificationExportAuditRegistry(
                repository
            )
            if command.endswith("-audit"):
                phase7u_audit_config = (
                    load_reviewed_range_catalog_incident_notification_export_audit_config(
                        args.config
                    )
                )
                phase7u_export_config = (
                    load_reviewed_range_catalog_incident_notification_export_config(
                        args.export_config
                    )
                )
                phase7u_source_config = load_reviewed_range_catalog_incident_notification_config(
                    args.source_config
                )
                phase7u_notification_registry = ReviewedRangeCatalogIncidentNotificationRegistry(
                    repository
                )
                phase7u_export_registry = ReviewedRangeCatalogIncidentNotificationExportRegistry(
                    repository, phase7u_notification_registry
                )
                audit_registry = (
                    ReviewedRangeCatalogIncidentNotificationExportAuditRegistry(
                        repository, phase7u_export_registry
                    )
                )
                phase7u_audit_receipt = audit_registry.audit(
                    export_id=args.export_id,
                    verified_at=datetime.fromisoformat(args.verified_at.replace("Z", "+00:00")),
                    audit_config=phase7u_audit_config,
                    export_config=phase7u_export_config,
                    notification_config=phase7u_source_config,
                )
                latest_status, verification_count = audit_registry.status(args.export_id)
                verification_id = phase7u_audit_receipt.verification_id
                expected_hash = phase7u_audit_receipt.expected_hash
                actual_hash = phase7u_audit_receipt.actual_hash
                reasons = phase7u_audit_receipt.reasons
            else:
                latest_status, verification_count = audit_registry.status(args.export_id)
                verification_id = None
                expected_hash = None
                actual_hash = None
                reasons = ()
            result = {
                "notification_export_id": args.export_id,
                "verification_id": verification_id,
                "latest_status": latest_status,
                "verification_count": verification_count,
                "expected_hash": expected_hash,
                "actual_hash": actual_hash,
                "reasons": reasons,
                "network_used": False,
                "delivery_attempted": False,
                "recipient_authenticated": False,
                "artifact_mutated": False,
                "quarantine_enforced": False,
                "approval_granted": False,
                "promotion_authority": False,
                "broker_write_performed": False,
            }
        else:
            raise ValueError(f"unsupported research command: {command}")
    print(canonical_json(result))
    return 0
