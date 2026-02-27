"""Next Step Signal builder.

Derives trading-day horizon bias/evidence from market_position and
axis_horizon_state snapshots.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from pretrend.pipeline.strategy_engine.report_context import (
    build_diagnostic_lines,
    build_evidence_lines,
    safe_json_dict,
)

from .schema import NEXT_STEP_SIGNAL_COLUMNS


_HORIZON_WEIGHTS: Dict[int, Tuple[float, float, float]] = {
    5: (0.10, 0.30, 0.60),
    10: (0.15, 0.45, 0.40),
    20: (0.20, 0.60, 0.20),
    60: (0.50, 0.40, 0.10),
    120: (0.70, 0.25, 0.05),
}
_HORIZON_THRESHOLDS: Dict[int, float] = {
    5: 0.35,
    10: 0.30,
    20: 0.25,
    60: 0.20,
    120: 0.15,
}
_HORIZON_HAZARD_PENALTY: Dict[int, float] = {
    5: 0.10,
    10: 0.10,
    20: 0.08,
    60: 0.05,
    120: 0.05,
}
_HORIZON_MIN_CONFIDENCE: Dict[int, float] = {
    5: 0.50,
    10: 0.50,
    20: 0.45,
    60: 0.40,
    120: 0.40,
}
_PHASE_BASELINE: Dict[str, str] = {
    "EXPANSION": "NEUTRAL_BIAS",
    "LATE_CYCLE": "NEUTRAL_BIAS",
    "RECOVERY": "RISK_ON_BIAS",
    "SLOWDOWN": "RISK_OFF_BIAS",
    "RECESSION": "RISK_OFF_BIAS",
    "UNKNOWN": "NEUTRAL_BIAS",
}

_COOLDOWN_DAYS = 5
_COOLDOWN_COMPRESSED_DAYS = 2
_RELIEF_STREAK_FOR_COMPRESSION = 2


def _long_to_score(long_phase: str) -> int:
    if long_phase in {"EXPANSION", "RECOVERY", "LATE_CYCLE"}:
        return 1
    if long_phase in {"SLOWDOWN", "RECESSION"}:
        return -1
    return 0


def _mid_to_score(mid_regime: str) -> int:
    if mid_regime == "RISK_ON":
        return 1
    if mid_regime == "RISK_OFF":
        return -1
    return 0


def _short_to_score(short_signal: str) -> int:
    if short_signal == "RELIEF":
        return 1
    if short_signal == "PANIC":
        return -1
    return 0


def _score_to_bias(score: float, threshold: float) -> str:
    if score >= threshold:
        return "RISK_ON_BIAS"
    if score <= -threshold:
        return "RISK_OFF_BIAS"
    return "NEUTRAL_BIAS"


def _compute_confidence(score: float, components: List[int], bias: str, min_floor: float) -> float:
    target = 0
    if bias == "RISK_ON_BIAS":
        target = 1
    elif bias == "RISK_OFF_BIAS":
        target = -1

    non_zero = [v for v in components if v != 0]
    if target == 0 or not non_zero:
        agreement = 0.0
    else:
        agreement = sum(1 for v in non_zero if v == target) / len(non_zero)

    confidence = 0.45 + (0.45 * agreement) + (0.10 * abs(score))
    confidence = max(min_floor, min(0.95, confidence))
    return round(float(confidence), 4)


def _threshold_for_horizon(h: int) -> float:
    return float(_HORIZON_THRESHOLDS.get(int(h), 0.25))


def _hazard_penalty(h: int, hazard: Optional[float]) -> float:
    if hazard is None:
        return 0.0
    try:
        hv = float(hazard)
    except Exception:
        return 0.0
    if hv != hv:  # NaN
        return 0.0
    if hv >= 0.95:
        return float(_HORIZON_HAZARD_PENALTY.get(int(h), 0.0))
    return 0.0


def _age_damping(
    h: int,
    state_age_days: Optional[int],
    lv: int,
    mv: int,
    sv: int,
) -> Tuple[float, float, float]:
    ld = float(lv)
    md = float(mv)
    sd = float(sv)
    if state_age_days is None:
        return ld, md, sd
    if int(state_age_days) < 3:
        if int(h) in {5, 10}:
            ld *= 0.5
        elif int(h) in {60, 120}:
            sd *= 0.5
    return ld, md, sd


def _compute_horizon_biases(
    long_phase: str,
    mid_regime: str,
    short_signal: str,
    *,
    hazards_by_horizon: Dict[int, Optional[float]] | None = None,
    state_age_days: Optional[int] = None,
) -> Dict[str, Any]:
    lv = _long_to_score(long_phase)
    mv = _mid_to_score(mid_regime)
    sv = _short_to_score(short_signal)
    hazards_by_horizon = hazards_by_horizon or {}

    out: Dict[str, Any] = {}
    for h, (lw, mw, sw) in _HORIZON_WEIGHTS.items():
        ld, md, sd = _age_damping(h, state_age_days, lv, mv, sv)
        score = (lw * ld) + (mw * md) + (sw * sd) - _hazard_penalty(h, hazards_by_horizon.get(h))
        threshold = _threshold_for_horizon(h)
        bias = _score_to_bias(score, threshold)
        parts = [lv, mv, sv]
        conf = _compute_confidence(score, parts, bias, min_floor=float(_HORIZON_MIN_CONFIDENCE[h]))
        out[f"bias_{h}d"] = bias
        out[f"confidence_{h}d"] = conf
    return out


def resolve_phase_baseline(long_phase: str) -> str:
    return _PHASE_BASELINE.get(str(long_phase), "NEUTRAL_BIAS")


def compute_overlay_score(
    mid_regime: str,
    short_signal: str,
    hazard_10d: Optional[float],
) -> int:
    score = 0
    if str(mid_regime) == "RISK_ON":
        score += 2
    elif str(mid_regime) == "RISK_OFF":
        score -= 2

    if str(short_signal) == "RELIEF":
        score += 1
    elif str(short_signal) == "PANIC":
        score -= 2

    if hazard_10d is not None and hazard_10d >= 0.95:
        score -= 1
    return score


def _overlay_reason(mid_regime: str, short_signal: str, hazard_10d: Optional[float]) -> str:
    if str(mid_regime) == "RISK_ON":
        return "MID_RISK_ON"
    if str(mid_regime) == "RISK_OFF":
        return "MID_RISK_OFF"
    if str(short_signal) == "PANIC":
        return "SHORT_PANIC"
    if str(short_signal) == "RELIEF":
        return "SHORT_RELIEF"
    if hazard_10d is not None and hazard_10d >= 0.95:
        return "HAZARD_HIGH"
    return "OVERLAY"


def apply_hysteresis(
    prev_bias: str,
    baseline_bias: str,
    score: int,
    cooldown_left: int,
    is_monday: bool,
    *,
    mid_regime: str,
    short_signal: str,
    hazard_10d: Optional[float],
    run_universe: bool,
) -> Tuple[str, str, bool, str, int]:
    """Resolve 20D execution bias with weekly cadence + hysteresis + cooldown."""
    if not run_universe:
        switched = prev_bias not in {"UNKNOWN", "RISK_OFF_BIAS"}
        return "RISK_OFF_BIAS", "HARD_GATE", switched, "HARD_GATE", cooldown_left

    hold_bias = prev_bias if prev_bias != "UNKNOWN" else baseline_bias
    if not is_monday:
        if cooldown_left > 0:
            return hold_bias, "HOLD_COOLDOWN", False, "COOLDOWN", max(0, cooldown_left - 1)
        return hold_bias, "BASELINE", False, "WEEKDAY_HOLD", cooldown_left

    if cooldown_left > 0:
        return hold_bias, "HOLD_COOLDOWN", False, "COOLDOWN", max(0, cooldown_left - 1)

    if score >= 2:
        candidate = "RISK_ON_BIAS"
        source = "OVERLAY"
        reason = _overlay_reason(mid_regime, short_signal, hazard_10d)
    elif score <= -2:
        candidate = "RISK_OFF_BIAS"
        source = "OVERLAY"
        reason = _overlay_reason(mid_regime, short_signal, hazard_10d)
    else:
        candidate = baseline_bias
        source = "BASELINE"
        reason = "PHASE_BASELINE"

    # hysteresis hold
    if prev_bias == "RISK_ON_BIAS" and score > 0 and candidate != "RISK_ON_BIAS":
        candidate = "RISK_ON_BIAS"
        source = "OVERLAY"
        reason = "HYSTERESIS_HOLD_ON"
    elif prev_bias == "RISK_OFF_BIAS" and score < 0 and candidate != "RISK_OFF_BIAS":
        candidate = "RISK_OFF_BIAS"
        source = "OVERLAY"
        reason = "HYSTERESIS_HOLD_OFF"

    switched = prev_bias != "UNKNOWN" and candidate != prev_bias
    next_cooldown = _COOLDOWN_DAYS if switched else cooldown_left
    return candidate, source, switched, reason, next_cooldown


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
                "sojourn_prob_60d",
                "sojourn_prob_120d",
                "transition_hazard_5d",
                "transition_hazard_10d",
                "transition_hazard_20d",
                "transition_hazard_60d",
                "transition_hazard_120d",
                "transition_expected_5d",
                "transition_expected_10d",
                "transition_expected_20d",
                "transition_expected_60d",
                "transition_expected_120d",
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
    horizons = [5, 10, 20, 60, 120]
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
                "sojourn_prob_60d": soj[60],
                "sojourn_prob_120d": soj[120],
                "transition_hazard_5d": hz[5],
                "transition_hazard_10d": hz[10],
                "transition_hazard_20d": hz[20],
                "transition_hazard_60d": hz[60],
                "transition_hazard_120d": hz[120],
                "transition_expected_5d": expected,
                "transition_expected_10d": expected,
                "transition_expected_20d": expected,
                "transition_expected_60d": expected,
                "transition_expected_120d": expected,
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
    mp_map: Dict[Any, Dict[str, Any]] = {}
    if not mp.empty:
        for _, mp_row in mp.sort_values("trade_date").iterrows():
            mp_map[mp_row["trade_date"]] = mp_row.to_dict()

    rows = []
    prev_bias_20d = "UNKNOWN"
    cooldown_left = 0
    prev_run_universe = True
    relief_streak_state = 0
    for _, ahs_row in ahs.sort_values("trade_date").iterrows():
        td = ahs_row.get("trade_date")
        long_phase = str(ahs_row.get("long_phase", "UNKNOWN"))
        mid_regime = str(ahs_row.get("mid_regime", "UNKNOWN"))
        short_signal = str(ahs_row.get("short_signal", "UNKNOWN"))

        long_detail = safe_json_dict(ahs_row.get("long_detail_json"))
        mid_detail = safe_json_dict(ahs_row.get("mid_detail_json"))
        short_detail = safe_json_dict(ahs_row.get("short_detail_json"))

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
        state_age_days = hist.get("state_age_days")
        hazards_by_horizon: Dict[int, Optional[float]] = {
            5: hist.get("transition_hazard_5d"),
            10: hist.get("transition_hazard_10d"),
            20: hist.get("transition_hazard_20d"),
            60: hist.get("transition_hazard_60d"),
            120: hist.get("transition_hazard_120d"),
        }
        horizon = _compute_horizon_biases(
            long_phase,
            mid_regime,
            short_signal,
            hazards_by_horizon=hazards_by_horizon,
            state_age_days=state_age_days,
        )
        hazard_10d = hist.get("transition_hazard_10d")
        if hazard_10d is not None:
            try:
                hazard_10d = float(hazard_10d)
            except Exception:
                hazard_10d = None
        baseline_bias = resolve_phase_baseline(long_phase)
        overlay_score = compute_overlay_score(mid_regime, short_signal, hazard_10d)

        mp_row = mp_map.get(td, {})
        run_universe = bool(mp_row.get("run_universe", True))
        is_monday = bool(hasattr(td, "weekday") and td.weekday() == 0)

        bias_20d_state, bias_source, switch_flag, switch_reason, cooldown_left = apply_hysteresis(
            prev_bias_20d,
            baseline_bias,
            overlay_score,
            cooldown_left,
            is_monday,
            mid_regime=mid_regime,
            short_signal=short_signal,
            hazard_10d=hazard_10d,
            run_universe=run_universe,
        )
        prev_bias_20d = bias_20d_state

        # v3.4.2a 실험용 메타(기본 nullable): 이 플래그들은 snapshot에 기록하고
        # 실제 적용 여부는 소비자(backtest/paper preset v3.4.2a)에서 결정한다.
        bias_candidate_20d = horizon["bias_20d"]
        relief_streak_state = relief_streak_state + 1 if short_signal == "RELIEF" else 0
        cooldown_compressed_flag = False
        cooldown_compressed_reason = "NONE"
        if bias_source == "HOLD_COOLDOWN" and cooldown_left > _COOLDOWN_COMPRESSED_DAYS:
            if mid_regime == "RISK_ON":
                cooldown_compressed_flag = True
                cooldown_compressed_reason = "MID_RISK_ON"
            elif relief_streak_state >= _RELIEF_STREAK_FOR_COMPRESSION:
                cooldown_compressed_flag = True
                cooldown_compressed_reason = "RELIEF_STREAK"

        hard_gate_exit_assist_flag = False
        hard_gate_exit_assist_reason = "NONE"
        if prev_run_universe is False and run_universe is True and relief_streak_state >= _RELIEF_STREAK_FOR_COMPRESSION:
            hard_gate_exit_assist_flag = True
            hard_gate_exit_assist_reason = "RUN_UNIVERSE_RECOVERY_RELIEF"
        prev_run_universe = run_universe

        # evidence_quality_score는 확장 포트: MVP는 nullable 유지
        horizon_biases = [horizon[f"bias_{h}d"] for h in (5, 10, 20, 60, 120)]
        horizon_confs = [float(horizon[f"confidence_{h}d"]) for h in (5, 10, 20, 60, 120)]
        diversity_count = len(set(horizon_biases))
        conf_spread = max(horizon_confs) - min(horizon_confs)
        rows.append(
            {
                "trade_date": td,
                "bias_5d": horizon["bias_5d"],
                "confidence_5d": horizon["confidence_5d"],
                "bias_10d": horizon["bias_10d"],
                "confidence_10d": horizon["confidence_10d"],
                "bias_20d": bias_20d_state,
                "confidence_20d": horizon["confidence_20d"],
                "bias_60d": horizon["bias_60d"],
                "confidence_60d": horizon["confidence_60d"],
                "bias_120d": horizon["bias_120d"],
                "confidence_120d": horizon["confidence_120d"],
                "bias_effective": bias_20d_state,
                "bias_override_flag": switch_flag,
                "bias_override_reason": switch_reason,
                "bias_state_source": bias_source,
                "bias_switch_flag": switch_flag,
                "bias_switch_reason": switch_reason,
                "bias_cooldown_left": cooldown_left,
                "bias_candidate_20d": bias_candidate_20d,
                "cooldown_compressed_flag": cooldown_compressed_flag,
                "cooldown_compressed_reason": cooldown_compressed_reason,
                "hard_gate_exit_assist_flag": hard_gate_exit_assist_flag,
                "hard_gate_exit_assist_reason": hard_gate_exit_assist_reason,
                "state_age_days": hist.get("state_age_days"),
                "sojourn_prob_5d": hist.get("sojourn_prob_5d"),
                "sojourn_prob_10d": hist.get("sojourn_prob_10d"),
                "sojourn_prob_20d": hist.get("sojourn_prob_20d"),
                "sojourn_prob_60d": hist.get("sojourn_prob_60d"),
                "sojourn_prob_120d": hist.get("sojourn_prob_120d"),
                "transition_hazard_5d": hist.get("transition_hazard_5d"),
                "transition_hazard_10d": hist.get("transition_hazard_10d"),
                "transition_hazard_20d": hist.get("transition_hazard_20d"),
                "transition_hazard_60d": hist.get("transition_hazard_60d"),
                "transition_hazard_120d": hist.get("transition_hazard_120d"),
                "transition_expected_5d": hist.get("transition_expected_5d", "UNKNOWN"),
                "transition_expected_10d": hist.get("transition_expected_10d", "UNKNOWN"),
                "transition_expected_20d": hist.get("transition_expected_20d", "UNKNOWN"),
                "transition_expected_60d": hist.get("transition_expected_60d", "UNKNOWN"),
                "transition_expected_120d": hist.get("transition_expected_120d", "UNKNOWN"),
                "evidence_axis_macro": evidence_axis_macro,
                "evidence_axis_price": evidence_axis_price,
                "evidence_axis_flow": evidence_axis_flow,
                "evidence_axis_sentiment": evidence_axis_sentiment,
                "evidence_quality_score": None,
                "evidence_unknown_ratio": unknown,
                "diag_12slot_coverage": coverage,
                "diag_12slot_quality": quality,
                "horizon_bias_diversity_count": diversity_count,
                "horizon_bias_diversity_ratio_60d": None,
                "horizon_conf_spread": round(float(conf_spread), 4),
                "source_run_id": run_id,
            }
        )

    out = pd.DataFrame(rows).sort_values("trade_date").reset_index(drop=True)
    # Gate B: row 시점 기준 과거 60개(행 기준)만 사용, look-ahead 금지.
    if not out.empty:
        div_flag = (out["horizon_bias_diversity_count"].fillna(1) >= 2).astype(float)
        out["horizon_bias_diversity_ratio_60d"] = (
            div_flag.rolling(window=60, min_periods=1).mean().round(4)
        )
    out = out.reindex(columns=NEXT_STEP_SIGNAL_COLUMNS)
    return out
