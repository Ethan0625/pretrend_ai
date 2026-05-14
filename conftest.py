"""Root pytest conftest.py — adds scripts/ to sys.path for bot module imports."""
import sys
from pathlib import Path

# Add scripts/ to sys.path at module load time (before test collection)
_scripts_dir = str(Path(__file__).parent / "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)


def pytest_configure(config):
    """Ensure scripts/ is in sys.path during early configuration."""
    if _scripts_dir not in sys.path:
        sys.path.insert(0, _scripts_dir)
