"""
Backtest 성과 출력 + 결과 저장 — 전체 + 구간별 분석.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .metrics import compute_metrics, compute_period_metrics

logger = logging.getLogger(__name__)

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


# ── 결과 저장 ────────────────────────────────────────────────


def _config_to_dict(config) -> dict:
    """BacktestConfig → JSON-직렬화 가능한 dict 변환."""
    def _v(val):
        if isinstance(val, date):
            return val.isoformat()
        if isinstance(val, Path):
            return str(val)
        if isinstance(val, dict):
            # tuple 키(v2 target_ratio_map_v2) → "EXPANSION,RISK_ON" 형태 문자열 키
            return {
                (",".join(k) if isinstance(k, tuple) else k): v
                for k, v in val.items()
            }
        if isinstance(val, (list, tuple)):
            return list(val)
        return val

    cfg = config
    return {
        "preset_name":                cfg.preset_name,
        "start_date":                 _v(cfg.start_date),
        "end_date":                   _v(cfg.end_date),
        "initial_capital":            cfg.initial_capital,
        "initial_invested_ratio":     cfg.initial_invested_ratio,
        "initial_weights":            _v(cfg.initial_weights),
        "schd_start_date":            _v(cfg.schd_start_date),
        "pre_schd_weights":           _v(cfg.pre_schd_weights),
        "rebalance_freq":             cfg.rebalance_freq,
        "max_tactical_slots":         cfg.max_tactical_slots,
        "tactical_weight":            cfg.tactical_weight,
        "tactical_groups":            _v(cfg.tactical_groups),
        "target_ratio_map":           _v(cfg.target_ratio_map),
        "target_ratio_map_v2":        _v(cfg.target_ratio_map_v2),
        "allocation_adjustment_limit": cfg.allocation_adjustment_limit,
        "allocation_step_size":       cfg.allocation_step_size,
        "benchmark_symbol":           cfg.benchmark_symbol,
        "data_root":                  _v(cfg.data_root),
    }


def _default_result_dir() -> Path:
    """PRETREND_RESULT_ROOT 환경변수 기반 기본 저장 경로."""
    return Path(os.getenv("PRETREND_RESULT_ROOT", "result")) / "backtest"


def save_result(
    result,
    base_dir: str | Path | None = None,
) -> Optional[Path]:
    """백테스트 결과를 parquet + JSON으로 저장한다.

    base_dir 미지정 시 PRETREND_RESULT_ROOT 환경변수(기본값: "result")를 참조한다.

    저장 경로:
        {base_dir}/{version}/{capital}_{benchmark}_{start}-{end}_{timestamp}.parquet
        {base_dir}/{version}/{capital}_{benchmark}_{start}-{end}_{timestamp}_trades.parquet
        {base_dir}/{version}/{capital}_{benchmark}_{start}-{end}_{timestamp}_config.json

    Returns
    -------
    Path
        저장된 디렉토리 경로. daily_log가 없으면 None.
    """
    if result.daily_log.empty:
        logger.warning("[save_result] daily_log가 비어있어 저장을 건너뜁니다.")
        return None

    resolved_dir = Path(base_dir) if base_dir is not None else _default_result_dir()

    cfg = result.config
    version = cfg.preset_name or "custom"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    capital = f"{cfg.initial_capital:.0f}"
    benchmark = cfg.benchmark_symbol
    period = f"{cfg.start_date.strftime('%Y%m%d')}-{cfg.end_date.strftime('%Y%m%d')}"
    stem = f"{capital}_{benchmark}_{period}_{ts}"

    out_dir = resolved_dir / version
    out_dir.mkdir(parents=True, exist_ok=True)

    # daily_log (인덱스 포함)
    daily_path = out_dir / f"{stem}.parquet"
    result.daily_log.to_parquet(daily_path)

    # trade_log
    if result.trade_log:
        trades_df = pd.DataFrame([
            {
                "trade_date": t.trade_date,
                "symbol":     t.symbol,
                "action":     t.action,
                "shares":     t.shares,
                "price":      t.price,
                "amount":     t.amount,
            }
            for t in result.trade_log
        ])
        trades_path = out_dir / f"{stem}_trades.parquet"
        trades_df.to_parquet(trades_path, index=False)

    # config JSON
    config_path = out_dir / f"{stem}_config.json"
    config_path.write_text(
        json.dumps(_config_to_dict(cfg), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info(
        "[save_result] 저장 완료 → %s  (%s, %s_trades, %s_config.json)",
        out_dir, stem, stem, stem,
    )
    return out_dir
