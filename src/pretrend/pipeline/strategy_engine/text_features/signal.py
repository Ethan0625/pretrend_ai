from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import pandas as pd

from .aggregator import TextFeatureSnapshot, prepare_text_feature_groups

TEXT_OVERLAY_SIGNAL_COLUMNS = [
    "trade_date",
    "text_signal_state",
    "text_signal_confidence",
    "text_rule_coverage_ratio",
    "text_llm_doc_count_5d",
    "text_tone_mean_5d",
    "text_top_topics_json",
    "text_top_tags_json",
    "text_latest_summary",
    "text_overlay_reason",
    "source_run_id",
]

_RISK_OFF_TAGS = {
    "hike", "qt", "guidance_raise", "downgrade", "default",
    "spread_widening", "liquidity_crunch", "bank_run", "crash",
    "correction", "capitulation", "volatility_spike", "risk_off",
}
_RISK_ON_TAGS = {"cut", "qe", "guidance_cut", "fiscal_stimulus", "risk_on"}
_RULE_FEATURES = (
    "macro_hawkish_score",
    "filing_risk_burst",
    "policy_uncertainty_idx",
)


@dataclass
class TextSignal:
    state: str
    confidence: float
    score: float
    reason: str
    evidence: Dict[str, Any]

    def to_row(self, snapshot: TextFeatureSnapshot, run_id: str) -> Dict[str, Any]:
        return {
            "trade_date": snapshot.trade_date,
            "text_signal_state": self.state,
            "text_signal_confidence": self.confidence,
            "text_rule_coverage_ratio": snapshot.rule_coverage_ratio,
            "text_llm_doc_count_5d": snapshot.llm_doc_count_5d,
            "text_tone_mean_5d": snapshot.llm_tone_mean_5d,
            "text_top_topics_json": snapshot.top_topics_json,
            "text_top_tags_json": snapshot.top_tags_json,
            "text_latest_summary": snapshot.latest_summary,
            "text_overlay_reason": self.reason,
            "source_run_id": run_id,
        }


def _safe_json_items(raw: Any) -> List[str]:
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    out: List[str] = []
    for item in parsed:
        if isinstance(item, dict) and item.get("item"):
            out.append(str(item["item"]))
    return out


def _safe_float(val: Any) -> Optional[float]:
    try:
        if val is None:
            return None
        f = float(val)
        if f != f:
            return None
        return f
    except Exception:
        return None


def _safe_json_dict_items(raw: Any) -> List[Tuple[str, str]]:
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    out: List[Tuple[str, str]] = []
    for item in parsed:
        if isinstance(item, dict) and item.get("category") and item.get("item"):
            out.append((str(item["category"]), str(item["item"])))
    return out


def _weighted_mean(pairs: Iterable[Tuple[Optional[float], Optional[float]]]) -> Optional[float]:
    clean = [(v, w if w is not None else 0.0) for v, w in pairs if v is not None]
    clean = [(v, w) for v, w in clean if w > 0]
    if not clean:
        return None
    total_w = sum(w for _, w in clean)
    if total_w <= 0:
        return None
    return sum(v * w for v, w in clean) / total_w


