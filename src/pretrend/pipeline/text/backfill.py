"""Text 백필 러너.

사용 예:
    python -m pretrend.pipeline.text.backfill \
        --source sec_index,fomc_archive \
        --start 2006-01-01 --end 2024-06-03 \
        --chunk-years 1
"""
from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta
from typing import Iterable, List

from pretrend.pipeline.text.bronze_ingest import run_text_bronze_ingest
from pretrend.pipeline.text.config import TextPipelineConfig
from pretrend.pipeline.text.gold_build import run_text_gold_build
from pretrend.pipeline.text.silver_build import run_text_silver_build

logger = logging.getLogger(__name__)


def _parse_date(text: str) -> date:
    return date.fromisoformat(text)


def _iter_year_chunks(start_dt: date, end_dt: date, chunk_years: int) -> Iterable[tuple[date, date]]:
    current = start_dt
    while current <= end_dt:
        chunk_end_year = min(current.year + chunk_years - 1, end_dt.year)
        chunk_end = date(chunk_end_year, 12, 31)
        if chunk_end > end_dt:
            chunk_end = end_dt
        yield current, chunk_end
        current = chunk_end + timedelta(days=1)


def _chunk_partition_exists(cfg: TextPipelineConfig, source: str, ingest_date: date) -> bool:
    partition_dir = cfg.bronze_root / source / f"ingest_date={ingest_date.isoformat()}"
    return any(partition_dir.glob("*.parquet"))


def run_text_backfill(
    sources: List[str],
    start_dt: date,
    end_dt: date,
    chunk_years: int,
    cfg: TextPipelineConfig | None = None,
) -> None:
    if cfg is None:
        cfg = TextPipelineConfig.default()

    for source in sources:
        for chunk_start, chunk_end in _iter_year_chunks(start_dt, end_dt, chunk_years):
            if _chunk_partition_exists(cfg, source, chunk_end):
                logger.info(
                    "Backfill skip: source=%s chunk=[%s,%s] ingest_date=%s",
                    source,
                    chunk_start,
                    chunk_end,
                    chunk_end,
                )
                continue
            logger.info(
                "Backfill bronze: source=%s chunk=[%s,%s] ingest_date=%s",
                source,
                chunk_start,
                chunk_end,
                chunk_end,
            )
            run_text_bronze_ingest(
                sources=[source],
                start_date=chunk_start,
                end_date=chunk_end,
                cfg=cfg,
                ingest_date=chunk_end,
                max_workers=1,
            )

    logger.info("Backfill silver: [%s, %s]", start_dt, end_dt)
    run_text_silver_build(start_date=start_dt, end_date=end_dt, cfg=cfg)

    logger.info("Backfill gold: [%s, %s]", start_dt, end_dt)
    run_text_gold_build(start_date=start_dt, end_date=end_dt, cfg=cfg)


def main() -> None:
    parser = argparse.ArgumentParser(description="Text backfill runner")
    parser.add_argument("--source", required=True, help="sec_index,fomc_archive")
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    parser.add_argument("--chunk-years", type=int, default=1, help="Chunk size in years")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    run_text_backfill(
        sources=[s.strip() for s in args.source.split(",") if s.strip()],
        start_dt=_parse_date(args.start),
        end_dt=_parse_date(args.end),
        chunk_years=args.chunk_years,
        cfg=TextPipelineConfig.default(),
    )


if __name__ == "__main__":
    main()
