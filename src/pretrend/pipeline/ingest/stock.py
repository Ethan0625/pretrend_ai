from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, Optional

import pandas as pd

from .base import BaseFetcher, BaseNormalizer, BaseWriter, IngestContext


@dataclass
class StockConfig:
    provider: str = "fmp"
    api_key: str | None = None
    universe_seed_path: str | None = None  # 초기엔 전체, 이후엔 Universe 기반 서브셋


class StockFetcher(BaseFetcher):
    def __init__(self, config: StockConfig) -> None:
        self.config = config

    def fetch(self, context: IngestContext, **kwargs) -> Dict[str, pd.DataFrame]:
        """
        stock_master, fundamentals 두 데이터셋을 반환.
        """
        # TODO: FMP/Finnhub 등 실제 연동 or CSV 기반
        stock_master = pd.DataFrame()
        fundamentals = pd.DataFrame()

        return {
            "stock_master": stock_master,
            "fundamentals": fundamentals,
        }


class StockNormalizer(BaseNormalizer):
    def normalize(
        self,
        context: IngestContext,
        raw_data: Dict[str, pd.DataFrame],
    ) -> Dict[str, pd.DataFrame]:
        stock_master = raw_data["stock_master"].copy()
        fundamentals = raw_data["fundamentals"].copy()

        # TODO: 통화/단위 변환, 결측치 처리, run_id/ingestion_ts 추가 등
        return {
            "stock_master": stock_master,
            "fundamentals": fundamentals,
        }


class StockWriter(BaseWriter):
    def write(
        self,
        context: IngestContext,
        normalized_data: Dict[str, pd.DataFrame],
    ) -> None:
        """
        stock/stock_master, stock/fundamentals에 파티션 단위 저장.
        """
        # TODO: macro/theme와 동일 패턴 적용
        pass


def run_stock_ingest(
    config: StockConfig,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> None:
    context = IngestContext(
        domain="stock",
        dataset="stock_master",
        run_id=_generate_run_id("stock"),
        start_date=start_date,
        end_date=end_date,
    )
    fetcher = StockFetcher(config=config)
    normalizer = StockNormalizer()
    writer = StockWriter()

    raw = fetcher.fetch(context)
    normalized = normalizer.normalize(context, raw)
    writer.write(context, normalized)


def _generate_run_id(domain: str) -> str:
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}_{domain}"
