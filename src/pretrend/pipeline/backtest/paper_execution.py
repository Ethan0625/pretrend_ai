"""Backward-compat shim — Deprecated.

Paper execution logic moved to pretrend.pipeline.paper.execution.
신규 코드는 pretrend.pipeline.paper.execution 을 직접 사용하라.
"""

from pretrend.pipeline.paper.execution import StagedSellPlan, simulate_paper_execution

__all__ = ["StagedSellPlan", "simulate_paper_execution"]