def _precompute_daily_maps(
    grouped_by_trade_date: Dict[date, pd.DataFrame],
) -> Dict[str, Dict[date, Any]]:
    rule_values_by_date: Dict[date, Dict[str, Optional[float]]] = {}
    rule_cov_by_date: Dict[date, float] = {}
    tone_pairs_by_date: Dict[date, List[Tuple[Optional[float], Optional[float]]]] = {}
    doc_ids_by_date: Dict[date, Set[str]] = {}
    topic_counter_by_date: Dict[date, Counter[Tuple[str, str]]] = {}
    tag_counter_by_date: Dict[date, Counter[Tuple[str, str]]] = {}
    latest_summary_by_date: Dict[date, Optional[str]] = {}

    for td, day_df in grouped_by_trade_date.items():
        rule_values: Dict[str, Optional[float]] = {name: None for name in _RULE_FEATURES}
        rule_covs: List[float] = []
        for feature in _RULE_FEATURES:
            hit = day_df[day_df["feature_name"] == feature]
            if hit.empty:
                continue
            last = hit.iloc[-1]
            rule_values[feature] = _safe_float(last.get("feature_value"))
            cov = _safe_float(last.get("coverage_ratio"))
            if cov is not None:
                rule_covs.append(cov)
        rule_values_by_date[td] = rule_values
        rule_cov_by_date[td] = round(float(pd.Series(rule_covs).median()), 4) if rule_covs else 0.0

        llm_df = day_df[day_df["feature_name"].isin(["llm_tone", "llm_topics", "llm_tags", "llm_summary"])]
        tone_rows = llm_df[llm_df["feature_name"] == "llm_tone"]
        tone_pairs_by_date[td] = [
            (_safe_float(r.get("feature_value")), _safe_float(r.get("confidence")))
            for _, r in tone_rows.iterrows()
        ]
        doc_ids_by_date[td] = {
            str(v)
            for v in llm_df.get("doc_id", pd.Series(dtype=object)).dropna().tolist()
            if str(v)
        }

        topic_counter: Counter[Tuple[str, str]] = Counter()
        tag_counter: Counter[Tuple[str, str]] = Counter()
        for _, row in llm_df[llm_df["feature_name"].isin(["llm_topics", "llm_tags"])].iterrows():
            items = _safe_json_dict_items(row.get("feature_str"))
            for key in items:
                if row["feature_name"] == "llm_topics":
                    topic_counter[key] += 1
                else:
                    tag_counter[key] += 1
        topic_counter_by_date[td] = topic_counter
        tag_counter_by_date[td] = tag_counter

        summary_rows = llm_df[llm_df["feature_name"] == "llm_summary"]
        latest_summary_by_date[td] = None
        if not summary_rows.empty:
            latest = summary_rows.iloc[-1].get("feature_str")
            latest_summary_by_date[td] = str(latest) if latest is not None else None

    return {
        "rule_values": rule_values_by_date,
        "rule_cov": rule_cov_by_date,
        "tone_pairs": tone_pairs_by_date,
        "doc_ids": doc_ids_by_date,
        "topic_counter": topic_counter_by_date,
        "tag_counter": tag_counter_by_date,
        "latest_summary": latest_summary_by_date,
    }


def _build_snapshot_from_maps(
    trade_date: date,
    window_dates: Sequence[date],
    daily_maps: Dict[str, Dict[date, Any]],
) -> TextFeatureSnapshot:
    rule_values = daily_maps["rule_values"].get(trade_date, {name: None for name in _RULE_FEATURES})
    rule_coverage_ratio = float(daily_maps["rule_cov"].get(trade_date, 0.0))

    tone_pairs: List[Tuple[Optional[float], Optional[float]]] = []
    doc_ids: Set[str] = set()
    topic_counter: Counter[Tuple[str, str]] = Counter()
    tag_counter: Counter[Tuple[str, str]] = Counter()
    latest_summary: Optional[str] = None

    for d in window_dates:
        tone_pairs.extend(daily_maps["tone_pairs"].get(d, []))
        doc_ids.update(daily_maps["doc_ids"].get(d, set()))
        topic_counter.update(daily_maps["topic_counter"].get(d, Counter()))
        tag_counter.update(daily_maps["tag_counter"].get(d, Counter()))
        summary = daily_maps["latest_summary"].get(d)
        if summary:
            latest_summary = summary

    top_topics = [
        {"category": cat, "item": item, "count": cnt}
        for (cat, item), cnt in topic_counter.most_common(3)
    ]
    top_tags = [
        {"category": cat, "item": item, "count": cnt}
        for (cat, item), cnt in tag_counter.most_common(5)
    ]
    llm_tone_mean = _weighted_mean(tone_pairs)

    return TextFeatureSnapshot(
        trade_date=trade_date,
        rule_values=rule_values,
        rule_coverage_ratio=round(rule_coverage_ratio, 4),
        llm_doc_count_5d=len(doc_ids),
        llm_tone_mean_5d=round(llm_tone_mean, 4) if llm_tone_mean is not None else None,
        top_topics_json=json.dumps(top_topics, ensure_ascii=True),
        top_tags_json=json.dumps(top_tags, ensure_ascii=True),
        latest_summary=latest_summary,
    )


