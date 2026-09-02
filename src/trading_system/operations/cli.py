"""Offline Phase 5 operations inspection and monitor planning commands."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from trading_system import PACKAGE_VERSION
from trading_system.operations.audit_config import load_observation_audit_config
from trading_system.operations.audit_export import ObservationAuditExportService
from trading_system.operations.audit_export_config import load_observation_audit_export_config
from trading_system.operations.audit_export_registry import ObservationAuditExportRegistry
from trading_system.operations.audit_registry import ObservationAuditRegistry
from trading_system.operations.audit_review_catalog_config import (
    load_observation_audit_review_catalog_config,
)
from trading_system.operations.audit_review_catalog_registry import (
    ObservationAuditReviewCatalogRegistry,
)
from trading_system.operations.audit_review_config import load_observation_audit_review_config
from trading_system.operations.audit_review_contracts import AuditReviewVerdict
from trading_system.operations.audit_review_export import ObservationAuditReviewExportService
from trading_system.operations.audit_review_export_config import (
    load_observation_audit_review_export_config,
)
from trading_system.operations.audit_review_export_registry import (
    ObservationAuditReviewExportRegistry,
)
from trading_system.operations.audit_review_plan_config import load_review_catalog_plan_config
from trading_system.operations.audit_review_plan_registry import ReviewCatalogPlanRegistry
from trading_system.operations.audit_review_registry import ObservationAuditReviewRegistry
from trading_system.operations.campaign_config import load_operations_campaign_config
from trading_system.operations.campaign_contracts import CampaignWindowRequest
from trading_system.operations.campaign_registry import OperationsCampaignRegistry
from trading_system.operations.config import load_operations_config
from trading_system.operations.contracts import OperationsManifest
from trading_system.operations.control_config import load_operations_control_config
from trading_system.operations.control_registry import OperationsControlRegistry
from trading_system.operations.controls import (
    ApprovalAction,
    ApprovalEvent,
    CancellationAction,
    CancellationEvent,
    IncidentAction,
    IncidentEvent,
    KillSwitchEvent,
    SwitchAction,
)
from trading_system.operations.inspection import inspect_component
from trading_system.operations.monitor_config import load_operations_monitor_config
from trading_system.operations.monitoring import (
    HealthObservation,
    HealthStatus,
    OperationalMode,
    OperationsMonitorEngine,
    ScheduleCursor,
    ScheduleDefinition,
)
from trading_system.operations.observation_config import load_observation_plan_config
from trading_system.operations.observation_contracts import ObservationPlanWindow
from trading_system.operations.observation_registry import ObservationPlanRegistry
from trading_system.operations.prospective_catalog_config import (
    load_prospective_catalog_materialization_config,
)
from trading_system.operations.prospective_catalog_registry import (
    ProspectiveCatalogMaterializationRegistry,
)
from trading_system.operations.prospective_chain_export import ProspectiveChainExportService
from trading_system.operations.prospective_chain_export_config import (
    load_prospective_chain_export_config,
)
from trading_system.operations.prospective_chain_export_registry import (
    ProspectiveChainExportRegistry,
)
from trading_system.operations.prospective_chain_review_bundle import (
    ProspectiveChainReviewBundleService,
)
from trading_system.operations.prospective_chain_review_bundle_config import (
    load_prospective_chain_review_bundle_config,
)
from trading_system.operations.prospective_chain_review_bundle_registry import (
    ProspectiveChainReviewBundleRegistry,
)
from trading_system.operations.prospective_chain_review_catalog_config import (
    load_prospective_chain_review_catalog_config,
)
from trading_system.operations.prospective_chain_review_catalog_plan_config import (
    load_prospective_chain_review_catalog_plan_config,
)
from trading_system.operations.prospective_chain_review_catalog_plan_registry import (
    ProspectiveChainReviewCatalogPlanRegistry,
)
from trading_system.operations.prospective_chain_review_catalog_registry import (
    ProspectiveChainReviewCatalogRegistry,
)
from trading_system.operations.prospective_chain_review_config import (
    load_prospective_chain_review_config,
)
from trading_system.operations.prospective_chain_review_contracts import (
    ProspectiveChainReviewVerdict,
)
from trading_system.operations.prospective_chain_review_registry import (
    ProspectiveChainReviewRegistry,
)
from trading_system.operations.prospective_review_bundle_chain_export import (
    ProspectiveReviewBundleChainExportService,
)
from trading_system.operations.prospective_review_bundle_chain_export_config import (
    load_prospective_review_bundle_chain_export_config,
)
from trading_system.operations.prospective_review_bundle_chain_export_registry import (
    ProspectiveReviewBundleChainExportRegistry,
)
from trading_system.operations.prospective_review_bundle_materialization_config import (
    load_prospective_review_bundle_materialization_config,
)
from trading_system.operations.prospective_review_bundle_materialization_registry import (
    ProspectiveReviewBundleMaterializationRegistry,
)
from trading_system.operations.prospective_review_bundle_plan_config import (
    load_prospective_review_bundle_plan_config,
)
from trading_system.operations.prospective_review_bundle_plan_registry import (
    ProspectiveReviewBundlePlanRegistry,
)
from trading_system.operations.prospective_review_config import (
    load_prospective_review_plan_config,
)
from trading_system.operations.prospective_review_registry import ProspectiveReviewPlanRegistry
from trading_system.operations.registry import OperationsRegistry
from trading_system.operations.release_config import load_operations_release_config
from trading_system.operations.release_registry import OperationsReleaseRegistry
from trading_system.operations.resilience import OperationsResilienceService
from trading_system.operations.resilience_config import load_operations_resilience_config
from trading_system.operations.resilience_registry import OperationsResilienceRegistry
from trading_system.operations.runner import JobRunRequest, OperationsJobRunner, WorkerAction
from trading_system.operations.runner_config import (
    OperationsRunnerConfig,
    load_operations_runner_config,
)
from trading_system.operations.runner_registry import OperationsRunnerRegistry
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_json


def configure_operations_parser(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    operations = commands.add_parser("operations")
    actions = operations.add_subparsers(dest="operations_command", required=True)
    validate = actions.add_parser("validate-config")
    validate.add_argument("--config", required=True)
    inspect = actions.add_parser("inspect")
    inspect.add_argument("--config", required=True)
    inspect.add_argument("--input", required=True)
    inspect.add_argument("--registry-database", required=True)
    status = actions.add_parser("status")
    status.add_argument("--registry-database", required=True)
    status.add_argument("--manifest-id", required=True)
    validate_monitor = actions.add_parser("validate-monitor-config")
    validate_monitor.add_argument("--config", required=True)
    monitor = actions.add_parser("monitor")
    monitor.add_argument("--config", required=True)
    monitor.add_argument("--input", required=True)
    monitor.add_argument("--database", required=True)
    monitor_status = actions.add_parser("monitor-status")
    monitor_status.add_argument("--database", required=True)
    monitor_status.add_argument("--report-id", required=True)
    validate_runner = actions.add_parser("validate-runner-config")
    validate_runner.add_argument("--config", required=True)
    run_job = actions.add_parser("run-job")
    run_job.add_argument("--config", required=True)
    run_job.add_argument("--input", required=True)
    run_job.add_argument("--database", required=True)
    run_status = actions.add_parser("run-status")
    run_status.add_argument("--database", required=True)
    run_status.add_argument("--request-id", required=True)
    validate_control = actions.add_parser("validate-control-config")
    validate_control.add_argument("--config", required=True)
    prepare_run = actions.add_parser("prepare-run")
    prepare_run.add_argument("--runner-config", required=True)
    prepare_run.add_argument("--input", required=True)
    prepare_run.add_argument("--database", required=True)
    approval = actions.add_parser("approval")
    approval.add_argument("--config", required=True)
    approval.add_argument("--input", required=True)
    approval.add_argument("--database", required=True)
    kill_switch = actions.add_parser("kill-switch")
    kill_switch.add_argument("--config", required=True)
    kill_switch.add_argument("--input", required=True)
    kill_switch.add_argument("--database", required=True)
    cancellation = actions.add_parser("cancellation")
    cancellation.add_argument("--config", required=True)
    cancellation.add_argument("--input", required=True)
    cancellation.add_argument("--database", required=True)
    incident = actions.add_parser("incident")
    incident.add_argument("--config", required=True)
    incident.add_argument("--input", required=True)
    incident.add_argument("--database", required=True)
    control_status = actions.add_parser("control-status")
    control_status.add_argument("--config", required=True)
    control_status.add_argument("--database", required=True)
    control_status.add_argument("--as-of", required=True)
    control_status.add_argument("--request-id")
    controlled_run = actions.add_parser("controlled-run")
    controlled_run.add_argument("--runner-config", required=True)
    controlled_run.add_argument("--control-config", required=True)
    controlled_run.add_argument("--input", required=True)
    controlled_run.add_argument("--database", required=True)
    validate_resilience = actions.add_parser("validate-resilience-config")
    validate_resilience.add_argument("--config", required=True)
    backup_database = actions.add_parser("backup-database")
    backup_database.add_argument("--config", required=True)
    backup_database.add_argument("--input", required=True)
    backup_database.add_argument("--database", required=True)
    verify_restore = actions.add_parser("verify-restore")
    verify_restore.add_argument("--config", required=True)
    verify_restore.add_argument("--input", required=True)
    verify_restore.add_argument("--database", required=True)
    retention_status = actions.add_parser("retention-status")
    retention_status.add_argument("--config", required=True)
    retention_status.add_argument("--database", required=True)
    retention_status.add_argument("--as-of", required=True)
    validate_release = actions.add_parser("validate-release-config")
    validate_release.add_argument("--config", required=True)
    release_evidence = actions.add_parser("release-evidence")
    release_evidence.add_argument("--config", required=True)
    release_evidence.add_argument("--input", required=True)
    release_evidence.add_argument("--database", required=True)
    release_status = actions.add_parser("release-status")
    release_status.add_argument("--database", required=True)
    release_status.add_argument("--bundle-id", required=True)
    validate_campaign = actions.add_parser("validate-campaign-config")
    validate_campaign.add_argument("--config", required=True)
    shadow_campaign = actions.add_parser("shadow-campaign")
    shadow_campaign.add_argument("--config", required=True)
    shadow_campaign.add_argument("--input", required=True)
    shadow_campaign.add_argument("--database", required=True)
    campaign_status = actions.add_parser("campaign-status")
    campaign_status.add_argument("--database", required=True)
    campaign_status.add_argument("--report-id", required=True)
    validate_observation = actions.add_parser("validate-observation-plan-config")
    validate_observation.add_argument("--config", required=True)
    register_observation = actions.add_parser("register-observation-plan")
    register_observation.add_argument("--config", required=True)
    register_observation.add_argument("--input", required=True)
    register_observation.add_argument("--database", required=True)
    observation_status = actions.add_parser("observation-plan-status")
    observation_status.add_argument("--database", required=True)
    observation_status.add_argument("--plan-id", required=True)
    reconcile_observation = actions.add_parser("reconcile-observation-plan")
    reconcile_observation.add_argument("--config", required=True)
    reconcile_observation.add_argument("--input", required=True)
    reconcile_observation.add_argument("--database", required=True)
    reconciliation_status = actions.add_parser("observation-reconciliation-status")
    reconciliation_status.add_argument("--database", required=True)
    reconciliation_status.add_argument("--reconciliation-id", required=True)
    validate_audit = actions.add_parser("validate-observation-audit-config")
    validate_audit.add_argument("--config", required=True)
    audit_packet = actions.add_parser("observation-audit-packet")
    audit_packet.add_argument("--config", required=True)
    audit_packet.add_argument("--input", required=True)
    audit_packet.add_argument("--database", required=True)
    audit_status = actions.add_parser("observation-audit-status")
    audit_status.add_argument("--database", required=True)
    audit_status.add_argument("--packet-id", required=True)
    validate_audit_export = actions.add_parser("validate-observation-audit-export-config")
    validate_audit_export.add_argument("--config", required=True)
    audit_export = actions.add_parser("observation-audit-export")
    audit_export.add_argument("--config", required=True)
    audit_export.add_argument("--input", required=True)
    audit_export.add_argument("--database", required=True)
    verify_audit_export = actions.add_parser("verify-observation-audit-export")
    verify_audit_export.add_argument("--config", required=True)
    verify_audit_export.add_argument("--input", required=True)
    verify_audit_export.add_argument("--database", required=True)
    audit_export_status = actions.add_parser("observation-audit-export-status")
    audit_export_status.add_argument("--config", required=True)
    audit_export_status.add_argument("--database", required=True)
    audit_export_status.add_argument("--export-id", required=True)
    validate_audit_review = actions.add_parser("validate-observation-audit-review-config")
    validate_audit_review.add_argument("--config", required=True)
    audit_review = actions.add_parser("observation-audit-review")
    audit_review.add_argument("--config", required=True)
    audit_review.add_argument("--input", required=True)
    audit_review.add_argument("--database", required=True)
    audit_review_status = actions.add_parser("observation-audit-review-status")
    audit_review_status.add_argument("--config", required=True)
    audit_review_status.add_argument("--database", required=True)
    audit_review_status.add_argument("--export-id", required=True)
    validate_review_export = actions.add_parser("validate-observation-audit-review-export-config")
    validate_review_export.add_argument("--config", required=True)
    review_export = actions.add_parser("observation-audit-review-export")
    review_export.add_argument("--config", required=True)
    review_export.add_argument("--input", required=True)
    review_export.add_argument("--database", required=True)
    verify_review_export = actions.add_parser("verify-observation-audit-review-export")
    verify_review_export.add_argument("--config", required=True)
    verify_review_export.add_argument("--input", required=True)
    verify_review_export.add_argument("--database", required=True)
    review_export_status = actions.add_parser("observation-audit-review-export-status")
    review_export_status.add_argument("--config", required=True)
    review_export_status.add_argument("--database", required=True)
    review_export_status.add_argument("--bundle-id", required=True)
    validate_review_catalog = actions.add_parser("validate-observation-audit-review-catalog-config")
    validate_review_catalog.add_argument("--config", required=True)
    review_catalog = actions.add_parser("observation-audit-review-catalog")
    review_catalog.add_argument("--config", required=True)
    review_catalog.add_argument("--input", required=True)
    review_catalog.add_argument("--database", required=True)
    review_catalog_status = actions.add_parser("observation-audit-review-catalog-status")
    review_catalog_status.add_argument("--config", required=True)
    review_catalog_status.add_argument("--database", required=True)
    review_catalog_status.add_argument("--catalog-id", required=True)
    validate_review_plan = actions.add_parser("validate-review-catalog-plan-config")
    validate_review_plan.add_argument("--config", required=True)
    register_review_plan = actions.add_parser("register-review-catalog-plan")
    register_review_plan.add_argument("--config", required=True)
    register_review_plan.add_argument("--input", required=True)
    register_review_plan.add_argument("--database", required=True)
    review_plan_status = actions.add_parser("review-catalog-plan-status")
    review_plan_status.add_argument("--config", required=True)
    review_plan_status.add_argument("--database", required=True)
    review_plan_status.add_argument("--plan-id", required=True)
    reconcile_review_plan = actions.add_parser("reconcile-review-catalog-plan")
    reconcile_review_plan.add_argument("--config", required=True)
    reconcile_review_plan.add_argument("--input", required=True)
    reconcile_review_plan.add_argument("--database", required=True)
    review_reconciliation_status = actions.add_parser("review-catalog-reconciliation-status")
    review_reconciliation_status.add_argument("--config", required=True)
    review_reconciliation_status.add_argument("--database", required=True)
    review_reconciliation_status.add_argument("--reconciliation-id", required=True)
    validate_prospective = actions.add_parser("validate-prospective-review-plan-config")
    validate_prospective.add_argument("--config", required=True)
    register_prospective = actions.add_parser("register-prospective-review-plan")
    register_prospective.add_argument("--config", required=True)
    register_prospective.add_argument("--input", required=True)
    register_prospective.add_argument("--database", required=True)
    bind_prospective = actions.add_parser("bind-prospective-review-slot")
    bind_prospective.add_argument("--config", required=True)
    bind_prospective.add_argument("--input", required=True)
    bind_prospective.add_argument("--database", required=True)
    prospective_status = actions.add_parser("prospective-review-plan-status")
    prospective_status.add_argument("--config", required=True)
    prospective_status.add_argument("--database", required=True)
    prospective_status.add_argument("--plan-id", required=True)
    validate_materialization = actions.add_parser(
        "validate-prospective-catalog-materialization-config"
    )
    validate_materialization.add_argument("--config", required=True)
    materialize = actions.add_parser("materialize-prospective-review-catalog")
    materialize.add_argument("--config", required=True)
    materialize.add_argument("--prospective-config", required=True)
    materialize.add_argument("--catalog-config", required=True)
    materialize.add_argument("--input", required=True)
    materialize.add_argument("--database", required=True)
    materialization_status = actions.add_parser("prospective-catalog-materialization-status")
    materialization_status.add_argument("--config", required=True)
    materialization_status.add_argument("--prospective-config", required=True)
    materialization_status.add_argument("--catalog-config", required=True)
    materialization_status.add_argument("--database", required=True)
    materialization_status.add_argument("--materialization-id", required=True)
    validate_chain_export = actions.add_parser("validate-prospective-chain-export-config")
    validate_chain_export.add_argument("--config", required=True)
    for command in ("prospective-chain-export", "verify-prospective-chain-export"):
        parser = actions.add_parser(command)
        parser.add_argument("--config", required=True)
        parser.add_argument("--prospective-config", required=True)
        parser.add_argument("--catalog-config", required=True)
        parser.add_argument("--materialization-config", required=True)
        parser.add_argument("--input", required=True)
        parser.add_argument("--database", required=True)
    chain_status = actions.add_parser("prospective-chain-export-status")
    chain_status.add_argument("--config", required=True)
    chain_status.add_argument("--database", required=True)
    chain_status.add_argument("--export-id", required=True)
    validate_chain_review = actions.add_parser("validate-prospective-chain-review-config")
    validate_chain_review.add_argument("--config", required=True)
    chain_review = actions.add_parser("prospective-chain-review")
    chain_review.add_argument("--config", required=True)
    chain_review.add_argument("--input", required=True)
    chain_review.add_argument("--database", required=True)
    chain_review_status = actions.add_parser("prospective-chain-review-status")
    chain_review_status.add_argument("--config", required=True)
    chain_review_status.add_argument("--database", required=True)
    chain_review_status.add_argument("--export-id", required=True)
    validate_chain_bundle = actions.add_parser("validate-prospective-chain-review-bundle-config")
    validate_chain_bundle.add_argument("--config", required=True)
    for command in (
        "prospective-chain-review-bundle",
        "verify-prospective-chain-review-bundle",
    ):
        parser = actions.add_parser(command)
        parser.add_argument("--config", required=True)
        parser.add_argument("--input", required=True)
        parser.add_argument("--database", required=True)
    chain_bundle_status = actions.add_parser("prospective-chain-review-bundle-status")
    chain_bundle_status.add_argument("--config", required=True)
    chain_bundle_status.add_argument("--database", required=True)
    chain_bundle_status.add_argument("--bundle-id", required=True)
    validate_chain_catalog = actions.add_parser("validate-prospective-chain-review-catalog-config")
    validate_chain_catalog.add_argument("--config", required=True)
    chain_catalog = actions.add_parser("prospective-chain-review-catalog")
    chain_catalog.add_argument("--config", required=True)
    chain_catalog.add_argument("--input", required=True)
    chain_catalog.add_argument("--database", required=True)
    chain_catalog_status = actions.add_parser("prospective-chain-review-catalog-status")
    chain_catalog_status.add_argument("--config", required=True)
    chain_catalog_status.add_argument("--database", required=True)
    chain_catalog_status.add_argument("--catalog-id", required=True)
    validate_chain_catalog_plan = actions.add_parser(
        "validate-prospective-chain-review-catalog-plan-config"
    )
    validate_chain_catalog_plan.add_argument("--config", required=True)
    register_chain_catalog_plan = actions.add_parser(
        "register-prospective-chain-review-catalog-plan"
    )
    register_chain_catalog_plan.add_argument("--config", required=True)
    register_chain_catalog_plan.add_argument("--catalog-config", required=True)
    register_chain_catalog_plan.add_argument("--input", required=True)
    register_chain_catalog_plan.add_argument("--database", required=True)
    chain_catalog_plan_status = actions.add_parser("prospective-chain-review-catalog-plan-status")
    chain_catalog_plan_status.add_argument("--config", required=True)
    chain_catalog_plan_status.add_argument("--catalog-config", required=True)
    chain_catalog_plan_status.add_argument("--database", required=True)
    chain_catalog_plan_status.add_argument("--plan-id", required=True)
    reconcile_chain_catalog_plan = actions.add_parser(
        "reconcile-prospective-chain-review-catalog-plan"
    )
    reconcile_chain_catalog_plan.add_argument("--config", required=True)
    reconcile_chain_catalog_plan.add_argument("--catalog-config", required=True)
    reconcile_chain_catalog_plan.add_argument("--input", required=True)
    reconcile_chain_catalog_plan.add_argument("--database", required=True)
    chain_catalog_reconciliation_status = actions.add_parser(
        "prospective-chain-review-catalog-reconciliation-status"
    )
    chain_catalog_reconciliation_status.add_argument("--config", required=True)
    chain_catalog_reconciliation_status.add_argument("--catalog-config", required=True)
    chain_catalog_reconciliation_status.add_argument("--database", required=True)
    chain_catalog_reconciliation_status.add_argument("--reconciliation-id", required=True)
    validate_review_bundle_plan = actions.add_parser(
        "validate-prospective-review-bundle-plan-config"
    )
    validate_review_bundle_plan.add_argument("--config", required=True)
    register_review_bundle_plan = actions.add_parser("register-prospective-review-bundle-plan")
    register_review_bundle_plan.add_argument("--config", required=True)
    register_review_bundle_plan.add_argument("--catalog-config", required=True)
    register_review_bundle_plan.add_argument("--input", required=True)
    register_review_bundle_plan.add_argument("--database", required=True)
    bind_review_bundle_slot = actions.add_parser("bind-prospective-review-bundle-slot")
    bind_review_bundle_slot.add_argument("--config", required=True)
    bind_review_bundle_slot.add_argument("--catalog-config", required=True)
    bind_review_bundle_slot.add_argument("--input", required=True)
    bind_review_bundle_slot.add_argument("--database", required=True)
    review_bundle_plan_status = actions.add_parser("prospective-review-bundle-plan-status")
    review_bundle_plan_status.add_argument("--config", required=True)
    review_bundle_plan_status.add_argument("--catalog-config", required=True)
    review_bundle_plan_status.add_argument("--database", required=True)
    review_bundle_plan_status.add_argument("--plan-id", required=True)
    validate_bundle_materialization = actions.add_parser(
        "validate-prospective-review-bundle-materialization-config"
    )
    validate_bundle_materialization.add_argument("--config", required=True)
    for command in (
        "materialize-prospective-review-bundle-catalog",
        "prospective-review-bundle-materialization-status",
    ):
        parser = actions.add_parser(command)
        parser.add_argument("--config", required=True)
        parser.add_argument("--plan-config", required=True)
        parser.add_argument("--catalog-plan-config", required=True)
        parser.add_argument("--catalog-config", required=True)
        parser.add_argument("--database", required=True)
        if command.startswith("materialize"):
            parser.add_argument("--input", required=True)
        else:
            parser.add_argument("--materialization-id", required=True)
    validate_bundle_chain_export = actions.add_parser(
        "validate-prospective-review-bundle-chain-export-config"
    )
    validate_bundle_chain_export.add_argument("--config", required=True)
    for command in (
        "prospective-review-bundle-chain-export",
        "verify-prospective-review-bundle-chain-export",
    ):
        parser = actions.add_parser(command)
        parser.add_argument("--config", required=True)
        parser.add_argument("--materialization-config", required=True)
        parser.add_argument("--plan-config", required=True)
        parser.add_argument("--catalog-plan-config", required=True)
        parser.add_argument("--catalog-config", required=True)
        parser.add_argument("--input", required=True)
        parser.add_argument("--database", required=True)
    bundle_chain_export_status = actions.add_parser("prospective-review-bundle-chain-export-status")
    bundle_chain_export_status.add_argument("--config", required=True)
    bundle_chain_export_status.add_argument("--database", required=True)
    bundle_chain_export_status.add_argument("--export-id", required=True)


def _object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{name} must be an object")
    return value


def _time(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("known_at must be an ISO timestamp")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("known_at must be timezone-aware")
    return result


def _string_tuple(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{name} must be an array of nonempty strings")
    if len(set(value)) != len(value):
        raise ValueError(f"{name} must not contain duplicates")
    return tuple(value)


def _string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _handle_monitor(args: argparse.Namespace) -> int:
    if args.operations_command == "validate-monitor-config":
        config = load_operations_monitor_config(args.config)
        print(canonical_json({"config_hash": config.config_hash, "valid": True}))
        return 0
    if args.operations_command == "monitor-status":
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            payload, status, count = OperationsRegistry(repository).monitor_status(args.report_id)
        print(
            canonical_json(
                {
                    "report_id": args.report_id,
                    "status": status,
                    "alert_count": count,
                    "report": json.loads(payload),
                }
            )
        )
        return 0
    config = load_operations_monitor_config(args.config)
    root = _object(
        json.loads(Path(args.input).read_text(encoding="utf-8")),
        "monitor input",
    )
    if set(root) != {"as_of", "source_revision", "jobs", "health"}:
        raise ValueError("monitor input fields are invalid")
    as_of = _time(root["as_of"])
    source_revision = root["source_revision"]
    if not isinstance(source_revision, str) or not source_revision:
        raise ValueError("monitor source revision is required")
    raw_jobs = root["jobs"]
    if not isinstance(raw_jobs, list):
        raise ValueError("monitor jobs must be an array")
    schedules = []
    cursors = []
    for raw in raw_jobs:
        job = _object(raw, "monitor job")
        if set(job) != {
            "name",
            "component",
            "mode",
            "first_due_at",
            "cadence_seconds",
            "last_completed_at",
        }:
            raise ValueError("monitor job fields are invalid")
        cadence = job["cadence_seconds"]
        if not isinstance(cadence, int) or isinstance(cadence, bool):
            raise ValueError("monitor job cadence_seconds must be an integer")
        definition = ScheduleDefinition.create(
            name=_string(job["name"], "monitor job name"),
            component=_string(job["component"], "monitor job component"),
            mode=OperationalMode(_string(job["mode"], "monitor job mode")),
            first_due_at=_time(job["first_due_at"]),
            cadence_seconds=cadence,
            config_hash=config.config_hash,
        )
        schedules.append(definition)
        last_completed = job["last_completed_at"]
        cursors.append(
            ScheduleCursor(
                definition.job_id,
                None if last_completed is None else _time(last_completed),
            )
        )
    raw_health = root["health"]
    if not isinstance(raw_health, list):
        raise ValueError("monitor health must be an array")
    health = []
    for raw in raw_health:
        item = _object(raw, "health observation")
        if set(item) != {
            "component",
            "observed_at",
            "status",
            "reasons",
            "evidence_fingerprint",
        }:
            raise ValueError("health observation fields are invalid")
        health.append(
            HealthObservation.create(
                component=_string(item["component"], "health component"),
                observed_at=_time(item["observed_at"]),
                status=HealthStatus(_string(item["status"], "health status")),
                reasons=_string_tuple(item["reasons"], "health reasons"),
                evidence_fingerprint=_string(
                    item["evidence_fingerprint"], "health evidence fingerprint"
                ),
                config_hash=config.config_hash,
            )
        )
    report, plan, alerts = OperationsMonitorEngine(config).evaluate(
        as_of=as_of,
        schedules=tuple(schedules),
        cursors=tuple(cursors),
        health=tuple(health),
        source_revision=source_revision,
    )
    with SQLiteRepository(args.database) as repository:
        repository.migrate()
        registry = OperationsRegistry(repository)
        for schedule in schedules:
            registry.insert_schedule(schedule)
        registry.insert_schedule_plan(plan)
        for observation in health:
            registry.insert_health(observation)
        for alert in alerts:
            registry.insert_alert(alert)
        registry.insert_monitor_report(report)
    print(canonical_json({"report": report, "plan": plan, "alerts": alerts}))
    return 0


def _load_run_request(
    config_path: str, input_path: str
) -> tuple[OperationsRunnerConfig, JobRunRequest]:
    config = load_operations_runner_config(config_path)
    root = _object(json.loads(Path(input_path).read_text(encoding="utf-8")), "run input")
    if set(root) != {
        "schedule_plan_id",
        "schedule_job_id",
        "due_at",
        "requested_at",
        "action",
        "target",
        "source_revision",
    }:
        raise ValueError("run input fields are invalid")
    target = root["target"]
    if target is not None and (not isinstance(target, str) or not target):
        raise ValueError("run target must be null or a nonempty string")
    request = JobRunRequest.create(
        schedule_plan_id=_string(root["schedule_plan_id"], "schedule plan ID"),
        schedule_job_id=_string(root["schedule_job_id"], "schedule job ID"),
        due_at=_time(root["due_at"]),
        requested_at=_time(root["requested_at"]),
        action=WorkerAction(_string(root["action"], "worker action")),
        target=target,
        source_revision=_string(root["source_revision"], "run source revision"),
        config_hash=config.config_hash,
    )
    return config, request


def _handle_runner(args: argparse.Namespace) -> int:
    if args.operations_command == "validate-runner-config":
        config = load_operations_runner_config(args.config)
        print(canonical_json({"config_hash": config.config_hash, "valid": True}))
        return 0
    if args.operations_command == "run-status":
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            payload, attempts = OperationsRunnerRegistry(repository).status(args.request_id)
        print(
            canonical_json(
                {
                    "request": json.loads(payload),
                    "attempts": attempts,
                    "attempt_count": len(attempts),
                }
            )
        )
        return 0
    config, request = _load_run_request(args.config, args.input)
    with SQLiteRepository(args.database) as repository:
        repository.migrate()
        registry = OperationsRunnerRegistry(repository)
        attempt = OperationsJobRunner(config, registry).run_once(request)
    print(
        canonical_json(
            {
                "request": request,
                "attempt": attempt,
                "packaged_worker_only": True,
                "shell_used": False,
                "network_used": False,
                "credential_accessed": False,
                "broker_write_performed": False,
            }
        )
    )
    return 0


def _control_input(path: str, expected: set[str]) -> dict[str, object]:
    root = _object(json.loads(Path(path).read_text(encoding="utf-8")), "control input")
    if set(root) != expected:
        raise ValueError("control input fields are invalid")
    return root


def _handle_control(args: argparse.Namespace) -> int:
    if args.operations_command == "validate-control-config":
        config = load_operations_control_config(args.config)
        print(canonical_json({"config_hash": config.config_hash, "valid": True}))
        return 0
    if args.operations_command == "prepare-run":
        _, request = _load_run_request(args.runner_config, args.input)
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            registry = OperationsRunnerRegistry(repository)
            registry.validate_due_request(request)
            registry.insert_run_request(request)
        print(canonical_json({"request": request, "prepared": True, "worker_invoked": False}))
        return 0
    control_path = args.config if hasattr(args, "config") else args.control_config
    config = load_operations_control_config(control_path)
    if args.operations_command == "control-status":
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            control_registry = OperationsControlRegistry(repository, config)
            snapshot = control_registry.snapshot(
                as_of=_time(args.as_of),
                request_id=args.request_id,
            )
            control_registry.insert_snapshot(snapshot)
        print(canonical_json({"snapshot": snapshot, "remote_control_used": False}))
        return 0
    if args.operations_command == "controlled-run":
        runner_config, request = _load_run_request(args.runner_config, args.input)
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            control = OperationsControlRegistry(repository, config)
            attempt = OperationsJobRunner(
                runner_config,
                OperationsRunnerRegistry(repository),
                control_gate=control,
            ).run_once(request)
        print(
            canonical_json(
                {
                    "request": request,
                    "attempt": attempt,
                    "control_enforced": True,
                    "remote_control_used": False,
                    "broker_write_performed": False,
                }
            )
        )
        return 0
    root = _control_input(
        args.input,
        {
            "request_id",
            "operator_id",
            "action",
            "known_at",
            "expires_at",
            "reasons",
        }
        if args.operations_command == "approval"
        else {"component", "operator_id", "action", "known_at", "reasons"}
        if args.operations_command == "kill-switch"
        else {"request_id", "operator_id", "action", "known_at", "reasons"}
        if args.operations_command == "cancellation"
        else {"alert_id", "operator_id", "action", "known_at", "reasons"},
    )
    reasons = _string_tuple(root["reasons"], "control reasons")
    operator_id = _string(root["operator_id"], "operator ID")
    known_at = _time(root["known_at"])
    with SQLiteRepository(args.database) as repository:
        repository.migrate()
        control_registry = OperationsControlRegistry(repository, config)
        if args.operations_command == "approval":
            expires = root["expires_at"]
            approval_event = ApprovalEvent.create(
                request_id=_string(root["request_id"], "request ID"),
                operator_id=operator_id,
                action=ApprovalAction(_string(root["action"], "approval action")),
                known_at=known_at,
                expires_at=None if expires is None else _time(expires),
                reasons=reasons,
                config=config,
            )
            control_registry.insert_approval(approval_event)
            output_event: object = approval_event
        elif args.operations_command == "kill-switch":
            component = root["component"]
            if component is not None and (not isinstance(component, str) or not component):
                raise ValueError("kill switch component must be null or nonempty")
            switch_event = KillSwitchEvent.create(
                component=component,
                action=SwitchAction(_string(root["action"], "switch action")),
                known_at=known_at,
                operator_id=operator_id,
                reasons=reasons,
                config=config,
            )
            control_registry.insert_kill_switch(switch_event)
            output_event = switch_event
        elif args.operations_command == "cancellation":
            cancellation_event = CancellationEvent.create(
                request_id=_string(root["request_id"], "request ID"),
                action=CancellationAction(_string(root["action"], "cancellation action")),
                known_at=known_at,
                operator_id=operator_id,
                reasons=reasons,
                config=config,
            )
            control_registry.insert_cancellation(cancellation_event)
            output_event = cancellation_event
        else:
            incident_event = IncidentEvent.create(
                alert_id=_string(root["alert_id"], "alert ID"),
                action=IncidentAction(_string(root["action"], "incident action")),
                known_at=known_at,
                operator_id=operator_id,
                reasons=reasons,
                config=config,
            )
            control_registry.insert_incident(incident_event)
            output_event = incident_event
    print(
        canonical_json({"event": output_event, "recorded": True, "operator_authenticated": False})
    )
    return 0


def _handle_resilience(args: argparse.Namespace) -> int:
    config = load_operations_resilience_config(args.config)
    if args.operations_command == "validate-resilience-config":
        print(canonical_json({"config_hash": config.config_hash, "valid": True}))
        return 0
    registry_path = Path(args.database).resolve()
    with SQLiteRepository(registry_path) as repository:
        repository.migrate()
        registry = OperationsResilienceRegistry(repository, config)
        if args.operations_command == "retention-status":
            report = registry.retention_report(_time(args.as_of))
            registry.insert_retention_report(report)
            print(
                canonical_json(
                    {
                        "report": report,
                        "deletion_performed": False,
                        "network_used": False,
                        "broker_write_performed": False,
                    }
                )
            )
            return 0
        root = _object(
            json.loads(Path(args.input).read_text(encoding="utf-8")),
            "resilience input",
        )
        service = OperationsResilienceService(config, registry)
        if args.operations_command == "backup-database":
            if set(root) != {"source_path", "known_at", "source_revision"}:
                raise ValueError("backup input fields are invalid")
            source_path = _string(root["source_path"], "backup source path")
            source = (config.workspace_root / source_path).resolve()
            if source == registry_path:
                raise ValueError("resilience registry must be separate from backup source")
            manifest = service.create_backup(
                source_path=source_path,
                known_at=_time(root["known_at"]),
                source_revision=_string(root["source_revision"], "backup source revision"),
            )
            print(
                canonical_json(
                    {
                        "manifest": manifest,
                        "source_opened_read_only": True,
                        "network_used": False,
                        "broker_write_performed": False,
                    }
                )
            )
            return 0
        if set(root) != {"backup_id", "known_at"}:
            raise ValueError("restore input fields are invalid")
        verification = service.verify_restore(
            backup_id=_string(root["backup_id"], "backup ID"),
            known_at=_time(root["known_at"]),
        )
        print(
            canonical_json(
                {
                    "verification": verification,
                    "isolated_restore_only": True,
                    "promotion_performed": False,
                    "network_used": False,
                    "broker_write_performed": False,
                }
            )
        )
        return 0


def _handle_release(args: argparse.Namespace) -> int:
    if args.operations_command == "release-status":
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            row = repository.connection.execute(
                """SELECT status, payload_json
                   FROM operations_release_evidence_bundles WHERE bundle_id = ?""",
                (args.bundle_id,),
            ).fetchone()
            if row is None:
                raise ValueError("unknown release evidence bundle")
        print(
            canonical_json(
                {
                    "bundle_id": args.bundle_id,
                    "status": str(row[0]),
                    "bundle": json.loads(str(row[1])),
                    "production_readiness_claim": False,
                    "network_used": False,
                    "broker_write_performed": False,
                    "live_trading_enabled": False,
                }
            )
        )
        return 0
    config = load_operations_release_config(args.config)
    if args.operations_command == "validate-release-config":
        print(
            canonical_json(
                {
                    "config_hash": config.config_hash,
                    "valid": True,
                    "production_readiness_claim": False,
                }
            )
        )
        return 0
    root = _control_input(
        args.input,
        {
            "as_of",
            "readiness_manifest_id",
            "monitor_report_id",
            "control_snapshot_id",
            "run_request_id",
            "backup_id",
            "restore_verification_id",
            "source_revision",
        },
    )
    with SQLiteRepository(args.database) as repository:
        repository.migrate()
        registry = OperationsReleaseRegistry(repository, config)
        bundle = registry.evaluate(
            as_of=_time(root["as_of"]),
            readiness_manifest_id=_string(root["readiness_manifest_id"], "readiness manifest ID"),
            monitor_report_id=_string(root["monitor_report_id"], "monitor report ID"),
            control_snapshot_id=_string(root["control_snapshot_id"], "control snapshot ID"),
            run_request_id=_string(root["run_request_id"], "run request ID"),
            backup_id=_string(root["backup_id"], "backup ID"),
            restore_verification_id=_string(
                root["restore_verification_id"], "restore verification ID"
            ),
            source_revision=_string(root["source_revision"], "source revision"),
        )
        inserted = registry.insert(bundle)
    print(
        canonical_json(
            {
                "bundle": bundle,
                "inserted": inserted,
                "production_readiness_claim": False,
                "network_used": False,
                "broker_write_performed": False,
                "live_trading_enabled": False,
            }
        )
    )
    return 0


def _handle_campaign(args: argparse.Namespace) -> int:
    if args.operations_command == "campaign-status":
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            row = repository.connection.execute(
                """SELECT status, payload_json FROM operations_shadow_campaign_reports
                   WHERE report_id = ?""",
                (args.report_id,),
            ).fetchone()
            if row is None:
                raise ValueError("unknown shadow campaign report")
            count_row = repository.connection.execute(
                """SELECT COUNT(*) FROM operations_shadow_campaign_windows
                   WHERE report_id = ?""",
                (args.report_id,),
            ).fetchone()
        print(
            canonical_json(
                {
                    "report_id": args.report_id,
                    "status": str(row[0]),
                    "window_count": 0 if count_row is None else int(count_row[0]),
                    "report": json.loads(str(row[1])),
                    "production_readiness_claim": False,
                    "automatic_promotion_performed": False,
                    "network_used": False,
                    "broker_write_performed": False,
                    "live_trading_enabled": False,
                }
            )
        )
        return 0
    config = load_operations_campaign_config(args.config)
    if args.operations_command == "validate-campaign-config":
        print(
            canonical_json(
                {
                    "config_hash": config.config_hash,
                    "valid": True,
                    "production_readiness_claim": False,
                    "automatic_promotion_enabled": False,
                }
            )
        )
        return 0
    root = _control_input(
        args.input,
        {
            "campaign_name",
            "start_at",
            "end_at",
            "evaluated_at",
            "windows",
            "source_revision",
        },
    )
    raw_windows = root["windows"]
    if not isinstance(raw_windows, list) or not raw_windows:
        raise ValueError("shadow campaign windows must be a nonempty array")
    requests: list[CampaignWindowRequest] = []
    for raw_window in raw_windows:
        window = _object(raw_window, "shadow campaign window")
        if set(window) != {"window_id", "expected_as_of", "bundle_id"}:
            raise ValueError("shadow campaign window fields are invalid")
        raw_bundle_id = window["bundle_id"]
        if raw_bundle_id is not None and not isinstance(raw_bundle_id, str):
            raise ValueError("shadow campaign bundle ID must be a string or null")
        requests.append(
            CampaignWindowRequest(
                _string(window["window_id"], "shadow campaign window ID"),
                _time(window["expected_as_of"]),
                raw_bundle_id,
            )
        )
    with SQLiteRepository(args.database) as repository:
        repository.migrate()
        registry = OperationsCampaignRegistry(repository, config)
        report = registry.evaluate(
            campaign_name=_string(root["campaign_name"], "campaign name"),
            start_at=_time(root["start_at"]),
            end_at=_time(root["end_at"]),
            evaluated_at=_time(root["evaluated_at"]),
            requests=tuple(requests),
            source_revision=_string(root["source_revision"], "source revision"),
        )
        inserted = registry.insert(report)
    print(
        canonical_json(
            {
                "report": report,
                "inserted": inserted,
                "production_readiness_claim": False,
                "automatic_promotion_performed": False,
                "network_used": False,
                "broker_write_performed": False,
                "live_trading_enabled": False,
            }
        )
    )
    return 0


def _handle_observation_plan(args: argparse.Namespace) -> int:
    if args.operations_command == "observation-plan-status":
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            row = repository.connection.execute(
                "SELECT status, payload_json FROM operations_observation_plans WHERE plan_id = ?",
                (args.plan_id,),
            ).fetchone()
            if row is None:
                raise ValueError("unknown observation plan")
            count = repository.connection.execute(
                "SELECT COUNT(*) FROM operations_observation_plan_windows WHERE plan_id = ?",
                (args.plan_id,),
            ).fetchone()
        print(
            canonical_json(
                {
                    "plan_id": args.plan_id,
                    "status": str(row[0]),
                    "window_count": 0 if count is None else int(count[0]),
                    "plan": json.loads(str(row[1])),
                    "production_readiness_claim": False,
                    "automatic_promotion_performed": False,
                    "network_used": False,
                    "broker_write_performed": False,
                    "live_trading_enabled": False,
                }
            )
        )
        return 0
    if args.operations_command == "observation-reconciliation-status":
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            row = repository.connection.execute(
                """SELECT status, payload_json
                   FROM operations_observation_plan_reconciliations
                   WHERE reconciliation_id = ?""",
                (args.reconciliation_id,),
            ).fetchone()
        if row is None:
            raise ValueError("unknown observation plan reconciliation")
        print(
            canonical_json(
                {
                    "reconciliation_id": args.reconciliation_id,
                    "status": str(row[0]),
                    "reconciliation": json.loads(str(row[1])),
                    "production_readiness_claim": False,
                    "automatic_promotion_performed": False,
                    "network_used": False,
                    "broker_write_performed": False,
                    "live_trading_enabled": False,
                }
            )
        )
        return 0
    config = load_observation_plan_config(args.config)
    if args.operations_command == "validate-observation-plan-config":
        print(
            canonical_json(
                {
                    "config_hash": config.config_hash,
                    "valid": True,
                    "production_readiness_claim": False,
                    "automatic_promotion_enabled": False,
                }
            )
        )
        return 0
    if args.operations_command == "register-observation-plan":
        root = _control_input(
            args.input,
            {
                "campaign_name",
                "registered_at",
                "start_at",
                "end_at",
                "windows",
                "source_revision",
            },
        )
        raw_windows = root["windows"]
        if not isinstance(raw_windows, list) or not raw_windows:
            raise ValueError("observation plan windows must be a nonempty array")
        windows: list[ObservationPlanWindow] = []
        for raw_window in raw_windows:
            window = _object(raw_window, "observation plan window")
            if set(window) != {"window_id", "expected_as_of"}:
                raise ValueError("observation plan window fields are invalid")
            windows.append(
                ObservationPlanWindow(
                    _string(window["window_id"], "observation plan window ID"),
                    _time(window["expected_as_of"]),
                )
            )
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            registry = ObservationPlanRegistry(repository, config)
            plan = registry.create_plan(
                campaign_name=_string(root["campaign_name"], "campaign name"),
                registered_at=_time(root["registered_at"]),
                start_at=_time(root["start_at"]),
                end_at=_time(root["end_at"]),
                windows=tuple(windows),
                source_revision=_string(root["source_revision"], "source revision"),
            )
            inserted = registry.insert_plan(plan)
        print(
            canonical_json(
                {
                    "plan": plan,
                    "inserted": inserted,
                    "production_readiness_claim": False,
                    "automatic_promotion_performed": False,
                    "network_used": False,
                    "broker_write_performed": False,
                    "live_trading_enabled": False,
                }
            )
        )
        return 0
    root = _control_input(
        args.input,
        {"plan_id", "campaign_report_id", "reconciled_at", "source_revision"},
    )
    with SQLiteRepository(args.database) as repository:
        repository.migrate()
        registry = ObservationPlanRegistry(repository, config)
        reconciliation = registry.reconcile(
            plan_id=_string(root["plan_id"], "observation plan ID"),
            campaign_report_id=_string(root["campaign_report_id"], "campaign report ID"),
            reconciled_at=_time(root["reconciled_at"]),
            source_revision=_string(root["source_revision"], "source revision"),
        )
        inserted = registry.insert_reconciliation(reconciliation)
    print(
        canonical_json(
            {
                "reconciliation": reconciliation,
                "inserted": inserted,
                "production_readiness_claim": False,
                "automatic_promotion_performed": False,
                "network_used": False,
                "broker_write_performed": False,
                "live_trading_enabled": False,
            }
        )
    )
    return 0


def _handle_observation_audit(args: argparse.Namespace) -> int:
    if args.operations_command == "observation-audit-status":
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            row = repository.connection.execute(
                """SELECT status, payload_json FROM operations_observation_audit_packets
                   WHERE packet_id = ?""",
                (args.packet_id,),
            ).fetchone()
            if row is None:
                raise ValueError("unknown observation audit packet")
            count = repository.connection.execute(
                """SELECT COUNT(*) FROM operations_observation_audit_artifacts
                   WHERE packet_id = ?""",
                (args.packet_id,),
            ).fetchone()
        print(
            canonical_json(
                {
                    "packet_id": args.packet_id,
                    "status": str(row[0]),
                    "artifact_count": 0 if count is None else int(count[0]),
                    "packet": json.loads(str(row[1])),
                    "production_readiness_claim": False,
                    "automatic_promotion_performed": False,
                    "external_attestation_performed": False,
                    "network_used": False,
                    "broker_write_performed": False,
                    "live_trading_enabled": False,
                }
            )
        )
        return 0
    config = load_observation_audit_config(args.config)
    if args.operations_command == "validate-observation-audit-config":
        print(
            canonical_json(
                {
                    "config_hash": config.config_hash,
                    "valid": True,
                    "production_readiness_claim": False,
                    "automatic_promotion_enabled": False,
                    "external_attestation_enabled": False,
                }
            )
        )
        return 0
    root = _control_input(
        args.input,
        {"reconciliation_id", "created_at", "source_revision"},
    )
    with SQLiteRepository(args.database) as repository:
        repository.migrate()
        registry = ObservationAuditRegistry(repository, config)
        packet = registry.create(
            reconciliation_id=_string(root["reconciliation_id"], "reconciliation ID"),
            created_at=_time(root["created_at"]),
            source_revision=_string(root["source_revision"], "source revision"),
        )
        inserted = registry.insert(packet)
    print(
        canonical_json(
            {
                "packet": packet,
                "inserted": inserted,
                "production_readiness_claim": False,
                "automatic_promotion_performed": False,
                "external_attestation_performed": False,
                "network_used": False,
                "broker_write_performed": False,
                "live_trading_enabled": False,
            }
        )
    )
    return 0


def _handle_observation_audit_export(args: argparse.Namespace) -> int:
    config = load_observation_audit_export_config(args.config)
    if args.operations_command == "validate-observation-audit-export-config":
        print(
            canonical_json(
                {
                    "config_hash": config.config_hash,
                    "valid": True,
                    "production_readiness_claim": False,
                    "automatic_promotion_enabled": False,
                    "signing_enabled": False,
                    "encryption_enabled": False,
                    "network_enabled": False,
                }
            )
        )
        return 0
    if args.operations_command == "observation-audit-export-status":
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            manifest, latest_status, verification_count = ObservationAuditExportRegistry(
                repository, config
            ).status(args.export_id)
        print(
            canonical_json(
                {
                    "manifest": manifest,
                    "latest_verification_status": latest_status,
                    "verification_count": verification_count,
                    "production_readiness_claim": False,
                    "automatic_promotion_performed": False,
                    "external_signature_performed": False,
                    "encryption_performed": False,
                    "network_used": False,
                    "broker_write_performed": False,
                    "live_trading_enabled": False,
                }
            )
        )
        return 0
    if args.operations_command == "observation-audit-export":
        root = _control_input(
            args.input,
            {"packet_id", "exported_at", "source_revision"},
        )
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            registry = ObservationAuditExportRegistry(repository, config)
            manifest = ObservationAuditExportService(config, registry).export(
                packet_id=_string(root["packet_id"], "audit packet ID"),
                exported_at=_time(root["exported_at"]),
                source_revision=_string(root["source_revision"], "source revision"),
            )
        payload: object = manifest
    else:
        root = _control_input(
            args.input,
            {"export_id", "verified_at", "source_revision"},
        )
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            registry = ObservationAuditExportRegistry(repository, config)
            payload = ObservationAuditExportService(config, registry).verify(
                export_id=_string(root["export_id"], "audit export ID"),
                verified_at=_time(root["verified_at"]),
                source_revision=_string(root["source_revision"], "source revision"),
            )
    print(
        canonical_json(
            {
                "evidence": payload,
                "production_readiness_claim": False,
                "automatic_promotion_performed": False,
                "external_signature_performed": False,
                "encryption_performed": False,
                "network_used": False,
                "broker_write_performed": False,
                "live_trading_enabled": False,
            }
        )
    )
    return 0


def _handle_observation_audit_review(args: argparse.Namespace) -> int:
    config = load_observation_audit_review_config(args.config)
    if args.operations_command == "validate-observation-audit-review-config":
        print(
            canonical_json(
                {
                    "config_hash": config.config_hash,
                    "valid": True,
                    "reviewer_authentication_enabled": False,
                    "consensus_enabled": False,
                    "production_readiness_claim": False,
                    "automatic_promotion_enabled": False,
                    "network_enabled": False,
                }
            )
        )
        return 0
    if args.operations_command == "observation-audit-review-status":
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            reviews, counts = ObservationAuditReviewRegistry(repository, config).status(
                args.export_id
            )
        print(
            canonical_json(
                {
                    "export_id": args.export_id,
                    "reviews": reviews,
                    "counts": counts,
                    "consensus_calculated": False,
                    "reviewers_authenticated": False,
                    "production_readiness_claim": False,
                    "automatic_promotion_performed": False,
                    "network_used": False,
                    "broker_write_performed": False,
                    "live_trading_enabled": False,
                }
            )
        )
        return 0
    root = _control_input(
        args.input,
        {
            "export_id",
            "verification_id",
            "reviewer_id",
            "reviewed_at",
            "verdict",
            "reason_codes",
            "notes",
            "supersedes_review_id",
            "source_revision",
        },
    )
    notes = root["notes"]
    supersedes = root["supersedes_review_id"]
    if not isinstance(notes, str):
        raise ValueError("audit review notes must be a string")
    if supersedes is not None and (not isinstance(supersedes, str) or not supersedes):
        raise ValueError("superseded audit review ID must be null or a nonempty string")
    with SQLiteRepository(args.database) as repository:
        repository.migrate()
        registry = ObservationAuditReviewRegistry(repository, config)
        review = registry.create(
            export_id=_string(root["export_id"], "audit export ID"),
            verification_id=_string(root["verification_id"], "audit verification ID"),
            reviewer_id=_string(root["reviewer_id"], "reviewer ID"),
            reviewed_at=_time(root["reviewed_at"]),
            verdict=AuditReviewVerdict(_string(root["verdict"], "audit review verdict")),
            reason_codes=_string_tuple(root["reason_codes"], "audit review reason codes"),
            notes=notes,
            supersedes_review_id=supersedes,
            source_revision=_string(root["source_revision"], "source revision"),
        )
        inserted = registry.insert(review)
    print(
        canonical_json(
            {
                "review": review,
                "inserted": inserted,
                "consensus_calculated": False,
                "reviewer_authenticated": False,
                "production_readiness_claim": False,
                "automatic_promotion_performed": False,
                "network_used": False,
                "broker_write_performed": False,
                "live_trading_enabled": False,
            }
        )
    )
    return 0


def _handle_observation_audit_review_export(args: argparse.Namespace) -> int:
    config = load_observation_audit_review_export_config(args.config)
    if args.operations_command == "validate-observation-audit-review-export-config":
        print(
            canonical_json(
                {
                    "config_hash": config.config_hash,
                    "valid": True,
                    "reviewers_authenticated": False,
                    "consensus_enabled": False,
                    "signing_enabled": False,
                    "encryption_enabled": False,
                    "network_enabled": False,
                    "production_readiness_claim": False,
                }
            )
        )
        return 0
    if args.operations_command == "observation-audit-review-export-status":
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            manifest, latest_status, verification_count = ObservationAuditReviewExportRegistry(
                repository, config
            ).status(args.bundle_id)
        print(
            canonical_json(
                {
                    "manifest": manifest,
                    "latest_verification_status": latest_status,
                    "verification_count": verification_count,
                    "consensus_calculated": False,
                    "reviewers_authenticated": False,
                    "external_signature_performed": False,
                    "encryption_performed": False,
                    "production_readiness_claim": False,
                    "automatic_promotion_performed": False,
                    "network_used": False,
                    "broker_write_performed": False,
                    "live_trading_enabled": False,
                }
            )
        )
        return 0
    if args.operations_command == "observation-audit-review-export":
        root = _control_input(
            args.input,
            {
                "export_id",
                "source_verification_id",
                "bundled_at",
                "source_revision",
            },
        )
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            registry = ObservationAuditReviewExportRegistry(repository, config)
            payload: object = ObservationAuditReviewExportService(config, registry).export(
                export_id=_string(root["export_id"], "audit export ID"),
                source_verification_id=_string(
                    root["source_verification_id"], "source verification ID"
                ),
                bundled_at=_time(root["bundled_at"]),
                source_revision=_string(root["source_revision"], "source revision"),
            )
    else:
        root = _control_input(
            args.input,
            {"bundle_id", "verified_at", "source_revision"},
        )
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            registry = ObservationAuditReviewExportRegistry(repository, config)
            payload = ObservationAuditReviewExportService(config, registry).verify(
                bundle_id=_string(root["bundle_id"], "review bundle ID"),
                verified_at=_time(root["verified_at"]),
                source_revision=_string(root["source_revision"], "source revision"),
            )
    print(
        canonical_json(
            {
                "evidence": payload,
                "consensus_calculated": False,
                "reviewers_authenticated": False,
                "external_signature_performed": False,
                "encryption_performed": False,
                "production_readiness_claim": False,
                "automatic_promotion_performed": False,
                "network_used": False,
                "broker_write_performed": False,
                "live_trading_enabled": False,
            }
        )
    )
    return 0


def _handle_observation_audit_review_catalog(args: argparse.Namespace) -> int:
    config = load_observation_audit_review_catalog_config(args.config)
    if args.operations_command == "validate-observation-audit-review-catalog-config":
        print(
            canonical_json(
                {
                    "config_hash": config.config_hash,
                    "valid": True,
                    "consensus_enabled": False,
                    "ranking_enabled": False,
                    "reviewers_authenticated": False,
                    "production_readiness_claim": False,
                    "automatic_promotion_enabled": False,
                    "network_enabled": False,
                }
            )
        )
        return 0
    if args.operations_command == "observation-audit-review-catalog-status":
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            catalog = ObservationAuditReviewCatalogRegistry(repository, config).status(
                args.catalog_id
            )
        print(
            canonical_json(
                {
                    "catalog": catalog,
                    "consensus_calculated": False,
                    "ranking_calculated": False,
                    "reviewers_authenticated": False,
                    "production_readiness_claim": False,
                    "automatic_promotion_performed": False,
                    "network_used": False,
                    "broker_write_performed": False,
                    "live_trading_enabled": False,
                }
            )
        )
        return 0
    root = _control_input(
        args.input,
        {"catalog_name", "cataloged_at", "sources", "source_revision"},
    )
    raw_sources = root["sources"]
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ValueError("review catalog sources must be a nonempty array")
    sources: list[tuple[str, str]] = []
    for raw_source in raw_sources:
        source = _object(raw_source, "review catalog source")
        if set(source) != {"bundle_id", "verification_id"}:
            raise ValueError("review catalog source fields are invalid")
        sources.append(
            (
                _string(source["bundle_id"], "review bundle ID"),
                _string(source["verification_id"], "bundle verification ID"),
            )
        )
    with SQLiteRepository(args.database) as repository:
        repository.migrate()
        registry = ObservationAuditReviewCatalogRegistry(repository, config)
        catalog = registry.create(
            catalog_name=_string(root["catalog_name"], "review catalog name"),
            cataloged_at=_time(root["cataloged_at"]),
            sources=tuple(sources),
            source_revision=_string(root["source_revision"], "source revision"),
        )
        inserted = registry.insert(catalog)
    print(
        canonical_json(
            {
                "catalog": catalog,
                "inserted": inserted,
                "consensus_calculated": False,
                "ranking_calculated": False,
                "reviewers_authenticated": False,
                "production_readiness_claim": False,
                "automatic_promotion_performed": False,
                "network_used": False,
                "broker_write_performed": False,
                "live_trading_enabled": False,
            }
        )
    )
    return 0


def _handle_review_catalog_plan(args: argparse.Namespace) -> int:
    config = load_review_catalog_plan_config(args.config)
    if args.operations_command == "validate-review-catalog-plan-config":
        print(
            canonical_json(
                {
                    "config_hash": config.config_hash,
                    "valid": True,
                    "selection_unbiased_claim": False,
                    "consensus_enabled": False,
                    "production_readiness_claim": False,
                    "automatic_promotion_enabled": False,
                    "network_enabled": False,
                }
            )
        )
        return 0
    if args.operations_command == "review-catalog-plan-status":
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            payload: object = ReviewCatalogPlanRegistry(repository, config).plan(args.plan_id)
    elif args.operations_command == "review-catalog-reconciliation-status":
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            payload = ReviewCatalogPlanRegistry(repository, config).reconciliation(
                args.reconciliation_id
            )
    elif args.operations_command == "register-review-catalog-plan":
        root = _control_input(
            args.input,
            {"catalog_name", "registered_at", "sources", "source_revision"},
        )
        raw_sources = root["sources"]
        if not isinstance(raw_sources, list) or not raw_sources:
            raise ValueError("review catalog plan sources must be a nonempty array")
        sources: list[tuple[str, str]] = []
        for raw_source in raw_sources:
            source = _object(raw_source, "planned review catalog source")
            if set(source) != {"bundle_id", "verification_id"}:
                raise ValueError("planned review catalog source fields are invalid")
            sources.append(
                (
                    _string(source["bundle_id"], "planned bundle ID"),
                    _string(source["verification_id"], "planned verification ID"),
                )
            )
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            registry = ReviewCatalogPlanRegistry(repository, config)
            plan = registry.create_plan(
                catalog_name=_string(root["catalog_name"], "planned catalog name"),
                registered_at=_time(root["registered_at"]),
                sources=tuple(sources),
                source_revision=_string(root["source_revision"], "source revision"),
            )
            inserted = registry.insert_plan(plan)
        payload = {"plan": plan, "inserted": inserted}
    else:
        root = _control_input(
            args.input,
            {"plan_id", "catalog_id", "reconciled_at", "source_revision"},
        )
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            registry = ReviewCatalogPlanRegistry(repository, config)
            result = registry.reconcile(
                plan_id=_string(root["plan_id"], "review catalog plan ID"),
                catalog_id=_string(root["catalog_id"], "review catalog ID"),
                reconciled_at=_time(root["reconciled_at"]),
                source_revision=_string(root["source_revision"], "source revision"),
            )
            inserted = registry.insert_reconciliation(result)
        payload = {"reconciliation": result, "inserted": inserted}
    print(
        canonical_json(
            {
                "evidence": payload,
                "selection_unbiased_claim": False,
                "consensus_calculated": False,
                "reviewers_authenticated": False,
                "production_readiness_claim": False,
                "automatic_promotion_performed": False,
                "network_used": False,
                "broker_write_performed": False,
                "live_trading_enabled": False,
            }
        )
    )
    return 0


def _handle_prospective_review_plan(args: argparse.Namespace) -> int:
    config = load_prospective_review_plan_config(args.config)
    if args.operations_command == "validate-prospective-review-plan-config":
        payload: object = {"config_hash": config.config_hash, "valid": True}
    elif args.operations_command == "prospective-review-plan-status":
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            payload = ProspectiveReviewPlanRegistry(repository, config).status(args.plan_id)
    elif args.operations_command == "register-prospective-review-plan":
        root = _control_input(
            args.input, {"catalog_name", "registered_at", "slots", "source_revision"}
        )
        raw_slots = root["slots"]
        if not isinstance(raw_slots, list) or not raw_slots:
            raise ValueError("prospective review slots must be a nonempty array")
        slots: list[tuple[str, datetime]] = []
        for raw_slot in raw_slots:
            slot = _object(raw_slot, "prospective review slot")
            if set(slot) != {"slot_id", "expected_as_of"}:
                raise ValueError("prospective review slot fields are invalid")
            slots.append((_string(slot["slot_id"], "slot ID"), _time(slot["expected_as_of"])))
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            registry = ProspectiveReviewPlanRegistry(repository, config)
            plan = registry.create_plan(
                catalog_name=_string(root["catalog_name"], "catalog name"),
                registered_at=_time(root["registered_at"]),
                slots=tuple(slots),
                source_revision=_string(root["source_revision"], "source revision"),
            )
            inserted = registry.insert_plan(plan)
        payload = {"plan": plan, "inserted": inserted}
    else:
        root = _control_input(
            args.input,
            {"plan_id", "slot_id", "bundle_id", "verification_id", "bound_at", "source_revision"},
        )
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            registry = ProspectiveReviewPlanRegistry(repository, config)
            binding = registry.bind(
                plan_id=_string(root["plan_id"], "plan ID"),
                slot_id=_string(root["slot_id"], "slot ID"),
                bundle_id=_string(root["bundle_id"], "bundle ID"),
                verification_id=_string(root["verification_id"], "verification ID"),
                bound_at=_time(root["bound_at"]),
                source_revision=_string(root["source_revision"], "source revision"),
            )
            inserted = registry.insert_binding(binding)
        payload = {"binding": binding, "inserted": inserted}
    print(
        canonical_json(
            {
                "evidence": payload,
                "selection_unbiased_claim": False,
                "consensus_calculated": False,
                "reviewers_authenticated": False,
                "production_readiness_claim": False,
                "automatic_promotion_performed": False,
                "network_used": False,
                "broker_write_performed": False,
                "live_trading_enabled": False,
            }
        )
    )
    return 0


def _handle_prospective_catalog_materialization(args: argparse.Namespace) -> int:
    config = load_prospective_catalog_materialization_config(args.config)
    if args.operations_command == "validate-prospective-catalog-materialization-config":
        payload: object = {"config_hash": config.config_hash, "valid": True}
    else:
        prospective_config = load_prospective_review_plan_config(args.prospective_config)
        catalog_config = load_observation_audit_review_catalog_config(args.catalog_config)
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            registry = ProspectiveCatalogMaterializationRegistry(
                repository, config, prospective_config, catalog_config
            )
            if args.operations_command == "prospective-catalog-materialization-status":
                payload = registry.status(args.materialization_id)
            else:
                root = _control_input(args.input, {"plan_id", "materialized_at", "source_revision"})
                evidence = registry.materialize(
                    plan_id=_string(root["plan_id"], "prospective plan ID"),
                    materialized_at=_time(root["materialized_at"]),
                    source_revision=_string(root["source_revision"], "source revision"),
                )
                inserted = registry.insert(evidence)
                payload = {"materialization": evidence, "inserted": inserted}
    print(
        canonical_json(
            {
                "evidence": payload,
                "caller_membership_override_used": False,
                "consensus_calculated": False,
                "reviewers_authenticated": False,
                "production_readiness_claim": False,
                "automatic_promotion_performed": False,
                "network_used": False,
                "broker_write_performed": False,
                "live_trading_enabled": False,
            }
        )
    )
    return 0


def _handle_prospective_chain_review_catalog(args: argparse.Namespace) -> int:
    config = load_prospective_chain_review_catalog_config(args.config)
    if args.operations_command == "validate-prospective-chain-review-catalog-config":
        payload: object = {"config_hash": config.config_hash, "valid": True}
    else:
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            registry = ProspectiveChainReviewCatalogRegistry(repository, config)
            if args.operations_command == "prospective-chain-review-catalog-status":
                payload = registry.status(args.catalog_id)
            else:
                root = _control_input(
                    args.input,
                    {"catalog_name", "cataloged_at", "sources", "source_revision"},
                )
                raw_sources = root["sources"]
                if not isinstance(raw_sources, list) or not raw_sources:
                    raise ValueError("prospective review catalog sources must be nonempty")
                sources: list[tuple[str, str]] = []
                for raw_source in raw_sources:
                    source = _object(raw_source, "prospective review catalog source")
                    if set(source) != {"bundle_id", "verification_id"}:
                        raise ValueError("prospective review catalog source fields are invalid")
                    sources.append(
                        (
                            _string(source["bundle_id"], "prospective review bundle ID"),
                            _string(source["verification_id"], "bundle verification ID"),
                        )
                    )
                catalog = registry.create(
                    catalog_name=_string(root["catalog_name"], "catalog name"),
                    cataloged_at=_time(root["cataloged_at"]),
                    sources=tuple(sources),
                    source_revision=_string(root["source_revision"], "source revision"),
                )
                inserted = registry.insert(catalog)
                payload = {"catalog": catalog, "inserted": inserted}
    print(
        canonical_json(
            {
                "evidence": payload,
                "caller_selection_used": True,
                "reviewers_authenticated": False,
                "consensus_calculated": False,
                "ranking_calculated": False,
                "production_readiness_claim": False,
                "automatic_promotion_performed": False,
                "network_used": False,
                "broker_write_performed": False,
                "live_trading_enabled": False,
            }
        )
    )
    return 0


def _handle_prospective_chain_review_catalog_plan(args: argparse.Namespace) -> int:
    config = load_prospective_chain_review_catalog_plan_config(args.config)
    if args.operations_command == "validate-prospective-chain-review-catalog-plan-config":
        payload: object = {"config_hash": config.config_hash, "valid": True}
    else:
        catalog_config = load_prospective_chain_review_catalog_config(args.catalog_config)
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            registry = ProspectiveChainReviewCatalogPlanRegistry(repository, config, catalog_config)
            if args.operations_command == "prospective-chain-review-catalog-plan-status":
                payload = registry.plan(args.plan_id)
            elif (
                args.operations_command == "prospective-chain-review-catalog-reconciliation-status"
            ):
                payload = registry.reconciliation(args.reconciliation_id)
            elif args.operations_command == "register-prospective-chain-review-catalog-plan":
                root = _control_input(
                    args.input,
                    {"catalog_name", "registered_at", "sources", "source_revision"},
                )
                raw_sources = root["sources"]
                if not isinstance(raw_sources, list) or not raw_sources:
                    raise ValueError("prospective review catalog plan sources must be nonempty")
                sources: list[tuple[str, str]] = []
                for raw_source in raw_sources:
                    source = _object(raw_source, "prospective review catalog plan source")
                    if set(source) != {"bundle_id", "verification_id"}:
                        raise ValueError(
                            "prospective review catalog plan source fields are invalid"
                        )
                    sources.append(
                        (
                            _string(source["bundle_id"], "prospective review bundle ID"),
                            _string(source["verification_id"], "bundle verification ID"),
                        )
                    )
                plan = registry.create_plan(
                    catalog_name=_string(root["catalog_name"], "catalog name"),
                    registered_at=_time(root["registered_at"]),
                    sources=tuple(sources),
                    source_revision=_string(root["source_revision"], "source revision"),
                )
                payload = {"plan": plan, "inserted": registry.insert_plan(plan)}
            else:
                root = _control_input(
                    args.input,
                    {"plan_id", "catalog_id", "reconciled_at", "source_revision"},
                )
                result = registry.reconcile(
                    plan_id=_string(root["plan_id"], "catalog plan ID"),
                    catalog_id=_string(root["catalog_id"], "catalog ID"),
                    reconciled_at=_time(root["reconciled_at"]),
                    source_revision=_string(root["source_revision"], "source revision"),
                )
                payload = {
                    "reconciliation": result,
                    "inserted": registry.insert_reconciliation(result),
                }
    print(
        canonical_json(
            {
                "evidence": payload,
                "selection_unbiased_claim": False,
                "reviewers_authenticated": False,
                "consensus_calculated": False,
                "ranking_calculated": False,
                "production_readiness_claim": False,
                "automatic_promotion_performed": False,
                "network_used": False,
                "broker_write_performed": False,
                "live_trading_enabled": False,
            }
        )
    )
    return 0


def _handle_prospective_review_bundle_plan(args: argparse.Namespace) -> int:
    config = load_prospective_review_bundle_plan_config(args.config)
    if args.operations_command == "validate-prospective-review-bundle-plan-config":
        payload: object = {"config_hash": config.config_hash, "valid": True}
    else:
        catalog_config = load_prospective_chain_review_catalog_config(args.catalog_config)
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            registry = ProspectiveReviewBundlePlanRegistry(repository, config, catalog_config)
            if args.operations_command == "prospective-review-bundle-plan-status":
                payload = registry.status(args.plan_id)
            elif args.operations_command == "register-prospective-review-bundle-plan":
                root = _control_input(
                    args.input,
                    {"catalog_name", "registered_at", "slots", "source_revision"},
                )
                raw_slots = root["slots"]
                if not isinstance(raw_slots, list) or not raw_slots:
                    raise ValueError("prospective review-bundle slots must be nonempty")
                slots: list[tuple[str, datetime]] = []
                for raw_slot in raw_slots:
                    slot = _object(raw_slot, "prospective review-bundle slot")
                    if set(slot) != {"slot_id", "expected_as_of"}:
                        raise ValueError("prospective review-bundle slot fields are invalid")
                    slots.append(
                        (
                            _string(slot["slot_id"], "review-bundle slot ID"),
                            _time(slot["expected_as_of"]),
                        )
                    )
                plan = registry.create_plan(
                    catalog_name=_string(root["catalog_name"], "catalog name"),
                    registered_at=_time(root["registered_at"]),
                    slots=tuple(slots),
                    source_revision=_string(root["source_revision"], "source revision"),
                )
                payload = {"plan": plan, "inserted": registry.insert_plan(plan)}
            else:
                root = _control_input(
                    args.input,
                    {
                        "plan_id",
                        "slot_id",
                        "bundle_id",
                        "verification_id",
                        "bound_at",
                        "source_revision",
                    },
                )
                binding = registry.bind(
                    plan_id=_string(root["plan_id"], "review-bundle plan ID"),
                    slot_id=_string(root["slot_id"], "review-bundle slot ID"),
                    bundle_id=_string(root["bundle_id"], "review bundle ID"),
                    verification_id=_string(root["verification_id"], "verification ID"),
                    bound_at=_time(root["bound_at"]),
                    source_revision=_string(root["source_revision"], "source revision"),
                )
                payload = {"binding": binding, "inserted": registry.insert_binding(binding)}
    print(
        canonical_json(
            {
                "evidence": payload,
                "timing_compliance_claim": False,
                "selection_unbiased_claim": False,
                "consensus_calculated": False,
                "production_readiness_claim": False,
                "automatic_promotion_performed": False,
                "network_used": False,
                "broker_write_performed": False,
                "live_trading_enabled": False,
            }
        )
    )
    return 0


def _handle_prospective_review_bundle_materialization(args: argparse.Namespace) -> int:
    config = load_prospective_review_bundle_materialization_config(args.config)
    if args.operations_command == "validate-prospective-review-bundle-materialization-config":
        payload: object = {"config_hash": config.config_hash, "valid": True}
    else:
        plan_config = load_prospective_review_bundle_plan_config(args.plan_config)
        catalog_plan_config = load_prospective_chain_review_catalog_plan_config(
            args.catalog_plan_config
        )
        catalog_config = load_prospective_chain_review_catalog_config(args.catalog_config)
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            registry = ProspectiveReviewBundleMaterializationRegistry(
                repository, config, plan_config, catalog_plan_config, catalog_config
            )
            if args.operations_command == "prospective-review-bundle-materialization-status":
                payload = registry.status(args.materialization_id)
            else:
                root = _control_input(
                    args.input,
                    {"source_plan_id", "materialized_at", "cataloged_at", "source_revision"},
                )
                item = registry.materialize(
                    source_plan_id=_string(root["source_plan_id"], "source plan ID"),
                    materialized_at=_time(root["materialized_at"]),
                    cataloged_at=_time(root["cataloged_at"]),
                    source_revision=_string(root["source_revision"], "source revision"),
                )
                payload = {"materialization": item, "inserted": registry.insert(item)}
    print(
        canonical_json(
            {
                "evidence": payload,
                "caller_membership_override_used": False,
                "consensus_calculated": False,
                "production_readiness_claim": False,
                "automatic_promotion_performed": False,
                "network_used": False,
                "broker_write_performed": False,
                "live_trading_enabled": False,
            }
        )
    )
    return 0


def _handle_prospective_review_bundle_chain_export(args: argparse.Namespace) -> int:
    config = load_prospective_review_bundle_chain_export_config(args.config)
    if args.operations_command == "validate-prospective-review-bundle-chain-export-config":
        payload: object = {"config_hash": config.config_hash, "valid": True}
    elif args.operations_command == "prospective-review-bundle-chain-export-status":
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            manifest, latest, count = ProspectiveReviewBundleChainExportRegistry(
                repository, config
            ).status(args.export_id)
        payload = {
            "manifest": manifest,
            "latest_verification_status": latest,
            "verification_count": count,
        }
    else:
        materialization_config = load_prospective_review_bundle_materialization_config(
            args.materialization_config
        )
        plan_config = load_prospective_review_bundle_plan_config(args.plan_config)
        catalog_plan_config = load_prospective_chain_review_catalog_plan_config(
            args.catalog_plan_config
        )
        catalog_config = load_prospective_chain_review_catalog_config(args.catalog_config)
        expected = (
            {"materialization_id", "exported_at", "source_revision"}
            if args.operations_command == "prospective-review-bundle-chain-export"
            else {"export_id", "verified_at", "source_revision"}
        )
        root = _control_input(args.input, expected)
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            registry = ProspectiveReviewBundleChainExportRegistry(repository, config)
            materializations = ProspectiveReviewBundleMaterializationRegistry(
                repository,
                materialization_config,
                plan_config,
                catalog_plan_config,
                catalog_config,
            )
            service = ProspectiveReviewBundleChainExportService(config, registry, materializations)
            if args.operations_command == "prospective-review-bundle-chain-export":
                payload = service.export(
                    materialization_id=_string(root["materialization_id"], "materialization ID"),
                    exported_at=_time(root["exported_at"]),
                    source_revision=_string(root["source_revision"], "source revision"),
                )
            else:
                payload = service.verify(
                    export_id=_string(root["export_id"], "chain export ID"),
                    verified_at=_time(root["verified_at"]),
                    source_revision=_string(root["source_revision"], "source revision"),
                )
    print(
        canonical_json(
            {
                "evidence": payload,
                "signed": False,
                "encrypted": False,
                "external_transport_used": False,
                "reviewers_authenticated": False,
                "consensus_calculated": False,
                "production_readiness_claim": False,
                "automatic_promotion_performed": False,
                "network_used": False,
                "broker_write_performed": False,
                "live_trading_enabled": False,
            }
        )
    )
    return 0


def _handle_prospective_chain_review_bundle(args: argparse.Namespace) -> int:
    config = load_prospective_chain_review_bundle_config(args.config)
    if args.operations_command == "validate-prospective-chain-review-bundle-config":
        payload: object = {"config_hash": config.config_hash, "valid": True}
    elif args.operations_command == "prospective-chain-review-bundle-status":
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            manifest, latest, count = ProspectiveChainReviewBundleRegistry(
                repository, config
            ).status(args.bundle_id)
        payload = {
            "manifest": manifest,
            "latest_verification_status": latest,
            "verification_count": count,
        }
    else:
        expected = (
            {"export_id", "source_verification_id", "bundled_at", "source_revision"}
            if args.operations_command == "prospective-chain-review-bundle"
            else {"bundle_id", "verified_at", "source_revision"}
        )
        root = _control_input(args.input, expected)
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            registry = ProspectiveChainReviewBundleRegistry(repository, config)
            service = ProspectiveChainReviewBundleService(config, registry)
            if args.operations_command == "prospective-chain-review-bundle":
                payload = service.export(
                    export_id=_string(root["export_id"], "prospective chain export ID"),
                    source_verification_id=_string(
                        root["source_verification_id"], "source verification ID"
                    ),
                    bundled_at=_time(root["bundled_at"]),
                    source_revision=_string(root["source_revision"], "source revision"),
                )
            else:
                payload = service.verify(
                    bundle_id=_string(root["bundle_id"], "prospective review bundle ID"),
                    verified_at=_time(root["verified_at"]),
                    source_revision=_string(root["source_revision"], "source revision"),
                )
    print(
        canonical_json(
            {
                "evidence": payload,
                "signed": False,
                "encrypted": False,
                "external_transport_used": False,
                "reviewers_authenticated": False,
                "consensus_calculated": False,
                "production_readiness_claim": False,
                "automatic_promotion_performed": False,
                "network_used": False,
                "broker_write_performed": False,
                "live_trading_enabled": False,
            }
        )
    )
    return 0


def _handle_prospective_chain_review(args: argparse.Namespace) -> int:
    config = load_prospective_chain_review_config(args.config)
    if args.operations_command == "validate-prospective-chain-review-config":
        payload: object = {"config_hash": config.config_hash, "valid": True}
    elif args.operations_command == "prospective-chain-review-status":
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            reviews, counts = ProspectiveChainReviewRegistry(repository, config).status(
                args.export_id
            )
        payload = {"export_id": args.export_id, "reviews": reviews, "counts": counts}
    else:
        root = _control_input(
            args.input,
            {
                "export_id",
                "verification_id",
                "reviewer_id",
                "reviewed_at",
                "verdict",
                "reason_codes",
                "notes",
                "supersedes_review_id",
                "source_revision",
            },
        )
        notes = root["notes"]
        supersedes = root["supersedes_review_id"]
        if not isinstance(notes, str):
            raise ValueError("prospective chain review notes must be a string")
        if supersedes is not None and (not isinstance(supersedes, str) or not supersedes):
            raise ValueError("superseded prospective chain review ID is invalid")
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            registry = ProspectiveChainReviewRegistry(repository, config)
            review = registry.create(
                export_id=_string(root["export_id"], "prospective chain export ID"),
                verification_id=_string(
                    root["verification_id"], "prospective chain verification ID"
                ),
                reviewer_id=_string(root["reviewer_id"], "reviewer ID"),
                reviewed_at=_time(root["reviewed_at"]),
                verdict=ProspectiveChainReviewVerdict(
                    _string(root["verdict"], "prospective chain review verdict")
                ),
                reason_codes=_string_tuple(
                    root["reason_codes"], "prospective chain review reason codes"
                ),
                notes=notes,
                supersedes_review_id=supersedes,
                source_revision=_string(root["source_revision"], "source revision"),
            )
            inserted = registry.insert(review)
        payload = {"review": review, "inserted": inserted}
    print(
        canonical_json(
            {
                "evidence": payload,
                "reviewer_authenticated": False,
                "consensus_calculated": False,
                "production_readiness_claim": False,
                "automatic_promotion_performed": False,
                "network_used": False,
                "broker_write_performed": False,
                "live_trading_enabled": False,
            }
        )
    )
    return 0


def _handle_prospective_chain_export(args: argparse.Namespace) -> int:
    config = load_prospective_chain_export_config(args.config)
    if args.operations_command == "validate-prospective-chain-export-config":
        payload: object = {"config_hash": config.config_hash, "valid": True}
    elif args.operations_command == "prospective-chain-export-status":
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            manifest, latest, count = ProspectiveChainExportRegistry(repository, config).status(
                args.export_id
            )
        payload = {
            "manifest": manifest,
            "latest_verification_status": latest,
            "verification_count": count,
        }
    else:
        prospective_config = load_prospective_review_plan_config(args.prospective_config)
        catalog_config = load_observation_audit_review_catalog_config(args.catalog_config)
        materialization_config = load_prospective_catalog_materialization_config(
            args.materialization_config
        )
        expected = (
            {"materialization_id", "exported_at", "source_revision"}
            if args.operations_command == "prospective-chain-export"
            else {"export_id", "verified_at", "source_revision"}
        )
        root = _control_input(args.input, expected)
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            export_registry = ProspectiveChainExportRegistry(repository, config)
            materializations = ProspectiveCatalogMaterializationRegistry(
                repository, materialization_config, prospective_config, catalog_config
            )
            service = ProspectiveChainExportService(config, export_registry, materializations)
            if args.operations_command == "prospective-chain-export":
                payload = service.export(
                    materialization_id=_string(root["materialization_id"], "materialization ID"),
                    exported_at=_time(root["exported_at"]),
                    source_revision=_string(root["source_revision"], "source revision"),
                )
            else:
                payload = service.verify(
                    export_id=_string(root["export_id"], "prospective chain export ID"),
                    verified_at=_time(root["verified_at"]),
                    source_revision=_string(root["source_revision"], "source revision"),
                )
    print(
        canonical_json(
            {
                "evidence": payload,
                "signed": False,
                "encrypted": False,
                "external_transport_used": False,
                "reviewers_authenticated": False,
                "consensus_calculated": False,
                "production_readiness_claim": False,
                "automatic_promotion_performed": False,
                "network_used": False,
                "broker_write_performed": False,
                "live_trading_enabled": False,
            }
        )
    )
    return 0


def handle_operations(args: argparse.Namespace) -> int:
    if args.operations_command in {
        "validate-prospective-review-bundle-chain-export-config",
        "prospective-review-bundle-chain-export",
        "verify-prospective-review-bundle-chain-export",
        "prospective-review-bundle-chain-export-status",
    }:
        return _handle_prospective_review_bundle_chain_export(args)
    if args.operations_command in {
        "validate-prospective-review-bundle-materialization-config",
        "materialize-prospective-review-bundle-catalog",
        "prospective-review-bundle-materialization-status",
    }:
        return _handle_prospective_review_bundle_materialization(args)
    if args.operations_command in {
        "validate-prospective-review-bundle-plan-config",
        "register-prospective-review-bundle-plan",
        "bind-prospective-review-bundle-slot",
        "prospective-review-bundle-plan-status",
    }:
        return _handle_prospective_review_bundle_plan(args)
    if args.operations_command in {
        "validate-prospective-chain-review-catalog-plan-config",
        "register-prospective-chain-review-catalog-plan",
        "prospective-chain-review-catalog-plan-status",
        "reconcile-prospective-chain-review-catalog-plan",
        "prospective-chain-review-catalog-reconciliation-status",
    }:
        return _handle_prospective_chain_review_catalog_plan(args)
    if args.operations_command in {
        "validate-prospective-chain-review-catalog-config",
        "prospective-chain-review-catalog",
        "prospective-chain-review-catalog-status",
    }:
        return _handle_prospective_chain_review_catalog(args)
    if args.operations_command in {
        "validate-prospective-chain-review-bundle-config",
        "prospective-chain-review-bundle",
        "verify-prospective-chain-review-bundle",
        "prospective-chain-review-bundle-status",
    }:
        return _handle_prospective_chain_review_bundle(args)
    if args.operations_command in {
        "validate-prospective-chain-review-config",
        "prospective-chain-review",
        "prospective-chain-review-status",
    }:
        return _handle_prospective_chain_review(args)
    if args.operations_command in {
        "validate-prospective-chain-export-config",
        "prospective-chain-export",
        "verify-prospective-chain-export",
        "prospective-chain-export-status",
    }:
        return _handle_prospective_chain_export(args)
    if args.operations_command in {
        "validate-prospective-catalog-materialization-config",
        "materialize-prospective-review-catalog",
        "prospective-catalog-materialization-status",
    }:
        return _handle_prospective_catalog_materialization(args)
    if args.operations_command in {
        "validate-prospective-review-plan-config",
        "register-prospective-review-plan",
        "bind-prospective-review-slot",
        "prospective-review-plan-status",
    }:
        return _handle_prospective_review_plan(args)
    if args.operations_command in {
        "validate-review-catalog-plan-config",
        "register-review-catalog-plan",
        "review-catalog-plan-status",
        "reconcile-review-catalog-plan",
        "review-catalog-reconciliation-status",
    }:
        return _handle_review_catalog_plan(args)
    if args.operations_command in {
        "validate-observation-audit-review-catalog-config",
        "observation-audit-review-catalog",
        "observation-audit-review-catalog-status",
    }:
        return _handle_observation_audit_review_catalog(args)
    if args.operations_command in {
        "validate-observation-audit-review-export-config",
        "observation-audit-review-export",
        "verify-observation-audit-review-export",
        "observation-audit-review-export-status",
    }:
        return _handle_observation_audit_review_export(args)
    if args.operations_command in {
        "validate-observation-audit-review-config",
        "observation-audit-review",
        "observation-audit-review-status",
    }:
        return _handle_observation_audit_review(args)
    if args.operations_command in {
        "validate-observation-audit-export-config",
        "observation-audit-export",
        "verify-observation-audit-export",
        "observation-audit-export-status",
    }:
        return _handle_observation_audit_export(args)
    if args.operations_command in {
        "validate-observation-audit-config",
        "observation-audit-packet",
        "observation-audit-status",
    }:
        return _handle_observation_audit(args)
    if args.operations_command in {
        "validate-observation-plan-config",
        "register-observation-plan",
        "observation-plan-status",
        "reconcile-observation-plan",
        "observation-reconciliation-status",
    }:
        return _handle_observation_plan(args)
    if args.operations_command in {
        "validate-campaign-config",
        "shadow-campaign",
        "campaign-status",
    }:
        return _handle_campaign(args)
    if args.operations_command in {
        "validate-release-config",
        "release-evidence",
        "release-status",
    }:
        return _handle_release(args)
    if args.operations_command in {
        "validate-resilience-config",
        "backup-database",
        "verify-restore",
        "retention-status",
    }:
        return _handle_resilience(args)
    if args.operations_command in {
        "validate-control-config",
        "prepare-run",
        "approval",
        "kill-switch",
        "cancellation",
        "incident",
        "control-status",
        "controlled-run",
    }:
        return _handle_control(args)
    if args.operations_command in {
        "validate-runner-config",
        "run-job",
        "run-status",
    }:
        return _handle_runner(args)
    if args.operations_command in {
        "validate-monitor-config",
        "monitor",
        "monitor-status",
    }:
        return _handle_monitor(args)
    if args.operations_command == "validate-config":
        config = load_operations_config(args.config)
        print(canonical_json({"config_hash": config.config_hash, "valid": True}))
        return 0
    if args.operations_command == "status":
        with SQLiteRepository(args.registry_database) as repository:
            repository.migrate()
            payload, status, count = OperationsRegistry(repository).status(args.manifest_id)
        print(
            canonical_json(
                {
                    "manifest_id": args.manifest_id,
                    "status": status,
                    "component_count": count,
                    "manifest": json.loads(payload),
                }
            )
        )
        return 0
    config = load_operations_config(args.config)
    input_path = Path(args.input).resolve()
    root = _object(json.loads(input_path.read_text(encoding="utf-8")), "operations input")
    if set(root) != {"known_at", "source_revision", "databases"}:
        raise ValueError("operations input fields are invalid")
    known_at = _time(root["known_at"])
    source_revision = str(root["source_revision"])
    if not source_revision:
        raise ValueError("operations source revision is required")
    databases = _object(root["databases"], "operations databases")
    if set(databases) != set(config.components):
        raise ValueError("operations input must bind every configured component")
    evidence = []
    source_paths: set[Path] = set()
    for component in config.components:
        binding = _object(databases[component], f"{component} database")
        if set(binding) != {"label", "path"}:
            raise ValueError(f"{component} database fields are invalid")
        label = binding["label"]
        raw_path_value = binding["path"]
        if not isinstance(label, str) or not label:
            raise ValueError(f"{component} database label is required")
        if not isinstance(raw_path_value, str) or not raw_path_value:
            raise ValueError(f"{component} database path is required")
        raw_path = Path(raw_path_value)
        resolved_path = raw_path if raw_path.is_absolute() else input_path.parent / raw_path
        resolved_path = resolved_path.resolve()
        source_paths.add(resolved_path)
        evidence.append(
            inspect_component(
                config,
                component=component,
                database_label=label,
                database_path=resolved_path,
                known_at=known_at,
            )
        )
    evidence_tuple = tuple(evidence)
    manifest = OperationsManifest.create(
        known_at=known_at,
        evidence=evidence_tuple,
        config_hash=config.config_hash,
        code_version=PACKAGE_VERSION,
        source_revision=source_revision,
    )
    registry_path = Path(args.registry_database).resolve()
    if registry_path in source_paths:
        raise ValueError("operations registry database must be separate from source databases")
    with SQLiteRepository(registry_path) as repository:
        repository.migrate()
        registry = OperationsRegistry(repository)
        registry.insert_manifest(manifest)
        for item in evidence_tuple:
            registry.insert_evidence(manifest.manifest_id, item)
    print(canonical_json({"manifest": manifest, "components": evidence_tuple}))
    return 0
