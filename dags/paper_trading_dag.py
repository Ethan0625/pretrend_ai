"""Paper Trading DAG — 미국장 개장 직후 1회 PAPER_RESULT Telegram 전송.

정책:
- 동일 Telegram 채널 사용
- message_type=PAPER_RESULT 고정
- 전송 실패는 fail-open (경고 로그 후 성공 유지)
"""
from __future__ import annotations

import os
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List

import pendulum
import pandas as pd
from airflow.decorators import dag, task
from pretrend.pipeline.backtest.config import BacktestConfig
from pretrend.pipeline.paper.execution import _GUARDRAIL_PANIC_WARN, simulate_paper_execution
from pretrend.pipeline.paper.report import (
    build_paper_result_payload,
    format_paper_result_message,
    save_paper_result_payload,
)
from pretrend.pipeline.broker.kis_mock import KISMockAdapter
from pretrend.pipeline.broker.cod_reference import load_cod_reference
from pretrend.pipeline.broker.order_manager import execute_from_ledger_rows, reconcile_positions
from pretrend.pipeline.paper.io import (
    load_group_transition_runtime_stage,
    load_prices,
    load_strategy_stage,
    load_next_step_for_date,
    load_next_step_runtime_stage,
    save_decision_partition,
)
from pretrend.pipeline.notify.telegram_sender import send_telegram_fail_open


DEFAULT_ARGS: Dict[str, Any] = {
    "owner": "pretrend",
    "retries": 2,
    "retry_delay": timedelta(minutes=10),
    "depends_on_past": False,
}

def _paper_schedule_interval() -> str | None:
    """기본은 수동 실행(None), 명시적으로 켠 경우에만 ET 기준 자동 스케줄 사용."""
    enabled = os.getenv("PAPER_AUTO_SCHEDULE_ENABLED", "0").strip().lower() in {"1", "true", "yes"}
    # ET 09:40 (Mon-Fri) — 미국장 개장(09:30) 후 10분 버퍼
    return "40 9 * * 1-5" if enabled else None


def _paper_telegram_mode() -> str:
    """PAPER Telegram 발송 모드: sim|mock|compare|off."""
    mode = os.getenv("PAPER_TELEGRAM_MODE", "compare").strip().lower()
    if mode not in {"sim", "mock", "compare", "off"}:
        return "compare"
    return mode


