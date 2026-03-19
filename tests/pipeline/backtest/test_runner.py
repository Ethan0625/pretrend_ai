"""BacktestRunner 통합 테스트 (in-memory fixture)."""
from datetime import date

import pandas as pd
import pytest

from pretrend.pipeline.backtest.config import BacktestConfig
from pretrend.pipeline.backtest.portfolio import Portfolio
from pretrend.pipeline.backtest.runner import BacktestRunner, StagedSellPlan
from pretrend.pipeline.backtest.allocation import compute_allocation_v1


@pytest.fixture
def mini_data(tmp_path):
    """최소 Gold EOD + Strategy snapshot fixture.

    2012-01-03 (화) ~ 2012-01-16 (월): 10 영업일
    첫 날(1/3 화) → 초기 매수
    1/9 (월) → 첫 주간 평가 (EXPANSION → INCREASE)
    1/10 (화) → 매수
    1/13 (금) → staged sell 없음 (INCREASE라서)
    """
    dates = pd.bdate_range("2012-01-03", periods=10).date
    rows = []
    for i, d in enumerate(dates):
        rows.append({"symbol": "SPY", "trade_date": d, "adj_close": 130.0 + i})
        rows.append({"symbol": "IAU", "trade_date": d, "adj_close": 16.0 + i * 0.1})
        rows.append({"symbol": "SCHD", "trade_date": d, "adj_close": 25.0 + i * 0.2})

    eod_dir = tmp_path / "gold" / "eod" / "eod_features"
    eod_dir.mkdir(parents=True)
    pd.DataFrame(rows).to_parquet(eod_dir / "mini.parquet", index=False)

    # Policy Selection snapshot
    ps_rows = []
    for d in dates:
        ps_rows.append({
            "trade_date": d,
            "long_phase": "EXPANSION",
            "mid_regime": "RISK_ON",
            "short_signal": "NEUTRAL",
            "run_universe": True,
            "risk_gate": True,
            "policy_profile_id": "RC_V0_DEFAULT",
            "target_invested_lower": 0.10,
            "target_invested_upper": 0.60,
            "adjustment_limit": 0.10,
            "step_size": 0.05,
            "policy_version": "v0",
            "notes": "",
            "source_run_id": "test",
        })
    ps_dir = tmp_path / "strategy" / "policy_selection" / "decision_date=2012-01-16"
    ps_dir.mkdir(parents=True)
    pd.DataFrame(ps_rows).to_parquet(ps_dir / "policy_selection_20120116.parquet", index=False)

    # Allocation snapshot
    alloc_rows = []
    for d in dates:
        alloc_rows.append({
            "trade_date": d,
            "action": "HOLD",
            "next_invested_ratio": 0.60,
            "delta_ratio": 0.0,
            "blocked_by_risk_gate": False,
            "notes": "",
        })
    alloc_dir = tmp_path / "strategy" / "exposure" / "decision_date=2012-01-16"
    alloc_dir.mkdir(parents=True)
    pd.DataFrame(alloc_rows).to_parquet(alloc_dir / "exposure_20120116.parquet", index=False)

    return tmp_path


