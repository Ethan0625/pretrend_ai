"""Gold LLM backfill CLI."""
from __future__ import annotations

import argparse
import logging
import time
from datetime import date

from pretrend.pipeline.text.gold_llm_build import run_text_gold_llm_build

logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gold LLM backfill runner")
    parser.add_argument(
        "--source",
        default="all",
        choices=["fed_fomc", "sec_edgar", "all"],
        help="Filter Silver docs by source",
    )
    parser.add_argument("--start", required=True, type=date.fromisoformat)
    parser.add_argument("--end", required=True, type=date.fromisoformat)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--chunk-years", type=int, default=1)
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = _parse_args()
    source_filter = None if args.source == "all" else args.source

    total_input = 0
    total_processed = 0
    total_skipped = 0
    total_rows = 0
    started = time.time()

    for year in range(args.start.year, args.end.year + 1, args.chunk_years):
        chunk_start = max(date(year, 1, 1), args.start)
        chunk_end = min(date(year + args.chunk_years - 1, 12, 31), args.end)
        t0 = time.time()
        result = run_text_gold_llm_build(
            start_date=chunk_start,
            end_date=chunk_end,
            source_filter=source_filter,
            max_workers=args.max_workers,
        )
        elapsed = time.time() - t0
        total_input += result.docs_input
        total_processed += result.docs_processed
        total_skipped += result.docs_skipped
        total_rows += result.feature_rows
        print(
            f"[{chunk_start}~{chunk_end}] input={result.docs_input} "
            f"processed={result.docs_processed} skipped={result.docs_skipped} "
            f"rows={result.feature_rows} coverage={result.coverage_ratio:.2f} "
            f"elapsed={elapsed:.1f}s success={result.success} error={result.error}",
            flush=True,
        )

    total_elapsed = time.time() - started
    overall_coverage = (total_processed / total_input) if total_input else 0.0
    print(
        f"SUMMARY input={total_input} processed={total_processed} skipped={total_skipped} "
        f"rows={total_rows} coverage={overall_coverage:.2f} elapsed={total_elapsed:.1f}s",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
