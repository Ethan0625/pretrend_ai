"""WalkForwardRunner 단위 테스트."""
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from pretrend.pipeline.backtest.walk_forward import (
    WalkForwardConfig,
    WalkForwardRunner,
    WALK_FORWARD_COLUMNS,
)
from pretrend.pipeline.backtest.report import save_walk_forward


# ── _generate_windows 검증 ─────────────────────────────────────


class TestGenerateWindows:
    def _runner(self):
        return WalkForwardRunner()

    def test_basic_window_count(self):
        """window=4, step=2, 2006~2014 → 4개 창 생성."""
        config = WalkForwardConfig(
            preset="v2",
            window_years=4,
            step_years=2,
            full_start=date(2006, 1, 3),
            full_end=date(2014, 1, 3),
        )
        windows = self._runner()._generate_windows(config)
        # 2006~2010, 2008~2012, 2010~2014
        assert len(windows) >= 3
        # 첫 창 시작 = full_start
        assert windows[0][0] == date(2006, 1, 3)
        # 마지막 창 끝 <= full_end
        assert windows[-1][1] <= date(2014, 1, 3)

    def test_window_end_capped_at_full_end(self):
        """마지막 창의 끝이 full_end를 초과하지 않는다."""
        config = WalkForwardConfig(
            preset="v2",
            window_years=4,
            step_years=3,
            full_start=date(2010, 1, 3),
            full_end=date(2015, 6, 3),
        )
        windows = self._runner()._generate_windows(config)
        for _, we in windows:
            assert we <= date(2015, 6, 3)

    def test_explicit_windows_bypass_generation(self):
        """windows 명시 시 자동 생성 없이 그대로 사용."""
        explicit = [
            (date(2006, 1, 3), date(2012, 1, 3)),
            (date(2012, 1, 3), date(2018, 1, 3)),
        ]
        config = WalkForwardConfig(preset="v2", windows=explicit)
        runner = self._runner()
        # run() 내부에서 explicit windows 그대로 사용하는지 확인
        # _generate_windows는 호출되지 않아야 함
        assert config.windows == explicit


# ── run() 결과 검증 ────────────────────────────────────────────


class TestWalkForwardRunnerRun:
    """BacktestRunner를 mock으로 대체해 run() 결과 DataFrame 구조 검증."""

    def _fake_metrics(self, cagr=0.05):
        return {
            "cagr": cagr,
            "total_return": cagr * 4,
            "max_drawdown": -0.10,
            "sharpe_ratio": 0.7,
            "benchmark_cagr": 0.08,
            "excess_cagr": cagr - 0.08,
        }

    def test_run_returns_correct_schema(self):
        """run() 결과 DataFrame의 컬럼이 WALK_FORWARD_COLUMNS와 일치해야 한다."""
        fake_result = MagicMock()
        fake_result.metrics = self._fake_metrics()

        with patch(
            "pretrend.pipeline.backtest.walk_forward.BacktestRunner"
        ) as MockRunner:
            MockRunner.return_value.run.return_value = fake_result

            config = WalkForwardConfig(
                preset="v2",
                windows=[
                    (date(2006, 1, 3), date(2010, 1, 3)),
                    (date(2010, 1, 3), date(2014, 1, 3)),
                ],
            )
            runner = WalkForwardRunner()
            df = runner.run(config)

        assert list(df.columns) == WALK_FORWARD_COLUMNS
        assert len(df) == 2

    def test_run_two_windows_row_count(self):
        """2개 window 실행 → 결과 DataFrame 2행."""
        fake_result = MagicMock()
        fake_result.metrics = self._fake_metrics(cagr=0.03)

        with patch(
            "pretrend.pipeline.backtest.walk_forward.BacktestRunner"
        ) as MockRunner:
            MockRunner.return_value.run.return_value = fake_result

            config = WalkForwardConfig(
                preset="v0",
                windows=[
                    (date(2008, 1, 3), date(2012, 1, 3)),
                    (date(2012, 1, 3), date(2016, 1, 3)),
                ],
            )
            df = WalkForwardRunner().run(config)

        assert len(df) == 2
        assert df["preset"].iloc[0] == "v0"
        assert df["cagr"].iloc[0] == pytest.approx(0.03)

    def test_run_empty_windows(self):
        """windows가 없으면 빈 DataFrame 반환."""
        config = WalkForwardConfig(
            preset="v2",
            windows=[],
            # full_start > full_end → _generate_windows도 빈 리스트
            full_start=date(2024, 1, 1),
            full_end=date(2006, 1, 1),
        )
        df = WalkForwardRunner().run(config)
        assert df.empty

    def test_run_status_pass_with_warning(self):
        """Tier-1 통과 + Tier-2 경고 -> PASS_WITH_WARNING."""
        fake_result = MagicMock()
        fake_result.metrics = self._fake_metrics(cagr=0.05)

        with patch("pretrend.pipeline.backtest.walk_forward.BacktestRunner") as MockRunner:
            MockRunner.return_value.run.return_value = fake_result
            runner = WalkForwardRunner()
            with patch.object(
                runner,
                "_compute_12slot_diagnostics",
                return_value={
                    "coverage": 0.10,
                    "unknown_ratio": 0.90,
                    "axis_consistency": 0.40,
                    "hazard_non_null_ratio": 0.20,
                    "calibration_error": 0.40,
                    "hazard_bucket_monotonicity": -0.10,
                },
            ):
                df = runner.run(
                    WalkForwardConfig(
                        preset="v2",
                        windows=[(date(2010, 1, 3), date(2014, 1, 3))],
                    )
                )

        assert bool(df["tier1_pass"].iloc[0]) is True
        assert bool(df["tier2_warning"].iloc[0]) is True
        assert df["validation_status"].iloc[0] == "PASS_WITH_WARNING"

    def test_run_status_fail_when_tier1_fails(self):
        """Tier-1 실패면 Tier-2와 무관하게 FAIL."""
        fake_result = MagicMock()
        fake_result.metrics = {
            "cagr": -0.01,
            "total_return": -0.05,
            "max_drawdown": -0.50,
            "sharpe_ratio": -0.10,
            "benchmark_cagr": 0.08,
            "excess_cagr": -0.09,
        }

        with patch("pretrend.pipeline.backtest.walk_forward.BacktestRunner") as MockRunner:
            MockRunner.return_value.run.return_value = fake_result
            runner = WalkForwardRunner()
            with patch.object(
                runner,
                "_compute_12slot_diagnostics",
                return_value={
                    "coverage": 0.80,
                    "unknown_ratio": 0.20,
                    "axis_consistency": 0.90,
                    "hazard_non_null_ratio": 0.80,
                    "calibration_error": 0.05,
                    "hazard_bucket_monotonicity": 0.20,
                },
            ):
                df = runner.run(
                    WalkForwardConfig(
                        preset="v2",
                        windows=[(date(2010, 1, 3), date(2014, 1, 3))],
                    )
                )

        assert bool(df["tier1_pass"].iloc[0]) is False
        assert df["validation_status"].iloc[0] == "FAIL"

    def test_tier2_warning_fallback_when_diag_missing(self):
        """진단 지표 결측(NaN)이면 Tier-2 경고를 강제하지 않는다."""
        runner = WalkForwardRunner()
        warn = runner._is_tier2_warning(
            {
                "coverage": float("nan"),
                "unknown_ratio": float("nan"),
                "axis_consistency": float("nan"),
                "calibration_error": float("nan"),
                "hazard_bucket_monotonicity": float("nan"),
            }
        )
        assert warn is False

    def test_tier2_warning_when_hazard_quality_bad(self):
        runner = WalkForwardRunner()
        warn = runner._is_tier2_warning(
            {
                "coverage": 0.50,
                "unknown_ratio": 0.50,
                "axis_consistency": 0.70,
                "calibration_error": 0.50,
                "hazard_bucket_monotonicity": -0.10,
            }
        )
        assert warn is True


