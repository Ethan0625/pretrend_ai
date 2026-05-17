"""Project pytest configuration and operational test gates."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from pretrend.testing.pytest_gates import (
    GATE_POLICIES,
    gate_matches,
    marker_names_for_path,
    normalize_gate,
)

REPO_ROOT = Path(__file__).parent.resolve()


# Add scripts/ to sys.path at module load time for legacy script imports.
_scripts_dir = str(REPO_ROOT / "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--gate",
        action="store",
        default=None,
        metavar="NAME",
        help=(
            "Run a named Pretrend pytest gate: "
            "fast, contracts, runtime, dags, pre-dashboard, personal, all. "
            "Can also be set with PRETREND_PYTEST_GATE."
        ),
    )


def pytest_configure(config: pytest.Config) -> None:
    """Ensure scripts/ is in sys.path during early configuration."""
    if _scripts_dir not in sys.path:
        sys.path.insert(0, _scripts_dir)


def _normalize_gate(gate: str | None) -> str | None:
    try:
        return normalize_gate(gate)
    except ValueError as exc:
        raise pytest.UsageError(str(exc)) from exc


def _marker_names_for_path(rel_path: str) -> set[str]:
    return marker_names_for_path(rel_path)


def _gate_matches(marker_names: set[str], gate: str | None) -> bool:
    try:
        return gate_matches(marker_names, gate)
    except ValueError as exc:
        raise pytest.UsageError(str(exc)) from exc


def _relative_test_path(item: pytest.Item) -> str | None:
    path = Path(str(item.fspath)).resolve()
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return None


def _attach_path_markers(item: pytest.Item, rel_path: str) -> None:
    for marker_name in sorted(_marker_names_for_path(rel_path)):
        item.add_marker(getattr(pytest.mark, marker_name))


def _item_marker_names(item: pytest.Item) -> set[str]:
    return {marker.name for marker in item.iter_markers()}


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Attach operational markers and apply an optional named gate."""
    for item in items:
        rel_path = _relative_test_path(item)
        if rel_path is not None:
            _attach_path_markers(item, rel_path)

    gate = _normalize_gate(
        config.getoption("--gate") or os.environ.get("PRETREND_PYTEST_GATE")
    )
    if gate is None or gate == "all":
        return

    selected: list[pytest.Item] = []
    deselected: list[pytest.Item] = []
    for item in items:
        if _gate_matches(_item_marker_names(item), gate):
            selected.append(item)
        else:
            deselected.append(item)

    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = selected
