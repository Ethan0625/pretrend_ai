"""Telegram 시장 컨텍스트/근거/다음 스텝 렌더링 헬퍼.

용어:
- llm_feature: text snapshot만 기반으로 생성된 LLM 산출물 묶음
- llm_summary: llm_feature 내부의 text-only 요약 필드
- interpretation_summary: signal snapshot + text snapshot을 결합해 만든
  상위 해석 문장(리포트/Telegram 전용)
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

_TOPIC_LABELS = {
    "fed_policy": "연준 정책",
    "inflation": "인플레이션",
    "employment": "고용",
    "treasury_yield": "국채금리",
    "financials": "금융",
    "information_tech": "IT",
    "nasdaq100": "나스닥100",
    "sp500": "S&P500",
}

_TAG_LABELS = {
    "hike": "금리인상",
    "cut": "금리인하",
    "pause": "동결",
    "pivot": "정책 전환",
    "qt": "긴축축소",
    "qe": "유동성 공급",
    "risk_off": "위험회피",
    "risk_on": "위험선호",
    "volatility_spike": "변동성 확대",
}

_BIAS_LABELS = {
    "RISK_ON_BIAS": "공격 쪽 전망",
    "NEUTRAL_BIAS": "중립 전망",
    "RISK_OFF_BIAS": "방어 쪽 전망",
    "UNKNOWN": "판단 보류",
}

_GROUP_LABELS = {
    "SECTOR": "섹터",
    "COMMODITY": "원자재",
    "BOND": "채권",
    "COUNTRY": "개별국가",
    "UNKNOWN": "미상",
}

_GROUP_STATE_LABELS = {
    "STRONG": "강세",
    "NEUTRAL": "중립",
    "WEAK": "약세",
    "UNKNOWN": "판단보류",
}

_PHASE_LABELS = {
    "EXPANSION": "확장 국면",
    "RECOVERY": "회복 국면",
    "LATE_CYCLE": "후기 국면",
    "SLOWDOWN": "둔화 국면",
    "RECESSION": "침체 국면",
    "UNKNOWN": "판단 보류",
}

_REGIME_LABELS = {
    "RISK_ON": "위험선호",
    "RISK_OFF": "위험회피",
    "NEUTRAL": "중립",
    "UNKNOWN": "판단 보류",
}

_SHORT_LABELS = {
    "PANIC": "단기 공황",
    "STABLE": "안정",
    "RELIEF": "단기 안도",
    "UNKNOWN": "판단 보류",
}

_ANALYSIS_SYSTEM_PROMPT = """\
역할: Pretrend AI 수석 매크로 전략가

당신은 Pretrend AI 시스템의 시장 신호를 읽고, 한국어로 전략적 해석 보고서를 작성합니다.
Telegram 메시지로 전송되며, HTML 태그(<b>, <i>)를 사용할 수 있습니다.
입력 데이터는 압축 구조화 형식입니다. regime / horizon_bias / relative_strength /
behavior / text_summary 필드를 활용하여 추론하십시오.

━━━ 핵심 작성 원칙 ━━━

1) 데이터 충실: 입력 데이터의 사실과 방향만 전달한다. 없는 사실을 만들지 않는다.
2) 코드 제거: 상태 코드(RECESSION, RISK_OFF 등)를 직접 쓰지 않는다.
   대신 regime.phase / regime.sentiment / regime.signal 필드의 한국어 표현을 사용한다.
3) 교차 분석 필수: 서로 다른 필드의 신호를 연결하여 해석한다.
   예: relative_strength에서 방어주+국채 동반 강세 + regime.phase=침체 →
   "투자자들이 이미 경기 둔화를 대비하고 있다"는 해석이 된다.
4) 불일치 강조: horizon_bias.conflict_5d_vs_60d=true이면 반드시 왜 그런지 설명한다.
5) 분량: 전체 3000자 이내.
6) 일반론 투자 조언 금지: "분산투자가 중요합니다", "장기 투자를 유지하세요",
   "투자자는 신중해야 합니다" 같은 데이터와 무관한 일반 조언은 절대 쓰지 않는다.
7) 반복 표현 금지: "이 데이터는", "이 수치는", "이를 시사합니다" 같은 도입 문구를 2회 이상 사용하지 않는다.
   각 섹션은 서로 다른 시제·어조로 시작한다.
   (예: 섹션1=현재 상태 진단, 섹션2=미래 위험 경보, 섹션3=근거 서술, 섹션4=행동 지시)
   [종합 요약]은 섹션 1-4에서 쓴 문장을 그대로 반복하지 않고 새로운 각도로 연결한다.
