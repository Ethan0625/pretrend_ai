"""Text Gold LLM Build — Ollama 기반 Observer-only annotation."""
from __future__ import annotations

import json
import logging
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from pretrend.pipeline.text.config import TextPipelineConfig
from pretrend.pipeline.text.gold_build import _load_silver

logger = logging.getLogger(__name__)

_FEATURE_VERSION = "v1"
_PROMPT_VERSION = "text_annotation_v2"
_TONE_VALUE = {"hawkish": 1.0, "dovish": -1.0, "neutral": 0.0}
_TONE_ALLOWLIST = frozenset({"hawkish", "dovish", "neutral"})
TOPIC_TAXONOMY: Dict[str, List[str]] = {
    "index": ["sp500", "nasdaq100", "dow30", "russell2000", "us_dividend"],
    "country": ["south_korea", "china", "japan", "india"],
    "commodity": [
        "gold", "gold_miners", "silver", "crude_oil", "oil_producers",
        "natural_gas", "agriculture",
    ],
    "bond": [
        "us_treasury_long", "high_yield_bond", "investment_grade_bond",
        "short_treasury", "tips",
    ],
    "sector": [
        "energy_sector", "financials", "regional_banks", "semiconductor",
        "information_tech", "health_care", "materials",
        "consumer_discretionary", "consumer_staples", "communication_services",
        "real_estate", "utilities", "nuclear_energy", "industrials",
    ],
    "macro": ["fed_policy", "inflation", "employment", "treasury_yield"],
}
TAG_TAXONOMY: Dict[str, List[str]] = {
    "policy_action": ["hike", "cut", "pause", "pivot", "qe", "qt"],
    "forward_guidance": ["guidance_change", "guidance_raise", "guidance_cut"],
    "fiscal_trade": ["fiscal_stimulus", "regulation_change", "tariff"],
    "credit_event": [
        "downgrade", "default", "spread_widening",
        "liquidity_crunch", "bank_run", "bailout",
    ],
    "corporate_event": ["earnings_miss", "earnings_beat", "layoff", "bankruptcy"],
    "market_regime": [
        "crash", "correction", "capitulation",
        "volatility_spike", "risk_off", "risk_on",
    ],
}
_TAG_DESCRIPTIONS: Dict[str, str] = {
    "hike": "raising interest rates",
    "cut": "lowering interest rates",
    "pause": "maintaining current interest rate levels",
    "pivot": "shifting monetary policy direction",
    "qe": "quantitative easing or asset purchases",
    "qt": "quantitative tightening or balance sheet reduction",
    "guidance_change": "change in forward guidance language",
    "guidance_raise": "raising economic or earnings outlook",
    "guidance_cut": "lowering economic or earnings outlook",
    "fiscal_stimulus": "government spending or tax policy stimulus",
    "regulation_change": "new or changed financial regulation",
    "tariff": "trade tariffs or import duties",
    "downgrade": "credit or rating downgrade",
    "default": "debt default or missed payment",
    "spread_widening": "credit spread widening",
    "liquidity_crunch": "tightening liquidity conditions",
    "bank_run": "bank deposit withdrawals or banking crisis",
    "bailout": "government or institutional rescue package",
    "earnings_miss": "company earnings below expectations",
    "earnings_beat": "company earnings above expectations",
    "layoff": "workforce reduction or job cuts",
    "bankruptcy": "company filing for bankruptcy",
    "crash": "sharp market decline",
    "correction": "moderate market pullback (10-20%)",
    "capitulation": "panic selling or market surrender",
    "volatility_spike": "sharp increase in market volatility",
    "risk_off": "flight to safety or risk aversion",
    "risk_on": "increased risk appetite",
}
_TOPIC_ALLOWLIST = frozenset(item for items in TOPIC_TAXONOMY.values() for item in items)
_TOPIC_TO_CATEGORY: Dict[str, str] = {
    item: category for category, items in TOPIC_TAXONOMY.items() for item in items
}
_TAG_ALLOWLIST = frozenset(item for items in TAG_TAXONOMY.values() for item in items)
_TAG_TO_CATEGORY: Dict[str, str] = {
    item: category for category, items in TAG_TAXONOMY.items() for item in items
}
_GOLD_LLM_COLUMNS = [
    "trade_date",
    "doc_id",
    "source",
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
_TAG_LIST_WITH_DESC = "\n".join(
    f"- {tag}: {_TAG_DESCRIPTIONS[tag]}"
    for tag in sorted(_TAG_ALLOWLIST)
)
_SYSTEM_PROMPT = (
    "You are a financial document analyst. Analyze the given document and return a JSON object "
    'with exactly these fields: "summary", "tone", "topics", "tags", "confidence".\n\n'
    'Tone must be one of: "hawkish", "dovish", "neutral".\n\n'
    "Topics must be selected ONLY from this list (pick up to 3 most relevant):\n"
    + ", ".join(sorted(_TOPIC_ALLOWLIST))
    + "\n\n"
    "Tags MUST be selected from the list below. "
    "Most financial documents will match at least 1-2 tags. "
    "Select the most relevant (up to 5):\n"
    + _TAG_LIST_WITH_DESC
    + "\n\n"
    "IMPORTANT tag selection rules:\n"
    '- If the document mentions raising rates, increasing the federal funds rate, '
    'or raising the interest rate paid on reserve balances → use "hike"\n'
    '- If the document mentions lowering or cutting rates → use "cut"\n'
    '- If the document mentions maintaining, keeping, or holding rates unchanged → use "pause"\n'
    '- Implementation notes, directives, and operational details about rate changes '
    "count as the corresponding policy action (hike/cut/pause)\n"
    '- If the document discusses balance sheet reduction or runoff → use "qt"\n'
    '- If the document discusses asset purchases or reinvestment → use "qe"\n\n'
    "Examples:\n"
    '{"summary":"The Fed raised the federal funds rate by 25bp to 4.5%","tone":"hawkish",'
    '"topics":["fed_policy","inflation"],"tags":["hike"],"confidence":0.95}\n'
    '{"summary":"The Board voted to raise the interest rate paid on reserve balances to 4.4%",'
    '"tone":"hawkish","topics":["fed_policy"],"tags":["hike"],"confidence":0.9}\n'
    '{"summary":"The Committee maintained the target range at 5.25-5.5%","tone":"neutral",'
    '"topics":["fed_policy"],"tags":["pause"],"confidence":0.9}\n\n'
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


_CONTENT_MARKERS = [
    "for release",
    "the federal open market",
    "the committee",
    "information received",
    "recent indicators",
    "statement regarding",
]
_MULTISPACE_RE = re.compile(r"\s{3,}")


def _prepare_text_for_llm(text: str, max_chars: int = 4096) -> str:
    """LLM 입력 전 보일러플레이트 스킵 + 잘림.

    콘텐츠 마커가 발견되면 그 200 chars 앞부터 시작하여
    웹사이트 네비게이션 등 무의미한 앞부분을 건너뛴다.
    마커가 없으면 원문 그대로 사용한다.
    """
    lower = text.lower()
    best_pos = -1
    for marker in _CONTENT_MARKERS:
        idx = lower.find(marker)
        if idx >= 0 and (best_pos < 0 or idx < best_pos):
            best_pos = idx
    if best_pos > 200:
        text = text[best_pos - 200:]
    cleaned = _MULTISPACE_RE.sub(" ", text).strip()
    return cleaned[:max_chars]


def _ollama_chat(text: str, model: str, base_url: str, timeout: int) -> str:
    client = _get_ollama_client(base_url)
    response = client.chat(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _prepare_text_for_llm(text)},
        ],
        format="json",
        options={"temperature": 0.1},
    )
    return str(response["message"]["content"])


