"""Text Gold LLM Build — Ollama 기반 Observer-only annotation."""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from pretrend.pipeline.text.config import TextPipelineConfig
from pretrend.pipeline.text.gold_build import _load_silver

logger = logging.getLogger(__name__)

_FEATURE_VERSION = "v1"
_PROMPT_VERSION = "text_annotation_v1"
_TONE_VALUE = {"hawkish": 1.0, "dovish": -1.0, "neutral": 0.0}
_TONE_ALLOWLIST = frozenset({"hawkish", "dovish", "neutral"})
_TOPIC_ALLOWLIST = frozenset(
    {
        "sp500", "nasdaq100", "dow30", "russell2000", "us_dividend",
        "south_korea", "china", "japan", "india",
        "gold", "silver", "crude_oil", "natural_gas", "agriculture",
        "us_treasury_long",
        "energy_sector", "financials", "regional_banks", "semiconductor",
        "information_tech", "health_care", "materials",
        "consumer_discretionary", "consumer_staples", "communication_services",
        "real_estate", "utilities", "nuclear_energy",
    }
)
_TAG_ALLOWLIST = frozenset(
    {
        "hike", "cut", "qe", "qt", "guidance_change", "fiscal_stimulus", "regulation_change",
        "downgrade", "default", "spread_widening", "liquidity_crunch", "bank_run", "bailout",
        "earnings_miss", "earnings_beat", "guidance_raise", "guidance_cut", "layoff", "bankruptcy",
        "crash", "capitulation", "volatility_spike", "risk_off", "risk_on",
    }
)
_GOLD_LLM_COLUMNS = [
    "trade_date",
    "doc_id",
    "feature_name",
    "feature_value",
    "feature_str",
    "confidence",
    "feature_version",
    "model_id",
    "prompt_version",
    "coverage_ratio",
    "staleness_days",
]
_SYSTEM_PROMPT = (
    "You are a financial document analyst. Analyze the given document and return a JSON object "
    'with exactly these fields: "summary", "tone", "topics", "tags", "confidence". '
    'Tone must be one of "hawkish", "dovish", "neutral". '
    "Return ONLY valid JSON."
)


@dataclass
class TextGoldLlmResult:
    docs_input: int
    docs_processed: int
    docs_skipped: int
    feature_rows: int
    coverage_ratio: float
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None


def _get_ollama_module():
    import ollama  # type: ignore

    return ollama


def _get_ollama_client(base_url: str):
    mod = _get_ollama_module()
    return mod.Client(host=base_url)


def _check_ollama_available(base_url: str) -> bool:
    try:
        client = _get_ollama_client(base_url)
        client.list()
        return True
    except Exception as exc:
        logger.warning("Ollama unavailable: %s", exc)
        return False


def _ollama_chat(text: str, model: str, base_url: str, timeout: int) -> str:
    client = _get_ollama_client(base_url)
    response = client.chat(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": text[:4096]},
        ],
        format="json",
        options={"temperature": 0.1},
    )
    return str(response["message"]["content"])


def _parse_llm_response(raw_json: str) -> Optional[dict]:
    try:
        parsed = json.loads(raw_json)
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _filter_response(parsed: dict) -> dict:
    tone = str(parsed.get("tone", "neutral")).lower()
    if tone not in _TONE_ALLOWLIST:
        tone = "neutral"

    topics = parsed.get("topics", [])
    if not isinstance(topics, list):
        topics = []
    topics = [str(t) for t in topics[:3] if str(t) in _TOPIC_ALLOWLIST]

    tags = parsed.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    tags = [str(t) for t in tags[:5] if str(t) in _TAG_ALLOWLIST]

    confidence = parsed.get("confidence", 0.5)
    try:
        confidence = float(confidence)
    except Exception:
        confidence = 0.5
    if not (0.0 <= confidence <= 1.0):
        confidence = 0.5

    summary = parsed.get("summary", "")
    if not isinstance(summary, str):
        summary = str(summary)

    return {
        "summary": summary,
        "tone": tone,
        "topics": topics,
        "tags": tags,
        "confidence": confidence,
    }


def _to_long_format(
    doc_id: str,
    trade_date: str,
    filtered: dict,
    model_id: str,
    prompt_version: str,
) -> List[dict]:
    confidence = float(filtered.get("confidence", 0.5))
    return [
        {
            "trade_date": trade_date,
            "doc_id": doc_id,
            "feature_name": "llm_tone",
            "feature_value": _TONE_VALUE.get(str(filtered.get("tone", "neutral")), 0.0),
            "feature_str": None,
            "confidence": confidence,
            "feature_version": _FEATURE_VERSION,
            "model_id": model_id,
            "prompt_version": prompt_version,
            "coverage_ratio": 0.0,
            "staleness_days": 0,
        },
        {
            "trade_date": trade_date,
            "doc_id": doc_id,
            "feature_name": "llm_topics",
            "feature_value": 0.0,
            "feature_str": json.dumps(filtered.get("topics", []), ensure_ascii=True),
            "confidence": confidence,
            "feature_version": _FEATURE_VERSION,
            "model_id": model_id,
            "prompt_version": prompt_version,
            "coverage_ratio": 0.0,
            "staleness_days": 0,
        },
        {
            "trade_date": trade_date,
            "doc_id": doc_id,
            "feature_name": "llm_tags",
            "feature_value": 0.0,
            "feature_str": json.dumps(filtered.get("tags", []), ensure_ascii=True),
            "confidence": confidence,
            "feature_version": _FEATURE_VERSION,
            "model_id": model_id,
            "prompt_version": prompt_version,
            "coverage_ratio": 0.0,
            "staleness_days": 0,
        },
        {
            "trade_date": trade_date,
            "doc_id": doc_id,
            "feature_name": "llm_summary",
            "feature_value": 0.0,
            "feature_str": str(filtered.get("summary", "")),
            "confidence": confidence,
            "feature_version": _FEATURE_VERSION,
            "model_id": model_id,
            "prompt_version": prompt_version,
            "coverage_ratio": 0.0,
            "staleness_days": 0,
        },
    ]


