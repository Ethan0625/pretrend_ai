from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, List, Optional

import pandas as pd
import requests

from .base import IngestContext, BaseFetcher, BaseNormalizer, BaseWriter


@dataclass
class FredSeriesSpec:
    """
    FRED 개별 시리즈 정의.
    - series_id: FRED 시리즈 ID (예: CPIAUCSL, UNRATE, FEDFUNDS ...)
    - indicator_id: 내부에서 사용할 지표 식별자
    - unit: 값의 단위 설명
    - source: 데이터 출처
    """
    series_id: str
    indicator_id: str
    unit: str
    source: str = "FRED"


@dataclass
class FredMacroConfig:
    api_key: str
    base_url: str = "https://api.stlouisfed.org/fred/series/observations"
    series_list: List[FredSeriesSpec] = None

    @classmethod
    def from_env_cpi_only(cls) -> "FredMacroConfig":
        """
        Step 1: CPI만 수집하는 구성.
        """
        api_key = os.getenv("FRED_API_KEY")
        if not api_key:
            raise RuntimeError("환경변수 FRED_API_KEY가 설정되지 않았습니다.")

        series_list = [
            FredSeriesSpec(
                series_id="CPIAUCSL",              # 미국 CPI (도시 소비자, SA)
                indicator_id="CPI_US_ALL_ITEMS_SA",
                unit="Index 1982-84=100",
            )
        ]
        return cls(api_key=api_key, series_list=series_list)

    @classmethod
    def from_env_with_defaults(cls) -> "FredMacroConfig":
        """
        Step 2: CPI + Core CPI + 실업률 + 기준금리 + 10Y 국채수익률 등
        (CPI 검증 후 이 옵션으로 확장)
        """
        api_key = os.getenv("FRED_API_KEY")
        if not api_key:
            raise RuntimeError("환경변수 FRED_API_KEY가 설정되지 않았습니다.")

        series_list = [
            FredSeriesSpec(
                series_id="CPIAUCSL",
                indicator_id="CPI_US_ALL_ITEMS_SA",
                unit="Index 1982-84=100",
            ),
            FredSeriesSpec(
                series_id="CPILFESL",
                indicator_id="CPI_US_CORE_SA",
                unit="Index 1982-84=100",
            ),
            FredSeriesSpec(
                series_id="UNRATE",
                indicator_id="US_UNEMPLOYMENT_RATE",
                unit="Percent",
            ),
            FredSeriesSpec(
                series_id="FEDFUNDS",
                indicator_id="US_FED_FUNDS_RATE",
                unit="Percent",
            ),
            FredSeriesSpec(
                series_id="DGS10",
                indicator_id="US_TREASURY_10Y_YIELD",
                unit="Percent",
            ),
        ]
        return cls(api_key=api_key, series_list=series_list)


class MacroFetcher(BaseFetcher):
    """
    FRED Macro Fetcher (초기엔 CPI만, 이후 여러 지표 확장)
    fetch() → DataFrame
    columns:
        date, value, indicator_id, unit, source, series_id
    """

    def __init__(self, config: Optional[FredMacroConfig] = None):
        # Step1: CPI만 수집
        self.config = config or FredMacroConfig.from_env_with_defaults()
        # CPI 검증 완료. 251202 -> 추가지표수집

    def _fetch_single_series(
        self,
        context: IngestContext,
        spec: FredSeriesSpec,
    ) -> pd.DataFrame:
        params: dict[str, Any] = {
            "series_id": spec.series_id,
            "api_key": self.config.api_key,
            "file_type": "json",
        }

        if context.start_date:
            params["observation_start"] = context.start_date.strftime("%Y-%m-%d")
        if context.end_date:
            params["observation_end"] = context.end_date.strftime("%Y-%m-%d")

        resp = requests.get(self.config.base_url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        observations = data.get("observations", [])

        rows: list[dict[str, Any]] = []
        for obs in observations:
            value_str = obs.get("value")
            if value_str is None or value_str == ".":
                continue
            rows.append(
                {
                    "date": obs.get("date"),          # string
                    "value": value_str,               # string
                    "indicator_id": spec.indicator_id,
                    "unit": spec.unit,
                    "source": spec.source,
                    "series_id": spec.series_id,
                }
            )

        if not rows:
            return pd.DataFrame(
                columns=[
                    "date",
                    "value",
                    "indicator_id",
                    "unit",
                    "source",
                    "series_id",
                ]
            )

        return pd.DataFrame(rows)
    
    def fetch(self, context: IngestContext, **kwargs: Any) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []

        for spec in self.config.series_list:
            df_spec = self._fetch_single_series(context, spec)
            if not df_spec.empty:
                frames.append(df_spec)

        if not frames:
            print("[MacroFetcher] No data fetched")
            return pd.DataFrame(
                columns=[
                    "date",
                    "value",
                    "indicator_id",
                    "unit",
                    "source",
                    "series_id",
                ]
            )

        merged = pd.concat(frames, ignore_index=True)
        return merged


class MacroNormalizer(BaseNormalizer):
    """
    Raw macro DataFrame을 표준 스키마로 정규화.

    입력(raw_df):
        date(str), value(str), indicator_id, unit, source, series_id
    출력(normalized_df):
        indicator_id, date, value, unit, source, run_id, ingestion_ts
    """

    def normalize(
        self,
        context: IngestContext,
        raw_df: pd.DataFrame,
    ) -> pd.DataFrame:
        if raw_df is None or raw_df.empty:
            print("[MacroNormalizer] empty input, skip")
            return pd.DataFrame(
                columns=[
                    "indicator_id",
                    "date",
                    "value",
                    "unit",
                    "source",
                    "run_id",
                    "ingestion_ts",
                ]
            )

        df = raw_df.copy()

        # 타입 정리
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df["value"] = pd.to_numeric(df["value"], errors="coerce")

        # 공통 메타 정보
        df["run_id"] = context.run_id
        df["ingestion_ts"] = context.ingestion_ts

        # 최종 스키마 순서 정리
        df = df[
            [
                "indicator_id",
                "date",
                "value",
                "unit",
                "source",
                "run_id",
                "ingestion_ts",
            ]
        ]

        return df


class MacroWriter(BaseWriter):
    """
    정규화된 매크로 지표를 parquet로 저장.

    저장 경로:
        {output_root}/{domain}/{dataset}/year=YYYY/month=MM/{indicator_id}_YYYYMM.parquet

    예:
        data/bronze/macro/econ_indicators/year=2015/month=01/CPI_US_ALL_ITEMS_SA_201501.parquet
    """

    def write(
        self,
        context: IngestContext,
        normalized_df: pd.DataFrame,
    ) -> None:
        if normalized_df is None or normalized_df.empty:
            print("[MacroWriter] empty input, skip")
            return

        df = normalized_df.copy()
        df["year"] = df["date"].apply(lambda d: d.year)
        df["month"] = df["date"].apply(lambda d: d.month)

        base_path = context.output_root / context.domain / context.dataset

        for (year, month), part in df.groupby(["year", "month"]):
            out_dir = base_path / f"year={year}" / f"month={month:02d}"
            out_dir.mkdir(parents=True, exist_ok=True)

            for indicator_id, part_ind in part.groupby("indicator_id"):
                file_name = f"{indicator_id}_{year}{month:02d}.parquet"
                out_path = out_dir / file_name

                part_ind.drop(columns=["year", "month"]).to_parquet(
                    out_path,
                    index=False,
                )

                print(f"[MacroWriter] Saved: {out_path}")


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
