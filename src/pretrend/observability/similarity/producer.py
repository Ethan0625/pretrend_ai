from __future__ import annotations

import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine import URL

from pretrend.observability.similarity.columns import (
    REGIME_SIMILARITY_FEATURE_COLUMNS,
    ROTATION_FEATURE_COLUMNS,
)


MARKET_STATE_FEATURE_TABLE = "gold_market_state_similarity_feature"

RISK_DIRECTION_CODE = {
    "RISK_ON": 1,
    "NEUTRAL": 0,
    "RISK_OFF": -1,
}

SHORT_SIGNAL_CODE = {
    "RELIEF": 1,
    "STABLE": 0,
    "PANIC": -1,
}

ROTATION_STATE_CODE = {
    "STRONG": 1,
    "NEUTRAL": 0,
    "WEAK": -1,
}

LONG_PHASES = {
    "EXPANSION": "long_phase_expansion",
    "LATE_CYCLE": "long_phase_late_cycle",
    "SLOWDOWN": "long_phase_slowdown",
    "RECESSION": "long_phase_recession",
    "RECOVERY": "long_phase_recovery",
    "UNKNOWN": "long_phase_unknown",
}

SIMILARITY_ASSET_NAMES = [
    "SP500",
    "NASDAQ100",
    "DOW30",
    "US_DIVIDEND",
    "RUSSELL2000",
    "US_DIVIDEND_SELECT",
    "US_DIVIDEND_APPRECIATION",
    "SOUTH_KOREA",
    "CHINA",
    "JAPAN",
    "INDIA",
    "GOLD",
    "GOLD_MINERS",
    "SILVER",
    "CRUDE_OIL",
    "OIL_PRODUCERS",
    "NATURAL_GAS",
    "AGRICULTURE",
    "US_TREASURY_20Y",
    "US_HIGH_YIELD",
    "US_INVESTMENT_GRADE",
    "US_TREASURY_1_3Y",
    "US_TIPS",
    "HEALTH_CARE",
    "ENERGY",
    "SEMICONDUCTOR",
    "FINANCIALS",
    "REGIONAL_BANKS",
    "NUCLEAR",
    "INFORMATION_TECH",
    "MATERIALS",
    "CONSUMER_DISCRETIONARY",
    "CONSUMER_STAPLES",
    "COMMUNICATION_SERVICES",
    "REAL_ESTATE",
    "UTILITIES",
    "INDUSTRIALS",
]

EXCLUDED_ASSET_GROUPS = {"VOLATILITY_INDEX"}
EXCLUDED_ASSET_NAMES = {"CBOE_VOLATILITY_INDEX", "CBOE_SKEW_INDEX"}

ASSET_NAME_TO_ROTATION_COLUMN = dict(
    zip(SIMILARITY_ASSET_NAMES, ROTATION_FEATURE_COLUMNS)
)

TRANSITION_NUMERIC_COLUMNS = [
    "state_age_days",
    "sojourn_prob_5d",
    "sojourn_prob_10d",
    "sojourn_prob_20d",
    "sojourn_prob_60d",
    "sojourn_prob_120d",
    "transition_hazard_5d",
    "transition_hazard_10d",
    "transition_hazard_20d",
    "transition_hazard_60d",
    "transition_hazard_120d",
]


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


def _env_value(key: str, dotenv_values: dict[str, str]) -> str | None:
    return os.getenv(key) or dotenv_values.get(key)


def _database_url_from_env() -> str:
    dotenv_values = _read_dotenv()
    user = _env_value("POSTGRES_USER", dotenv_values)
    password = _env_value("POSTGRES_PASSWORD", dotenv_values)
    database = _env_value("POSTGRES_DB", dotenv_values)
    host = _env_value("POSTGRES_HOST", dotenv_values) or "localhost"
    port = _env_value("POSTGRES_PORT", dotenv_values) or "5432"
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


def _get_engine() -> Engine:
    return create_engine(_database_url_from_env())


def _normalize_label(value: Any) -> str:
    if value is None or pd.isna(value):
        return "UNKNOWN"
    return str(value).strip().upper()


def encode_risk_direction(value: str) -> int | None:
    return RISK_DIRECTION_CODE.get(_normalize_label(value))


def encode_short_signal(value: str) -> int | None:
    return SHORT_SIGNAL_CODE.get(_normalize_label(value))


def encode_rotation_state(value: str) -> int | None:
    return ROTATION_STATE_CODE.get(_normalize_label(value))


def encode_bool(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)) and value in (0, 1):
        return int(value)
    normalized = str(value).strip().lower()
    if normalized in {"true", "t", "1", "yes", "y"}:
        return 1
    if normalized in {"false", "f", "0", "no", "n"}:
        return 0
    return None


def pivot_rotation_features(rotation_df: pd.DataFrame | None) -> pd.DataFrame:
    columns = ["trade_date", *ROTATION_FEATURE_COLUMNS]
    if rotation_df is None or rotation_df.empty:
        return pd.DataFrame(columns=columns)

    required = {"trade_date", "asset_name"}
    if not required.issubset(rotation_df.columns):
        missing = sorted(required - set(rotation_df.columns))
        raise ValueError(f"rotation_df missing required columns: {missing}")

    state_col = (
        "group_state_now"
        if "group_state_now" in rotation_df.columns
        else "rotation_state"
    )
    if state_col not in rotation_df.columns:
        raise ValueError("rotation_df requires group_state_now or rotation_state")

    out = rotation_df.copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"]).dt.date
    out["asset_name"] = out["asset_name"].astype(str).str.upper()
    if "asset_group" in out.columns:
        out = out[~out["asset_group"].astype(str).str.upper().isin(EXCLUDED_ASSET_GROUPS)]
    out = out[~out["asset_name"].isin(EXCLUDED_ASSET_NAMES)]
    out = out[out["asset_name"].isin(ASSET_NAME_TO_ROTATION_COLUMN)]
    if out.empty:
        return pd.DataFrame(columns=columns)

    out["feature_column"] = out["asset_name"].map(ASSET_NAME_TO_ROTATION_COLUMN)
    out["feature_value"] = out[state_col].map(encode_rotation_state)
    pivot = (
        out.sort_values(["trade_date", "feature_column"])
        .drop_duplicates(["trade_date", "feature_column"], keep="last")
        .pivot(index="trade_date", columns="feature_column", values="feature_value")
        .reset_index()
    )
    for column in ROTATION_FEATURE_COLUMNS:
        if column not in pivot.columns:
            pivot[column] = None
    return pivot[columns].sort_values("trade_date").reset_index(drop=True)


