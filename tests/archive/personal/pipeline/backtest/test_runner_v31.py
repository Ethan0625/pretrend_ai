from __future__ import annotations

from datetime import date

import pandas as pd

from pretrend.pipeline.backtest.runner import (
    _apply_group_transition_gate_v341,
    _get_hazard_threshold_10d,
    _resolve_v3_mode_flags,
    resolve_effective_bias_v32,
    resolve_monthly_locked_bias,
)
from pretrend.pipeline.backtest.config import BacktestConfig


def test_monthly_bias_lock_keeps_same_month_value() -> None:
    next_step_df = pd.DataFrame(
        [
            {"trade_date": date(2025, 1, 6), "bias_20d": "RISK_ON_BIAS"},
            {"trade_date": date(2025, 1, 20), "bias_20d": "RISK_OFF_BIAS"},
        ]
    )
    locked_month = (2025, 1)
    locked_bias = "RISK_ON_BIAS"

    new_month, new_bias = resolve_monthly_locked_bias(
        next_step_df=next_step_df,
        td=date(2025, 1, 28),
        locked_month=locked_month,
        locked_bias=locked_bias,
    )

    assert new_month == (2025, 1)
    assert new_bias == "RISK_ON_BIAS"


def test_monthly_bias_lock_refreshes_on_month_change() -> None:
    next_step_df = pd.DataFrame(
        [
            {"trade_date": date(2025, 1, 20), "bias_20d": "RISK_OFF_BIAS"},
            {"trade_date": date(2025, 2, 3), "bias_20d": "RISK_ON_BIAS"},
        ]
    )

    new_month, new_bias = resolve_monthly_locked_bias(
        next_step_df=next_step_df,
        td=date(2025, 2, 10),
        locked_month=(2025, 1),
        locked_bias="RISK_OFF_BIAS",
    )

    assert new_month == (2025, 2)
    assert new_bias == "RISK_ON_BIAS"


def test_v32_override_triggered_by_two_day_panic_streak() -> None:
    s1 = resolve_effective_bias_v32(
        locked_bias="RISK_ON_BIAS",
        short_signal="PANIC",
        mid_regime="NEUTRAL",
        panic_streak=0,
        risk_off_streak=0,
        override_days_left=0,
        override_bias="UNKNOWN",
        override_reason="NONE",
    )
    s2 = resolve_effective_bias_v32(
        locked_bias="RISK_ON_BIAS",
        short_signal="PANIC",
        mid_regime="NEUTRAL",
        panic_streak=s1[3],
        risk_off_streak=s1[4],
        override_days_left=s1[5],
        override_bias=s1[6],
        override_reason=s1[7],
    )
    assert s2[0] == "RISK_OFF_BIAS"
    assert s2[1] == "OVERRIDE"
    assert s2[2] == "PANIC"
    assert s2[5] == 5


def test_v32_override_triggered_by_three_day_risk_off_streak() -> None:
    s = ("RISK_ON_BIAS", "LOCKED", "NONE", 0, 0, 0, "UNKNOWN", "NONE")
    for _ in range(3):
        s = resolve_effective_bias_v32(
            locked_bias="RISK_ON_BIAS",
            short_signal="STABLE",
            mid_regime="RISK_OFF",
            panic_streak=s[3],
            risk_off_streak=s[4],
            override_days_left=s[5],
            override_bias=s[6],
            override_reason=s[7],
        )
    assert s[0] == "NEUTRAL_BIAS"
    assert s[1] == "OVERRIDE"
    assert s[2] == "RISK_OFF"


def test_v32_cooldown_blocks_retrigger() -> None:
    # already in override cooldown
    s = resolve_effective_bias_v32(
        locked_bias="RISK_ON_BIAS",
        short_signal="PANIC",
        mid_regime="RISK_OFF",
        panic_streak=5,
        risk_off_streak=5,
        override_days_left=3,
        override_bias="RISK_OFF_BIAS",
        override_reason="PANIC",
    )
    assert s[0] == "RISK_OFF_BIAS"
    assert s[1] == "OVERRIDE"
    assert s[2] == "PANIC"
    assert s[5] == 2


def test_v32_unknown_bias_fail_open_to_neutral() -> None:
    s = resolve_effective_bias_v32(
        locked_bias="UNKNOWN",
        short_signal="STABLE",
        mid_regime="NEUTRAL",
        panic_streak=0,
        risk_off_streak=0,
        override_days_left=0,
        override_bias="UNKNOWN",
        override_reason="NONE",
    )
    assert s[0] == "NEUTRAL_BIAS"
    assert s[1] == "LOCKED"


def test_attach_next_step_bias_contains_hazard_metadata() -> None:
    from pretrend.pipeline.backtest.runner import BacktestRunner

    runner = BacktestRunner()
    policy = pd.Series({"long_phase": "EXPANSION", "mid_regime": "RISK_ON"})
    out = runner._attach_next_step_bias(  # noqa: SLF001
        policy_row=policy,
        next_step_df=None,
        td=date(2025, 1, 2),
        override_bias="RISK_OFF_BIAS",
        override_source="OVERRIDE",
        override_reason="PANIC",
        hazard_source="SNAPSHOT",
        hazard_value_10d=0.42,
        override_applied=True,
    )
    assert out is not None
    assert out["next_step_bias_effective"] == "RISK_OFF_BIAS"
    assert out["hazard_source"] == "SNAPSHOT"
    assert out["hazard_value_10d"] == 0.42
    assert bool(out["override_applied"]) is True


def test_hazard_threshold_env_override(monkeypatch) -> None:
    monkeypatch.setenv("PRETREND_HAZARD_THRESHOLD_10D", "0.95")
    assert _get_hazard_threshold_10d() == 0.95


