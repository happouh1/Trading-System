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

__all__ = [
    "DesktopDashboardArtifact",
    "DesktopDashboardConfig",
    "DesktopLaunchConfig",
    "DesktopLaunchStatus",
    "inspect_desktop_launcher",
    "load_desktop_dashboard_config",
    "load_desktop_launch_config",
    "render_desktop_dashboard",
]
