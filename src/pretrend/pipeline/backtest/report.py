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

from .metrics import compute_metrics, compute_xirr, compute_period_metrics, compute_phase_distribution

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

    total_injected = getattr(result, "total_capital_injected", 0.0)
    cash_flows = getattr(result, "cash_flows", None)
    bm_cash_flows = getattr(result, "bm_cash_flows", None)

    # 포트폴리오 성과
    metrics = compute_metrics(
        nav_series, benchmark_nav,
        total_capital_injected=total_injected,
        cash_flows=cash_flows,
    )
    # 벤치마크 성과 (동일 지표 — SPY를 portfolio로 재계산)
    bm_metrics = compute_metrics(
        benchmark_nav, benchmark_nav,
        total_capital_injected=total_injected,
        cash_flows=bm_cash_flows,
    ) if not benchmark_nav.empty else {}

    preset = result.config.preset_name or "custom"
    SEP = "─" * 62

    # 사이드바이사이드 행 포맷: 라벨 | 전략 | SPY
    def row(label: str, pval: str, bval: str = "") -> str:
        return f"  {label:<26} {pval:>13}  {bval:>13}"

    def hdr(label: str, pcol: str, bcol: str) -> str:
        return f"  {label:<26} {pcol:>13}  {bcol:>13}"

    print(f"\n{'='*62}")
    print(f"  백테스트 결과 (Backtest Result) — {start} ~ {end}")
    print(f"{'='*62}")
    print(f"  전략 (Preset):     {preset}")
    print(f"  초기 자본:         ${result.config.initial_capital:,.2f}"
          f"   │  월 적립금:  ${result.config.monthly_addition:,.2f}")
    print(f"  총 투입금:         ${total_injected:,.2f}")
    print(f"  {SEP}")
    print(hdr("", f"전략 ({preset})", "SPY B&H"))
    print(f"  {SEP}")

    bm_final = f"${benchmark_nav.iloc[-1]:,.2f}" if not benchmark_nav.empty else "—"
    print(row("최종 자산 (Final NAV)", f"${nav_series.iloc[-1]:,.2f}", bm_final))
    print(f"  {SEP}")
    print(row("적립식 수익률 (DCA Ret)",
              f"{metrics.get('dca_return', 0):+.1%}",
              f"{bm_metrics.get('dca_return', 0):+.1%}"))
    print(row("내부수익률 (XIRR)",
              f"{metrics.get('xirr', 0):+.2%}",
              f"{bm_metrics.get('xirr', 0):+.2%}"))
    print(row("연평균 수익률 (CAGR)",
              f"{metrics['cagr']:+.2%}",
              f"{bm_metrics.get('cagr', 0):+.2%}"))
    print(row("최대 낙폭 (MDD)",
              f"{metrics['max_drawdown']:.2%}",
              f"{bm_metrics.get('max_drawdown', 0):.2%}"))
    print(row("샤프 비율 (Sharpe)",
              f"{metrics['sharpe_ratio']:.2f}",
              f"{bm_metrics.get('sharpe_ratio', 0):.2f}"))
    print(row("소르티노 비율 (Sortino)",
              f"{metrics['sortino_ratio']:.2f}",
              f"{bm_metrics.get('sortino_ratio', 0):.2f}"))
    print(row("칼마 비율 (Calmar)",
              f"{metrics['calmar_ratio']:.2f}",
              f"{bm_metrics.get('calmar_ratio', 0):.2f}"))
    print(row("월 승률 (Win Rate)",
              f"{metrics['win_rate_monthly']:.1%}",
              f"{bm_metrics.get('win_rate_monthly', 0):.1%}"))
    print(f"  {SEP}")
    print(row("초과 연평균 (Excess CAGR)", f"{metrics['excess_cagr']:+.2%}", ""))

    # 구간별 성과
    for name, ps, pe in NOTABLE_PERIODS:
        pm = compute_period_metrics(nav_series, benchmark_nav, ps, pe)
        if pm["total_return"] == 0.0 and pm["max_drawdown"] == 0.0:
            continue
        print(f"{'─'*60}")
        print(f"  [{name}] {ps[:7]} ~ {pe[:7]}")
        print(f"    수익률 (Return): {pm['total_return']:+.1%}  vs  SPY {pm['benchmark_total_return']:+.1%}")
        print(f"    최대낙폭 (MDD):  {pm['max_drawdown']:.2%}  vs  SPY {pm['benchmark_max_drawdown']:.2%}")

    def _print_holdings_table(positions: dict, total_val: float, label: str) -> None:
        if not positions:
            return
        print(f"{'─'*60}")
        print(f"  {label}")
        print(f"  {'Symbol':<8} {'Shares':>10} {'AvgCost':>9} {'Price':>9} {'Return':>8} {'Value':>12} {'Weight':>7}")
        print(f"  {'─'*8} {'─'*10} {'─'*9} {'─'*9} {'─'*8} {'─'*12} {'─'*7}")
        sorted_pos = sorted(
            [(sym, d) for sym, d in positions.items() if sym != "_CASH"],
            key=lambda x: x[1]["value"],
            reverse=True,
        )
        for sym, d in sorted_pos:
            shares_str = f"{d['shares']:>10.2f}"
            avg_cost_str = f"${d.get('avg_cost', 0.0):>7.2f}"
            price_str = f"${d['price']:>7.2f}"
            gain_str = f"{d.get('gain_pct', 0.0):>+7.1%}"
            value_str = f"${d['value']:>10,.2f}"
            weight_str = f"{d['weight']:>6.1%}"
            print(f"  {sym:<8} {shares_str} {avg_cost_str} {price_str} {gain_str} {value_str} {weight_str}")
        if "_CASH" in positions:
            cd = positions["_CASH"]
            print(f"  {'Cash':<8} {'':>10} {'':>9} {'':>9} {'':>8} ${cd['value']:>10,.2f} {cd['weight']:>6.1%}")
        print(f"  {'─'*8} {'─'*10} {'─'*9} {'─'*9} {'─'*8} {'─'*12} {'─'*7}")
        print(f"  {'Total':<8} {'':>10} {'':>9} {'':>9} {'':>8} ${total_val:>10,.2f} {'100.0%':>7}")

    # 최종 포트폴리오 구성
    final_positions = getattr(result, "final_positions", {})
    final_benchmark_positions = getattr(result, "final_benchmark_positions", {})
    if final_positions:
        _print_holdings_table(final_positions, nav_series.iloc[-1], f"최종 포트폴리오 구성 — 전략 ({preset})")
    if final_benchmark_positions and not benchmark_nav.empty:
        _print_holdings_table(final_benchmark_positions, benchmark_nav.iloc[-1], "최종 포트폴리오 구성 — SPY B&H")

    # 매매 요약
    n_trades = len(result.trade_log)
    n_buys = sum(1 for t in result.trade_log if t.action == "BUY")
    n_sells = sum(1 for t in result.trade_log if t.action == "SELL")
    print(f"{'─'*60}")
    print(f"  매매 횟수 (Trades): 총 {n_trades}회  (매수 {n_buys} / 매도 {n_sells})")
    print(f"{'─'*60}")
    print(f"  ⚠  배당금: adj_close 기준 총수익(배당 재투자) 포함.")
    print(f"  ⚠  신호 기준: 전일(T-1) 종가 — 부분적 미래참조 보정.")
    print(f"     완전한 Point-in-Time 검증 → 워크포워드(4년 창) 사용 권장.")
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
    has_validation = "validation_status" in df.columns
    if has_validation:
        print(
            f"  {'Window':<24} {'CAGR':>7} {'Total':>7} {'MDD':>7} {'Sharpe':>7} {'Exc.CAGR':>9} {'Status':>17}"
        )
        print(f"  {'-'*24} {'-------':>7} {'-------':>7} {'-------':>7} {'-------':>7} {'---------':>9} {'-'*17:>17}")
    else:
        print(
            f"  {'Window':<24} {'CAGR':>7} {'Total':>7} {'MDD':>7} {'Sharpe':>7} {'Exc.CAGR':>9}"
        )
        print(f"  {'-'*24} {'-------':>7} {'-------':>7} {'-------':>7} {'-------':>7} {'---------':>9}")
    for _, row in df.iterrows():
        ws = str(row["window_start"])[:7] if pd.notna(row["window_start"]) else "?"
        we = str(row["window_end"])[:7] if pd.notna(row["window_end"]) else "?"
        window_label = f"{ws} ~ {we}"
        if has_validation:
            status = row.get("validation_status", "N/A")
            print(
                f"  {window_label:<24}"
                f" {row['cagr']:>+7.2%}"
                f" {row['total_return']:>+7.1%}"
                f" {row['max_drawdown']:>7.2%}"
                f" {row['sharpe_ratio']:>7.2f}"
                f" {row['excess_cagr']:>+9.2%}"
                f" {str(status):>17}"
            )
        else:
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
    if has_validation:
        status_counts = (
            df["validation_status"].value_counts(dropna=False).to_dict()
            if "validation_status" in df.columns else {}
        )
        print(f"  Validation Status Count: {status_counts}")
        print(f"  (Tier-1 성과 + Tier-2 진단 결합 결과)")
        print("")


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
        "validation_status_counts": (
            df["validation_status"].value_counts(dropna=False).to_dict()
            if "validation_status" in df.columns else {}
        ),
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
        "monthly_addition":           cfg.monthly_addition,
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