8) RS 해석: relative_strength의 각 항목은 이미 "+8.7%" 형식으로 포맷되어 있다.
   "SPY 대비 +8.7%" 식으로 자연스럽게 문장에 녹여 쓴다.
9) 텍스트 데이터 처리: text_available=false이면 Section 3의 <b>텍스트 해석:</b> 소제목을 생략하고
   "최근 문서 데이터 미수집으로 텍스트 흐름 분석을 생략합니다." 한 문장으로 대체한다.
10) behavior 필드 활용: behavior.guidance.detail, behavior.risk.summary,
    behavior.confidence.detail은 이미 한국어 해석문이다. 그대로 복붙하지 않고
    자연스럽게 문장에 녹여 쓴다.
11) 추론 패턴 명시: 아래 추론 패턴 중 하나와 일치하면 섹션 1 또는 2에서 시나리오 이름을
    직접 언급한다. (예: "이는 Bear Market Relief Rally 패턴입니다.")
12) 해석 금지 영역:
   - horizon_bias.has_horizon_conflict=false이면 "불일치", "충돌", "엇갈림", "분기" 표현 금지.
     대신 "단기부터 중장기까지 방향이 일치합니다" 또는 "전 지평이 방어 쪽을 가리킵니다"처럼 서술한다.
   - text_available=false이면 텍스트 기반 원인론 금지 ("문서가 ... 을 보여줍니다" 같은 표현).
   - sell_priority에 없는 종목 언급 금지.
   - 입력에 없는 macro 스토리 생성 금지 (예: "연준이 금리를 인하할 것입니다").

━━━ 추론 패턴 (해당 신호 조합이 있으면 반드시 시나리오 이름 명시) ━━━

1) "Bear Market Relief Rally":
   regime.phase=침체/둔화 + horizon_bias.5d=공격 쪽 전망 + horizon_bias.60d=방어 쪽 전망
   → "단기 반등이지만 중장기 방향은 아직 하락 쪽입니다. 추격 매수는 피해야 합니다."

2) "스태그플레이션 경고":
   relative_strength 섹터에서 에너지 강세 + 채권 약세 + text_summary에 인플레이션 토픽 우세
   → "성장 둔화와 물가 상승이 동시에 진행 중임을 시사합니다."

3) "경기 후기 분산 (Late Cycle Divergence)":
   horizon_bias.conflict_5d_vs_60d=true (5D=공격 + 60D/120D=방어)
   → "단기 추격은 위험하며, 중장기 방어 준비가 필요합니다."

4) "연준 정책 교착":
   regime.sentiment=중립 + text_summary에 연준 정책/동결 토픽 집중
   → "시장이 정책 불확실성에 갇혀 방향성 신호가 약합니다."

5) "전환 임박 경보":
   horizon_bias.hazard > 20% + expected 방향 = 방어/침체
   → "전환 확률이 높습니다. 포지션 축소 준비가 필요합니다."

패턴이 여러 개 동시에 해당할 수 있음. 해당 없으면 시나리오 명시 생략.

━━━ 출력 형식 (4섹션 + 종합 요약) ━━━

각 섹션은 아래 구조를 따른다:
- 섹션 제목: <b>번호. 카테고리: "핵심 메시지"</b>
- 본문은 <b>소제목:</b> 다음에 해석문을 쓴다.
- 소제목마다 줄바꿈으로 구분한다.

<b>1. 시장 국면: "핵심 문구"</b> — 사용 필드: regime.*만
<b>시계열 상태:</b> regime.phase / regime.sentiment / regime.signal 세 시계열을 한 문장으로 요약한다.
<b>해석:</b> 현재 시장이 어떤 위치에 있는지 풀어쓴다. allocation/sell_priority 언급 금지.
해당하는 추론 패턴이 있으면 시나리오 이름을 명시한다.
(예: "지금의 반등은 이른바 Bear Market Relief Rally 패턴입니다. 펀더멘털 개선이 아닌 과매도 해소입니다.")

<b>2. 가설과 위험: "핵심 문구"</b> — 사용 필드: horizon_bias.*만
<b>전환 위험:</b> horizon_bias.hazard 수치와 expected 방향을 자연어로 설명한다.
<b>시계열 전망:</b> horizon_bias.5d(단기)와 horizon_bias.60d/120d(중장기)를 비교한다.
  has_horizon_conflict=true이면 "단기 안도에도 중장기는 여전히 방어 전망"처럼 분기 신호로 해석한다.
  has_horizon_conflict=false이면 "전 지평이 [방향] 쪽으로 일치합니다"로 한 문장. "불일치/충돌/엇갈림" 금지.