def _parse_llm_response(raw_json: str) -> Optional[dict]:
    # Try direct parse first
    try:
        parsed = json.loads(raw_json)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    # Extract JSON from markdown code block (```json ... ``` or ``` ... ```)
    import re
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_json, re.DOTALL)
    if m:
        try:
            parsed = json.loads(m.group(1))
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    # Try finding first { ... } block
    start = raw_json.find("{")
    end = raw_json.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(raw_json[start:end + 1])
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return None


def _filter_response(parsed: dict) -> dict:
    tone = str(parsed.get("tone", "neutral")).lower()
    if tone not in _TONE_ALLOWLIST:
        tone = "neutral"

    topics_raw = parsed.get("topics", [])
    if not isinstance(topics_raw, list):
        topics_raw = []
    topics = [
        {"category": _TOPIC_TO_CATEGORY[str(t)], "item": str(t)}
        for t in topics_raw[:3]
        if str(t) in _TOPIC_ALLOWLIST
    ]

    tags_raw = parsed.get("tags", [])
    if not isinstance(tags_raw, list):
        tags_raw = []
    tags = [
        {"category": _TAG_TO_CATEGORY[str(t)], "item": str(t)}
        for t in tags_raw[:5]
        if str(t) in _TAG_ALLOWLIST
    ]

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
    source: str = "unknown",
) -> List[dict]:
    confidence = float(filtered.get("confidence", 0.5))
    base = {
        "trade_date": trade_date,
        "doc_id": doc_id,
        "source": source,
        "confidence": confidence,
        "feature_version": _FEATURE_VERSION,
        "model_id": model_id,
        "prompt_version": prompt_version,
        "coverage_ratio": 0.0,
        "staleness_days": 0,
    }
    return [
        {**base, "feature_name": "llm_tone",
         "feature_value": _TONE_VALUE.get(str(filtered.get("tone", "neutral")), 0.0),
         "feature_str": None},
        {**base, "feature_name": "llm_topics",
         "feature_value": 0.0,
         "feature_str": json.dumps(filtered.get("topics", []), ensure_ascii=True)},
        {**base, "feature_name": "llm_tags",
         "feature_value": 0.0,
         "feature_str": json.dumps(filtered.get("tags", []), ensure_ascii=True)},
        {**base, "feature_name": "llm_summary",
         "feature_value": 0.0,
         "feature_str": str(filtered.get("summary", ""))},
    ]


