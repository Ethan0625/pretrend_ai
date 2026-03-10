from __future__ import annotations

from pretrend.pipeline.strategy_engine.report_context import (
    build_llm_analysis_payload as _build_llm_analysis_payload,
    _build_compact_llm_input,
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
            "bias_5d": "RISK_OFF_BIAS",
            "confidence_5d": 0.80,
            "bias_10d": "RISK_OFF_BIAS",
            "confidence_10d": 0.71,
            "bias_20d": "RISK_OFF_BIAS",
            "confidence_20d": 0.65,
            "bias_60d": "NEUTRAL_BIAS",
            "confidence_60d": 0.55,
            "bias_120d": "NEUTRAL_BIAS",
            "confidence_120d": 0.50,
            "transition_hazard_10d": 1.0,
            "transition_expected_10d": "RECESSION_NEUTRAL_RELIEF",
            "horizon_bias_diversity_count": 2,
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
    # market_position codes + labels
    assert payload["market_position"]["long_phase"] == "RECESSION"
    assert payload["market_position"]["long_phase_label"] == "침체 국면"
    assert payload["market_position"]["mid_regime"] == "NEUTRAL"
    assert payload["market_position"]["mid_regime_label"] == "중립"
    assert payload["market_position"]["short_signal"] == "RELIEF"
    assert payload["market_position"]["short_signal_label"] == "단기 안도"
    assert payload["market_position"]["risk_gate"] is True
    assert payload["market_position"]["run_universe"] is True
    # allocation
    assert payload["allocation"]["action"] == "DECREASE"
    assert payload["allocation"]["current_ratio"] == 0.30
    assert payload["allocation"]["next_ratio"] == 0.20
    assert payload["allocation"]["v2_target"] == 0.10
    # tactical_etf
    assert "SECTOR" in payload["tactical_etf"]
    assert len(payload["tactical_etf"]["SECTOR"]) == 2
    assert payload["tactical_etf"]["SECTOR"][0]["symbol"] == "XLE"
    # sell_advice
    assert payload["sell_advice"]["sell_budget"] == 0.10
    assert payload["sell_advice"]["sell_priority"] == ["UNG", "INDA", "XLF"]
    assert "sell_priority_note" in payload["sell_advice"]
    # behavior
    assert payload["behavior"]["guidance"]["guidance"] == "분할 접근"
    assert payload["behavior"]["risk"]["reason"] == "HAZARD_HIGH"
    assert payload["behavior"]["confidence"]["level"] == "낮음"
    # text_available (text_windows=None → False)
    assert payload["text_available"] is False
    assert payload["text_windows"] is None


def test_build_llm_analysis_payload_multihorizon_bias() -> None:
    payload = _build_llm_analysis_payload(**_make_payload_kwargs())
    ns = payload["next_step"]
    # 5개 horizon 모두 존재
    for h in ("bias_5d", "bias_10d", "bias_20d", "bias_60d", "bias_120d"):
        assert h in ns, f"{h} missing from next_step"
        assert "bias" in ns[h]
        assert "label" in ns[h]
        assert "confidence" in ns[h]
    # 단기(5D/10D/20D) = RISK_OFF_BIAS → 방어 쪽 전망
    assert ns["bias_5d"]["bias"] == "RISK_OFF_BIAS"
    assert ns["bias_5d"]["label"] == "방어 쪽 전망"
    # 중기(60D/120D) = NEUTRAL_BIAS → 중립 전망
    assert ns["bias_60d"]["bias"] == "NEUTRAL_BIAS"
    assert ns["bias_60d"]["label"] == "중립 전망"
    assert ns["bias_120d"]["label"] == "중립 전망"
    # confidence는 문자열 (None이 아님)
    assert isinstance(ns["bias_5d"]["confidence"], str)
    # backward-compat 평탄 키도 유지
    assert "bias_10d_label" in ns
    assert "confidence_10d" in ns


def test_build_llm_analysis_payload_text_available_false() -> None:
    kwargs = _make_payload_kwargs()
    kwargs["text_windows"] = None
    payload = _build_llm_analysis_payload(**kwargs)
    assert payload["text_available"] is False
    assert payload["text_windows"] is None


def test_build_llm_analysis_payload_text_available_true() -> None:
    kwargs = _make_payload_kwargs()
    kwargs["text_windows"] = {"short": {"tone": "hawkish", "doc_count": 5}}
    payload = _build_llm_analysis_payload(**kwargs)
    assert payload["text_available"] is True
    assert payload["text_windows"] is not None


def test_build_llm_analysis_payload_phase_labels() -> None:
    for phase, expected_label in [
        ("RECESSION", "침체 국면"),
        ("EXPANSION", "확장 국면"),
        ("LATE_CYCLE", "후기 국면"),
        ("SLOWDOWN", "둔화 국면"),
        ("RECOVERY", "회복 국면"),
    ]:
        kwargs = _make_payload_kwargs()
        kwargs["long_phase"] = phase
        payload = _build_llm_analysis_payload(**kwargs)
        assert payload["market_position"]["long_phase_label"] == expected_label
    for regime, expected_label in [
        ("RISK_ON", "위험선호"),
        ("RISK_OFF", "위험회피"),
        ("NEUTRAL", "중립"),
    ]:
        kwargs = _make_payload_kwargs()
        kwargs["mid_regime"] = regime
        payload = _build_llm_analysis_payload(**kwargs)
        assert payload["market_position"]["mid_regime_label"] == expected_label


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


# ── 신규: compact LLM input builder ──


def test_compact_llm_input_structure() -> None:
    payload = _build_llm_analysis_payload(**_make_payload_kwargs())
    compact = _build_compact_llm_input(payload)
    # 상위 레벨 키 존재
    for key in ("date", "regime", "horizon_bias", "allocation", "relative_strength", "behavior", "text_available"):
        assert key in compact, f"{key} missing from compact"
    # 대형 nested dict 제거됨
    assert "detail" not in compact
    assert "group_transition" not in compact
    assert "next_step" not in compact
    # regime 필드 (P3-6b: 영문 key → 한국어 key)
    assert compact["regime"]["phase"] == "침체 국면"
    assert compact["regime"]["시장심리"] == "중립"
    assert compact["regime"]["단기신호"] == "단기 안도"
    assert compact["regime"]["risk_gate"] is True
    # allocation 포맷
    assert compact["allocation"]["current"] == "30%"
    assert compact["allocation"]["next"] == "20%"
    assert compact["allocation"]["action"] == "DECREASE"


def test_compact_llm_input_horizon_conflict() -> None:
    # 5D=방어, 60D=중립 → conflict (방어 vs 중립은 not None & not equal)
    payload = _build_llm_analysis_payload(**_make_payload_kwargs())
    compact = _build_compact_llm_input(payload)
    hb = compact["horizon_bias"]
    assert hb["5d"]["label"] == "방어 쪽 전망"
    assert hb["60d"]["label"] == "중립 전망"
    # 방어 vs 중립: _is_risk_on("방어 쪽 전망")=False, _is_risk_on("중립 전망")=None → conflict=False
    assert hb["conflict_5d_vs_60d"] is False
    assert hb["has_horizon_conflict"] is False
    assert hb["conflict_pair"] == []

    # 5D=공격 vs 60D=방어 → conflict=True
    kwargs = _make_payload_kwargs()
    kwargs["next_step_row"]["bias_5d"] = "RISK_ON_BIAS"
    kwargs["next_step_row"]["bias_60d"] = "RISK_OFF_BIAS"
    payload2 = _build_llm_analysis_payload(**kwargs)
    compact2 = _build_compact_llm_input(payload2)
    assert compact2["horizon_bias"]["conflict_5d_vs_60d"] is True
    assert compact2["horizon_bias"]["has_horizon_conflict"] is True
    assert compact2["horizon_bias"]["conflict_pair"] == ["5d", "60d"]

    # 5D=방어 vs 60D=방어 → conflict=False (동일 방향)
    kwargs3 = _make_payload_kwargs()
    kwargs3["next_step_row"]["bias_5d"] = "RISK_OFF_BIAS"
    kwargs3["next_step_row"]["bias_60d"] = "RISK_OFF_BIAS"
    payload3 = _build_llm_analysis_payload(**kwargs3)
    compact3 = _build_compact_llm_input(payload3)
    assert compact3["horizon_bias"]["conflict_5d_vs_60d"] is False
    assert compact3["horizon_bias"]["has_horizon_conflict"] is False
    assert compact3["horizon_bias"]["conflict_pair"] == []


def test_compact_llm_input_sell_priority_truncated() -> None:
    kwargs = _make_payload_kwargs()
    kwargs["sell_list"] = ["UNG", "INDA", "XLF", "SLV", "XLK", "SPY", "DBA"]  # 7개
    payload = _build_llm_analysis_payload(**kwargs)
    compact = _build_compact_llm_input(payload)
    assert compact["sell_priority"] is not None
    assert len(compact["sell_priority"]) == 3
    assert compact["sell_priority"] == ["UNG", "INDA", "XLF"]  # 순서 유지

    # 빈 리스트 → None
    kwargs2 = _make_payload_kwargs()
    kwargs2["sell_list"] = []
    payload2 = _build_llm_analysis_payload(**kwargs2)
    compact2 = _build_compact_llm_input(payload2)
    assert compact2["sell_priority"] is None


def test_compact_llm_input_rs_format() -> None:
    kwargs = _make_payload_kwargs()
    kwargs["tactical_by_group"] = {
        "SECTOR": [("에너지", "XLE", 0.087), ("유틸리티", "XLU", -0.032)],
    }
    payload = _build_llm_analysis_payload(**kwargs)
    compact = _build_compact_llm_input(payload)
    rs_entries = compact["relative_strength"]["섹터"]
    assert any("+8.7%" in entry for entry in rs_entries), f"expected +8.7% in {rs_entries}"
    assert any("-3.2%" in entry for entry in rs_entries), f"expected -3.2% in {rs_entries}"


def test_compact_llm_input_text_summary() -> None:
    kwargs = _make_payload_kwargs()
    kwargs["text_windows"] = {
        "short": {
            "tone": "negative",
            "topics": ["fed_policy", "inflation", "employment", "treasury_yield"],
            "doc_count": 5,
        }
    }
    payload = _build_llm_analysis_payload(**kwargs)
    compact = _build_compact_llm_input(payload)
    assert compact["text_available"] is True
    summary = compact["text_summary"]
    assert summary is not None
    assert "short" in summary
    short = summary["short"]
    assert short["tone"] == "negative"
    assert short["doc_count"] == 5
    # 상위 3 토픽만 (4개 중 3개)
    assert len(short["topics"]) == 3
    # 한국어 레이블 변환
    assert short["topics"][0] == "연준 정책"
    assert short["topics"][1] == "인플레이션"
    assert short["topics"][2] == "고용"

    # text_windows=None → text_summary=None
    kwargs2 = _make_payload_kwargs()
    kwargs2["text_windows"] = None
    payload2 = _build_llm_analysis_payload(**kwargs2)
    compact2 = _build_compact_llm_input(payload2)
    assert compact2["text_available"] is False
    assert compact2["text_summary"] is None


# ── P3-6b: Fact Control 신규 테스트 ──


def test_compact_rs_assets_top5_present() -> None:
    """rs_assets_top5 필드가 존재하고 최대 5개이며 각 항목에 필수 키가 있다."""
    kwargs = _make_payload_kwargs()
    kwargs["tactical_by_group"] = {
        "SECTOR": [("에너지", "XLE", 0.15), ("유틸리티", "XLU", 0.08)],
        "BOND": [("미국채20Y", "TLT", 0.05), ("하이일드", "HYG", -0.03)],
        "COMMODITY": [("금", "IAU", 0.12), ("원유", "USO", 0.09)],
    }
    payload = _build_llm_analysis_payload(**kwargs)
    compact = _build_compact_llm_input(payload)

    assert "rs_assets_top5" in compact
    top5 = compact["rs_assets_top5"]
    assert isinstance(top5, list)
    assert 1 <= len(top5) <= 5

    for item in top5:
        assert "name_ko" in item
        assert "symbol" in item
        assert "rs" in item
        assert "group" in item
        # rs는 "+X.X%" 또는 "-X.X%" 형식
        assert "%" in item["rs"]

    # rs 내림차순 정렬 확인
    rs_floats = [float(item["rs"].replace("+", "").replace("%", "")) for item in top5]
    assert rs_floats == sorted(rs_floats, reverse=True)


def test_compact_conflict_label_none_when_no_conflict() -> None:
    """5d와 60d가 같은 방향이면 conflict_label="NONE"이다."""
    kwargs = _make_payload_kwargs()
    # 기본 fixture: 5d=RISK_OFF_BIAS, 60d=NEUTRAL_BIAS → 방어 vs None → conflict=False
    kwargs["next_step_row"]["bias_5d"] = "RISK_OFF_BIAS"
    kwargs["next_step_row"]["bias_60d"] = "RISK_OFF_BIAS"
    payload = _build_llm_analysis_payload(**kwargs)
    compact = _build_compact_llm_input(payload)

    assert compact["horizon_bias"]["conflict_label"] == "NONE"
    assert compact["horizon_bias"]["has_horizon_conflict"] is False


def test_compact_conflict_label_short_vs_long_when_conflict() -> None:
    """5d=공격, 60d=방어이면 conflict_label="SHORT_VS_LONG"이다."""
    kwargs = _make_payload_kwargs()
    kwargs["next_step_row"]["bias_5d"] = "RISK_ON_BIAS"
    kwargs["next_step_row"]["bias_60d"] = "RISK_OFF_BIAS"
    payload = _build_llm_analysis_payload(**kwargs)
    compact = _build_compact_llm_input(payload)

    assert compact["horizon_bias"]["conflict_label"] == "SHORT_VS_LONG"
    assert compact["horizon_bias"]["has_horizon_conflict"] is True


def test_compact_regime_keys_no_english_schema_terms() -> None:
    """compact regime에 영문 스키마 key(sentiment, signal)가 없고 한국어 key가 존재한다."""
    payload = _build_llm_analysis_payload(**_make_payload_kwargs())
    compact = _build_compact_llm_input(payload)

    regime = compact["regime"]
    assert "sentiment" not in regime, "영문 key 'sentiment'이 compact regime에 남아 있음"
    assert "signal" not in regime, "영문 key 'signal'이 compact regime에 남아 있음"
    assert "시장심리" in regime
    assert "단기신호" in regime
    assert isinstance(regime["시장심리"], str)
    assert isinstance(regime["단기신호"], str)


def test_compact_sell_priority_reason_summary_structure() -> None:
    """sell_priority가 있을 때 sell_priority_reason_summary 리스트가 존재하고 각 항목에 symbol/reason_tag가 있다."""
    kwargs = _make_payload_kwargs()
    kwargs["tactical_by_group"] = {
        "COMMODITY": [("원유", "UNG", 0.05)],
        "COUNTRY": [("인도", "INDA", -0.10)],
        "SECTOR": [("금융", "XLF", 0.02)],
    }
    kwargs["sell_list"] = ["UNG", "INDA", "XLF"]
    payload = _build_llm_analysis_payload(**kwargs)
    compact = _build_compact_llm_input(payload)

    assert "sell_priority_reason_summary" in compact
    summary = compact["sell_priority_reason_summary"]
    assert isinstance(summary, list)
    assert len(summary) == 3

    symbols = [item["symbol"] for item in summary]
    assert symbols == ["UNG", "INDA", "XLF"]

    tags = {item["symbol"]: item["reason_tag"] for item in summary}
    assert tags["UNG"] == "HIGH_VOL_COMMODITY"
    assert tags["INDA"] == "EM_RISK"
    assert tags["XLF"] == "SECTOR_ROTATION"

    # sell_priority 없으면 빈 리스트
    kwargs2 = _make_payload_kwargs()
    kwargs2["sell_list"] = []
    payload2 = _build_llm_analysis_payload(**kwargs2)
    compact2 = _build_compact_llm_input(payload2)
    assert compact2["sell_priority_reason_summary"] == []
