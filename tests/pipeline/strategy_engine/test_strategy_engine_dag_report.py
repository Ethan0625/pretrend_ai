from __future__ import annotations

from pretrend.pipeline.strategy_engine.report_context import (
    apply_report_llm_overrides as _apply_report_llm_overrides,
    build_context_lines as _build_context_lines,
    build_diagnostic_lines as _build_diagnostic_lines,
    build_evidence_lines as _build_evidence_lines,
    build_interpretation_summary as _build_interpretation_summary,
    build_text_window_lines as _build_text_window_lines,
    generate_report_llm_overrides as _generate_report_llm_overrides,
    format_group_transition_lines as _format_group_transition_lines,
    format_transition_expected as _format_transition_expected,
    format_next_step_hazard_lines as _format_next_step_hazard_lines,
    format_bias_state_line as _format_bias_state_line,
    select_interpretation_text as _select_interpretation_text,
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


def test_market_context_lines_use_horizon_text_windows() -> None:
    lines = _build_context_lines(
        "RECESSION",
        "NEUTRAL",
        "STABLE",
        long_detail={"regime_mode": "tightening", "delta_6m_z_mean": -0.42},
        mid_detail={"price_signal": "NEUTRAL", "macro_signal": "RISK_OFF", "breadth_signal": "RISK_OFF"},
        short_detail={"secondary_confirm_count": 1},
        text_windows={
            "long": {
                "text_llm_doc_count_5d": 3,
                "text_tone_mean_5d": 0.40,
                "text_top_topics_json": '[{"category":"macro","item":"fed_policy"}]',
                "text_top_tags_json": '[{"category":"policy_action","item":"hike"}]',
            },
            "mid": {
                "text_llm_doc_count_5d": 2,
                "text_tone_mean_5d": 0.00,
                "text_top_topics_json": '[{"category":"macro","item":"inflation"}]',
                "text_top_tags_json": '[]',
            },
            "short": {
                "text_llm_doc_count_5d": 1,
                "text_tone_mean_5d": -0.30,
                "text_top_topics_json": '[{"category":"macro","item":"fed_policy"}]',
                "text_top_tags_json": '[{"category":"policy_action","item":"cut"}]',
            },
        },
    )
    text = "\n".join(lines)
    assert "정책 기조는 긴축 쪽입니다." in text
    assert "delta_6m_z -0.42로 둔화 압력이 뚜렷합니다." in text
    assert "최근 60거래일 문서는 정책 부담 쪽으로 기울어 있습니다." in text
    assert "가격은 중립, 매크로는 방어, 수급은 방어 쪽입니다." in text
    assert "최근 20거래일 문서는 방향성이 강하지 않습니다." in text
    assert "보조 확인 신호는 1건입니다." in text
    assert "최근 5거래일 문서는 완화 기대를 시사합니다." in text
    assert "연준 정책" in text


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


def test_text_window_lines_render_when_signal_present() -> None:
    lines = _build_text_window_lines(
        {
            "short": {
                "text_llm_doc_count_5d": 1,
                "text_tone_mean_5d": -0.25,
                "text_top_topics_json": '[{"category":"macro","item":"fed_policy"}]',
                "text_top_tags_json": '[{"category":"policy_action","item":"cut"}]',
            },
            "mid": {
                "text_llm_doc_count_5d": 3,
                "text_tone_mean_5d": 0.0,
                "text_top_topics_json": '[{"category":"macro","item":"inflation"}]',
                "text_top_tags_json": '[]',
            },
            "long": {
                "text_llm_doc_count_5d": 4,
                "text_tone_mean_5d": 0.33,
                "text_top_topics_json": '[{"category":"macro","item":"fed_policy"}]',
                "text_top_tags_json": '[{"category":"policy_action","item":"hike"}]',
            },
        }
    )
    text = "\n".join(lines)
    assert "📝텍스트 해석" in text
    assert "장기(60D): 최근 60거래일 문서는 정책 부담 쪽으로 기울어 있습니다." in text
    assert "중기(20D): 최근 20거래일 문서는 방향성이 강하지 않습니다." in text
    assert "단기(5D): 최근 5거래일 문서는 완화 기대를 시사합니다." in text
    assert "연준 정책" in text
    assert "금리인상" in text


def test_text_window_lines_hidden_when_missing() -> None:
    assert _build_text_window_lines(None) == []


def test_report_llm_overrides_apply_when_available() -> None:
    context = [
        "🔴 장기 국면: 회복 우세 (RECOVERY)",
        "→ 회복 국면 신호가 우세합니다.",
        "",
        "🟢 중기 성향: 위험선호 (RISK_ON)",
        "→ 위험자산 선호 흐름입니다.",
        "",
        "🔵 단기 흐름: 안정 (STABLE)",
        "→ 급락 신호는 약하며 관망이 유리합니다.",
    ]
    evidence = [
        "🏛️매크로,정책", "→ 정책 기조는 완화 쪽입니다.", "",
        "💵가격", "→ 중기 가격 흐름은 방향성이 크지 않습니다.", "",
        "📈수급/구조", "→ 수급 breadth는 위험선호 쪽입니다.", "",
        "💕심리", "→ 위험선호 확인은 아직 약합니다.",
    ]
    text_lines = ["📝텍스트 해석", "→ 장기(60D): 최근 60거래일 문서는 방향성이 강하지 않습니다."]
    context2, evidence2, text2 = _apply_report_llm_overrides(
        context,
        evidence,
        text_lines,
        {
            "context_long": "회복 흐름은 유지되지만 정책 부담은 아직 남아 있습니다.",
            "evidence_macro": "정책은 완화 쪽이지만 강한 확장 신호는 아닙니다.",
            "text_summary": "최근 문서는 대체로 중립적이며 정책 이벤트 중심입니다.",
        },
    )
    assert context2[1] == "→ 회복 흐름은 유지되지만 정책 부담은 아직 남아 있습니다."
    assert evidence2[1] == "→ 정책은 완화 쪽이지만 강한 확장 신호는 아닙니다."
    assert text2[0] == "📝텍스트 해석"
    assert text2[1] == "→ 최근 문서는 대체로 중립적이며 정책 이벤트 중심입니다."


def test_report_llm_overrides_fail_open_on_error(monkeypatch) -> None:
    context = [
        "🔴 장기 국면: 회복 우세 (RECOVERY)",
        "→ 회복 국면 신호가 우세합니다.",
        "",
        "🟢 중기 성향: 위험선호 (RISK_ON)",
        "→ 위험자산 선호 흐름입니다.",
        "",
        "🔵 단기 흐름: 안정 (STABLE)",
        "→ 급락 신호는 약하며 관망이 유리합니다.",
    ]
    evidence = [
        "🏛️매크로,정책", "→ 정책 기조는 완화 쪽입니다.", "",
        "💵가격", "→ 중기 가격 흐름은 방향성이 크지 않습니다.", "",
        "📈수급/구조", "→ 수급 breadth는 위험선호 쪽입니다.", "",
        "💕심리", "→ 위험선호 확인은 아직 약합니다.",
    ]
    text_lines = ["📝텍스트 해석", "→ 장기(60D): 최근 60거래일 문서는 방향성이 강하지 않습니다."]

    def _boom(*args, **kwargs):
        raise RuntimeError("ollama down")

    monkeypatch.setattr(
        "pretrend.pipeline.strategy_engine.report_context._call_report_llm",
        _boom,
    )
    overrides = _generate_report_llm_overrides(
        long_phase="RECOVERY",
        mid_regime="RISK_ON",
        short_signal="STABLE",
        context_lines=context,
        evidence_lines=evidence,
        text_lines=text_lines,
        model="dummy",
        base_url="http://localhost:11434",
        timeout=5,
    )
    assert overrides == {}


def test_switch_lines_when_panic_and_universe_blocked() -> None:
    lines = _build_switch_lines(risk_gate=False, run_universe=False)
    assert lines[0] == "😱 단기 공황 여부: 예"
    assert lines[1] == "📈 전술 실행: 제한"


def test_switch_lines_when_normal_and_universe_enabled() -> None:
    lines = _build_switch_lines(risk_gate=True, run_universe=True)
    assert lines[0] == "😱 단기 공황 여부: 아니오"
    assert lines[1] == "📈 전술 실행: 허용"


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


def test_next_step_hazard_lines_snapshot_present() -> None:
    lines = _format_next_step_hazard_lines(
        {
            "bias_5d": "NEUTRAL_BIAS",
            "confidence_5d": 0.5,
            "bias_10d": "RISK_OFF_BIAS",
            "confidence_10d": 0.71,
            "bias_20d": "RISK_ON_BIAS",
            "confidence_20d": 0.8,
            "bias_60d": "NEUTRAL_BIAS",
            "confidence_60d": 0.6,
            "bias_120d": "RISK_OFF_BIAS",
            "confidence_120d": 0.65,
            "transition_hazard_5d": 0.2,
            "transition_hazard_10d": 0.4,
            "transition_hazard_20d": 0.6,
            "transition_hazard_60d": 0.3,
            "transition_hazard_120d": 0.1,
            "transition_expected_5d": "RECOVERY_NEUTRAL_RELIEF",
            "transition_expected_10d": "RECOVERY_NEUTRAL_RELIEF",
            "transition_expected_20d": "RECOVERY_NEUTRAL_RELIEF",
            "transition_expected_60d": "RECOVERY_NEUTRAL_RELIEF",
            "transition_expected_120d": "RECOVERY_NEUTRAL_RELIEF",
            "horizon_bias_diversity_count": 3,
            "horizon_bias_diversity_ratio_60d": 0.42,
            "horizon_conf_spread": 0.3,
        }
    )
    text = "\n".join(lines)
    assert "🧭 10D: RISK_OFF_BIAS (71%)" in text
    assert "⏱ 10D 전환위험: 40%" in text
    assert "🔭 10D 예상 전이: 장기 회복(RECOVERY) · 중기 혼조(NEUTRAL) · 단기 안도(RELIEF)" in text
    assert "🧭 지평 요약: 5D NEUTRAL_BIAS(50%) · 20D RISK_ON_BIAS(80%) · 60D NEUTRAL_BIAS(60%) · 120D RISK_OFF_BIAS(65%)" in text
    assert "🧪 분화도: diversity=3/5, recent60=42%, conf_spread=0.30" in text


def test_next_step_hazard_lines_snapshot_missing_fail_open() -> None:
    lines = _format_next_step_hazard_lines(None)
    text = "\n".join(lines)
    assert "🧭 10D: UNKNOWN (N/A)" in text
    assert "⏱ 10D 전환위험: N/A" in text
    assert "🔭 10D 예상 전이: UNKNOWN" in text
    assert "🧭 지평 요약: 5D UNKNOWN(N/A) · 20D UNKNOWN(N/A) · 60D UNKNOWN(N/A) · 120D UNKNOWN(N/A)" in text
    assert "🧪 분화도: diversity=N/A, recent60=N/A, conf_spread=N/A" in text


def test_bias_state_line_render_and_fallback() -> None:
    line = _format_bias_state_line(
        {
            "bias_state_source": "OVERLAY",
            "bias_switch_flag": True,
            "bias_switch_reason": "MID_RISK_ON",
            "bias_cooldown_left": 4,
        }
    )
    assert "source=OVERLAY" in line
    assert "switch=Y" in line
    assert "reason=MID_RISK_ON" in line
    assert "cooldown=4" in line

    fb = _format_bias_state_line(None)
    assert "source=UNKNOWN" in fb
    assert "switch=N" in fb
    assert "reason=UNKNOWN" in fb
    assert "cooldown=N/A" in fb


def test_format_transition_expected_human_readable() -> None:
    out = _format_transition_expected("RECESSION_NEUTRAL_RELIEF")
    assert out == "장기 침체(RECESSION) · 중기 혼조(NEUTRAL) · 단기 안도(RELIEF)"


def test_group_transition_lines_render_10d_summary() -> None:
    lines = _format_group_transition_lines(
        [
            {
                "asset_group": "SECTOR",
                "group_state_now": "STRONG",
                "group_expected_5d": "WEAK",
                "group_expected_10d": "NEUTRAL",
                "group_transition_hazard_5d": 0.35,
                "group_transition_hazard_10d": 0.42,
            },
            {
                "asset_group": "BOND",
                "group_state_now": "NEUTRAL",
                "group_expected_5d": "STRONG",
                "group_expected_10d": "STRONG",
                "group_transition_hazard_5d": 0.12,
                "group_transition_hazard_10d": 0.18,
            },
        ]
    )
    text = "\n".join(lines)
    assert "SECTOR: 🟢STRONG → 5D:🔴WEAK (35%) / 10D:🟡NEUTRAL (42%)" in text
    assert "BOND: 🟡NEUTRAL → 5D:🟢STRONG (12%) / 10D:🟢STRONG (18%)" in text


def test_group_transition_lines_missing_fail_open() -> None:
    lines = _format_group_transition_lines(None)
    assert lines == ["전술 그룹 전이 데이터 없음 (UNKNOWN/N/A)"]


def test_next_step_hazard_lines_10d_primary_and_four_horizon_summary() -> None:
    lines = _format_next_step_hazard_lines(
        {
            "bias_10d": "RISK_ON_BIAS",
            "confidence_10d": 0.80,
            "transition_hazard_10d": 0.15,
            "transition_expected_10d": "EXPANSION_RISK_ON_STABLE",
            "bias_5d": "NEUTRAL_BIAS",
            "confidence_5d": 0.55,
            "bias_20d": "RISK_ON_BIAS",
            "confidence_20d": 0.70,
            "bias_60d": "NEUTRAL_BIAS",
            "confidence_60d": 0.60,
            "bias_120d": "RISK_ON_BIAS",
            "confidence_120d": 0.65,
        }
    )
    assert lines[0].startswith("🧭 10D:")
    assert "RISK_ON_BIAS" in lines[0]
    assert lines[1].startswith("⏱ 10D 전환위험:")
    assert lines[2].startswith("🔭 10D 예상 전이:")
    summary_line = next((line for line in lines if line.startswith("🧭 지평 요약:")), None)
    assert summary_line is not None
    for horizon in ("5D", "20D", "60D", "120D"):
        assert horizon in summary_line
    assert "10D" not in summary_line


def test_select_interpretation_text_fallback() -> None:
    deterministic = "결정론 메시지"
    assert _select_interpretation_text(deterministic, "  LLM 해석  ") == deterministic
    assert _select_interpretation_text(deterministic, None) == deterministic
    assert _select_interpretation_text(deterministic, "   ") == deterministic


def test_build_interpretation_summary_uses_llm_text_or_falls_back() -> None:
    deterministic = "signal + text 결합 해석"
    assert _build_interpretation_summary(deterministic, "  상위 해석문  ") == deterministic
    assert _build_interpretation_summary(deterministic, None) == deterministic