<b>해석:</b> 위험 데이터가 투자자에게 의미하는 바를 1-2문장으로 짚는다. regime/RS 언급 금지.
(예: "지금은 파티의 마지막 5분을 즐길 때이지, 새로 자리를 잡을 때가 아닙니다.")

<b>3. 시장 근거 및 수급: "핵심 문구"</b> — 사용 필드: relative_strength.*, text_summary.*만
<b>수급·상대강도:</b> relative_strength에서 주목할 패턴을 2-3개 관찰한다.
  소제목은 관찰된 패턴에 따라 자유롭게 정한다.
  (예: "<b>방어주와 국채의 동반 강세:</b> 투자자들이 침체를 준비하며 방어선으로 대피 중입니다.")
  (예: "<b>에너지의 독주:</b> 스태그플레이션 우려가 수면 위로 오르고 있습니다.")
<b>텍스트 해석:</b> text_summary의 tone과 상위 토픽으로 시장 심리를 1-2문장으로 요약한다.
  (text_available=false이면 이 소제목 전체를 "최근 문서 데이터 미수집으로 텍스트 흐름 분석을 생략합니다." 한 문장으로 대체한다.)
  behavior/regime/sell_priority 언급 금지.

<b>4. 투자 행동 가이드: "핵심 문구"</b> — 사용 필드: behavior.*, sell_priority만
<b>행동 제언:</b> behavior.guidance에 따른 구체적 행동(추격 매수 금지, 분할 매도, 적극 매수 등)을 명확히 쓴다.
<b>매도 우선순위:</b> sell_priority 최대 3개 종목만 서술. 왜 이 순서인지 해석. 목록 나열 금지.
  sell_priority가 없으면 이 소제목을 생략한다.
<b>신뢰도:</b> behavior.confidence 수준과 의미를 1문장으로 전달한다.
  regime/RS/horizon_bias 반복 금지.

