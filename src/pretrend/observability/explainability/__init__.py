"""Explainability helpers for report context rendering."""

from pretrend.observability.explainability.context import (
    build_context_lines,
    build_diagnostic_lines,
    build_evidence_lines,
    generate_llm_analysis,
)
from pretrend.observability.explainability.schema import safe_json_dict

__all__ = [
    "build_context_lines",
    "build_diagnostic_lines",
    "build_evidence_lines",
    "generate_llm_analysis",
    "safe_json_dict",
]