def test_hazard_threshold_env_invalid_fallback(monkeypatch) -> None:
    monkeypatch.setenv("PRETREND_HAZARD_THRESHOLD_10D", "abc")
    assert _get_hazard_threshold_10d() == 0.95


def test_v34_mode_flags_include_v31_v32_v33_features() -> None:
    flags = _resolve_v3_mode_flags("v3.4")
    assert flags == (True, True, True, True, False)


def test_v33_mode_flags_exclude_group_transition_only() -> None:
    flags = _resolve_v3_mode_flags("v3.3")
    assert flags == (True, True, True, False, False)


def test_v341_mode_flags_enable_reentry_variant() -> None:
    flags = _resolve_v3_mode_flags("v3.4.1")
    assert flags == (True, True, True, True, True)


def test_v342a_mode_flags_follow_phase_and_group_chain() -> None:
    flags = _resolve_v3_mode_flags("v3.4.2a")
    assert flags == (False, False, False, True, False)


def test_v341_group_gate_triggers_on_weak_count_ge_2() -> None:
    cfg = BacktestConfig.from_preset("v3.4.1", start_date=date(2025, 1, 1), end_date=date(2025, 2, 1))
    group_df = pd.DataFrame(
        [
            {"trade_date": date(2025, 1, 6), "asset_group": "SECTOR", "group_state_now": "WEAK"},
            {"trade_date": date(2025, 1, 6), "asset_group": "BOND", "group_state_now": "WEAK"},
            {"trade_date": date(2025, 1, 6), "asset_group": "COUNTRY", "group_state_now": "STRONG"},
        ]
    )
    new_cfg, meta, _, active = _apply_group_transition_gate_v341(
        cfg,
        group_df,
        date(2025, 1, 6),
        short_signal="STABLE",
        mid_regime="NEUTRAL",
        relief_streak=0,
        group_gate_active=False,
    )
    assert active is True
    assert meta["group_gate_applied"] is True
    assert meta["weak_group_count"] == 2
    assert new_cfg.max_tactical_slots == max(0, cfg.max_tactical_slots - 1)


def test_v341_group_gate_reentry_by_relief_streak() -> None:
    cfg = BacktestConfig.from_preset("v3.4.1", start_date=date(2025, 1, 1), end_date=date(2025, 2, 1))
    group_df = pd.DataFrame(
        [
            {"trade_date": date(2025, 1, 7), "asset_group": "SECTOR", "group_state_now": "WEAK"},
            {"trade_date": date(2025, 1, 7), "asset_group": "BOND", "group_state_now": "WEAK"},
        ]
    )
    new_cfg, meta, _, active = _apply_group_transition_gate_v341(
        cfg,
        group_df,
        date(2025, 1, 7),
        short_signal="RELIEF",
        mid_regime="NEUTRAL",
        relief_streak=2,
        group_gate_active=True,
    )
    assert active is False
    assert meta["group_gate_applied"] is False
    assert meta["reentry_trigger"] == "RELIEF_STREAK"
    assert new_cfg.max_tactical_slots == cfg.max_tactical_slots


def test_attach_next_step_bias_v342a_applies_cooldown_compression() -> None:
    from pretrend.pipeline.backtest.runner import BacktestRunner

    runner = BacktestRunner()
    policy = pd.Series({"long_phase": "EXPANSION", "mid_regime": "RISK_ON"})
    next_df = pd.DataFrame(
        [
            {
                "trade_date": date(2025, 1, 10),
                "bias_20d": "RISK_OFF_BIAS",
                "bias_candidate_20d": "NEUTRAL_BIAS",
                "bias_state_source": "HOLD_COOLDOWN",
                "cooldown_compressed_flag": True,
                "cooldown_compressed_reason": "RELIEF_STREAK",
                "hard_gate_exit_assist_flag": False,
                "hard_gate_exit_assist_reason": "NONE",
            }
        ]
    )
    out = runner._attach_next_step_bias(  # noqa: SLF001
        policy_row=policy,
        next_step_df=next_df,
        td=date(2025, 1, 10),
        apply_v342a=True,
    )
    assert out is not None
    assert out["next_step_bias_effective"] == "NEUTRAL_BIAS"
    assert out["next_step_bias_source"] == "COMPRESSED"
    assert out["next_step_bias_reason"] == "RELIEF_STREAK"


def test_attach_next_step_bias_v342a_applies_hard_gate_exit_assist() -> None:
    from pretrend.pipeline.backtest.runner import BacktestRunner

    runner = BacktestRunner()
    policy = pd.Series({"long_phase": "RECESSION", "mid_regime": "NEUTRAL"})
    next_df = pd.DataFrame(
        [
            {
                "trade_date": date(2025, 1, 13),
                "bias_20d": "RISK_OFF_BIAS",
                "bias_candidate_20d": "RISK_OFF_BIAS",
                "bias_state_source": "BASELINE",
                "cooldown_compressed_flag": False,
                "cooldown_compressed_reason": "NONE",
                "hard_gate_exit_assist_flag": True,
                "hard_gate_exit_assist_reason": "RUN_UNIVERSE_RECOVERY_RELIEF",
            }
        ]
    )
    out = runner._attach_next_step_bias(  # noqa: SLF001
        policy_row=policy,
        next_step_df=next_df,
        td=date(2025, 1, 13),
        apply_v342a=True,
    )
    assert out is not None
    assert out["next_step_bias_effective"] == "NEUTRAL_BIAS"
    assert out["next_step_bias_source"] == "ASSIST"