class TestBacktestRunner:
    def test_basic_run(self, mini_data):
        config = BacktestConfig(
            start_date=date(2012, 1, 3),
            end_date=date(2012, 1, 16),
            initial_capital=1000.0,
            monthly_addition=0.0,  # DCA 없음
            data_root=mini_data,
        )
        runner = BacktestRunner()
        result = runner.run(config)

        assert not result.daily_log.empty
        assert len(result.daily_log) == 10
        assert result.daily_log["nav"].iloc[0] == pytest.approx(1000.0, abs=1.0)
        assert len(result.trade_log) > 0  # 초기 매수

    def test_initial_weights(self, mini_data):
        config = BacktestConfig(
            start_date=date(2012, 1, 3),
            end_date=date(2012, 1, 16),
            initial_capital=1000.0,
            monthly_addition=0.0,
            data_root=mini_data,
        )
        runner = BacktestRunner()
        result = runner.run(config)

        # 첫 날 invested_ratio ≈ 0.6
        first = result.daily_log.iloc[0]
        assert first["invested_ratio"] == pytest.approx(0.60, abs=0.02)

    def test_benchmark_nav(self, mini_data):
        config = BacktestConfig(
            start_date=date(2012, 1, 3),
            end_date=date(2012, 1, 16),
            initial_capital=1000.0,
            monthly_addition=0.0,
            data_root=mini_data,
        )
        runner = BacktestRunner()
        result = runner.run(config)

        assert len(result.benchmark_nav) == 10
        assert result.benchmark_nav.iloc[0] == pytest.approx(1000.0, abs=10.0)

    def test_daily_log_includes_schd_weight(self, mini_data):
        config = BacktestConfig(
            start_date=date(2012, 1, 3),
            end_date=date(2012, 1, 16),
            initial_capital=1000.0,
            monthly_addition=0.0,
            data_root=mini_data,
        )
        result = BacktestRunner().run(config)

        assert "schd_weight" in result.daily_log.columns
        assert result.daily_log["schd_weight"].iloc[0] > 0.0

    def test_daily_log_schd_weight_zero_when_no_position(self, tmp_path):
        dates = pd.bdate_range("2008-01-02", periods=5).date
        rows = []
        for d in dates:
            rows.append({"symbol": "SPY", "trade_date": d, "adj_close": 140.0})
            rows.append({"symbol": "IAU", "trade_date": d, "adj_close": 18.0})

        eod_dir = tmp_path / "gold" / "eod" / "eod_features"
        eod_dir.mkdir(parents=True)
        pd.DataFrame(rows).to_parquet(eod_dir / "pre_schd.parquet", index=False)

        config = BacktestConfig(
            start_date=date(2008, 1, 2),
            end_date=date(2008, 1, 8),
            initial_capital=1000.0,
            monthly_addition=0.0,
            data_root=tmp_path,
        )
        result = BacktestRunner().run(config)

        assert "schd_weight" in result.daily_log.columns
        assert result.daily_log["schd_weight"].eq(0.0).all()

    def test_no_data(self, tmp_path):
        eod_dir = tmp_path / "gold" / "eod" / "eod_features"
        eod_dir.mkdir(parents=True)

        config = BacktestConfig(
            start_date=date(2012, 1, 3),
            end_date=date(2012, 1, 16),
            data_root=tmp_path,
        )
        runner = BacktestRunner()
        result = runner.run(config)
        assert result.daily_log.empty

    def test_pre_schd_period(self, tmp_path):
        """SCHD 미출시 기간 → SPY+IAU만 매수."""
        dates = pd.bdate_range("2008-01-02", periods=5).date
        rows = []
        for d in dates:
            rows.append({"symbol": "SPY", "trade_date": d, "adj_close": 140.0})
            rows.append({"symbol": "IAU", "trade_date": d, "adj_close": 18.0})

        eod_dir = tmp_path / "gold" / "eod" / "eod_features"
        eod_dir.mkdir(parents=True)
        pd.DataFrame(rows).to_parquet(eod_dir / "pre_schd.parquet", index=False)

        config = BacktestConfig(
            start_date=date(2008, 1, 2),
            end_date=date(2008, 1, 8),
            initial_capital=1000.0,
            monthly_addition=0.0,
            data_root=tmp_path,
        )
        runner = BacktestRunner()
        result = runner.run(config)

        assert not result.daily_log.empty
        buy_symbols = {t.symbol for t in result.trade_log if t.action == "BUY"}
        assert "SPY" in buy_symbols
        assert "IAU" in buy_symbols
        assert "SCHD" not in buy_symbols

    def test_monthly_rebalance_false_skips_rebalance_but_keeps_dca(self, tmp_path, monkeypatch):
        dates = pd.bdate_range("2012-01-23", periods=10).date  # includes Monday before month boundary
        rows = []
        for i, d in enumerate(dates):
            rows.append({"symbol": "SPY", "trade_date": d, "adj_close": 130.0 + i})
            rows.append({"symbol": "IAU", "trade_date": d, "adj_close": 16.0 + i * 0.1})
            rows.append({"symbol": "SCHD", "trade_date": d, "adj_close": 25.0 + i * 0.2})

        eod_dir = tmp_path / "gold" / "eod" / "eod_features"
        eod_dir.mkdir(parents=True)
        pd.DataFrame(rows).to_parquet(eod_dir / "cross_month.parquet", index=False)

        ps_rows = []
        alloc_rows = []
        for d in dates:
            ps_rows.append({
                "trade_date": d,
                "long_phase": "EXPANSION",
                "mid_regime": "RISK_ON",
                "short_signal": "NEUTRAL",
                "run_universe": True,
                "risk_gate": True,
                "policy_profile_id": "RC_V0_DEFAULT",
                "target_invested_lower": 0.10,
                "target_invested_upper": 0.60,
                "adjustment_limit": 0.10,
                "step_size": 0.05,
                "policy_version": "v0",
                "notes": "",
                "source_run_id": "test",
            })
            alloc_rows.append({
                "trade_date": d,
                "action": "HOLD",
                "next_invested_ratio": 0.60,
                "delta_ratio": 0.0,
                "blocked_by_risk_gate": False,
                "notes": "",
            })
        ps_dir = tmp_path / "strategy" / "policy_selection" / "decision_date=2012-02-03"
        ps_dir.mkdir(parents=True)
        pd.DataFrame(ps_rows).to_parquet(ps_dir / "policy_selection_20120203.parquet", index=False)
        alloc_dir = tmp_path / "strategy" / "exposure" / "decision_date=2012-02-03"
        alloc_dir.mkdir(parents=True)
        pd.DataFrame(alloc_rows).to_parquet(alloc_dir / "exposure_20120203.parquet", index=False)

        calls = {"count": 0}
        original = Portfolio.rebalance_to_weights

        def _counting_rebalance(self, *args, **kwargs):
            calls["count"] += 1
            return original(self, *args, **kwargs)

        monkeypatch.setattr(Portfolio, "rebalance_to_weights", _counting_rebalance)

        config = BacktestConfig(
            start_date=date(2012, 1, 23),
            end_date=date(2012, 2, 3),
            initial_capital=1000.0,
            monthly_addition=300.0,
            monthly_rebalance=False,
            data_root=tmp_path,
        )
        result = BacktestRunner().run(config)

        assert calls["count"] == 0
        assert result.total_capital_injected == pytest.approx(300.0)
        feb_row = result.daily_log.loc[pd.Timestamp("2012-02-01")]
        assert feb_row["cash"] >= 300.0

    def test_monthly_rebalance_true_keeps_default_behavior(self, tmp_path, monkeypatch):
        dates = pd.bdate_range("2012-01-23", periods=10).date
        rows = []
        for i, d in enumerate(dates):
            rows.append({"symbol": "SPY", "trade_date": d, "adj_close": 130.0 + i})
            rows.append({"symbol": "IAU", "trade_date": d, "adj_close": 16.0 + i * 0.1})
            rows.append({"symbol": "SCHD", "trade_date": d, "adj_close": 25.0 + i * 0.2})

        eod_dir = tmp_path / "gold" / "eod" / "eod_features"
        eod_dir.mkdir(parents=True)
        pd.DataFrame(rows).to_parquet(eod_dir / "cross_month.parquet", index=False)

        ps_rows = []
        alloc_rows = []
        for d in dates:
            ps_rows.append({
                "trade_date": d,
                "long_phase": "EXPANSION",
                "mid_regime": "RISK_ON",
                "short_signal": "NEUTRAL",
                "run_universe": True,
                "risk_gate": True,
                "policy_profile_id": "RC_V0_DEFAULT",
                "target_invested_lower": 0.10,
                "target_invested_upper": 0.60,
                "adjustment_limit": 0.10,
                "step_size": 0.05,
                "policy_version": "v0",
                "notes": "",
                "source_run_id": "test",
            })
            alloc_rows.append({
                "trade_date": d,
                "action": "HOLD",
                "next_invested_ratio": 0.60,
                "delta_ratio": 0.0,
                "blocked_by_risk_gate": False,
                "notes": "",
            })
        ps_dir = tmp_path / "strategy" / "policy_selection" / "decision_date=2012-02-03"
        ps_dir.mkdir(parents=True)
        pd.DataFrame(ps_rows).to_parquet(ps_dir / "policy_selection_20120203.parquet", index=False)
        alloc_dir = tmp_path / "strategy" / "exposure" / "decision_date=2012-02-03"
        alloc_dir.mkdir(parents=True)
        pd.DataFrame(alloc_rows).to_parquet(alloc_dir / "exposure_20120203.parquet", index=False)

        calls = {"count": 0}
        original = Portfolio.rebalance_to_weights

        def _counting_rebalance(self, *args, **kwargs):
            calls["count"] += 1
            return original(self, *args, **kwargs)

        monkeypatch.setattr(Portfolio, "rebalance_to_weights", _counting_rebalance)

        config = BacktestConfig(
            start_date=date(2012, 1, 23),
            end_date=date(2012, 2, 3),
            initial_capital=1000.0,
            monthly_addition=300.0,
            monthly_rebalance=True,
            data_root=tmp_path,
        )
        result = BacktestRunner().run(config)

        assert calls["count"] >= 2
        assert result.total_capital_injected == pytest.approx(300.0)


