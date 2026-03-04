"""Telegram 시장 컨텍스트/근거/다음 스텝 렌더링 헬퍼."""
from __future__ import annotations

import json
from typing import Any, Dict, List


def safe_json_dict(raw: Any) -> Dict[str, Any]:
    """JSON 문자열/객체를 dict로 변환. 실패 시 빈 dict."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            val = json.loads(raw)
            return val if isinstance(val, dict) else {}
        except Exception:
            return {}
    return {}


def select_interpretation_text(deterministic_text: str, llm_text: Any) -> str:
    """LLM 해석 문구 선택(fail-open).

    - llm_text가 유효 문자열이면 사용
    - 그 외에는 결정론 문구(deterministic_text)로 fallback
    """
    if isinstance(llm_text, str):
        stripped = llm_text.strip()
        if stripped:
            return stripped
    return deterministic_text


def build_context_lines(long_phase: str, mid_regime: str, short_signal: str) -> List[str]:
    long_msg = {
        "EXPANSION": "확장 국면이 이어집니다.",
        "LATE_CYCLE": "후기 사이클 국면입니다.",
        "SLOWDOWN": "경기 둔화 신호가 감지됩니다.",
        "RECESSION": "경기 둔화 신호가 우세합니다.",
        "RECOVERY": "회복 국면 신호가 우세합니다.",
        "UNKNOWN": "장기 국면 근거가 부족합니다.",
    }
    mid_msg = {
        "RISK_ON": "위험자산 선호 흐름입니다.",
        "NEUTRAL": "방향성이 뚜렷하지 않은 혼조 구간입니다.",
        "RISK_OFF": "방어 성향이 우세한 구간입니다.",
        "UNKNOWN": "중기 성향 근거가 부족합니다.",
    }
    short_msg = {
        "PANIC": "단기 변동성 스트레스가 큽니다.",
        "STABLE": "급락 신호는 약하며 관망이 유리합니다.",
        "RELIEF": "단기 안도 흐름이 확인됩니다.",
        "UNKNOWN": "단기 신호 근거가 부족합니다.",
    }
    long_label = {
        "EXPANSION": "확장 우세", "LATE_CYCLE": "후기 사이클", "SLOWDOWN": "둔화 우세",
        "RECESSION": "둔화 우세", "RECOVERY": "회복 우세", "UNKNOWN": "판단불가",
    }
    mid_label = {"RISK_ON": "위험선호", "NEUTRAL": "혼조", "RISK_OFF": "위험회피", "UNKNOWN": "판단불가"}
    short_label = {"PANIC": "공황", "STABLE": "안정", "RELIEF": "안도", "UNKNOWN": "판단불가"}
    return [
        f"🔴 장기 국면: {long_label.get(long_phase, long_phase)} ({long_phase})",
        f"→ {long_msg.get(long_phase, '장기 국면 해석 대기')}",
        "",
        f"🟢 중기 성향: {mid_label.get(mid_regime, mid_regime)} ({mid_regime})",
        f"→ {mid_msg.get(mid_regime, '중기 흐름 해석 대기')}",
        "",
        f"🔵 단기 흐름: {short_label.get(short_signal, short_signal)} ({short_signal})",
        f"→ {short_msg.get(short_signal, '단기 흐름 해석 대기')}",
    ]


def build_switch_lines(risk_gate: bool, run_universe: bool) -> List[str]:
    """사용자 표시용 상태 스위치 라인.

    내부 필드:
      - risk_gate: True=정상, False=PANIC
      - run_universe: True=전술 실행 허용
    표시 별칭:
      - 단기 공황 여부: 예/아니오 (is_panic = not risk_gate)
      - 전술 실행: 허용/제한
    """
    is_panic = not risk_gate
    return [
        f"😱 단기 공황 여부: {'예' if is_panic else '아니오'}",
        f"📈 전술 실행: {'허용' if run_universe else '제한'}",
    ]


def build_evidence_lines(
    long_detail: Dict[str, Any],
    mid_detail: Dict[str, Any],
    short_detail: Dict[str, Any],
) -> List[str]:
    macro_line = "매크로,정책: 영향 근거 없음"
    price_line = "가격: 영향 근거 없음"
    flow_line = "수급/구조: 영향 근거 없음"
    senti_line = "심리: 영향 근거 없음"

    regime_mode = long_detail.get("regime_mode")
    delta_z = long_detail.get("delta_6m_z_mean")
    threshold = long_detail.get("z_threshold")
    if regime_mode is not None or delta_z is not None:
        parts = []
        if regime_mode is not None:
            parts.append(f"regime={regime_mode}")
        if delta_z is not None:
            parts.append(f"delta_6m_z={float(delta_z):+.2f}")
        if threshold is not None:
            parts.append(f"threshold={float(threshold):.2f}")
        macro_line = f"매크로,정책: {', '.join(parts)}"

    price_signal = mid_detail.get("price_signal")
    short_primary_panic = short_detail.get("primary_panic")
    short_primary_relief = short_detail.get("primary_relief")
    if price_signal is not None or short_primary_panic is not None or short_primary_relief is not None:
        parts = []
        if price_signal is not None:
            parts.append(f"mid.price={price_signal}")
        if short_primary_panic:
            parts.append("short.primary=PANIC")
        elif short_primary_relief:
            parts.append("short.primary=RELIEF")
        elif short_primary_panic is not None:
            parts.append("short.primary=STABLE")
        price_line = f"가격: {', '.join(parts)}" if parts else price_line

    breadth_signal = mid_detail.get("breadth_signal")
    breadth_spread = mid_detail.get("breadth_spread")
    confirmations = short_detail.get("secondary_confirmations")
    confirm_count = short_detail.get("secondary_confirm_count")
    smallcap_stress = short_detail.get("smallcap_stress")
    if (
        breadth_signal is not None
        or breadth_spread is not None
        or confirm_count is not None
        or smallcap_stress is not None
    ):
        parts = []
        if breadth_signal is not None:
            parts.append(f"breadth={breadth_signal}")
        if breadth_spread is not None:
            parts.append(f"spread={float(breadth_spread):+.3f}")
        if confirm_count is not None:
            parts.append(f"confirm={int(confirm_count)}")
        if smallcap_stress is not None:
            parts.append(f"smallcap_stress={'Y' if bool(smallcap_stress) else 'N'}")
        if confirmations:
            parts.append(f"signals={'/'.join(confirmations)}")
        flow_line = f"수급/구조: {', '.join(parts)}" if parts else flow_line

    risk_on_confirm = short_detail.get("risk_on_confirm")
    if confirmations is not None or risk_on_confirm is not None:
        parts = []
        if confirmations:
            senti_related = [s for s in confirmations if s in {"flight_to_safety"}]
            if senti_related:
                parts.append(f"확인신호={'/'.join(senti_related)}")
        if risk_on_confirm is not None:
            parts.append(f"risk_on_confirm={'Y' if bool(risk_on_confirm) else 'N'}")
        senti_line = f"심리: {', '.join(parts)}" if parts else "심리: 영향 근거 없음"

    return [
        "🏛️매크로,정책",
        f"→ {macro_line.replace('매크로,정책: ', '')}",
        "",
        "💵가격",
        f"→ {price_line.replace('가격: ', '')}",
        "",
        "📈수급/구조",
        f"→ {flow_line.replace('수급/구조: ', '')}",
        "",
        "💕심리",
        f"→ {senti_line.replace('심리: ', '')}",
    ]


def build_text_overlay_lines(text_row: Dict[str, Any] | None) -> List[str]:
    """Text overlay evidence lines for Telegram market evidence section."""
    if not text_row:
        return []

    state = str(text_row.get("text_signal_state", "UNKNOWN"))
    if state == "UNKNOWN":
        return []

    conf = text_row.get("text_signal_confidence")
    tone = text_row.get("text_tone_mean_5d")
    conf_txt = "N/A"
    tone_txt = "N/A"
    try:
        if conf is not None:
            f = float(conf)
            if f == f:
                conf_txt = f"{f:.0%}"
    except Exception:
        conf_txt = "N/A"
    try:
        if tone is not None:
            f = float(tone)
            if f == f:
                tone_txt = f"{f:+.2f}"
    except Exception:
        tone_txt = "N/A"

    top_tags = []
    raw_tags = text_row.get("text_top_tags_json")
    if isinstance(raw_tags, str):
        try:
            parsed = json.loads(raw_tags)
            if isinstance(parsed, list):
                top_tags = [str(x.get("item")) for x in parsed if isinstance(x, dict) and x.get("item")]
        except Exception:
            top_tags = []

    label = {
        "RISK_ON": "위험선호 보조",
        "NEUTRAL": "중립 보조",
        "RISK_OFF": "위험회피 보조",
    }.get(state, state)
    reason = str(text_row.get("text_overlay_reason", "NO_TEXT_EDGE"))

    detail = f"state={label}({state}), conf={conf_txt}, tone={tone_txt}"
    if top_tags:
        detail += f", tags={'/'.join(top_tags[:3])}"

    return [
        "",
        "📝텍스트",
        f"→ {detail}",
        f"→ reason={reason}",
    ]


def format_transition_expected(expected: Any) -> str:
    """transition_expected를 사람이 읽기 쉬운 문장으로 변환한다."""
    raw = "UNKNOWN" if expected is None else str(expected)
    parts = raw.split("_")
    if len(parts) != 3:
        return raw

    long_phase, mid_regime, short_signal = parts
    long_ko = {
        "EXPANSION": "확장",
        "LATE_CYCLE": "후기",
        "SLOWDOWN": "둔화",
        "RECESSION": "침체",
        "RECOVERY": "회복",
        "UNKNOWN": "미상",
    }.get(long_phase, long_phase)
    mid_ko = {
        "RISK_ON": "위험선호",
        "NEUTRAL": "혼조",
        "RISK_OFF": "위험회피",
        "UNKNOWN": "미상",
    }.get(mid_regime, mid_regime)
    short_ko = {
        "PANIC": "공황",
        "STABLE": "안정",
        "RELIEF": "안도",
        "UNKNOWN": "미상",
    }.get(short_signal, short_signal)
    return (
        f"장기 {long_ko}({long_phase}) · "
        f"중기 {mid_ko}({mid_regime}) · "
        f"단기 {short_ko}({short_signal})"
    )


def format_next_step_hazard_lines(nrow: Dict[str, Any] | None) -> List[str]:
    """next_step snapshot 전용 렌더링 (운영 메시지용).

    nrow가 없거나 필드 결측이면 UNKNOWN/N/A로 fail-open 표기한다.
    """
    nrow = nrow or {}

    def _pct_or_na(v: Any) -> str:
        try:
            if v is None:
                return "N/A"
            fv = float(v)
            if fv != fv:  # NaN
                return "N/A"
            return f"{fv:.0%}"
        except Exception:
            return "N/A"

    rows: List[str] = [
        f"🧭 10D: {str(nrow.get('bias_10d', 'UNKNOWN'))} ({_pct_or_na(nrow.get('confidence_10d'))})",
        f"⏱ 10D 전환위험: {_pct_or_na(nrow.get('transition_hazard_10d'))}",
        f"🔭 10D 예상 전이: {format_transition_expected(nrow.get('transition_expected_10d', 'UNKNOWN'))}",
    ]

    summary = []
    for h in (5, 20, 60, 120):
        summary.append(f"{h}D {str(nrow.get(f'bias_{h}d', 'UNKNOWN'))}({_pct_or_na(nrow.get(f'confidence_{h}d'))})")
    rows.append("🧭 지평 요약: " + " · ".join(summary))

    diversity_count = nrow.get("horizon_bias_diversity_count")
    diversity_ratio = nrow.get("horizon_bias_diversity_ratio_60d")
    conf_spread = nrow.get("horizon_conf_spread")
    diversity_count_txt = "N/A"
    conf_spread_txt = "N/A"
    try:
        if diversity_count is not None:
            diversity_count_txt = f"{int(diversity_count)}/5"
    except Exception:
        diversity_count_txt = "N/A"
    try:
        if conf_spread is not None:
            fv = float(conf_spread)
            if fv == fv:
                conf_spread_txt = f"{fv:.2f}"
    except Exception:
        conf_spread_txt = "N/A"
    rows.append(
        "🧪 분화도: "
        f"diversity={diversity_count_txt}, "
        f"recent60={_pct_or_na(diversity_ratio)}, "
        f"conf_spread={conf_spread_txt}"
    )
    return rows


def format_bias_state_line(nrow: Dict[str, Any] | None) -> str:
    nrow = nrow or {}
    source = nrow.get("bias_state_source", "UNKNOWN")
    switch_flag = "Y" if bool(nrow.get("bias_switch_flag", False)) else "N"
    reason = nrow.get("bias_switch_reason", "UNKNOWN")
    cooldown = nrow.get("bias_cooldown_left", "N/A")
    return (
        "🧩 bias state: "
        f"source={source}, "
        f"switch={switch_flag}, "
        f"reason={reason}, "
        f"cooldown={cooldown}"
    )


def format_group_transition_lines(rows: List[Dict[str, Any]] | None) -> List[str]:
    """그룹 전이 요약 라인 생성 (5D/10D + 전환가능성)."""
    if not rows:
        return ["전술 그룹 전이 데이터 없음 (UNKNOWN/N/A)"]

    icon = {
        "SECTOR": "🏭",
        "COMMODITY": "⛽️",
        "BOND": "🏦",
        "COUNTRY": "🌍",
    }
    state_icon = {
        "STRONG": "🟢",
        "NEUTRAL": "🟡",
        "WEAK": "🔴",
        "UNKNOWN": "⚪",
    }

    ordered = sorted(rows, key=lambda r: str(r.get("asset_group", "ZZZ")))
    out: List[str] = []
    for r in ordered:
        grp = str(r.get("asset_group", "UNKNOWN"))
        now_state = str(r.get("group_state_now", "UNKNOWN"))
        exp5 = str(r.get("group_expected_5d", "UNKNOWN"))
        exp10 = str(r.get("group_expected_10d", "UNKNOWN"))
        hz5 = r.get("group_transition_hazard_5d")
        hz10 = r.get("group_transition_hazard_10d")
        hz5_txt = "N/A"
        hz10_txt = "N/A"
        try:
            if hz5 is not None:
                fv5 = float(hz5)
                if fv5 == fv5:
                    hz5_txt = f"{fv5:.0%}"
            if hz10 is not None:
                fv10 = float(hz10)
                if fv10 == fv10:
                    hz10_txt = f"{fv10:.0%}"
        except Exception:
            hz5_txt = "N/A"
            hz10_txt = "N/A"
        out.append(
            f"{icon.get(grp, '📌')} {grp}: {state_icon.get(now_state, '⚪')}{now_state} → "
            f"5D:{state_icon.get(exp5, '⚪')}{exp5} ({hz5_txt}) / "
            f"10D:{state_icon.get(exp10, '⚪')}{exp10} ({hz10_txt})"
        )
    return out


def build_diagnostic_lines(
    long_detail: Dict[str, Any],
    mid_detail: Dict[str, Any],
    short_detail: Dict[str, Any],
) -> List[str]:
    """12셀 진단 KPI를 품질 상태로 압축 출력한다."""
    known = 0
    total = 12

    # macro
    if long_detail.get("regime_mode") is not None or long_detail.get("delta_6m_z_mean") is not None:
        known += 1  # macro-long
    if mid_detail.get("macro_signal") is not None:
        known += 1  # macro-mid
    # macro-short (v0/v1 현재 없음)

    # price
    if mid_detail.get("price_signal") is not None:
        known += 1  # price-mid
    if short_detail.get("primary_panic") is not None or short_detail.get("primary_relief") is not None:
        known += 1  # price-short
    # price-long (현재 없음)

    # flow
    if mid_detail.get("breadth_signal") is not None:
        known += 1  # flow-mid
    if (
        short_detail.get("secondary_confirm_count") is not None
        or short_detail.get("smallcap_stress") is not None
        or short_detail.get("secondary_confirmations") is not None
    ):
        known += 1  # flow-short
    # flow-long (현재 없음)

    # sentiment
    if short_detail.get("risk_on_confirm") is not None:
        known += 1  # sentiment-short
    # sentiment-long/mid (현재 없음)

    coverage = known / total
    unknown_ratio = 1.0 - coverage
    quality = "양호" if coverage >= 0.50 else "경고"

    return [
        f"🧪 12셀 품질: {quality}",
        f"→ coverage={coverage:.1%}, unknown={unknown_ratio:.1%}",
    ]
