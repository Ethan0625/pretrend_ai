"""Text Bronze Ingest — 원문 수집 및 저장.

저장 경로: data/bronze/text/{source}/ingest_date=YYYY-MM-DD/bronze_{source}_{YYYYMMDD}.parquet
멱등키: (source, source_doc_id) → doc_id (SHA-256)
병렬 수집: 소스별 ThreadPoolExecutor
"""
from __future__ import annotations

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pandas as pd

from pretrend.pipeline.text.adapters.base import RawDoc, TextSourceAdapter, make_doc_id
from pretrend.pipeline.text.adapters.fed_fomc import FedFomcAdapter
from pretrend.pipeline.text.adapters.fed_fomc_archive import FedFomcArchiveAdapter
from pretrend.pipeline.text.adapters.sec_edgar import SECEdgarAdapter
from pretrend.pipeline.text.adapters.sec_edgar_index import SECEdgarIndexAdapter
from pretrend.pipeline.text.config import TextPipelineConfig

logger = logging.getLogger(__name__)

# Bronze 스키마 컬럼 순서
_BRONZE_COLUMNS = [
    "doc_id",
    "source",
    "source_doc_id",
    "canonical_url",
    "published_at",
    "ingested_at",
    "title",
    "body",
    "lang",
    "raw_payload_hash",
]


@dataclass
class TextIngestResult:
    source: str
    docs_fetched: int
    docs_written: int
    docs_skipped_duplicate: int
    output_path: Optional[Path] = None
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None


def _build_adapter(source: str, cfg: TextPipelineConfig) -> TextSourceAdapter:
    """소스 이름으로 어댑터 인스턴스 생성."""
    if source == "sec":
        return SECEdgarAdapter(
            seed_tickers=cfg.sec_seed_tickers,
            user_agent=cfg.sec_user_agent,
            cik_cache_path=cfg.cik_cache_path,
            request_delay_sec=cfg.sec_request_delay_sec,
        )
    if source == "fed":
        return FedFomcAdapter(
            rss_url=cfg.fed_rss_url,
            request_delay_sec=cfg.fed_request_delay_sec,
        )
    if source == "sec_index":
        return SECEdgarIndexAdapter(
            user_agent=cfg.sec_user_agent,
            request_delay_sec=cfg.sec_request_delay_sec,
        )
    if source == "fomc_archive":
        return FedFomcArchiveAdapter(
            request_delay_sec=cfg.fed_request_delay_sec,
            user_agent=cfg.sec_user_agent,
        )
    raise ValueError(f"Unknown source: {source!r}. Available: sec, fed, sec_index, fomc_archive")


def _docs_to_df(docs: List[RawDoc]) -> pd.DataFrame:
    """RawDoc 리스트 → DataFrame (doc_id 컬럼 추가, 중복 제거)."""
    if not docs:
        return pd.DataFrame(columns=_BRONZE_COLUMNS)

    records = []
    for doc in docs:
        record = dict(doc)
        record["doc_id"] = make_doc_id(doc["source"], doc["source_doc_id"])
        records.append(record)

    df = pd.DataFrame(records)[_BRONZE_COLUMNS]
    # 동일 doc_id 중복 제거 (같은 run 내 재등장)
    before = len(df)
    df = df.drop_duplicates(subset=["doc_id"], keep="first")
    dupes = before - len(df)
    if dupes:
        logger.debug("Dropped %d intra-run duplicate docs", dupes)
    return df


def _write_partition(
    df: pd.DataFrame,
    source: str,
    ingest_date: date,
    bronze_root: Path,
) -> Path:
    """tmp → atomic rename으로 parquet 파티션 기록."""
    partition_dir = bronze_root / source / f"ingest_date={ingest_date.isoformat()}"
    partition_dir.mkdir(parents=True, exist_ok=True)
    filename = f"bronze_{source}_{ingest_date.strftime('%Y%m%d')}.parquet"
    out_path = partition_dir / filename
    tmp_path = partition_dir / f".tmp_{uuid.uuid4().hex}_{filename}"

    df.to_parquet(tmp_path, index=False, compression="snappy")
    tmp_path.rename(out_path)
    logger.info("Bronze written: %s (%d rows)", out_path, len(df))
    return out_path