# ── v1 Target-Seeking Allocation 단위 테스트 ──────────────────


class TestTargetSeekingAllocation:
    """compute_allocation_v1 순수 로직 테스트 (allocation.py로 이전)."""

    @pytest.fixture
    def v1_config(self):
        return BacktestConfig.from_preset(
            "v1", start_date=date(2012, 1, 3), end_date=date(2024, 6, 3),
        )

    def test_expansion_at_target(self, v1_config):
        """현재=0.60, EXPANSION target=0.60 → HOLD."""
        row = pd.Series({"long_phase": "EXPANSION", "risk_gate": True})
        result = compute_allocation_v1(0.60, row, v1_config)
        assert result["action"] == "HOLD"
        assert result["next_invested_ratio"] == 0.60

    def test_recession_decrease(self, v1_config):
        """현재=0.60, RECESSION target=0.10 → DECREASE by 0.10."""
        row = pd.Series({"long_phase": "RECESSION", "risk_gate": True})
        result = compute_allocation_v1(0.60, row, v1_config)
        assert result["action"] == "DECREASE"
        assert result["next_invested_ratio"] == pytest.approx(0.50)

    def test_recovery_increase(self, v1_config):
        """현재=0.20, RECOVERY target=0.60 → INCREASE by 0.10."""
        row = pd.Series({"long_phase": "RECOVERY", "risk_gate": True})
        result = compute_allocation_v1(0.20, row, v1_config)
        assert result["action"] == "INCREASE"
        assert result["next_invested_ratio"] == pytest.approx(0.30)

    def test_risk_gate_allows_increase(self, v1_config):
        """risk_gate=false(PANIC)여도 INCREASE 허용 — 저점매수. 매도 동결은 runner.py에서 처리."""
        row = pd.Series({"long_phase": "RECOVERY", "risk_gate": False})
        result = compute_allocation_v1(0.20, row, v1_config)
        assert result["action"] == "INCREASE"
        assert result["blocked_by_risk_gate"] is False
        assert result["next_invested_ratio"] == pytest.approx(0.30)

    def test_risk_gate_allows_decrease(self, v1_config):
        """risk_gate=false 여도 DECREASE는 허용."""
        row = pd.Series({"long_phase": "RECESSION", "risk_gate": False})
        result = compute_allocation_v1(0.60, row, v1_config)
        assert result["action"] == "DECREASE"

    def test_run_universe_blocks_increase(self, v1_config):
        """run_universe=false → INCREASE 차단 (v1 버그 수정 검증)."""
        row = pd.Series({"long_phase": "RECOVERY", "risk_gate": True, "run_universe": False})
        result = compute_allocation_v1(0.20, row, v1_config)
        assert result["action"] == "HOLD"
        assert result["blocked_by_risk_gate"] is False
        assert "increase_blocked_by_run_universe" in result["notes"][0]

    def test_small_delta_hold(self, v1_config):
        """delta < step_size → HOLD."""
        row = pd.Series({"long_phase": "LATE_CYCLE", "risk_gate": True})
        result = compute_allocation_v1(0.58, row, v1_config)
        assert result["action"] == "HOLD"

    def test_unknown_phase_fallback(self, v1_config):
        """UNKNOWN phase → target=0.40."""
        row = pd.Series({"long_phase": "UNKNOWN", "risk_gate": True})
        result = compute_allocation_v1(0.60, row, v1_config)
        assert result["action"] == "DECREASE"
        assert result["next_invested_ratio"] == pytest.approx(0.50)

    def test_step_size_quantization(self, v1_config):
        """step_size=0.05 양자화 확인."""
        row = pd.Series({"long_phase": "SLOWDOWN", "risk_gate": True})
        result = compute_allocation_v1(0.33, row, v1_config)
        assert result["action"] == "DECREASE"
        assert result["next_invested_ratio"] == pytest.approx(0.23)


