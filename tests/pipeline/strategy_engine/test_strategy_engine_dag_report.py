from __future__ import annotations

from pretrend.pipeline.strategy_engine.report_context import (
    build_context_lines as _build_context_lines,
    build_diagnostic_lines as _build_diagnostic_lines,
    build_evidence_lines as _build_evidence_lines,
    build_next_step_lines as _build_next_step_lines,
    build_switch_lines as _build_switch_lines,
)


def test_market_context_lines_include_three_horizons() -> None:
    lines = _build_context_lines("RECESSION", "NEUTRAL", "STABLE")
    text = "\n".join(lines)
    assert "🔴 장기 국면:" in text
    assert "🟢 중기 성향:" in text
    assert "🔵 단기 흐름:" in text
    assert "→ " in text
    assert lines[2] == ""
    assert lines[5] == ""


def test_market_evidence_lines_fallback_when_missing_details() -> None:
    lines = _build_evidence_lines({}, {}, {})
    assert len(lines) == 11
    assert lines[0] == "🏛️매크로,정책"
    assert lines[1] == "→ 영향 근거 없음"
    assert lines[2] == ""
    assert lines[3] == "💵가격"
    assert lines[4] == "→ 영향 근거 없음"
    assert lines[5] == ""
    assert lines[6] == "📈수급/구조"
    assert lines[7] == "→ 영향 근거 없음"
    assert lines[8] == ""
    assert lines[9] == "💕심리"
    assert lines[10] == "→ 영향 근거 없음"


def test_switch_lines_when_panic_and_universe_blocked() -> None:
    lines = _build_switch_lines(risk_gate=False, run_universe=False)
    assert lines[0] == "😱 단기 공황 여부: 예"
    assert lines[1] == "📈 전술 실행: 제한"


def test_switch_lines_when_normal_and_universe_enabled() -> None:
    lines = _build_switch_lines(risk_gate=True, run_universe=True)
    assert lines[0] == "😱 단기 공황 여부: 아니오"
    assert lines[1] == "📈 전술 실행: 허용"


def test_next_step_lines_render_1m_3m_hypothesis() -> None:
    lines = _build_next_step_lines("EXPANSION", "RISK_ON", "RELIEF")
    assert len(lines) == 2
    assert lines[0].startswith("🧭 1M:")
    assert lines[1].startswith("🧭 3M:")
    assert "RISK_ON_BIAS" in lines[0]
    assert "RISK_ON_BIAS" in lines[1]


def test_diagnostic_lines_show_quality_and_coverage() -> None:
    long_detail = {"regime_mode": "tightening"}
    mid_detail = {"price_signal": "RISK_ON", "macro_signal": "NEUTRAL", "breadth_signal": "RISK_OFF"}
    short_detail = {
        "primary_panic": False,
        "secondary_confirm_count": 1,
        "secondary_confirmations": ["smallcap_stress"],
        "risk_on_confirm": False,
    }
    lines = _build_diagnostic_lines(long_detail, mid_detail, short_detail)
    assert len(lines) == 2
    assert lines[0].startswith("🧪 12셀 품질:")
    assert "coverage=" in lines[1]
    assert "unknown=" in lines[1]
