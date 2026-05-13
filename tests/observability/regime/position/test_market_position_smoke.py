from __future__ import annotations

from datetime import date

import pandas as pd

from pretrend.observability.regime.position.engine import build_market_position


def test_market_position_smoke_builds_state_vector() -> None:
    state = pd.DataFrame(
        [{
            "trade_date": date(2024, 6, 3),
            "long_phase": "EXPANSION",
            "mid_regime": "RISK_ON",
            "short_signal": "STABLE",
        }]
    )

    out = build_market_position(state, run_id="smoke")

    assert len(out) == 1
    assert bool(out.loc[0, "run_universe"]) is True
    assert bool(out.loc[0, "risk_gate"]) is True
