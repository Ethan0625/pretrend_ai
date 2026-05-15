"""Tactical asset-group transition signal module."""

from .engine import build_group_transition_signal
from .history_io import (
    load_group_transition_history,
    save_group_transition_history_incremental,
)
from .io import (
    load_group_transition_for_runtime,
    load_group_transition_snapshot,
    load_universe_for_group_transition,
)
from .schema import GROUP_TRANSITION_SIGNAL_COLUMNS

__all__ = [
    "GROUP_TRANSITION_SIGNAL_COLUMNS",
    "build_group_transition_signal",
    "load_group_transition_for_runtime",
    "load_group_transition_history",
    "load_group_transition_snapshot",
    "load_universe_for_group_transition",
    "save_group_transition_history_incremental",
]
