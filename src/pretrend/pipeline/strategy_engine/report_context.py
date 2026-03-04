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

_REPORT_LLM_SYSTEM_PROMPT = """You are a Korean financial report writer for a Telegram SIGNAL report.
Rewrite sections using provided market signals and text evidence.
Rules:
- Preserve facts and direction from the inputs. Do not invent new facts.
- Gold/strategy evidence is primary; text/llm feature is only supporting context.
- Do not copy raw field names or JSON keys into output.
- Do not quote llm_summary verbatim.
- Keep each output to one concise Korean sentence.
- Return JSON only with keys:
  context_long, context_mid, context_short,
  evidence_macro, evidence_price, evidence_flow, evidence_sentiment,
  text_summary
- If unsure, return an empty string for that field."""


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


def _call_report_llm(payload: Dict[str, Any], *, model: str, base_url: str, timeout: int) -> Dict[str, str]:
    client = _get_report_ollama_client(base_url)
    response = client.chat(
        model=model,
        messages=[
            {"role": "system", "content": _REPORT_LLM_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        format="json",
        options={"temperature": 0.1},
    )
    raw = str(response["message"]["content"])
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        return {}
    return {str(k): str(v).strip() for k, v in parsed.items() if isinstance(v, str)}


def _report_llm_enabled() -> bool:
    return os.getenv("REPORT_LLM_ENABLED", "1").strip().lower() not in {"0", "false", "no"}


def generate_report_llm_overrides(
    *,
    long_phase: str,
    mid_regime: str,
    short_signal: str,
    context_lines: List[str],
    evidence_lines: List[str],
    text_lines: List[str],
    model: str,
    base_url: str,
    timeout: int,
) -> Dict[str, str]:
    if not _report_llm_enabled():
        return {}

    payload = {
        "states": {
            "long_phase": long_phase,
            "mid_regime": mid_regime,
            "short_signal": short_signal,
        },
        "draft_context": {
            "long": context_lines[1][2:] if len(context_lines) > 1 and context_lines[1].startswith("→ ") else "",
            "mid": context_lines[4][2:] if len(context_lines) > 4 and context_lines[4].startswith("→ ") else "",
            "short": context_lines[7][2:] if len(context_lines) > 7 and context_lines[7].startswith("→ ") else "",
        },
        "draft_evidence": {
            "macro": evidence_lines[1][2:] if len(evidence_lines) > 1 and evidence_lines[1].startswith("→ ") else "",
            "price": evidence_lines[4][2:] if len(evidence_lines) > 4 and evidence_lines[4].startswith("→ ") else "",
            "flow": evidence_lines[7][2:] if len(evidence_lines) > 7 and evidence_lines[7].startswith("→ ") else "",
            "sentiment": evidence_lines[10][2:] if len(evidence_lines) > 10 and evidence_lines[10].startswith("→ ") else "",
        },
        "text_windows": {
            "summary_lines": [line[2:] if line.startswith("→ ") else line for line in text_lines[1:4]]
            if len(text_lines) >= 4 else [],
        },
    }
    try:
        return _call_report_llm(payload, model=model, base_url=base_url, timeout=timeout)
    except Exception:
        return {}


def apply_report_llm_overrides(
    context_lines: List[str],
    evidence_lines: List[str],
    text_lines: List[str],
    overrides: Optional[Dict[str, str]],
) -> tuple[List[str], List[str], List[str]]:
    if not overrides:
        return context_lines, evidence_lines, text_lines

    out_context = list(context_lines)
    out_evidence = list(evidence_lines)
    out_text = list(text_lines)

    mapping_context = {
        "context_long": 1,
        "context_mid": 4,
        "context_short": 7,
    }
    for key, idx in mapping_context.items():
        val = overrides.get(key, "").strip()
        if val:
            out_context[idx] = f"→ {val}"

    mapping_evidence = {
        "evidence_macro": 1,
        "evidence_price": 4,
        "evidence_flow": 7,
        "evidence_sentiment": 10,
    }
    for key, idx in mapping_evidence.items():
        val = overrides.get(key, "").strip()
        if val:
            out_evidence[idx] = f"→ {val}"

    text_summary = overrides.get("text_summary", "").strip()
    if text_summary:
        if not out_text:
            out_text = ["📝텍스트 해석", f"→ {text_summary}"]
        elif len(out_text) >= 1 and out_text[0] == "📝텍스트 해석":
            out_text = [out_text[0], f"→ {text_summary}"] + out_text[1:]
        elif len(out_text) >= 2 and out_text[1] == "📝텍스트 해석":
            out_text = [out_text[0], out_text[1], f"→ {text_summary}"] + out_text[2:]
        elif len(out_text) >= 1:
            out_text = [out_text[0], f"→ {text_summary}"] + out_text[1:]

    return out_context, out_evidence, out_text


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
