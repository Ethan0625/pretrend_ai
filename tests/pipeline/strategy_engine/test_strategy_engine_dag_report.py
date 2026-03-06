from __future__ import annotations

from pretrend.pipeline.strategy_engine.report_context import (
    build_llm_analysis_payload as _build_llm_analysis_payload,
    build_risk_summary_struct as _build_risk_summary_struct,
    build_signal_confidence_struct as _build_signal_confidence_struct,
    build_trading_guidance_struct as _build_trading_guidance_struct,
    build_context_lines as _build_context_lines,
    build_diagnostic_lines as _build_diagnostic_lines,
    build_evidence_lines as _build_evidence_lines,
    build_interpretation_summary as _build_interpretation_summary,
    build_text_window_lines as _build_text_window_lines,
    generate_llm_analysis as _generate_llm_analysis,
    format_group_transition_lines as _format_group_transition_lines,
    format_transition_expected as _format_transition_expected,
    format_next_step_hazard_lines as _format_next_step_hazard_lines,
    format_risk_summary_lines as _format_risk_summary_lines,
    format_signal_confidence_lines as _format_signal_confidence_lines,
    format_trading_guidance_lines as _format_trading_guidance_lines,
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


def test_switch_lines_when_panic_and_universe_blocked() -> None:
    lines = _build_switch_lines(risk_gate=False, run_universe=False)
    assert lines[0] == "😱 단기 공황 여부: 예"
    assert lines[1] == "📈 전술 실행: 제한"


def test_switch_lines_when_normal_and_universe_enabled() -> None:
    lines = _build_switch_lines(risk_gate=True, run_universe=True)
    assert lines[0] == "😱 단기 공황 여부: 아니오"
    assert lines[1] == "📈 전술 실행: 허용"


def test_trading_guidance_priority_run_universe_wins() -> None:
    gs = _build_trading_guidance_struct(
        mid_regime="RISK_ON",
        short_signal="STABLE",
        run_universe=False,
        risk_gate=True,
        hazard_10d=0.1,
    )
    assert gs["guidance"] == "관망/실행 제한"
    assert gs["reason"] == "RUN_UNIVERSE_BLOCK"


def test_trading_guidance_priority_short_panic_wins() -> None:
    gs = _build_trading_guidance_struct(
        mid_regime="RISK_ON",
        short_signal="PANIC",
        run_universe=True,
        risk_gate=True,
        hazard_10d=0.1,
    )
    assert gs["guidance"] == "방어"
    assert gs["reason"] == "SHORT_PANIC"


def test_trading_guidance_priority_hazard_high_over_mid() -> None:
    gs = _build_trading_guidance_struct(
        mid_regime="RISK_ON",
        short_signal="STABLE",
        run_universe=True,
        risk_gate=True,
        hazard_10d=0.9,
    )
    assert gs["guidance"] == "분할 접근"
    assert gs["reason"] == "HAZARD_HIGH"


def test_confidence_label_mapping() -> None:
    low = _build_signal_confidence_struct(hazard_10d=0.9, diversity_count=4, evidence_unknown_ratio=0.1)
    assert low["level"] == "낮음"
    high = _build_signal_confidence_struct(hazard_10d=0.3, diversity_count=4, evidence_unknown_ratio=0.1)
    assert high["level"] == "높음"
    mid = _build_signal_confidence_struct(hazard_10d=0.6, diversity_count=2, evidence_unknown_ratio=0.1)
    assert mid["level"] == "중간"


def test_risk_summary_priority_mapping() -> None:
    r1 = _build_risk_summary_struct(
        run_universe=False,
        short_signal="STABLE",
        hazard_10d=0.2,
        group_rows=[{"group_state_now": "STRONG"}],
    )
    assert r1["reason"] == "RUN_UNIVERSE_BLOCK"
    r2 = _build_risk_summary_struct(
        run_universe=True,
        short_signal="PANIC",
        hazard_10d=0.2,
        group_rows=[{"group_state_now": "STRONG"}],
    )
    assert r2["reason"] == "SHORT_PANIC"


def test_behavior_lines_format() -> None:
    g = _format_trading_guidance_lines(
        {"guidance": "관망", "reason": "MID_NEUTRAL", "detail": "방향성이 뚜렷하지 않아 관망이 적절합니다."}
    )
    r = _format_risk_summary_lines({"summary": "단기 전환 가능성이 높아 추격 진입 위험이 큽니다.", "reason": "HAZARD_HIGH"})
    c = _format_signal_confidence_lines({"level": "중간", "detail": "신호가 혼재돼 중간 신뢰도로 해석합니다.", "reason": "MIXED"})
    assert g[0] == "── 투자 행동 가이드 ──"
    assert "관망" in g[1]
    assert r[0] == "── 핵심 리스크 ──"
    assert "추격 진입" in r[1]
    assert c[0] == "── 시장 신뢰도 ──"
    assert "중간" in c[1]


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


# ── 신규: LLM Analysis (2-message split) ──


def _make_payload_kwargs():
    """공통 payload kwargs for build_llm_analysis_payload tests."""
    return dict(
        decision_date="2026-03-05",
        long_phase="RECESSION",
        mid_regime="NEUTRAL",
        short_signal="RELIEF",
        long_detail={"regime_mode": "tightening", "delta_6m_z_mean": -0.10},
        mid_detail={"price_signal": "NEUTRAL", "macro_signal": "RISK_OFF"},
        short_detail={"primary_panic": False},
        action="DECREASE",
        current_ratio=0.30,
        next_ratio=0.20,
        v2_target=0.10,
        risk_gate=True,
        run_universe=True,
        tactical_by_group={
            "SECTOR": [("에너지", "XLE", 0.15), ("유틸리티", "XLU", 0.13)],
            "BOND": [("미국채20Y", "TLT", 0.05)],
        },
        sell_budget=0.10,
        sell_list=["UNG", "INDA", "XLF"],
        next_step_row={
            "bias_10d": "RISK_OFF_BIAS",
            "confidence_10d": 0.71,
            "transition_hazard_10d": 1.0,
            "transition_expected_10d": "RECESSION_NEUTRAL_RELIEF",
        },
        group_rows=[
            {"asset_group": "BOND", "group_state_now": "NEUTRAL", "group_expected_10d": "STRONG"},
        ],
        text_windows=None,
        guidance_struct={"guidance": "분할 접근", "reason": "HAZARD_HIGH", "detail": "전환 위험이 높아 분할 접근이 유리합니다."},
        risk_struct={"reason": "HAZARD_HIGH", "summary": "전환 위험이 높습니다."},
        confidence_struct={"level": "낮음", "reason": "HAZARD_HIGH", "detail": "전환 위험이 높아 신뢰도를 낮게 봅니다."},
    )


def test_build_llm_analysis_payload_structure() -> None:
    payload = _build_llm_analysis_payload(**_make_payload_kwargs())
    assert isinstance(payload, dict)
    assert payload["decision_date"] == "2026-03-05"
    assert payload["market_position"]["long_phase"] == "RECESSION"
    assert payload["market_position"]["mid_regime"] == "NEUTRAL"
    assert payload["market_position"]["short_signal"] == "RELIEF"
    assert payload["market_position"]["risk_gate"] is True
    assert payload["market_position"]["run_universe"] is True
    assert payload["allocation"]["action"] == "DECREASE"
    assert payload["allocation"]["current_ratio"] == 0.30
    assert payload["allocation"]["next_ratio"] == 0.20
    assert payload["allocation"]["v2_target"] == 0.10
    assert "SECTOR" in payload["tactical_etf"]
    assert len(payload["tactical_etf"]["SECTOR"]) == 2
    assert payload["tactical_etf"]["SECTOR"][0]["symbol"] == "XLE"
    assert payload["sell_advice"]["sell_budget"] == 0.10
    assert payload["sell_advice"]["sell_priority"] == ["UNG", "INDA", "XLF"]
    assert payload["behavior"]["guidance"]["guidance"] == "분할 접근"
    assert payload["behavior"]["risk"]["reason"] == "HAZARD_HIGH"
    assert payload["behavior"]["confidence"]["level"] == "낮음"


def test_build_llm_analysis_payload_empty_tactical() -> None:
    kwargs = _make_payload_kwargs()
    kwargs["tactical_by_group"] = {}
    payload = _build_llm_analysis_payload(**kwargs)
    assert payload["tactical_etf"] == {}


def test_generate_llm_analysis_disabled_returns_none(monkeypatch) -> None:
    monkeypatch.setenv("REPORT_LLM_ENABLED", "0")
    result = _generate_llm_analysis(
        {"dummy": "payload"},
        model="dummy",
        base_url="http://localhost:11434",
        timeout=5,
    )
    assert result is None


def test_generate_llm_analysis_fail_open_on_error(monkeypatch) -> None:
    def _boom(*args, **kwargs):
        raise RuntimeError("ollama down")

    monkeypatch.setenv("REPORT_LLM_ENABLED", "1")
    monkeypatch.setattr(
        "pretrend.pipeline.strategy_engine.report_context._get_report_ollama_client",
        _boom,
    )
    result = _generate_llm_analysis(
        {"dummy": "payload"},
        model="dummy",
        base_url="http://localhost:11434",
        timeout=5,
    )
    assert result is None


def test_generate_llm_analysis_returns_string_on_success(monkeypatch) -> None:
    class _MockResponse:
        pass

    class _MockClient:
        def __init__(self, host=None):
            pass

        def chat(self, **kwargs):
            return {"message": {"content": "1. 시장 국면: 테스트 해석문입니다."}}

    monkeypatch.setenv("REPORT_LLM_ENABLED", "1")
    monkeypatch.setattr(
        "pretrend.pipeline.strategy_engine.report_context._get_report_ollama_client",
        lambda base_url: _MockClient(host=base_url),
    )
    result = _generate_llm_analysis(
        _build_llm_analysis_payload(**_make_payload_kwargs()),
        model="test-model",
        base_url="http://localhost:11434",
        timeout=5,
    )
    assert isinstance(result, str)
    assert "시장 국면" in result
