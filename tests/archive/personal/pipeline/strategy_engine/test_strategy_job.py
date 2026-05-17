"""
Strategy Engine E2E Runner 테스트.

SOT: docs/architecture/strategy_engine_design.md
DoD:
  - E2E smoke: 합성 데이터로 전체 파이프라인 실행
  - 각 단계 결과 존재 확인
  - 멱등성 (동일 date 재실행 시 동일 결과)
  - 스냅샷 저장 경로 검증
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from pretrend.pipeline.strategy_engine.config import StrategyEngineConfig
from pretrend.pipeline.strategy_engine.strategy_job import (
    StrategyJobRunner,
    StrategyJobResult,
)


def _create_gold_fixtures(data_root: Path) -> None:
    """합성 Gold Macro + EOD 파일 생성."""
    # Gold Macro
    macro_dir = data_root / "gold" / "macro" / "macro_features" / "year=2024" / "month=06"
    macro_dir.mkdir(parents=True, exist_ok=True)

    dates = [date(2024, 6, 3), date(2024, 6, 4)]
    indicators = ["CPI_US_ALL_ITEMS_SA", "US_UNEMPLOYMENT_RATE"]
    macro_rows = []
    for td in dates:
        for ind in indicators:
            macro_rows.append({
                "indicator_id": ind,
                "trade_date": td,
                "selected_observation_date": date(2024, 5, 1),
                "selected_value": 310.0 if "CPI" in ind else 3.9,
                "selected_release_date": date(2024, 6, 1),
                "delta_1m": 0.5,
                "delta_3m": 1.2,
                "delta_6m": 2.1,
                "direction": "up",
                "regime": "tightening",
                "zscore_12m": 1.1,
                "release_source": "econ_events",
                "is_assumption_based": False,
            })
    pd.DataFrame(macro_rows).to_parquet(
        macro_dir / "gold_macro_features_202406.parquet", index=False
    )

    # Gold EOD
    eod_dir = data_root / "gold" / "eod" / "eod_features" / "year=2024" / "month=06"
    eod_dir.mkdir(parents=True, exist_ok=True)

    symbols = ["SPY", "TLT", "IAU", "IWM"]
    eod_rows = []
    for td in dates:
        for i, sym in enumerate(symbols):
            eod_rows.append({
                "symbol": sym, "trade_date": td,
                "open": 500.0 + i, "high": 505.0 + i, "low": 498.0 + i,
                "close": 503.0 + i, "adj_close": 503.0 + i,
                "volume": 1_000_000 * (i + 1), "currency": "USD",
                "prev_adj_close": 501.0 + i,
                "ret_1d": 0.004 * ((-1) ** i),
                "log_ret_1d": 0.004 * ((-1) ** i),
                "ret_5d": 0.02 * ((-1) ** i),
                "ret_20d": 0.05 * ((-1) ** i),
                "vol_20d": 0.15 + 0.02 * i,
                "vol_60d": 0.14 + 0.02 * i,
                "ma_5": 500.0, "ma_20": 498.0, "ma_60": 495.0, "ma_120": 490.0,
                "ma_ratio_5_20": 1.004,
                "atr_14": 5.0 + i, "rsi_14": 55.0 + i * 3,
                "intraday_range": 0.014 + 0.002 * i,
                "gap_open": 0.001,
                "volume_zscore_20d": 0.5 + i * 0.8,
                "is_trading_day": True, "is_missing_imputed": False,
                "is_outlier": False, "is_partial_day": False,
                "asset_group": "INDEX" if sym in ("SPY", "IWM") else ("BOND" if sym == "TLT" else "COMMODITY"),
                "asset_name": sym, "asset_subtype": None,
                "run_id_gold": "test_run",
                "ingestion_ts_gold": pd.Timestamp.now("UTC"),
            })
    pd.DataFrame(eod_rows).to_parquet(
        eod_dir / "gold_eod_features_202406.parquet", index=False
    )


def _create_gold_text_fixtures(data_root: Path) -> None:
    rule_dir = data_root / "gold" / "text" / "text_daily_features" / "year=2024" / "month=06"
    llm_dir = data_root / "gold" / "text" / "text_llm_features" / "year=2024" / "month=06"
    rule_dir.mkdir(parents=True, exist_ok=True)
    llm_dir.mkdir(parents=True, exist_ok=True)

    rule_rows = [
        {
            "trade_date": "2024-06-03",
            "feature_name": "macro_hawkish_score",
            "feature_value": 0.7,
            "feature_version": "v0",
            "coverage_ratio": 1.0,
            "staleness_days": 0,
        },
        {
            "trade_date": "2024-06-03",
            "feature_name": "filing_risk_burst",
            "feature_value": 0.0,
            "feature_version": "v0",
            "coverage_ratio": 1.0,
            "staleness_days": 0,
        },
        {
            "trade_date": "2024-06-03",
            "feature_name": "policy_uncertainty_idx",
            "feature_value": 0.8,
            "feature_version": "v0",
            "coverage_ratio": 1.0,
            "staleness_days": 0,
        },
        {
            "trade_date": "2024-06-04",
            "feature_name": "macro_hawkish_score",
            "feature_value": 0.7,
            "feature_version": "v0",
            "coverage_ratio": 1.0,
            "staleness_days": 0,
        },
        {
            "trade_date": "2024-06-04",
            "feature_name": "filing_risk_burst",
            "feature_value": 2.5,
            "feature_version": "v0",
            "coverage_ratio": 1.0,
            "staleness_days": 0,
        },
        {
            "trade_date": "2024-06-04",
            "feature_name": "policy_uncertainty_idx",
            "feature_value": 0.8,
            "feature_version": "v0",
            "coverage_ratio": 1.0,
            "staleness_days": 0,
        },
    ]
    pd.DataFrame(rule_rows).to_parquet(rule_dir / "gold_text_202406.parquet", index=False)

    llm_rows = [
        {
            "trade_date": "2024-06-03",
            "doc_id": "doc1",
            "source": "fed_fomc",
            "feature_name": "llm_tone",
            "feature_value": 1.0,
            "feature_str": None,
            "confidence": 0.9,
            "feature_version": "v1",
            "model_id": "llama3.1:latest",
            "prompt_version": "text_annotation_v2",
            "coverage_ratio": 1.0,
            "staleness_days": 0,
        },
        {
            "trade_date": "2024-06-03",
            "doc_id": "doc1",
            "source": "fed_fomc",
            "feature_name": "llm_tags",
            "feature_value": 0.0,
            "feature_str": '[{\"category\":\"policy_action\",\"item\":\"hike\"}]',
            "confidence": 0.9,
            "feature_version": "v1",
            "model_id": "llama3.1:latest",
            "prompt_version": "text_annotation_v2",
            "coverage_ratio": 1.0,
            "staleness_days": 0,
        },
        {
            "trade_date": "2024-06-04",
            "doc_id": "doc2",
            "source": "fed_fomc",
            "feature_name": "llm_tone",
            "feature_value": 1.0,
            "feature_str": None,
            "confidence": 0.9,
            "feature_version": "v1",
            "model_id": "llama3.1:latest",
            "prompt_version": "text_annotation_v2",
            "coverage_ratio": 1.0,
            "staleness_days": 0,
        },
        {
            "trade_date": "2024-06-04",
            "doc_id": "doc2",
            "source": "fed_fomc",
            "feature_name": "llm_tags",
            "feature_value": 0.0,
            "feature_str": '[{\"category\":\"policy_action\",\"item\":\"hike\"}]',
            "confidence": 0.9,
            "feature_version": "v1",
            "model_id": "llama3.1:latest",
            "prompt_version": "text_annotation_v2",
            "coverage_ratio": 1.0,
            "staleness_days": 0,
        },
    ]
    pd.DataFrame(llm_rows).to_parquet(llm_dir / "gold_llm_202406.parquet", index=False)


class TestStrategyJobE2E:
    def test_smoke_run(self, tmp_path):
        """합성 데이터로 전체 파이프라인 실행."""
        _create_gold_fixtures(tmp_path)
        config = StrategyEngineConfig(data_root=tmp_path)
        runner = StrategyJobRunner(config, current_invested_ratio=0.10)
        result = runner.run(date(2024, 6, 4))

        assert isinstance(result, StrategyJobResult)
        assert result.decision_date == date(2024, 6, 4)
        assert result.run_id.startswith("strategy_")

    def test_all_stages_have_results(self, tmp_path):
        """각 단계 결과 존재 확인."""
        _create_gold_fixtures(tmp_path)
        config = StrategyEngineConfig(data_root=tmp_path)
        runner = StrategyJobRunner(config, current_invested_ratio=0.10)
        result = runner.run(date(2024, 6, 4))

        assert result.axis_features.row_count > 0
        assert result.axis_horizon_state.row_count > 0
        assert result.market_position.row_count > 0
        assert result.text_overlay_signal.row_count > 0
        assert result.policy_selection.row_count > 0
        assert result.allocation.row_count > 0
        assert result.group_transition_signal.row_count >= 0

    def test_snapshot_files_created(self, tmp_path):
        """스냅샷 파일 생성 확인."""
        _create_gold_fixtures(tmp_path)
        config = StrategyEngineConfig(data_root=tmp_path)
        runner = StrategyJobRunner(config, current_invested_ratio=0.10)
        runner.run(date(2024, 6, 4))

        strategy_root = tmp_path / "strategy"
        assert (strategy_root / "axis_horizon_state").exists()
        assert (strategy_root / "market_position").exists()
        assert (strategy_root / "policy_selection").exists()
        assert (strategy_root / "text_overlay_signal").exists()
        assert (strategy_root / "exposure").exists()
        assert (strategy_root / "group_transition_signal").exists()
        assert (strategy_root / "group_transition_history").exists()

    def test_snapshot_path_convention(self, tmp_path):
        """decision_date 파티션 경로 검증."""
        _create_gold_fixtures(tmp_path)
        config = StrategyEngineConfig(data_root=tmp_path)
        runner = StrategyJobRunner(config, current_invested_ratio=0.10)
        runner.run(date(2024, 6, 4))

        ahs_dir = tmp_path / "strategy" / "axis_horizon_state" / "decision_date=2024-06-04"
        assert ahs_dir.exists()
        parquets = list(ahs_dir.glob("*.parquet"))
        assert len(parquets) == 1
        assert "20240604" in parquets[0].name

    def test_idempotent_rerun(self, tmp_path):
        """동일 date 재실행 시 동일 결과."""
        _create_gold_fixtures(tmp_path)
        config = StrategyEngineConfig(data_root=tmp_path)
        runner = StrategyJobRunner(config, current_invested_ratio=0.10)

        result1 = runner.run(date(2024, 6, 4))
        result2 = runner.run(date(2024, 6, 4))

        # 같은 단계별 row_count
        assert result1.axis_horizon_state.row_count == result2.axis_horizon_state.row_count
        assert result1.allocation.row_count == result2.allocation.row_count

        # 파일 하나만 존재 (overwrite)
        ahs_dir = tmp_path / "strategy" / "axis_horizon_state" / "decision_date=2024-06-04"
        assert len(list(ahs_dir.glob("*.parquet"))) == 1

    def test_meta_log_written(self, tmp_path):
        """메타 로그 기록 확인."""
        _create_gold_fixtures(tmp_path)
        config = StrategyEngineConfig(data_root=tmp_path)
        runner = StrategyJobRunner(config, current_invested_ratio=0.10)
        runner.run(date(2024, 6, 4))

        log_path = config.strategy_job_log_path
        assert log_path.exists()
        df = pd.read_parquet(log_path)
        assert len(df) >= 1
        assert "run_id" in df.columns
        assert "text_overlay_rows" in df.columns
        assert "group_transition_rows" in df.columns

    def test_text_overlay_signal_and_policy_selection_columns(self, tmp_path):
        _create_gold_fixtures(tmp_path)
        _create_gold_text_fixtures(tmp_path)
        config = StrategyEngineConfig(data_root=tmp_path)
        runner = StrategyJobRunner(config, current_invested_ratio=0.10)
        result = runner.run(date(2024, 6, 4))

        assert result.text_overlay_signal.row_count > 0
        text_path = tmp_path / "strategy" / "text_overlay_signal" / "decision_date=2024-06-04"
        df_text = pd.read_parquet(next(text_path.glob("*.parquet")))
        assert "text_signal_state" in df_text.columns
        assert "text_top_tags_json" in df_text.columns
        assert set(df_text["text_signal_state"]).issubset({"RISK_ON", "NEUTRAL", "RISK_OFF", "UNKNOWN"})

        ps_path = tmp_path / "strategy" / "policy_selection" / "decision_date=2024-06-04"
        df_ps = pd.read_parquet(next(ps_path.glob("*.parquet")))
        assert "text_signal_state" in df_ps.columns
        assert "text_signal_confidence" in df_ps.columns

    def test_empty_gold_data(self, tmp_path):
        """Gold 데이터 없어도 에러 없이 완료."""
        config = StrategyEngineConfig(data_root=tmp_path)
        runner = StrategyJobRunner(config, current_invested_ratio=0.50)
        result = runner.run(date(2024, 6, 4))
        assert result.axis_horizon_state.row_count == 0
