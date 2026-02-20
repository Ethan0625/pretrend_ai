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

from .metrics import compute_metrics, compute_period_metrics, compute_phase_distribution

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


# ── Phase 분포 모니터링 ──────────────────────────────────────

# 경고 기준 (KPI threshold)
_LATE_CYCLE_WARN = 0.60   # 연도별 LATE_CYCLE% 경고
_SR_WARN_HIGH = 0.50      # S+R 합계% 경고 (과다)
_SR_WARN_LOW = 0.15       # S+R 합계% 경고 (과소)


def print_phase_distribution(
    policy_df,
    *,
    group_by: str = "year",
) -> None:
    """연/반기/분기별 long_phase 분포 테이블을 콘솔에 출력한다.

    경고 기준:
      - LATE_CYCLE% > 60% → 「!」 표시
      - S+R 합계% > 50% 또는 < 15% → 「!」 표시
    """
    dist_df = compute_phase_distribution(policy_df, group_by=group_by)
    if dist_df.empty:
        print("[PhaseDistribution] No data.")
        return

    header = f"  Phase Distribution by {group_by.upper()}"
    print(f"\n{'='*60}")
    print(header)
    print(f"{'='*60}")
    print(f"  {'Period':<12} {'LATE%':>6} {'SLOW%':>6} {'REC%':>6} {'S+R%':>6} {'EXP%':>6} {'REC%':>6} {'UNK%':>6}  Warn")
    print(f"  {'-'*12} {'------':>6} {'------':>6} {'------':>6} {'------':>6} {'------':>6} {'------':>6} {'------':>6}")
    for _, row in dist_df.iterrows():
        warn = ""
        if row["LATE_CYCLE_pct"] > _LATE_CYCLE_WARN:
            warn += "L"
        if row["SR_combined_pct"] > _SR_WARN_HIGH:
            warn += "H"
        elif row["SR_combined_pct"] < _SR_WARN_LOW:
            warn += "l"
        warn_str = f"  ! ({warn})" if warn else ""
        print(
            f"  {str(row['period']):<12}"
            f" {row['LATE_CYCLE_pct']:>5.1%}"
            f" {row['SLOWDOWN_pct']:>6.1%}"
            f" {row['RECESSION_pct']:>6.1%}"
            f" {row['SR_combined_pct']:>6.1%}"
            f" {row['EXPANSION_pct']:>6.1%}"
            f" {row['RECOVERY_pct']:>6.1%}"
            f" {row['UNKNOWN_pct']:>6.1%}"
            f"{warn_str}"
        )
    print(f"{'='*60}\n")


# ── Walk-Forward 출력/저장 ──────────────────────────────────

_WF_CAVEAT = (
    "주의: 본 결과는 동일 snapshot 재사용으로 look-ahead bias가 존재할 수 있음"
)


def print_walk_forward_summary(
    df: pd.DataFrame,
    *,
    caveat: bool = True,
) -> None:
    """Walk-Forward 기간별 성과 테이블을 콘솔에 출력한다.

    Parameters
    ----------
    df : pd.DataFrame
        WalkForwardRunner.run()의 반환값.
    caveat : bool
        True(기본)이면 헤더에 look-ahead bias 주의문 포함.
    """
    if df.empty:
        print("[WalkForward] No results.")
        return

    print(f"\n{'='*70}")
    print("  Walk-Forward Period Analysis")
    if caveat:
        print(f"  ※ {_WF_CAVEAT}")
    print(f"  Preset: {df['preset'].iloc[0] if 'preset' in df.columns else 'N/A'}")
    print(f"{'='*70}")
    print(
        f"  {'Window':<24} {'CAGR':>7} {'Total':>7} {'MDD':>7} {'Sharpe':>7} {'Exc.CAGR':>9}"
    )
    print(f"  {'-'*24} {'-------':>7} {'-------':>7} {'-------':>7} {'-------':>7} {'---------':>9}")
    for _, row in df.iterrows():
        ws = str(row["window_start"])[:7] if pd.notna(row["window_start"]) else "?"
        we = str(row["window_end"])[:7] if pd.notna(row["window_end"]) else "?"
        window_label = f"{ws} ~ {we}"
        print(
            f"  {window_label:<24}"
            f" {row['cagr']:>+7.2%}"
            f" {row['total_return']:>+7.1%}"
            f" {row['max_drawdown']:>7.2%}"
            f" {row['sharpe_ratio']:>7.2f}"
            f" {row['excess_cagr']:>+9.2%}"
        )
    print(f"{'─'*70}")
    print(
        f"  {'Mean':<24}"
        f" {df['cagr'].mean():>+7.2%}"
        f" {df['total_return'].mean():>+7.1%}"
        f" {df['max_drawdown'].mean():>7.2%}"
        f" {df['sharpe_ratio'].mean():>7.2f}"
        f" {df['excess_cagr'].mean():>+9.2%}"
    )
    print(f"{'='*70}\n")


def save_walk_forward(
    df: pd.DataFrame,
    preset: str,
    base_dir: "Path",
) -> "Path":
    """Walk-Forward 결과를 Parquet + 요약 JSON으로 저장한다.

    저장 산출물:
        {base_dir}/walk_forward_{preset}_{ts}.parquet
        {base_dir}/walk_forward_{preset}_{ts}_summary.json

    Returns
    -------
    Path
        저장된 base_dir 경로.
    """
    from pathlib import Path as _Path

    base_dir = _Path(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = f"walk_forward_{preset}_{ts}"

    # Parquet
    parquet_path = base_dir / f"{stem}.parquet"
    df.to_parquet(parquet_path, index=False)

    # 요약 JSON
    summary = {
        "preset": preset,
        "n_windows": len(df),
        "mean_cagr": round(df["cagr"].mean(), 6) if not df.empty else None,
        "min_cagr": round(df["cagr"].min(), 6) if not df.empty else None,
        "max_cagr": round(df["cagr"].max(), 6) if not df.empty else None,
        "mean_total_return": round(df["total_return"].mean(), 6) if not df.empty else None,
        "mean_max_drawdown": round(df["max_drawdown"].mean(), 6) if not df.empty else None,
        "mean_sharpe": round(df["sharpe_ratio"].mean(), 6) if not df.empty else None,
        "generated_at": ts,
        "caveat": _WF_CAVEAT,
    }
    summary_path = base_dir / f"{stem}_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info("[save_walk_forward] 저장 완료 → %s", base_dir)
    return base_dir


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

    # metrics JSON (total_return 포함)
    if result.metrics:
        metrics_path = out_dir / f"{stem}_metrics.json"
        metrics_path.write_text(
            json.dumps(result.metrics, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    logger.info(
        "[save_result] 저장 완료 → %s  (%s, %s_trades, %s_config.json, %s_metrics.json)",
        out_dir, stem, stem, stem, stem,
    )
    return out_dir
