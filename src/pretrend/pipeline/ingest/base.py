from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd


@dataclass
class IngestContext:
    """
    개별 ingest job 실행 시 공통으로 사용하는 컨텍스트 정보.
    domain: macro / theme / stock
    dataset: econ_indicators / etf_master / ...
    """
    domain: str
    dataset: str
    run_id: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    output_root: Path = Path("data/bronze")
    meta_root: Path = Path("data/meta")


class BaseFetcher(ABC):
    """외부 API/파일 등에서 Raw 데이터를 수집하는 베이스 클래스."""

    @abstractmethod
    def fetch(self, context: IngestContext, **kwargs: Any) -> Dict[str, pd.DataFrame]:
        """
        Returns:
            dict[dataset_name, DataFrame]
        """
        raise NotImplementedError


class BaseNormalizer(ABC):
    """Raw DataFrame을 표준 스키마로 변환."""

    @abstractmethod
    def normalize(
        self,
        context: IngestContext,
        raw_data: Dict[str, pd.DataFrame],
    ) -> Dict[str, pd.DataFrame]:
        raise NotImplementedError


class BaseWriter(ABC):
    """정규화된 DataFrame을 Parquet로 저장 + 메타데이터 기록."""

    @abstractmethod
    def write(
        self,
        context: IngestContext,
        normalized_data: Dict[str, pd.DataFrame],
    ) -> None:
        raise NotImplementedError
