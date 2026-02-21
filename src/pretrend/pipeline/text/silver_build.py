"""Text Silver Build — Bronze 정제 + 중복 제거 + 품질 플래그 + asset_scope.

입력: data/bronze/text/{source}/ingest_date=YYYY-MM-DD/*.parquet
출력: data/silver/text/text_enriched/event_date=YYYY-MM-DD/silver_{YYYYMMDD}.parquet

Silver 스키마:
    doc_id, source, canonical_url, event_date, title, clean_text,
    asset_scope, quality_flags, lang, enricher_version, published_at
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

import pandas as pd

from pretrend.pipeline.text.config import TextPipelineConfig

logger = logging.getLogger(__name__)

_ENRICHER_VERSION = "v0"

# Silver 스키마 컬럼 순서
_SILVER_COLUMNS = [
    "doc_id",
    "source",
    "canonical_url",
    "event_date",
    "title",
    "clean_text",
    "asset_scope",
    "quality_flags",
    "lang",
    "enricher_version",
    "published_at",
]

# asset_scope 감지 키워드
_MACRO_KEYWORDS = (
    "federal reserve", "fomc", "fed funds", "inflation", "unemployment",
    "gdp", "monetary policy", "interest rate", "treasury", "yield curve",
    "recession", "economic outlook", "beige book",
)
_THEME_KEYWORDS = (
    "sector", "etf", "energy", "technology", "healthcare", "financial",
    "consumer", "industrial", "utilities", "real estate", "communication",
    "materials", "semiconductor", "biotech", "clean energy",
)


# ------------------------------------------------------------------
# HTML → clean text
# ------------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>", re.DOTALL)
_WHITESPACE_RE = re.compile(r"\s+")


def _strip_html(html: str) -> str:
    """HTML 태그 제거 + 연속 공백 정리."""
    text = _TAG_RE.sub(" ", html)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


# ------------------------------------------------------------------
# Quality flags
# ------------------------------------------------------------------

def _compute_quality_flags(clean_text: str, lang: str, body: str) -> str:
    """품질 플래그 문자열 (쉼표 구분)."""
    flags = []
    if lang != "en":
        flags.append("non_english")
    if len(clean_text) < 100:
        flags.append("body_too_short")
    if len(clean_text) > 500_000:
        flags.append("body_too_long")
    if "<html" in body.lower() or "<!doctype" in body.lower():
        flags.append("has_html_markup")
    return ",".join(flags) if flags else "ok"


# ------------------------------------------------------------------
# asset_scope
# ------------------------------------------------------------------

def _detect_asset_scope(source: str, title: str, clean_text: str) -> str:
    """문서의 자산 범위 분류: macro | theme | ticker | unknown.

    v0 규칙:
    - fed_fomc 소스 → macro
    - SEC 8-K/10-K/10-Q → ticker (특정 기업 공시)
    - 텍스트 내 macro 키워드 다수 → macro
    - 텍스트 내 theme 키워드 다수 → theme
    """
    if source == "fed_fomc":
        return "macro"
    if source == "sec_edgar":
        return "ticker"

    text_lower = (title + " " + clean_text[:2000]).lower()
    macro_hits = sum(1 for kw in _MACRO_KEYWORDS if kw in text_lower)
    theme_hits = sum(1 for kw in _THEME_KEYWORDS if kw in text_lower)

    if macro_hits >= 2:
        return "macro"
    if theme_hits >= 2:
        return "theme"
    return "unknown"


# ------------------------------------------------------------------
# Bronze 로딩
# ------------------------------------------------------------------

def _load_bronze(bronze_root: Path, start_date: date, end_date: date) -> pd.DataFrame:
    """Bronze 파티션 로드 (날짜 범위 필터)."""
    frames: List[pd.DataFrame] = []
    if not bronze_root.exists():
        return pd.DataFrame()
    for source_dir in bronze_root.iterdir():
        if not source_dir.is_dir():
            continue
        for partition_dir in source_dir.iterdir():
            if not partition_dir.name.startswith("ingest_date="):
                continue
            part_date_str = partition_dir.name.split("=", 1)[1]
            try:
                part_date = date.fromisoformat(part_date_str)
            except ValueError:
                continue
            if not (start_date <= part_date <= end_date):
                continue
            for pq in partition_dir.glob("*.parquet"):
                frames.append(pd.read_parquet(pq))

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

@dataclass
class TextSilverResult:
    docs_input: int
    docs_output: int
    docs_deduped: int
    event_dates: List[str]
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None


def run_text_silver_build(
    start_date: date,
    end_date: date,
    cfg: Optional[TextPipelineConfig] = None,
) -> TextSilverResult:
    """Bronze → Silver 변환.

    Args:
        start_date: Bronze ingest_date 시작 (inclusive)
        end_date: Bronze ingest_date 종료 (inclusive)
        cfg: TextPipelineConfig

    Returns:
        TextSilverResult
    """
    if cfg is None:
        cfg = TextPipelineConfig.default()

    logger.info("Silver build: range=[%s, %s]", start_date, end_date)

    # 1. Bronze 로드
    bronze_df = _load_bronze(cfg.bronze_root, start_date, end_date)
    if bronze_df.empty:
        logger.warning("No Bronze data found in [%s, %s]", start_date, end_date)
        return TextSilverResult(
            docs_input=0, docs_output=0, docs_deduped=0, event_dates=[]
        )

    n_input = len(bronze_df)
    logger.info("Bronze loaded: %d docs", n_input)

    # 2. lang 필터 (영어만)
    df = bronze_df[bronze_df["lang"] == "en"].copy()

    # 3. published_at → event_date
    df["published_at"] = pd.to_datetime(df["published_at"], utc=True)
    df["event_date"] = df["published_at"].dt.date.astype(str)

    # 4. HTML → clean_text
    df["clean_text"] = df["body"].apply(_strip_html)

    # 5. quality_flags
    df["quality_flags"] = df.apply(
        lambda r: _compute_quality_flags(r["clean_text"], r["lang"], r["body"]),
        axis=1,
    )

    # 6. asset_scope
    df["asset_scope"] = df.apply(
        lambda r: _detect_asset_scope(r["source"], r["title"], r["clean_text"]),
        axis=1,
    )

    # 7. enricher_version
    df["enricher_version"] = _ENRICHER_VERSION

    # 8. 중복 제거 — doc_id 기준 (Bronze에서 이미 멱등키 보장)
    before_dedup = len(df)
    df = df.drop_duplicates(subset=["doc_id"], keep="first")
    n_deduped = before_dedup - len(df)
    if n_deduped:
        logger.info("Deduped %d cross-partition duplicate docs", n_deduped)

    # 9. event_date별 Silver 파티션 저장
    event_dates: List[str] = []
    for event_date_str, group in df.groupby("event_date"):
        out_df = group[_SILVER_COLUMNS].reset_index(drop=True)
        event_date = date.fromisoformat(str(event_date_str))
        _write_silver_partition(out_df, event_date, cfg.silver_root)
        event_dates.append(str(event_date_str))

    logger.info(
        "Silver build complete: input=%d, output=%d, deduped=%d, dates=%d",
        n_input, len(df), n_deduped, len(event_dates),
    )
    return TextSilverResult(
        docs_input=n_input,
        docs_output=len(df),
        docs_deduped=n_deduped,
        event_dates=sorted(event_dates),
    )


def _write_silver_partition(df: pd.DataFrame, event_date: date, silver_root: Path) -> Path:
    """Silver 파티션 기록 (tmp → atomic rename)."""
    partition_dir = silver_root / "text_enriched" / f"event_date={event_date.isoformat()}"
    partition_dir.mkdir(parents=True, exist_ok=True)
    filename = f"silver_{event_date.strftime('%Y%m%d')}.parquet"
    out_path = partition_dir / filename
    tmp_path = partition_dir / f".tmp_{uuid.uuid4().hex}_{filename}"

    df.to_parquet(tmp_path, index=False, compression="snappy")
    tmp_path.rename(out_path)
    logger.info("Silver written: %s (%d rows)", out_path, len(df))
    return out_path
