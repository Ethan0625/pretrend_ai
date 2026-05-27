from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from math import isfinite
from typing import Any, Sequence

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pretrend.models import GoldMarketStateSimilarityFeature
from pretrend.observability.similarity.columns import REGIME_SIMILARITY_FEATURE_COLUMNS


@dataclass(frozen=True)
class HistoricalEvent:
    name: str
    anchor_date: date


HISTORICAL_EVENTS: list[HistoricalEvent] = [
    HistoricalEvent("닷컴버블 정점", date(2000, 3, 24)),
    HistoricalEvent("9/11 테러", date(2001, 9, 10)),
    HistoricalEvent("사스 공포", date(2003, 4, 3)),
    HistoricalEvent("서브프라임 위기 시작", date(2007, 8, 9)),
    HistoricalEvent("리먼 파산", date(2008, 9, 15)),
    HistoricalEvent("금융위기 저점", date(2009, 3, 9)),
    HistoricalEvent("미국 신용등급 강등", date(2011, 8, 8)),
    HistoricalEvent("유로존 위기", date(2012, 7, 26)),
    HistoricalEvent("테이퍼 탠트럼", date(2013, 5, 22)),
    HistoricalEvent("차이나 쇼크", date(2015, 8, 24)),
    HistoricalEvent("브렉시트", date(2016, 6, 24)),
    HistoricalEvent("트럼프 1기 당선", date(2016, 11, 9)),
    HistoricalEvent("VIX 폭발", date(2018, 2, 5)),
    HistoricalEvent("크리스마스 폭락", date(2018, 12, 24)),
    HistoricalEvent("미중 관세 폭탄", date(2019, 5, 13)),
    HistoricalEvent("COVID 폭락", date(2020, 3, 16)),
    HistoricalEvent("밈주식 광란", date(2021, 1, 27)),
    HistoricalEvent("연준 긴축 전환 공식화", date(2022, 1, 26)),
    HistoricalEvent("연준 75bp 인상", date(2022, 6, 16)),
    HistoricalEvent("SVB 파산", date(2023, 3, 10)),
]


EventSimilarityRows = list[tuple[HistoricalEvent, date | None, float | None]]


async def compute_event_similarities(
    query_date: date,
    session: AsyncSession,
) -> tuple[GoldMarketStateSimilarityFeature | None, EventSimilarityRows]:
    result = await session.execute(
        select(GoldMarketStateSimilarityFeature).order_by(
            GoldMarketStateSimilarityFeature.trade_date
        )
    )
    rows = result.scalars().all()
    return compute_event_similarity_rows(query_date, rows)


def compute_event_similarity_rows(
    query_date: date,
    rows: Sequence[Any],
) -> tuple[Any | None, EventSimilarityRows]:
    rows_by_date = {row.trade_date: row for row in rows}
    query_row = rows_by_date.get(query_date)
    if query_row is None:
        return None, []

    vectors_by_date = _normalized_vectors_by_date(rows)
    query_vector = vectors_by_date.get(query_date)
    if query_vector is None:
        return query_row, _null_event_rows()

    event_rows: EventSimilarityRows = []
    for event in HISTORICAL_EVENTS:
        actual_date = _nearest_available_date(event.anchor_date, rows_by_date)
        if actual_date is None:
            event_rows.append((event, None, None))
            continue
        event_rows.append(
            (
                event,
                actual_date,
                cosine_similarity_score(query_vector, vectors_by_date[actual_date]),
            )
        )

    event_rows.sort(key=_sort_key)
    return query_row, event_rows


def cosine_similarity_score(
    query_vector: np.ndarray,
    candidate_vector: np.ndarray,
) -> float | None:
    query_norm = float(np.linalg.norm(query_vector))
    candidate_norm = float(np.linalg.norm(candidate_vector))
    if query_norm == 0.0 or candidate_norm == 0.0:
        return None

    raw_score = float(np.dot(query_vector, candidate_vector) / (query_norm * candidate_norm))
    if not isfinite(raw_score):
        return None
    return min(max(raw_score, 0.0), 1.0)


def _normalized_vectors_by_date(
    rows: Sequence[Any],
) -> dict[date, np.ndarray]:
    if not rows:
        return {}

    matrix = np.array(
        [
            [_numeric_or_nan(getattr(row, column, None)) for column in REGIME_SIMILARITY_FEATURE_COLUMNS]
            for row in rows
        ],
        dtype=float,
    )
    mean, std = _column_mean_std(matrix)
    filled = np.where(np.isfinite(matrix), matrix, mean)
    normalized = np.nan_to_num((filled - mean) / std, nan=0.0, posinf=0.0, neginf=0.0)
    return {row.trade_date: vector for row, vector in zip(rows, normalized)}


def _column_mean_std(matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    means: list[float] = []
    stds: list[float] = []
    for column in matrix.T:
        valid = column[np.isfinite(column)]
        if valid.size == 0:
            means.append(0.0)
            stds.append(1.0)
            continue
        means.append(float(valid.mean()))
        std = float(valid.std(ddof=0))
        stds.append(std if std != 0.0 else 1.0)
    return np.array(means, dtype=float), np.array(stds, dtype=float)


def _numeric_or_nan(value: object) -> float:
    if value is None:
        return np.nan
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return np.nan
    return numeric if isfinite(numeric) else np.nan


def _nearest_available_date(
    anchor_date: date,
    rows_by_date: dict[date, GoldMarketStateSimilarityFeature],
) -> date | None:
    if anchor_date in rows_by_date:
        return anchor_date

    start = anchor_date - timedelta(days=5)
    end = anchor_date + timedelta(days=5)
    candidates = [trade_date for trade_date in rows_by_date if start <= trade_date <= end]
    if not candidates:
        return None
    return min(candidates, key=lambda trade_date: (abs((trade_date - anchor_date).days), trade_date))


def _null_event_rows() -> EventSimilarityRows:
    return [(event, None, None) for event in HISTORICAL_EVENTS]


def _sort_key(row: tuple[HistoricalEvent, date | None, float | None]):
    event, actual_date, score = row
    return (
        score is None,
        -(score or 0.0),
        actual_date or date.max,
        event.anchor_date,
    )
