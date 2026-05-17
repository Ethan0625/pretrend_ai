"""Broker Mock Trading DAG — KIS mock API 연동 주문 실행 및 MOCK Telegram 전송.

정책:
- strategy stages + broker state 기준으로 독립 주문 계획을 계산함
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
from pretrend.pipeline.broker.execution_planner import build_broker_target_orders
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

_ET_TZ = pendulum.timezone("America/New_York")


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


def _should_skip_market_hours(now_et: pendulum.DateTime | None = None) -> tuple[bool, str | None, bool]:
    """Return (should_skip, reason, bypassed) for broker mock execution."""
    bypass = os.getenv("BROKER_SKIP_MARKET_HOURS_CHECK", "0").strip().lower() in {"1", "true", "yes"}
    if bypass:
        return False, None, True

    current = now_et or pendulum.now(_ET_TZ)
    current = current.in_timezone(_ET_TZ)

    if current.day_of_week >= 5:
        return True, "장외 시간", False

    market_open = current.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = current.replace(hour=16, minute=0, second=0, microsecond=0)
    if current < market_open or current > market_close:
        return True, "장외 시간", False
    return False, None, False


def _save_quality_json(root: Path, decision_date: date, quality: Dict[str, Any]) -> None:
    part = root / f"decision_date={decision_date.isoformat()}"
    part.mkdir(parents=True, exist_ok=True)
    out = part / f"quality_{decision_date.strftime('%Y%m%d')}.json"
    out.write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8")


def _latest_row_at_or_before(df: pd.DataFrame, date_col: str, td: date) -> pd.Series | None:
    if df is None or df.empty or date_col not in df.columns:
        return None
    x = df.copy()
    x[date_col] = pd.to_datetime(x[date_col]).dt.date
    x = x[x[date_col] <= td]
    if x.empty:
        return None
    latest = x[date_col].max()
    row = x[x[date_col] == latest]
    if row.empty:
        return None
    return row.iloc[-1]


def _latest_window_at_or_before(df: pd.DataFrame, date_col: str, td: date) -> pd.DataFrame:
    if df is None or df.empty or date_col not in df.columns:
        return pd.DataFrame()
    x = df.copy()
    x[date_col] = pd.to_datetime(x[date_col]).dt.date
    x = x[x[date_col] <= td]
    if x.empty:
        return pd.DataFrame()
    latest = x[date_col].max()
    return x[x[date_col] == latest].copy()


def _list_partition_dates(root: Path) -> List[date]:
    dates: List[date] = []
    if not root.exists():
        return dates
    for part in root.glob("decision_date=*"):
        try:
            dates.append(date.fromisoformat(part.name.split("=", 1)[1]))
        except Exception:
            continue
    return sorted(dates)


def _estimate_total_invested_capital_usd(
    *,
    paper_start: date,
    decision_date: date,
    initial_krw: float,
    monthly_krw: float,
    fx_usdkrw: float,
) -> float | None:
    if fx_usdkrw <= 0:
        return None
    total_krw = float(initial_krw)
    month_cursor = date(paper_start.year, paper_start.month, 1)
    decision_month = date(decision_date.year, decision_date.month, 1)
    while month_cursor <= decision_month:
        if month_cursor >= date(paper_start.year, paper_start.month, 1):
            total_krw += float(monthly_krw)
        if month_cursor.month == 12:
            month_cursor = date(month_cursor.year + 1, 1, 1)
        else:
            month_cursor = date(month_cursor.year, month_cursor.month + 1, 1)
    return total_krw / fx_usdkrw


def _broker_staged_sell_path(paper_root: Path) -> Path:
    return paper_root / "broker_staged_sell" / "staged_sell_state.json"


def _load_broker_staged_sell(paper_root: Path) -> Dict[str, Any] | None:
    path = _broker_staged_sell_path(paper_root)
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(state, dict):
        return None
    return state


def _save_broker_staged_sell(paper_root: Path, state: Dict[str, Any]) -> None:
    path = _broker_staged_sell_path(paper_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _clear_broker_staged_sell(paper_root: Path) -> None:
    path = _broker_staged_sell_path(paper_root)
    if path.exists():
        path.unlink()


def _load_broker_peak_nav(paper_root: Path, current_nav_usd: float) -> float:
    bootstrap_root = paper_root / "broker_bootstrap"
    peak_nav = float(current_nav_usd)
    for prior_date in _list_partition_dates(bootstrap_root):
        prev_df = load_decision_partition(
            bootstrap_root,
            prior_date,
            execution_mode="MOCK",
        )
        if prev_df is None or prev_df.empty:
            continue
        row = prev_df.iloc[-1]
        prev_total = row.get("total_value")
        prev_ccy = str(row.get("currency", "UNKNOWN")).upper()
        prev_fx = row.get("fx_usdkrw")
        try:
            if prev_total is None:
                continue
            prev_total_f = float(prev_total)
            if prev_ccy == "KRW":
                fx = float(prev_fx) if prev_fx is not None and float(prev_fx) > 0 else None
                if fx is None or fx <= 0:
                    continue
                nav_usd = prev_total_f / fx
            elif prev_ccy == "USD":
                nav_usd = prev_total_f
            else:
                continue
        except Exception:
            continue
        peak_nav = max(peak_nav, float(nav_usd))
    return peak_nav


@dag(
    dag_id="broker_mock_trading_dag",
    description="KIS mock broker order execution + MOCK Telegram (manual trigger)",
    default_args=DEFAULT_ARGS,
    start_date=pendulum.datetime(2026, 1, 1, tz="US/Eastern"),
    schedule=_broker_schedule_interval(),
    catchup=False,
    max_active_runs=1,
    tags=["pretrend", "broker", "mock", "telegram"],
)
def broker_mock_trading_pipeline():
    @task(task_id="load_sim_ledger")
    def load_sim_ledger_task(**context: Any) -> Dict[str, Any]:
        import logging

        logger = logging.getLogger(__name__)
        data_root = Path(os.getenv("PRETREND_DATA_ROOT", "data"))
        should_skip, skip_reason, bypassed = _should_skip_market_hours()
        if bypassed:
            logger.warning("broker market hours check bypassed by BROKER_SKIP_MARKET_HOURS_CHECK=1")
        if should_skip:
            return {
                "status": "skipped",
                "reason": skip_reason or "장외 시간",
                "decision_date": date.today().isoformat(),
            }

        exposure_df = load_strategy_stage(data_root, "exposure", "trade_date")
        if exposure_df is None or exposure_df.empty:
            return {
                "status": "skipped",
                "reason": "strategy exposure 없음",
                "decision_date": date.today().isoformat(),
            }

        decision_date = pd.to_datetime(exposure_df["trade_date"]).dt.date.max()

        now_kst = pendulum.now("Asia/Seoul").date().isoformat()
        return {
            "status": "ok",
            "decision_date": decision_date.isoformat(),
            "simulation_date": now_kst,
            "source_job": "broker_mock_trading_dag",
        }

    @task(task_id="execute_broker_orders")
    def execute_broker_orders_task(ledger_meta: Dict[str, Any]) -> Dict[str, Any]:
        import logging

        logger = logging.getLogger(__name__)
        if ledger_meta.get("status") != "ok":
            return {"status": "skipped", "warnings": [ledger_meta.get("reason", "strategy stage 없음")]}

        decision_date = date.fromisoformat(str(ledger_meta.get("decision_date")))
        simulation_date = date.fromisoformat(str(ledger_meta.get("simulation_date")))
        data_root = Path(os.getenv("PRETREND_DATA_ROOT", "data"))
        paper_root = data_root / "paper"
        source_job = str(ledger_meta.get("source_job", "broker_mock_trading_dag"))

        try:
            adapter = KISMockAdapter.from_env()
            balance = adapter.get_balance()
            broker_positions = adapter.get_positions()

            exposure_df = load_strategy_stage(data_root, "exposure", "trade_date")
            what_to_hold_df = load_strategy_stage(data_root, "what_to_hold", "decision_date")
            next_step_df = load_next_step_runtime_stage(data_root)

            exposure_row = _latest_row_at_or_before(exposure_df, "trade_date", decision_date)
            if exposure_row is None:
                return {
                    "status": "skipped",
                    "warnings": [f"exposure 없음 (decision_date={decision_date})"],
                }

            action = str(exposure_row.get("action", "HOLD")).upper()
            next_invested_ratio = float(exposure_row.get("next_invested_ratio", 0.0))
            delta_ratio = float(exposure_row.get("delta_ratio", 0.0))
            next_row = load_next_step_for_date(next_step_df, decision_date)
            effective_bias = (
                str(next_row.get("bias_effective"))
                if next_row is not None and next_row.get("bias_effective") is not None
                else str(next_row.get("bias_20d", "UNKNOWN")) if next_row is not None else "UNKNOWN"
            )
            _univ_dc = "decision_date" if not what_to_hold_df.empty and "decision_date" in what_to_hold_df.columns else "rebalance_date"
            universe_df = _latest_window_at_or_before(what_to_hold_df, _univ_dc, decision_date)

            today_et = pendulum.now("America/New_York").date()
            weekday = today_et.weekday()

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

            # Market probe: price + orderable info per symbol in strategy/broker universe
            probe_rows: List[Dict[str, Any]] = []
            strategy_symbols = set()
            if not universe_df.empty and "symbol" in universe_df.columns:
                strategy_symbols.update(
                    str(s).upper() for s in universe_df["symbol"].tolist() if str(s).strip()
                )
            strategy_symbols.update({"SPY", "SCHD", "IAU"})
            strategy_symbols.update(str(p.symbol).upper() for p in broker_positions)
            symbols = sorted(strategy_symbols)
            live_prices: Dict[str, float] = {}
            planning_warnings: List[str] = []
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
                    if price_ok:
                        live_prices[sym] = last_price
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
                    planning_warnings.append(f"{sym} live price unavailable: {exc}")
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

            broker_nav_usd = float(balance.total_value) / float(balance.fx_usdkrw or 1300.0)
            invested_usd = 0.0
            for _pos in broker_positions:
                try:
                    mv = getattr(_pos, "market_value", None)
                    if mv is not None:
                        invested_usd += float(mv)
                    else:
                        qty = float(getattr(_pos, "quantity", 0.0))
                        mp = getattr(_pos, "market_price", None) or live_prices.get(str(getattr(_pos, "symbol", "")).upper())
                        if mp is not None:
                            invested_usd += float(mp) * qty
                except Exception:
                    pass
            current_invested_ratio = 0.0
            if broker_nav_usd > 0:
                current_invested_ratio = max(0.0, min(1.0, invested_usd / broker_nav_usd))

            staged_sell = _load_broker_staged_sell(paper_root)
            if staged_sell is None and _broker_staged_sell_path(paper_root).exists():
                planning_warnings.append("staged_sell JSON 파싱 실패 - 주문 없이 진행")

            if action != "DECREASE" and staged_sell is not None:
                _clear_broker_staged_sell(paper_root)
                staged_sell = None

            if weekday == 0:
                if action != "DECREASE":
                    _clear_broker_staged_sell(paper_root)
                orders_df = pd.DataFrame()
                fills_df = pd.DataFrame()
                cancelled_df = pd.DataFrame()
                warnings = ["월요일: 신호 평가만 수행, 주문 없음"] + planning_warnings
                recon_df = reconcile_positions(
                    broker_positions=broker_positions,
                    paper_positions_df=pd.DataFrame(
                        [{"trade_date": decision_date, "symbol": p.symbol, "shares": float(p.quantity)} for p in broker_positions]
                    ),
                    decision_date=decision_date,
                    source_job=source_job,
                )
                auth_meta = adapter.auth_status()
                auth_df = pd.DataFrame(
                    [{
                        "decision_date": decision_date,
                        "simulation_date": simulation_date,
                        "source_job": source_job,
                        "token_refresh_count": auth_meta.get("token_refresh_count", 0),
                        "last_refresh_at": auth_meta.get("last_refresh_at"),
                        "auth_status": auth_meta.get("auth_status", "UNKNOWN"),
                        "error_code": auth_meta.get("error_code"),
                    }]
                )
                fx_df = pd.DataFrame([{
                    "decision_date": decision_date,
                    "simulation_date": simulation_date,
                    "source_job": source_job,
                    "fx_usdkrw": balance.fx_usdkrw,
                    "fx_source": "KIS_BALANCE",
                }])
                save_decision_partition(bootstrap_df, paper_root / "broker_bootstrap", decision_date, "broker_bootstrap", execution_mode="MOCK")
                save_decision_partition(auth_df, paper_root / "broker_auth", decision_date, "broker_auth", execution_mode="MOCK")
                save_decision_partition(fx_df, paper_root / "fx_daily", decision_date, "fx_daily", execution_mode="MOCK")
                save_decision_partition(probe_df, paper_root / "market_probe", decision_date, "market_probe", execution_mode="MOCK")
                save_decision_partition(orders_df, paper_root / "broker_orders", decision_date, "broker_orders", execution_mode="MOCK")
                save_decision_partition(fills_df, paper_root / "broker_fills", decision_date, "broker_fills", execution_mode="MOCK")
                save_decision_partition(recon_df, paper_root / "reconciliation", decision_date, "reconciliation", execution_mode="MOCK")
                save_decision_partition(cancelled_df, paper_root / "broker_cancelled", decision_date, "broker_cancelled", execution_mode="MOCK")
                return {
                    "status": "ok",
                    "decision_date": decision_date.isoformat(),
                    "simulation_date": simulation_date.isoformat(),
                    "source_job": source_job,
                    "action": action,
                    "next_invested_ratio": next_invested_ratio,
                    "delta_ratio": delta_ratio,
                    "orders_count": 0,
                    "fills_count": 0,
                    "cancelled_count": 0,
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
                    "fx_usdkrw": float(fx_df["fx_usdkrw"].iloc[0]) if not fx_df.empty and pd.notna(fx_df["fx_usdkrw"].iloc[0]) else None,
                    "warnings": warnings,
                }

            if weekday not in {1, 4}:
                return {
                    "status": "ok",
                    "decision_date": decision_date.isoformat(),
                    "simulation_date": simulation_date.isoformat(),
                    "source_job": source_job,
                    "action": "HOLD",
                    "next_invested_ratio": next_invested_ratio,
                    "delta_ratio": 0.0,
                    "orders_count": 0,
                    "fills_count": 0,
                    "cancelled_count": 0,
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
                    "auth_status": "UNKNOWN",
                    "token_refresh_count": 0,
                    "fx_usdkrw": balance.fx_usdkrw,
                    "warnings": ["수/목: 실행 요일 아님"] + planning_warnings,
                }

            initial_krw = float(os.getenv("PAPER_INITIAL_CAPITAL_KRW", "1000000"))
            total_invested_capital_usd = _estimate_total_invested_capital_usd(
                paper_start=date.fromisoformat(os.getenv("PAPER_START_DATE", "2026-01-01")),
                decision_date=decision_date,
                initial_krw=initial_krw,
                monthly_krw=0.0,
                fx_usdkrw=float(balance.fx_usdkrw or 1300.0),
            )
            peak_nav_usd = _load_broker_peak_nav(paper_root, broker_nav_usd)
            guardrail_paused = False
            guardrail_warnings: List[str] = []
            if total_invested_capital_usd is not None and total_invested_capital_usd > 0:
                nav_tc_ratio = broker_nav_usd / total_invested_capital_usd
                peak_dd = (broker_nav_usd - peak_nav_usd) / peak_nav_usd if peak_nav_usd > 0 else 0.0
                if nav_tc_ratio < 0.85 or peak_dd < -0.20:
                    guardrail_paused = True
                    guardrail_warnings.append(
                        f"🚨 Level 2 가드레일 발동: NAV/TC={nav_tc_ratio:.2%}, peak_dd={peak_dd:.2%}"
                    )

            if weekday == 1 and guardrail_paused and action == "INCREASE":
                target_orders_df = pd.DataFrame()
            elif weekday == 1:
                target_orders_df = build_broker_target_orders(
                    action=action,
                    next_invested_ratio=next_invested_ratio,
                    what_to_hold_df=universe_df,
                    broker_nav_usd=broker_nav_usd,
                    broker_positions=broker_positions,
                    live_prices=live_prices,
                    effective_bias=effective_bias,
                    decision_date=decision_date,
                    simulation_date=simulation_date,
                    source_job=source_job,
                    allow_sell=False,
                    lock_sell_symbols=[],
                    schd_min_weight=0.20,
                )
            elif action != "DECREASE":
                _clear_broker_staged_sell(paper_root)
                target_orders_df = pd.DataFrame()
                planning_warnings.append("금요일: DECREASE 신호 아님 - staged_sell 없음")
            else:
                if staged_sell is None:
                    total_sell_amount_pct = max(0.0, current_invested_ratio - max(0.0, min(1.0, next_invested_ratio)))
                    if total_sell_amount_pct > 0:
                        staged_sell = {
                            "tranche_idx": 0,
                            "total_sell_amount_pct": total_sell_amount_pct,
                            "tranches": [0.50, 0.30, 0.20],
                            "target_ratio": next_invested_ratio,
                            "created_decision_date": decision_date.isoformat(),
                        }
                        _save_broker_staged_sell(paper_root, staged_sell)
                if staged_sell is None:
                    target_orders_df = pd.DataFrame()
                else:
                    tranche_idx = int(staged_sell.get("tranche_idx", 0))
                    tranches = list(staged_sell.get("tranches", [0.50, 0.30, 0.20]))
                    total_sell_amount_pct = float(staged_sell.get("total_sell_amount_pct", 0.0))
                    base_target_ratio = float(staged_sell.get("target_ratio", next_invested_ratio))
                    if tranche_idx >= len(tranches):
                        _clear_broker_staged_sell(paper_root)
                        target_orders_df = pd.DataFrame()
                    else:
                        tranche_target_ratio = max(
                            base_target_ratio,
                            current_invested_ratio - (total_sell_amount_pct * float(tranches[tranche_idx])),
                        )
                        target_orders_df = build_broker_target_orders(
                            action=action,
                            next_invested_ratio=tranche_target_ratio,
                            what_to_hold_df=universe_df,
                            broker_nav_usd=broker_nav_usd,
                            broker_positions=broker_positions,
                            live_prices=live_prices,
                            effective_bias=effective_bias,
                            decision_date=decision_date,
                            simulation_date=simulation_date,
                            source_job=source_job,
                            allow_sell=True,
                            lock_sell_symbols=[],
                            schd_min_weight=0.20,
                        )
                        staged_sell["tranche_idx"] = tranche_idx + 1
                        if staged_sell["tranche_idx"] >= len(tranches):
                            _clear_broker_staged_sell(paper_root)
                        else:
                            _save_broker_staged_sell(paper_root, staged_sell)

            ledger_like_df = pd.DataFrame()
            if not target_orders_df.empty:
                ledger_like_df = target_orders_df.rename(columns={"qty": "shares"})

            # Execute broker orders from broker target plan
            if ledger_like_df.empty:
                orders_df = pd.DataFrame()
                fills_df = pd.DataFrame()
                cancelled_df = pd.DataFrame()
                if weekday == 1 and guardrail_paused and action == "INCREASE":
                    warnings = guardrail_warnings + ["broker target orders 없음 - broker 주문 생략(잔고/인증 조회는 수행)"]
                else:
                    warnings = ["broker target orders 없음 - broker 주문 생략(잔고/인증 조회는 수행)"]
            else:
                orders_df, fills_df, warnings = execute_from_ledger_rows(
                    adapter,
                    ledger_df=ledger_like_df.head(20),
                    decision_date=decision_date,
                    simulation_date=simulation_date,
                    source_job=source_job,
                )
                fill_wait_sec = int(os.getenv("BROKER_FILL_WAIT_SEC", "30"))
                cancelled_df, fills_df, cancel_warnings = check_and_cancel_unfilled(
                    adapter,
                    orders_df,
                    fills_df=fills_df,
                    wait_sec=fill_wait_sec,
                )
                warnings += cancel_warnings
            warnings += planning_warnings + guardrail_warnings

            broker_positions = adapter.get_positions()
            recon_df = reconcile_positions(
                broker_positions=broker_positions,
                paper_positions_df=pd.DataFrame(
                    [{"trade_date": decision_date, "symbol": p.symbol, "shares": float(p.quantity)} for p in broker_positions]
                ),
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
            "action": action,
            "next_invested_ratio": next_invested_ratio,
            "delta_ratio": delta_ratio,
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
                action=str(broker_meta.get("action", "HOLD")),
                next_invested_ratio=float(broker_meta.get("next_invested_ratio", 0.0)),
                delta_ratio=float(broker_meta.get("delta_ratio", 0.0)),
                initial_capital=float(os.getenv("PAPER_INITIAL_CAPITAL_KRW", "1000000")) / 1300.0,
                monthly_addition=float(os.getenv("PAPER_MONTHLY_ADDITION_KRW", "300000")) / 1300.0,
                fx_usdkrw=1300.0,
                buy_day_rule="월요일(T-1) 평가 후 화요일 INCREASE 실행",
                sell_day_rule="금요일 DECREASE 분할매도",
                sell_tranches=[0.50, 0.30, 0.20],
                schd_sell_locked=False,
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
        paper_start_date = date.fromisoformat(os.getenv("PAPER_START_DATE", "2026-01-01"))

        fills_df = load_decision_partition(
            data_root / "paper" / "broker_fills",
            decision_date,
            execution_mode="MOCK",
        )
        next_step_df = load_next_step_runtime_stage(data_root)
        group_transition_df = load_group_transition_runtime_stage(data_root)
        policy_df = load_strategy_stage(data_root, "policy_selection", "trade_date")

        action = str(broker_meta.get("action", "HOLD")).upper()
        fills: List[str] = ["실제 broker 체결 없음"]
        if fills_df is not None and not fills_df.empty:
            fill_lines: List[str] = []
            for _, row in fills_df.head(10).iterrows():
                status = str(row.get("fill_status", "")).upper()
                if status not in {"FILLED", "PARTIAL_FILLED"}:
                    continue
                qty = row.get("actual_filled_qty", row.get("filled_qty", 0))
                try:
                    qty = float(qty)
                except Exception:
                    qty = 0.0
                if qty <= 0:
                    continue
                side = str(row.get("side", "UNKNOWN")).upper()
                filled_price = row.get("filled_price")
                try:
                    filled_price = float(filled_price) if filled_price is not None else 0.0
                except Exception:
                    filled_price = 0.0
                fill_lines.append(
                    f"{row.get('symbol')} {side} {int(round(qty))}주 @ ${filled_price:,.2f}"
                )
            if fill_lines:
                fills = fill_lines

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

        total_invested_capital = _estimate_total_invested_capital_usd(
            paper_start=paper_start_date,
            decision_date=decision_date,
            initial_krw=initial_krw,
            monthly_krw=monthly_krw,
            fx_usdkrw=fx_usdkrw,
        )
        cumulative_pnl = None
        if (
            nav_usd is not None
            and total_invested_capital is not None
            and float(total_invested_capital) > 0
        ):
            cumulative_pnl = (float(nav_usd) - float(total_invested_capital)) / float(total_invested_capital)

        daily_pnl = None
        previous_nav_usd = None
        bootstrap_root = data_root / "paper" / "broker_bootstrap"
        for prior_date in reversed(_list_partition_dates(bootstrap_root)):
            if prior_date >= decision_date:
                continue
            prev_df = load_decision_partition(
                bootstrap_root,
                prior_date,
                execution_mode="MOCK",
            )
            if prev_df is None or prev_df.empty:
                continue
            prev_total = prev_df.iloc[-1].get("total_value")
            prev_ccy = str(prev_df.iloc[-1].get("currency", "UNKNOWN")).upper()
            prev_fx = prev_df.iloc[-1].get("fx_usdkrw")
            try:
                if prev_total is not None:
                    prev_total = float(prev_total)
                    if prev_ccy == "KRW":
                        px = float(prev_fx) if prev_fx is not None and float(prev_fx) > 0 else fx_usdkrw
                        previous_nav_usd = prev_total / px if px > 0 else None
                    elif prev_ccy == "USD":
                        previous_nav_usd = prev_total
            except Exception:
                previous_nav_usd = None
            if previous_nav_usd is not None:
                break
        if nav_usd is not None:
            if previous_nav_usd is not None and float(previous_nav_usd) > 0:
                daily_pnl = (float(nav_usd) - float(previous_nav_usd)) / float(previous_nav_usd)
            else:
                daily_pnl = 0.0

        position_changes = []
        if broker_raw_positions:
            position_changes.append(f"브로커 보유종목 {len(broker_raw_positions)}개, 상위 {len(top_positions)}개 표시")
        else:
            position_changes.append("포지션 없음(당일 미체결 가능성)")
        position_changes += [
            f"브로커 기준 현금(USD): {cash_usd:,.2f}" if cash_usd is not None else "브로커 기준 현금(USD): N/A",
            f"브로커 주문 {broker_meta.get('orders_count', 0)}건 / 체결 {broker_meta.get('fills_count', 0)}건",
        ]
        risk_warnings = list(broker_meta.get("warnings", []))
        risk_warnings.append("MOCK 결과는 브로커 실시간 스냅샷 기준이며 PnL/원금은 근사치입니다")
        if previous_nav_usd is None:
            risk_warnings.append("전일 브로커 스냅샷 부재로 당일 수익률은 0.0% 근사치로 표시됩니다")

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
            paper_start_date=paper_start_date.isoformat(),
            action=action,
            next_invested_ratio=float(broker_meta.get("next_invested_ratio", next_ratio)),
            delta_ratio=float(broker_meta.get("delta_ratio", 0.0)),
            initial_capital=initial_krw / fx_usdkrw,
            monthly_addition=monthly_krw / fx_usdkrw,
            fx_usdkrw=fx_usdkrw,
            buy_day_rule="월요일(T-1) 평가 후 화요일 INCREASE 실행",
            sell_day_rule="금요일 DECREASE 분할매도",
            sell_tranches=[0.50, 0.30, 0.20],
            schd_sell_locked=False,
            virtual_fills=fills,
            daily_pnl=daily_pnl,
            cumulative_pnl=cumulative_pnl,
            position_changes=position_changes,
            risk_warnings=risk_warnings,
            nav=nav_usd,
            total_invested_capital=total_invested_capital,
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
