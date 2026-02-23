"""Telegram 시장 컨텍스트/근거 렌더링 헬퍼."""
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
