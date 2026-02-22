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
        """RECESSION: phase 차단 없음 — Universe v1 eligible pool이 처리."""
        row = pd.Series({
            "run_universe": True,
            "risk_gate": True,
            "long_phase": "RECESSION",
        })
        assert _should_run_tactical(row) is True

    def test_slowdown(self):
        """SLOWDOWN: phase 차단 없음 — Universe v1 eligible pool이 처리."""
        row = pd.Series({
            "run_universe": True,
            "risk_gate": True,
            "long_phase": "SLOWDOWN",
        })
        assert _should_run_tactical(row) is True

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
        # 비례 차감: core 전체에서 5:3:2 비율 그대로 차감
        base = {"SCHD": 0.50, "SPY": 0.30, "IAU": 0.20}
        result = _apply_tactical(base, ["XLK"], default_config, date(2024, 1, 2))
        assert result["XLK"] == 0.15
        assert result["SCHD"] == pytest.approx(0.425)  # 0.50 - 0.15*0.50
        assert result["SPY"] == pytest.approx(0.255)   # 0.30 - 0.15*0.30
        assert result["IAU"] == pytest.approx(0.170)   # 0.20 - 0.15*0.20

    def test_two_tactical(self, default_config):
        # 비례 차감: tactical 2개(30%) → 각 core에서 30% 비례 차감
        base = {"SCHD": 0.50, "SPY": 0.30, "IAU": 0.20}
        result = _apply_tactical(base, ["XLK", "XLE"], default_config, date(2024, 1, 2))
        assert result["XLK"] == 0.15
        assert result["XLE"] == 0.15
        assert result["SCHD"] == pytest.approx(0.35)  # 0.50 - 0.30*0.50
        assert result["SPY"] == pytest.approx(0.21)   # 0.30 - 0.30*0.30
        assert result["IAU"] == pytest.approx(0.14)   # 0.20 - 0.30*0.20

    def test_pre_schd_tactical(self, default_config):
        # 비례 차감: SPY 80%, IAU 20% 구성에서 15% 차감
        base = {"SPY": 0.80, "IAU": 0.20}
        result = _apply_tactical(base, ["XLE"], default_config, date(2008, 6, 1))
        assert result["XLE"] == 0.15
        assert result["SPY"] == pytest.approx(0.68)  # 0.80 - 0.15*0.80
        assert result["IAU"] == pytest.approx(0.17)  # 0.20 - 0.15*0.20


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
        # pre-SCHD 기간: DVY 25% + VIG 25% + SPY 30% + IAU 20%
        ratio, weights = compute_target_weights(
            trade_date=date(2008, 6, 1),
            policy_row=None,
            allocation_row=None,
            universe_df=None,
            config=default_config,
            prices={"DVY": 50.0, "VIG": 60.0, "SPY": 100.0, "IAU": 50.0},
        )
        assert "SCHD" not in weights
        assert weights == {"DVY": 0.25, "VIG": 0.25, "SPY": 0.30, "IAU": 0.20}


# ── Tactical v1 테스트 ────────────────────────────────────


class TestPickTacticalV1:
    def test_sector_only_config(self):
        """SECTOR 단독 config: COMMODITY 제외."""
        config = BacktestConfig(
            start_date=date(2006, 1, 3),
            end_date=date(2024, 6, 3),
            tactical_groups=["SECTOR"],
        )
        universe_df = pd.DataFrame([
            {"rebalance_date": date(2024, 1, 2), "symbol": "SPY", "asset_group": "INDEX", "relative_strength": 0.05, "is_candidate": True},
            {"rebalance_date": date(2024, 1, 2), "symbol": "XLK", "asset_group": "SECTOR", "relative_strength": 0.10, "is_candidate": True},
            {"rebalance_date": date(2024, 1, 2), "symbol": "USO", "asset_group": "COMMODITY", "relative_strength": 0.12, "is_candidate": True},
        ])
        prices = {"SPY": 100.0, "XLK": 50.0, "USO": 30.0}
        result = _pick_tactical(universe_df, prices, config, date(2024, 1, 2))
        assert "XLK" in result
        assert "USO" not in result

    def test_is_candidate_filter(self, default_config):
        """is_candidate=False인 ETF는 tactical 제외."""
        universe_df = pd.DataFrame([
            {"rebalance_date": date(2024, 1, 2), "symbol": "SPY",
             "asset_group": "INDEX", "relative_strength": 0.05, "is_candidate": True},
            {"rebalance_date": date(2024, 1, 2), "symbol": "TLT",
             "asset_group": "BOND", "relative_strength": 0.12, "is_candidate": False},
            {"rebalance_date": date(2024, 1, 2), "symbol": "XLK",
             "asset_group": "SECTOR", "relative_strength": 0.10, "is_candidate": True},
        ])
        prices = {"SPY": 100.0, "TLT": 90.0, "XLK": 50.0}
        result = _pick_tactical(universe_df, prices, default_config, date(2024, 1, 2))
        assert "TLT" not in result   # is_candidate=False → 제외
        assert "XLK" in result

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
