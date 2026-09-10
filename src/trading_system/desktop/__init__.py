"""Read-only desktop operator surfaces."""

from trading_system.desktop.backup_preflight import (
    BackupPreflightConfig,
    RealDatabaseBackupPreflight,
    RealDatabaseBackupPreflightState,
    assess_real_database_backup_preflight,
    load_backup_preflight_config,
)
from trading_system.desktop.dashboard import (
    DesktopDashboardArtifact,
    DesktopDashboardConfig,
    load_desktop_dashboard_config,
    render_desktop_dashboard,
)
from trading_system.desktop.launcher import (
    DesktopLaunchConfig,
    DesktopLaunchStatus,
    inspect_desktop_launcher,
    load_desktop_launch_config,
)
from trading_system.desktop.local_status import (
    LocalOperationsStatus,
    LocalStatusConfig,
    inspect_local_operations,
    load_local_status_config,
)
from trading_system.desktop.readiness import (
    LaunchReadinessConfig,
    LocalLaunchReadiness,
    ReadinessEvidence,
    assess_local_launch_readiness,
    load_launch_readiness_config,
)
from trading_system.desktop.upgrade_authorization import (
    DatabaseUpgradeReviewAssessment,
    DatabaseUpgradeReviewAttestation,
    DatabaseUpgradeReviewConfig,
    DatabaseUpgradeReviewCredential,
    DatabaseUpgradeReviewRequest,
    DatabaseUpgradeReviewState,
    build_database_upgrade_review_attestation,
    build_database_upgrade_review_credential,
    build_database_upgrade_review_request,
    database_upgrade_review_message,
    evaluate_database_upgrade_review,
    load_database_upgrade_review_config,
)
from trading_system.desktop.upgrade_plan import (
    LocalSchemaUpgradePlan,
    UpgradePlanConfig,
    build_local_schema_upgrade_plan,
    load_upgrade_plan_config,
)
from trading_system.desktop.upgrade_rehearsal import (
    UpgradeRehearsalConfig,
    UpgradeRehearsalResult,
    load_upgrade_rehearsal_config,
    rehearse_schema_upgrade,
)

__all__ = [
    "BackupPreflightConfig",
    "DatabaseUpgradeReviewAssessment",
    "DatabaseUpgradeReviewAttestation",
    "DatabaseUpgradeReviewConfig",
    "DatabaseUpgradeReviewCredential",
    "DatabaseUpgradeReviewRequest",
    "DatabaseUpgradeReviewState",
    "DesktopDashboardArtifact",
    "DesktopDashboardConfig",
    "DesktopLaunchConfig",
    "DesktopLaunchStatus",
    "LaunchReadinessConfig",
    "LocalLaunchReadiness",
    "LocalOperationsStatus",
    "LocalSchemaUpgradePlan",
    "LocalStatusConfig",
    "ReadinessEvidence",
    "RealDatabaseBackupPreflight",
    "RealDatabaseBackupPreflightState",
    "UpgradePlanConfig",
    "UpgradeRehearsalConfig",
    "UpgradeRehearsalResult",
    "assess_local_launch_readiness",
    "assess_real_database_backup_preflight",
    "build_database_upgrade_review_attestation",
    "build_database_upgrade_review_credential",
    "build_database_upgrade_review_request",
    "build_local_schema_upgrade_plan",
    "database_upgrade_review_message",
    "evaluate_database_upgrade_review",
    "inspect_desktop_launcher",
    "inspect_local_operations",
    "load_backup_preflight_config",
    "load_database_upgrade_review_config",
    "load_desktop_dashboard_config",
    "load_desktop_launch_config",
    "load_launch_readiness_config",
    "load_local_status_config",
    "load_upgrade_plan_config",
    "load_upgrade_rehearsal_config",
    "rehearse_schema_upgrade",
    "render_desktop_dashboard",
]
