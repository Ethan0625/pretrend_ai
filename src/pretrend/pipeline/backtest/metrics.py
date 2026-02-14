"""
Backtest 성과 지표 — CAGR, MDD, Sharpe 등.
"""
from __future__ import annotations

import math
from typing import Dict

import pandas as pd


def compute_metrics(daily_nav: pd.Series, benchmark_nav: pd.Series) -> Dict:
    """일별 NAV 시리즈로부터 성과 지표를 산출한다.

    Parameters
    ----------
    daily_nav : Series
        index=date, values=portfolio NAV.
    benchmark_nav : Series
        index=date, values=benchmark NAV (동일 기간).

    Returns
    -------
    Dict with metric names → values.
    """
    if len(daily_nav) < 2:
        return _empty_metrics()

    initial = daily_nav.iloc[0]
    final = daily_nav.iloc[len(daily_nav) - 1]

    # Total return
    total_return = (final - initial) / initial if initial > 0 else 0.0

    # CAGR
    n_days = (daily_nav.index[-1] - daily_nav.index[0]).days
    years = n_days / 365.25 if n_days > 0 else 1.0
    cagr = (final / initial) ** (1 / years) - 1 if initial > 0 and years > 0 else 0.0

    # Daily returns
    daily_ret = daily_nav.pct_change().dropna()

    # Max Drawdown
    cummax = daily_nav.cummax()
    drawdown = (daily_nav - cummax) / cummax
    max_drawdown = drawdown.min()

    # Sharpe (annualized, rf=0)
    if len(daily_ret) > 1 and daily_ret.std() > 0:
        sharpe = (daily_ret.mean() / daily_ret.std()) * math.sqrt(252)
    else:
        sharpe = 0.0

    # Sortino (downside deviation)
    downside = daily_ret[daily_ret < 0]
    if len(downside) > 1 and downside.std() > 0:
        sortino = (daily_ret.mean() / downside.std()) * math.sqrt(252)
    else:
        sortino = 0.0

    # Calmar
    calmar = cagr / abs(max_drawdown) if max_drawdown != 0 else 0.0

    # Win rate (monthly)
    monthly_ret = daily_nav.resample("ME").last().pct_change().dropna()
    win_rate = (monthly_ret > 0).mean() if len(monthly_ret) > 0 else 0.0

    # Benchmark metrics
    bm_total = 0.0
    bm_cagr = 0.0
    bm_mdd = 0.0
    if len(benchmark_nav) >= 2:
        bm_initial = benchmark_nav.iloc[0]
        bm_final = benchmark_nav.iloc[len(benchmark_nav) - 1]
        bm_total = (bm_final - bm_initial) / bm_initial if bm_initial > 0 else 0.0
        bm_cagr = (
            (bm_final / bm_initial) ** (1 / years) - 1
            if bm_initial > 0 and years > 0
            else 0.0
        )
        bm_cummax = benchmark_nav.cummax()
        bm_dd = (benchmark_nav - bm_cummax) / bm_cummax
        bm_mdd = bm_dd.min()

    return {
        "total_return": total_return,
        "cagr": cagr,
        "max_drawdown": max_drawdown,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "calmar_ratio": calmar,
        "win_rate_monthly": win_rate,
        "benchmark_total_return": bm_total,
        "benchmark_cagr": bm_cagr,
        "benchmark_max_drawdown": bm_mdd,
        "excess_return": total_return - bm_total,
        "excess_cagr": cagr - bm_cagr,
    }


def compute_period_metrics(
    daily_nav: pd.Series,
    benchmark_nav: pd.Series,
    start: str,
    end: str,
) -> Dict:
    """특정 구간의 성과 지표를 산출한다."""
    mask = (daily_nav.index >= pd.Timestamp(start)) & (
        daily_nav.index <= pd.Timestamp(end)
    )
    nav_slice = daily_nav[mask]
    bm_mask = (benchmark_nav.index >= pd.Timestamp(start)) & (
        benchmark_nav.index <= pd.Timestamp(end)
    )
    bm_slice = benchmark_nav[bm_mask]
    return compute_metrics(nav_slice, bm_slice)


def _empty_metrics() -> Dict:
    return {
        "total_return": 0.0,
        "cagr": 0.0,
        "max_drawdown": 0.0,
        "sharpe_ratio": 0.0,
        "sortino_ratio": 0.0,
        "calmar_ratio": 0.0,
        "win_rate_monthly": 0.0,
        "benchmark_total_return": 0.0,
        "benchmark_cagr": 0.0,
        "benchmark_max_drawdown": 0.0,
        "excess_return": 0.0,
        "excess_cagr": 0.0,
    }
