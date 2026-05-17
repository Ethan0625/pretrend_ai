"""Data validation and schema utilities for report_context.

Pure functions — no I/O, no external dependencies.
"""
from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional


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
        if not math.isfinite(fv):
            return "N/A"
        return f"{fv:.0%}"
    except Exception:
        return "N/A"


def _safe_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        fv = float(v)
        if not math.isfinite(fv):
            return None
        return fv
    except Exception:
        return None