def _ingest_one_source(
    source: str,
    start_date: date,
    end_date: date,
    cfg: TextPipelineConfig,
    ingest_date: date,
) -> TextIngestResult:
    """단일 소스에 대한 Bronze 수집 + 저장."""
    try:
        adapter = _build_adapter(source, cfg)
    except ValueError as exc:
        return TextIngestResult(source=source, docs_fetched=0, docs_written=0,
                                docs_skipped_duplicate=0, error=str(exc))

    docs: List[RawDoc] = []
    try:
        for doc in adapter.fetch(start_date, end_date):
            docs.append(doc)
    except Exception as exc:
        logger.error("Source %s fetch failed: %s", source, exc)
        return TextIngestResult(source=source, docs_fetched=len(docs), docs_written=0,
                                docs_skipped_duplicate=0, error=str(exc))

    df = _docs_to_df(docs)
    n_fetched = len(docs)
    n_deduped = len(df)
    n_skipped = n_fetched - n_deduped

    if df.empty:
        logger.info("Source %s: 0 docs in [%s, %s] — nothing to write", source, start_date, end_date)
        return TextIngestResult(source=source, docs_fetched=0, docs_written=0,
                                docs_skipped_duplicate=0)

    try:
        out_path = _write_partition(df, source, ingest_date, cfg.bronze_root)
    except Exception as exc:
        logger.error("Bronze write failed for %s: %s", source, exc)
        return TextIngestResult(source=source, docs_fetched=n_fetched, docs_written=0,
                                docs_skipped_duplicate=n_skipped, error=str(exc))

    return TextIngestResult(
        source=source,
        docs_fetched=n_fetched,
        docs_written=n_deduped,
        docs_skipped_duplicate=n_skipped,
        output_path=out_path,
    )


def run_text_bronze_ingest(
    sources: List[str],
    start_date: date,
    end_date: date,
    cfg: Optional[TextPipelineConfig] = None,
    ingest_date: Optional[date] = None,
    max_workers: int = 4,
) -> List[TextIngestResult]:
    """여러 소스를 병렬로 수집하여 Bronze 파티션에 저장.

    Args:
        sources: 수집할 소스 목록 (["sec", "fed"])
        start_date: 수집 시작일 (inclusive)
        end_date: 수집 종료일 (inclusive)
        cfg: TextPipelineConfig (None이면 default 사용)
        ingest_date: 파티션 날짜 (None이면 today)
        max_workers: 병렬 스레드 수

    Returns:
        소스별 TextIngestResult 리스트
    """
    if cfg is None:
        cfg = TextPipelineConfig.default()
    if ingest_date is None:
        ingest_date = datetime.now(timezone.utc).date()

    logger.info(
        "Bronze ingest: sources=%s, range=[%s, %s], ingest_date=%s",
        sources, start_date, end_date, ingest_date,
    )

    results: List[TextIngestResult] = []

    with ThreadPoolExecutor(max_workers=min(max_workers, len(sources))) as pool:
        futures = {
            pool.submit(
                _ingest_one_source, src, start_date, end_date, cfg, ingest_date
            ): src
            for src in sources
        }
        for future in as_completed(futures):
            src = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                logger.error("Unexpected error for source %s: %s", src, exc)
                result = TextIngestResult(source=src, docs_fetched=0, docs_written=0,
                                         docs_skipped_duplicate=0, error=str(exc))
            results.append(result)
            logger.info(
                "  [%s] fetched=%d, written=%d, skipped=%d%s",
                result.source, result.docs_fetched, result.docs_written,
                result.docs_skipped_duplicate,
                f", ERROR={result.error}" if result.error else "",
            )

    return results
