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
