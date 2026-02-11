from __future__ import annotations

import os
import argparse
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence
from datetime import timedelta

import pandas as pd
import yfinance as yf  # requirements.txt에 yfinance 추가 필요

from pretrend.pipeline.ingest.base import (
    IngestContext,
    BaseFetcher,
    BaseNormalizer,
    BaseWriter,
)
from pretrend.pipeline.config.eod_observability import (
    LABEL_BY_SYMBOL_V1,
    OBSERVABILITY_SYMBOLS_V1,
)

logger = logging.getLogger(__name__)


# -------------------------------------------------
# Config
# -------------------------------------------------


@dataclass
class EodIngestConfig:
    """
    EOD Bronze ingest 설정.

    - data_root: data/ 이하 루트
    - default_symbols: 초기 테스트용 기본 심볼 (SPY, QQQ, VOO)
    """

    data_root: Path = Path(os.getenv("PRETREND_DATA_ROOT", "data"))
    default_symbols: List[str] = None

    def __post_init__(self) -> None:
        if self.default_symbols is None:
            self.default_symbols = list(OBSERVABILITY_SYMBOLS_V1)

    @property
    def bronze_root(self) -> Path:
        """
        IngestContext.output_root로 들어가는 bronze 루트.
        macro_job과 동일하게 data/bronze 기준으로 사용.
        """
        return self.data_root / "bronze"


# -------------------------------------------------
# Fetcher
# -------------------------------------------------


class EodFetcher(BaseFetcher):
    """
    yfinance 기반 EOD Fetcher.

    fetch() 결과 스키마(raw):
        symbol, theme, source, trade_date, open, high, low, close, adj_close, volume, currency
    """

    def __init__(self, source: str = "YF") -> None:
        self.source = source

    def fetch(
        self,
        context: IngestContext,
        symbols: Sequence[str] | None = None,
        theme: str = "GENERIC",
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        **_: Any,
    ) -> pd.DataFrame:
        """
        Args:
            context: IngestContext (start_date, end_date 사용)
            symbols: 수집할 티커 리스트 (None이면 예외)
            theme: 테마 라벨 (초기엔 단일값)
        """
        if symbols is None:
            raise ValueError("[EodFetcher] `symbols` must be provided.")

        start = start_date or context.start_date
        end = end_date or context.end_date
        if start is None or end is None:
            raise ValueError(
                "[EodFetcher] start_date/end_date must be set "
                "(via context or arguments)."
            )

        yf_end = end + timedelta(days=1)
        frames: List[pd.DataFrame] = []

        for symbol in symbols:
            logger.info(
                "[EodFetcher] fetching symbol=%s, start=%s, end=%s (yf_end=%s)",
                symbol,
                start,
                end,
                yf_end
            )

            ticker = yf.Ticker(symbol)
            hist = ticker.history(
                start=start,
                end=yf_end,
                auto_adjust=False,  # raw OHLC + Adj Close 별도
            )

            if hist.empty:
                logger.warning(
                    "[EodFetcher] No data for symbol=%s in range %s~%s",
                    symbol,
                    start,
                    end,
                )
                continue

            df = hist.reset_index().rename(
                columns={
                    "Date": "trade_date",
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Adj Close": "adj_close",
                    "Volume": "volume",
                }
            )

            df["symbol"] = symbol
            df["theme"] = theme
            df["source"] = self.source

            currency = None
            try:
                info = getattr(ticker, "fast_info", None)
                if info is not None and hasattr(info, "currency"):
                    currency = info.currency
            except Exception:
                logger.exception(
                    "[EodFetcher] Failed to get currency info for symbol=%s",
                    symbol,
                )

            df["currency"] = currency
            frames.append(df)

        if not frames:
            logger.warning("[EodFetcher] No frames collected.")
            return pd.DataFrame(
                columns=[
                    "symbol",
                    "theme",
                    "source",
                    "trade_date",
                    "open",
                    "high",
                    "low",
                    "close",
                    "adj_close",
                    "volume",
                    "currency",
                ]
            )

        out = pd.concat(frames, ignore_index=True)
        out = out[
            [
                "symbol",
                "theme",
                "source",
                "trade_date",
                "open",
                "high",
                "low",
                "close",
                "adj_close",
                "volume",
                "currency",
            ]
        ]

        return out


