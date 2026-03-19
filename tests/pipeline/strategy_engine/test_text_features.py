from __future__ import annotations

from datetime import date

import pandas as pd

from pretrend.pipeline.strategy_engine.text_features.aggregator import aggregate_text_features
from pretrend.pipeline.strategy_engine.text_features.signal import build_text_overlay_signal, compute_text_signal


def _raw_text_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": date(2024, 6, 3),
                "feature_name": "macro_hawkish_score",
                "feature_value": 0.70,
                "coverage_ratio": 1.0,
                "feature_str": None,
                "doc_id": None,
                "confidence": None,
            },
            {
                "trade_date": date(2024, 6, 3),
                "feature_name": "filing_risk_burst",
                "feature_value": 2.1,
                "coverage_ratio": 1.0,
                "feature_str": None,
                "doc_id": None,
                "confidence": None,
            },
            {
                "trade_date": date(2024, 6, 3),
                "feature_name": "policy_uncertainty_idx",
                "feature_value": 0.75,
                "coverage_ratio": 1.0,
                "feature_str": None,
                "doc_id": None,
                "confidence": None,
            },
            {
                "trade_date": date(2024, 6, 3),
                "feature_name": "llm_tone",
                "feature_value": 1.0,
                "coverage_ratio": 1.0,
                "feature_str": None,
                "doc_id": "doc1",
                "confidence": 0.9,
            },
            {
                "trade_date": date(2024, 6, 3),
                "feature_name": "llm_tags",
                "feature_value": 0.0,
                "coverage_ratio": 1.0,
                "feature_str": '[{"category":"policy_action","item":"hike"}]',
                "doc_id": "doc1",
                "confidence": 0.9,
            },
            {
                "trade_date": date(2024, 6, 4),
                "feature_name": "macro_hawkish_score",
                "feature_value": 0.20,
                "coverage_ratio": 1.0,
                "feature_str": None,
                "doc_id": None,
                "confidence": None,
            },
            {
                "trade_date": date(2024, 6, 4),
                "feature_name": "filing_risk_burst",
                "feature_value": 0.0,
                "coverage_ratio": 1.0,
                "feature_str": None,
                "doc_id": None,
                "confidence": None,
            },
            {
                "trade_date": date(2024, 6, 4),
                "feature_name": "policy_uncertainty_idx",
                "feature_value": 0.20,
                "coverage_ratio": 1.0,
                "feature_str": None,
                "doc_id": None,
                "confidence": None,
            },
            {
                "trade_date": date(2024, 6, 4),
                "feature_name": "llm_tone",
                "feature_value": -1.0,
                "coverage_ratio": 1.0,
                "feature_str": None,
                "doc_id": "doc2",
                "confidence": 0.8,
            },
            {
                "trade_date": date(2024, 6, 4),
                "feature_name": "llm_tags",
                "feature_value": 0.0,
                "coverage_ratio": 1.0,
                "feature_str": '[{"category":"policy_action","item":"cut"}]',
                "doc_id": "doc2",
                "confidence": 0.8,
            },
        ]
    )


def test_aggregate_text_features_empty_input() -> None:
    snap = aggregate_text_features(pd.DataFrame(), date(2024, 6, 4), all_trade_dates=[date(2024, 6, 4)])
    assert snap.rule_coverage_ratio == 0.0
    assert snap.llm_doc_count_5d == 0
    assert snap.top_tags_json == "[]"


def test_aggregate_text_features_mixed_sources() -> None:
    snap = aggregate_text_features(_raw_text_df(), date(2024, 6, 4), all_trade_dates=[date(2024, 6, 3), date(2024, 6, 4)])
    assert snap.rule_coverage_ratio == 1.0
    assert snap.llm_doc_count_5d == 2
    assert snap.llm_tone_mean_5d is not None
    assert 'cut' in snap.top_tags_json or 'hike' in snap.top_tags_json


def test_compute_text_signal_risk_off_boundary() -> None:
    snap = aggregate_text_features(_raw_text_df(), date(2024, 6, 3), all_trade_dates=[date(2024, 6, 3)])
    signal = compute_text_signal(snap)
    assert signal.state == "RISK_OFF"
    assert signal.confidence > 0


def test_compute_text_signal_unknown_when_rule_coverage_low() -> None:
    raw = _raw_text_df().copy()
    raw.loc[raw["feature_name"] == "macro_hawkish_score", "coverage_ratio"] = 0.0
    raw.loc[raw["feature_name"] == "filing_risk_burst", "coverage_ratio"] = 0.0
    raw.loc[raw["feature_name"] == "policy_uncertainty_idx", "coverage_ratio"] = 0.0
    snap = aggregate_text_features(raw, date(2024, 6, 3), all_trade_dates=[date(2024, 6, 3)])
    signal = compute_text_signal(snap)
    assert signal.state == "UNKNOWN"


def test_build_text_overlay_signal_output_columns() -> None:
    out = build_text_overlay_signal(_raw_text_df(), [date(2024, 6, 3), date(2024, 6, 4)], run_id="rid")
    assert len(out) == 2
    assert {"text_signal_state", "text_signal_confidence", "text_top_tags_json", "source_run_id"}.issubset(out.columns)
    assert (out["source_run_id"] == "rid").all()
