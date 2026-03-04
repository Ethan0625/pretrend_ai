from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

_RULE_FEATURES = (
    "macro_hawkish_score",
    "filing_risk_burst",
    "policy_uncertainty_idx",
)


@dataclass
class TextFeatureSnapshot:
    trade_date: date
    rule_values: Dict[str, Optional[float]]
    rule_coverage_ratio: float
    llm_doc_count_5d: int
    llm_tone_mean_5d: Optional[float]
    top_topics_json: str
    top_tags_json: str
    latest_summary: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["trade_date"] = self.trade_date
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


def _safe_json_list(raw: Any) -> List[Dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [x for x in parsed if isinstance(x, dict)]
        except Exception:
            return []
    return []


def _rolling_trade_dates(all_dates: Sequence[date], trade_date: date, lookback: int = 5) -> List[date]:
    elig = [d for d in all_dates if d <= trade_date]
    return elig[-lookback:]


def _weighted_mean(values: Iterable[tuple[Optional[float], Optional[float]]]) -> Optional[float]:
    pairs = [(v, w if w is not None else 0.0) for v, w in values if v is not None]
    pairs = [(v, w) for v, w in pairs if w > 0]
    if not pairs:
        return None
    total_w = sum(w for _, w in pairs)
    if total_w <= 0:
        return None
    return sum(v * w for v, w in pairs) / total_w


def prepare_text_feature_groups(
    raw_df: pd.DataFrame,
) -> Tuple[pd.DataFrame, Dict[date, pd.DataFrame], List[date]]:
    """Normalize Gold Text rows once and group them by trade_date."""
    if raw_df is None or raw_df.empty:
        empty = pd.DataFrame()
        return empty, {}, []

    x = raw_df.copy()
    if "trade_date" in x.columns:
        x["trade_date"] = pd.to_datetime(x["trade_date"], errors="coerce").dt.date
    x = x[x["trade_date"].notna()].reset_index(drop=True)
    if x.empty:
        return x, {}, []

    grouped = {td: df.reset_index(drop=True) for td, df in x.groupby("trade_date", sort=True)}
    ordered_dates = sorted(grouped)
    return x, grouped, ordered_dates


def aggregate_text_features(
    raw_df: pd.DataFrame,
    trade_date: date,
    *,
    all_trade_dates: Optional[Sequence[date]] = None,
    grouped_by_trade_date: Optional[Dict[date, pd.DataFrame]] = None,
) -> TextFeatureSnapshot:
    """Aggregate rule-based + LLM Gold Text into a daily overlay snapshot."""
    if raw_df is None or raw_df.empty:
        return TextFeatureSnapshot(
            trade_date=trade_date,
            rule_values={name: None for name in _RULE_FEATURES},
            rule_coverage_ratio=0.0,
            llm_doc_count_5d=0,
            llm_tone_mean_5d=None,
            top_topics_json="[]",
            top_tags_json="[]",
            latest_summary=None,
        )

    if grouped_by_trade_date is None:
        x, grouped_by_trade_date, grouped_dates = prepare_text_feature_groups(raw_df)
    else:
        x = raw_df
        grouped_dates = sorted(grouped_by_trade_date)

    day_df = grouped_by_trade_date.get(trade_date, x.iloc[0:0])
    rule_values: Dict[str, Optional[float]] = {}
    rule_coverages: List[float] = []
    for feature in _RULE_FEATURES:
        hit = day_df[day_df["feature_name"] == feature]
        if hit.empty:
            rule_values[feature] = None
            continue
        last = hit.iloc[-1]
        rule_values[feature] = _safe_float(last.get("feature_value"))
        cov = _safe_float(last.get("coverage_ratio"))
        if cov is not None:
            rule_coverages.append(cov)

    rule_coverage_ratio = float(pd.Series(rule_coverages).median()) if rule_coverages else 0.0

    if all_trade_dates is None:
        all_trade_dates = grouped_dates
    lookback_dates = _rolling_trade_dates(list(all_trade_dates), trade_date, lookback=5)

    llm_parts = [
        grouped_by_trade_date[d]
        for d in lookback_dates
        if d in grouped_by_trade_date
    ]
    if llm_parts:
        llm_df = pd.concat(llm_parts, ignore_index=True)
        llm_df = llm_df[llm_df["feature_name"].isin(["llm_tone", "llm_topics", "llm_tags", "llm_summary"])].copy()
    else:
        llm_df = x.iloc[0:0].copy()

    tone_rows = llm_df[llm_df["feature_name"] == "llm_tone"]
    llm_tone_mean = _weighted_mean(
        (_safe_float(r.get("feature_value")), _safe_float(r.get("confidence")))
        for _, r in tone_rows.iterrows()
    )

    doc_ids = {
        str(v)
        for v in llm_df.get("doc_id", pd.Series(dtype=object)).dropna().tolist()
        if str(v)
    }

    topic_counter: Counter[tuple[str, str]] = Counter()
    tag_counter: Counter[tuple[str, str]] = Counter()
    for _, row in llm_df[llm_df["feature_name"].isin(["llm_topics", "llm_tags"])] .iterrows():
        items = _safe_json_list(row.get("feature_str"))
        for item in items:
            category = str(item.get("category", ""))
            value = str(item.get("item", ""))
            if not category or not value:
                continue
            if row["feature_name"] == "llm_topics":
                topic_counter[(category, value)] += 1
            else:
                tag_counter[(category, value)] += 1

    top_topics = [
        {"category": cat, "item": item, "count": cnt}
        for (cat, item), cnt in topic_counter.most_common(3)
    ]
    top_tags = [
        {"category": cat, "item": item, "count": cnt}
        for (cat, item), cnt in tag_counter.most_common(5)
    ]

    summary_rows = llm_df[llm_df["feature_name"] == "llm_summary"].sort_values("trade_date")
    latest_summary = None
    if not summary_rows.empty:
        latest = summary_rows.iloc[-1].get("feature_str")
        latest_summary = str(latest) if latest is not None else None

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
