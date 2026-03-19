from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from pandas.testing import assert_frame_equal

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
        "bias_5d",
        "bias_10d",
        "bias_20d",
        "bias_60d",
        "bias_120d",
        "diag_12slot_coverage",
        "evidence_axis_macro",
        "state_age_days",
        "sojourn_prob_10d",
        "sojourn_prob_60d",
        "sojourn_prob_120d",
        "transition_hazard_10d",
        "transition_hazard_60d",
        "transition_hazard_120d",
        "transition_expected_10d",
        "transition_expected_60d",
        "transition_expected_120d",
        "bias_state_source",
        "bias_switch_flag",
        "bias_switch_reason",
        "bias_cooldown_left",
        "bias_candidate_20d",
        "cooldown_compressed_flag",
        "cooldown_compressed_reason",
        "hard_gate_exit_assist_flag",
        "hard_gate_exit_assist_reason",
        "horizon_bias_diversity_count",
        "horizon_bias_diversity_ratio_60d",
        "horizon_conf_spread",
    }.issubset(set(out.columns))
    assert "bias_1m" not in out.columns
    assert "bias_3m" not in out.columns
    assert "transition_expected" not in out.columns
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
    for col in [
        "sojourn_prob_5d", "sojourn_prob_10d", "sojourn_prob_20d", "sojourn_prob_60d", "sojourn_prob_120d",
        "transition_hazard_5d", "transition_hazard_10d", "transition_hazard_20d",
        "transition_hazard_60d", "transition_hazard_120d",
    ]:
        vals = out[col].dropna()
        assert ((vals >= 0.0) & (vals <= 1.0)).all()


def test_build_next_step_signal_confidence_reflects_agreement() -> None:
    ahs = pd.DataFrame(
        [
            {
                "trade_date": date(2026, 2, 20),
                "long_phase": "RECESSION",
                "mid_regime": "RISK_OFF",
                "short_signal": "PANIC",
                "long_detail_json": "{}",
                "mid_detail_json": "{}",
                "short_detail_json": "{}",
            },
            {
                "trade_date": date(2026, 2, 21),
                "long_phase": "EXPANSION",
                "mid_regime": "RISK_OFF",
                "short_signal": "RELIEF",
                "long_detail_json": "{}",
                "mid_detail_json": "{}",
                "short_detail_json": "{}",
            },
        ]
    )

    out = build_next_step_signal(ahs, pd.DataFrame(), run_id="r4")
    agree = out.iloc[0]
    mixed = out.iloc[1]

    # 합의도 높은 케이스(동일 방향) confidence가 혼합 신호보다 높아야 한다.
    assert float(agree["confidence_10d"]) > float(mixed["confidence_10d"])
    assert float(agree["confidence_5d"]) >= 0.50
    assert float(agree["confidence_60d"]) >= 0.40


def test_build_next_step_signal_recovery_baseline_is_risk_on() -> None:
    ahs = pd.DataFrame(
        [
            {
                "trade_date": date(2026, 2, 23),  # Monday
                "long_phase": "RECOVERY",
                "mid_regime": "NEUTRAL",
                "short_signal": "STABLE",
                "long_detail_json": "{}",
                "mid_detail_json": "{}",
                "short_detail_json": "{}",
            }
        ]
    )
    mp = pd.DataFrame([{"trade_date": date(2026, 2, 23), "run_universe": True, "risk_gate": True}])
    out = build_next_step_signal(ahs, mp, run_id="r5")
    row = out.iloc[0]
    assert row["bias_20d"] == "RISK_ON_BIAS"
    assert row["bias_state_source"] in {"BASELINE", "OVERLAY"}


def test_build_next_step_signal_weekly_only_holds_non_monday() -> None:
    ahs = pd.DataFrame(
        [
            {
                "trade_date": date(2026, 2, 23),  # Monday
                "long_phase": "EXPANSION",
                "mid_regime": "RISK_ON",
                "short_signal": "RELIEF",
                "long_detail_json": "{}",
                "mid_detail_json": "{}",
                "short_detail_json": "{}",
            },
            {
                "trade_date": date(2026, 2, 24),  # Tuesday
                "long_phase": "EXPANSION",
                "mid_regime": "RISK_OFF",
                "short_signal": "PANIC",
                "long_detail_json": "{}",
                "mid_detail_json": "{}",
                "short_detail_json": "{}",
            },
        ]
    )
    mp = pd.DataFrame(
        [
            {"trade_date": date(2026, 2, 23), "run_universe": True, "risk_gate": True},
            {"trade_date": date(2026, 2, 24), "run_universe": True, "risk_gate": True},
        ]
    )
    out = build_next_step_signal(ahs, mp, run_id="r6").sort_values("trade_date")
    mon = out.iloc[0]
    tue = out.iloc[1]
    assert mon["bias_20d"] == tue["bias_20d"]
    assert tue["bias_state_source"] in {"HOLD_COOLDOWN", "BASELINE"}


