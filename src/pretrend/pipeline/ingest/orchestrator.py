from __future__ import annotations

import argparse
from datetime import date
from typing import Optional

from .macro import MacroConfig, run_macro_ingest
from .theme import ThemeConfig, run_theme_ingest
from .stock import StockConfig, run_stock_ingest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Step 0 Data Source Ingest")
    parser.add_argument("--job", choices=["macro", "theme", "stock"], required=True)
    parser.add_argument("--start", type=str, help="YYYY-MM-DD")
    parser.add_argument("--end", type=str, help="YYYY-MM-DD")
    # 필요 시 --universe, --config-path 등 추가
    return parser.parse_args()


def _parse_date(value: Optional[str]) -> Optional[date]:
    if value is None:
        return None
    return date.fromisoformat(value)


def main() -> None:
    args = parse_args()
    start_date = _parse_date(args.start)
    end_date = _parse_date(args.end)

    if args.job == "macro":
        config = MacroConfig(fred_api_key="DEMO_KEY")
        run_macro_ingest(config=config, start_date=start_date, end_date=end_date)
    elif args.job == "theme":
        config = ThemeConfig(provider="yahoo")
        run_theme_ingest(config=config)
    elif args.job == "stock":
        config = StockConfig(provider="fmp")
        run_stock_ingest(config=config, start_date=start_date, end_date=end_date)


if __name__ == "__main__":
    main()
