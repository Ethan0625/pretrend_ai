from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pretrend.observability.similarity.features import (
    build_gold_view_features,
    build_regime_view_features,
)
from pretrend.observability.similarity.producer import _get_engine


DEFAULT_TOP_N = 100
DEFAULT_MIN_GAP_DAYS = 30


def cosine_topn(
    query_vec: np.ndarray,
    candidate_matrix: np.ndarray,
    candidate_dates: list[date],
    query_date: date,
    n: int = DEFAULT_TOP_N,
    min_gap: int = DEFAULT_MIN_GAP_DAYS,
) -> list[dict[str, Any]]:
    query = np.asarray(query_vec, dtype=float)
    query_norm = np.linalg.norm(query)
    if query_norm == 0:
        return []

    rows: list[dict[str, Any]] = []
    for candidate_date, raw_candidate in zip(candidate_dates, candidate_matrix):
        gap_days = (query_date - candidate_date).days
        if gap_days < min_gap:
            continue

        candidate = np.asarray(raw_candidate, dtype=float)
        candidate_norm = np.linalg.norm(candidate)
        if candidate_norm == 0:
            score = 0.0
        else:
            score = float(np.dot(query, candidate) / (query_norm * candidate_norm))
        if score < 0:
            continue
        rows.append(
            {
                "neighbor_date": candidate_date,
                "score": min(score, 1.0),
                "gap_days": gap_days,
            }
        )

    rows.sort(key=lambda row: (-row["score"], row["neighbor_date"]))
    top_rows = rows[:n]
    for rank, row in enumerate(top_rows, start=1):
        row["rank"] = rank
    return top_rows


def build_similarity_regime(
    query_start: date,
    query_end: date,
    engine: Engine | None = None,
) -> dict[str, Any]:
    db_engine = engine or _get_engine()
    candidate_dates = _fetch_trade_dates(
        db_engine,
        "gold_market_state_similarity_feature",
    )
    query_dates = [
        trade_date
        for trade_date in candidate_dates
        if query_start <= trade_date <= query_end
    ]
    features = build_regime_view_features(db_engine, candidate_dates)
    rows = _build_rows_for_view(query_dates, features)
    rows_upserted = _replace_similarity_rows(
        db_engine,
        "similarity_regime",
        query_dates,
        rows,
    )
    return {"rows_upserted": rows_upserted, "query_count": len(query_dates), "view": "regime"}


def build_similarity_gold(
    query_start: date,
    query_end: date,
    engine: Engine | None = None,
) -> dict[str, Any]:
    db_engine = engine or _get_engine()
    candidate_dates = _fetch_gold_trade_dates(db_engine)
    query_dates = [
        trade_date
        for trade_date in candidate_dates
        if query_start <= trade_date <= query_end
    ]
    features = build_gold_view_features(db_engine, candidate_dates)
    rows = _build_rows_for_view(query_dates, features)
    rows_upserted = _replace_similarity_rows(
        db_engine,
        "similarity_gold",
        query_dates,
        rows,
    )
    return {"rows_upserted": rows_upserted, "query_count": len(query_dates), "view": "gold"}


def _fetch_trade_dates(engine: Engine, table_name: str) -> list[date]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(f"SELECT DISTINCT trade_date FROM {table_name} ORDER BY trade_date")
        ).scalars()
        return [pd.Timestamp(row).date() for row in rows]


def _fetch_gold_trade_dates(engine: Engine) -> list[date]:
    sql = text(
        """
        SELECT trade_date FROM gold_eod_features
        UNION
        SELECT trade_date FROM gold_macro_features
        ORDER BY trade_date
        """
    )
    with engine.connect() as conn:
        return [pd.Timestamp(row).date() for row in conn.execute(sql).scalars()]


def _build_rows_for_view(
    query_dates: list[date],
    features: pd.DataFrame,
) -> list[dict[str, Any]]:
    if features.empty:
        return []

    candidate_dates = list(features.index)
    candidate_matrix = features.to_numpy(dtype=float)
    rows: list[dict[str, Any]] = []
    for query_date in query_dates:
        if query_date not in features.index:
            continue
        top_rows = cosine_topn(
            features.loc[query_date].to_numpy(dtype=float),
            candidate_matrix,
            candidate_dates,
            query_date,
        )
        for row in top_rows:
            rows.append({"query_date": query_date, **row})
    return rows


def _replace_similarity_rows(
    engine: Engine,
    table_name: str,
    query_dates: list[date],
    rows: list[dict[str, Any]],
) -> int:
    if not query_dates:
        return 0

    built_at = datetime.now(timezone.utc)
    records = [{**row, "built_at": built_at} for row in rows]
    insert_sql = text(
        f"""
        INSERT INTO {table_name}
          (query_date, neighbor_date, rank, score, gap_days, built_at)
        VALUES
          (:query_date, :neighbor_date, :rank, :score, :gap_days, :built_at)
        """
    )
    delete_sql = text(f"DELETE FROM {table_name} WHERE query_date = ANY(:query_dates)")

    with engine.begin() as conn:
        conn.execute(delete_sql, {"query_dates": query_dates})
        if records:
            conn.execute(insert_sql, records)
    return len(records)
