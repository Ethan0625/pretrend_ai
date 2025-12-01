from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Optional

import pandas as pd

from .base import BaseFetcher, BaseNormalizer, BaseWriter, IngestContext


@dataclass
class MacroConfig:
    fred_api_key: str
    news_api_key: Optional[str] = None
    # TODO: base_url, timeout 등 필요시 확장


class MacroFetcher(BaseFetcher):
    def __init__(self, config: MacroConfig) -> None:
        self.config = config

    def fetch(self, context: IngestContext, **kwargs: Any) -> Dict[str, pd.DataFrame]:
        """
        econ_indicators, news_headlines 두 데이터셋을 반환하는 형태로 설계.
        MVP 초기에는 로컬 CSV/dummy 데이터로 먼저 구조 검증 후,
        실제 FRED/News API 연동을 추가하는 순서로 가는 것을 권장.
        """
        # TODO: 실제 구현
        econ_df = pd.DataFrame()   # FRED API 결과를 담을 예정
        news_df = pd.DataFrame()   # News API / RSS 결과를 담을 예정

        return {
            "econ_indicators": econ_df,
            "news_headlines": news_df,
        }


class MacroNormalizer(BaseNormalizer):
    def normalize(
        self,
        context: IngestContext,
        raw_data: Dict[str, pd.DataFrame],
    ) -> Dict[str, pd.DataFrame]:
        econ_df = raw_data["econ_indicators"].copy()
        news_df = raw_data["news_headlines"].copy()

        ingestion_ts = pd.Timestamp.utcnow()

        # TODO: indicator_id 매핑, 타입 캐스팅, 결측치 처리 등 구현
        # 예시:
        # econ_df["indicator_id"] = econ_df["indicator_name"].map(...)
        econ_df["run_id"] = context.run_id
        econ_df["ingestion_ts"] = ingestion_ts

        news_df["run_id"] = context.run_id
        news_df["ingestion_ts"] = ingestion_ts

        return {
            "econ_indicators": econ_df,
            "news_headlines": news_df,
        }


class MacroWriter(BaseWriter):
    def write(
        self,
        context: IngestContext,
        normalized_data: Dict[str, pd.DataFrame],
    ) -> None:
        """
        - /tmp/pretrend/.../{run_id} 아래에 우선 저장
        - 대상 파티션(year/month or date)을 기준으로 기존 데이터 삭제 후 atomic move
        - ingest_log.parquet 업데이트

        실제 구현은 I/O 유틸을 utils 모듈로 분리해도 됨.
        """
        # TODO:
        # 1. 파티션 경로 계산
        # 2. tmp 디렉토리 쓰기
        # 3. 기존 파티션 삭제 + rename
        # 4. ingest_log 업데이트
        pass


def run_macro_ingest(
    config: MacroConfig,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> None:
    context = IngestContext(
        domain="macro",
        dataset="econ_indicators",  # 대표 dataset 명 (실제론 여러 dataset 처리)
        run_id=_generate_run_id("macro"),
        start_date=start_date,
        end_date=end_date,
    )
    fetcher = MacroFetcher(config=config)
    normalizer = MacroNormalizer()
    writer = MacroWriter()

    raw_data = fetcher.fetch(context)
    normalized = normalizer.normalize(context, raw_data)
    writer.write(context, normalized)


def _generate_run_id(domain: str) -> str:
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}_{domain}"