def compute_text_signal(snapshot: TextFeatureSnapshot) -> TextSignal:
    if snapshot.rule_coverage_ratio < 0.5:
        return TextSignal(
            state="UNKNOWN",
            confidence=0.0,
            score=0.0,
            reason="RULE_COVERAGE_LOW",
            evidence={},
        )

    score = 0.0
    reasons: List[str] = []
    rule_values = snapshot.rule_values

    hawkish = rule_values.get("macro_hawkish_score")
    if hawkish is not None and hawkish >= 0.60:
        score -= 1.0
        reasons.append("macro_hawkish_high")
    elif hawkish is not None and hawkish <= 0.35:
        score += 1.0
        reasons.append("macro_hawkish_low")

    filing = rule_values.get("filing_risk_burst")
    if filing is not None and filing >= 2.0:
        score -= 1.0
        reasons.append("filing_risk_burst")

    uncertainty = rule_values.get("policy_uncertainty_idx")
    if uncertainty is not None and uncertainty >= 0.70:
        score -= 1.0
        reasons.append("policy_uncertainty_high")
    elif uncertainty is not None and uncertainty <= 0.30:
        score += 0.5
        reasons.append("policy_uncertainty_low")

    tone = snapshot.llm_tone_mean_5d
    if tone is not None and tone >= 0.25:
        score -= 1.0
        reasons.append("llm_hawkish")
    elif tone is not None and tone <= -0.25:
        score += 1.0
        reasons.append("llm_dovish")

    tags = set(_safe_json_items(snapshot.top_tags_json))
    off_hit = bool(tags & _RISK_OFF_TAGS)
    on_hit = bool(tags & _RISK_ON_TAGS)
    if off_hit and not on_hit:
        score -= 1.0
        reasons.append("tag_risk_off")
    elif on_hit and not off_hit:
        score += 1.0
        reasons.append("tag_risk_on")

    if score >= 1.5:
        state = "RISK_ON"
    elif score <= -1.5:
        state = "RISK_OFF"
    else:
        state = "NEUTRAL"

    confidence = min(
        0.95,
        0.5 * float(snapshot.rule_coverage_ratio)
        + 0.5 * min(1.0, float(snapshot.llm_doc_count_5d) / 3.0),
    )
    return TextSignal(
        state=state,
        confidence=round(confidence, 4),
        score=round(score, 4),
        reason="|".join(reasons) if reasons else "NO_TEXT_EDGE",
        evidence={
            "rule_values": dict(snapshot.rule_values),
            "llm_tone_mean_5d": snapshot.llm_tone_mean_5d,
            "top_tags": _safe_json_items(snapshot.top_tags_json),
            "top_topics": _safe_json_items(snapshot.top_topics_json),
        },
    )


def build_text_overlay_signal(
    raw_df: pd.DataFrame,
    trade_dates: Sequence[date],
    *,
    run_id: str,
) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    ordered_dates = sorted({d for d in trade_dates if d is not None})
    normalized_df, grouped_by_trade_date, grouped_dates = prepare_text_feature_groups(raw_df)
    daily_maps = _precompute_daily_maps(grouped_by_trade_date)
    for idx, td in enumerate(ordered_dates):
        window_dates = ordered_dates[max(0, idx - 4): idx + 1]
        snapshot = _build_snapshot_from_maps(
            td,
            window_dates if window_dates else grouped_dates,
            daily_maps,
        )
        signal = compute_text_signal(snapshot)
        rows.append(signal.to_row(snapshot, run_id=run_id))

    if not rows:
        return pd.DataFrame(columns=TEXT_OVERLAY_SIGNAL_COLUMNS)
    out = pd.DataFrame(rows)
    for col in TEXT_OVERLAY_SIGNAL_COLUMNS:
        if col not in out.columns:
            out[col] = None
    return out[TEXT_OVERLAY_SIGNAL_COLUMNS]
