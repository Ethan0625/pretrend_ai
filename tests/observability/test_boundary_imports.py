from __future__ import annotations

import ast
from pathlib import Path

import pytest


pytestmark = pytest.mark.contract


FORBIDDEN_MODULE_PREFIXES = (
    "pretrend.pipeline.backtest",
    "pretrend.pipeline.strategy_engine",
    "pretrend.pipeline.paper",
    "pretrend.pipeline.broker",
    "pretrend.backtest",
    "pretrend.paper",
    "pretrend.broker",
)


def test_observability_does_not_import_frozen_personal_modules() -> None:
    root = Path(__file__).parents[2] / "src" / "pretrend" / "observability"
    violations: list[str] = []

    for file in sorted(root.rglob("*.py")):
        tree = ast.parse(file.read_text(), filename=str(file))
        for node in ast.walk(tree):
            module = _imported_module(node)
            if module is None:
                continue
            if module.startswith(FORBIDDEN_MODULE_PREFIXES):
                violations.append(f"{file.relative_to(root.parent.parent.parent)}:{node.lineno}:{module}")

    assert violations == []


def _imported_module(node: ast.AST) -> str | None:
    if isinstance(node, ast.ImportFrom):
        return node.module
    if isinstance(node, ast.Import):
        return next(
            (
                alias.name
                for alias in node.names
                if alias.name.startswith(FORBIDDEN_MODULE_PREFIXES)
            ),
            None,
        )
    return None
