from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from pretrend.observability.regime import regime_feature_builder as builder


def test_build_rotation_df_from_gold_preserves_asset_name_and_trims_range() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_gold_tables(engine)
    _insert_eod(
        engine,
        [
            _eod_row(date(2026, 5, 10), "SPY", "INDEX", "SP500", 0.01),
            _eod_row(date(2026, 5, 10), "QQQ", "INDEX", "NASDAQ100", 0.02),
            _eod_row(date(2026, 5, 12), "SPY", "INDEX", "SP500", 0.03),
            _eod_row(date(2026, 5, 12), "QQQ", "INDEX", "NASDAQ100", 0.08),
        ],
    )

    rotation = builder.build_rotation_df_from_gold(
        engine,
        date(2026, 5, 12),
        date(2026, 5, 12),
        lookback_days=7,
    )

    assert rotation["trade_date"].tolist() == [date(2026, 5, 12), date(2026, 5, 12)]
    assert set(rotation["asset_name"]) == {"SP500", "NASDAQ100"}
    states = dict(zip(rotation["asset_name"], rotation["group_state_now"]))
    assert states == {"SP500": "NEUTRAL", "NASDAQ100": "STRONG"}


def test_build_market_state_df_from_gold_reads_lookback_and_trims_output(
    monkeypatch,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_gold_tables(engine)
    _insert_eod(
        engine,
        [
            _eod_row(date(2026, 5, 10), "SPY", "INDEX", "SP500", 0.01),
            _eod_row(date(2026, 5, 12), "SPY", "INDEX", "SP500", 0.03),
        ],
    )
    _insert_macro(
        engine,
        [
            _macro_row(date(2026, 5, 10), "CPIAUCSL", "RISING"),
            _macro_row(date(2026, 5, 12), "CPIAUCSL", "RISING"),
        ],
    )

    def fake_axis_features(macro: pd.DataFrame, eod: pd.DataFrame) -> SimpleNamespace:
        assert set(eod["trade_date"]) == {date(2026, 5, 10), date(2026, 5, 12)}
        assert set(macro["trade_date"]) == {date(2026, 5, 10), date(2026, 5, 12)}
        return SimpleNamespace(dates=sorted(eod["trade_date"].unique()))

    def fake_axis_horizon_state(bundle: SimpleNamespace, run_id: str) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "trade_date": current_date,
                    "long_phase": "LATE_CYCLE",
                    "mid_regime": "RISK_OFF",
                    "short_signal": "STABLE",
                    "long_phase_confidence": 0.8,
                    "mid_regime_confidence": 0.7,
                    "short_signal_confidence": 0.6,
                    "source_run_id": run_id,
                }
                for current_date in bundle.dates
            ]
        )

    def fake_market_position(axis_horizon_state: pd.DataFrame, run_id: str) -> pd.DataFrame:
        out = axis_horizon_state[
            ["trade_date", "long_phase", "mid_regime", "short_signal"]
        ].copy()
        out["run_universe"] = False
        out["risk_gate"] = True
        out["source_run_id"] = run_id
        return out

    def fake_next_step_signal(
        axis_horizon_state: pd.DataFrame,
        market_position: pd.DataFrame,
        *,
        run_id: str,
    ) -> pd.DataFrame:
        out = axis_horizon_state[["trade_date"]].copy()
        for column in builder.TRANSITION_COLUMNS:
            out[column] = 7 if column == "state_age_days" else 0.25
        out["source_run_id"] = run_id
        return out

    monkeypatch.setattr(builder, "build_axis_features", fake_axis_features)
    monkeypatch.setattr(builder, "build_axis_horizon_state", fake_axis_horizon_state)
    monkeypatch.setattr(builder, "build_market_position", fake_market_position)
    monkeypatch.setattr(builder, "build_next_step_signal", fake_next_step_signal)

    market_state = builder.build_market_state_df_from_gold(
        engine,
        date(2026, 5, 12),
        date(2026, 5, 12),
        lookback_days=2,
    )

    assert market_state.columns.tolist() == builder.MARKET_STATE_COLUMNS
    assert market_state["trade_date"].tolist() == [date(2026, 5, 12)]
    row = market_state.iloc[0]
    assert row["state_age_days"] == 7
    assert bool(row["run_universe"]) is False
    assert bool(row["risk_gate"]) is True