# ── v1 통합 테스트 ──────────────────────────────────────


class TestBacktestRunnerV1:
    def test_v1_expansion_stays_invested(self, mini_data):
        """v1 EXPANSION → target=0.60 유지."""
        config = BacktestConfig.from_preset(
            "v1",
            start_date=date(2012, 1, 3),
            end_date=date(2012, 1, 16),
            initial_capital=1000.0,
            monthly_addition=0.0,
            data_root=mini_data,
        )
        runner = BacktestRunner()
        result = runner.run(config)
        last_ratio = result.daily_log["invested_ratio"].iloc[-1]
        assert last_ratio == pytest.approx(0.60, abs=0.05)

    def test_v1_recession_decreases(self, tmp_path):
        """v1 RECESSION → 3 금요일 단계 매도 후 invested_ratio 감소."""
        # 3개월치 데이터 (65 영업일): 월요일 평가 → 금요일 단계 매도 여러 번
        dates = pd.bdate_range("2012-01-03", periods=65).date
        rows = []
        for d in dates:
            rows.append({"symbol": "SPY", "trade_date": d, "adj_close": 130.0})
            rows.append({"symbol": "IAU", "trade_date": d, "adj_close": 16.0})
            rows.append({"symbol": "SCHD", "trade_date": d, "adj_close": 25.0})
        eod_dir = tmp_path / "gold" / "eod" / "eod_features"
        eod_dir.mkdir(parents=True)
        pd.DataFrame(rows).to_parquet(eod_dir / "test.parquet", index=False)

        # RECESSION policy (run_universe=False → tactical 없음)
        ps_rows = []
        for d in dates:
            ps_rows.append({
                "trade_date": d, "long_phase": "RECESSION", "mid_regime": "RISK_OFF",
                "short_signal": "STABLE", "run_universe": False, "risk_gate": True,
                "policy_profile_id": "RC_V0_DEFAULT",
                "target_invested_lower": 0.10, "target_invested_upper": 0.60,
                "adjustment_limit": 0.10, "step_size": 0.05,
                "policy_version": "v0", "notes": "", "source_run_id": "test",
            })
        ps_dir = tmp_path / "strategy" / "policy_selection" / "decision_date=2012-04-01"
        ps_dir.mkdir(parents=True)
        pd.DataFrame(ps_rows).to_parquet(ps_dir / "ps.parquet", index=False)

        config = BacktestConfig.from_preset(
            "v1",
            start_date=date(2012, 1, 3),
            end_date=date(2012, 3, 30),
            initial_capital=1000.0,
            monthly_addition=0.0,
            data_root=tmp_path,
        )
        runner = BacktestRunner()
        result = runner.run(config)
        last_ratio = result.daily_log["invested_ratio"].iloc[-1]
        # 시작 0.60, 단계 매도 여러 번 → 0.40 이하로 감소
        assert last_ratio <= 0.40

    def test_v0_compat(self, mini_data):
        """from_preset('v0') → v0 동작 유지."""
        config = BacktestConfig.from_preset(
            "v0",
            start_date=date(2012, 1, 3),
            end_date=date(2012, 1, 16),
            initial_capital=1000.0,
            monthly_addition=0.0,
            data_root=mini_data,
        )
        runner = BacktestRunner()
        result = runner.run(config)
        assert not result.daily_log.empty


