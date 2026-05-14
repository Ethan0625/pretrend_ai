"""Pytest configuration for bot tests.

Adds scripts/ to sys.path so that `from bot.*` imports work.
"""
import sys
from pathlib import Path

# scripts/ directory → bot sub-package
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
