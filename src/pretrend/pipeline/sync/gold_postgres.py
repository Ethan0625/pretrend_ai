from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine import URL


logger = logging.getLogger(__name__)

WATERMARK_LOOKBACK_DAYS_MACRO = 35
WATERMARK_LOOKBACK_DAYS_EOD = 0

MACRO_GOLD_ROOT_REL = "gold/macro/macro_features"
EOD_GOLD_ROOT_REL = "gold/eod/eod_features"

MACRO_COLUMNS = [
    "indicator_id",
    "trade_date",
    "selected_observation_date",
    "selected_value",
    "selected_release_date",
    "delta_1m",
    "delta_3m",
    "delta_6m",
    "direction",
    "regime",
    "zscore_12m",
    "release_source",
    "is_assumption_based",
]

EOD_COLUMNS = [
    "symbol",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
    "currency",
    "prev_adj_close",
    "ret_1d",
    "log_ret_1d",
    "ret_5d",
    "ret_20d",
    "vol_20d",
    "vol_60d",
    "ma_5",
    "ma_20",
    "ma_60",
    "ma_120",
    "ma_ratio_5_20",
    "atr_14",
    "rsi_14",
    "intraday_range",
    "gap_open",
    "volume_zscore_20d",
    "is_trading_day",
    "is_missing_imputed",
    "is_outlier",
    "is_partial_day",
    "asset_group",
    "asset_name",
    "asset_subtype",
    "run_id_gold",
    "ingestion_ts_gold",
]

MACRO_UPDATE_COLUMNS = MACRO_COLUMNS[2:]
EOD_UPDATE_COLUMNS = EOD_COLUMNS[2:]


def _read_dotenv() -> dict[str, str]:
    env_path = Path(".env")
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    for line in env_path.read_text().splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def _get_env_value(key: str, dotenv_values: dict[str, str]) -> str | None:
    return os.getenv(key) or dotenv_values.get(key)


def _database_url_from_env() -> str:
    dotenv_values = _read_dotenv()
    user = _get_env_value("POSTGRES_USER", dotenv_values)
    password = _get_env_value("POSTGRES_PASSWORD", dotenv_values)
    database = _get_env_value("POSTGRES_DB", dotenv_values)
    host = _get_env_value("POSTGRES_HOST", dotenv_values) or "localhost"
    port = _get_env_value("POSTGRES_PORT", dotenv_values) or "5432"
    if not user or not password or not database:
        missing = [
            key
            for key, value in {
                "POSTGRES_USER": user,
                "POSTGRES_PASSWORD": password,
                "POSTGRES_DB": database,
            }.items()
            if not value
        ]
        raise RuntimeError(f"Missing database settings: {missing}")

    return URL.create(
        drivername="postgresql+psycopg2",
        username=user,
        password=password,
        host=host,
        port=int(port),
        database=database,
    ).render_as_string(hide_password=False)


def get_engine() -> Engine:
    return create_engine(_database_url_from_env())



def _default_gold_root(relative: str) -> Path:
    data_root = Path(os.getenv("PRETREND_DATA_ROOT", "data"))
    return data_root / relative


def _get_watermark(engine: Engine, table_name: str) -> date | None:
    allowed = {"gold_macro_features", "gold_eod_features"}
    if table_name not in allowed:
        raise ValueError(f"Unsupported table_name: {table_name}")

    with engine.connect() as conn:
        value = conn.execute(
            text(f"SELECT MAX(trade_date) FROM {table_name}")
        ).scalar_one()
    return value


def _month_start(value: date) -> date:
    return date(value.year, value.month, 1)


def _file_in_scope(path: Path, lower_bound: date | None) -> bool:
    if lower_bound is None:
        return True

    year = None
    month = None
    for part in path.parts:
        if part.startswith("year="):
            year = int(part.split("=", 1)[1])
        elif part.startswith("month="):
            month = int(part.split("=", 1)[1])

    if year is None or month is None:
        return True
    return date(year, month, 1) >= _month_start(lower_bound)


def _read_parquet_files(
    gold_root: Path,
    columns: list[str],
    lower_bound: date | None,
) -> pd.DataFrame:
    files = [
        path
        for path in sorted(gold_root.rglob("*.parquet"))
        if _file_in_scope(path, lower_bound)
    ]
    if not files:
        return pd.DataFrame(columns=columns)

    frames = [pd.read_parquet(path) for path in files]
    df = pd.concat(frames, ignore_index=True)
    for column in columns:
        if column not in df.columns:
            df[column] = None
    return df[columns].copy()


def _filter_by_lower_bound(
    df: pd.DataFrame,
    lower_bound: date | None,
) -> pd.DataFrame:
    if df.empty or lower_bound is None:
        return df.copy()

    out = df.copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"]).dt.date
    return out[out["trade_date"] > lower_bound].reset_index(drop=True)


