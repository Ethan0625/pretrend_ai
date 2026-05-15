from __future__ import annotations

import pytest


pytestmark = pytest.mark.contract


def test_strategy_engine_regime_shim_package_exports() -> None:
    from pretrend.pipeline.strategy_engine.axis_features import (
        build_axis_features,
        build_macro_policy_axis,
    )
    from pretrend.pipeline.strategy_engine.axis_horizon_state import (
        build_axis_horizon_state,
    )
    from pretrend.pipeline.strategy_engine.group_transition import (
        build_group_transition_signal,
    )
    from pretrend.pipeline.strategy_engine.market_position import build_market_position
    from pretrend.pipeline.strategy_engine.next_step import build_next_step_signal

    assert callable(build_axis_features)
    assert callable(build_macro_policy_axis)
    assert callable(build_axis_horizon_state)
    assert callable(build_market_position)
    assert callable(build_next_step_signal)
    assert callable(build_group_transition_signal)
