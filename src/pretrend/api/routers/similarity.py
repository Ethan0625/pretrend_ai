from __future__ import annotations

from datetime import date, timedelta
from math import isfinite, sqrt
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pretrend.api.auth import require_api_key
from pretrend.api.db import get_session
from pretrend.api.routers._utils import not_found
from pretrend.api.schemas import (
    EventSimilarityItem,
    EventSimilarityResponse,
    ReplayAssetOverlay,
    ReplayAssetRanking,
    ReplayAssetPath,
    ReplayPathPoint,
    ReplayTrajectory,
    SimilarityNeighbor,
    SimilarityReplayResponse,
    SimilarityResponse,
)
from pretrend.models import GoldEodFeature, GoldMarketStateSimilarityFeature, SimilarityGold, SimilarityRegime
from pretrend.observability.similarity.events import compute_event_similarities


router = APIRouter(
    prefix="/api/v1/similarity",
    tags=["similarity"],
    dependencies=[Depends(require_api_key)],
)


DEFAULT_REPLAY_RANK_SYMBOLS = [
    "SPY",
    "VOO",
    "QQQ",
    "DIA",
    "SCHD",
    "IWM",
    "DVY",
    "VIG",
    "EWY",
    "ASHR",
    "CQQQ",
    "EWJ",
    "INDA",
    "IAU",
    "GDX",
    "SLV",
    "USO",
    "XOP",
    "UNG",
    "DBA",
    "TLT",
    "HYG",
    "LQD",
    "SHY",
    "TIP",
    "XLV",
    "XLE",
    "SOXX",
    "XLF",
    "KRE",
    "NLR",
    "XLK",
    "XLB",
    "XLY",
    "XLP",
    "XLC",
    "XLRE",
    "XLU",
    "XLI",
]