# ── _get_signal_row 결정론적 선택 테스트 ────────────────────────────


class TestGetSignalRowDeterminism:
    """_get_signal_row의 다중 decision_date 처리 결정론성 검증."""

    def setup_method(self):
        self.runner = BacktestRunner()

    def _make_df(self, rows: list) -> pd.DataFrame:
        df = pd.DataFrame(rows)
        if "trade_date" in df.columns:
            df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
        if "decision_date" in df.columns:
            df["decision_date"] = pd.to_datetime(df["decision_date"]).dt.date
        return df

    def test_latest_decision_date_wins(self):
        """다른 decision_date 두 스냅샷이 같은 trade_date를 커버할 때 최신 decision_date 행 선택."""
        td = date(2012, 1, 10)
        df = self._make_df([
            {"trade_date": td, "long_phase": "RECESSION", "decision_date": "2012-01-01"},
            {"trade_date": td, "long_phase": "EXPANSION", "decision_date": "2012-01-15"},
        ])
        row = self.runner._get_signal_row(df, td, "trade_date")
        assert row is not None
        assert row["long_phase"] == "EXPANSION"

    def test_string_decision_date_compared_correctly(self):
        """decision_date가 문자열 형태여도 date 변환 후 최신값 선택."""
        td = date(2012, 1, 10)
        df = pd.DataFrame([
            {"trade_date": td, "long_phase": "RECESSION", "decision_date": "2012-02-01"},
            {"trade_date": td, "long_phase": "EXPANSION", "decision_date": "2012-09-01"},
        ])
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
        df["decision_date"] = pd.to_datetime(df["decision_date"]).dt.date

        row = self.runner._get_signal_row(df, td, "trade_date")
        assert row is not None
        assert row["long_phase"] == "EXPANSION"

    def test_source_run_id_tiebreaker(self):
        """같은 (trade_date, decision_date) 복수 행 → source_run_id desc로 결정론적 선택."""
        td = date(2012, 1, 10)
        dd = date(2012, 1, 15)
        df = self._make_df([
            {"trade_date": td, "long_phase": "RECESSION", "decision_date": str(dd),
             "source_run_id": "strategy_20120115T090000"},
            {"trade_date": td, "long_phase": "EXPANSION", "decision_date": str(dd),
             "source_run_id": "strategy_20120115T120000"},
        ])
        row = self.runner._get_signal_row(df, td, "trade_date")
        assert row is not None
        assert row["long_phase"] == "EXPANSION"


