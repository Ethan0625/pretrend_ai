"""Telegram formatter functions.

Renders structured signal data into human-readable Telegram message lines.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from pretrend.observability.explainability.localization import (
    format_transition_expected,
)
from pretrend.observability.explainability.schema import (
    _pct_str,
    build_interpretation_summary,
)
from pretrend.observability.explainability.interpretation import (
    _build_long_context_detail,
    _build_mid_context_detail,
    _build_short_context_detail,
    _context_with_text,
    _window_phrase,
)


def build_context_lines(
    long_phase: str,
    mid_regime: str,
    short_signal: str,
    *,
    long_detail: Optional[Dict[str, Any]] = None,
    mid_detail: Optional[Dict[str, Any]] = None,
    short_detail: Optional[Dict[str, Any]] = None,
    text_windows: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[str]:
    long_label = {
        "EXPANSION": "확장 우세", "LATE_CYCLE": "후기 사이클", "SLOWDOWN": "둔화 우세",
        "RECESSION": "둔화 우세", "RECOVERY": "회복 우세", "UNKNOWN": "판단불가",
    }
    mid_label = {"RISK_ON": "위험선호", "NEUTRAL": "혼조", "RISK_OFF": "위험회피", "UNKNOWN": "판단불가"}
    short_label = {"PANIC": "공황", "STABLE": "안정", "RELIEF": "안도", "UNKNOWN": "판단불가"}
    long_desc = _build_long_context_detail(long_phase, long_detail)
    mid_desc = _build_mid_context_detail(mid_regime, mid_detail)
    short_desc = _build_short_context_detail(short_signal, short_detail)

    if text_windows:
        long_desc = build_interpretation_summary(
            _context_with_text(long_desc, text_windows.get("long"), "최근 60거래일"),
            None,
        )
        mid_desc = build_interpretation_summary(
            _context_with_text(mid_desc, text_windows.get("mid"), "최근 20거래일"),
            None,
        )
        short_desc = build_interpretation_summary(
            _context_with_text(short_desc, text_windows.get("short"), "최근 5거래일"),
            None,
        )

    return [
        f"🔴 장기 국면: {long_label.get(long_phase, long_phase)} ({long_phase})",
        f"→ {long_desc}",
        "",
        f"🟢 중기 성향: {mid_label.get(mid_regime, mid_regime)} ({mid_regime})",
        f"→ {mid_desc}",
        "",
        f"🔵 단기 흐름: {short_label.get(short_signal, short_signal)} ({short_signal})",
        f"→ {short_desc}",
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
    macro_line = "영향 근거 없음"
    price_line = "영향 근거 없음"
    flow_line = "영향 근거 없음"
    senti_line = "영향 근거 없음"

    regime_mode = long_detail.get("regime_mode")
    delta_z = long_detail.get("delta_6m_z_mean")
    threshold = long_detail.get("z_threshold")
    if regime_mode is not None or delta_z is not None:
        regime_phrase = {
            "easing": "정책 기조는 완화 쪽입니다.",
            "tightening": "정책 기조는 긴축 쪽입니다.",
            "neutral": "정책 기조는 중립권입니다.",
        }.get(str(regime_mode), "정책 기조 판단 근거가 있습니다.")
        delta_phrase = None
        try:
            if delta_z is not None:
                dz = float(delta_z)
                if dz <= -0.30:
                    delta_phrase = f"delta_6m_z {dz:+.2f}로 둔화 압력이 임계값 아래입니다."
                elif dz >= 0.30:
                    delta_phrase = f"delta_6m_z {dz:+.2f}로 확장 압력이 유지됩니다."
                else:
                    delta_phrase = f"delta_6m_z {dz:+.2f}로 임계값 부근의 중립권입니다."
        except Exception:
            delta_phrase = None
        macro_line = regime_phrase if not delta_phrase else f"{regime_phrase} {delta_phrase}"
        if threshold is not None:
            try:
                macro_line += f" (threshold {float(threshold):.2f})"
            except Exception:
                pass

    price_signal = mid_detail.get("price_signal")
    short_primary_panic = short_detail.get("primary_panic")
    short_primary_relief = short_detail.get("primary_relief")
    if price_signal is not None or short_primary_panic is not None or short_primary_relief is not None:
        price_phrase = {
            "RISK_ON": "중기 가격 흐름은 위험선호 쪽입니다.",
            "RISK_OFF": "중기 가격 흐름은 방어 쪽입니다.",
            "NEUTRAL": "중기 가격 흐름은 방향성이 크지 않습니다.",
        }.get(str(price_signal), "중기 가격 신호가 있습니다.")
        short_phrase = "단기 가격 확인 신호는 안정권입니다."
        if short_primary_panic:
            short_phrase = "단기 가격 확인 신호는 공황 쪽입니다."
        elif short_primary_relief:
            short_phrase = "단기 가격 확인 신호는 안도 쪽입니다."
        price_line = f"{price_phrase} {short_phrase}"

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
        flow_phrase = {
            "RISK_ON": "수급 breadth는 위험선호 쪽입니다.",
            "RISK_OFF": "수급 breadth는 방어 쪽입니다.",
            "NEUTRAL": "수급 breadth는 중립권입니다.",
        }.get(str(breadth_signal), "수급 breadth 신호가 있습니다.")
        spread_phrase = None
        try:
            if breadth_spread is not None:
                spread_phrase = f"소형주 대비 spread는 {float(breadth_spread):+.3f}입니다."
        except Exception:
            spread_phrase = None
        confirm_phrase = None
        if confirm_count is not None:
            confirm_phrase = f"보조 확인 신호 {int(confirm_count)}건입니다."
        stress_phrase = None
        if smallcap_stress is not None:
            stress_phrase = "소형주 스트레스가 보입니다." if bool(smallcap_stress) else "소형주 스트레스는 제한적입니다."
        signal_phrase = None
        if confirmations:
            signal_phrase = f"확인 신호는 {'/'.join(confirmations)}입니다."
        flow_line = " ".join(
            p for p in [flow_phrase, spread_phrase, confirm_phrase, stress_phrase, signal_phrase] if p
        )

    risk_on_confirm = short_detail.get("risk_on_confirm")
    if confirmations is not None or risk_on_confirm is not None:
        senti_parts = []
        if confirmations:
            senti_related = [s for s in confirmations if s in {"flight_to_safety"}]
            if senti_related:
                senti_parts.append(f"안전자산 선호 확인 신호는 {'/'.join(senti_related)}입니다.")
        if risk_on_confirm is not None:
            senti_parts.append(
                "위험선호 확인은 유지됩니다." if bool(risk_on_confirm) else "위험선호 확인은 아직 약합니다."
            )
        senti_line = " ".join(senti_parts) if senti_parts else "영향 근거 없음"

    return [
        "🏛️매크로,정책",
        f"→ {macro_line}",
        "",
        "💵가격",
        f"→ {price_line}",
        "",
        "📈수급/구조",
        f"→ {flow_line}",
        "",
        "💕심리",
        f"→ {senti_line}",
    ]


def build_text_overlay_lines(text_row: Dict[str, Any] | None) -> List[str]:
    """Text overlay evidence lines for Telegram market evidence section.

    이 함수는 text overlay snapshot과 text-only llm_feature를 함께 읽어
    report-layer 해석문(interpretation_summary)과 근거 요약을 만든다.
    전략 입력이나 snapshot 스키마를 바꾸지는 않는다.
    """
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

    top_topics = []
    raw_topics = text_row.get("text_top_topics_json")
    if isinstance(raw_topics, str):
        try:
            parsed = json.loads(raw_topics)
            if isinstance(parsed, list):
                top_topics = [str(x.get("item")) for x in parsed if isinstance(x, dict) and x.get("item")]
        except Exception:
            top_topics = []

    doc_count = text_row.get("text_llm_doc_count_5d")
    try:
        doc_count_txt = str(int(doc_count)) if doc_count is not None else "0"
    except Exception:
        doc_count_txt = "0"

    label = {
        "RISK_ON": "위험선호 보조",
        "NEUTRAL": "중립 보조",
        "RISK_OFF": "위험회피 보조",
    }.get(state, state)

    tone_phrase = "톤 정보가 부족합니다."
    tone_value = None
    try:
        if tone is not None:
            tone_value = float(tone)
    except Exception:
        tone_value = None
    if tone_value is not None:
        if tone_value <= -0.20:
            tone_phrase = f"문서 톤은 완화 쪽({tone_txt})입니다."
        elif tone_value >= 0.20:
            tone_phrase = f"문서 톤은 긴축 쪽({tone_txt})입니다."
        else:
            tone_phrase = f"문서 톤은 중립권({tone_txt})입니다."

    deterministic = {
        "RISK_ON": f"최근 텍스트 근거는 {label}로 기울어 있습니다. {tone_phrase}",
        "RISK_OFF": f"최근 텍스트 근거는 {label}로 기울어 있습니다. {tone_phrase}",
        "NEUTRAL": f"최근 텍스트 근거는 {label}이며 방향성은 크지 않습니다. {tone_phrase}",
    }.get(state, f"최근 텍스트 근거는 {label} 상태입니다. {tone_phrase}")
    interpretation_summary = build_interpretation_summary(
        deterministic,
        text_row.get("text_latest_summary"),
    )

    evidence_parts: List[str] = [f"최근 문서 {doc_count_txt}건", f"신뢰도 {conf_txt}"]
    if top_topics:
        evidence_parts.append(f"주제 {'/'.join(top_topics[:2])}")
    if top_tags:
        evidence_parts.append(f"태그 {'/'.join(top_tags[:3])}")

    return [
        "",
        "📝텍스트 해석",
        f"→ {interpretation_summary}",
        f"→ {' · '.join(evidence_parts)}",
    ]


def build_text_window_lines(
    text_windows: Optional[Dict[str, Dict[str, Any]]],
) -> List[str]:
    if not text_windows:
        return []

    lines = ["", "📝텍스트 해석"]
    mapping = [
        ("장기(60D)", text_windows.get("long"), "최근 60거래일"),
        ("중기(20D)", text_windows.get("mid"), "최근 20거래일"),
        ("단기(5D)", text_windows.get("short"), "최근 5거래일"),
    ]
    for label, row, horizon_label in mapping:
        phrase = _window_phrase(row, horizon_label)
        lines.append(f"→ {label}: {phrase}")
    return lines


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
