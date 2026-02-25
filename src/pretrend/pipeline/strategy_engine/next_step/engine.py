"""Next Step Signal builder.

Derives 1M/3M bias + evidence summaries from market_position and
axis_horizon_state snapshots.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from pretrend.pipeline.strategy_engine.report_context import (
    build_diagnostic_lines,
    build_evidence_lines,
    build_next_step_lines,
    safe_json_dict,
)

from .schema import NEXT_STEP_SIGNAL_COLUMNS


def _parse_bias_and_conf(line: str) -> Tuple[str, float]:
    bias_match = re.search(r"\(([^,\)]+)", line)
    pct_match = re.search(r",\s*(\d+)%\)", line)
    bias = bias_match.group(1) if bias_match else "UNKNOWN"
    conf = float(pct_match.group(1)) / 100.0 if pct_match else 0.5
    return bias, conf


def _extract_evidence_value(lines: list[str], idx: int) -> str:
    if idx + 1 >= len(lines):
        return "영향 근거 없음"
    line = str(lines[idx + 1]).strip()
    if line.startswith("→"):
        return line.replace("→", "", 1).strip()
    return line or "영향 근거 없음"


def _compute_diag_coverage(
    long_detail: Dict[str, Any],
    mid_detail: Dict[str, Any],
    short_detail: Dict[str, Any],
) -> float:
    known = 0
    total = 12

    if long_detail.get("regime_mode") is not None or long_detail.get("delta_6m_z_mean") is not None:
        known += 1
    if mid_detail.get("macro_signal") is not None:
        known += 1
    if mid_detail.get("price_signal") is not None:
        known += 1
    if short_detail.get("primary_panic") is not None or short_detail.get("primary_relief") is not None:
        known += 1
    if mid_detail.get("breadth_signal") is not None:
        known += 1
    if (
        short_detail.get("secondary_confirm_count") is not None
        or short_detail.get("smallcap_stress") is not None
        or short_detail.get("secondary_confirmations") is not None
    ):
        known += 1
    if short_detail.get("risk_on_confirm") is not None:
        known += 1

    return known / total


def _build_state_history(ahs: pd.DataFrame) -> pd.DataFrame:
    """Build rolling state-age / sojourn / hazard estimate frame.

    Uses only past completed episodes for each date (fail-open when sample is too small).
    """
    if ahs.empty:
        return pd.DataFrame(
            columns=[
                "trade_date",
                "state_age_days",
                "sojourn_prob_5d",
                "sojourn_prob_10d",
                "sojourn_prob_20d",
                "transition_hazard_5d",
                "transition_hazard_10d",
                "transition_hazard_20d",
                "transition_expected",
            ]
        )

    x = ahs[["trade_date", "long_phase", "mid_regime", "short_signal"]].copy()
    x = x.sort_values("trade_date").reset_index(drop=True)
    x["state_key"] = list(zip(x["long_phase"], x["mid_regime"], x["short_signal"]))

    episode_id: List[int] = []
    ep = -1
    prev = None
    for state in x["state_key"].tolist():
        if state != prev:
            ep += 1
        episode_id.append(ep)
        prev = state
    x["episode_id"] = episode_id
    x["idx"] = x.index
    x["episode_pos"] = x.groupby("episode_id").cumcount() + 1

    eps = (
        x.groupby("episode_id")
        .agg(
            start_idx=("idx", "min"),
            end_idx=("idx", "max"),
            duration=("idx", "size"),
            state_key=("state_key", "first"),
        )
        .reset_index()
    )
    eps["next_state"] = eps["episode_id"].map(
        eps.set_index("episode_id")["state_key"].shift(-1)
    )

    rows = []
    horizons = [5, 10, 20]
    for _, row in x.iterrows():
        cur_ep = int(row["episode_id"])
        cur_state = row["state_key"]
        age = int(row["episode_pos"])

        prior = eps[(eps["state_key"] == cur_state) & (eps["episode_id"] < cur_ep)]
        if len(prior) < 3:
            soj = {h: None for h in horizons}
            hz = {h: None for h in horizons}
            expected = "UNKNOWN"
        else:
            durations = prior["duration"].tolist()
            next_states = [s for s in prior["next_state"].tolist() if isinstance(s, tuple)]
            expected = (
                "_".join(Counter(next_states).most_common(1)[0][0])
                if next_states
                else "UNKNOWN"
            )

            soj = {}
            hz = {}
            at_risk = [d for d in durations if d > age]
            for h in horizons:
                if not at_risk:
                    soj[h] = None
                    hz[h] = None
                    continue
                survived = sum(1 for d in at_risk if d > (age + h))
                p = survived / len(at_risk)
                soj[h] = p
                hz[h] = 1.0 - p

        rows.append(
            {
                "trade_date": row["trade_date"],
                "state_age_days": age,
                "sojourn_prob_5d": soj[5],
                "sojourn_prob_10d": soj[10],
                "sojourn_prob_20d": soj[20],
                "transition_hazard_5d": hz[5],
                "transition_hazard_10d": hz[10],
                "transition_hazard_20d": hz[20],
                "transition_expected": expected,
            }
        )

    return pd.DataFrame(rows)


def build_next_step_signal(
    axis_horizon_state_df: pd.DataFrame,
    market_position_df: pd.DataFrame,
    *,
    run_id: str,
) -> pd.DataFrame:
    """Build next_step_signal snapshot frame.

    Strategy output remains deterministic + fail-open.
    """
    if axis_horizon_state_df is None or axis_horizon_state_df.empty:
        return pd.DataFrame(columns=NEXT_STEP_SIGNAL_COLUMNS)

    ahs = axis_horizon_state_df.copy()
    if "trade_date" in ahs.columns:
        ahs["trade_date"] = pd.to_datetime(ahs["trade_date"]).dt.date

    mp = market_position_df.copy() if market_position_df is not None else pd.DataFrame()
    if not mp.empty and "trade_date" in mp.columns:
        mp["trade_date"] = pd.to_datetime(mp["trade_date"]).dt.date

    hist_df = _build_state_history(ahs)
    hist_map = (
        hist_df.set_index("trade_date").to_dict(orient="index")
        if not hist_df.empty
        else {}
    )

    rows = []
    for _, ahs_row in ahs.iterrows():
        td = ahs_row.get("trade_date")
        long_phase = str(ahs_row.get("long_phase", "UNKNOWN"))
        mid_regime = str(ahs_row.get("mid_regime", "UNKNOWN"))
        short_signal = str(ahs_row.get("short_signal", "UNKNOWN"))

        long_detail = safe_json_dict(ahs_row.get("long_detail_json"))
        mid_detail = safe_json_dict(ahs_row.get("mid_detail_json"))
        short_detail = safe_json_dict(ahs_row.get("short_detail_json"))

        next_lines = build_next_step_lines(long_phase, mid_regime, short_signal)
        bias_1m, conf_1m = _parse_bias_and_conf(next_lines[0]) if next_lines else ("UNKNOWN", 0.5)
        bias_3m, conf_3m = _parse_bias_and_conf(next_lines[1]) if len(next_lines) > 1 else ("UNKNOWN", 0.5)

        ev_lines = build_evidence_lines(long_detail, mid_detail, short_detail)
        evidence_axis_macro = _extract_evidence_value(ev_lines, 0)
        evidence_axis_price = _extract_evidence_value(ev_lines, 3)
        evidence_axis_flow = _extract_evidence_value(ev_lines, 6)
        evidence_axis_sentiment = _extract_evidence_value(ev_lines, 9)

        coverage = _compute_diag_coverage(long_detail, mid_detail, short_detail)
        unknown = 1.0 - coverage
        diag_lines = build_diagnostic_lines(long_detail, mid_detail, short_detail)
        quality = "경고"
        if diag_lines:
            q = str(diag_lines[0]).replace("🧪 12셀 품질:", "").strip()
            quality = q if q else "경고"

        hist = hist_map.get(td, {})

        # evidence_quality_score는 확장 포트: MVP는 nullable 유지
        rows.append(
            {
                "trade_date": td,
                "bias_1m": bias_1m,
                "confidence_1m": conf_1m,
                "bias_3m": bias_3m,
                "confidence_3m": conf_3m,
                "bias_effective": None,
                "bias_override_flag": None,
                "bias_override_reason": None,
                "state_age_days": hist.get("state_age_days"),
                "sojourn_prob_5d": hist.get("sojourn_prob_5d"),
                "sojourn_prob_10d": hist.get("sojourn_prob_10d"),
                "sojourn_prob_20d": hist.get("sojourn_prob_20d"),
                "transition_hazard_5d": hist.get("transition_hazard_5d"),
                "transition_hazard_10d": hist.get("transition_hazard_10d"),
                "transition_hazard_20d": hist.get("transition_hazard_20d"),
                "transition_expected": hist.get("transition_expected", "UNKNOWN"),
                "evidence_axis_macro": evidence_axis_macro,
                "evidence_axis_price": evidence_axis_price,
                "evidence_axis_flow": evidence_axis_flow,
                "evidence_axis_sentiment": evidence_axis_sentiment,
                "evidence_quality_score": None,
                "evidence_unknown_ratio": unknown,
                "diag_12slot_coverage": coverage,
                "diag_12slot_quality": quality,
                "source_run_id": run_id,
            }
        )

    out = pd.DataFrame(rows, columns=NEXT_STEP_SIGNAL_COLUMNS)
    return out
