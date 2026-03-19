"""Backward-compat shim.

Paper trading report helpers moved to pretrend.pipeline.paper.report.
"""

from pretrend.pipeline.paper.report import (
    PAPER_RESULT_REQUIRED_FIELDS,
    build_paper_result_payload,
    format_paper_result_message,
    validate_paper_result_payload,
)

__all__ = [
    "PAPER_RESULT_REQUIRED_FIELDS",
    "build_paper_result_payload",
    "format_paper_result_message",
    "validate_paper_result_payload",
]