def test_build_next_step_signal_sets_compression_flag_on_hold_cooldown() -> None:
    ahs = pd.DataFrame(
        [
            {
                "trade_date": date(2026, 2, 20),  # Friday, hard-gate OFF state
                "long_phase": "RECESSION",
                "mid_regime": "RISK_OFF",
                "short_signal": "PANIC",
                "long_detail_json": "{}",
                "mid_detail_json": "{}",
                "short_detail_json": "{}",
            },
            {
                "trade_date": date(2026, 2, 23),  # Monday, switch to ON
                "long_phase": "EXPANSION",
                "mid_regime": "RISK_ON",
                "short_signal": "RELIEF",
                "long_detail_json": "{}",
                "mid_detail_json": "{}",
                "short_detail_json": "{}",
            },
            {
                "trade_date": date(2026, 2, 24),  # Tuesday, cooldown hold
                "long_phase": "EXPANSION",
                "mid_regime": "RISK_ON",
                "short_signal": "RELIEF",
                "long_detail_json": "{}",
                "mid_detail_json": "{}",
                "short_detail_json": "{}",
            },
        ]
    )
    mp = pd.DataFrame(
        [
            {"trade_date": date(2026, 2, 20), "run_universe": False, "risk_gate": True, "short_signal": "PANIC"},
            {"trade_date": date(2026, 2, 23), "run_universe": True, "risk_gate": True, "short_signal": "RELIEF"},
            {"trade_date": date(2026, 2, 24), "run_universe": True, "risk_gate": True, "short_signal": "RELIEF"},
        ]
    )
    out = build_next_step_signal(ahs, mp, run_id="r8").sort_values("trade_date")
    tue = out.iloc[2]
    assert tue["bias_state_source"] == "HOLD_COOLDOWN"
    assert bool(tue["cooldown_compressed_flag"]) is True
    assert str(tue["cooldown_compressed_reason"]) in {"MID_RISK_ON", "RELIEF_STREAK"}


def test_build_next_step_signal_hard_gate_run_universe_forces_off() -> None:
    ahs = pd.DataFrame(
        [
            {
                "trade_date": date(2026, 2, 23),  # Monday
                "long_phase": "RECOVERY",
                "mid_regime": "RISK_ON",
                "short_signal": "RELIEF",
                "long_detail_json": "{}",
                "mid_detail_json": "{}",
                "short_detail_json": "{}",
            }
        ]
    )
    mp = pd.DataFrame([{"trade_date": date(2026, 2, 23), "run_universe": False, "risk_gate": True}])
    out = build_next_step_signal(ahs, mp, run_id="r7")
    row = out.iloc[0]
    assert row["bias_20d"] == "RISK_OFF_BIAS"
    assert row["bias_state_source"] == "HARD_GATE"


def test_build_next_step_signal_sets_hard_gate_exit_assist_flag() -> None:
    ahs = pd.DataFrame(
        [
            {
                "trade_date": date(2026, 2, 21),
                "long_phase": "RECESSION",
                "mid_regime": "NEUTRAL",
                "short_signal": "RELIEF",
                "long_detail_json": "{}",
                "mid_detail_json": "{}",
                "short_detail_json": "{}",
            },
            {
                "trade_date": date(2026, 2, 22),
                "long_phase": "RECESSION",
                "mid_regime": "NEUTRAL",
                "short_signal": "RELIEF",
                "long_detail_json": "{}",
                "mid_detail_json": "{}",
                "short_detail_json": "{}",
            },
        ]
    )
    mp = pd.DataFrame(
        [
            {"trade_date": date(2026, 2, 21), "run_universe": False, "risk_gate": True},
            {"trade_date": date(2026, 2, 22), "run_universe": True, "risk_gate": True},
        ]
    )
    out = build_next_step_signal(ahs, mp, run_id="r9").sort_values("trade_date")
    row = out.iloc[1]
    assert bool(row["hard_gate_exit_assist_flag"]) is True
    assert str(row["hard_gate_exit_assist_reason"]) == "RUN_UNIVERSE_RECOVERY_RELIEF"


def test_build_next_step_signal_horizon_diversification_exists() -> None:
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
    out = build_next_step_signal(ahs, pd.DataFrame(), run_id="r10")
    row = out.iloc[0]
    biases = {row["bias_5d"], row["bias_10d"], row["bias_20d"], row["bias_60d"], row["bias_120d"]}
    assert len(biases) >= 2


