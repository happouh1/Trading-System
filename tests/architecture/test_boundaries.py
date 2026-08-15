from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_decisions_do_not_import_learning_or_outcomes() -> None:
    decisions = ROOT / "src" / "trading_system" / "decisions"
    forbidden = {"trading_system.learning", "trading_system.domain.outcomes"}
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
            if any(name == ban or name.startswith(f"{ban}.") for name in names for ban in forbidden):
                violations.append(f"{path}:{node.lineno}")
    assert not violations, f"forbidden dependency imports: {violations}"

