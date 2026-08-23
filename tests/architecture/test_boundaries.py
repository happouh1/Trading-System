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