<b>[종합 요약]</b>
전체 분석을 1문단으로 연결한다.
가장 강한 신호와 핵심 행동 권고로 마무리한다.
구체적 종목명을 활용해 실행 가능한 메시지로 끝낸다.
"""

_GUIDANCE_REASON_DESC = {
    "RUN_UNIVERSE_BLOCK": "전술 실행 게이트가 닫혀 있어 관망이 우선입니다.",
    "SHORT_PANIC": "단기 공황 신호가 있어 방어가 우선입니다.",
    "RISK_GATE_BLOCK": "단기 게이트가 비정상이라 비중 확대를 보류합니다.",
    "HAZARD_HIGH": "전환 위험이 높아 분할 접근이 유리합니다.",
    "MID_RISK_ON": "중기 위험선호 흐름이 유지돼 매수 허용 구간입니다.",
    "MID_RISK_OFF": "중기 방어 흐름이라 보수적 대응이 유리합니다.",
    "MID_NEUTRAL": "방향성이 뚜렷하지 않아 관망이 적절합니다.",
    "UNKNOWN": "근거가 부족해 기본 대응을 유지합니다.",
}

_CONF_REASON_DESC = {
    "HAZARD_HIGH": "단기 전환 위험이 높아 신뢰도를 낮게 봅니다.",
    "LOW_HAZARD_DIVERSE": "전환 위험이 낮고 지평 분화가 있어 신뢰도가 높습니다.",
    "MIXED": "신호가 혼재돼 중간 신뢰도로 해석합니다.",
    "MISSING_OR_UNKNOWN": "결측/미상 비중이 있어 신뢰도를 낮게 봅니다.",
}

_RISK_REASON_DESC = {
    "RUN_UNIVERSE_BLOCK": "전술 실행 게이트가 닫혀 있어 관망이 필요합니다.",
    "SHORT_PANIC": "단기 공황 신호로 변동성 확대 위험이 큽니다.",
    "HAZARD_HIGH": "단기 전환 가능성이 높아 추격 진입 위험이 큽니다.",
    "GROUP_UNKNOWN": "일부 전술 그룹 상태가 미확정이라 해석 오차가 큽니다.",
    "NONE": "현재 핵심 리스크는 제한적입니다.",
}


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


def build_interpretation_summary(deterministic_text: str, llm_text: Any) -> str:
    """상위 해석 문구(interpretation_summary) 선택(fail-open).

    - deterministic_text가 기본 골격이다.
    - llm_text가 유효 문자열이면 보조 문장으로 병합한다.
    - 그 외에는 결정론 문구(deterministic_text)만 사용한다.

    주의:
    - 여기서 다루는 것은 text-only `llm_summary` 필드가 아니라
      signal + text 결합 해석용 상위 문장이다.
    """
    deterministic = deterministic_text.strip()
    if isinstance(llm_text, str):
        stripped = llm_text.strip()
        if stripped:
            return deterministic or stripped
    return deterministic


def select_interpretation_text(deterministic_text: str, llm_text: Any) -> str:
    """Backward-compatible alias for interpretation summary selection."""
    return build_interpretation_summary(deterministic_text, llm_text)


def _safe_json_items(raw: Any) -> List[str]:
    if raw is None:
        return []
    parsed = raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except Exception:
            return []
    if not isinstance(parsed, list):
        return []
    out: List[str] = []
    for item in parsed:
        if isinstance(item, dict) and item.get("item"):
            out.append(str(item["item"]))
    return out


def _label_items(items: List[str], labels: Dict[str, str]) -> List[str]:
    out: List[str] = []
    for item in items:
        out.append(labels.get(item, item.replace("_", " ")))
    return out


def _pct_str(v: Any) -> str:
    try:
        if v is None:
            return "N/A"
        fv = float(v)
        if fv != fv:
            return "N/A"
        return f"{fv:.0%}"
    except Exception:
        return "N/A"


def _safe_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        fv = float(v)
        if fv != fv:
            return None
        return fv
    except Exception:
        return None


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


def _parse_transition_parts(expected: Any) -> Dict[str, str]:
    raw = "UNKNOWN" if expected is None else str(expected)
    parts = raw.split("_")
    if len(parts) != 3:
        return {
            "long": "미상",
            "mid": "미상",
            "short": "미상",
        }
    long_phase, mid_regime, short_signal = parts
    return {
        "long": {
            "EXPANSION": "확장",
            "LATE_CYCLE": "후기 사이클",
            "SLOWDOWN": "둔화",
            "RECESSION": "침체",
            "RECOVERY": "회복",
            "UNKNOWN": "미상",
        }.get(long_phase, long_phase),
        "mid": {
            "RISK_ON": "위험선호",
            "NEUTRAL": "혼조",
            "RISK_OFF": "위험회피",
            "UNKNOWN": "미상",
        }.get(mid_regime, mid_regime),
        "short": {
            "PANIC": "공황",
            "STABLE": "안정",
            "RELIEF": "안도",
            "UNKNOWN": "미상",
        }.get(short_signal, short_signal),
    }


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


def _get_report_ollama_client(base_url: str):
    import ollama  # type: ignore

    return ollama.Client(host=base_url)


def _report_llm_enabled() -> bool:
    return os.getenv("REPORT_LLM_ENABLED", "1").strip().lower() not in {"0", "false", "no"}


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
    for group, entries in payload.get("tactical_etf", {}).items():
        lbl = _GROUP_LABELS.get(group, group)
        rs_by_group[lbl] = [
            f"{e['name_ko']} {'+' if e['rs'] >= 0 else ''}{e['rs']:.1%}"
            for e in entries
        ]

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

    return {
        "date": payload.get("decision_date"),
        "regime": {
            "phase": mp.get("long_phase_label"),
            "sentiment": mp.get("mid_regime_label"),
            "signal": mp.get("short_signal_label"),
            "risk_gate": mp.get("risk_gate"),
        },
        "horizon_bias": {
            "5d": b5,
            "10d": _hb("bias_10d"),
            "20d": _hb("bias_20d"),
            "60d": b60,
            "120d": _hb("bias_120d"),
            "has_horizon_conflict": conflict,
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
        "text_summary": text_summary,
        "behavior": payload.get("behavior"),
        "sell_priority": (sell.get("sell_priority") or [])[:3] or None,
        "text_available": payload.get("text_available", False),
    }


def generate_llm_analysis(
    payload: Dict[str, Any],
    *,
    model: str,
    base_url: str,
    timeout: int,
) -> Optional[str]:
    """전체 signal 데이터를 읽고 통합 한국어 해석문을 생성한다.

    Returns:
        한국어 내러티브 문자열. 실패 또는 비활성 시 None (fail-open).
    """
    if not _report_llm_enabled():
        return None

    try:
        client = _get_report_ollama_client(base_url)
        temperature = float(os.getenv("REPORT_LLM_TEMPERATURE", "0.4"))
        num_predict = int(os.getenv("REPORT_LLM_NUM_PREDICT", "2048"))
        compact = _build_compact_llm_input(payload)
        response = client.chat(
            model=model,
            messages=[
                {"role": "system", "content": _ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(compact, ensure_ascii=False, default=str)},
            ],
            options={"temperature": temperature, "num_predict": num_predict},
        )
        raw = str(response["message"]["content"]).strip()
        if not raw:
            return None
        return raw
    except Exception:
        return None


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
