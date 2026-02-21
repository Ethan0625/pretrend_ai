"""Text Pipeline E2E CLI.

Usage:
    # 단계별 실행
    python -m pretrend.pipeline.text.text_job --stage bronze --source sec --date 2026-02-20
    python -m pretrend.pipeline.text.text_job --stage bronze --source fed --date 2026-02-20
    python -m pretrend.pipeline.text.text_job --stage silver --date 2026-02-20
    python -m pretrend.pipeline.text.text_job --stage gold --date 2026-02-20

    # E2E
    python -m pretrend.pipeline.text.text_job --stage all --start 2026-02-01 --end 2026-02-20

    # 날짜 범위 지정
    python -m pretrend.pipeline.text.text_job --stage bronze --source sec,fed \\
        --start 2026-01-01 --end 2026-02-20
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta

from pretrend.pipeline.text.bronze_ingest import run_text_bronze_ingest
from pretrend.pipeline.text.config import TextPipelineConfig
from pretrend.pipeline.text.gold_build import run_text_gold_build
from pretrend.pipeline.text.silver_build import run_text_silver_build

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

_DEFAULT_SOURCES = ["sec", "fed"]


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _resolve_date_range(args: argparse.Namespace) -> tuple[date, date]:
    """--date / --start / --end 조합으로 (start_date, end_date) 반환."""
    if args.date:
        d = _parse_date(args.date)
        return d, d
    if args.start and args.end:
        return _parse_date(args.start), _parse_date(args.end)
    if args.start:
        return _parse_date(args.start), date.today()
    # fallback: 어제
    yesterday = date.today() - timedelta(days=1)
    return yesterday, yesterday


def _run_bronze(args: argparse.Namespace, cfg: TextPipelineConfig) -> None:
    start_date, end_date = _resolve_date_range(args)
    sources = [s.strip() for s in (args.source or "sec,fed").split(",") if s.strip()]
    logger.info("=== Bronze Ingest: sources=%s [%s, %s] ===", sources, start_date, end_date)
    results = run_text_bronze_ingest(sources=sources, start_date=start_date, end_date=end_date, cfg=cfg)
    for r in results:
        status = "OK" if r.success else f"ERROR: {r.error}"
        logger.info("  [%s] fetched=%d written=%d skipped=%d → %s",
                    r.source, r.docs_fetched, r.docs_written, r.docs_skipped_duplicate, status)
    if any(not r.success for r in results):
        sys.exit(1)


def _run_silver(args: argparse.Namespace, cfg: TextPipelineConfig) -> None:
    start_date, end_date = _resolve_date_range(args)
    logger.info("=== Silver Build [%s, %s] ===", start_date, end_date)
    result = run_text_silver_build(start_date=start_date, end_date=end_date, cfg=cfg)
    logger.info("  input=%d output=%d deduped=%d dates=%d → %s",
                result.docs_input, result.docs_output, result.docs_deduped,
                len(result.event_dates), "OK" if result.success else f"ERROR: {result.error}")
    if not result.success:
        sys.exit(1)


def _run_gold(args: argparse.Namespace, cfg: TextPipelineConfig) -> None:
    start_date, end_date = _resolve_date_range(args)
    logger.info("=== Gold Build [%s, %s] ===", start_date, end_date)
    result = run_text_gold_build(start_date=start_date, end_date=end_date, cfg=cfg)
    logger.info("  feature_rows=%d dates=%d → %s",
                result.feature_rows, len(result.trade_dates),
                "OK" if result.success else f"ERROR: {result.error}")
    if not result.success:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Text Pipeline CLI")
    parser.add_argument(
        "--stage",
        choices=["bronze", "silver", "gold", "all"],
        required=True,
        help="실행 단계",
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Bronze 소스 (쉼표 구분, 예: sec,fed). bronze 단계에서만 사용.",
    )
    parser.add_argument("--date", default=None, help="단일 날짜 (YYYY-MM-DD)")
    parser.add_argument("--start", default=None, help="시작 날짜 (YYYY-MM-DD)")
    parser.add_argument("--end", default=None, help="종료 날짜 (YYYY-MM-DD)")

    args = parser.parse_args()
    cfg = TextPipelineConfig.default()

    if args.stage == "bronze":
        _run_bronze(args, cfg)
    elif args.stage == "silver":
        _run_silver(args, cfg)
    elif args.stage == "gold":
        _run_gold(args, cfg)
    elif args.stage == "all":
        _run_bronze(args, cfg)
        _run_silver(args, cfg)
        _run_gold(args, cfg)


if __name__ == "__main__":
    main()
