"""Rebalancer 단위 테스트."""
from datetime import date

import pandas as pd
import pytest

from pretrend.pipeline.backtest.config import BacktestConfig
from pretrend.pipeline.backtest.rebalancer import (
    compute_target_weights,
    is_rebalance_day,
    _should_run_tactical,
    _pick_tactical,
    _apply_tactical,
)


@pytest.fixture
def default_config():
    return BacktestConfig(
        start_date=date(2006, 1, 3),
        end_date=date(2024, 6, 3),
    )


class TestIsRebalanceDay:
    def test_first_day(self):
        assert is_rebalance_day(date(2024, 1, 2), None) is True

    def test_same_month(self):
        assert is_rebalance_day(date(2024, 1, 15), date(2024, 1, 2)) is False

    def test_new_month(self):
        assert is_rebalance_day(date(2024, 2, 1), date(2024, 1, 31)) is True

    def test_not_monthly(self):
        assert is_rebalance_day(date(2024, 2, 1), date(2024, 1, 31), "weekly") is False


class TestShouldRunTactical:
    def test_all_conditions_met(self):
        row = pd.Series({
            "run_universe": True,
            "risk_gate": True,
            "long_phase": "EXPANSION",
        })
        assert _should_run_tactical(row) is True

    def test_no_run_universe(self):
        row = pd.Series({
            "run_universe": False,
            "risk_gate": True,
            "long_phase": "EXPANSION",
        })
        assert _should_run_tactical(row) is False

    def test_no_risk_gate(self):
        row = pd.Series({
            "run_universe": True,
            "risk_gate": False,
            "long_phase": "EXPANSION",
        })
        assert _should_run_tactical(row) is False

    def test_recession(self):
        row = pd.Series({
            "run_universe": True,
            "risk_gate": True,
            "long_phase": "RECESSION",
        })
        assert _should_run_tactical(row) is False

    def test_slowdown(self):
        row = pd.Series({
            "run_universe": True,
            "risk_gate": True,
            "long_phase": "SLOWDOWN",
        })
        assert _should_run_tactical(row) is False

    def test_none_row(self):
        assert _should_run_tactical(None) is False


class TestPickTactical:
    def test_picks_sector_above_spy(self, default_config):
        universe_df = pd.DataFrame([
            {"rebalance_date": date(2024, 1, 2), "symbol": "SPY", "asset_group": "INDEX", "relative_strength": 0.05, "is_candidate": True},
            {"rebalance_date": date(2024, 1, 2), "symbol": "XLK", "asset_group": "SECTOR", "relative_strength": 0.10, "is_candidate": True},
            {"rebalance_date": date(2024, 1, 2), "symbol": "XLE", "asset_group": "SECTOR", "relative_strength": 0.08, "is_candidate": True},
            {"rebalance_date": date(2024, 1, 2), "symbol": "XLV", "asset_group": "SECTOR", "relative_strength": 0.03, "is_candidate": True},
        ])
        prices = {"SPY": 100.0, "XLK": 50.0, "XLE": 30.0, "XLV": 40.0}
        result = _pick_tactical(universe_df, prices, default_config, date(2024, 1, 2))
        assert result == ["XLK", "XLE"]  # above SPY rs=0.05, max 2

    def test_none_above_spy(self, default_config):
        universe_df = pd.DataFrame([
            {"rebalance_date": date(2024, 1, 2), "symbol": "SPY", "asset_group": "INDEX", "relative_strength": 0.10, "is_candidate": True},
            {"rebalance_date": date(2024, 1, 2), "symbol": "XLK", "asset_group": "SECTOR", "relative_strength": 0.05, "is_candidate": True},
        ])
        prices = {"SPY": 100.0, "XLK": 50.0}
        result = _pick_tactical(universe_df, prices, default_config, date(2024, 1, 2))
        assert result == []

    def test_empty_universe(self, default_config):
        result = _pick_tactical(None, {}, default_config, date(2024, 1, 2))
        assert result == []


class TestApplyTactical:
    def test_single_tactical(self, default_config):
        base = {"SCHD": 0.50, "SPY": 0.30, "IAU": 0.20}
        result = _apply_tactical(base, ["XLK"], default_config, date(2024, 1, 2))
        assert result["XLK"] == 0.15
        assert result["SCHD"] == pytest.approx(0.35)  # 0.50 - 0.15
        assert result["SPY"] == 0.30
        assert result["IAU"] == 0.20

    def test_two_tactical(self, default_config):
        base = {"SCHD": 0.50, "SPY": 0.30, "IAU": 0.20}
        result = _apply_tactical(base, ["XLK", "XLE"], default_config, date(2024, 1, 2))
        assert result["XLK"] == 0.15
        assert result["XLE"] == 0.15
        assert result["SCHD"] == pytest.approx(0.20)  # 0.50 - 0.30

    def test_pre_schd_tactical(self, default_config):
        base = {"SPY": 0.80, "IAU": 0.20}
        result = _apply_tactical(base, ["XLE"], default_config, date(2008, 6, 1))
        assert result["XLE"] == 0.15
        assert result["SPY"] == pytest.approx(0.65)  # 0.80 - 0.15


