"""
Backtest 성과 출력 — 전체 + 구간별 분석.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from .metrics import compute_metrics, compute_period_metrics

# 주요 구간 정의
NOTABLE_PERIODS: List[Tuple[str, str, str]] = [
    ("GFC", "2008-09-01", "2009-03-31"),
    ("COVID", "2020-02-01", "2020-04-30"),
    ("Rate Hike", "2022-01-01", "2022-12-31"),
    ("Recovery 2023", "2023-01-01", "2023-12-31"),
]


def print_report(result) -> None:
    """백테스트 결과를 콘솔에 출력한다."""
    daily_log = result.daily_log
    benchmark_nav = result.benchmark_nav

    if daily_log.empty:
        print("No backtest data.")
        return

    nav_series = daily_log["nav"]
    start = nav_series.index[0].strftime("%Y-%m")
    end = nav_series.index[-1].strftime("%Y-%m")

    # 전체 성과
    metrics = compute_metrics(nav_series, benchmark_nav)

    print(f"\n{'='*60}")
    print(f"  Backtest Result ({start} ~ {end})")
    print(f"{'='*60}")
    print(f"  Preset:           {result.config.preset_name or 'custom'}")
    print(f"  Initial Capital:  ${result.config.initial_capital:,.0f}")
    print(f"  Final NAV:        ${nav_series.iloc[-1]:,.2f}")
    print(f"  Total Return:     {metrics['total_return']:+.1%}")
    print(f"  CAGR:             {metrics['cagr']:+.2%}")
    print(f"  Max Drawdown:     {metrics['max_drawdown']:.2%}")
    print(f"  Sharpe Ratio:     {metrics['sharpe_ratio']:.2f}")
    print(f"  Sortino Ratio:    {metrics['sortino_ratio']:.2f}")
    print(f"  Calmar Ratio:     {metrics['calmar_ratio']:.2f}")
    print(f"  Win Rate (M):     {metrics['win_rate_monthly']:.1%}")
    print(f"{'─'*60}")
    print(f"  Benchmark (SPY B&H):")
    print(f"  Total Return:     {metrics['benchmark_total_return']:+.1%}")
    print(f"  CAGR:             {metrics['benchmark_cagr']:+.2%}")
    print(f"  Max Drawdown:     {metrics['benchmark_max_drawdown']:.2%}")
    print(f"  Excess Return:    {metrics['excess_return']:+.1%}")
    print(f"  Excess CAGR:      {metrics['excess_cagr']:+.2%}")

    # 구간별 성과
    for name, ps, pe in NOTABLE_PERIODS:
        pm = compute_period_metrics(nav_series, benchmark_nav, ps, pe)
        if pm["total_return"] == 0.0 and pm["max_drawdown"] == 0.0:
            continue
        print(f"{'─'*60}")
        print(f"  {name} ({ps[:7]} ~ {pe[:7]})")
        print(f"    Return:    {pm['total_return']:+.1%}  vs  SPY {pm['benchmark_total_return']:+.1%}")
        print(f"    MDD:       {pm['max_drawdown']:.2%}  vs  SPY {pm['benchmark_max_drawdown']:.2%}")

    # 매매 요약
    n_trades = len(result.trade_log)
    n_buys = sum(1 for t in result.trade_log if t.action == "BUY")
    n_sells = sum(1 for t in result.trade_log if t.action == "SELL")
    print(f"{'─'*60}")
    print(f"  Trades: {n_trades} total ({n_buys} buys, {n_sells} sells)")
    print(f"{'='*60}\n")
