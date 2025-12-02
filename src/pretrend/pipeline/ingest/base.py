from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import uuid


@dataclass
class IngestContext:
    """
    개별 ingest job 실행 시 공통으로 사용하는 컨텍스트 정보.
    domain: macro / theme / stock
    dataset: econ_indicators / etf_master / ...
    """
    domain: str
    dataset: str
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    output_root: Path = Path("data/bronze")
    meta_root: Path = Path("data/meta")
    ingestion_ts: pd.Timestamp = field(default_factory=pd.Timestamp.utcnow)


class BaseFetcher(ABC):
    """외부 API/파일 등에서 Raw 데이터를 수집하는 베이스 클래스."""

    @abstractmethod
    def fetch(self, context: IngestContext, **kwargs: Any) -> pd.DataFrame:
        """
        Returns:
            Raw DataFrame (job 당 1개 dataset 기준)
        """
        raise NotImplementedError


class BaseNormalizer(ABC):
    """Raw DataFrame을 표준 스키마로 변환."""

    @abstractmethod
    def normalize(
        self,
        context: IngestContext,
        raw_df: pd.DataFrame,
    ) -> pd.DataFrame:
        raise NotImplementedError


class BaseWriter(ABC):
    """정규화된 DataFrame을 Parquet로 저장 + 메타데이터 기록."""

    @abstractmethod
    def write(
        self,
        context: IngestContext,
        normalized_df: pd.DataFrame,
    ) -> None:
        raise NotImplementedError