# -------------------------------------------------
# Normalizer
# -------------------------------------------------


class EodNormalizer(BaseNormalizer):
    """
    Raw EOD DataFrame → 표준 스키마로 정규화.

    입력(raw_df):
        symbol, theme, source, trade_date, open, high, low, close, adj_close, volume, currency
    출력(normalized_df):
        symbol, theme, source, trade_date,
        open, high, low, close, adj_close, volume,
        currency, run_id, ingestion_ts
    """

    def normalize(
        self,
        context: IngestContext,
        raw_df: pd.DataFrame,
    ) -> pd.DataFrame:
        if raw_df is None or raw_df.empty:
            logger.warning("[EodNormalizer] empty input, skip")
            return pd.DataFrame(
                columns=[
                    "symbol",
                    "theme",
                    "source",
                    "trade_date",
                    "open",
                    "high",
                    "low",
                    "close",
                    "adj_close",
                    "volume",
                    "currency",
                    "asset_group",
                    "asset_name",
                    "asset_subtype",
                    "run_id",
                    "ingestion_ts",
                ]
            )

        df = raw_df.copy()

        # 타입 정리
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date

        float_cols = ["open", "high", "low", "close", "adj_close"]
        int_cols = ["volume"]

        for col in float_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        for col in int_cols:
            if col in df.columns:
                df[col] = (
                    pd.to_numeric(df[col], errors="coerce")
                    .fillna(0)
                    .astype("int64")
                )

        # Observability 라벨 부여 (Bronze에서 1회 확정)
        unregistered = set(df["symbol"].unique()) - set(LABEL_BY_SYMBOL_V1.keys())
        if unregistered:
            raise ValueError(
                f"[EodNormalizer] unregistered symbol(s): {sorted(unregistered)}. "
                f"All symbols must be in OBSERVABILITY_SET_V1."
            )

        df["asset_group"] = df["symbol"].map(
            lambda s: LABEL_BY_SYMBOL_V1[s]["asset_group"]
        )
        df["asset_name"] = df["symbol"].map(
            lambda s: LABEL_BY_SYMBOL_V1[s]["asset_name"]
        )
        df["asset_subtype"] = df["symbol"].map(
            lambda s: LABEL_BY_SYMBOL_V1[s]["asset_subtype"]
        )

        # 공통 메타 정보 (MacroNormalizer와 동일 패턴)
        df["run_id"] = context.run_id
        df["ingestion_ts"] = context.ingestion_ts

        df = df[
            [
                "symbol",
                "theme",
                "source",
                "trade_date",
                "open",
                "high",
                "low",
                "close",
                "adj_close",
                "volume",
                "currency",
                "asset_group",
                "asset_name",
                "asset_subtype",
                "run_id",
                "ingestion_ts",
            ]
        ].sort_values(["symbol", "trade_date"])

        return df.reset_index(drop=True)


# -------------------------------------------------
# Writer
# -------------------------------------------------


class EodWriter(BaseWriter):
    """
    정규화된 EOD 데이터를 parquet로 저장.

    저장 경로:
      {output_root}/{domain}/{dataset}/
        source=YF/theme=GENERIC/symbol=SPY/trade_date=2024-01-02/eod.parquet

    예:
      data/bronze/eod/daily_prices/source=YF/theme=GENERIC/symbol=SPY/trade_date=2024-01-02/eod.parquet
    """

    def write(
        self,
        context: IngestContext,
        normalized_df: pd.DataFrame,
    ) -> None:
        if normalized_df is None or normalized_df.empty:
            logger.warning("[EodWriter] empty input, skip")
            return

        df = normalized_df.copy()

        required_cols = [
            "source",
            "theme",
            "symbol",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "adj_close",
            "volume",
            "currency",
            "run_id",
            "ingestion_ts",
        ]
        missing = set(required_cols) - set(df.columns)
        if missing:
            raise ValueError(f"[EodWriter] Missing columns: {missing}")

        base_path = context.output_root / context.domain / context.dataset

        # 파티션 단위: source/theme/symbol/trade_date
        grouped = df.groupby(
            ["source", "theme", "symbol", "trade_date"],
            as_index=False,
        )

        for (source, theme, symbol, trade_date), part in grouped:
            trade_date_str = str(trade_date)

            rel_dir = (
                f"source={source}/theme={theme}/symbol={symbol}/trade_date={trade_date_str}"
            )
            out_dir = base_path / rel_dir
            out_dir.mkdir(parents=True, exist_ok=True)

            out_path = out_dir / "eod.parquet"
            part.to_parquet(out_path, index=False)

            logger.info("[EodWriter] Saved: %s", out_path)


