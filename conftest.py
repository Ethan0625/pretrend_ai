"""Root pytest conftest.py — adds scripts/ to sys.path for bot module imports."""
import sys
from pathlib import Path

import pytest

# Add scripts/ to sys.path at module load time (before test collection)
_scripts_dir = str(Path(__file__).parent / "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)


def pytest_configure(config):
    """Ensure scripts/ is in sys.path during early configuration."""
    if _scripts_dir not in sys.path:
        sys.path.insert(0, _scripts_dir)


def pytest_collection_modifyitems(config, items):
    """Attach P29 operational markers by test path without touching every file."""
    repo_root = Path(__file__).parent.resolve()
    for item in items:
        path = Path(str(item.fspath)).resolve()
        rel = path.relative_to(repo_root).as_posix()

        if rel.startswith("tests/archive/personal/"):
            item.add_marker(pytest.mark.personal)

        if rel.startswith("tests/api/"):
            item.add_marker(pytest.mark.contract)

        if rel.startswith("tests/dags/"):
            item.add_marker(pytest.mark.dag)
            item.add_marker(pytest.mark.contract)

        if rel.startswith("tests/models/"):
            item.add_marker(pytest.mark.db)
            item.add_marker(pytest.mark.contract)

        if rel.startswith("tests/pipeline/sync/"):
            item.add_marker(pytest.mark.db)
            item.add_marker(pytest.mark.invariant)

        if rel.startswith("tests/pipeline/research/"):
            item.add_marker(pytest.mark.invariant)

        if rel == "tests/observability/explainability/test_invariant_filter.py":
            item.add_marker(pytest.mark.invariant)

        if rel.startswith("tests/observability/similarity/"):
            item.add_marker(pytest.mark.invariant)

        if rel == "tests/pipeline/test_eod_observability_contract.py":
            item.add_marker(pytest.mark.contract)