def _as_sim_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Mock 메타를 제거한 sim 전용 표시 payload."""
    p = dict(payload)
    p["source_job"] = "paper_trading_sim"
    p["broker_auth_status"] = "N/A(SIM)"
    p["broker_token_refresh_count"] = 0
    p["broker_orders_count"] = 0
    p["broker_fills_count"] = 0
    return p


def _as_mock_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """브로커 스냅샷 기준으로 재계산한 mock 전용 표시 payload."""
    p = dict(payload)
    p["source_job"] = "paper_trading_mock"
    broker_status = str(p.get("broker_status", "UNKNOWN")).upper()
    if broker_status != "OK":
        warnings = list(p.get("risk_warnings", []))
        warnings.append("MOCK 계산 미적용(브로커 상태 비정상) — SIM 기준 유지")
        p["risk_warnings"] = warnings
        return p

    fx = p.get("broker_fx_usdkrw")
    if fx is None or (isinstance(fx, float) and pd.isna(fx)) or float(fx) <= 0:
        fx = p.get("fx_usdkrw")
    fx = None if fx is None else float(fx)

    bal_total = p.get("broker_balance_total")
    bal_cash = p.get("broker_balance_cash")
    bal_ccy = str(p.get("broker_balance_currency", "UNKNOWN")).upper()

    nav_usd = p.get("nav")
    cash_usd = None
    if bal_total is not None and not (isinstance(bal_total, float) and pd.isna(bal_total)):
        bt = float(bal_total)
        if bal_ccy == "KRW" and fx and fx > 0:
            nav_usd = bt / fx
        elif bal_ccy == "USD":
            nav_usd = bt
    if bal_cash is not None and not (isinstance(bal_cash, float) and pd.isna(bal_cash)):
        bc = float(bal_cash)
        if bal_ccy == "KRW" and fx and fx > 0:
            cash_usd = bc / fx
        elif bal_ccy == "USD":
            cash_usd = bc

    broker_positions = p.get("broker_positions") or []
    invested_usd = 0.0
    top_positions: List[Dict[str, Any]] = []
    for row in broker_positions:
        try:
            mv = row.get("market_value")
            qty = float(row.get("quantity", 0.0))
            avg = float(row.get("avg_price", 0.0))
            mp = row.get("market_price")
            mv_val = float(mv) if mv is not None else (float(mp) * qty if mp is not None else None)
            if mv_val is not None:
                invested_usd += mv_val
            top_positions.append(
                {
                    "symbol": row.get("symbol"),
                    "shares": qty,
                    "avg_cost": avg,
                    "eod_price": (None if mp is None else float(mp)),
                    "market_value": mv_val,
                    "gain_pct": None,
                }
            )
        except Exception:
            continue
    top_positions.sort(key=lambda x: float(x.get("market_value") or 0.0), reverse=True)
    top_positions = top_positions[:5]

    if nav_usd is not None and float(nav_usd) > 0:
        next_ratio = max(0.0, min(1.0, invested_usd / float(nav_usd)))
    else:
        next_ratio = float(p.get("next_invested_ratio", 0.0))

    p["nav"] = None if nav_usd is None else float(nav_usd)
    p["next_invested_ratio"] = float(next_ratio)
    p["top_positions"] = top_positions
    p["daily_pnl"] = None
    p["cumulative_pnl"] = None
    p["position_changes"] = [
        f"브로커 보유종목 {len(broker_positions)}개, 상위 {len(top_positions)}개 표시",
        f"브로커 기준 현금(USD): {cash_usd:,.2f}" if cash_usd is not None else "브로커 기준 현금(USD): N/A",
    ]
    warnings = list(p.get("risk_warnings", []))
    warnings.append("MOCK 결과는 브로커 실시간 스냅샷 기준(NAV/PnL은 당일 누적 미집계)")
    p["risk_warnings"] = warnings
    return p


def _format_compare_message(sim_payload: Dict[str, Any], mock_payload: Dict[str, Any]) -> str:
    """sim vs mock 비교 요약 (Telegram 전송용)."""
    sim_nav = sim_payload.get("nav")
    mock_nav = mock_payload.get("nav")
    sim_action = sim_payload.get("action", "HOLD")
    mock_action = mock_payload.get("action", "HOLD")
    sim_ratio = float(sim_payload.get("next_invested_ratio", 0.0))
    mock_ratio = float(mock_payload.get("next_invested_ratio", 0.0))
    sim_daily = sim_payload.get("daily_pnl")
    mock_daily = mock_payload.get("daily_pnl")
    sim_cum = sim_payload.get("cumulative_pnl")
    mock_cum = mock_payload.get("cumulative_pnl")
    orders = mock_payload.get("broker_orders_count", "N/A")
    fills = mock_payload.get("broker_fills_count", "N/A")
    auth = mock_payload.get("broker_auth_status", "UNKNOWN")
    decision_date = mock_payload.get("decision_date", "N/A")
    simulation_date = mock_payload.get("simulation_date", "N/A")

    def _pct(v: Any) -> str:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return "N/A"
        return f"{float(v):+.1%}"

    def _money(v: Any) -> str:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return "N/A"
        return f"${float(v):,.2f}"

    lines = [
        "📄 <b>Pretrend Paper Trading Compare</b>",
        "<code>message_type=PAPER_RESULT | source_job=paper_trading_compare</code>",
        f"<code>decision_date={decision_date} | simulation_date={simulation_date}</code>",
        "",
        "🔀 <b>SIM vs MOCK 요약</b>",
        f"- Action: SIM={sim_action} / MOCK={mock_action}",
        f"- Invested Ratio: SIM={sim_ratio:.0%} / MOCK={mock_ratio:.0%}",
        f"- Daily PnL: SIM={_pct(sim_daily)} / MOCK={_pct(mock_daily)}",
        f"- Cumulative PnL: SIM={_pct(sim_cum)} / MOCK={_pct(mock_cum)}",
        f"- NAV: SIM={_money(sim_nav)} / MOCK={_money(mock_nav)}",
        "",
        "🏦 <b>브로커 실행 상태</b>",
        f"- Auth: {auth}",
        f"- Orders/Fills: {orders}/{fills}",
    ]
    return "\n".join(lines)


def _list_decision_dates(exposure_root: Path) -> List[date]:
    dates: List[date] = []
    for part in exposure_root.glob("decision_date=*"):
        try:
            dates.append(date.fromisoformat(part.name.split("=", 1)[1]))
        except Exception:
            continue
    return sorted(dates)


def _resolve_paper_capital_params(fx_override: float | None = None) -> Dict[str, float]:
    """Paper 운영 입력(KRW)과 실행값(USD)을 정규화한다."""
    initial_krw = float(os.getenv("PAPER_INITIAL_CAPITAL_KRW", "1000000"))
    monthly_krw = float(os.getenv("PAPER_MONTHLY_ADDITION_KRW", "300000"))
    # PAPER_FX_USDKRW env 의존 제거:
    # - 1순위: 브로커/KIS 실시간 FX
    # - 2순위: 내부 안전 fallback(1300)
    if fx_override is not None:
        fx = float(fx_override)
    else:
        fx = 1300.0
    if fx <= 0:
        fx = 1300.0
    return {
        "initial_capital_krw": initial_krw,
        "monthly_addition_krw": monthly_krw,
        "fx_usdkrw": fx,
        "initial_capital_usd": initial_krw / fx,
        "monthly_addition_usd": monthly_krw / fx,
    }


def _resolve_live_fx_usdkrw() -> float | None:
    """Try dedicated KIS FX first, then balance response fx. Fallback is handled by caller."""
    enabled = os.getenv("PAPER_BROKER_ENABLED", "0").strip().lower() in {"1", "true", "yes"}
    dry_run = os.getenv("KIS_DRY_RUN", "true").strip().lower() in {"1", "true", "yes"}
    if not enabled or dry_run:
        return None
    try:
        adapter = KISMockAdapter.from_env()
        fx = adapter.get_usdkrw_rate()
        if fx and fx > 0:
            return float(fx)
        bal = adapter.get_balance()
        if bal.fx_usdkrw and bal.fx_usdkrw > 0:
            return float(bal.fx_usdkrw)
    except Exception:
        return None
    return None


def _save_quality_json(root: Path, decision_date: date, quality: Dict[str, Any]) -> None:
    part = root / f"decision_date={decision_date.isoformat()}"
    part.mkdir(parents=True, exist_ok=True)
    out = part / f"quality_{decision_date.strftime('%Y%m%d')}.json"
    out.write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8")


@dag(
    dag_id="paper_trading_dag",
    description="Paper trading summary + Telegram PAPER_RESULT (US/Eastern open+10m, auto optional)",
    default_args=DEFAULT_ARGS,
    start_date=pendulum.datetime(2026, 1, 1, tz="US/Eastern"),
    schedule_interval=_paper_schedule_interval(),
    catchup=False,
    max_active_runs=1,
    tags=["pretrend", "paper", "telegram"],
)
def paper_trading_pipeline():
    @task(task_id="build_paper_execution")
    def build_paper_execution_task(**context: Any) -> Dict[str, Any]:
        data_root = Path(os.getenv("PRETREND_DATA_ROOT", "data"))
        exposure_root = data_root / "strategy" / "exposure"
        decision_dates = _list_decision_dates(exposure_root)
        paper_start = date.fromisoformat(os.getenv("PAPER_START_DATE", "2026-01-01"))

        now_kst = pendulum.now("Asia/Seoul").date().isoformat()
        source_job = "paper_trading_dag"

        fx_live = _resolve_live_fx_usdkrw()
        cap = _resolve_paper_capital_params(fx_override=fx_live)
        if not decision_dates:
            return {
                "decision_date": now_kst,
                "simulation_date": now_kst,
                "source_job": source_job,
                "status": "empty_exposure",
                "paper_start_date": paper_start.isoformat(),
                **cap,
            }

        exposure_df = load_strategy_stage(data_root, "exposure", "trade_date")
        policy_df = load_strategy_stage(data_root, "policy_selection", "trade_date")
        universe_df = load_strategy_stage(data_root, "what_to_hold", "rebalance_date")
        next_step_df = load_next_step_runtime_stage(data_root, start_date=paper_start)
        group_transition_df = load_group_transition_runtime_stage(data_root, start_date=paper_start)
        prices_df = load_prices(data_root)
        if not exposure_df.empty:
            exposure_df = exposure_df[exposure_df["trade_date"] >= paper_start]
        if not policy_df.empty:
            policy_df = policy_df[policy_df["trade_date"] >= paper_start]
        if not universe_df.empty and "rebalance_date" in universe_df.columns:
            universe_df = universe_df[universe_df["rebalance_date"] >= paper_start]
        if not prices_df.empty:
            prices_df = prices_df[prices_df["trade_date"] >= paper_start]

        latest = decision_dates[-1]
        sim_date = date.fromisoformat(now_kst)
        cfg = BacktestConfig(
            start_date=min(decision_dates),
            end_date=latest,
            initial_capital=float(cap["initial_capital_usd"]),
            monthly_addition=float(cap["monthly_addition_usd"]),
            initial_invested_ratio=0.60,
            preset_name="v3.4.2a",
        )

        ledger_df, positions_df, portfolio_df, guardrail_status = simulate_paper_execution(
            config=cfg,
            exposure_df=exposure_df if exposure_df is not None else None,
            prices_df=prices_df,
            source_job=source_job,
            decision_date=latest,
            simulation_date=sim_date,
            initial_capital=float(cap["initial_capital_usd"]),
            monthly_addition=float(cap["monthly_addition_usd"]),
            sell_tranches=[0.50, 0.30, 0.20],
            schd_sell_locked=True,
            policy_df=policy_df,
            universe_df=universe_df,
            next_step_df=next_step_df,
            group_transition_df=group_transition_df,
            enable_predictor_gate=True,
        )

        paper_root = data_root / "paper"
        save_decision_partition(ledger_df, paper_root / "execution_ledger", latest, "execution_ledger")
        save_decision_partition(positions_df, paper_root / "positions_daily", latest, "positions_daily")
        save_decision_partition(portfolio_df, paper_root / "portfolio_daily", latest, "portfolio_daily")

        # Phase 1 artifacts: COD parse + ETF view + candidate report
        cod_root = data_root / "reference" / "kis_cod"
        if cod_root.exists():
            full_cod_df, etf_cod_df, cod_quality = load_cod_reference(cod_root)
            if not full_cod_df.empty:
                save_decision_partition(
                    full_cod_df,
                    data_root / "reference" / "kis_cod_parsed",
                    latest,
                    "kis_cod_parsed",
                )
            if not etf_cod_df.empty:
                save_decision_partition(
                    etf_cod_df,
                    data_root / "reference" / "kis_cod_etf",
                    latest,
                    "kis_cod_etf",
                )
            _save_quality_json(
                data_root / "reference" / "kis_cod_quality",
                latest,
                cod_quality.as_dict(),
            )

        # candidate reason report from strategy snapshots
        if not universe_df.empty:
            last_univ = universe_df.copy()
            if "rebalance_date" in last_univ.columns:
                last_univ = last_univ[last_univ["rebalance_date"] <= latest]
                if not last_univ.empty:
                    latest_reb = last_univ["rebalance_date"].max()
                    last_univ = last_univ[last_univ["rebalance_date"] == latest_reb].copy()
            if not last_univ.empty:
                p_row = policy_df[policy_df["trade_date"] <= latest].tail(1)
                n_row = next_step_df[next_step_df["trade_date"] <= latest].tail(1) if not next_step_df.empty else pd.DataFrame()
                long_phase = str(p_row["long_phase"].iloc[0]) if not p_row.empty else "UNKNOWN"
                mid_regime = str(p_row["mid_regime"].iloc[0]) if not p_row.empty else "UNKNOWN"
                short_signal = str(p_row["short_signal"].iloc[0]) if not p_row.empty else "UNKNOWN"
                bias_20d = str(n_row["bias_20d"].iloc[0]) if not n_row.empty and "bias_20d" in n_row.columns else "UNKNOWN"
                hazard_10d = (
                    float(n_row["transition_hazard_10d"].iloc[0])
                    if not n_row.empty and "transition_hazard_10d" in n_row.columns and pd.notna(n_row["transition_hazard_10d"].iloc[0])
                    else None
                )
                report_df = last_univ.copy()
                report_df["long_phase"] = long_phase
                report_df["mid_regime"] = mid_regime
                report_df["short_signal"] = short_signal
                report_df["bias_20d"] = bias_20d
                report_df["transition_hazard_10d"] = hazard_10d
                report_df["selection_reason"] = report_df.apply(
                    lambda r: (
                        f"group={r.get('asset_group','UNKNOWN')}, "
                        f"candidate={bool(r.get('is_candidate', False))}, "
                        f"rs={float(r.get('relative_strength', 0.0)):.4f}"
                    ),
                    axis=1,
                )
                save_decision_partition(
                    report_df,
                    paper_root / "candidate_report",
                    latest,
                    "candidate_report",
                )

        return {
            "decision_date": latest.isoformat(),
            "simulation_date": now_kst,
            "source_job": source_job,
            "status": "ok",
            "paper_start_date": paper_start.isoformat(),
            "guardrail_paused": guardrail_status["paused"],
            "guardrail_paused_since": guardrail_status["paused_since"],
            "guardrail_panic_streak": guardrail_status["panic_streak"],
            "guardrail_nav_breach": guardrail_status["nav_breach"],
            "guardrail_peak_dd_breach": guardrail_status["peak_dd_breach"],
            "guardrail_peak_nav": guardrail_status["peak_nav"],
            **cap,
        }

    @task(task_id="build_paper_result_payload")
    def build_paper_result_payload_task(meta: Dict[str, Any], broker_meta: Dict[str, Any]) -> Dict[str, Any]:
        data_root = Path(os.getenv("PRETREND_DATA_ROOT", "data"))
        source_job = str(meta.get("source_job", "paper_trading_dag"))
        decision_date = date.fromisoformat(str(meta.get("decision_date")))
        simulation_date = str(meta.get("simulation_date"))
        paper_start_date = str(meta.get("paper_start_date", "N/A"))

        initial_krw = float(meta.get("initial_capital_krw", 1_000_000.0))
        monthly_krw = float(meta.get("monthly_addition_krw", 300_000.0))
        fx_usdkrw = float(meta.get("fx_usdkrw", 1300.0))
        if broker_meta.get("fx_usdkrw") is not None:
            try:
                fx_usdkrw = float(broker_meta.get("fx_usdkrw"))
            except Exception:
                pass

        if meta.get("status") != "ok":
            return build_paper_result_payload(
            source_job=source_job,
            decision_date=decision_date.isoformat(),
            simulation_date=simulation_date,
            paper_start_date=paper_start_date,
            action="HOLD",
            next_invested_ratio=0.0,
            delta_ratio=0.0,
            initial_capital=initial_krw,
            monthly_addition=monthly_krw,
            fx_usdkrw=fx_usdkrw,
            buy_day_rule="월요일(T-1) 평가 후 화요일 INCREASE 실행",
            sell_day_rule="금요일 DECREASE 분할매도",
            sell_tranches=[0.50, 0.30, 0.20],
            schd_sell_locked=True,
            virtual_fills=["exposure 스냅샷 없음"],
            daily_pnl=None,
            cumulative_pnl=None,
            position_changes=["집계 대상 데이터 없음"],
            risk_warnings=["전략 스냅샷 부재"] + list(broker_meta.get("warnings", [])),
        )

        policy_df = load_strategy_stage(data_root, "policy_selection", "trade_date")
        next_step_df = load_next_step_runtime_stage(data_root)
        group_transition_df = load_group_transition_runtime_stage(data_root)

        portfolio_part = data_root / "paper" / "portfolio_daily" / f"decision_date={decision_date.isoformat()}"
        positions_part = data_root / "paper" / "positions_daily" / f"decision_date={decision_date.isoformat()}"
        ledger_part = data_root / "paper" / "execution_ledger" / f"decision_date={decision_date.isoformat()}"

        import pandas as pd

        pf_files = list(portfolio_part.glob("*.parquet"))
        pos_files = list(positions_part.glob("*.parquet"))
        ld_files = list(ledger_part.glob("*.parquet"))
        if not pf_files:
            return build_paper_result_payload(
                source_job=source_job,
                decision_date=decision_date.isoformat(),
                simulation_date=simulation_date,
                paper_start_date=paper_start_date,
                action="HOLD",
                next_invested_ratio=0.0,
                delta_ratio=0.0,
                initial_capital=initial_krw,
                monthly_addition=monthly_krw,
                fx_usdkrw=fx_usdkrw,
                buy_day_rule="월요일(T-1) 평가 후 화요일 INCREASE 실행",
                sell_day_rule="금요일 DECREASE 분할매도",
                sell_tranches=[0.50, 0.30, 0.20],
                schd_sell_locked=True,
                virtual_fills=["포트폴리오 스냅샷 없음"],
                daily_pnl=None,
                cumulative_pnl=None,
                position_changes=["집계 대상 데이터 없음"],
                risk_warnings=["paper portfolio 부재"] + list(broker_meta.get("warnings", [])),
            )

        pf_df = pd.read_parquet(pf_files[0])
        pf_row = pf_df.iloc[-1].to_dict()
        pos_df = pd.read_parquet(pos_files[0]) if pos_files else pd.DataFrame()
        ld_df = pd.read_parquet(ld_files[0]) if ld_files else pd.DataFrame()

        action = "HOLD"
        delta_ratio = 0.0
        next_ratio = 0.0
        position_changes: List[str] = []
        risk_warnings: List[str] = []
        if ld_df is not None and not ld_df.empty:
            first_action = str(ld_df["action"].iloc[0])
            action = "INCREASE" if first_action == "BUY" else ("DECREASE" if first_action == "SELL" else "HOLD")
            delta_ratio = 0.0
            fills = [f"{r['symbol']} {r['action']} ${float(r['amount']):,.2f}" for _, r in ld_df.head(10).iterrows()]
        else:
            fills = ["체결 없음 (HOLD)"]

        nav = float(pf_row.get("nav", 0.0))
        total_capital = float(pf_row.get("total_invested_capital", 0.0))
        next_ratio = (float(pf_row.get("invested_value", 0.0)) / nav) if nav > 0 else 0.0
        daily_pnl = pf_row.get("daily_pnl")
        cumulative_pnl = pf_row.get("cumulative_pnl")

        if pos_df is not None and not pos_df.empty:
            last_td = pos_df["trade_date"].max()
            day_pos = pos_df[pos_df["trade_date"] == last_td].sort_values("market_value", ascending=False)
            top = day_pos.head(5)
            top_positions = []
            for _, p in top.iterrows():
                top_positions.append(
                    {
                        "symbol": p["symbol"],
                        "shares": float(p["shares"]),
                        "avg_cost": float(p["avg_cost"]),
                        "eod_price": float(p["eod_price"]),
                        "market_value": float(p["market_value"]),
                        "gain_pct": None if pd.isna(p.get("gain_pct")) else float(p["gain_pct"]),
                    }
                )
            position_changes = [f"보유종목 {len(day_pos)}개, 상위 {len(top_positions)}개 표시"]
        else:
            top_positions = []
            position_changes = ["포지션 없음"]

        if action == "DECREASE" and any(p.get("symbol") == "SCHD" for p in top_positions):
            risk_warnings.append("SCHD 매도 금지 정책 적용 중")

        guardrail_paused = bool(meta.get("guardrail_paused", False))
        guardrail_since = meta.get("guardrail_paused_since")
        guardrail_panic = int(meta.get("guardrail_panic_streak", 0))
        guardrail_nav_breach = bool(meta.get("guardrail_nav_breach", False))
        guardrail_peak_breach = bool(meta.get("guardrail_peak_dd_breach", False))
        if guardrail_paused:
            reasons: List[str] = []
            if guardrail_nav_breach:
                reasons.append("누적투입 -15% 미달")
            if guardrail_peak_breach:
                reasons.append("ATH -20% 낙폭 초과")
            risk_warnings.append(
                f"🚨 Level 2 가드레일 발동 ({', '.join(reasons)}) — INCREASE 차단 중"
                + (f", 발동일: {guardrail_since}" if guardrail_since else "")
            )
        elif guardrail_panic >= _GUARDRAIL_PANIC_WARN:
            risk_warnings.append(f"⚠️ PANIC {guardrail_panic}거래일 연속")

        policy_row = None
        if policy_df is not None and not policy_df.empty and "trade_date" in policy_df.columns:
            x = policy_df.copy()
            x["trade_date"] = pd.to_datetime(x["trade_date"]).dt.date
            x = x[x["trade_date"] <= decision_date]
            if not x.empty:
                policy_row = x.iloc[-1]

        next_row = load_next_step_for_date(next_step_df, decision_date)
        effective_bias = str(next_row.get("bias_effective")) if next_row is not None and next_row.get("bias_effective") is not None else None
        if effective_bias is None and next_row is not None:
            effective_bias = str(next_row.get("bias_20d", "UNKNOWN"))
        hazard_10d = None
        bias_state_source = None
        bias_switch_flag = None
        bias_switch_reason = None
        bias_cooldown_left = None
        cooldown_compressed_flag = None
        cooldown_compressed_reason = None
        hard_gate_exit_assist_flag = None
        hard_gate_exit_assist_reason = None
        if next_row is not None:
            v = next_row.get("transition_hazard_10d")
            hazard_10d = None if pd.isna(v) else float(v)
            bias_state_source = next_row.get("bias_state_source")
            bias_switch_flag = next_row.get("bias_switch_flag")
            bias_switch_reason = next_row.get("bias_switch_reason")
            bias_cooldown_left = next_row.get("bias_cooldown_left")
            cooldown_compressed_flag = next_row.get("cooldown_compressed_flag")
            cooldown_compressed_reason = next_row.get("cooldown_compressed_reason")
            hard_gate_exit_assist_flag = next_row.get("hard_gate_exit_assist_flag")
            hard_gate_exit_assist_reason = next_row.get("hard_gate_exit_assist_reason")
            if str(effective_bias) == "RISK_OFF_BIAS" and bool(hard_gate_exit_assist_flag):
                effective_bias = "NEUTRAL_BIAS"
            elif (
                bool(cooldown_compressed_flag)
                and str(bias_state_source) == "HOLD_COOLDOWN"
            ):
                candidate = str(next_row.get("bias_candidate_20d", "UNKNOWN"))
                if candidate in {"RISK_ON_BIAS", "NEUTRAL_BIAS", "RISK_OFF_BIAS"}:
                    effective_bias = candidate

        group_day = pd.DataFrame()
        if group_transition_df is not None and not group_transition_df.empty and "trade_date" in group_transition_df.columns:
            g = group_transition_df.copy()
            g["trade_date"] = pd.to_datetime(g["trade_date"]).dt.date
            g = g[g["trade_date"] <= decision_date]
            if not g.empty:
                latest = g["trade_date"].max()
                group_day = g[g["trade_date"] == latest].copy()

        reduced_groups: List[str] = []
        applied_groups: List[str] = []
        if group_day is not None and not group_day.empty and "asset_group" in group_day.columns:
            all_groups = {"SECTOR", "COMMODITY", "BOND", "COUNTRY"}
            reduced_groups = sorted(
                {
                    str(r["asset_group"])
                    for _, r in group_day.iterrows()
                    if str(r.get("group_state_now", "UNKNOWN")) == "WEAK"
                }
            )
            applied_groups = sorted(list(all_groups - set(reduced_groups)))
            group_gate_source = "SNAPSHOT"
        else:
            group_gate_source = "MISSING"

        broker_warnings = list(broker_meta.get("warnings", []))
        broker_status = str(broker_meta.get("status", "unknown")).upper()
        broker_orders = int(broker_meta.get("orders_count", 0))
        broker_fills = int(broker_meta.get("fills_count", 0))
        broker_balance_cash = broker_meta.get("balance_cash")
        broker_balance_total = broker_meta.get("balance_total")
        broker_balance_currency = broker_meta.get("balance_currency")
        broker_positions = broker_meta.get("broker_positions", [])
        broker_auth_status = str(broker_meta.get("auth_status", "UNKNOWN"))
        broker_token_refresh_count = int(broker_meta.get("token_refresh_count", 0))
        if broker_meta.get("status") == "ok":
            position_changes.append(f"브로커 주문 {broker_orders}건 / 체결 {broker_fills}건")
        elif broker_meta.get("status") == "skipped":
            position_changes.append("브로커 주문 실행 비활성 (PAPER_BROKER_ENABLED=0)")
        elif broker_meta.get("status") == "failed":
            broker_warnings.append("브로커 주문 실행 실패 - paper 시뮬레이션만 유지")

        return build_paper_result_payload(
            source_job=source_job,
            decision_date=decision_date.isoformat(),
            simulation_date=simulation_date,
            paper_start_date=paper_start_date,
            action=action,
            next_invested_ratio=next_ratio,
            delta_ratio=delta_ratio,
            initial_capital=initial_krw,
            monthly_addition=monthly_krw,
            fx_usdkrw=fx_usdkrw,
            buy_day_rule="월요일(T-1) 평가 후 화요일 INCREASE 실행",
            sell_day_rule="금요일 DECREASE 분할매도",
            sell_tranches=[0.50, 0.30, 0.20],
            schd_sell_locked=True,
            virtual_fills=fills,
            daily_pnl=None if pd.isna(daily_pnl) else float(daily_pnl),
            cumulative_pnl=None if pd.isna(cumulative_pnl) else float(cumulative_pnl),
            position_changes=position_changes,
            risk_warnings=risk_warnings + broker_warnings,
            nav=nav,
            total_invested_capital=total_capital,
            top_positions=top_positions,
            effective_bias=effective_bias,
            bias_source="SNAPSHOT" if next_row is not None else "UNKNOWN",
            override_reason=(
                str(next_row.get("bias_override_reason"))
                if next_row is not None and next_row.get("bias_override_reason") is not None
                else None
            ),
            bias_state_source=(
                None if bias_state_source is None else str(bias_state_source)
            ),
            bias_switch_flag=(
                None if bias_switch_flag is None else bool(bias_switch_flag)
            ),
            bias_switch_reason=(
                None if bias_switch_reason is None else str(bias_switch_reason)
            ),
            bias_cooldown_left=(
                None if bias_cooldown_left is None or pd.isna(bias_cooldown_left)
                else int(bias_cooldown_left)
            ),
            cooldown_compressed_flag=(
                None if cooldown_compressed_flag is None else bool(cooldown_compressed_flag)
            ),
            cooldown_compressed_reason=(
                None if cooldown_compressed_reason is None else str(cooldown_compressed_reason)
            ),
            hard_gate_exit_assist_flag=(
                None if hard_gate_exit_assist_flag is None else bool(hard_gate_exit_assist_flag)
            ),
            hard_gate_exit_assist_reason=(
                None if hard_gate_exit_assist_reason is None else str(hard_gate_exit_assist_reason)
            ),
            hard_gate_run_universe=(
                None if policy_row is None else bool(policy_row.get("run_universe", True))
            ),
            hard_gate_risk_gate=(
                None if policy_row is None else bool(policy_row.get("risk_gate", True))
            ),
            effective_max_tactical_slots=(
                2 if effective_bias == "RISK_ON_BIAS"
                else 1 if effective_bias in {"NEUTRAL_BIAS", "UNKNOWN", None}
                else 0
            ),
            effective_tactical_weight=(
                0.30 if effective_bias == "RISK_ON_BIAS"
                else 0.225 if effective_bias in {"NEUTRAL_BIAS", "UNKNOWN", None}
                else 0.0
            ),
            hazard_10d=hazard_10d,
            broker_auth_status=broker_auth_status,
            broker_token_refresh_count=broker_token_refresh_count,
            broker_orders_count=broker_orders,
            broker_fills_count=broker_fills,
            broker_status=broker_status,
            broker_balance_cash=broker_balance_cash,
            broker_balance_total=broker_balance_total,
            broker_balance_currency=broker_balance_currency,
            broker_positions=broker_positions,
            broker_fx_usdkrw=broker_meta.get("fx_usdkrw"),
            group_gate_applied_groups=applied_groups,
            group_gate_reduced_groups=reduced_groups,
            group_gate_source=group_gate_source,
        )

    @task(task_id="execute_broker_orders")
    def execute_broker_orders_task(meta: Dict[str, Any]) -> Dict[str, Any]:
        import logging
        import pandas as pd

        logger = logging.getLogger(__name__)
        enabled = os.getenv("PAPER_BROKER_ENABLED", "0").strip().lower() in {"1", "true", "yes"}
        if not enabled:
            return {"status": "skipped", "warnings": []}
        if meta.get("status") != "ok":
            return {"status": "skipped", "warnings": ["paper 실행 결과 없음 - broker 생략"]}

        decision_date = date.fromisoformat(str(meta.get("decision_date")))
        simulation_date = date.fromisoformat(str(meta.get("simulation_date")))
        data_root = Path(os.getenv("PRETREND_DATA_ROOT", "data"))
        paper_root = data_root / "paper"
        source_job = str(meta.get("source_job", "paper_trading_dag"))

        ledger_part = data_root / "paper" / "execution_ledger" / f"decision_date={decision_date.isoformat()}"
        positions_part = data_root / "paper" / "positions_daily" / f"decision_date={decision_date.isoformat()}"
        ld_files = list(ledger_part.glob("*.parquet"))
        pos_files = list(positions_part.glob("*.parquet"))
        if not ld_files:
            return {"status": "skipped", "warnings": ["execution_ledger 없음 - broker 실행 생략"]}

        ld_df = pd.read_parquet(ld_files[0])
        pos_df = pd.read_parquet(pos_files[0]) if pos_files else pd.DataFrame()

        try:
            adapter = KISMockAdapter.from_env()
            # bootstrap checks (token + balance + positions)
            balance = adapter.get_balance()
            broker_positions = adapter.get_positions()
            bootstrap_df = pd.DataFrame(
                [
                    {
                        "decision_date": decision_date,
                        "simulation_date": simulation_date,
                        "source_job": source_job,
                        "token_ok": True,
                        "balance_ok": True,
                        "positions_ok": True,
                        "cash": balance.cash,
                        "total_value": balance.total_value,
                        "currency": balance.currency,
                        "fx_usdkrw": balance.fx_usdkrw,
                    }
                ]
            )
            probe_rows: List[Dict[str, Any]] = []
            for sym in sorted({str(s).upper() for s in ld_df.get("symbol", pd.Series(dtype=str)).head(20).tolist() if str(s).strip()}):
                price_ok = False
                quote_ok = False
                last_price = None
                orderable_usd = None
                orderable_overseas_amt = None
                orderable_krw_amt = None
                orderable_ccy = None
                orderable_exrt = None
                orderable_status_code = None
                orderable_rt_cd = None
                orderable_msg_cd = None
                orderable_msg1 = None
                orderable_error = None
                error_code = None
                try:
                    last_price = float(adapter.get_current_price(sym))
                    price_ok = last_price > 0
                    quote_ok = price_ok
                    try:
                        info = adapter.get_orderable_info(sym, exchange_code="NASD", order_price=last_price if last_price > 0 else None)
                        orderable_ccy = info.get("tr_crcy_cd")
                        orderable_exrt = info.get("exrt")
                        orderable_usd = info.get("ord_psbl_frcr_amt")
                        if orderable_usd is None:
                            orderable_usd = info.get("frcr_ord_psbl_amt1")
                        orderable_overseas_amt = info.get("ovrs_ord_psbl_amt")
                        orderable_krw_amt = info.get("ord_psbl_amt")
                        orderable_status_code = info.get("status_code")
                        orderable_rt_cd = info.get("rt_cd")
                        orderable_msg_cd = info.get("msg_cd")
                        orderable_msg1 = info.get("msg1")
                        orderable_error = info.get("error")
                    except Exception:
                        orderable_usd = None
                except Exception as exc:
                    error_code = str(exc)
                probe_rows.append(
                    {
                        "decision_date": decision_date,
                        "simulation_date": simulation_date,
                        "source_job": source_job,
                        "symbol": sym,
                        "price_ok": price_ok,
                        "quote_ok": quote_ok,
                        "last_price": last_price,
                        "orderable_usd": orderable_usd,
                        "orderable_overseas_amt": orderable_overseas_amt,
                        "orderable_krw_amt": orderable_krw_amt,
                        "orderable_ccy": orderable_ccy,
                        "orderable_exrt": orderable_exrt,
                        "orderable_status_code": orderable_status_code,
                        "orderable_rt_cd": orderable_rt_cd,
                        "orderable_msg_cd": orderable_msg_cd,
                        "orderable_msg1": orderable_msg1,
                        "orderable_error": orderable_error,
                        "orderable_available": bool(
                            (orderable_usd is not None and float(orderable_usd) > 0)
                            or (orderable_overseas_amt is not None and float(orderable_overseas_amt) > 0)
                            or (orderable_krw_amt is not None and float(orderable_krw_amt) > 0)
                        ),
                        "spread": None,
                        "error_code": error_code,
                    }
                )
            probe_df = pd.DataFrame(probe_rows)
            # Merge probe diagnostics into candidate report to explain "why selected / can we trade now".
            candidate_part = data_root / "paper" / "candidate_report" / f"decision_date={decision_date.isoformat()}"
            candidate_files = list(candidate_part.glob("*.parquet"))
            if candidate_files and not probe_df.empty:
                cand_df = pd.read_parquet(candidate_files[0])
                if "symbol" in cand_df.columns:
                    merged = cand_df.merge(
                        probe_df[
                            [
                                "symbol",
                                "last_price",
                                "orderable_available",
                                "orderable_usd",
                                "orderable_overseas_amt",
                                "orderable_krw_amt",
                                "orderable_ccy",
                                "orderable_exrt",
                                "orderable_status_code",
                                "orderable_rt_cd",
                                "orderable_msg_cd",
                                "orderable_msg1",
                                "orderable_error",
                            ]
                        ],
                        on="symbol",
                        how="left",
                    )
                    save_decision_partition(
                        merged,
                        paper_root / "candidate_report",
                        decision_date,
                        "candidate_report",
                    )
            orders_df, fills_df, warnings = execute_from_ledger_rows(
                adapter,
                ledger_df=ld_df.head(20),
                decision_date=decision_date,
                simulation_date=simulation_date,
                source_job=source_job,
            )
            broker_positions = adapter.get_positions()
            recon_df = reconcile_positions(
                broker_positions=broker_positions,
                paper_positions_df=pos_df,
                decision_date=decision_date,
                source_job=source_job,
            )
            auth_meta = adapter.auth_status()
            auth_df = pd.DataFrame(
                [
                    {
                        "decision_date": decision_date,
                        "simulation_date": simulation_date,
                        "source_job": source_job,
                        "token_refresh_count": auth_meta.get("token_refresh_count", 0),
                        "last_refresh_at": auth_meta.get("last_refresh_at"),
                        "auth_status": auth_meta.get("auth_status", "UNKNOWN"),
                        "error_code": auth_meta.get("error_code"),
                    }
                ]
            )
            fx_df = pd.DataFrame(
                [
                    {
                        "decision_date": decision_date,
                        "simulation_date": simulation_date,
                        "source_job": source_job,
                        "fx_usdkrw": balance.fx_usdkrw,
                        "fx_source": "KIS_BALANCE",
                    }
                ]
            )
        except Exception as exc:
            logger.warning("broker execution failed: %s", exc)
            return {"status": "failed", "warnings": [f"broker execution failed: {exc}"]}

        save_decision_partition(bootstrap_df, paper_root / "broker_bootstrap", decision_date, "broker_bootstrap")
        save_decision_partition(auth_df, paper_root / "broker_auth", decision_date, "broker_auth")
        save_decision_partition(fx_df, paper_root / "fx_daily", decision_date, "fx_daily")
        save_decision_partition(probe_df, paper_root / "market_probe", decision_date, "market_probe")
        save_decision_partition(orders_df, paper_root / "broker_orders", decision_date, "broker_orders")
        save_decision_partition(fills_df, paper_root / "broker_fills", decision_date, "broker_fills")
        save_decision_partition(recon_df, paper_root / "reconciliation", decision_date, "reconciliation")

        return {
            "status": "ok",
            "orders_count": int(len(orders_df)),
            "fills_count": int(len(fills_df)),
            "balance_cash": float(balance.cash),
            "balance_total": float(balance.total_value),
            "balance_currency": str(balance.currency),
            "positions_count": int(len(broker_positions)),
            "broker_positions": [
                {
                    "symbol": bp.symbol,
                    "quantity": float(bp.quantity),
                    "avg_price": float(bp.avg_price),
                    "market_price": (None if bp.market_price is None else float(bp.market_price)),
                    "market_value": (None if bp.market_value is None else float(bp.market_value)),
                }
                for bp in broker_positions
            ],
            "auth_status": str(auth_df["auth_status"].iloc[0]) if not auth_df.empty else "UNKNOWN",
            "token_refresh_count": int(auth_df["token_refresh_count"].iloc[0]) if not auth_df.empty else 0,
            "fx_usdkrw": (
                float(fx_df["fx_usdkrw"].iloc[0])
                if not fx_df.empty and pd.notna(fx_df["fx_usdkrw"].iloc[0])
                else None
            ),
            "warnings": warnings,
        }

    @task(task_id="send_paper_result_telegram")
    def send_paper_result_telegram_task(payload: Dict[str, Any]) -> None:
        import logging

        logger = logging.getLogger(__name__)
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        mode = _paper_telegram_mode()
        sim_payload = _as_sim_payload(payload)
        mock_payload = _as_mock_payload(payload)

        # 실행/저장은 sim+mock 모두 수행
        save_paper_result_payload(sim_payload)
        save_paper_result_payload(mock_payload)

        if mode == "off":
            logger.info("[paper_telegram] mode=off, skip telegram send")
            return

        if mode == "sim":
            text = format_paper_result_message(sim_payload)
            source_job = "paper_trading_sim"
        elif mode == "mock":
            text = format_paper_result_message(mock_payload)
            source_job = "paper_trading_mock"
        else:  # compare -> 3 messages
            compare_text = _format_compare_message(sim_payload, mock_payload)
            sim_text = format_paper_result_message(sim_payload)
            mock_text = format_paper_result_message(mock_payload)

            send_telegram_fail_open(
                token=token,
                chat_id=chat_id,
                text=compare_text,
                source_job="paper_trading_compare",
                logger=logger,
            )
            send_telegram_fail_open(
                token=token,
                chat_id=chat_id,
                text=sim_text,
                source_job="paper_trading_sim",
                logger=logger,
            )
            send_telegram_fail_open(
                token=token,
                chat_id=chat_id,
                text=mock_text,
                source_job="paper_trading_mock",
                logger=logger,
            )
            return

        send_telegram_fail_open(
            token=token,
            chat_id=chat_id,
            text=text,
            source_job=source_job,
            logger=logger,
        )

    meta = build_paper_execution_task()
    broker_meta = execute_broker_orders_task(meta)
    payload = build_paper_result_payload_task(meta, broker_meta)
    send_paper_result_telegram_task(payload)


paper_trading_dag = paper_trading_pipeline()