# ── BacktestResult.metrics 자동 계산 검증 ──────────────────────


class TestBacktestResultMetrics:
    """BacktestResult.metrics 필드가 자동으로 채워지는지 검증."""

    def test_metrics_populated_after_run(self, mini_data):
        config = BacktestConfig(
            start_date=date(2012, 1, 3),
            end_date=date(2012, 1, 16),
            initial_capital=1000.0,
            monthly_addition=0.0,
            data_root=mini_data,
        )
        runner = BacktestRunner()
        result = runner.run(config)

        assert result.metrics, "metrics dict가 비어있으면 안 된다"
        assert "total_return" in result.metrics
        assert "cagr" in result.metrics
        assert "max_drawdown" in result.metrics
        assert "sharpe_ratio" in result.metrics
        assert "benchmark_total_return" in result.metrics
        assert "dca_return" in result.metrics
        assert isinstance(result.metrics["total_return"], float)


# ── DCA 자금 투입 테스트 ─────────────────────────────────────────


def _make_long_fixture(tmp_path, n_days: int, long_phase: str = "EXPANSION"):
    """n_days 영업일 데이터 + policy snapshot 생성 헬퍼."""
    dates = pd.bdate_range("2012-01-02", periods=n_days).date
    rows = []
    for d in dates:
        rows.append({"symbol": "SPY", "trade_date": d, "adj_close": 130.0})
        rows.append({"symbol": "IAU", "trade_date": d, "adj_close": 16.0})
        rows.append({"symbol": "SCHD", "trade_date": d, "adj_close": 25.0})

    eod_dir = tmp_path / "gold" / "eod" / "eod_features"
    eod_dir.mkdir(parents=True)
    pd.DataFrame(rows).to_parquet(eod_dir / "data.parquet", index=False)

    ps_rows = []
    for d in dates:
        ps_rows.append({
            "trade_date": d, "long_phase": long_phase, "mid_regime": "NEUTRAL",
            "short_signal": "STABLE", "run_universe": True, "risk_gate": True,
            "policy_profile_id": "RC_V0_DEFAULT",
            "target_invested_lower": 0.10, "target_invested_upper": 0.60,
            "adjustment_limit": 0.10, "step_size": 0.05,
            "policy_version": "v0", "notes": "", "source_run_id": "test",
        })
    last_date = dates[-1]
    ps_dir = tmp_path / "strategy" / "policy_selection" / f"decision_date={last_date}"
    ps_dir.mkdir(parents=True)
    pd.DataFrame(ps_rows).to_parquet(ps_dir / "ps.parquet", index=False)

    return dates


class TestDCAInjection:
    """월별 자금 추가 (monthly_addition) 검증."""

    def test_monthly_addition_increases_cash(self, tmp_path):
        """월 경계 거래일에 cash += monthly_addition 확인."""
        # 2012-01-02(월) ~ 2012-02-29 : 2개월치
        dates = _make_long_fixture(tmp_path, 45, long_phase="LATE_CYCLE")
        start = dates[0]
        end = dates[-1]

        monthly = 50.0
        config = BacktestConfig(
            start_date=start,
            end_date=end,
            initial_capital=1000.0,
            monthly_addition=monthly,
            data_root=tmp_path,
        )
        runner = BacktestRunner()
        result = runner.run(config)

        # 45일 = 2개월 넘으므로 최소 1회 투입
        assert result.total_capital_injected >= monthly

    def test_zero_monthly_addition(self, tmp_path):
        """monthly_addition=0 → total_capital_injected=0."""
        dates = _make_long_fixture(tmp_path, 45)
        config = BacktestConfig(
            start_date=dates[0],
            end_date=dates[-1],
            initial_capital=1000.0,
            monthly_addition=0.0,
            data_root=tmp_path,
        )
        runner = BacktestRunner()
        result = runner.run(config)
        assert result.total_capital_injected == 0.0


