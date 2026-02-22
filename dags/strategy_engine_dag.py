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


# ── Telegram 메시지 구성 상수 ────────────────────────────

# v2 목표 비율 룩업 (allocation_mode="v2" 기준, SE allocation/engine.py 와 동기화)
_V2_TARGET_MAP: dict = {
    ("EXPANSION",  "RISK_ON"):  0.80, ("EXPANSION",  "NEUTRAL"): 0.70,
    ("EXPANSION",  "RISK_OFF"): 0.55, ("EXPANSION",  "UNKNOWN"): 0.65,
    ("LATE_CYCLE", "RISK_ON"):  0.60, ("LATE_CYCLE", "NEUTRAL"): 0.45,
    ("LATE_CYCLE", "RISK_OFF"): 0.30, ("LATE_CYCLE", "UNKNOWN"): 0.45,
    ("SLOWDOWN",   "RISK_ON"):  0.35, ("SLOWDOWN",   "NEUTRAL"): 0.25,
    ("SLOWDOWN",   "RISK_OFF"): 0.15, ("SLOWDOWN",   "UNKNOWN"): 0.25,
    ("RECOVERY",   "RISK_ON"):  0.70, ("RECOVERY",   "NEUTRAL"): 0.60,
    ("RECOVERY",   "RISK_OFF"): 0.45, ("RECOVERY",   "UNKNOWN"): 0.60,
    ("RECESSION",  "RISK_ON"):  0.20, ("RECESSION",  "NEUTRAL"): 0.10,
    ("RECESSION",  "RISK_OFF"): 0.05, ("RECESSION",  "UNKNOWN"): 0.10,
    ("UNKNOWN",    "RISK_ON"):  0.50, ("UNKNOWN",    "NEUTRAL"): 0.40,
    ("UNKNOWN",    "RISK_OFF"): 0.30, ("UNKNOWN",    "UNKNOWN"): 0.40,
}

_CORE_HOLD: frozenset = frozenset({"SPY", "SCHD", "IAU"})  # 항상 보유 — 매일 표시 생략
_WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]


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
            allocation_mode="v2",  # f(long_phase, mid_regime) 2D lookup — Backtest v2 기준
        )
        result = runner.run(decision_date=decision_date)

        return {
            "decision_date": decision_date.isoformat(),
            "run_id": result.run_id,
            "current_invested_ratio": current_ratio,
            "ahs_rows": result.axis_horizon_state.row_count,
            "universe_rows": result.universe.row_count,
            "allocation_rows": result.allocation.row_count,
            "sell_advice_rows": result.sell_advice.row_count,
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
        df_sell = _load_snapshot(strategy_root, "sell_advice", decision_date)

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

        # ── Universe — 전술 ETF + RS 점수 ──────────────────────
        tactical_with_rs: List[str] = []
        if not df_univ.empty:
            if "rebalance_date" in df_univ.columns:
                latest = df_univ["rebalance_date"].max()
                df_univ = df_univ[df_univ["rebalance_date"] == latest]
            if "is_candidate" in df_univ.columns:
                df_univ = df_univ[df_univ["is_candidate"] == True]
            if "symbol" in df_univ.columns:
                df_tac = df_univ[~df_univ["symbol"].isin(_CORE_HOLD)]
                if "relative_strength" in df_tac.columns:
                    df_tac = df_tac.sort_values("relative_strength", ascending=False)
                for _, r in df_tac.head(5).iterrows():
                    rs = r.get("relative_strength", None)
                    sym = r["symbol"]
                    entry = f"{sym} {float(rs):+.1%}" if rs is not None else sym
                    tactical_with_rs.append(entry)

        # ── Sell ─────────────────────────────────────────────
        sell_budget = 0.0
        sell_list: List[str] = []
        if not df_sell.empty:
            row = df_sell.iloc[-1]
            sell_budget = float(row.get("sell_budget_ratio", 0.0))
            raw = row.get("sell_priority_list", None)
            sell_list = list(raw) if raw is not None else []

        # ── V2 목표 비율 ──────────────────────────────────────
        v2_target = _V2_TARGET_MAP.get(
            (long_phase, mid_regime),
            _V2_TARGET_MAP.get((long_phase, "UNKNOWN"),
            _V2_TARGET_MAP.get(("UNKNOWN", "UNKNOWN"), 0.40)),
        )

        # ── 표시 텍스트 ───────────────────────────────────────
        _LONG_LABEL = {
            "EXPANSION": "확장기", "LATE_CYCLE": "후기사이클",
            "SLOWDOWN": "둔화기", "RECESSION": "침체기",
            "RECOVERY": "회복기", "UNKNOWN": "판단불가",
        }
        _MID_LABEL = {
            "RISK_ON": "위험선호", "NEUTRAL": "중립",
            "RISK_OFF": "위험회피", "UNKNOWN": "판단불가",
        }
        _SHORT_LABEL = {
            "PANIC": "공황", "RELIEF": "안도",
            "NEUTRAL": "중립", "UNKNOWN": "판단불가",
        }
        _LONG_SHORT = {
            "EXPANSION": "확장", "LATE_CYCLE": "후기", "SLOWDOWN": "둔화",
            "RECESSION": "침체", "RECOVERY": "회복", "UNKNOWN": "불가",
        }
        _MID_SHORT = {
            "RISK_ON": "위험선호", "NEUTRAL": "중립",
            "RISK_OFF": "위험회피", "UNKNOWN": "불가",
        }
        _ACTION_KO = {"INCREASE": "비중확대", "DECREASE": "비중축소", "HOLD": "유지"}

        weekday = _WEEKDAY_KO[decision_date.weekday()]
        action_emoji = {"INCREASE": "📈", "DECREASE": "📉", "HOLD": "⏸"}.get(action, "❓")
        is_panic = (short_signal == "PANIC")
        driver = f"{_LONG_SHORT.get(long_phase, long_phase)}+{_MID_SHORT.get(mid_regime, mid_regime)}"
        cur_pct = strategy_summary["current_invested_ratio"]

        # ── 메시지 조립 ───────────────────────────────────────
        lines = [
            f"📊 <b>Pretrend</b> · {decision_date.isoformat()} ({weekday})",
            "",
            (
                f"{action_emoji} <b>{_ACTION_KO.get(action, action)}</b>  "
                f"{cur_pct:.0%} → {next_ratio:.0%}  |  목표 <b>{v2_target:.0%}</b> ({driver})"
            ),
        ]

        if is_panic:
            lines += ["", "⚠️ 단기 공황 — 이번 주 매도 신호 동결 가능"]

        lines += [
            "",
            (
                f"시장: {_LONG_LABEL.get(long_phase, long_phase)}"
                f" | {_MID_LABEL.get(mid_regime, mid_regime)}"
                f" | {_SHORT_LABEL.get(short_signal, short_signal)}"
            ),
        ]

        if tactical_with_rs:
            lines += ["", f"🎯 {' · '.join(tactical_with_rs)}"]

        if sell_budget > 0:
            sell_order = " → ".join(sell_list) if sell_list else "—"
            lines += ["", f"🚨 <b>매도 예산</b> {sell_budget:.0%}  순서: {sell_order}"]

        lines += ["", f"<code>─ {strategy_summary['run_id']}</code>"]

        _send_telegram(token, chat_id, "\n".join(lines))

    strategy_summary = run_strategy_engine_task()
    send_telegram_report_task(strategy_summary)


strategy_engine_dag = strategy_engine_pipeline()
