"""Paper trading package."""

from .execution import simulate_paper_execution
from .report import (
    PAPER_RESULT_REQUIRED_FIELDS,
    build_paper_result_payload,
    format_paper_result_message,
    validate_paper_result_payload,
)

__all__ = [
    "simulate_paper_execution",
    "PAPER_RESULT_REQUIRED_FIELDS",
    "build_paper_result_payload",
    "format_paper_result_message",
    "validate_paper_result_payload",
]
