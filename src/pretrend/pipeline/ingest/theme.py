from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict

import pandas as pd

from .base import BaseFetcher, BaseNormalizer, BaseWriter, IngestContext


@dataclass
class ThemeConfig:
    provider: str = "yahoo"   # 예: yahoo, fmp 등
    api_key: str | None = None


class ThemeFetcher(BaseFetcher):
    def __init__(self, config: ThemeConfig) -> None:
        self.config = config

    def fetch(self, context: IngestContext, **kwargs) -> Dict[str, pd.DataFrame]:
        """
        etf_master, etf_holdings, etf_performance 세 가지 데이터셋을 반환하는 형태.
        """
        # TODO: 실제 API 연동 or 초기에는 로컬 CSV 기반
        etf_master = pd.DataFrame()
        etf_holdings = pd.DataFrame()
        etf_perf = pd.DataFrame()

        return {
            "etf_master": etf_master,
            "etf_holdings": etf_holdings,
            "etf_performance": etf_perf,
        }


class ThemeNormalizer(BaseNormalizer):
    def normalize(
        self,
        context: IngestContext,
        raw_data: Dict[str, pd.DataFrame],
    ) -> Dict[str, pd.DataFrame]:
        etf_master = raw_data["etf_master"].copy()
        etf_holdings = raw_data["etf_holdings"].copy()
        etf_perf = raw_data["etf_performance"].copy()

        # TODO: ticker 포맷 정규화, 통화/단위 통일, run_id/ingestion_ts 추가 등
        # for df in (etf_master, etf_holdings, etf_perf):
        #     df["run_id"] = context.run_id
        #     df["ingestion_ts"] = pd.Timestamp.utcnow()

        return {
            "etf_master": etf_master,
            "etf_holdings": etf_holdings,
            "etf_performance": etf_perf,
        }


class ThemeWriter(BaseWriter):
    def write(
        self,
        context: IngestContext,
        normalized_data: Dict[str, pd.DataFrame],
    ) -> None:
        """
        theme/etf_master, etf_holdings, etf_performance 각각에 대해
        파티션 단위 overwrite + ingest_log 기록.
        """
        # TODO: macro와 동일한 패턴으로 구현
        pass


def run_theme_ingest(config: ThemeConfig) -> None:
    context = IngestContext(
        domain="theme",
        dataset="etf_master",
        run_id=_generate_run_id("theme"),
    )
    fetcher = ThemeFetcher(config=config)
    normalizer = ThemeNormalizer()
    writer = ThemeWriter()

    raw = fetcher.fetch(context)
    normalized = normalizer.normalize(context, raw)
    writer.write(context, normalized)


def _generate_run_id(domain: str) -> str:
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}_{domain}"
