"""Paper trading Telegram payload/message helpers."""
from __future__ import annotations

import json
import os
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from pretrend.pipeline.utils.result_registry import append_registry_entry

PAPER_RESULT_REQUIRED_FIELDS = (
    "message_type",
    "source_job",
    "decision_date",
    "simulation_date",
    "action",
    "next_invested_ratio",
    "delta_ratio",
    "initial_capital",
    "monthly_addition",
    "buy_day_rule",
    "sell_day_rule",
    "sell_tranches",
    "schd_sell_locked",
)


def build_paper_result_payload(
    *,
    source_job: str,
    decision_date: str,
    simulation_date: str,
    action: str,
    next_invested_ratio: float,
    delta_ratio: float,
    virtual_fills: Optional[List[str]] = None,
    daily_pnl: Optional[float] = None,
    cumulative_pnl: Optional[float] = None,
    position_changes: Optional[List[str]] = None,
    risk_warnings: Optional[List[str]] = None,
    nav: Optional[float] = None,
    total_invested_capital: Optional[float] = None,
    top_positions: Optional[List[Dict[str, Any]]] = None,
    initial_capital: float = 1_000_000.0,
    monthly_addition: float = 300_000.0,
    buy_day_rule: str = "화요일 INCREASE 실행",
    sell_day_rule: str = "금요일 DECREASE 분할매도",
    sell_tranches: Optional[List[float]] = None,
    schd_sell_locked: bool = True,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "message_type": "PAPER_RESULT",
        "source_job": source_job,
        "decision_date": decision_date,
        "simulation_date": simulation_date,
        "action": action,
        "next_invested_ratio": float(next_invested_ratio),
        "delta_ratio": float(delta_ratio),
        "initial_capital": float(initial_capital),
        "monthly_addition": float(monthly_addition),
        "buy_day_rule": buy_day_rule,
        "sell_day_rule": sell_day_rule,
        "sell_tranches": list(sell_tranches or [0.50, 0.30, 0.20]),
        "schd_sell_locked": bool(schd_sell_locked),
        "virtual_fills": list(virtual_fills or []),
        "daily_pnl": None if daily_pnl is None else float(daily_pnl),
        "cumulative_pnl": None if cumulative_pnl is None else float(cumulative_pnl),
        "position_changes": list(position_changes or []),
        "risk_warnings": list(risk_warnings or []),
        "nav": None if nav is None else float(nav),
        "total_invested_capital": None if total_invested_capital is None else float(total_invested_capital),
        "top_positions": list(top_positions or []),
    }
    return payload


def validate_paper_result_payload(payload: Dict[str, Any]) -> None:
    missing = [k for k in PAPER_RESULT_REQUIRED_FIELDS if k not in payload]
    if missing:
        raise ValueError(f"missing required fields: {', '.join(missing)}")
    if payload.get("message_type") != "PAPER_RESULT":
        raise ValueError("message_type must be PAPER_RESULT")


def _fmt_pct(val: float) -> str:
    return f"{val:+.1%}"


