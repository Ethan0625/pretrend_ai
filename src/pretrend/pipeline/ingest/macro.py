from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, List, Optional

import pandas as pd
import requests

from pretrend.pipeline.ingest.base import IngestContext, BaseFetcher, BaseNormalizer, BaseWriter


class _FredVintageSeriesUnavailable(RuntimeError):
    """Raised when a FRED series exists but has no ALFRED vintage history."""


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


    # --------------------------------------------------
    # Vintage fetching (Bronze Calendar fred_vintages)
    # --------------------------------------------------

    _VINTAGE_DELAY: float = 0.5       # 요청 간 대기(초)
    _VINTAGE_MAX_RETRIES: int = 3      # 429 시 최대 재시도 횟수
    _VINTAGE_BACKOFF_BASE: float = 2.0 # 지수 백오프 기본 대기(초)

    _VINTAGE_COLUMNS: tuple[str, ...] = (
        "series_id",
        "observation_date",
        "vintage_date",
        "value",
        "source",
    )

    @classmethod
    def _empty_vintage_frame(cls) -> pd.DataFrame:
        return pd.DataFrame(columns=list(cls._VINTAGE_COLUMNS))

    def _fetch_vintage_chunk(
        self,
        spec: FredSeriesSpec,
        obs_start: str,
        obs_end: str,
        rt_start: str,
        rt_end: str,
    ) -> pd.DataFrame:
        """단일 청크에 대한 FRED vintage API 호출 (rate limit + retry)."""
        params: dict[str, Any] = {
            "series_id": spec.series_id,
            "api_key": self.config.api_key,
            "file_type": "json",
            "observation_start": obs_start,
            "observation_end": obs_end,
            "realtime_start": rt_start,
            "realtime_end": rt_end,
        }

        time.sleep(self._VINTAGE_DELAY)

        for attempt in range(self._VINTAGE_MAX_RETRIES + 1):
            resp = requests.get(self.config.base_url, params=params, timeout=60)
            if resp.status_code == 429 or 500 <= resp.status_code < 600:
                if attempt < self._VINTAGE_MAX_RETRIES:
                    wait = self._VINTAGE_BACKOFF_BASE * (2 ** attempt)
                    print(
                        f"[MacroFetcher] FRED vintage retryable error "
                        f"status={resp.status_code} ({spec.series_id}), "
                        f"retry {attempt + 1}/{self._VINTAGE_MAX_RETRIES} "
                        f"after {wait:.0f}s"
                    )
                    time.sleep(wait)
                    continue
                message = getattr(resp, "text", "")
                print(
                    "[MacroFetcher] Vintage chunk skipped after retryable "
                    "FRED error: "
                    f"status={resp.status_code}, series_id={spec.series_id}, "
                    f"observation_start={obs_start}, observation_end={obs_end}, "
                    f"realtime_start={rt_start}, realtime_end={rt_end}, "
                    f"message={message[:300]!r}"
                )
                return self._empty_vintage_frame()
            if resp.status_code == 400:
                message = getattr(resp, "text", "")
                if "does not exist in ALFRED" in message:
                    print(
                        "[MacroFetcher] Vintage series skipped because ALFRED "
                        "history is unavailable: "
                        f"series_id={spec.series_id}, message={message[:300]!r}"
                    )
                    raise _FredVintageSeriesUnavailable(spec.series_id)
                print(
                    "[MacroFetcher] Vintage chunk skipped after FRED 400: "
                    f"series_id={spec.series_id}, "
                    f"observation_start={obs_start}, observation_end={obs_end}, "
                    f"realtime_start={rt_start}, realtime_end={rt_end}, "
                    f"message={message[:300]!r}"
                )
                return self._empty_vintage_frame()
            resp.raise_for_status()
            break

        data = resp.json()

        observations = data.get("observations", [])

        rows: list[dict[str, Any]] = []
        for obs in observations:
            value_str = obs.get("value")
            if value_str is None or value_str == ".":
                continue
            rows.append(
                {
                    "series_id": spec.series_id,
                    "observation_date": obs.get("date"),
                    "vintage_date": obs.get("realtime_start"),
                    "value": value_str,
                    "source": "fred_api",
                }
            )

        if not rows:
            return self._empty_vintage_frame()
        return pd.DataFrame(rows)

    @staticmethod
    def _fred_safe_max_date():
        """
        FRED API의 realtime_end 상한을 반환한다.
        FRED는 UTC 기준이라 서버 로컬 시간(KST 등)과 차이가 날 수 있으므로
        안전하게 전일(today - 1)을 사용한다.
        """
        from datetime import date as _date, timedelta
        return _date.today() - timedelta(days=1)

    def _fetch_single_series_vintages(
        self,
        context: IngestContext,
        spec: FredSeriesSpec,
    ) -> pd.DataFrame:
        """
        FRED vintage 데이터를 이중 청크(observation 연도 × realtime 2년)로 수집.

        FRED API 제약:
        - vintage dates > 2000 → 400 에러
        - realtime_end > FRED 기준 오늘(UTC) → 400 에러
          → 안전하게 전일(today-1)을 상한으로 사용

        일별 시리즈(DGS10)는 연간 ~250 trading days × 수년 = 수천 vintage dates
        → realtime 구간도 2년 단위로 분할하여 API 한도 이내로 유지.
        """
        from datetime import date as _date

        start = context.start_date or _date(2009, 1, 1)
        end = context.end_date or _date.today()
        safe_max = self._fred_safe_max_date()

        # end_date가 FRED 수집 가능 범위를 초과하면 경고 후 조정
        if end > safe_max:
            print(
                f"[MacroFetcher] observation_end {end} > FRED safe max {safe_max}, "
                f"adjusting to {safe_max}"
            )
            end = safe_max

        REALTIME_CHUNK_YEARS = 2

        frames: list[pd.DataFrame] = []
        obs_year = start.year
        while obs_year <= end.year:
            obs_start = _date(obs_year, 1, 1) if obs_year > start.year else start
            obs_end = _date(obs_year, 12, 31) if obs_year < end.year else end

            # realtime 구간을 2년 단위로 청크
            rt_year = obs_year
            while rt_year <= safe_max.year:
                rt_start = _date(rt_year, 1, 1) if rt_year > obs_year else obs_start
                rt_end_candidate = _date(rt_year + REALTIME_CHUNK_YEARS - 1, 12, 31)
                rt_end = min(rt_end_candidate, safe_max)

                try:
                    df_chunk = self._fetch_vintage_chunk(
                        spec,
                        obs_start=obs_start.strftime("%Y-%m-%d"),
                        obs_end=obs_end.strftime("%Y-%m-%d"),
                        rt_start=rt_start.strftime("%Y-%m-%d"),
                        rt_end=rt_end.strftime("%Y-%m-%d"),
                    )
                except _FredVintageSeriesUnavailable:
                    print(
                        "[MacroFetcher] Stop vintage collection for "
                        f"{spec.series_id}; Gold macro will use release-date "
                        "fallback where needed."
                    )
                    return self._empty_vintage_frame()
                if not df_chunk.empty:
                    frames.append(df_chunk)

                rt_year += REALTIME_CHUNK_YEARS

            obs_year += 1

        if not frames:
            return self._empty_vintage_frame()

        # 청크 간 중복 제거 (realtime 구간 경계에서 겹칠 수 있음)
        result = pd.concat(frames, ignore_index=True)
        result = result.drop_duplicates(
            subset=["series_id", "observation_date", "vintage_date"],
            keep="last",
        )
        return result.reset_index(drop=True)

    def fetch_vintages(self, context: IngestContext, **kwargs: Any) -> pd.DataFrame:
        """모든 시리즈의 vintage 데이터를 수집한다."""
        frames: list[pd.DataFrame] = []

        for spec in self.config.series_list:
            df_spec = self._fetch_single_series_vintages(context, spec)
            if not df_spec.empty:
                frames.append(df_spec)
                print(
                    f"[MacroFetcher] Vintage fetched: {spec.series_id} "
                    f"({len(df_spec)} rows)"
                )

        if not frames:
            print("[MacroFetcher] No vintage data fetched")
            return pd.DataFrame(
                columns=["series_id", "observation_date", "vintage_date",
                         "value", "source"]
            )

        return pd.concat(frames, ignore_index=True)

    # --------------------------------------------------
    # Econ events fetching (Bronze Calendar econ_events)
    # --------------------------------------------------

    _RELEASE_DATES_URL: str = "https://api.stlouisfed.org/fred/release/dates"

    def _fetch_release_dates(
        self,
        release_id: int,
        start: str,
        end: str,
    ) -> list[dict[str, Any]]:
        """단일 release_id에 대한 FRED release/dates API 호출."""
        params: dict[str, Any] = {
            "release_id": release_id,
            "api_key": self.config.api_key,
            "file_type": "json",
            "realtime_start": start,
            "realtime_end": end,
            "include_release_dates_with_no_data": "false",
        }

        time.sleep(self._VINTAGE_DELAY)

        for attempt in range(self._VINTAGE_MAX_RETRIES + 1):
            resp = requests.get(self._RELEASE_DATES_URL, params=params, timeout=30)
            if resp.status_code == 429:
                if attempt < self._VINTAGE_MAX_RETRIES:
                    wait = self._VINTAGE_BACKOFF_BASE * (2 ** attempt)
                    print(
                        f"[MacroFetcher] 429 rate limited (release_id={release_id}), "
                        f"retry {attempt + 1}/{self._VINTAGE_MAX_RETRIES} "
                        f"after {wait:.0f}s"
                    )
                    time.sleep(wait)
                    continue
            resp.raise_for_status()
            break

        data = resp.json()
        return data.get("release_dates", [])

    @staticmethod
    def _release_date_to_observation_date(release_date_str: str) -> str:
        """월간 릴리스의 release_date → observation_date (전월 1일) 매핑."""
        from datetime import timedelta
        rd = pd.Timestamp(release_date_str).date()
        first_of_month = rd.replace(day=1)
        prev_month_last = first_of_month - timedelta(days=1)
        return prev_month_last.replace(day=1).strftime("%Y-%m-%d")

    def fetch_econ_events(
        self, context: IngestContext, **kwargs: Any
    ) -> pd.DataFrame:
        """FRED release/dates API로 econ_events Bronze 데이터 수집."""
        from pretrend.pipeline.calendar.config import RELEASE_ID_TO_INDICATORS

        start = (context.start_date or pd.Timestamp("2009-01-01").date()).strftime("%Y-%m-%d")
        safe_max = self._fred_safe_max_date()
        end_date = context.end_date or pd.Timestamp.today().date()
        if end_date > safe_max:
            end_date = safe_max
        end = end_date.strftime("%Y-%m-%d")

        rows: list[dict[str, Any]] = []

        for release_id, indicator_ids in RELEASE_ID_TO_INDICATORS.items():
            release_dates = self._fetch_release_dates(release_id, start, end)
            print(
                f"[MacroFetcher] EconEvents fetched: release_id={release_id} "
                f"({len(release_dates)} release dates)"
            )

            for rd_entry in release_dates:
                release_date_str = rd_entry.get("date")
                if not release_date_str:
                    continue

                obs_date = self._release_date_to_observation_date(release_date_str)

                for indicator_id in indicator_ids:
                    rows.append({
                        "indicator_id": indicator_id,
                        "observation_date": obs_date,
                        "release_date_local": release_date_str,
                        "source": "fred_release_dates",
                    })

        if not rows:
            print("[MacroFetcher] No econ_events data fetched")
            return pd.DataFrame(
                columns=["indicator_id", "observation_date",
                         "release_date_local", "source"]
            )

        return pd.DataFrame(rows)


