"""Paper Trading DAG — 일 1회 EOD PAPER_RESULT Telegram 전송.

정책:
- 동일 Telegram 채널 사용
- message_type=PAPER_RESULT 고정
- 전송 실패는 fail-open (경고 로그 후 성공 유지)
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List

import pendulum
from airflow.decorators import dag, task
from pretrend.pipeline.backtest.config import BacktestConfig
from pretrend.pipeline.paper.execution import simulate_paper_execution
from pretrend.pipeline.paper.report import (
    build_paper_result_payload,
    format_paper_result_message,
    save_paper_result_payload,
)
from pretrend.pipeline.paper.io import (
    load_prices,
    load_strategy_stage,
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


def _list_decision_dates(exposure_root: Path) -> List[date]:
    dates: List[date] = []
    for part in exposure_root.glob("decision_date=*"):
        try:
            dates.append(date.fromisoformat(part.name.split("=", 1)[1]))
        except Exception:
            continue
    return sorted(dates)


@dag(
    dag_id="paper_trading_dag",
    description="Paper trading daily summary + Telegram PAPER_RESULT (10:30 KST)",
    default_args=DEFAULT_ARGS,
    start_date=pendulum.datetime(2026, 1, 1, tz="Asia/Seoul"),
    schedule_interval="30 10 * * *",
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

        if not decision_dates:
            return {
                "decision_date": now_kst,
                "simulation_date": now_kst,
                "source_job": source_job,
                "status": "empty_exposure",
            }

        exposure_df = load_strategy_stage(data_root, "exposure", "trade_date")
        policy_df = load_strategy_stage(data_root, "policy_selection", "trade_date")
        universe_df = load_strategy_stage(data_root, "what_to_hold", "rebalance_date")
        next_step_df = load_next_step_runtime_stage(data_root, start_date=paper_start)
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
            initial_capital=1_000_000.0,
            monthly_addition=300_000.0,
            initial_invested_ratio=0.60,
            preset_name="paper_v1",
        )

        ledger_df, positions_df, portfolio_df = simulate_paper_execution(
            config=cfg,
            exposure_df=exposure_df if exposure_df is not None else None,
            prices_df=prices_df,
            source_job=source_job,
            decision_date=latest,
            simulation_date=sim_date,
            initial_capital=1_000_000.0,
            monthly_addition=300_000.0,
            sell_tranches=[0.50, 0.30, 0.20],
            schd_sell_locked=True,
            policy_df=policy_df,
            universe_df=universe_df,
            next_step_df=next_step_df,
            enable_predictor_gate=True,
        )

        paper_root = data_root / "paper"
        save_decision_partition(ledger_df, paper_root / "execution_ledger", latest, "execution_ledger")
        save_decision_partition(positions_df, paper_root / "positions_daily", latest, "positions_daily")
        save_decision_partition(portfolio_df, paper_root / "portfolio_daily", latest, "portfolio_daily")

        return {
            "decision_date": latest.isoformat(),
            "simulation_date": now_kst,
            "source_job": source_job,
            "status": "ok",
        }

    @task(task_id="build_paper_result_payload")
    def build_paper_result_payload_task(meta: Dict[str, Any]) -> Dict[str, Any]:
        data_root = Path(os.getenv("PRETREND_DATA_ROOT", "data"))
        source_job = str(meta.get("source_job", "paper_trading_dag"))
        decision_date = date.fromisoformat(str(meta.get("decision_date")))
        simulation_date = str(meta.get("simulation_date"))

        if meta.get("status") != "ok":
            return build_paper_result_payload(
            source_job=source_job,
            decision_date=decision_date.isoformat(),
            simulation_date=simulation_date,
            action="HOLD",
            next_invested_ratio=0.0,
            delta_ratio=0.0,
            initial_capital=1_000_000.0,
            monthly_addition=300_000.0,
            buy_day_rule="월요일(T-1) 평가 후 화요일 INCREASE 실행",
            sell_day_rule="금요일 DECREASE 분할매도",
            sell_tranches=[0.50, 0.30, 0.20],
            schd_sell_locked=True,
            virtual_fills=["exposure 스냅샷 없음"],
            daily_pnl=None,
            cumulative_pnl=None,
            position_changes=["집계 대상 데이터 없음"],
            risk_warnings=["전략 스냅샷 부재"],
        )

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
                action="HOLD",
                next_invested_ratio=0.0,
                delta_ratio=0.0,
                initial_capital=1_000_000.0,
                monthly_addition=300_000.0,
                buy_day_rule="월요일(T-1) 평가 후 화요일 INCREASE 실행",
                sell_day_rule="금요일 DECREASE 분할매도",
                sell_tranches=[0.50, 0.30, 0.20],
                schd_sell_locked=True,
                virtual_fills=["포트폴리오 스냅샷 없음"],
                daily_pnl=None,
                cumulative_pnl=None,
                position_changes=["집계 대상 데이터 없음"],
                risk_warnings=["paper portfolio 부재"],
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

        return build_paper_result_payload(
            source_job=source_job,
            decision_date=decision_date.isoformat(),
            simulation_date=simulation_date,
            action=action,
            next_invested_ratio=next_ratio,
            delta_ratio=delta_ratio,
            initial_capital=1_000_000.0,
            monthly_addition=300_000.0,
            buy_day_rule="월요일(T-1) 평가 후 화요일 INCREASE 실행",
            sell_day_rule="금요일 DECREASE 분할매도",
            sell_tranches=[0.50, 0.30, 0.20],
            schd_sell_locked=True,
            virtual_fills=fills,
            daily_pnl=None if pd.isna(daily_pnl) else float(daily_pnl),
            cumulative_pnl=None if pd.isna(cumulative_pnl) else float(cumulative_pnl),
            position_changes=position_changes,
            risk_warnings=risk_warnings,
            nav=nav,
            total_invested_capital=total_capital,
            top_positions=top_positions,
        )

    @task(task_id="send_paper_result_telegram")
    def send_paper_result_telegram_task(payload: Dict[str, Any]) -> None:
        import logging

        logger = logging.getLogger(__name__)
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        save_paper_result_payload(payload)
        text = format_paper_result_message(payload)
        send_telegram_fail_open(
            token=token,
            chat_id=chat_id,
            text=text,
            source_job="paper_trading_dag",
            logger=logger,
        )

    meta = build_paper_execution_task()
    payload = build_paper_result_payload_task(meta)
    send_paper_result_telegram_task(payload)


paper_trading_dag = paper_trading_pipeline()
