"""Read-only desktop operator surfaces."""

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

__all__ = [
    "DesktopDashboardArtifact",
    "DesktopDashboardConfig",
    "DesktopLaunchConfig",
    "DesktopLaunchStatus",
    "LaunchReadinessConfig",
    "LocalLaunchReadiness",
    "LocalOperationsStatus",
    "LocalStatusConfig",
    "ReadinessEvidence",
    "assess_local_launch_readiness",
    "inspect_desktop_launcher",
    "inspect_local_operations",
    "load_desktop_dashboard_config",
    "load_desktop_launch_config",
    "load_launch_readiness_config",
    "load_local_status_config",
    "render_desktop_dashboard",
]
