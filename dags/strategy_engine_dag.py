"""
Strategy Engine DAG — 매일 10:00 UTC 실행.

의존성:
  - macro_pipeline_dag  (09:00 UTC, ~09:10 완료)
  - eod_pipeline_dag    (08:00 UTC, ~08:20 완료)
  → 고정 시간(10:00 UTC)으로 의존성 감지 없이 순차 실행 보장.

태스크:
  1. run_strategy_engine  — StrategyJobRunner 실행, XCom 반환
  2. send_telegram_report — 결과 요약 → Telegram Bot 발송

환경변수:
  PRETREND_DATA_ROOT    — 데이터 루트 (기본: 'data')
  TELEGRAM_BOT_TOKEN    — Telegram Bot API 토큰
  TELEGRAM_CHAT_ID      — 메시지 수신 chat_id
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import pendulum
from airflow.decorators import dag, task


DEFAULT_ARGS: Dict[str, Any] = {
    "owner": "pretrend",
    "retries": 2,
    "retry_delay": timedelta(minutes=10),
    "depends_on_past": False,
}


# ── 헬퍼: 마지막 거래일 계산 ──────────────────────────────

def _last_us_trading_date(anchor: pendulum.DateTime) -> date:
    """anchor 기준 직전 완전한 미국 거래일 (주말 롤백, 공휴일 미반영)."""
    candidate = (anchor - timedelta(days=1)).date()
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


# ── 헬퍼: 최신 exposure 스냅샷에서 invested_ratio 로드 ───

def _load_last_invested_ratio(strategy_root: Path) -> float:
    """가장 최근 exposure 파티션의 next_invested_ratio를 반환.

    파일이 없으면 0.0 (콜드스타트) 반환.
    """
    exposure_root = strategy_root / "exposure"
    if not exposure_root.exists():
        return 0.0

    partitions = sorted(exposure_root.glob("decision_date=*"), reverse=True)
    for partition in partitions:
        files = list(partition.glob("*.parquet"))
        if not files:
            continue
        try:
            import pandas as pd
            df = pd.read_parquet(files[0])
            if "next_invested_ratio" in df.columns and not df.empty:
                return float(df["next_invested_ratio"].iloc[-1])
        except Exception:
            continue
    return 0.0


# ── 헬퍼: Telegram 메시지 발송 ────────────────────────────

def _send_telegram(token: str, chat_id: str, text: str) -> None:
    import requests
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(
        url,
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        timeout=10,
    )
    resp.raise_for_status()


# ── 헬퍼: 스냅샷 로드 ────────────────────────────────────

def _load_snapshot(strategy_root: Path, stage: str, decision_date: date) -> "pd.DataFrame":
    import pandas as pd
    date_str = decision_date.isoformat()
    partition = strategy_root / stage / f"decision_date={date_str}"
    files = list(partition.glob("*.parquet"))
    if not files:
        return pd.DataFrame()
    return pd.read_parquet(files[0])


# ── DAG ──────────────────────────────────────────────────

@dag(
    dag_id="strategy_engine_dag",
    description="Strategy Engine 7단계 파이프라인 + Telegram 리포트 (매일 10:00 UTC)",
    default_args=DEFAULT_ARGS,
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    schedule_interval="0 10 * * *",  # EOD(08:00) + Macro(09:00) 완료 후
    catchup=False,
    max_active_runs=1,
    tags=["pretrend", "strategy", "telegram"],
)
def strategy_engine_pipeline():
    """
    Strategy Engine E2E + Telegram 리포트.

    - EOD/Macro DAG 완료를 고정 스케줄(10:00 UTC)로 암묵적 보장.
    - current_invested_ratio: 최신 exposure 스냅샷에서 자동 로드.
    - Telegram 환경변수 미설정 시 알림 스킵 (파이프라인 성공 유지).
    """

    @task(task_id="run_strategy_engine")
    def run_strategy_engine_task(**context: Any) -> Dict[str, Any]:
        from pretrend.pipeline.strategy_engine.config import StrategyEngineConfig
        from pretrend.pipeline.strategy_engine.strategy_job import StrategyJobRunner

        data_interval_start = context["data_interval_start"]
        decision_date = _last_us_trading_date(data_interval_start)

        data_root = Path(os.getenv("PRETREND_DATA_ROOT", "data"))
        config = StrategyEngineConfig(data_root=data_root)

        current_ratio = _load_last_invested_ratio(config.strategy_output_root)

        runner = StrategyJobRunner(
            config=config,
            policy_profile_id="RC_V0_DEFAULT",
            current_invested_ratio=current_ratio,
        )
        result = runner.run(decision_date=decision_date)

        return {
            "decision_date": decision_date.isoformat(),
            "run_id": result.run_id,
            "current_invested_ratio": current_ratio,
            "ahs_rows": result.axis_horizon_state.row_count,
            "universe_rows": result.universe.row_count,
            "allocation_rows": result.allocation.row_count,
            "sell_plan_rows": result.sell_plan.row_count,
        }

    @task(task_id="send_telegram_report")
    def send_telegram_report_task(strategy_summary: Dict[str, Any]) -> None:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        if not token or not chat_id:
            import logging
            logging.getLogger(__name__).warning(
                "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 미설정 — 알림 스킵"
            )
            return

        decision_date = date.fromisoformat(strategy_summary["decision_date"])
        data_root = Path(os.getenv("PRETREND_DATA_ROOT", "data"))
        strategy_root = data_root / "strategy"

        # 스냅샷 로드
        df_mp = _load_snapshot(strategy_root, "market_position", decision_date)
        df_alloc = _load_snapshot(strategy_root, "exposure", decision_date)
        df_univ = _load_snapshot(strategy_root, "what_to_hold", decision_date)
        df_sell = _load_snapshot(strategy_root, "sell_plan", decision_date)

        # ── Market Position ──
        long_phase = mid_regime = short_signal = "UNKNOWN"
        run_universe = risk_gate = False
        if not df_mp.empty:
            row = df_mp.iloc[-1]
            long_phase = row.get("long_phase", "UNKNOWN")
            mid_regime = row.get("mid_regime", "UNKNOWN")
            short_signal = row.get("short_signal", "UNKNOWN")
            run_universe = bool(row.get("run_universe", False))
            risk_gate = bool(row.get("risk_gate", False))

        # ── Allocation ──
        action = "HOLD"
        next_ratio = strategy_summary["current_invested_ratio"]
        delta = 0.0
        if not df_alloc.empty:
            row = df_alloc.iloc[-1]
            action = row.get("action", "HOLD")
            next_ratio = float(row.get("next_invested_ratio", next_ratio))
            delta = float(row.get("delta_ratio", 0.0))

        # ── Universe (최신 rebalance_date만 필터) ──
        core_symbols: List[str] = []
        tactical_symbols: List[str] = []
        if not df_univ.empty:
            # 전체 히스토리가 포함돼 있으므로 최신 날짜만 사용
            if "rebalance_date" in df_univ.columns:
                latest = df_univ["rebalance_date"].max()
                df_univ = df_univ[df_univ["rebalance_date"] == latest]
            # is_candidate=True 필터
            if "is_candidate" in df_univ.columns:
                df_univ = df_univ[df_univ["is_candidate"] == True]
            if "role" in df_univ.columns:
                core_symbols = df_univ[df_univ["role"] == "CORE"]["symbol"].tolist()
                tactical_symbols = df_univ[df_univ["role"] == "TACTICAL"]["symbol"].tolist()
            elif "symbol" in df_univ.columns:
                core_symbols = df_univ["symbol"].tolist()

        # ── Sell ──
        sell_budget = 0.0
        sell_list: List[str] = []
        if not df_sell.empty:
            row = df_sell.iloc[-1]
            sell_budget = float(row.get("sell_budget_ratio", 0.0))
            raw = row.get("sell_priority_list", None)
            sell_list = list(raw) if raw is not None else []

        # ── 용어 매핑 ──
        _LONG_LABEL = {
            "EXPANSION": "확장",
            "LATE_CYCLE": "후기사이클",
            "SLOWDOWN": "둔화",
            "RECESSION": "침체",
            "RECOVERY": "회복",
            "UNKNOWN": "판단불가",
        }
        _MID_LABEL = {
            "RISK_ON": "위험선호",
            "NEUTRAL": "중립",
            "RISK_OFF": "위험회피",
            "UNKNOWN": "판단불가",
        }
        _SHORT_LABEL = {
            "PANIC": "공황",
            "RELIEF": "안도",
            "NEUTRAL": "중립",
            "UNKNOWN": "판단불가",
        }
        _ACTION_LABEL = {
            "INCREASE": "비중확대",
            "DECREASE": "비중축소",
            "HOLD": "유지",
        }

        def _fmt(val: str, mapping: dict) -> str:
            label = mapping.get(val, val)
            return f"{label} ({val})"

        # ── 액션 이모지 ──
        action_emoji = {"INCREASE": "📈", "DECREASE": "📉", "HOLD": "⏸"}.get(action, "❓")
        risk_tag = " 🔒 <b>RISK GATE ON</b> (포지션 증가 금지)" if risk_gate else ""

        # ── 메시지 조립 ──
        lines = [
            f"📊 <b>Pretrend Daily Strategy</b> [{decision_date.isoformat()}]",
            "",
            f"{action_emoji} <b>액션:</b> {_fmt(action, _ACTION_LABEL)}  (Δ{delta:+.0%}){risk_tag}",
            f"💼 <b>투자비중:</b> {strategy_summary['current_invested_ratio']:.0%} → {next_ratio:.0%}",
            "",
            "📍 <b>시장 국면</b>",
            f"  장기 : {_fmt(long_phase, _LONG_LABEL)}",
            f"  중기 : {_fmt(mid_regime, _MID_LABEL)}",
            f"  단기 : {_fmt(short_signal, _SHORT_LABEL)}",
            f"  유니버스 가동: {'✅' if run_universe else '❌'}",
        ]

        if core_symbols or tactical_symbols:
            lines += ["", "🎯 <b>편입 후보</b>"]
            if core_symbols:
                lines.append(f"  핵심 : {', '.join(core_symbols)}")
            if tactical_symbols:
                lines.append(f"  전술 : {', '.join(tactical_symbols)}")

        if sell_budget > 0:
            lines += [
                "",
                f"🚨 <b>매도 예산:</b> {sell_budget:.0%}",
                f"  우선순위: {', '.join(sell_list) if sell_list else '—'}",
            ]

        lines += ["", f"🔖 run_id: <code>{strategy_summary['run_id']}</code>"]

        _send_telegram(token, chat_id, "\n".join(lines))

    strategy_summary = run_strategy_engine_task()
    send_telegram_report_task(strategy_summary)


strategy_engine_dag = strategy_engine_pipeline()
