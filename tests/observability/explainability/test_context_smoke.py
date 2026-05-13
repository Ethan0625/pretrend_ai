from __future__ import annotations

from pretrend.observability.explainability.context import build_context_lines


def test_explainability_context_smoke_builds_lines() -> None:
    lines = build_context_lines("EXPANSION", "RISK_ON", "STABLE")

    assert lines
    assert any("장기 국면" in line for line in lines)
