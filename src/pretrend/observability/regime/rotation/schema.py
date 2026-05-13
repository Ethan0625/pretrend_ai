"""Schema for group transition signal snapshots."""
from __future__ import annotations


GROUP_TRANSITION_SIGNAL_COLUMNS = [
    "trade_date",
    "asset_group",
    "group_state_now",
    "group_expected_5d",
    "group_expected_10d",
    "group_expected_20d",
    "group_sojourn_prob_5d",
    "group_sojourn_prob_10d",
    "group_sojourn_prob_20d",
    "group_transition_hazard_5d",
    "group_transition_hazard_10d",
    "group_transition_hazard_20d",
    "group_confidence",
    "source_run_id",
]