class EconEventsNormalizer:
    """
    Raw econ_events DataFrame을 Bronze Calendar econ_events 스키마로 정규화.

    입력: indicator_id, observation_date(str), release_date_local(str), source
    출력: ECON_EVENTS_BRONZE_COLUMNS
    """

    def normalize(
        self,
        context: IngestContext,
        raw_df: pd.DataFrame,
    ) -> pd.DataFrame:
        from pretrend.pipeline.calendar.config import ECON_EVENTS_BRONZE_COLUMNS

        if raw_df is None or raw_df.empty:
            print("[EconEventsNormalizer] empty input, skip")
            return pd.DataFrame(columns=ECON_EVENTS_BRONZE_COLUMNS)

        df = raw_df.copy()
        df["observation_date"] = pd.to_datetime(df["observation_date"]).dt.date
        df["release_date_local"] = pd.to_datetime(df["release_date_local"]).dt.date
        df["release_ts_utc"] = pd.NaT
        df["run_id"] = context.run_id
        df["ingestion_ts"] = context.ingestion_ts

        return df[ECON_EVENTS_BRONZE_COLUMNS]


class EconEventsWriter:
    """
    Bronze Calendar econ_events를 parquet로 저장.

    저장 경로:
        data/bronze/calendar/econ_events/year=YYYY/month=MM/econ_events_YYYYMM.parquet
    """

    def write(
        self,
        context: IngestContext,
        normalized_df: pd.DataFrame,
    ) -> None:
        if normalized_df is None or normalized_df.empty:
            print("[EconEventsWriter] empty input, skip")
            return

        df = normalized_df.copy()
        df["year"] = df["observation_date"].apply(lambda d: d.year)
        df["month"] = df["observation_date"].apply(lambda d: d.month)

        base_path = context.output_root / "calendar" / "econ_events"

        for (year, month), part in df.groupby(["year", "month"]):
            out_dir = base_path / f"year={year}" / f"month={month:02d}"
            out_dir.mkdir(parents=True, exist_ok=True)

            file_name = f"econ_events_{year}{month:02d}.parquet"
            out_path = out_dir / file_name

            part.drop(columns=["year", "month"]).to_parquet(
                out_path, index=False,
            )
            print(f"[EconEventsWriter] Saved: {out_path}")


