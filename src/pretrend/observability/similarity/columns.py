from __future__ import annotations


CORE_FEATURE_COLUMNS = [
    "long_phase_expansion",
    "long_phase_late_cycle",
    "long_phase_slowdown",
    "long_phase_recession",
    "long_phase_recovery",
    "long_phase_unknown",
    "mid_regime_code",
    "short_signal_code",
    "long_phase_confidence",
    "mid_regime_confidence",
    "short_signal_confidence",
    "run_universe_flag",
    "risk_gate_flag",
]

TRANSITION_FEATURE_COLUMNS = [
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
]

ROTATION_FEATURE_COLUMNS = [
    "rot_sp500_state_code",
    "rot_nasdaq100_state_code",
    "rot_dow30_state_code",
    "rot_us_dividend_state_code",
    "rot_russell2000_state_code",
    "rot_us_dividend_select_state_code",
    "rot_us_dividend_appreciation_state_code",
    "rot_south_korea_state_code",
    "rot_china_state_code",
    "rot_japan_state_code",
    "rot_india_state_code",
    "rot_gold_state_code",
    "rot_gold_miners_state_code",
    "rot_silver_state_code",
    "rot_crude_oil_state_code",
    "rot_oil_producers_state_code",
    "rot_natural_gas_state_code",
    "rot_agriculture_state_code",
    "rot_us_treasury_20y_state_code",
    "rot_us_high_yield_state_code",
    "rot_us_investment_grade_state_code",
    "rot_us_treasury_1_3y_state_code",
    "rot_us_tips_state_code",
    "rot_health_care_state_code",
    "rot_energy_state_code",
    "rot_semiconductor_state_code",
    "rot_financials_state_code",
    "rot_regional_banks_state_code",
    "rot_nuclear_state_code",
    "rot_information_tech_state_code",
    "rot_materials_state_code",
    "rot_consumer_discretionary_state_code",
    "rot_consumer_staples_state_code",
    "rot_communication_services_state_code",
    "rot_real_estate_state_code",
    "rot_utilities_state_code",
    "rot_industrials_state_code",
]

REGIME_SIMILARITY_FEATURE_COLUMNS = (
    CORE_FEATURE_COLUMNS + TRANSITION_FEATURE_COLUMNS + ROTATION_FEATURE_COLUMNS
)
