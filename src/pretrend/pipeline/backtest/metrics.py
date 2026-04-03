"""
Backtest 성과 지표 — CAGR, MDD, Sharpe, XIRR 등.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import pandas as pd


def _month_end_nav(nav: pd.Series) -> pd.Series:
    """pandas 버전별 월말 리샘플 alias 차이를 흡수한다 (ME → M fallback)."""
    for freq in ("ME", "M"):
        try:
            return nav.resample(freq).last()
        except ValueError:
            continue
    raise ValueError("No supported month-end resample frequency found")


def compute_xirr(cash_flows: List[Tuple]) -> float:
    """XIRR 계산 — 이분법(bisection) 기반 내부수익률.

    Parameters
    ----------
    cash_flows : list of (date, amount)
        amount < 0: 투입 (outflow), amount > 0: 수령 (inflow).
        최소 2건 이상, 양방향(출입) 모두 존재해야 유효.

    Returns
    -------
    float
        연 수익률 (예: 0.085 = 8.5%). 계산 실패 시 0.0.
    """
    if not cash_flows or len(cash_flows) < 2:
        return 0.0

    dates = [cf[0] for cf in cash_flows]
    amounts = [cf[1] for cf in cash_flows]
    t0 = dates[0]

    try:
        days_list = [(d - t0).days for d in dates]
    except AttributeError:
        return 0.0

    if not any(a > 0 for a in amounts) or not any(a < 0 for a in amounts):
        return 0.0

    def npv(rate: float) -> float:
        try:
            return sum(
                cf / (1.0 + rate) ** (d / 365.0)
                for cf, d in zip(amounts, days_list)
            )
        except (ZeroDivisionError, OverflowError):
            return float("nan")

    lo, hi = -0.5, 5.0
    npv_lo, npv_hi = npv(lo), npv(hi)

    if math.isnan(npv_lo) or math.isnan(npv_hi):
        return 0.0

    if npv_lo * npv_hi > 0:
        lo, hi = -0.9, 20.0
        npv_lo, npv_hi = npv(lo), npv(hi)
        if npv_lo * npv_hi > 0:
            return 0.0

    try:
        for _ in range(200):
            mid = (lo + hi) / 2
            npv_mid = npv(mid)
            if math.isnan(npv_mid):
                return 0.0
            if npv_mid > 0:
                lo = mid
            else:
                hi = mid
            if hi - lo < 1e-9:
                break
        return round((lo + hi) / 2, 6)
    except Exception:
        return 0.0


def compute_metrics(
    daily_nav: pd.Series,
    benchmark_nav: pd.Series,
    total_capital_injected: float = 0.0,
    cash_flows: Optional[List[Tuple]] = None,
) -> Dict:
    """일별 NAV 시리즈로부터 성과 지표를 산출한다.

    Parameters
    ----------
    daily_nav : Series
        index=date, values=portfolio NAV.
    benchmark_nav : Series
        index=date, values=benchmark NAV (동일 기간).
    total_capital_injected : float
        initial_capital 이후 DCA로 추가 투입된 총 금액 (default: 0).
    cash_flows : list of (date, amount), optional
        XIRR 계산용 현금흐름. None이면 XIRR=0.0.

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
    monthly_ret = _month_end_nav(daily_nav).pct_change().dropna()
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

    # DCA 기준 수익률: (final - total_invested) / total_invested
    total_invested = initial + total_capital_injected
    dca_return = (final - total_invested) / total_invested if total_invested > 0 else 0.0

    # XIRR — 현금흐름 타이밍 반영 내부수익률
    xirr = compute_xirr(cash_flows) if cash_flows else 0.0

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
        "total_capital_injected": total_capital_injected,
        "dca_return": dca_return,
        "xirr": xirr,
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
        "total_capital_injected": 0.0,
        "dca_return": 0.0,
        "xirr": 0.0,
    }


# ── Phase 분포 집계 ────────────────────────────────────────────

_PHASE_COLS: List[str] = [
    "EXPANSION", "LATE_CYCLE", "SLOWDOWN", "RECESSION", "RECOVERY", "UNKNOWN",
]


def compute_phase_distribution(
    policy_df: pd.DataFrame,
    group_by: str = "year",
) -> pd.DataFrame:
    """policy_selection DataFrame → 기간별 long_phase 분포 집계.

    Parameters
    ----------
    policy_df : pd.DataFrame
        long_phase 컬럼을 포함하는 policy_selection DataFrame.
        trade_date 컬럼은 date 또는 datetime 타입.
    group_by : str
        집계 기준. "year" | "half"(상/하반기) | "quarter".

    Returns
    -------
    DataFrame with columns:
        period, EXPANSION_pct, LATE_CYCLE_pct, SLOWDOWN_pct,
        RECESSION_pct, RECOVERY_pct, UNKNOWN_pct, SR_combined_pct
    """
    if policy_df is None or policy_df.empty or "long_phase" not in policy_df.columns:
        return pd.DataFrame()

    df = policy_df.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"])

    if group_by == "year":
        df["period"] = df["trade_date"].dt.year.astype(str)
    elif group_by == "half":
        df["period"] = (
            df["trade_date"].dt.year.astype(str)
            + "-H"
            + df["trade_date"].dt.quarter.map({1: "1", 2: "1", 3: "2", 4: "2"})
        )
    elif group_by == "quarter":
        df["period"] = (
            df["trade_date"].dt.year.astype(str)
            + "-Q"
            + df["trade_date"].dt.quarter.astype(str)
        )
    else:
        raise ValueError(f"group_by must be 'year', 'half', or 'quarter'. Got: {group_by!r}")

    rows = []
    for period, grp in df.groupby("period", sort=True):
        total = len(grp)
        row: Dict = {"period": period}
        for phase in _PHASE_COLS:
            pct = (grp["long_phase"] == phase).sum() / total if total > 0 else 0.0
            row[f"{phase}_pct"] = round(pct, 4)
        row["SR_combined_pct"] = round(
            row["SLOWDOWN_pct"] + row["RECESSION_pct"], 4
        )
        rows.append(row)

    return pd.DataFrame(rows)