def build_market_state_feature_frame(
    market_state_df: pd.DataFrame,
    rotation_df: pd.DataFrame | None = None,
    query_start: date | None = None,
    query_end: date | None = None,
) -> pd.DataFrame:
    if market_state_df is None or market_state_df.empty:
        return pd.DataFrame(columns=["trade_date", *REGIME_SIMILARITY_FEATURE_COLUMNS])
    if "trade_date" not in market_state_df.columns:
        raise ValueError("market_state_df requires trade_date")

    state = market_state_df.copy()
    state["trade_date"] = pd.to_datetime(state["trade_date"]).dt.date
    if query_start is not None:
        state = state[state["trade_date"] >= query_start]
    if query_end is not None:
        state = state[state["trade_date"] <= query_end]
    if state.empty:
        return pd.DataFrame(columns=["trade_date", *REGIME_SIMILARITY_FEATURE_COLUMNS])

    rows: list[dict[str, Any]] = []
    for raw in state.to_dict(orient="records"):
        row: dict[str, Any] = {"trade_date": raw["trade_date"]}
        long_phase = _normalize_label(raw.get("long_phase"))
        if long_phase not in LONG_PHASES or long_phase == "UNKNOWN":
            for column in LONG_PHASES.values():
                row[column] = None
        else:
            for phase, column in LONG_PHASES.items():
                row[column] = 1 if long_phase == phase else 0

        row["mid_regime_code"] = encode_risk_direction(raw.get("mid_regime"))
        row["short_signal_code"] = encode_short_signal(raw.get("short_signal"))
        row["long_phase_confidence"] = raw.get("long_phase_confidence")
        row["mid_regime_confidence"] = raw.get("mid_regime_confidence")
        row["short_signal_confidence"] = raw.get("short_signal_confidence")
        row["run_universe_flag"] = encode_bool(raw.get("run_universe"))
        row["risk_gate_flag"] = encode_bool(raw.get("risk_gate"))
        for column in TRANSITION_NUMERIC_COLUMNS:
            row[column] = raw.get(column)
        rows.append(row)

    frame = pd.DataFrame(rows).drop_duplicates(["trade_date"], keep="last")
    rotation = pivot_rotation_features(rotation_df)
    if not rotation.empty:
        frame = frame.merge(rotation, on="trade_date", how="left")
    for column in ROTATION_FEATURE_COLUMNS:
        if column not in frame.columns:
            frame[column] = None

    for column in REGIME_SIMILARITY_FEATURE_COLUMNS:
        if column not in frame.columns:
            frame[column] = None
    return (
        frame[["trade_date", *REGIME_SIMILARITY_FEATURE_COLUMNS]]
        .sort_values("trade_date")
        .reset_index(drop=True)
    )


def _normalize_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    return value


def _records(df: pd.DataFrame, built_at: datetime) -> list[dict[str, Any]]:
    if df.empty:
        return []
    out = df.copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"]).dt.date
    out["built_at"] = built_at
    columns = ["trade_date", *REGIME_SIMILARITY_FEATURE_COLUMNS, "built_at"]
    return [
        {column: _normalize_value(row[column]) for column in columns}
        for row in out[columns].to_dict(orient="records")
    ]


def _upsert_market_state_features(engine: Engine, df: pd.DataFrame) -> int:
    built_at = datetime.now(timezone.utc)
    records = _records(df, built_at)
    if not records:
        return 0

    columns = ["trade_date", *REGIME_SIMILARITY_FEATURE_COLUMNS, "built_at"]
    insert_cols = ", ".join(columns)
    value_cols = ", ".join(f":{column}" for column in columns)
    update_cols = ", ".join(
        f"{column} = EXCLUDED.{column}"
        for column in [*REGIME_SIMILARITY_FEATURE_COLUMNS, "built_at"]
    )
    stmt = text(
        f"""
        INSERT INTO {MARKET_STATE_FEATURE_TABLE} ({insert_cols})
        VALUES ({value_cols})
        ON CONFLICT (trade_date) DO UPDATE SET
          {update_cols}
        """
    )
    with engine.begin() as conn:
        conn.execute(stmt, records)
    return len(records)


def build_market_state_similarity_features(
    query_start: date,
    query_end: date,
    engine: Engine | None = None,
    market_state_df: pd.DataFrame | None = None,
    rotation_df: pd.DataFrame | None = None,
) -> dict[str, Any]:
    if market_state_df is None:
        raise ValueError("market_state_df is required for P26-3a producer")
    db_engine = engine or _get_engine()
    frame = build_market_state_feature_frame(
        market_state_df,
        rotation_df=rotation_df,
        query_start=query_start,
        query_end=query_end,
    )
    rows = _upsert_market_state_features(db_engine, frame)
    return {
        "rows_upserted": rows,
        "query_count": len(frame),
        "table": MARKET_STATE_FEATURE_TABLE,
    }