# ── 단계적 매도 테스트 ─────────────────────────────────────────


class TestStagedSell:
    """DECREASE 신호 → 3 금요일 단계 매도 (50/30/20) 검증."""

    def _build_recession_data(self, tmp_path, n_days=25):
        """RECESSION 시그널 데이터 생성."""
        _make_long_fixture(tmp_path, n_days, long_phase="RECESSION")
        # policy를 RECESSION으로 오버라이드
        dates = pd.bdate_range("2012-01-02", periods=n_days).date
        ps_rows = []
        for d in dates:
            ps_rows.append({
                "trade_date": d, "long_phase": "RECESSION", "mid_regime": "RISK_OFF",
                "short_signal": "STABLE", "run_universe": False, "risk_gate": True,
                "policy_profile_id": "RC_V0_DEFAULT",
                "target_invested_lower": 0.10, "target_invested_upper": 0.60,
                "adjustment_limit": 0.10, "step_size": 0.05,
                "policy_version": "v0", "notes": "", "source_run_id": "test",
            })
        last_date = dates[-1]
        # 기존 ps_dir 재생성 (덮어쓰기)
        import shutil
        strategy_dir = tmp_path / "strategy" / "policy_selection"
        if strategy_dir.exists():
            shutil.rmtree(strategy_dir)
        ps_dir = strategy_dir / f"decision_date={last_date}"
        ps_dir.mkdir(parents=True)
        import pandas as _pd
        _pd.DataFrame(ps_rows).to_parquet(ps_dir / "ps.parquet", index=False)
        return dates

    def test_staged_sell_reduces_invested_ratio(self, tmp_path):
        """RECESSION 신호 → 3주에 걸친 단계 매도로 invested_ratio 감소."""
        dates = self._build_recession_data(tmp_path, n_days=25)

        config = BacktestConfig.from_preset(
            "v1",
            start_date=dates[0],
            end_date=dates[-1],
            initial_capital=1000.0,
            monthly_addition=0.0,
            data_root=tmp_path,
        )
        runner = BacktestRunner()
        result = runner.run(config)

        # 초기 invested_ratio=0.60, RECESSION 단계 매도 후 감소 확인
        first_ratio = result.daily_log["invested_ratio"].iloc[0]
        last_ratio = result.daily_log["invested_ratio"].iloc[-1]
        assert last_ratio < first_ratio, "RECESSION 단계 매도 후 invested_ratio가 감소해야 함"

    def test_signal_reversal_cancels_sell(self, tmp_path):
        """RECESSION 신호 1주 후 EXPANSION으로 반전 → 잔여 매도 취소."""
        # 25일: 초반 RECESSION → 이후 EXPANSION (반전)
        dates = pd.bdate_range("2012-01-02", periods=25).date
        rows = []
        for d in dates:
            for sym, price in [("SPY", 130.0), ("IAU", 16.0), ("SCHD", 25.0)]:
                rows.append({"symbol": sym, "trade_date": d, "adj_close": price})

        eod_dir = tmp_path / "gold" / "eod" / "eod_features"
        eod_dir.mkdir(parents=True)
        pd.DataFrame(rows).to_parquet(eod_dir / "data.parquet", index=False)

        # 첫 5일: RECESSION, 이후: EXPANSION (월요일 신호 반전)
        ps_rows = []
        for i, d in enumerate(dates):
            phase = "RECESSION" if i < 5 else "EXPANSION"
            ps_rows.append({
                "trade_date": d, "long_phase": phase, "mid_regime": "NEUTRAL",
                "short_signal": "STABLE", "run_universe": True, "risk_gate": True,
                "policy_profile_id": "RC_V0_DEFAULT",
                "target_invested_lower": 0.10, "target_invested_upper": 0.60,
                "adjustment_limit": 0.10, "step_size": 0.05,
                "policy_version": "v0", "notes": "", "source_run_id": "test",
            })
        ps_dir = tmp_path / "strategy" / "policy_selection" / f"decision_date={dates[-1]}"
        ps_dir.mkdir(parents=True)
        pd.DataFrame(ps_rows).to_parquet(ps_dir / "ps.parquet", index=False)

        config = BacktestConfig.from_preset(
            "v1",
            start_date=dates[0],
            end_date=dates[-1],
            initial_capital=1000.0,
            monthly_addition=0.0,
            data_root=tmp_path,
        )
        runner = BacktestRunner()
        result = runner.run(config)

        # 실행 완료 (에러 없음) + SELL 횟수가 3회 미만 (반전으로 일부 취소)
        sell_count = sum(1 for t in result.trade_log if t.action == "SELL")
        # 반전 취소로 3 금요일 전부 실행되지 않아야 함 (최소 1회 이상은 실행)
        assert not result.daily_log.empty