def _annotate_one(
    doc_id: str,
    event_date: str,
    clean_text: str,
    source: str,
    model: str,
    base_url: str,
    timeout: int,
) -> Tuple[str, List[dict]]:
    """단일 문서 LLM 호출 → long-format rows 반환. (thread-safe)"""
    raw = _ollama_chat(clean_text, model, base_url, timeout)
    parsed = _parse_llm_response(raw)
    if parsed is None:
        logger.warning("LLM JSON parse failed: doc_id=%s", doc_id)
        return doc_id, []
    filtered = _filter_response(parsed)
    return doc_id, _to_long_format(
        doc_id=doc_id,
        trade_date=event_date,
        filtered=filtered,
        model_id=model,
        prompt_version=_PROMPT_VERSION,
        source=source,
    )


def _batch_annotate(
    docs_df: pd.DataFrame,
    model: str,
    base_url: str,
    timeout: int,
    max_workers: int = 1,
) -> List[dict]:
    rows: List[dict] = []
    if docs_df.empty:
        return rows

    has_source = "source" in docs_df.columns
    tasks = [
        (
            str(rec["doc_id"]),
            str(rec["event_date"]),
            str(rec["clean_text"]),
            str(rec["source"]) if has_source else "unknown",
        )
        for _, rec in docs_df.iterrows()
    ]

    if max_workers <= 1:
        for doc_id, event_date, clean_text, source in tasks:
            try:
                _, doc_rows = _annotate_one(
                    doc_id, event_date, clean_text, source, model, base_url, timeout,
                )
                rows.extend(doc_rows)
            except Exception as exc:
                logger.warning("LLM annotate skipped: doc_id=%s error=%s", doc_id, exc)
        return rows

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                _annotate_one, doc_id, event_date, clean_text, source,
                model, base_url, timeout,
            ): doc_id
            for doc_id, event_date, clean_text, source in tasks
        }
        done_count = 0
        for future in as_completed(futures):
            doc_id = futures[future]
            done_count += 1
            try:
                _, doc_rows = future.result()
                rows.extend(doc_rows)
            except Exception as exc:
                logger.warning("LLM annotate skipped: doc_id=%s error=%s", doc_id, exc)
            if done_count % 50 == 0:
                logger.info("LLM progress: %d / %d docs", done_count, len(tasks))
    return rows


def _write_gold_llm_partition(df: pd.DataFrame, gold_root: Path) -> List[Path]:
    """source별 파티션 분리 저장.

    파일명: gold_llm_{source}_{YYYYMM}.parquet
    source_filter로 특정 source만 실행해도 다른 source 파일이 보존된다.
    """
    paths: List[Path] = []
    if df.empty:
        return paths
    x = df.copy()
    x["trade_date"] = pd.to_datetime(x["trade_date"])
    x["year"] = x["trade_date"].dt.year
    x["month"] = x["trade_date"].dt.month
    x["trade_date"] = x["trade_date"].dt.strftime("%Y-%m-%d")
    if "source" not in x.columns:
        x["source"] = "unknown"
    for (year, month, source), group in x.groupby(["year", "month", "source"]):
        partition_dir = gold_root / "text_llm_features" / f"year={year}" / f"month={month:02d}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        filename = f"gold_llm_{source}_{year}{month:02d}.parquet"
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
    source_filter: Optional[str] = None,
    max_workers: int = 1,
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
    if source_filter and "source" in docs_df.columns:
        docs_df = docs_df[docs_df["source"] == source_filter]
    docs_input = int(len(docs_df))
    if docs_input == 0:
        return TextGoldLlmResult(
            docs_input=0,
            docs_processed=0,
            docs_skipped=0,
            feature_rows=0,
            coverage_ratio=0.0,
        )

    logger.info(
        "LLM build: %d docs, source_filter=%s, max_workers=%d",
        docs_input, source_filter, max_workers,
    )
    rows = _batch_annotate(
        docs_df=docs_df,
        model=cfg.ollama_model,
        base_url=cfg.ollama_base_url,
        timeout=int(cfg.ollama_timeout),
        max_workers=max_workers,
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