def test_regime_feature_builder_does_not_depend_on_strategy_snapshots() -> None:
    source = builder.__loader__.get_source(builder.__name__)

    assert source is not None
    assert "load_strategy_snapshot" not in source
    assert "data/strategy" not in source
    assert "strategy_root" not in source


def _create_gold_tables(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE gold_eod_features (
                    symbol TEXT,
                    trade_date DATE,
                    adj_close REAL,
                    volume REAL,
                    ret_1d REAL,
                    ret_5d REAL,
                    ret_20d REAL,
                    vol_20d REAL,
                    vol_60d REAL,
                    atr_14 REAL,
                    rsi_14 REAL,
                    intraday_range REAL,
                    volume_zscore_20d REAL,
                    asset_group TEXT,
                    asset_name TEXT
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE gold_macro_features (
                    indicator_id TEXT,
                    trade_date DATE,
                    selected_value REAL,
                    selected_release_date DATE,
                    regime TEXT,
                    delta_1m REAL,
                    delta_3m REAL,
                    delta_6m REAL,
                    zscore_12m REAL,
                    release_source TEXT,
                    direction TEXT
                )
                """
            )
        )


def _insert_eod(engine: Engine, rows: list[dict[str, object]]) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO gold_eod_features (
                    symbol, trade_date, adj_close, volume, ret_1d, ret_5d, ret_20d,
                    vol_20d, vol_60d, atr_14, rsi_14, intraday_range,
                    volume_zscore_20d, asset_group, asset_name
                )
                VALUES (
                    :symbol, :trade_date, :adj_close, :volume, :ret_1d, :ret_5d,
                    :ret_20d, :vol_20d, :vol_60d, :atr_14, :rsi_14,
                    :intraday_range, :volume_zscore_20d, :asset_group, :asset_name
                )
                """
            ),
            rows,
        )


def _insert_macro(engine: Engine, rows: list[dict[str, object]]) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO gold_macro_features (
                    indicator_id, trade_date, selected_value, selected_release_date,
                    regime, delta_1m, delta_3m, delta_6m, zscore_12m,
                    release_source, direction
                )
                VALUES (
                    :indicator_id, :trade_date, :selected_value, :selected_release_date,
                    :regime, :delta_1m, :delta_3m, :delta_6m, :zscore_12m,
                    :release_source, :direction
                )
                """
            ),
            rows,
        )


def _eod_row(
    trade_date: date,
    symbol: str,
    asset_group: str,
    asset_name: str,
    ret_20d: float,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "trade_date": trade_date.isoformat(),
        "adj_close": 100.0,
        "volume": 1_000_000.0,
        "ret_1d": 0.01,
        "ret_5d": 0.02,
        "ret_20d": ret_20d,
        "vol_20d": 0.12,
        "vol_60d": 0.18,
        "atr_14": 1.0,
        "rsi_14": 55.0,
        "intraday_range": 0.01,
        "volume_zscore_20d": 0.2,
        "asset_group": asset_group,
        "asset_name": asset_name,
    }


def _macro_row(trade_date: date, indicator_id: str, regime: str) -> dict[str, object]:
    return {
        "indicator_id": indicator_id,
        "trade_date": trade_date.isoformat(),
        "selected_value": 100.0,
        "selected_release_date": trade_date.isoformat(),
        "regime": regime,
        "delta_1m": 0.1,
        "delta_3m": 0.2,
        "delta_6m": 0.3,
        "zscore_12m": 0.4,
        "release_source": "fixture",
        "direction": "UP",
    }
