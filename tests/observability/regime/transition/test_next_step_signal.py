from __future__ import annotations

from pretrend.observability.explainability.context import (
    build_evidence_lines as _build_evidence_lines,
)
from pretrend.observability.regime.transition.engine import build_next_step_signal
import pandas as pd
from datetime import date


def test_next_step_signal_generates_4axis_evidence_lines() -> None:
    lines = _build_evidence_lines(
        {"regime_mode": "neutral", "delta_6m_z_mean": -0.13, "z_threshold": 0.3},
        {"price_signal": "RISK_ON", "breadth_signal": "RISK_OFF", "breadth_spread": -0.02},
        {"primary_relief": True, "risk_on_confirm": False},
    )
    text = "\n".join(lines)
    assert "🏛️매크로,정책" in text
    assert "💵가격" in text
    assert "📈수급/구조" in text
    assert "💕심리" in text


def test_next_step_signal_evidence_fail_open_when_missing() -> None:
    lines = _build_evidence_lines({}, {}, {})
    text = "\n".join(lines)
    assert text.count("영향 근거 없음") == 4


def test_next_step_signal_bias_differs_by_horizon() -> None:
    ahs = pd.DataFrame(
        [
            {
                "trade_date": date(2026, 2, 20),
                "long_phase": "EXPANSION",
                "mid_regime": "RISK_OFF",
                "short_signal": "RELIEF",
                "long_detail_json": "{}",
                "mid_detail_json": "{}",
                "short_detail_json": "{}",
            }
        ]
    )
    out = build_next_step_signal(ahs, pd.DataFrame(), run_id="r_bias")
    row = out.iloc[0]

    assert row["bias_5d"] == "RISK_ON_BIAS"
    assert row["bias_60d"] == "NEUTRAL_BIAS"
    assert "horizon_bias_diversity_count" in out.columns
    assert "horizon_bias_diversity_ratio_60d" in out.columns
    assert "horizon_conf_spread" in out.columns
