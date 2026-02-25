"""Backward-compat shim.

Paper execution logic moved to pretrend.pipeline.paper.execution.
"""

from pretrend.pipeline.paper.execution import StagedSellPlan, simulate_paper_execution

__all__ = ["StagedSellPlan", "simulate_paper_execution"]