def _normalize_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        if value.tzinfo is not None:
            return value.to_pydatetime()
        return value.to_pydatetime()
    if isinstance(value, datetime):
        return value
    return value


def _records(df: pd.DataFrame, columns: list[str]) -> list[dict[str, Any]]:
    if df.empty:
        return []
    out = df.copy()
    for col in columns:
        if col.endswith("_date") or col == "trade_date":
            out[col] = pd.to_datetime(out[col]).dt.date
    return [
        {column: _normalize_value(row[column]) for column in columns}
        for row in out.to_dict(orient="records")
    ]


def _load_macro_parquet(gold_root: Path, lower_bound: date | None) -> pd.DataFrame:
    return _read_parquet_files(gold_root, MACRO_COLUMNS, lower_bound)


def _load_eod_parquet(gold_root: Path, lower_bound: date | None) -> pd.DataFrame:
    return _read_parquet_files(gold_root, EOD_COLUMNS, lower_bound)


def _upsert_macro(engine: Engine, df: pd.DataFrame) -> int:
    records = _records(df, MACRO_COLUMNS)
    if not records:
        return 0

    insert_cols = ", ".join(MACRO_COLUMNS)
    value_cols = ", ".join(f":{column}" for column in MACRO_COLUMNS)
    update_cols = ", ".join(
        f"{column} = EXCLUDED.{column}" for column in MACRO_UPDATE_COLUMNS
    )
    stmt = text(
        f"""
        INSERT INTO gold_macro_features ({insert_cols})
        VALUES ({value_cols})
        ON CONFLICT (indicator_id, trade_date) DO UPDATE SET
          {update_cols}
        """
    )

    with engine.begin() as conn:
        conn.execute(stmt, records)
    return len(records)


def _upsert_eod(engine: Engine, df: pd.DataFrame) -> int:
    records = _records(df, EOD_COLUMNS)
    if not records:
        return 0

    insert_cols = ", ".join(EOD_COLUMNS)
    value_cols = ", ".join(f":{column}" for column in EOD_COLUMNS)
    update_cols = ", ".join(
        f"{column} = EXCLUDED.{column}" for column in EOD_UPDATE_COLUMNS
    )
    stmt = text(
        f"""
        INSERT INTO gold_eod_features ({insert_cols})
        VALUES ({value_cols})
        ON CONFLICT (symbol, trade_date) DO UPDATE SET
          {update_cols}
        """
    )

    with engine.begin() as conn:
        conn.execute(stmt, records)
    return len(records)


def sync_gold_macro(
    gold_root: Path | None = None,
    engine: Engine | None = None,
) -> dict[str, Any]:
    engine = engine or get_engine()
    gold_root = gold_root or _default_gold_root(MACRO_GOLD_ROOT_REL)

    watermark_before = _get_watermark(engine, "gold_macro_features")
    lower_bound = (
        None
        if watermark_before is None
        else watermark_before - timedelta(days=WATERMARK_LOOKBACK_DAYS_MACRO)
    )
    df = _load_macro_parquet(gold_root, lower_bound)
    df_filtered = _filter_by_lower_bound(df, lower_bound)
    rows_upserted = _upsert_macro(engine, df_filtered)
    watermark_after = _get_watermark(engine, "gold_macro_features")

    result = {
        "table": "gold_macro_features",
        "rows_read": int(len(df)),
        "rows_upserted": int(rows_upserted),
        "watermark_before": watermark_before.isoformat()
        if watermark_before is not None
        else None,
        "watermark_after": watermark_after.isoformat()
        if watermark_after is not None
        else None,
    }
    logger.info("[GoldPostgresSync] macro sync result=%s", result)
    return result


def sync_gold_eod(
    gold_root: Path | None = None,
    engine: Engine | None = None,
) -> dict[str, Any]:
    engine = engine or get_engine()
    gold_root = gold_root or _default_gold_root(EOD_GOLD_ROOT_REL)

    watermark_before = _get_watermark(engine, "gold_eod_features")
    lower_bound = (
        None
        if watermark_before is None
        else watermark_before - timedelta(days=WATERMARK_LOOKBACK_DAYS_EOD)
    )
    df = _load_eod_parquet(gold_root, lower_bound)
    df_filtered = _filter_by_lower_bound(df, lower_bound)
    rows_upserted = _upsert_eod(engine, df_filtered)
    watermark_after = _get_watermark(engine, "gold_eod_features")

    result = {
        "table": "gold_eod_features",
        "rows_read": int(len(df)),
        "rows_upserted": int(rows_upserted),
        "watermark_before": watermark_before.isoformat()
        if watermark_before is not None
        else None,
        "watermark_after": watermark_after.isoformat()
        if watermark_after is not None
        else None,
    }
    logger.info("[GoldPostgresSync] eod sync result=%s", result)
    return result