def _batch_annotate(
    docs_df: pd.DataFrame,
    model: str,
    base_url: str,
    timeout: int,
) -> List[dict]:
    rows: List[dict] = []
    if docs_df.empty:
        return rows
    for _, rec in docs_df.iterrows():
        try:
            raw = _ollama_chat(str(rec["clean_text"]), model, base_url, timeout)
            parsed = _parse_llm_response(raw)
            if parsed is None:
                logger.warning("LLM JSON parse failed: doc_id=%s", rec.get("doc_id"))
                continue
            filtered = _filter_response(parsed)
            rows.extend(
                _to_long_format(
                    doc_id=str(rec["doc_id"]),
                    trade_date=str(rec["event_date"]),
                    filtered=filtered,
                    model_id=model,
                    prompt_version=_PROMPT_VERSION,
                )
            )
        except Exception as exc:
            logger.warning("LLM annotate skipped: doc_id=%s error=%s", rec.get("doc_id"), exc)
            continue
    return rows


def _write_gold_llm_partition(df: pd.DataFrame, gold_root: Path) -> List[Path]:
    paths: List[Path] = []
    if df.empty:
        return paths
    x = df.copy()
    x["trade_date"] = pd.to_datetime(x["trade_date"])
    x["year"] = x["trade_date"].dt.year
    x["month"] = x["trade_date"].dt.month
    x["trade_date"] = x["trade_date"].dt.strftime("%Y-%m-%d")
    for (year, month), group in x.groupby(["year", "month"]):
        partition_dir = gold_root / "text_llm_features" / f"year={year}" / f"month={month:02d}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        filename = f"gold_llm_{year}{month:02d}.parquet"
        out_path = partition_dir / filename
        tmp_path = partition_dir / f".tmp_{uuid.uuid4().hex}_{filename}"
        out_df = group.drop(columns=["year", "month"]).reset_index(drop=True)
        out_df.to_parquet(tmp_path, index=False, compression="snappy")
        tmp_path.rename(out_path)
        paths.append(out_path)
    return paths


def run_text_gold_llm_build(
    start_date: date,
    end_date: date,
    cfg: Optional[TextPipelineConfig] = None,
) -> TextGoldLlmResult:
    if cfg is None:
        cfg = TextPipelineConfig.default()

    if not _check_ollama_available(cfg.ollama_base_url):
        return TextGoldLlmResult(
            docs_input=0,
            docs_processed=0,
            docs_skipped=0,
            feature_rows=0,
            coverage_ratio=0.0,
        )

    silver_df = _load_silver(cfg.silver_root, start_date, end_date)
    if silver_df.empty:
        return TextGoldLlmResult(
            docs_input=0,
            docs_processed=0,
            docs_skipped=0,
            feature_rows=0,
            coverage_ratio=0.0,
        )

    docs_df = silver_df[silver_df.get("quality_flags", "ok") == "ok"].copy()
    docs_input = int(len(docs_df))
    if docs_input == 0:
        return TextGoldLlmResult(
            docs_input=0,
            docs_processed=0,
            docs_skipped=0,
            feature_rows=0,
            coverage_ratio=0.0,
        )

    rows = _batch_annotate(
        docs_df=docs_df,
        model=cfg.ollama_model,
        base_url=cfg.ollama_base_url,
        timeout=int(cfg.ollama_timeout),
    )
    docs_processed = int(len({r["doc_id"] for r in rows}))
    docs_skipped = int(max(docs_input - docs_processed, 0))
    coverage_ratio = float(docs_processed / docs_input) if docs_input > 0 else 0.0

    if not rows:
        return TextGoldLlmResult(
            docs_input=docs_input,
            docs_processed=0,
            docs_skipped=docs_input,
            feature_rows=0,
            coverage_ratio=0.0,
        )

    out_df = pd.DataFrame(rows)[_GOLD_LLM_COLUMNS]
    if not out_df.empty:
        out_df["coverage_ratio"] = coverage_ratio
        out_df["staleness_days"] = 0
        _write_gold_llm_partition(out_df, cfg.gold_llm_root)

    return TextGoldLlmResult(
        docs_input=docs_input,
        docs_processed=docs_processed,
        docs_skipped=docs_skipped,
        feature_rows=int(len(out_df)),
        coverage_ratio=coverage_ratio,
    )