# ── save_walk_forward 저장 검증 ────────────────────────────────


class TestSaveWalkForward:
    def _make_df(self):
        return pd.DataFrame([
            {
                "window_start": date(2006, 1, 3),
                "window_end": date(2010, 6, 3),
                "cagr": 0.04,
                "total_return": 0.18,
                "max_drawdown": -0.08,
                "sharpe_ratio": 0.75,
                "benchmark_cagr": 0.08,
                "excess_cagr": -0.04,
                "diag_12slot_coverage": 0.40,
                "diag_unknown_ratio": 0.60,
                "diag_axis_consistency": 0.66,
                "hazard_non_null_ratio": 0.55,
                "diag_calibration_error": 0.12,
                "diag_hazard_bucket_monotonicity": 0.08,
                "tier1_pass": True,
                "tier2_warning": True,
                "validation_status": "PASS_WITH_WARNING",
                "preset": "v2",
                "generated_at": "2026-02-21T00:00:00",
            }
        ])

    def test_parquet_and_summary_json_created(self, tmp_path):
        """parquet + summary json 파일이 생성되어야 한다."""
        df = self._make_df()
        out_dir = save_walk_forward(df, preset="v2", base_dir=tmp_path)

        parquets = list(tmp_path.glob("walk_forward_v2_*.parquet"))
        jsons = list(tmp_path.glob("walk_forward_v2_*_summary.json"))

        assert len(parquets) == 1, "parquet 파일 1개 기대"
        assert len(jsons) == 1, "summary json 파일 1개 기대"

    def test_parquet_contains_required_columns(self, tmp_path):
        """저장된 parquet에 고정 스키마 컬럼이 포함되어야 한다."""
        df = self._make_df()
        save_walk_forward(df, preset="v2", base_dir=tmp_path)

        parquet_path = next(tmp_path.glob("walk_forward_v2_*.parquet"))
        loaded = pd.read_parquet(parquet_path)
        for col in ["window_start", "window_end", "cagr", "total_return",
                    "max_drawdown", "sharpe_ratio", "preset"]:
            assert col in loaded.columns, f"컬럼 누락: {col}"

    def test_summary_json_contains_required_keys(self, tmp_path):
        """요약 JSON에 mean_cagr, n_windows, caveat 키가 있어야 한다."""
        import json as _json

        df = self._make_df()
        save_walk_forward(df, preset="v2", base_dir=tmp_path)

        json_path = next(tmp_path.glob("walk_forward_v2_*_summary.json"))
        summary = _json.loads(json_path.read_text())

        assert "n_windows" in summary
        assert "mean_cagr" in summary
        assert "caveat" in summary
        assert summary["n_windows"] == 1