def format_paper_result_message(payload: Dict[str, Any]) -> str:
    validate_paper_result_payload(payload)

    action_ko = {
        "INCREASE": "비중확대",
        "DECREASE": "비중축소",
        "HOLD": "유지",
    }.get(str(payload["action"]), str(payload["action"]))

    lines: List[str] = [
        "📄 <b>Pretrend Paper Trading</b>",
        f"<code>message_type={payload['message_type']} | source_job={payload['source_job']}</code>",
        (
            f"<code>decision_date={payload['decision_date']} | "
            f"simulation_date={payload['simulation_date']}</code>"
        ),
        "",
        (
            f"🧾 <b>가상 체결 요약</b>: {action_ko}  "
            f"{payload['next_invested_ratio']:.0%} ({_fmt_pct(payload['delta_ratio'])})"
        ),
    ]
    tranches = payload.get("sell_tranches", [0.50, 0.30, 0.20])
    tranche_txt = " → ".join([f"{int(float(x) * 100)}%" for x in tranches])
    lines += [
        "",
        "📐 <b>운영 조건</b>",
        f"- 초기자금: {payload.get('initial_capital', 0):,.0f}원",
        f"- 월 첫 거래일 DCA: {payload.get('monthly_addition', 0):,.0f}원",
        f"- 매수 규칙: {payload.get('buy_day_rule', 'N/A')}",
        f"- 매도 규칙: {payload.get('sell_day_rule', 'N/A')} ({tranche_txt})",
        f"- SCHD 매도: {'금지' if payload.get('schd_sell_locked', True) else '허용'}",
    ]

    fills = payload.get("virtual_fills") or ["가상 체결 데이터 없음"]
    lines += [f"- {item}" for item in fills]

    lines += ["", "💰 <b>PnL 요약</b>"]
    daily_pnl = payload.get("daily_pnl")
    cum_pnl = payload.get("cumulative_pnl")
    nav = payload.get("nav")
    invested_capital = payload.get("total_invested_capital")
    lines.append(f"- 당일: {_fmt_pct(daily_pnl) if daily_pnl is not None else '집계 데이터 없음'}")
    lines.append(f"- 누적: {_fmt_pct(cum_pnl) if cum_pnl is not None else '집계 데이터 없음'}")
    lines.append(f"- NAV: {f'${nav:,.2f}' if nav is not None else '집계 데이터 없음'}")
    lines.append(
        f"- 총투입원금: {f'${invested_capital:,.2f}' if invested_capital is not None else '집계 데이터 없음'}"
    )

    changes = payload.get("position_changes") or ["포지션 변화 없음"]
    lines += ["", "🧩 <b>포지션 변화</b>"]
    lines += [f"- {item}" for item in changes]

    top_positions = payload.get("top_positions") or []
    if top_positions:
        lines += ["", "📦 <b>상위 보유 종목</b>"]
        for p in top_positions:
            symbol = p.get("symbol", "?")
            shares = float(p.get("shares", 0.0))
            avg_cost = p.get("avg_cost")
            eod_price = p.get("eod_price")
            value = p.get("market_value")
            gain_pct = p.get("gain_pct")
            parts = [f"{symbol} {shares:.2f}주"]
            if avg_cost is not None:
                parts.append(f"평단 ${float(avg_cost):.2f}")
            if eod_price is not None:
                parts.append(f"현재가 ${float(eod_price):.2f}")
            if value is not None:
                parts.append(f"평가 ${float(value):,.2f}")
            if gain_pct is not None:
                parts.append(f"손익 {_fmt_pct(float(gain_pct))}")
            lines.append(f"- {' | '.join(parts)}")

    warnings = payload.get("risk_warnings") or []
    if warnings:
        lines += ["", "⚠️ <b>리스크 경고</b>"]
        lines += [f"- {item}" for item in warnings]

    return "\n".join(lines)


def save_paper_result_payload(
    payload: Dict[str, Any],
    *,
    base_dir: str | Path | None = None,
) -> Path:
    """Save paper payload for analysis + append registry entry."""
    validate_paper_result_payload(payload)
    root = Path(base_dir) if base_dir is not None else Path(os.getenv("PRETREND_RESULT_ROOT", "result")) / "paper"
    root.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    decision_date = str(payload.get("decision_date"))
    stem = f"paper_result_{decision_date.replace('-', '')}_{ts}"

    payload_json = root / f"{stem}.json"
    payload_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    payload_parquet = root / f"{stem}.parquet"
    pd.DataFrame([payload]).to_parquet(payload_parquet, index=False)

    entry = {
        "pipeline": "paper",
        "artifact_path": str(payload_parquet),
        "preset": "paper_v1",
        "start_date": None,
        "end_date": str(payload.get("simulation_date")),
        "decision_date_ref": decision_date,
        "code_version": os.getenv("PRETREND_CODE_VERSION", "unknown"),
        "data_version": os.getenv("PRETREND_DATA_VERSION", "unknown"),
        "metrics_hash": hashlib.md5(
            json.dumps(
                {
                    "daily_pnl": payload.get("daily_pnl"),
                    "cumulative_pnl": payload.get("cumulative_pnl"),
                    "nav": payload.get("nav"),
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest(),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    append_registry_entry(
        Path(os.getenv("PRETREND_RESULT_ROOT", "result")) / "backtest" / "registry",
        entry,
    )
    return root
