from __future__ import annotations

from datetime import date

import pandas as pd

from pretrend.pipeline.strategy_engine.next_step.engine import build_next_step_signal


def test_build_next_step_signal_outputs_required_columns() -> None:
    ahs = pd.DataFrame(
        [
            {
                "trade_date": date(2026, 2, 20),
                "long_phase": "EXPANSION",
                "mid_regime": "RISK_ON",
                "short_signal": "RELIEF",
                "long_detail_json": '{"regime_mode":"neutral","delta_6m_z_mean":-0.13,"z_threshold":0.3}',
                "mid_detail_json": '{"price_signal":"RISK_ON","breadth_signal":"RISK_OFF","breadth_spread":-0.02}',
                "short_detail_json": '{"primary_relief":true,"risk_on_confirm":false}',
            }
        ]
    )
    mp = pd.DataFrame([{"trade_date": date(2026, 2, 20)}])

    out = build_next_step_signal(ahs, mp, run_id="r1")

    assert not out.empty
    assert {
        "bias_1m",
        "bias_3m",
        "diag_12slot_coverage",
        "evidence_axis_macro",
        "state_age_days",
        "sojourn_prob_10d",
        "transition_hazard_10d",
        "transition_expected",
    }.issubset(set(out.columns))
    assert out.iloc[0]["source_run_id"] == "r1"


def test_build_next_step_signal_fail_open_when_detail_missing() -> None:
    ahs = pd.DataFrame(
        [
            {
                "trade_date": date(2026, 2, 20),
                "long_phase": "UNKNOWN",
                "mid_regime": "UNKNOWN",
                "short_signal": "UNKNOWN",
                "long_detail_json": None,
                "mid_detail_json": None,
                "short_detail_json": None,
            }
        ]
    )

    out = build_next_step_signal(ahs, pd.DataFrame(), run_id="r2")
    row = out.iloc[0]

    assert row["evidence_axis_macro"] == "영향 근거 없음"
    assert row["evidence_axis_price"] == "영향 근거 없음"
    assert row["evidence_axis_flow"] == "영향 근거 없음"
    assert row["evidence_axis_sentiment"] == "영향 근거 없음"
    assert row["evidence_unknown_ratio"] == 1.0


def test_build_next_step_signal_hazard_probabilities_within_bounds() -> None:
    # 동일 상태 구간이 반복되도록 8행 생성 (소표본 fail-open 구간 포함)
    rows = []
    seq = [
        ("EXPANSION", "RISK_ON", "RELIEF"),
        ("EXPANSION", "RISK_ON", "RELIEF"),
        ("RECESSION", "RISK_OFF", "PANIC"),
        ("RECESSION", "RISK_OFF", "PANIC"),
        ("EXPANSION", "RISK_ON", "RELIEF"),
        ("EXPANSION", "RISK_ON", "RELIEF"),
        ("RECESSION", "RISK_OFF", "PANIC"),
        ("RECESSION", "RISK_OFF", "PANIC"),
    ]
    for i, s in enumerate(seq):
        rows.append(
            {
                "trade_date": date(2026, 1, 1 + i),
                "long_phase": s[0],
                "mid_regime": s[1],
                "short_signal": s[2],
                "long_detail_json": "{}",
                "mid_detail_json": "{}",
                "short_detail_json": "{}",
            }
        )
    ahs = pd.DataFrame(rows)
    out = build_next_step_signal(ahs, pd.DataFrame(), run_id="r3")

    assert "state_age_days" in out.columns
    assert out["state_age_days"].notna().any()
    # None(초기 fail-open) 또는 [0,1] 범위를 만족해야 한다.
    for col in ["sojourn_prob_5d", "sojourn_prob_10d", "sojourn_prob_20d",
                "transition_hazard_5d", "transition_hazard_10d", "transition_hazard_20d"]:
        vals = out[col].dropna()
        assert ((vals >= 0.0) & (vals <= 1.0)).all()