class TestComputeTargetWeights:
    def test_with_allocation(self, default_config):
        alloc_row = pd.Series({"next_invested_ratio": 0.40})
        ratio, weights = compute_target_weights(
            trade_date=date(2024, 1, 2),
            policy_row=None,
            allocation_row=alloc_row,
            universe_df=None,
            config=default_config,
            prices={"SCHD": 30.0, "SPY": 100.0, "IAU": 50.0},
        )
        assert ratio == 0.40
        assert weights == {"SCHD": 0.50, "SPY": 0.30, "IAU": 0.20}

    def test_no_allocation_fallback(self, default_config):
        ratio, weights = compute_target_weights(
            trade_date=date(2024, 1, 2),
            policy_row=None,
            allocation_row=None,
            universe_df=None,
            config=default_config,
            prices={"SCHD": 30.0, "SPY": 100.0, "IAU": 50.0},
        )
        assert ratio == 0.60  # config default

    def test_pre_schd_weights(self, default_config):
        ratio, weights = compute_target_weights(
            trade_date=date(2008, 6, 1),
            policy_row=None,
            allocation_row=None,
            universe_df=None,
            config=default_config,
            prices={"SPY": 100.0, "IAU": 50.0},
        )
        assert "SCHD" not in weights
        assert weights == {"SPY": 0.80, "IAU": 0.20}


# ── Tactical v1 테스트 ────────────────────────────────────


class TestPickTacticalV1:
    def test_sector_only_default(self, default_config):
        """v0 default: SECTOR만 선택, COMMODITY 제외."""
        universe_df = pd.DataFrame([
            {"rebalance_date": date(2024, 1, 2), "symbol": "SPY", "asset_group": "INDEX", "relative_strength": 0.05, "is_candidate": True},
            {"rebalance_date": date(2024, 1, 2), "symbol": "XLK", "asset_group": "SECTOR", "relative_strength": 0.10, "is_candidate": True},
            {"rebalance_date": date(2024, 1, 2), "symbol": "USO", "asset_group": "COMMODITY", "relative_strength": 0.12, "is_candidate": True},
        ])
        prices = {"SPY": 100.0, "XLK": 50.0, "USO": 30.0}
        result = _pick_tactical(universe_df, prices, default_config, date(2024, 1, 2))
        assert "XLK" in result
        assert "USO" not in result

    def test_sector_and_commodity(self):
        """v1: SECTOR + COMMODITY 모두 선택."""
        config = BacktestConfig(
            start_date=date(2006, 1, 3),
            end_date=date(2024, 6, 3),
            tactical_groups=["SECTOR", "COMMODITY"],
        )
        universe_df = pd.DataFrame([
            {"rebalance_date": date(2024, 1, 2), "symbol": "SPY", "asset_group": "INDEX", "relative_strength": 0.05, "is_candidate": True},
            {"rebalance_date": date(2024, 1, 2), "symbol": "XLK", "asset_group": "SECTOR", "relative_strength": 0.10, "is_candidate": True},
            {"rebalance_date": date(2024, 1, 2), "symbol": "USO", "asset_group": "COMMODITY", "relative_strength": 0.12, "is_candidate": True},
        ])
        prices = {"SPY": 100.0, "XLK": 50.0, "USO": 30.0}
        result = _pick_tactical(universe_df, prices, config, date(2024, 1, 2))
        assert "USO" in result
        assert "XLK" in result

    def test_commodity_below_spy_excluded(self):
        """COMMODITY 추가되어도 SPY보다 약하면 제외."""
        config = BacktestConfig(
            start_date=date(2006, 1, 3),
            end_date=date(2024, 6, 3),
            tactical_groups=["SECTOR", "COMMODITY"],
        )
        universe_df = pd.DataFrame([
            {"rebalance_date": date(2024, 1, 2), "symbol": "SPY", "asset_group": "INDEX", "relative_strength": 0.10, "is_candidate": True},
            {"rebalance_date": date(2024, 1, 2), "symbol": "USO", "asset_group": "COMMODITY", "relative_strength": 0.03, "is_candidate": True},
        ])
        prices = {"SPY": 100.0, "USO": 30.0}
        result = _pick_tactical(universe_df, prices, config, date(2024, 1, 2))
        assert result == []

    def test_invalid_tactical_group_raises(self):
        """잘못된 tactical group → ValueError."""
        with pytest.raises(ValueError, match="Unknown tactical group"):
            BacktestConfig(
                start_date=date(2006, 1, 3),
                end_date=date(2024, 6, 3),
                tactical_groups=["SECTOR", "FOREX"],
            )
