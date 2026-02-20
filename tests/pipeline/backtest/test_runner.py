"""BacktestRunner 통합 테스트 (in-memory fixture)."""
from datetime import date

import pandas as pd
import pytest

from pretrend.pipeline.backtest.config import BacktestConfig
from pretrend.pipeline.backtest.runner import BacktestRunner
from pretrend.pipeline.backtest.allocation import compute_allocation_v1


@pytest.fixture
def mini_data(tmp_path):
    """최소 Gold EOD + Strategy snapshot fixture."""
    # Gold EOD: SPY, IAU — 10 영업일
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
            data_root=mini_data,
        )
        runner = BacktestRunner()
        result = runner.run(config)

        assert len(result.benchmark_nav) == 10
        assert result.benchmark_nav.iloc[0] == 1000.0  # starts at initial capital

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
            data_root=tmp_path,
        )
        runner = BacktestRunner()
        result = runner.run(config)

        assert not result.daily_log.empty
        # SPY 80%, IAU 20% → no SCHD position
        buy_symbols = {t.symbol for t in result.trade_log if t.action == "BUY"}
        assert "SPY" in buy_symbols
        assert "IAU" in buy_symbols
        assert "SCHD" not in buy_symbols


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

    def test_risk_gate_blocks_increase(self, v1_config):
        """risk_gate=false → INCREASE 차단."""
        row = pd.Series({"long_phase": "RECOVERY", "risk_gate": False})
        result = compute_allocation_v1(0.20, row, v1_config)
        assert result["action"] == "HOLD"
        assert result["blocked_by_risk_gate"] is True
        assert result["next_invested_ratio"] == 0.20

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
        # target=0.60, current=0.58 → delta=0.02 < step_size=0.05
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
        # target=0.20, current=0.33 → raw_delta=0.13, limit=0.10, quantize(0.10,0.05)=0.10
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
            data_root=mini_data,
        )
        runner = BacktestRunner()
        result = runner.run(config)
        last_ratio = result.daily_log["invested_ratio"].iloc[-1]
        assert last_ratio == pytest.approx(0.60, abs=0.05)

    def test_v1_recession_decreases(self, tmp_path):
        """v1 RECESSION → invested_ratio 감소."""
        # 3개월치 데이터 (리밸런싱 3회)
        dates = pd.bdate_range("2012-01-03", periods=65).date
        rows = []
        for d in dates:
            rows.append({"symbol": "SPY", "trade_date": d, "adj_close": 130.0})
            rows.append({"symbol": "IAU", "trade_date": d, "adj_close": 16.0})
            rows.append({"symbol": "SCHD", "trade_date": d, "adj_close": 25.0})
        eod_dir = tmp_path / "gold" / "eod" / "eod_features"
        eod_dir.mkdir(parents=True)
        pd.DataFrame(rows).to_parquet(eod_dir / "test.parquet", index=False)

        # RECESSION policy
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
            data_root=tmp_path,
        )
        runner = BacktestRunner()
        result = runner.run(config)
        last_ratio = result.daily_log["invested_ratio"].iloc[-1]
        # 시작 0.60, 매월 -0.10씩 감소, 3회 리밸런싱 → ≤0.40
        assert last_ratio <= 0.40

    def test_v0_compat(self, mini_data):
        """from_preset('v0') → v0 동작 유지."""
        config = BacktestConfig.from_preset(
            "v0",
            start_date=date(2012, 1, 3),
            end_date=date(2012, 1, 16),
            initial_capital=1000.0,
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
        # 최신 decision_date=2012-01-15 행 → EXPANSION
        assert row["long_phase"] == "EXPANSION"

    def test_string_decision_date_compared_correctly(self):
        """decision_date가 문자열 형태여도 date 변환 후 최신값 선택 (사전식 오류 방지)."""
        td = date(2012, 1, 10)
        # '2012-01-09' vs '2012-01-15' — 사전식으로도 맞지만 의미론적으로도 검증
        # '2009-12-01' vs '2012-01-01' 케이스: 사전식이면 '2012-...' > '2009-...' 이므로 OK
        # 하지만 '2012-02-01' vs '2012-09-01'처럼 month이 한 자리인 경우 사전식 문제가 생길 수 있음
        df = pd.DataFrame([
            {"trade_date": td, "long_phase": "RECESSION", "decision_date": "2012-02-01"},
            {"trade_date": td, "long_phase": "EXPANSION", "decision_date": "2012-09-01"},
        ])
        # date_col로 로드 시 _load_snapshot에서 정규화됨 — 여기선 수동으로 date 변환
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
        df["decision_date"] = pd.to_datetime(df["decision_date"]).dt.date

        row = self.runner._get_signal_row(df, td, "trade_date")
        assert row is not None
        # 최신 decision_date=2012-09-01 행 → EXPANSION
        assert row["long_phase"] == "EXPANSION"

    def test_source_run_id_tiebreaker(self):
        """같은 (trade_date, decision_date) 복수 행 → source_run_id desc로 결정론적 선택."""
        td = date(2012, 1, 10)
        dd = date(2012, 1, 15)
        df = self._make_df([
            {"trade_date": td, "long_phase": "RECESSION", "decision_date": str(dd),
             "source_run_id": "strategy_20120115T090000"},
            {"trade_date": td, "long_phase": "EXPANSION", "decision_date": str(dd),
             "source_run_id": "strategy_20120115T120000"},  # 더 늦은 run_id
        ])
        row = self.runner._get_signal_row(df, td, "trade_date")
        assert row is not None
        # source_run_id desc → "strategy_20120115T120000" 행 → EXPANSION
        assert row["long_phase"] == "EXPANSION"


# ── BacktestResult.metrics 자동 계산 검증 ──────────────────────


class TestBacktestResultMetrics:
    """BacktestResult.metrics 필드가 자동으로 채워지는지 검증."""

    def test_metrics_populated_after_run(self, mini_data):
        """run() 완료 후 metrics에 total_return, cagr, max_drawdown이 포함되어야 한다."""
        config = BacktestConfig(
            start_date=date(2012, 1, 3),
            end_date=date(2012, 1, 16),
            initial_capital=1000.0,
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
        # total_return은 float 타입이어야 한다
        assert isinstance(result.metrics["total_return"], float)