# -------------------------------------------------
# Runner / CLI
# -------------------------------------------------


@dataclass
class EodIngestResult:
    run_id: str
    start_date: date
    end_date: date
    symbols: List[str]
    row_count: int


def run_eod_bronze_ingest(
    start_date: date,
    end_date: date,
    symbols: Optional[Iterable[str]] = None,
    theme: str = "GENERIC",
    cfg: Optional[EodIngestConfig] = None,
) -> EodIngestResult:
    """
    3개 ETF(SPY, QQQ, VOO)를 기본으로 사용하는
    EOD Bronze ingest 실행 함수.
    """
    cfg = cfg or EodIngestConfig()
    if symbols is None:
        symbols_list = cfg.default_symbols
    else:
        symbols_list = [s.strip().upper() for s in symbols if s.strip()]

    # IngestContext: macro_job의 _run_bronze_ingest와 동일 패턴
    ctx = IngestContext(
        domain="eod",
        dataset="daily_prices",
        start_date=start_date,
        end_date=end_date,
        output_root=cfg.bronze_root,
        # run_id, meta_root, ingestion_ts는 IngestContext의 기본값 사용
    )

    logger.info(
        "[EOD Bronze] start. symbols=%s, start=%s, end=%s, output_root=%s",
        symbols_list,
        start_date,
        end_date,
        cfg.bronze_root,
    )

    fetcher = EodFetcher()
    normalizer = EodNormalizer()
    writer = EodWriter()

    raw_df = fetcher.fetch(ctx, symbols=symbols_list, theme=theme)
    if raw_df is None or raw_df.empty:
        logger.warning("[EOD Bronze] No data fetched.")
        return EodIngestResult(
            run_id=ctx.run_id,
            start_date=start_date,
            end_date=end_date,
            symbols=symbols_list,
            row_count=0,
        )

    norm_df = normalizer.normalize(ctx, raw_df)
    if norm_df is None or norm_df.empty:
        logger.warning("[EOD Bronze] Normalized dataframe is empty.")
        return EodIngestResult(
            run_id=ctx.run_id,
            start_date=start_date,
            end_date=end_date,
            symbols=symbols_list,
            row_count=0,
        )

    writer.write(ctx, norm_df)
    row_count = int(len(norm_df))

    logger.info(
        "[EOD Bronze] done. run_id=%s, rows=%s",
        ctx.run_id,
        row_count,
    )

    return EodIngestResult(
        run_id=ctx.run_id,
        start_date=start_date,
        end_date=end_date,
        symbols=symbols_list,
        row_count=row_count,
    )


# ----------------------
# CLI entrypoint
# ----------------------


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="EOD Bronze ingest for SPY/QQQ/VOO (yfinance 기반)",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default="",
        help="테스트용 티커 목록 (콤마 구분). 비우면 SPY,QQQ,VOO 사용",
    )
    parser.add_argument(
        "--start",
        type=str,
        required=True,
        help="시작일 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end",
        type=str,
        required=True,
        help="종료일 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--theme",
        type=str,
        default="GENERIC",
        help="테마 라벨 (초기엔 단일 값)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    args = _parse_args(argv)

    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    else:
        # 빈 경우: 기본 3개 ETF 사용
        symbols = None

    start_dt = date.fromisoformat(args.start)
    end_dt = date.fromisoformat(args.end)

    result = run_eod_bronze_ingest(
        start_date=start_dt,
        end_date=end_dt,
        symbols=symbols,
        theme=args.theme,
    )

    logger.info(
        "[EOD Bronze] summary: run_id=%s, symbols=%s, rows=%s, range=[%s, %s]",
        result.run_id,
        result.symbols,
        result.row_count,
        result.start_date,
        result.end_date,
    )


if __name__ == "__main__":
    main()
