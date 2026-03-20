"""Telegram 시장 컨텍스트/근거/다음 스텝 렌더링 헬퍼.

용어:
- llm_feature: text snapshot만 기반으로 생성된 LLM 산출물 묶음
- llm_summary: llm_feature 내부의 text-only 요약 필드
- interpretation_summary: signal snapshot + text snapshot을 결합해 만든
  상위 해석 문장(리포트/Telegram 전용)

모듈 구조 (분리된 서브모듈):
- report_context_localization: 라벨 상수, LLM 프롬프트, 전이 포매터
- report_context_schema: 데이터 검증/변환 유틸
- report_context_interpretation: 신호 해석 빌더 (순수 함수)
- report_context_formatter: Telegram 렌더링 함수
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

# ── Re-exports (backward compat) ─────────────────────────────────────────────

from pretrend.pipeline.strategy_engine.report_context_localization import (  # noqa: F401
    _ANALYSIS_SYSTEM_PROMPT,
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

from pretrend.pipeline.strategy_engine.report_context_schema import (  # noqa: F401
    _label_items,
    _pct_str,
    _safe_float,
    _safe_json_items,
    build_interpretation_summary,
    safe_json_dict,
    select_interpretation_text,
)

from pretrend.pipeline.strategy_engine.report_context_interpretation import (  # noqa: F401
    _build_compact_llm_input,
    _build_group_material,
    _build_long_context_detail,
    _build_mid_context_detail,
    _build_next_step_material,
    _build_short_context_detail,
    _context_with_text,
    _EM_ETF_SYMBOLS,
    _infer_sell_reason_tag,
    _tone_bucket,
    _window_phrase,
    build_llm_analysis_payload,
    build_risk_summary_struct,
    build_signal_confidence_struct,
    build_trading_guidance_struct,
    format_risk_summary_lines,
    format_signal_confidence_lines,
    format_trading_guidance_lines,
)

from pretrend.pipeline.strategy_engine.report_context_formatter import (  # noqa: F401
    build_context_lines,
    build_diagnostic_lines,
    build_evidence_lines,
    build_switch_lines,
    build_text_overlay_lines,
    build_text_window_lines,
    format_bias_state_line,
    format_group_transition_lines,
    format_next_step_hazard_lines,
)


# ── LLM I/O ──────────────────────────────────────────────────────────────────

def _get_report_ollama_client(base_url: str):
    import ollama  # type: ignore

    return ollama.Client(host=base_url)


def _call_gemini(
    model: str,
    system_prompt: str,
    user_content: str,
    temperature: float,
    max_tokens: int,
) -> str:
    from google import genai  # type: ignore
    from google.genai import types as genai_types  # type: ignore

    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=user_content,
        config=genai_types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            max_output_tokens=max_tokens,
        ),
    )
    return response.text.strip()


def _report_llm_enabled() -> bool:
    return os.getenv("REPORT_LLM_ENABLED", "1").strip().lower() not in {"0", "false", "no"}


def generate_llm_analysis(
    payload: Dict[str, Any],
    *,
    model: str,
    base_url: str,
    timeout: int,
) -> Optional[str]:
    """전체 signal 데이터를 읽고 통합 한국어 해석문을 생성한다.

    REPORT_LLM_PROVIDER=gemini(기본값): Gemini API 시도 → 실패 시 Ollama fallback.
    REPORT_LLM_PROVIDER=ollama: Ollama 직접 사용.
    항상 fail-open (예외 시 None 반환).
    """
    if not _report_llm_enabled():
        return None

    provider = os.getenv("REPORT_LLM_PROVIDER", "gemini").strip().lower()
    temperature = float(os.getenv("REPORT_LLM_TEMPERATURE", "0.4"))
    num_predict = int(os.getenv("REPORT_LLM_NUM_PREDICT", "2048"))
    retries = int(os.getenv("REPORT_LLM_RETRY", "3"))
    compact = _build_compact_llm_input(payload)
    user_content = json.dumps(compact, ensure_ascii=False, default=str)

    if provider == "gemini":
        for attempt in range(retries):
            try:
                raw = _call_gemini(model, _ANALYSIS_SYSTEM_PROMPT, user_content, temperature, num_predict)
                if raw:
                    return raw
            except Exception:
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)

        # Gemini 전체 실패 → Ollama fallback
        if os.getenv("REPORT_LLM_FALLBACK_ENABLED", "1").strip().lower() not in {"0", "false", "no"}:
            try:
                fallback_model = os.getenv("OLLAMA_MODEL", "llama3.1:latest")
                client = _get_report_ollama_client(base_url)
                response = client.chat(
                    model=fallback_model,
                    messages=[
                        {"role": "system", "content": _ANALYSIS_SYSTEM_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                    options={"temperature": temperature, "num_predict": num_predict},
                )
                raw = str(response["message"]["content"]).strip()
                return raw if raw else None
            except Exception:
                return None
        return None

    # provider == "ollama" (기존 동작)
    try:
        client = _get_report_ollama_client(base_url)
        response = client.chat(
            model=model,
            messages=[
                {"role": "system", "content": _ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            options={"temperature": temperature, "num_predict": num_predict},
        )
        raw = str(response["message"]["content"]).strip()
        return raw if raw else None
    except Exception:
        return None
