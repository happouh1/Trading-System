from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_decisions_do_not_import_learning_or_outcomes() -> None:
    decisions = ROOT / "src" / "trading_system" / "decisions"
    forbidden = {
        "trading_system.learning",
        "trading_system.domain.outcomes",
        "trading_system.research",
    }
    violations: list[str] = []
    for path in decisions.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                names = {node.module or ""}
            else:
                continue
            forbidden_import = any(
                name == ban or name.startswith(f"{ban}.")
                for name in names
                for ban in forbidden
            )
            if forbidden_import:
                violations.append(f"{path}:{node.lineno}")
    assert not violations, f"forbidden dependency imports: {violations}"


def test_phase1_authority_does_not_import_modeling() -> None:
    violations: list[str] = []
    for package in ("decisions", "risk", "execution_sim"):
        for path in (ROOT / "src" / "trading_system" / package).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = {alias.name for alias in node.names}
                elif isinstance(node, ast.ImportFrom):
                    names = {node.module or ""}
                else:
                    continue
                if any(
                    name == "trading_system.modeling"
                    or name.startswith("trading_system.modeling.")
                    for name in names
                ):
                    violations.append(f"{path}:{node.lineno}")
    assert not violations, f"modeling imported by Phase 1 authority: {violations}"


def test_phase1_authority_does_not_import_paper_runtime() -> None:
    violations: list[str] = []
    for package in ("decisions", "risk", "execution_sim"):
        for path in (ROOT / "src" / "trading_system" / package).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = {alias.name for alias in node.names}
                elif isinstance(node, ast.ImportFrom):
                    names = {node.module or ""}
                else:
                    continue
                if any(name == "trading_system.paper" or name.startswith("trading_system.paper.")
                       for name in names):
                    violations.append(f"{path}:{node.lineno}")
    assert not violations, f"paper runtime imported by Phase 1 authority: {violations}"


def test_phase1_authority_does_not_import_webull() -> None:
    violations: list[str] = []
    for package in ("decisions", "risk", "execution_sim"):
        for path in (ROOT / "src" / "trading_system" / package).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = {alias.name for alias in node.names}
                elif isinstance(node, ast.ImportFrom):
                    names = {node.module or ""}
                else:
                    continue
                if any(name == "trading_system.webull" or name.startswith("trading_system.webull.")
                       for name in names):
                    violations.append(f"{path}:{node.lineno}")
    assert not violations, f"Webull imported by Phase 1 authority: {violations}"


def test_only_webull_transport_imports_vendor_sdk() -> None:
    violations: list[str] = []
    root = ROOT / "src" / "trading_system"
    for path in root.rglob("*.py"):
        if path.as_posix().endswith("webull/transport.py"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                names = {node.module or ""}
            else:
                continue
            if any(name == "webull" or name.startswith("webull.") for name in names):
                violations.append(f"{path}:{node.lineno}")
    assert not violations, f"vendor SDK escaped Webull transport boundary: {violations}"


def test_portfolio_research_has_no_broker_model_or_learning_dependency() -> None:
    violations: list[str] = []
    root = ROOT / "src" / "trading_system" / "portfolio"
    forbidden = {
        "trading_system.learning",
        "trading_system.modeling",
        "trading_system.paper",
        "trading_system.webull",
    }
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                names = {node.module or ""}
            else:
                continue
            if any(
                name == ban or name.startswith(f"{ban}.")
                for name in names
                for ban in forbidden
            ):
                violations.append(f"{path}:{node.lineno}")
    assert not violations, f"forbidden portfolio dependencies: {violations}"


def test_options_research_has_no_broker_model_learning_or_decision_dependency() -> None:
    violations: list[str] = []
    root = ROOT / "src" / "trading_system" / "options"
    forbidden = {
        "trading_system.decisions",
        "trading_system.learning",
        "trading_system.modeling",
        "trading_system.paper",
        "trading_system.webull",
    }
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                names = {node.module or ""}
            else:
                continue
            if any(
                name == ban or name.startswith(f"{ban}.")
                for name in names
                for ban in forbidden
            ):
                violations.append(f"{path}:{node.lineno}")
    assert not violations, f"forbidden options dependencies: {violations}"


def test_operations_control_plane_has_no_strategy_or_broker_dependency() -> None:
    violations: list[str] = []
    root = ROOT / "src" / "trading_system" / "operations"
    forbidden = {
        "trading_system.decisions",
        "trading_system.execution_sim",
        "trading_system.learning",
        "trading_system.modeling",
        "trading_system.options",
        "trading_system.paper",
        "trading_system.portfolio",
        "trading_system.risk",
        "trading_system.webull",
    }
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                names = {node.module or ""}
            else:
                continue
            if any(
                name == ban or name.startswith(f"{ban}.")
                for name in names
                for ban in forbidden
            ):
                violations.append(f"{path}:{node.lineno}")
    assert not violations, f"forbidden operations dependencies: {violations}"


def test_phase7_terminal_boundary_cannot_enter_authority_packages() -> None:
    terminal_modules = {
        "trading_system.research.range_terminal_boundary",
        (
            "trading_system.reporting."
            "reviewed_range_catalog_incident_notification_export_incident_notification"
        ),
    }
    terminal_exports = {
        "ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationConfig",
        "ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationIntent",
        "ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationRegistry",
        "ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationSummary",
        "load_reviewed_range_catalog_incident_notification_export_incident_notification_config",
    }
    violations: list[str] = []
    for package in (
        "decisions",
        "execution_sim",
        "operations",
        "options",
        "paper",
        "portfolio",
        "risk",
        "webull",
    ):
        for path in (ROOT / "src" / "trading_system" / package).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = {alias.name for alias in node.names}
                elif isinstance(node, ast.ImportFrom):
                    names = {node.module or ""}
                    if node.module == "trading_system.reporting" and any(
                        alias.name in terminal_exports for alias in node.names
                    ):
                        violations.append(f"{path}:{node.lineno}")
                else:
                    continue
                if any(
                    name == terminal or name.startswith(f"{terminal}.")
                    for name in names
                    for terminal in terminal_modules
                ):
                    violations.append(f"{path}:{node.lineno}")
    assert not violations, f"Phase 7 terminal boundary entered authority code: {violations}"


def test_phase8_confirmatory_boundary_cannot_enter_authority_packages() -> None:
    forbidden = {
        "trading_system.research.range_confirmatory_export",
        "trading_system.research.range_confirmatory_export_registry",
        "trading_system.research.range_confirmatory_report",
        "trading_system.research.range_confirmatory_report_registry",
        "trading_system.research.range_confirmatory_terminal_boundary",
        "trading_system.research.range_replication_protocol",
        "trading_system.research.range_replication_protocol_registry",
    }
    violations: list[str] = []
    for package in (
        "decisions",
        "execution_sim",
        "operations",
        "options",
        "paper",
        "portfolio",
        "risk",
        "webull",
    ):
        for path in (ROOT / "src" / "trading_system" / package).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = {alias.name for alias in node.names}
                elif isinstance(node, ast.ImportFrom):
                    names = {node.module or ""}
                else:
                    continue
                if any(
                    name == banned or name.startswith(f"{banned}.")
                    for name in names
                    for banned in forbidden
                ):
                    violations.append(f"{path}:{node.lineno}")
    assert not violations, f"Phase 8 confirmatory boundary entered authority code: {violations}"