def test_build_next_step_signal_hazard_penalty_makes_bias_more_conservative() -> None:
    base = {
        "trade_date": date(2026, 2, 20),
        "long_phase": "EXPANSION",
        "mid_regime": "RISK_ON",
        "short_signal": "RELIEF",
        "long_detail_json": "{}",
        "mid_detail_json": "{}",
        "short_detail_json": "{}",
    }
    # low hazard path
    ahs_low = pd.DataFrame([base] * 1)
    out_low = build_next_step_signal(ahs_low, pd.DataFrame(), run_id="r11")

    # high hazard path by creating history with short past episodes
    seq = []
    for i in range(10):
        seq.append(
            {
                "trade_date": date(2026, 2, 1 + i),
                "long_phase": "EXPANSION" if i % 2 == 0 else "RECESSION",
                "mid_regime": "RISK_ON" if i % 2 == 0 else "RISK_OFF",
                "short_signal": "RELIEF" if i % 2 == 0 else "PANIC",
                "long_detail_json": "{}",
                "mid_detail_json": "{}",
                "short_detail_json": "{}",
            }
        )
    ahs_high = pd.DataFrame(seq + [base])
    out_high = build_next_step_signal(ahs_high, pd.DataFrame(), run_id="r12")
    row_low = out_low.iloc[-1]
    row_high = out_high.iloc[-1]
    # high hazard should not be more aggressive than low hazard for 10D.
    rank = {"RISK_OFF_BIAS": -1, "NEUTRAL_BIAS": 0, "RISK_ON_BIAS": 1, "UNKNOWN": 0}
    assert rank[str(row_high["bias_10d"])] <= rank[str(row_low["bias_10d"])]


def test_build_next_step_signal_state_age_damping_changes_edge_horizons() -> None:
    rows = []
    for i in range(3):
        rows.append(
            {
                "trade_date": date(2026, 2, 20 + i),
                "long_phase": "EXPANSION",
                "mid_regime": "NEUTRAL",
                "short_signal": "PANIC",
                "long_detail_json": "{}",
                "mid_detail_json": "{}",
                "short_detail_json": "{}",
            }
        )
    out = build_next_step_signal(pd.DataFrame(rows), pd.DataFrame(), run_id="r13")
    early = out.iloc[0]  # age=1 (damping active)
    late = out.iloc[2]   # age=3 (damping inactive)
    assert float(early["confidence_5d"]) != float(late["confidence_5d"]) or float(early["confidence_120d"]) != float(late["confidence_120d"])


def test_build_next_step_signal_diagnostics_ranges_and_determinism() -> None:
    rows = []
    for i in range(80):
        rows.append(
            {
                "trade_date": date(2026, 1, 1) + timedelta(days=i),
                "long_phase": "EXPANSION" if i % 3 else "RECESSION",
                "mid_regime": "RISK_ON" if i % 2 else "RISK_OFF",
                "short_signal": "RELIEF" if i % 5 else "PANIC",
                "long_detail_json": "{}",
                "mid_detail_json": "{}",
                "short_detail_json": "{}",
            }
        )
    ahs = pd.DataFrame(rows)
    ahs["trade_date"] = pd.to_datetime(ahs["trade_date"]).dt.date
    out1 = build_next_step_signal(ahs, pd.DataFrame(), run_id="r14")
    out2 = build_next_step_signal(ahs, pd.DataFrame(), run_id="r14")
    assert_frame_equal(out1, out2)

    assert ((out1["horizon_bias_diversity_count"] >= 1) & (out1["horizon_bias_diversity_count"] <= 5)).all()
    assert ((out1["horizon_bias_diversity_ratio_60d"] >= 0.0) & (out1["horizon_bias_diversity_ratio_60d"] <= 1.0)).all()
    assert ((out1["horizon_conf_spread"] >= 0.0) & (out1["horizon_conf_spread"] <= 1.0)).all()


def test_build_next_step_signal_diversity_ratio_no_lookahead() -> None:
    rows = []
    for i in range(70):
        rows.append(
            {
                "trade_date": date(2026, 1, 1) + timedelta(days=i),
                "long_phase": "EXPANSION" if i % 4 else "RECESSION",
                "mid_regime": "RISK_ON" if i % 3 else "RISK_OFF",
                "short_signal": "RELIEF" if i % 2 else "PANIC",
                "long_detail_json": "{}",
                "mid_detail_json": "{}",
                "short_detail_json": "{}",
            }
        )
    base = pd.DataFrame(rows)
    base["trade_date"] = pd.to_datetime(base["trade_date"]).dt.date
    out_base = build_next_step_signal(base, pd.DataFrame(), run_id="r15")

    extra = base.copy()
    for j in range(10):
        extra.loc[len(extra)] = {
            "trade_date": date(2026, 4, 1) + timedelta(days=j),
            "long_phase": "RECOVERY",
            "mid_regime": "RISK_ON",
            "short_signal": "RELIEF",
            "long_detail_json": "{}",
            "mid_detail_json": "{}",
            "short_detail_json": "{}",
        }
    extra["trade_date"] = pd.to_datetime(extra["trade_date"]).dt.date
    out_extra = build_next_step_signal(extra, pd.DataFrame(), run_id="r15")
    assert_frame_equal(
        out_base[["trade_date", "horizon_bias_diversity_ratio_60d"]],
        out_extra.iloc[: len(out_base)][["trade_date", "horizon_bias_diversity_ratio_60d"]],
    )
