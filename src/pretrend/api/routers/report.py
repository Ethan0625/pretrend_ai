from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends
from starlette.concurrency import run_in_threadpool

from pretrend.api.auth import require_api_key
from pretrend.api.schemas import (
    StrategyReportAnalyzeRequest,
    StrategyReportAnalyzeResponse,
)
from pretrend.observability.explainability.context import generate_llm_analysis
from pretrend.pipeline.strategy_engine.json_safety import make_json_safe

router = APIRouter(
    prefix="/api/v1/report",
    tags=["report"],
    dependencies=[Depends(require_api_key)],
)


DEFAULT_REPORT_LLM_MODEL = "gemini-2.5-flash"
DEFAULT_REPORT_LLM_BASE_URL = "http://localhost:11434"
DEFAULT_REPORT_LLM_TIMEOUT = 30

logger = logging.getLogger(__name__)


def _env_str(name: str, default: str) -> str:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.split("#", 1)[0].strip()
    return value or default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw.split("#", 1)[0].strip())
    except (TypeError, ValueError):
        return default


@router.post("/strategy/analyze", response_model=StrategyReportAnalyzeResponse)
async def analyze_strategy_report(
    request: StrategyReportAnalyzeRequest,
) -> StrategyReportAnalyzeResponse:
    model = request.model or _env_str("REPORT_LLM_MODEL", DEFAULT_REPORT_LLM_MODEL)
    base_url = request.base_url or _env_str(
        "REPORT_LLM_BASE_URL", DEFAULT_REPORT_LLM_BASE_URL
    )
    timeout = request.timeout or _env_int(
        "REPORT_LLM_TIMEOUT", DEFAULT_REPORT_LLM_TIMEOUT
    )

    try:
        analysis_text = await run_in_threadpool(
            generate_llm_analysis,
            make_json_safe(request.payload),
            model=model,
            base_url=base_url,
            timeout=timeout,
        )
    except Exception:
        logger.warning("strategy report analysis failed; returning null analysis_text", exc_info=True)
        analysis_text = None
    return StrategyReportAnalyzeResponse(analysis_text=analysis_text)