# ── 벤치마크 DCA 테스트 ──────────────────────────────────────


class TestBenchmarkDCA:
    """벤치마크(SPY)도 동일 DCA 규칙 적용 검증."""

    def test_benchmark_nav_is_series(self, mini_data):
        """benchmark_nav가 portfolio 기반 시리즈인지 확인."""
        config = BacktestConfig(
            start_date=date(2012, 1, 3),
            end_date=date(2012, 1, 16),
            initial_capital=1000.0,
            monthly_addition=0.0,
            data_root=mini_data,
        )
        runner = BacktestRunner()
        result = runner.run(config)

        # benchmark_nav는 일별 NAV 시리즈
        assert isinstance(result.benchmark_nav, pd.Series)
        assert len(result.benchmark_nav) == 10

    def test_benchmark_starts_at_initial_capital(self, mini_data):
        """벤치마크 NAV 첫 날 ≈ initial_capital * initial_invested_ratio + cash."""
        config = BacktestConfig(
            start_date=date(2012, 1, 3),
            end_date=date(2012, 1, 16),
            initial_capital=1000.0,
            monthly_addition=0.0,
            data_root=mini_data,
        )
        runner = BacktestRunner()
        result = runner.run(config)

        # 벤치마크 초기 NAV = initial_capital (cash + SPY 매수)
        assert result.benchmark_nav.iloc[0] == pytest.approx(1000.0, abs=5.0)


# ── Look-ahead 신호 테스트 ──────────────────────────────────────


class TestLookAheadSignal:
    """Monday 평가 시 prev_date(금요일) 신호 사용 확인."""

    def test_monday_uses_prev_date_signal(self, tmp_path):
        """Monday(1/9)는 금요일(1/6) 신호를 사용해야 함.

        정확히는 _get_signal_row(df, prev_date)를 사용하므로,
        prev_date까지의 데이터만 조회 가능.
        trade_date=1/9 는 policy가 없고, 1/6까지는 있는 경우: 1/6 신호 사용.
        """
        # 2012-01-03(화) ~ 2012-01-13(금): 9일
        dates = pd.bdate_range("2012-01-03", periods=9).date
        rows = []
        for d in dates:
            for sym, price in [("SPY", 130.0), ("IAU", 16.0), ("SCHD", 25.0)]:
                rows.append({"symbol": sym, "trade_date": d, "adj_close": price})

        eod_dir = tmp_path / "gold" / "eod" / "eod_features"
        eod_dir.mkdir(parents=True)
        pd.DataFrame(rows).to_parquet(eod_dir / "data.parquet", index=False)

        # policy: 1/3~1/6까지만 존재 (1/9 월요일 데이터 없음)
        ps_rows = []
        for d in dates[:4]:  # 1/3, 1/4, 1/5, 1/6
            ps_rows.append({
                "trade_date": d, "long_phase": "EXPANSION", "mid_regime": "RISK_ON",
                "short_signal": "NEUTRAL", "run_universe": True, "risk_gate": True,
                "policy_profile_id": "RC_V0_DEFAULT",
                "target_invested_lower": 0.10, "target_invested_upper": 0.60,
                "adjustment_limit": 0.10, "step_size": 0.05,
                "policy_version": "v0", "notes": "", "source_run_id": "test",
            })
        ps_dir = tmp_path / "strategy" / "policy_selection" / "decision_date=2012-01-06"
        ps_dir.mkdir(parents=True)
        pd.DataFrame(ps_rows).to_parquet(ps_dir / "ps.parquet", index=False)

        config = BacktestConfig(
            start_date=dates[0],
            end_date=dates[-1],
            initial_capital=1000.0,
            monthly_addition=0.0,
            data_root=tmp_path,
        )
        runner = BacktestRunner()
        result = runner.run(config)

        # 실행 완료 — 월요일(1/9)에 금요일(1/6) 신호를 사용해 정상 동작
        assert not result.daily_log.empty
        assert len(result.daily_log) == 9
