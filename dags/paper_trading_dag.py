"""Paper Trading DAG — 미국장 개장 직후 1회 PAPER_RESULT Telegram 전송.

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
import pandas as pd
from airflow.decorators import dag, task
from pretrend.pipeline.backtest.config import BacktestConfig
from pretrend.pipeline.paper.execution import _GUARDRAIL_PANIC_WARN, simulate_paper_execution
from pretrend.pipeline.paper.report import (
    build_paper_result_payload,
    format_paper_result_message,
    save_paper_result_payload,
)
from pretrend.pipeline.paper.io import (
    load_decision_partition,
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

        cap = _resolve_paper_capital_params()
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
            schd_sell_locked=False,
            schd_min_weight=0.20,
            policy_df=policy_df,
            universe_df=universe_df,
            next_step_df=next_step_df,
            group_transition_df=group_transition_df,
            enable_predictor_gate=True,
        )

        paper_root = data_root / "paper"
        save_decision_partition(
            ledger_df,
            paper_root / "execution_ledger",
            latest,
            "execution_ledger",
            execution_mode="SIM",
        )
        save_decision_partition(
            positions_df,
            paper_root / "positions_daily",
            latest,
            "positions_daily",
            execution_mode="SIM",
        )
        save_decision_partition(
            portfolio_df,
            paper_root / "portfolio_daily",
            latest,
            "portfolio_daily",
            execution_mode="SIM",
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
                    execution_mode="SIM",
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
    def build_paper_result_payload_task(meta: Dict[str, Any]) -> Dict[str, Any]:
        data_root = Path(os.getenv("PRETREND_DATA_ROOT", "data"))
        source_job = str(meta.get("source_job", "paper_trading_dag"))
        decision_date = date.fromisoformat(str(meta.get("decision_date")))
        simulation_date = str(meta.get("simulation_date"))
        paper_start_date = str(meta.get("paper_start_date", "N/A"))

        initial_krw = float(meta.get("initial_capital_krw", 1_000_000.0))
        monthly_krw = float(meta.get("monthly_addition_krw", 300_000.0))
        fx_usdkrw = float(meta.get("fx_usdkrw", 1300.0))

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
            schd_sell_locked=False,
            virtual_fills=["exposure 스냅샷 없음"],
            daily_pnl=None,
            cumulative_pnl=None,
            position_changes=["집계 대상 데이터 없음"],
            risk_warnings=["전략 스냅샷 부재"],
            execution_mode="SIM",
            capital_source="ENV_SIM",
            broker_source="NONE",
            account_id="N/A(SIM)",
            nav_source="SIM_LEDGER",
        )

        policy_df = load_strategy_stage(data_root, "policy_selection", "trade_date")
        next_step_df = load_next_step_runtime_stage(data_root)
        group_transition_df = load_group_transition_runtime_stage(data_root)

        import pandas as pd

        pf_df = load_decision_partition(
            data_root / "paper" / "portfolio_daily",
            decision_date,
            execution_mode="SIM",
        )
        pos_df = load_decision_partition(
            data_root / "paper" / "positions_daily",
            decision_date,
            execution_mode="SIM",
        )
        ld_df = load_decision_partition(
            data_root / "paper" / "execution_ledger",
            decision_date,
            execution_mode="SIM",
        )
        if pf_df.empty:
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
                schd_sell_locked=False,
                virtual_fills=["포트폴리오 스냅샷 없음"],
                daily_pnl=None,
                cumulative_pnl=None,
                position_changes=["집계 대상 데이터 없음"],
                risk_warnings=["paper portfolio 부재"],
                execution_mode="SIM",
                capital_source="ENV_SIM",
                broker_source="NONE",
                account_id="N/A(SIM)",
                nav_source="SIM_LEDGER",
            )
        pf_row = pf_df.iloc[-1].to_dict()

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
            schd_sell_locked=False,
            virtual_fills=fills,
            daily_pnl=None if pd.isna(daily_pnl) else float(daily_pnl),
            cumulative_pnl=None if pd.isna(cumulative_pnl) else float(cumulative_pnl),
            position_changes=position_changes,
            risk_warnings=risk_warnings,
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
            broker_auth_status="N/A(SIM)",
            broker_token_refresh_count=0,
            broker_orders_count=0,
            broker_fills_count=0,
            broker_status="SKIPPED",
            execution_mode="SIM",
            capital_source="ENV_SIM",
            broker_source="NONE",
            account_id="N/A(SIM)",
            nav_source="SIM_LEDGER",
            group_gate_applied_groups=applied_groups,
            group_gate_reduced_groups=reduced_groups,
            group_gate_source=group_gate_source,
        )

    @task(task_id="send_paper_result_telegram")
    def send_paper_result_telegram_task(payload: Dict[str, Any]) -> None:
        import logging

        logger = logging.getLogger(__name__)
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

        save_paper_result_payload(payload)

        if not token or not chat_id:
            logger.info("[paper_telegram] token/chat_id not set, skip telegram send")
            return

        text = format_paper_result_message(payload)
        send_telegram_fail_open(
            token=token,
            chat_id=chat_id,
            text=text,
            source_job="paper_trading_sim",
            logger=logger,
        )

    meta = build_paper_execution_task()
    payload = build_paper_result_payload_task(meta)
    send_paper_result_telegram_task(payload)


paper_trading_dag = paper_trading_pipeline()
