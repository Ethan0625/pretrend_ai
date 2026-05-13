"""Signal interpretation builders.

Pure functions mapping raw signal data to structured interpretation dicts
for LLM input and Telegram rendering.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pretrend.observability.explainability.localization import (
    _BIAS_LABELS,
    _CONF_REASON_DESC,
    _GROUP_LABELS,
    _GROUP_STATE_LABELS,
    _GUIDANCE_REASON_DESC,
    _PHASE_LABELS,
    _REGIME_LABELS,
    _RISK_REASON_DESC,
    _SHORT_LABELS,
    _TAG_LABELS,
    _TOPIC_LABELS,
    _parse_transition_parts,
    format_transition_expected,
)
from pretrend.observability.explainability.schema import (
    _label_items,
    _pct_str,
    _safe_float,
    _safe_json_items,
    build_interpretation_summary,
)


def _tone_bucket(tone: Any) -> str:
    try:
        if tone is None:
            return "unknown"
        f = float(tone)
        if f != f:
            return "unknown"
        if f >= 0.20:
            return "hawkish"
        if f <= -0.20:
            return "dovish"
        return "neutral"
    except Exception:
        return "unknown"


def _window_phrase(window_row: Optional[Dict[str, Any]], horizon_label: str) -> str:
    if not window_row:
        return f"{horizon_label} 텍스트 근거는 부족합니다."

    doc_count = 0
    try:
        raw_doc_count = window_row.get("text_llm_doc_count_5d", window_row.get("llm_doc_count_5d"))
        if raw_doc_count is not None:
            doc_count = int(raw_doc_count)
    except Exception:
        doc_count = 0
    topics = _label_items(
        _safe_json_items(window_row.get("text_top_topics_json", window_row.get("top_topics_json"))),
        _TOPIC_LABELS,
    )
    tags = _label_items(
        _safe_json_items(window_row.get("text_top_tags_json", window_row.get("top_tags_json"))),
        _TAG_LABELS,
    )
    tone_bucket = _tone_bucket(window_row.get("text_tone_mean_5d", window_row.get("llm_tone_mean_5d")))

    if doc_count <= 0 and not topics and not tags:
        return f"{horizon_label} 텍스트 근거는 부족합니다."

    base = {
        "hawkish": f"{horizon_label} 문서는 정책 부담 쪽으로 기울어 있습니다.",
        "dovish": f"{horizon_label} 문서는 완화 기대를 시사합니다.",
        "neutral": f"{horizon_label} 문서는 방향성이 강하지 않습니다.",
        "unknown": f"{horizon_label} 문서는 중립적으로 해석됩니다.",
    }[tone_bucket]
    details: List[str] = []
    if topics:
        details.append(f"주제는 {'/'.join(topics[:2])}")
    if tags:
        details.append(f"태그는 {'/'.join(tags[:2])}")
    if doc_count > 0:
        details.append(f"문서 {doc_count}건 기준")
    if details:
        return f"{base} {' · '.join(details)}."
    return base


def _build_next_step_material(nrow: Dict[str, Any]) -> Dict[str, Any]:
    expected_parts = _parse_transition_parts(nrow.get("transition_expected_10d", "UNKNOWN"))

    def _bias_entry(bias_key: str) -> Dict[str, Any]:
        v = str(nrow.get(bias_key, "UNKNOWN"))
        conf_key = bias_key.replace("bias_", "confidence_")
        return {
            "bias": v,
            "label": _BIAS_LABELS.get(v, v),
            "confidence": _pct_str(nrow.get(conf_key)),
        }

    return {
        # Multi-horizon bias (5D/10D/20D/60D/120D)
        "bias_5d": _bias_entry("bias_5d"),
        "bias_10d": _bias_entry("bias_10d"),
        "bias_20d": _bias_entry("bias_20d"),
        "bias_60d": _bias_entry("bias_60d"),
        "bias_120d": _bias_entry("bias_120d"),
        # Backward-compat flat fields (기존 소비자용)
        "bias_10d_label": _BIAS_LABELS.get(str(nrow.get("bias_10d", "UNKNOWN")), str(nrow.get("bias_10d", "UNKNOWN"))),
        "confidence_10d": _pct_str(nrow.get("confidence_10d")),
        "hazard_10d": _pct_str(nrow.get("transition_hazard_10d")),
        "expected_10d": format_transition_expected(nrow.get("transition_expected_10d", "UNKNOWN")),
        "expected_long_10d": expected_parts["long"],
        "expected_mid_10d": expected_parts["mid"],
        "expected_short_10d": expected_parts["short"],
        "bias_state_source": str(nrow.get("bias_state_source", "UNKNOWN")),
        "bias_switch_reason": str(nrow.get("bias_switch_reason", "UNKNOWN")),
        "cooldown_left": str(nrow.get("bias_cooldown_left", "N/A")),
        "diversity": (
            f"{int(nrow.get('horizon_bias_diversity_count'))}/5"
            if nrow.get("horizon_bias_diversity_count") is not None
            else "N/A"
        ),
    }


def _build_group_material(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in rows:
        grp = str(r.get("asset_group", "UNKNOWN"))
        out.append(
            {
                "asset_group": _GROUP_LABELS.get(grp, grp),
                "state_now": _GROUP_STATE_LABELS.get(str(r.get("group_state_now", "UNKNOWN")), str(r.get("group_state_now", "UNKNOWN"))),
                "expected_5d": _GROUP_STATE_LABELS.get(str(r.get("group_expected_5d", "UNKNOWN")), str(r.get("group_expected_5d", "UNKNOWN"))),
                "expected_10d": _GROUP_STATE_LABELS.get(str(r.get("group_expected_10d", "UNKNOWN")), str(r.get("group_expected_10d", "UNKNOWN"))),
                "hazard_10d": _pct_str(r.get("group_transition_hazard_10d")),
                "hazard_5d": _pct_str(r.get("group_transition_hazard_5d")),
                "confidence": _pct_str(r.get("group_confidence")),
            }
        )
    return out


def build_trading_guidance_struct(
    *,
    mid_regime: str,
    short_signal: str,
    run_universe: bool,
    risk_gate: bool,
    hazard_10d: Any,
) -> Dict[str, str]:
    hazard = _safe_float(hazard_10d)
    if not run_universe:
        reason = "RUN_UNIVERSE_BLOCK"
        return {
            "guidance": "관망/실행 제한",
            "reason": reason,
            "priority_source": "RUN_UNIVERSE",
            "detail": _GUIDANCE_REASON_DESC[reason],
        }
    if short_signal == "PANIC":
        reason = "SHORT_PANIC"
        return {
            "guidance": "방어",
            "reason": reason,
            "priority_source": "SHORT",
            "detail": _GUIDANCE_REASON_DESC[reason],
        }
    if not risk_gate:
        reason = "RISK_GATE_BLOCK"
        return {
            "guidance": "관망",
            "reason": reason,
            "priority_source": "RISK_GATE",
            "detail": _GUIDANCE_REASON_DESC[reason],
        }
    if hazard is not None and hazard > 0.70:
        reason = "HAZARD_HIGH"
        return {
            "guidance": "분할 접근",
            "reason": reason,
            "priority_source": "HAZARD",
            "detail": _GUIDANCE_REASON_DESC[reason],
        }
    if mid_regime == "RISK_ON":
        reason = "MID_RISK_ON"
        guidance = "매수 허용"
    elif mid_regime == "RISK_OFF":
        reason = "MID_RISK_OFF"
        guidance = "방어"
    else:
        reason = "MID_NEUTRAL"
        guidance = "관망"
    return {
        "guidance": guidance,
        "reason": reason,
        "priority_source": "MID_REGIME",
        "detail": _GUIDANCE_REASON_DESC.get(reason, _GUIDANCE_REASON_DESC["UNKNOWN"]),
    }


def build_signal_confidence_struct(
    *,
    hazard_10d: Any,
    diversity_count: Any,
    evidence_unknown_ratio: Any = None,
) -> Dict[str, str]:
    hazard = _safe_float(hazard_10d)
    unknown_ratio = _safe_float(evidence_unknown_ratio)
    dcount = None
    try:
        if diversity_count is not None:
            dcount = int(diversity_count)
    except Exception:
        dcount = None

    if unknown_ratio is not None and unknown_ratio >= 0.50:
        reason = "MISSING_OR_UNKNOWN"
        level = "낮음"
    elif hazard is not None and hazard >= 0.80:
        reason = "HAZARD_HIGH"
        level = "낮음"
    elif (hazard is not None and hazard <= 0.50) and (dcount is not None and dcount >= 3):
        reason = "LOW_HAZARD_DIVERSE"
        level = "높음"
    else:
        reason = "MIXED"
        level = "중간"
    return {
        "level": level,
        "reason": reason,
        "detail": _CONF_REASON_DESC[reason],
    }


def build_risk_summary_struct(
    *,
    run_universe: bool,
    short_signal: str,
    hazard_10d: Any,
    group_rows: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, str]:
    hazard = _safe_float(hazard_10d)
    rows = group_rows or []
    has_unknown_group = any(str(r.get("group_state_now", "UNKNOWN")) == "UNKNOWN" for r in rows)

    if not run_universe:
        reason = "RUN_UNIVERSE_BLOCK"
    elif short_signal == "PANIC":
        reason = "SHORT_PANIC"
    elif hazard is not None and hazard > 0.70:
        reason = "HAZARD_HIGH"
    elif has_unknown_group:
        reason = "GROUP_UNKNOWN"
    else:
        reason = "NONE"
    return {
        "reason": reason,
        "summary": _RISK_REASON_DESC[reason],
    }


def format_trading_guidance_lines(guidance_struct: Dict[str, str]) -> List[str]:
    guidance = guidance_struct.get("guidance", "관망")
    detail = guidance_struct.get("detail", _GUIDANCE_REASON_DESC["UNKNOWN"])
    return [
        "── 투자 행동 가이드 ──",
        f"🎯 행동: {guidance}",
        f"→ {detail}",
    ]


def format_risk_summary_lines(risk_struct: Dict[str, str]) -> List[str]:
    summary = risk_struct.get("summary", _RISK_REASON_DESC["NONE"])
    return [
        "── 핵심 리스크 ──",
        f"⚠️ {summary}",
        "→ 현재 구간의 최우선 리스크를 기준으로 요약했습니다.",
    ]


def format_signal_confidence_lines(confidence_struct: Dict[str, str]) -> List[str]:
    level = confidence_struct.get("level", "중간")
    detail = confidence_struct.get("detail", _CONF_REASON_DESC["MIXED"])
    return [
        "── 시장 신뢰도 ──",
        f"📊 신뢰도: {level}",
        f"→ {detail}",
    ]


def _build_long_context_detail(long_phase: str, long_detail: Optional[Dict[str, Any]]) -> str:
    detail = long_detail or {}
    regime_mode = str(detail.get("regime_mode") or "unknown")
    delta_z = detail.get("delta_6m_z_mean")

    base = {
        "EXPANSION": "확장 국면이 이어집니다.",
        "LATE_CYCLE": "후기 사이클 국면입니다.",
        "SLOWDOWN": "경기 둔화 신호가 감지됩니다.",
        "RECESSION": "경기 둔화 신호가 우세합니다.",
        "RECOVERY": "회복 국면 신호가 우세합니다.",
        "UNKNOWN": "장기 국면 근거가 부족합니다.",
    }.get(long_phase, "장기 국면 해석 대기")

    regime_text = {
        "easing": "정책 기조는 완화 쪽입니다.",
        "tightening": "정책 기조는 긴축 쪽입니다.",
        "neutral": "정책 기조는 중립권입니다.",
        "unknown": "정책 기조 판단 근거는 제한적입니다.",
    }.get(regime_mode, "정책 기조 판단 근거는 제한적입니다.")

    delta_text = None
    try:
        if delta_z is not None:
            dz = float(delta_z)
            if dz <= -0.30:
                delta_text = f"delta_6m_z {dz:+.2f}로 둔화 압력이 뚜렷합니다."
            elif dz >= 0.30:
                delta_text = f"delta_6m_z {dz:+.2f}로 확장 압력이 유지됩니다."
            else:
                delta_text = f"delta_6m_z {dz:+.2f}로 중립권입니다."
    except Exception:
        delta_text = None

    if delta_text:
        return f"{base} {regime_text} {delta_text}"
    return f"{base} {regime_text}"


def _build_mid_context_detail(mid_regime: str, mid_detail: Optional[Dict[str, Any]]) -> str:
    detail = mid_detail or {}
    price_signal = str(detail.get("price_signal") or "UNKNOWN")
    macro_signal = str(detail.get("macro_signal") or "UNKNOWN")
    breadth_signal = str(detail.get("breadth_signal") or "UNKNOWN")

    base = {
        "RISK_ON": "위험자산 선호 흐름입니다.",
        "NEUTRAL": "방향성이 뚜렷하지 않은 혼조 구간입니다.",
        "RISK_OFF": "방어 성향이 우세한 구간입니다.",
        "UNKNOWN": "중기 성향 근거가 부족합니다.",
    }.get(mid_regime, "중기 흐름 해석 대기")

    sig_label = {
        "RISK_ON": "위험선호",
        "NEUTRAL": "중립",
        "RISK_OFF": "방어",
        "UNKNOWN": "판단불가",
    }
    details = (
        f"가격은 {sig_label.get(price_signal, price_signal)}, "
        f"매크로는 {sig_label.get(macro_signal, macro_signal)}, "
        f"수급은 {sig_label.get(breadth_signal, breadth_signal)} 쪽입니다."
    )
    return f"{base} {details}"


def _build_short_context_detail(short_signal: str, short_detail: Optional[Dict[str, Any]]) -> str:
    detail = short_detail or {}
    confirm_count = detail.get("secondary_confirm_count")
    base = {
        "PANIC": "단기 변동성 스트레스가 큽니다.",
        "STABLE": "급락 신호는 약하며 관망이 유리합니다.",
        "RELIEF": "단기 안도 흐름이 확인됩니다.",
        "UNKNOWN": "단기 신호 근거가 부족합니다.",
    }.get(short_signal, "단기 흐름 해석 대기")

    if detail.get("primary_panic"):
        return f"{base} 1차 공황 조건이 직접 충족됐습니다."
    if detail.get("primary_relief"):
        return f"{base} 1차 안도 조건이 직접 충족됐습니다."
    if confirm_count is not None:
        try:
            return f"{base} 보조 확인 신호는 {int(confirm_count)}건입니다."
        except Exception:
            return base
    return base


def _context_with_text(base_text: str, window_row: Optional[Dict[str, Any]], horizon_label: str) -> str:
    phrase = _window_phrase(window_row, horizon_label)
    if "텍스트 근거는 부족합니다" in phrase:
        return base_text
    return f"{base_text} {phrase}"


def build_llm_analysis_payload(
    *,
    decision_date: str,
    long_phase: str,
    mid_regime: str,
    short_signal: str,
    long_detail: Dict[str, Any],
    mid_detail: Dict[str, Any],
    short_detail: Dict[str, Any],
    action: str,
    current_ratio: float,
    next_ratio: float,
    v2_target: float,
    risk_gate: bool,
    run_universe: bool,
    tactical_by_group: Dict[str, List[tuple]],
    sell_budget: float,
    sell_list: List[str],
    next_step_row: Dict[str, Any],
    group_rows: List[Dict[str, Any]],
    text_windows: Optional[Dict[str, Dict[str, Any]]],
    guidance_struct: Dict[str, str],
    risk_struct: Dict[str, str],
    confidence_struct: Dict[str, str],
) -> Dict[str, Any]:
    """전체 signal 데이터를 단일 dict로 조립 (순수 함수, I/O 없음)."""
    return {
        "decision_date": decision_date,
        "market_position": {
            "long_phase": long_phase,
            "long_phase_label": _PHASE_LABELS.get(long_phase, long_phase),
            "mid_regime": mid_regime,
            "mid_regime_label": _REGIME_LABELS.get(mid_regime, mid_regime),
            "short_signal": short_signal,
            "short_signal_label": _SHORT_LABELS.get(short_signal, short_signal),
            "risk_gate": risk_gate,
            "run_universe": run_universe,
        },
        "detail": {
            "long": long_detail,
            "mid": mid_detail,
            "short": short_detail,
        },
        "allocation": {
            "action": action,
            "current_ratio": current_ratio,
            "next_ratio": next_ratio,
            "v2_target": v2_target,
        },
        "next_step": _build_next_step_material(next_step_row),
        "group_transition": _build_group_material(group_rows),
        "tactical_etf": {
            group: [
                {"name_ko": name, "symbol": sym, "rs": rs}
                for name, sym, rs in entries
            ]
            for group, entries in tactical_by_group.items()
        },
        "sell_advice": {
            "sell_budget": sell_budget,
            "sell_priority": sell_list,
            "sell_priority_note": "RS 최하위 / 목표 비중 초과 순 정렬",
        },
        "text_windows": text_windows,
        "text_available": text_windows is not None and bool(text_windows),
        "behavior": {
            "guidance": guidance_struct,
            "risk": risk_struct,
            "confidence": confidence_struct,
        },
    }


_EM_ETF_SYMBOLS = {"EEM", "INDA", "MCHI", "FXI", "VWO", "EWZ", "EWT"}


def _infer_sell_reason_tag(sym: str, payload: Dict[str, Any]) -> str:
    """tactical_etf group 기반으로 sell priority 이유 태그를 추론한다."""
    for group, entries in payload.get("tactical_etf", {}).items():
        for e in entries:
            if e.get("symbol") == sym:
                if group == "COMMODITY":
                    return "HIGH_VOL_COMMODITY"
                if group == "COUNTRY" and sym in _EM_ETF_SYMBOLS:
                    return "EM_RISK"
                if group == "BOND":
                    return "RATE_SENSITIVE"
                if group == "SECTOR":
                    return "SECTOR_ROTATION"
                return "RS_UNDERPERFORMER"
    return "RS_UNDERPERFORMER"


def _build_compact_llm_input(payload: Dict[str, Any]) -> Dict[str, Any]:
    """LLM 입력용 압축 payload. ~1500토큰 → ~600토큰 목표.

    제거 항목: detail(long/mid/short), group_transition, backward-compat next_step 키
    compact 항목: text_windows → tone + 상위 3 토픽 + doc_count만
    포맷 변환: rs float → "+8.7%" string, ratio float → "45%"
    """
    ns = payload.get("next_step", {})
    mp = payload.get("market_position", {})

    def _hb(key: str) -> Dict[str, str]:
        entry = ns.get(key, {})
        if isinstance(entry, dict):
            return {"label": entry.get("label", "판단 보류"), "pct": entry.get("confidence", "N/A")}
        return {"label": "판단 보류", "pct": "N/A"}

    def _is_risk_on(e: Dict[str, str]) -> Optional[bool]:
        lbl = e.get("label", "")
        if "공격" in lbl:
            return True
        if "방어" in lbl:
            return False
        return None

    b5, b60 = _hb("bias_5d"), _hb("bias_60d")
    d5, d60 = _is_risk_on(b5), _is_risk_on(b60)
    conflict = (d5 is not None) and (d60 is not None) and (d5 != d60)

    rs_by_group: Dict[str, List[str]] = {}
    rs_by_group_raw: Dict[str, List[float]] = {}
    all_assets_raw: List[Dict[str, Any]] = []
    for group, entries in payload.get("tactical_etf", {}).items():
        lbl = _GROUP_LABELS.get(group, group)
        rs_by_group[lbl] = [
            f"{e['name_ko']} {'+' if e['rs'] >= 0 else ''}{e['rs']:.1%}"
            for e in entries
        ]
        rs_vals = [e["rs"] for e in entries]
        if rs_vals:
            rs_by_group_raw[lbl] = rs_vals
        for e in entries:
            all_assets_raw.append({
                "name_ko": e["name_ko"],
                "symbol": e["symbol"],
                "rs_float": e["rs"],
                "group": lbl,
            })

    # rs_assets_top5: 전체 자산 중 RS 상위 5개 (raw float 기준 정렬)
    all_assets_sorted = sorted(all_assets_raw, key=lambda x: x["rs_float"], reverse=True)
    rs_assets_top5 = [
        {
            "name_ko": a["name_ko"],
            "symbol": a["symbol"],
            "rs": f"+{a['rs_float']:.1%}" if a["rs_float"] >= 0 else f"{a['rs_float']:.1%}",
            "group": a["group"],
        }
        for a in all_assets_sorted[:5]
    ]

    # rs_asset_groups_summary: 그룹별 평균 RS → 최강/최약 그룹
    group_avg = {
        lbl: sum(vals) / len(vals)
        for lbl, vals in rs_by_group_raw.items()
        if vals
    }
    rs_asset_groups_summary = {
        "strongest": max(group_avg, key=group_avg.get) if group_avg else None,
        "weakest": min(group_avg, key=group_avg.get) if group_avg else None,
    }

    text_summary = None
    if payload.get("text_available"):
        text_summary = {}
        for win_name, win in (payload.get("text_windows") or {}).items():
            topics = [_TOPIC_LABELS.get(t, t) for t in (win.get("topics") or [])[:3]]
            text_summary[win_name] = {
                "tone": win.get("tone"),
                "topics": topics,
                "doc_count": win.get("doc_count"),
            }

    alloc = payload.get("allocation", {})
    sell = payload.get("sell_advice", {})
    sell_list = (sell.get("sell_priority") or [])[:3]

    # sell_priority_reason_summary: 매도 우선순위 종목별 이유 태그
    sell_priority_reason_summary = [
        {"symbol": sym, "reason_tag": _infer_sell_reason_tag(sym, payload)}
        for sym in sell_list
    ]

    return {
        "date": payload.get("decision_date"),
        "regime": {
            "phase": mp.get("long_phase_label"),
            "시장심리": mp.get("mid_regime_label"),
            "단기신호": mp.get("short_signal_label"),
            "risk_gate": mp.get("risk_gate"),
        },
        "horizon_bias": {
            "5d": b5,
            "10d": _hb("bias_10d"),
            "20d": _hb("bias_20d"),
            "60d": b60,
            "120d": _hb("bias_120d"),
            "has_horizon_conflict": conflict,
            "conflict_label": "NONE" if not conflict else "SHORT_VS_LONG",
            "conflict_5d_vs_60d": conflict,
            "conflict_pair": ["5d", "60d"] if conflict else [],
            "hazard": ns.get("hazard_10d"),
            "expected": ns.get("expected_10d"),
        },
        "allocation": {
            "action": alloc.get("action"),
            "current": f"{alloc.get('current_ratio', 0.0):.0%}",
            "next": f"{alloc.get('next_ratio', 0.0):.0%}",
        },
        "relative_strength": rs_by_group,
        "rs_assets_top5": rs_assets_top5,
        "rs_asset_groups_summary": rs_asset_groups_summary,
        "text_summary": text_summary,
        "behavior": payload.get("behavior"),
        "sell_priority": sell_list or None,
        "sell_priority_reason_summary": sell_priority_reason_summary,
        "text_available": payload.get("text_available", False),
    }