@router.get("", response_model=SimilarityResponse)
@router.get("/", response_model=SimilarityResponse, include_in_schema=False)
async def get_similarity(
    query_date: date,
    view: Literal["regime", "gold"],
    top_n: int = Query(default=10, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> SimilarityResponse:
    model = SimilarityRegime if view == "regime" else SimilarityGold
    result = await session.execute(
        select(model)
        .where(model.query_date == query_date)
        .order_by(model.rank)
        .limit(top_n)
    )
    rows = result.scalars().all()
    if not rows:
        raise not_found(
            "similarity",
            {"query_date": query_date.isoformat(), "view": view},
        )
    return SimilarityResponse(
        query_date=query_date,
        view=view,
        neighbors=[
            SimilarityNeighbor(
                neighbor_date=row.neighbor_date,
                rank=row.rank,
                score=row.score,
                gap_days=row.gap_days,
            )
            for row in rows
        ],
    )


@router.get("/replay", response_model=SimilarityReplayResponse)
async def get_similarity_replay(
    query_date: date,
    view: Literal["events", "regime", "gold"] = "events",
    top_n: int = Query(default=5, ge=1, le=10),
    compare_days: int = Query(default=60, ge=0, le=180),
    forward_days: int = Query(default=30, ge=1, le=180),
    top_assets: int = Query(default=5, ge=1, le=10),
    symbol: str = Query(default="SPY"),
    ranking_symbols: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> SimilarityReplayResponse:
    if compare_days + forward_days > 365:
        raise HTTPException(
            status_code=422,
            detail="compare_days + forward_days must be less than or equal to 365",
        )
    selected_symbol = _parse_symbol(symbol)
    rank_symbols = _parse_ranking_symbols(ranking_symbols, selected_symbol)
    anchors = await _load_replay_anchors(
        session,
        query_date=query_date,
        view=view,
        top_n=top_n,
    )
    if not anchors:
        raise not_found(
            "similarity_replay",
            {"query_date": query_date.isoformat(), "view": view},
            reason="not_yet_built",
            latest_available=await _latest_replay_source_date(session, view),
        )

    current_start = query_date - timedelta(days=compare_days)
    current_end = query_date
    windows = [
        (
            rank,
            anchor_date,
            actual_date,
            score,
            label,
            event_name,
            actual_date - timedelta(days=compare_days),
            actual_date,
            actual_date + timedelta(days=forward_days),
        )
        for rank, anchor_date, actual_date, score, label, event_name in anchors
    ]
    date_filters = [
        and_(GoldEodFeature.trade_date >= current_start, GoldEodFeature.trade_date <= current_end),
        *[
            and_(GoldEodFeature.trade_date >= window_start, GoldEodFeature.trade_date <= window_end)
            for _, _, _, _, _, _, window_start, _, window_end in windows
        ],
    ]
    eod_result = await session.execute(
        select(GoldEodFeature)
        .where(
            GoldEodFeature.symbol.in_(rank_symbols),
            or_(*date_filters),
        )
        .order_by(GoldEodFeature.symbol, GoldEodFeature.trade_date)
    )
    eod_rows = eod_result.scalars().all()
    current_paths = {
        item: _build_asset_path(
            eod_rows,
            symbol=item,
            anchor_date=query_date,
            window_start=current_start,
            window_end=current_end,
        )
        for item in rank_symbols
    }

    trajectories = []
    for rank, anchor_date, actual_date, score, label, event_name, window_start, compare_end, window_end in windows:
        historical_paths = {
            item: _build_asset_path(
                eod_rows,
                symbol=item,
                anchor_date=actual_date,
                window_start=window_start,
                window_end=window_end,
            )
            for item in rank_symbols
        }
        current_path = current_paths[selected_symbol]
        historical_path = historical_paths[selected_symbol]
        asset_rankings = _build_asset_rankings(current_paths, historical_paths)
        trajectories.append(
            ReplayTrajectory(
                label=label,
                event_name=event_name,
                anchor_date=anchor_date,
                actual_date=actual_date,
                rank=rank,
                state_similarity_score=score,
                trajectory_similarity_score=_trajectory_similarity(current_path, historical_path),
                compare_start=window_start,
                compare_end=compare_end,
                window_start=window_start,
                window_end=window_end,
                current_path=current_path,
                historical_path=historical_path,
                overlay_assets=_build_asset_overlays(
                    current_paths,
                    historical_paths,
                    asset_rankings,
                    top_assets=top_assets,
                ),
                asset_rankings=asset_rankings,
            )
        )

    return SimilarityReplayResponse(
        query_date=query_date,
        view=view,
        symbol=selected_symbol,
        asset_name=current_paths[selected_symbol].asset_name,
        compare_days=compare_days,
        forward_days=forward_days,
        trajectories=trajectories,
    )


@router.get("/events", response_model=EventSimilarityResponse)
async def get_similarity_events(
    query_date: date,
    session: AsyncSession = Depends(get_session),
) -> EventSimilarityResponse:
    query_row, event_rows = await compute_event_similarities(query_date, session)
    if query_row is None:
        raise not_found("regime", {"trade_date": query_date.isoformat()})
    return EventSimilarityResponse(
        query_date=query_date,
        data=[
            EventSimilarityItem(
                event_name=event.name,
                anchor_date=event.anchor_date,
                actual_date=actual_date,
                similarity_score=score,
            )
            for event, actual_date, score in event_rows
        ],
    )


ReplayAnchor = tuple[int, date, date, float, str, str | None]


async def _load_replay_anchors(
    session: AsyncSession,
    *,
    query_date: date,
    view: Literal["events", "regime", "gold"],
    top_n: int,
) -> list[ReplayAnchor]:
    if view == "events":
        query_row, event_rows = await compute_event_similarities(query_date, session)
        if query_row is None:
            return []
        return [
            (rank, event.anchor_date, actual_date, score, event.name, event.name)
            for rank, (event, actual_date, score) in enumerate(event_rows, start=1)
            if actual_date is not None and score is not None
        ][:top_n]

    model = SimilarityRegime if view == "regime" else SimilarityGold
    result = await session.execute(
        select(model)
        .where(model.query_date == query_date)
        .order_by(model.rank)
        .limit(top_n)
    )
    rows = result.scalars().all()
    return [
        (
            row.rank,
            row.neighbor_date,
            row.neighbor_date,
            row.score,
            row.neighbor_date.isoformat(),
            None,
        )
        for row in rows
    ]


async def _latest_replay_source_date(
    session: AsyncSession,
    view: Literal["events", "regime", "gold"],
) -> date | None:
    if view == "events":
        result = await session.execute(select(func.max(GoldMarketStateSimilarityFeature.trade_date)))
        return result.scalar_one_or_none()
    model = SimilarityRegime if view == "regime" else SimilarityGold
    result = await session.execute(select(func.max(model.query_date)))
    return result.scalar_one_or_none()


def _parse_symbol(raw: str) -> str:
    symbol = raw.strip().upper()
    if not symbol:
        raise HTTPException(status_code=422, detail="symbol must not be empty")
    return symbol


def _parse_ranking_symbols(raw: str | None, selected_symbol: str) -> list[str]:
    source = raw if raw is not None else ",".join(DEFAULT_REPLAY_RANK_SYMBOLS)
    symbols = [selected_symbol]
    for value in source.split(","):
        symbol = value.strip().upper()
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    if len(symbols) > 60:
        raise HTTPException(status_code=422, detail="ranking_symbols can include at most 60 symbols")
    return symbols


def _build_asset_path(
    rows: list[GoldEodFeature],
    *,
    symbol: str,
    anchor_date: date,
    window_start: date,
    window_end: date,
) -> ReplayAssetPath:
    symbol_rows = [
        row
        for row in rows
        if row.symbol == symbol and window_start <= row.trade_date <= window_end
    ]
    symbol_rows.sort(key=lambda row: row.trade_date)
    base = _base_row(symbol_rows, anchor_date)
    base_price = _price(base) if base is not None else None
    points = []
    for row in symbol_rows:
        price = _price(row)
        normalized = (
            (price / base_price) - 1.0
            if price is not None and base_price is not None and base_price > 0
            else None
        )
        points.append(
            ReplayPathPoint(
                trade_date=row.trade_date,
                day_offset=(row.trade_date - anchor_date).days,
                adj_close=price,
                normalized_return=normalized,
            )
        )
    label_row = base or (symbol_rows[0] if symbol_rows else None)
    return ReplayAssetPath(
        symbol=symbol,
        asset_name=getattr(label_row, "asset_name", None) or symbol,
        asset_group=getattr(label_row, "asset_group", None),
        base_date=base.trade_date if base is not None else None,
        base_adj_close=base_price,
        points=points,
    )


def _build_asset_rankings(
    current_paths: dict[str, ReplayAssetPath],
    historical_paths: dict[str, ReplayAssetPath],
) -> list[ReplayAssetRanking]:
    rankings = [
        ReplayAssetRanking(
            symbol=symbol,
            asset_name=current_path.asset_name or historical_paths[symbol].asset_name,
            asset_group=current_path.asset_group or historical_paths[symbol].asset_group,
            trajectory_similarity_score=_trajectory_similarity(current_path, historical_paths[symbol]),
        )
        for symbol, current_path in current_paths.items()
        if symbol in historical_paths
    ]
    rankings.sort(
        key=lambda row: (
            row.trajectory_similarity_score is None,
            -(row.trajectory_similarity_score or 0.0),
            row.asset_name,
            row.symbol,
        )
    )
    return rankings[:10]


def _build_asset_overlays(
    current_paths: dict[str, ReplayAssetPath],
    historical_paths: dict[str, ReplayAssetPath],
    rankings: list[ReplayAssetRanking],
    *,
    top_assets: int,
) -> list[ReplayAssetOverlay]:
    overlays = []
    for ranking in rankings[:top_assets]:
        if ranking.symbol not in current_paths or ranking.symbol not in historical_paths:
            continue
        overlays.append(
            ReplayAssetOverlay(
                symbol=ranking.symbol,
                asset_name=ranking.asset_name,
                asset_group=ranking.asset_group,
                trajectory_similarity_score=ranking.trajectory_similarity_score,
                current_path=current_paths[ranking.symbol],
                historical_path=historical_paths[ranking.symbol],
            )
        )
    return overlays


def _trajectory_similarity(
    current_path: ReplayAssetPath,
    historical_path: ReplayAssetPath,
) -> float | None:
    current_by_offset = {
        point.day_offset: point.normalized_return
        for point in current_path.points
        if point.normalized_return is not None
    }
    pairs = [
        (current_by_offset[point.day_offset], point.normalized_return)
        for point in historical_path.points
        if point.day_offset in current_by_offset and point.normalized_return is not None
    ]
    if len(pairs) < 2:
        return None
    dot = sum(current * historical for current, historical in pairs)
    current_norm = sqrt(sum(current * current for current, _ in pairs))
    historical_norm = sqrt(sum(historical * historical for _, historical in pairs))
    if current_norm == 0.0 or historical_norm == 0.0:
        return None
    score = dot / (current_norm * historical_norm)
    if not isfinite(score):
        return None
    return min(max(float(score), 0.0), 1.0)


def _base_row(rows: list[GoldEodFeature], actual_date: date) -> GoldEodFeature | None:
    for row in rows:
        if row.trade_date >= actual_date and _price(row) is not None:
            return row
    for row in rows:
        if _price(row) is not None:
            return row
    return None


def _price(row: GoldEodFeature | None) -> float | None:
    if row is None:
        return None
    value = row.adj_close if row.adj_close is not None else row.close
    if value is None or value <= 0:
        return None
    return float(value)
