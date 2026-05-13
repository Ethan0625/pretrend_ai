"""Build tactical asset-group transition signal.

Input source: strategy what_to_hold snapshot history.
Output grain: (trade_date, asset_group).
"""
from __future__ import annotations

from collections import Counter
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .schema import GROUP_TRANSITION_SIGNAL_COLUMNS

_TARGET_GROUPS = ("SECTOR", "COMMODITY", "BOND", "COUNTRY")
_HORIZONS = (5, 10, 20)


def _classify_group_state(rs_values: List[float]) -> Tuple[str, Optional[float]]:
    if len(rs_values) < 2:
        return "UNKNOWN", None
    s = pd.Series(rs_values, dtype=float)
    med = float(s.median())
    pos_ratio = float((s > 0).mean())
    if med > 0 and pos_ratio >= 0.5:
        state = "STRONG"
    elif med < 0 and pos_ratio < 0.4:
        state = "WEAK"
    else:
        state = "NEUTRAL"
    confidence = min(0.90, 0.40 + 0.10 * min(len(rs_values), 5))
    return state, confidence


def _build_group_states(universe_df: pd.DataFrame) -> pd.DataFrame:
    if universe_df is None or universe_df.empty:
        return pd.DataFrame(columns=["trade_date", "asset_group", "group_state_now", "group_confidence"])

    x = universe_df.copy()
    if "decision_date" in x.columns:
        x["trade_date"] = pd.to_datetime(x["decision_date"], errors="coerce").dt.date
    elif "rebalance_date" in x.columns:
        x["trade_date"] = pd.to_datetime(x["rebalance_date"], errors="coerce").dt.date
    elif "trade_date" in x.columns:
        x["trade_date"] = pd.to_datetime(x["trade_date"], errors="coerce").dt.date
    else:
        return pd.DataFrame(columns=["trade_date", "asset_group", "group_state_now", "group_confidence"])

    x = x[x["asset_group"].isin(_TARGET_GROUPS)]
    if "is_candidate" in x.columns:
        x = x[x["is_candidate"] == True]
    x = x.dropna(subset=["trade_date", "asset_group", "relative_strength"])
    if x.empty:
        return pd.DataFrame(columns=["trade_date", "asset_group", "group_state_now", "group_confidence"])

    rows: List[Dict] = []
    for (td, grp), g in x.groupby(["trade_date", "asset_group"]):
        rs_values = [float(v) for v in g["relative_strength"].tolist() if pd.notna(v)]
        state, conf = _classify_group_state(rs_values)
        rows.append(
            {
                "trade_date": td,
                "asset_group": str(grp),
                "group_state_now": state,
                "group_confidence": conf,
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(["asset_group", "trade_date"]).reset_index(drop=True)


def _build_group_transition(group_states: pd.DataFrame) -> pd.DataFrame:
    if group_states is None or group_states.empty:
        return pd.DataFrame(columns=GROUP_TRANSITION_SIGNAL_COLUMNS)

    rows: List[Dict] = []
    for grp, g in group_states.groupby("asset_group"):
        y = g.sort_values("trade_date").reset_index(drop=True).copy()
        y["state_key"] = y["group_state_now"].astype(str)

        episode_id: List[int] = []
        ep = -1
        prev = None
        for state in y["state_key"].tolist():
            if state != prev:
                ep += 1
            episode_id.append(ep)
            prev = state
        y["episode_id"] = episode_id
        y["idx"] = y.index
        y["episode_pos"] = y.groupby("episode_id").cumcount() + 1

        eps = (
            y.groupby("episode_id")
            .agg(
                duration=("idx", "size"),
                state_key=("state_key", "first"),
            )
            .reset_index()
        )
        eps["next_state"] = eps["episode_id"].map(
            eps.set_index("episode_id")["state_key"].shift(-1)
        )

        for _, r in y.iterrows():
            cur_ep = int(r["episode_id"])
            cur_state = str(r["state_key"])
            age = int(r["episode_pos"])

            prior = eps[(eps["state_key"] == cur_state) & (eps["episode_id"] < cur_ep)]
            if len(prior) < 3:
                soj = {h: None for h in _HORIZONS}
                hz = {h: None for h in _HORIZONS}
                exp = {h: "UNKNOWN" for h in _HORIZONS}
            else:
                durations = prior["duration"].tolist()
                next_states = [str(s) for s in prior["next_state"].tolist() if isinstance(s, str)]
                expected = Counter(next_states).most_common(1)[0][0] if next_states else "UNKNOWN"

                soj = {}
                hz = {}
                at_risk = [d for d in durations if d > age]
                for h in _HORIZONS:
                    if not at_risk:
                        soj[h] = None
                        hz[h] = None
                    else:
                        survived = sum(1 for d in at_risk if d > (age + h))
                        p = survived / len(at_risk)
                        soj[h] = p
                        hz[h] = 1.0 - p
                exp = {h: expected for h in _HORIZONS}

            rows.append(
                {
                    "trade_date": r["trade_date"],
                    "asset_group": grp,
                    "group_state_now": cur_state,
                    "group_expected_5d": exp[5],
                    "group_expected_10d": exp[10],
                    "group_expected_20d": exp[20],
                    "group_sojourn_prob_5d": soj[5],
                    "group_sojourn_prob_10d": soj[10],
                    "group_sojourn_prob_20d": soj[20],
                    "group_transition_hazard_5d": hz[5],
                    "group_transition_hazard_10d": hz[10],
                    "group_transition_hazard_20d": hz[20],
                    "group_confidence": r.get("group_confidence"),
                }
            )

    out = pd.DataFrame(rows, columns=[c for c in GROUP_TRANSITION_SIGNAL_COLUMNS if c != "source_run_id"])
    return out.sort_values(["trade_date", "asset_group"]).reset_index(drop=True)


def build_group_transition_signal(
    universe_history_df: pd.DataFrame,
    *,
    run_id: str,
) -> pd.DataFrame:
    """Build group_transition_signal frame from what_to_hold history."""
    states = _build_group_states(universe_history_df)
    out = _build_group_transition(states)
    if out.empty:
        return pd.DataFrame(columns=GROUP_TRANSITION_SIGNAL_COLUMNS)
    out["source_run_id"] = run_id
    return out[GROUP_TRANSITION_SIGNAL_COLUMNS]

