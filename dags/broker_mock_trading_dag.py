"""Broker Mock Trading DAG — KIS mock API 연동 주문 실행 및 MOCK Telegram 전송.

정책:
- paper_trading_dag의 SIM execution_ledger를 입력으로 받음
- KIS mock API 연동으로 실제 주문 인프라 검증
- 전송 실패는 fail-open (경고 로그 후 성공 유지)
- 수동 트리거 전용 (BROKER_MOCK_AUTO_SCHEDULE_ENABLED=1 시 ET 09:40 자동)
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
from pretrend.pipeline.broker.kis_mock import KISMockAdapter
from pretrend.pipeline.broker.cod_reference import load_cod_reference
from pretrend.pipeline.broker.order_manager import (
    check_and_cancel_unfilled,
    execute_from_ledger_rows,
    reconcile_positions,
)
from pretrend.pipeline.paper.report import (
    build_paper_result_payload,
    format_paper_result_message,
    save_paper_result_payload,
)
from pretrend.pipeline.paper.io import (
    load_decision_partition,
    load_group_transition_runtime_stage,
    load_next_step_for_date,
    load_next_step_runtime_stage,
    load_strategy_stage,
    save_decision_partition,
)
from pretrend.pipeline.notify.telegram_sender import send_telegram_fail_open


DEFAULT_ARGS: Dict[str, Any] = {
    "owner": "pretrend",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "depends_on_past": False,
}


def _broker_schedule_interval() -> str | None:
    """기본은 수동 실행(None), 명시적으로 켠 경우에만 ET 기준 자동 스케줄 사용."""
    enabled = os.getenv("BROKER_MOCK_AUTO_SCHEDULE_ENABLED", "0").strip().lower() in {"1", "true", "yes"}
    return "40 9 * * 1-5" if enabled else None


def _resolve_broker_source() -> str:
    is_mock = os.getenv("KIS_IS_MOCK", "true").strip().lower() in {"1", "true", "yes"}
    return "KIS_MOCK" if is_mock else "KIS_LIVE"


def _resolve_account_id() -> str:
    is_mock = os.getenv("KIS_IS_MOCK", "true").strip().lower() in {"1", "true", "yes"}
    if is_mock:
        acc = str(os.getenv("KIS_MOCK_ACCOUNT_NO", "")).strip()
        prd = str(os.getenv("KIS_MOCK_PRODUCT_CODE", "")).strip()
    else:
        acc = str(os.getenv("KIS_LIVE_ACCOUNT_NO", "")).strip()
        prd = str(os.getenv("KIS_LIVE_PRODUCT_CODE", "")).strip()
    if not acc:
        acc = str(os.getenv("KIS_ACCOUNT_NO", "")).strip()
    if not prd:
        prd = str(os.getenv("KIS_ACCOUNT_PRODUCT", "")).strip()
    if not acc:
        return "UNKNOWN"
    if len(acc) <= 4:
        masked = "*" * len(acc)
    else:
        masked = "*" * (len(acc) - 4) + acc[-4:]
    return f"{masked}-{prd}" if prd else masked


def _save_quality_json(root: Path, decision_date: date, quality: Dict[str, Any]) -> None:
    part = root / f"decision_date={decision_date.isoformat()}"
    part.mkdir(parents=True, exist_ok=True)
    out = part / f"quality_{decision_date.strftime('%Y%m%d')}.json"
    out.write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8")


def _list_sim_decision_dates(paper_root: Path) -> List[date]:
    ledger_root = paper_root / "execution_ledger"
    dates: List[date] = []
    if not ledger_root.exists():
        return dates
    for part in ledger_root.glob("decision_date=*"):
        sim_part = part / "execution_mode=SIM"
        if not sim_part.exists():
            # also accept flat layout without execution_mode subdir
            if any(part.glob("*.parquet")):
                try:
                    dates.append(date.fromisoformat(part.name.split("=", 1)[1]))
                except Exception:
                    continue
            continue
        if any(sim_part.glob("*.parquet")):
            try:
                dates.append(date.fromisoformat(part.name.split("=", 1)[1]))
            except Exception:
                continue
    return sorted(dates)


@dag(
    dag_id="broker_mock_trading_dag",
    description="KIS mock broker order execution + MOCK Telegram (manual trigger)",
    default_args=DEFAULT_ARGS,
    start_date=pendulum.datetime(2026, 1, 1, tz="US/Eastern"),
    schedule_interval=_broker_schedule_interval(),
    catchup=False,
    max_active_runs=1,
    tags=["pretrend", "broker", "mock", "telegram"],
)
def broker_mock_trading_pipeline():
    @task(task_id="load_sim_ledger")
    def load_sim_ledger_task(**context: Any) -> Dict[str, Any]:
        data_root = Path(os.getenv("PRETREND_DATA_ROOT", "data"))
        paper_root = data_root / "paper"

        decision_dates = _list_sim_decision_dates(paper_root)
        if not decision_dates:
            return {
                "status": "skipped",
                "reason": "SIM execution_ledger 없음",
                "decision_date": date.today().isoformat(),
            }

        decision_date = decision_dates[-1]
        ld_df = load_decision_partition(
            paper_root / "execution_ledger",
            decision_date,
            execution_mode="SIM",
        )
        if ld_df is None or ld_df.empty:
            return {
                "status": "skipped",
                "reason": f"execution_ledger 비어있음 (decision_date={decision_date})",
                "decision_date": decision_date.isoformat(),
            }

        now_kst = pendulum.now("Asia/Seoul").date().isoformat()
        return {
            "status": "ok",
            "decision_date": decision_date.isoformat(),
            "simulation_date": now_kst,
            "source_job": "broker_mock_trading_dag",
            "ledger_rows": len(ld_df),
        }

    @task(task_id="execute_broker_orders")
    def execute_broker_orders_task(ledger_meta: Dict[str, Any]) -> Dict[str, Any]:
        import logging

        logger = logging.getLogger(__name__)
        if ledger_meta.get("status") != "ok":
            return {"status": "skipped", "warnings": [ledger_meta.get("reason", "ledger 없음")]}

        decision_date = date.fromisoformat(str(ledger_meta.get("decision_date")))
        simulation_date = date.fromisoformat(str(ledger_meta.get("simulation_date")))
        data_root = Path(os.getenv("PRETREND_DATA_ROOT", "data"))
        paper_root = data_root / "paper"
        source_job = str(ledger_meta.get("source_job", "broker_mock_trading_dag"))

        try:
            adapter = KISMockAdapter.from_env()
            balance = adapter.get_balance()
            broker_positions = adapter.get_positions()

            ld_df = load_decision_partition(
                paper_root / "execution_ledger",
                decision_date,
                execution_mode="SIM",
            )
            pos_df = load_decision_partition(
                paper_root / "positions_daily",
                decision_date,
                execution_mode="SIM",
            )

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

            # COD reference parse (broker-side ETF tradability lookup)
            cod_root = data_root / "reference" / "kis_cod"
            if cod_root.exists():
                full_cod_df, etf_cod_df, cod_quality = load_cod_reference(cod_root)
                if not full_cod_df.empty:
                    save_decision_partition(
                        full_cod_df,
                        data_root / "reference" / "kis_cod_parsed",
                        decision_date,
                        "kis_cod_parsed",
                    )
                if not etf_cod_df.empty:
                    save_decision_partition(
                        etf_cod_df,
                        data_root / "reference" / "kis_cod_etf",
                        decision_date,
                        "kis_cod_etf",
                    )
                _save_quality_json(
                    data_root / "reference" / "kis_cod_quality",
                    decision_date,
                    cod_quality.as_dict(),
                )

            # Market probe: price + orderable info per symbol in ledger
            probe_rows: List[Dict[str, Any]] = []
            symbols = sorted({str(s).upper() for s in ld_df.get("symbol", pd.Series(dtype=str)).head(20).tolist() if str(s).strip()})
            for sym in symbols:
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

            # Merge probe into candidate_report if available
            cand_df = load_decision_partition(
                paper_root / "candidate_report",
                decision_date,
                execution_mode="SIM",
            )
            if not cand_df.empty and not probe_df.empty and "symbol" in cand_df.columns:
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
                    execution_mode="SIM",
                )

            # Execute broker orders from SIM ledger
            if ld_df.empty:
                orders_df = pd.DataFrame()
                fills_df = pd.DataFrame()
                cancelled_df = pd.DataFrame()
                warnings: List[str] = ["execution_ledger 없음 - broker 주문 생략(잔고/인증 조회는 수행)"]
            else:
                orders_df, fills_df, warnings = execute_from_ledger_rows(
                    adapter,
                    ledger_df=ld_df.head(20),
                    decision_date=decision_date,
                    simulation_date=simulation_date,
                    source_job=source_job,
                )
                fill_wait_sec = int(os.getenv("BROKER_FILL_WAIT_SEC", "30"))
                cancelled_df, cancel_warnings = check_and_cancel_unfilled(
                    adapter,
                    orders_df,
                    wait_sec=fill_wait_sec,
                )
                warnings += cancel_warnings

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

        save_decision_partition(
            bootstrap_df,
            paper_root / "broker_bootstrap",
            decision_date,
            "broker_bootstrap",
            execution_mode="MOCK",
        )
        save_decision_partition(
            auth_df,
            paper_root / "broker_auth",
            decision_date,
            "broker_auth",
            execution_mode="MOCK",
        )
        save_decision_partition(
            fx_df,
            paper_root / "fx_daily",
            decision_date,
            "fx_daily",
            execution_mode="MOCK",
        )
        save_decision_partition(
            probe_df,
            paper_root / "market_probe",
            decision_date,
            "market_probe",
            execution_mode="MOCK",
        )
        save_decision_partition(
            orders_df,
            paper_root / "broker_orders",
            decision_date,
            "broker_orders",
            execution_mode="MOCK",
        )
        save_decision_partition(
            fills_df,
            paper_root / "broker_fills",
            decision_date,
            "broker_fills",
            execution_mode="MOCK",
        )
        save_decision_partition(
            recon_df,
            paper_root / "reconciliation",
            decision_date,
            "reconciliation",
            execution_mode="MOCK",
        )
        save_decision_partition(
            cancelled_df,
            paper_root / "broker_cancelled",
            decision_date,
            "broker_cancelled",
            execution_mode="MOCK",
        )

        return {
            "status": "ok",
            "decision_date": decision_date.isoformat(),
            "simulation_date": simulation_date.isoformat(),
            "source_job": source_job,
            "orders_count": int(len(orders_df)),
            "fills_count": int(len(fills_df)),
            "cancelled_count": int(len(cancelled_df)),
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

    @task(task_id="build_broker_result_payload")
    def build_broker_result_payload_task(
        ledger_meta: Dict[str, Any], broker_meta: Dict[str, Any]
    ) -> Dict[str, Any]:
        import logging

        logger = logging.getLogger(__name__)
        data_root = Path(os.getenv("PRETREND_DATA_ROOT", "data"))

        if broker_meta.get("status") != "ok":
            decision_date_str = str(ledger_meta.get("decision_date", date.today().isoformat()))
            simulation_date_str = str(ledger_meta.get("simulation_date", date.today().isoformat()))
            warnings = list(broker_meta.get("warnings", []))
            return build_paper_result_payload(
                source_job="broker_mock_trading_dag",
                decision_date=decision_date_str,
                simulation_date=simulation_date_str,
                paper_start_date="N/A",
                action="HOLD",
                next_invested_ratio=0.0,
                delta_ratio=0.0,
                initial_capital=float(os.getenv("PAPER_INITIAL_CAPITAL_KRW", "1000000")) / 1300.0,
                monthly_addition=float(os.getenv("PAPER_MONTHLY_ADDITION_KRW", "300000")) / 1300.0,
                fx_usdkrw=1300.0,
                buy_day_rule="월요일(T-1) 평가 후 화요일 INCREASE 실행",
                sell_day_rule="금요일 DECREASE 분할매도",
                sell_tranches=[0.50, 0.30, 0.20],
                schd_sell_locked=True,
                virtual_fills=["브로커 주문 실행 실패 또는 생략"],
                daily_pnl=None,
                cumulative_pnl=None,
                position_changes=["브로커 주문 미실행"],
                risk_warnings=warnings,
                execution_mode="MOCK",
                capital_source="BROKER_UNAVAILABLE",
                broker_source=_resolve_broker_source(),
                account_id=_resolve_account_id(),
                nav_source="BROKER_UNAVAILABLE",
                broker_status=str(broker_meta.get("status", "unknown")).upper(),
                broker_auth_status=str(broker_meta.get("auth_status", "UNKNOWN")),
                broker_token_refresh_count=0,
                broker_orders_count=0,
                broker_fills_count=0,
            )

        decision_date = date.fromisoformat(str(broker_meta.get("decision_date")))
        simulation_date = str(broker_meta.get("simulation_date"))
        source_job = str(broker_meta.get("source_job", "broker_mock_trading_dag"))

        fx_usdkrw = broker_meta.get("fx_usdkrw")
        if fx_usdkrw is None or float(fx_usdkrw) <= 0:
            fx_usdkrw = 1300.0
        fx_usdkrw = float(fx_usdkrw)

        initial_krw = float(os.getenv("PAPER_INITIAL_CAPITAL_KRW", "1000000"))
        monthly_krw = float(os.getenv("PAPER_MONTHLY_ADDITION_KRW", "300000"))

        ld_df = load_decision_partition(
            data_root / "paper" / "execution_ledger",
            decision_date,
            execution_mode="SIM",
        )
        next_step_df = load_next_step_runtime_stage(data_root)
        group_transition_df = load_group_transition_runtime_stage(data_root)
        policy_df = load_strategy_stage(data_root, "policy_selection", "trade_date")

        # action from SIM ledger
        action = "HOLD"
        fills: List[str] = ["체결 없음 (HOLD)"]
        if ld_df is not None and not ld_df.empty:
            first_action = str(ld_df["action"].iloc[0])
            action = "INCREASE" if first_action == "BUY" else ("DECREASE" if first_action == "SELL" else "HOLD")
            fills = [f"{r['symbol']} {r['action']} ${float(r['amount']):,.2f}" for _, r in ld_df.head(10).iterrows()]

        # broker NAV from balance
        bal_total = broker_meta.get("balance_total")
        bal_cash = broker_meta.get("balance_cash")
        bal_ccy = str(broker_meta.get("balance_currency", "UNKNOWN")).upper()
        nav_usd = None
        cash_usd = None
        if bal_total is not None:
            bt = float(bal_total)
            if bal_ccy == "KRW" and fx_usdkrw > 0:
                nav_usd = bt / fx_usdkrw
            elif bal_ccy == "USD":
                nav_usd = bt
        if bal_cash is not None:
            bc = float(bal_cash)
            if bal_ccy == "KRW" and fx_usdkrw > 0:
                cash_usd = bc / fx_usdkrw
            elif bal_ccy == "USD":
                cash_usd = bc
        if (cash_usd is None or cash_usd <= 0) and nav_usd is not None:
            cash_usd = nav_usd  # fallback: treat total as cash baseline

        broker_raw_positions = broker_meta.get("broker_positions", [])
        invested_usd = 0.0
        top_positions: List[Dict[str, Any]] = []
        for row in broker_raw_positions:
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
            next_ratio = 0.0

        position_changes = [
            f"브로커 보유종목 {len(broker_raw_positions)}개, 상위 {len(top_positions)}개 표시",
            f"브로커 기준 현금(USD): {cash_usd:,.2f}" if cash_usd is not None else "브로커 기준 현금(USD): N/A",
            f"브로커 주문 {broker_meta.get('orders_count', 0)}건 / 체결 {broker_meta.get('fills_count', 0)}건",
        ]
        risk_warnings = list(broker_meta.get("warnings", []))
        risk_warnings.append("MOCK 결과는 브로커 실시간 스냅샷 기준(NAV/PnL은 당일 누적 미집계)")

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

        policy_row = None
        if policy_df is not None and not policy_df.empty and "trade_date" in policy_df.columns:
            x = policy_df.copy()
            x["trade_date"] = pd.to_datetime(x["trade_date"]).dt.date
            x = x[x["trade_date"] <= decision_date]
            if not x.empty:
                policy_row = x.iloc[-1]

        return build_paper_result_payload(
            source_job=source_job,
            decision_date=decision_date.isoformat(),
            simulation_date=simulation_date,
            paper_start_date="N/A",
            action=action,
            next_invested_ratio=next_ratio,
            delta_ratio=0.0,
            initial_capital=initial_krw / fx_usdkrw,
            monthly_addition=monthly_krw / fx_usdkrw,
            fx_usdkrw=fx_usdkrw,
            buy_day_rule="월요일(T-1) 평가 후 화요일 INCREASE 실행",
            sell_day_rule="금요일 DECREASE 분할매도",
            sell_tranches=[0.50, 0.30, 0.20],
            schd_sell_locked=True,
            virtual_fills=fills,
            daily_pnl=None,
            cumulative_pnl=None,
            position_changes=position_changes,
            risk_warnings=risk_warnings,
            nav=nav_usd,
            total_invested_capital=None,
            top_positions=top_positions,
            effective_bias=effective_bias,
            bias_source="SNAPSHOT" if next_row is not None else "UNKNOWN",
            override_reason=(
                str(next_row.get("bias_override_reason"))
                if next_row is not None and next_row.get("bias_override_reason") is not None
                else None
            ),
            bias_state_source=(None if bias_state_source is None else str(bias_state_source)),
            bias_switch_flag=(None if bias_switch_flag is None else bool(bias_switch_flag)),
            bias_switch_reason=(None if bias_switch_reason is None else str(bias_switch_reason)),
            bias_cooldown_left=(
                None if bias_cooldown_left is None or pd.isna(bias_cooldown_left)
                else int(bias_cooldown_left)
            ),
            cooldown_compressed_flag=(None if cooldown_compressed_flag is None else bool(cooldown_compressed_flag)),
            cooldown_compressed_reason=(None if cooldown_compressed_reason is None else str(cooldown_compressed_reason)),
            hard_gate_exit_assist_flag=(None if hard_gate_exit_assist_flag is None else bool(hard_gate_exit_assist_flag)),
            hard_gate_exit_assist_reason=(None if hard_gate_exit_assist_reason is None else str(hard_gate_exit_assist_reason)),
            hard_gate_run_universe=(None if policy_row is None else bool(policy_row.get("run_universe", True))),
            hard_gate_risk_gate=(None if policy_row is None else bool(policy_row.get("risk_gate", True))),
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
            broker_auth_status=str(broker_meta.get("auth_status", "UNKNOWN")),
            broker_token_refresh_count=int(broker_meta.get("token_refresh_count", 0)),
            broker_orders_count=int(broker_meta.get("orders_count", 0)),
            broker_fills_count=int(broker_meta.get("fills_count", 0)),
            broker_status="OK",
            execution_mode="MOCK",
            capital_source="BROKER_BALANCE",
            broker_source=_resolve_broker_source(),
            account_id=_resolve_account_id(),
            nav_source="BROKER_SNAPSHOT",
            broker_balance_cash=broker_meta.get("balance_cash"),
            broker_balance_total=broker_meta.get("balance_total"),
            broker_balance_currency=broker_meta.get("balance_currency"),
            broker_positions=broker_raw_positions,
            broker_fx_usdkrw=broker_meta.get("fx_usdkrw"),
            group_gate_applied_groups=applied_groups,
            group_gate_reduced_groups=reduced_groups,
            group_gate_source=group_gate_source,
        )

    @task(task_id="send_broker_telegram")
    def send_broker_telegram_task(payload: Dict[str, Any]) -> None:
        import logging

        logger = logging.getLogger(__name__)
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

        save_paper_result_payload(payload)

        if not token or not chat_id:
            logger.info("[broker_telegram] token/chat_id not set, skip telegram send")
            return

        text = format_paper_result_message(payload)
        send_telegram_fail_open(
            token=token,
            chat_id=chat_id,
            text=text,
            source_job="broker_mock_trading_dag",
            logger=logger,
        )

    ledger_meta = load_sim_ledger_task()
    broker_meta = execute_broker_orders_task(ledger_meta)
    payload = build_broker_result_payload_task(ledger_meta, broker_meta)
    send_broker_telegram_task(payload)


broker_mock_trading_dag = broker_mock_trading_pipeline()