class VintageNormalizer:
    """
    Raw vintage DataFrame을 Bronze Calendar fred_vintages 스키마로 정규화.

    입력: series_id, observation_date(str), vintage_date(str), value(str), source
    출력: series_id, observation_date, vintage_date, value, source, run_id, ingestion_ts
    """

    def normalize(
        self,
        context: IngestContext,
        raw_df: pd.DataFrame,
    ) -> pd.DataFrame:
        if raw_df is None or raw_df.empty:
            print("[VintageNormalizer] empty input, skip")
            return pd.DataFrame(
                columns=["series_id", "observation_date", "vintage_date",
                         "value", "source", "run_id", "ingestion_ts"]
            )

        df = raw_df.copy()
        df["observation_date"] = pd.to_datetime(df["observation_date"]).dt.date
        df["vintage_date"] = pd.to_datetime(df["vintage_date"]).dt.date
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df["run_id"] = context.run_id
        df["ingestion_ts"] = context.ingestion_ts

        return df[["series_id", "observation_date", "vintage_date",
                    "value", "source", "run_id", "ingestion_ts"]]


class VintageWriter:
    """
    Bronze Calendar fred_vintages를 parquet로 저장.

    저장 경로 (contract §4b):
        data/bronze/calendar/fred_vintages/year=YYYY/month=MM/fred_vintages_YYYYMM.parquet
    """

    def write(
        self,
        context: IngestContext,
        normalized_df: pd.DataFrame,
    ) -> None:
        if normalized_df is None or normalized_df.empty:
            print("[VintageWriter] empty input, skip")
            return

        df = normalized_df.copy()
        df["year"] = df["observation_date"].apply(lambda d: d.year)
        df["month"] = df["observation_date"].apply(lambda d: d.month)

        base_path = context.output_root / "calendar" / "fred_vintages"

        for (year, month), part in df.groupby(["year", "month"]):
            out_dir = base_path / f"year={year}" / f"month={month:02d}"
            out_dir.mkdir(parents=True, exist_ok=True)

            file_name = f"fred_vintages_{year}{month:02d}.parquet"
            out_path = out_dir / file_name

            part.drop(columns=["year", "month"]).to_parquet(
                out_path, index=False,
            )
            print(f"[VintageWriter] Saved: {out_path}")


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
