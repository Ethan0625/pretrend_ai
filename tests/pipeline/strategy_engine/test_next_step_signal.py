from __future__ import annotations

from pretrend.pipeline.strategy_engine.report_context import (
    build_evidence_lines as _build_evidence_lines,
    build_next_step_lines as _build_next_step_lines,
)


def test_next_step_signal_generates_4axis_evidence_lines() -> None:
    lines = _build_evidence_lines(
        {"regime_mode": "neutral", "delta_6m_z_mean": -0.13, "z_threshold": 0.3},
        {"price_signal": "RISK_ON", "breadth_signal": "RISK_OFF", "breadth_spread": -0.02},
        {"primary_relief": True, "risk_on_confirm": False},
    )
    text = "\n".join(lines)
    assert "🏛️매크로,정책" in text
    assert "💵가격" in text
    assert "📈수급/구조" in text
    assert "💕심리" in text


def test_next_step_signal_evidence_fail_open_when_missing() -> None:
    lines = _build_evidence_lines({}, {}, {})
    text = "\n".join(lines)
    assert text.count("영향 근거 없음") == 4


def test_next_step_signal_bias_off_for_recession_and_panic() -> None:
    lines = _build_next_step_lines("RECESSION", "RISK_OFF", "PANIC")
    assert "RISK_OFF_BIAS" in lines[0]
    assert "RISK_OFF_BIAS" in lines[1]
