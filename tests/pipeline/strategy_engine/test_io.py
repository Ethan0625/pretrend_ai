"""
Strategy Engine I/O 계약 테스트.

SOT: docs/strategy_engine_design.md §C, §E
"""
from __future__ import annotations

from errno import EXDEV
import uuid
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from pretrend.pipeline.strategy_engine.io import (
    load_gold_macro,
    load_gold_eod,
    write_snapshot_atomic,
)


@pytest.fixture
def tmp_data(tmp_path: Path):
    """테스트용 parquet 파일 생성."""
    # Gold Macro
    macro_dir = tmp_path / "gold" / "macro" / "macro_features" / "year=2024" / "month=06"
    macro_dir.mkdir(parents=True)
    df_macro = pd.DataFrame(
        {
            "indicator_id": ["CPI_US_ALL_ITEMS_SA", "US_UNEMPLOYMENT_RATE"],
            "trade_date": [date(2024, 6, 3), date(2024, 6, 3)],
            "selected_value": [310.0, 3.9],
        }
    )
    df_macro.to_parquet(macro_dir / "gold_macro_features_202406.parquet", index=False)

    # Gold EOD
    eod_dir = tmp_path / "gold" / "eod" / "eod_features" / "year=2024" / "month=06"
    eod_dir.mkdir(parents=True)
    df_eod = pd.DataFrame(
        {
            "symbol": ["SPY", "TLT"],
            "trade_date": [date(2024, 6, 3), date(2024, 6, 3)],
            "close": [530.0, 95.0],
        }
    )
    df_eod.to_parquet(eod_dir / "gold_eod_features_202406.parquet", index=False)

    return tmp_path


class TestLoadGoldMacro:
    def test_load_returns_dataframe(self, tmp_data):
        root = tmp_data / "gold" / "macro" / "macro_features"
        df = load_gold_macro(root)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2

    def test_empty_dir_returns_empty(self, tmp_path):
        root = tmp_path / "empty_dir"
        root.mkdir()
        df = load_gold_macro(root)
        assert df.empty

    def test_date_filter(self, tmp_data):
        root = tmp_data / "gold" / "macro" / "macro_features"
        df = load_gold_macro(root, start_date=date(2024, 6, 4))
        assert df.empty

    def test_trade_date_is_date_type(self, tmp_data):
        root = tmp_data / "gold" / "macro" / "macro_features"
        df = load_gold_macro(root)
        for val in df["trade_date"]:
            assert isinstance(val, date)


class TestLoadGoldEod:
    def test_load_returns_dataframe(self, tmp_data):
        root = tmp_data / "gold" / "eod" / "eod_features"
        df = load_gold_eod(root)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2

    def test_symbol_filter(self, tmp_data):
        root = tmp_data / "gold" / "eod" / "eod_features"
        df = load_gold_eod(root, symbols=["SPY"])
        assert len(df) == 1
        assert df.iloc[0]["symbol"] == "SPY"

    def test_empty_dir_returns_empty(self, tmp_path):
        root = tmp_path / "empty_dir"
        root.mkdir()
        df = load_gold_eod(root)
        assert df.empty


class TestWriteSnapshotAtomic:
    def test_write_and_read(self, tmp_path):
        df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
        run_id = uuid.uuid4().hex[:8]
        result_path = write_snapshot_atomic(
            df, tmp_path, "test_stage", date(2024, 6, 3), run_id
        )
        assert result_path.exists()
        loaded = pd.read_parquet(result_path)
        assert len(loaded) == 2

    def test_path_convention(self, tmp_path):
        df = pd.DataFrame({"x": [1]})
        run_id = "abc123"
        result_path = write_snapshot_atomic(
            df, tmp_path, "composer", date(2024, 6, 3), run_id
        )
        assert "decision_date=2024-06-03" in str(result_path)
        assert result_path.name == "composer_20240603.parquet"

    def test_idempotent_overwrite(self, tmp_path):
        df1 = pd.DataFrame({"v": [1]})
        df2 = pd.DataFrame({"v": [2]})
        run_id = "run1"
        write_snapshot_atomic(df1, tmp_path, "stage", date(2024, 1, 1), run_id)
        path = write_snapshot_atomic(df2, tmp_path, "stage", date(2024, 1, 1), "run2")
        loaded = pd.read_parquet(path)
        assert loaded.iloc[0]["v"] == 2

    def test_tmp_dir_cleaned_up(self, tmp_path):
        df = pd.DataFrame({"x": [1]})
        run_id = "cleanup_test"
        write_snapshot_atomic(df, tmp_path, "s", date(2024, 1, 1), run_id)
        tmp_dirs = list(tmp_path.rglob("_tmp_run=*"))
        assert len(tmp_dirs) == 0

    def test_cross_device_replace_fallback_move(self, tmp_path, monkeypatch):
        df = pd.DataFrame({"x": [1]})

        def _raise_exdev(self, target):
            raise OSError(EXDEV, "Invalid cross-device link")

        monkeypatch.setattr(Path, "replace", _raise_exdev)
        result_path = write_snapshot_atomic(
            df, tmp_path, "stage", date(2024, 1, 1), "exdev"
        )
        assert result_path.exists()
        loaded = pd.read_parquet(result_path)
        assert loaded.iloc[0]["x"] == 1

    def test_cross_device_fallback_overwrites_existing(self, tmp_path, monkeypatch):
        df1 = pd.DataFrame({"x": [1]})
        df2 = pd.DataFrame({"x": [2]})
        write_snapshot_atomic(df1, tmp_path, "stage", date(2024, 1, 2), "base")

        def _raise_exdev(self, target):
            raise OSError(EXDEV, "Invalid cross-device link")

        monkeypatch.setattr(Path, "replace", _raise_exdev)
        result_path = write_snapshot_atomic(
            df2, tmp_path, "stage", date(2024, 1, 2), "exdev2"
        )
        loaded = pd.read_parquet(result_path)
        assert loaded.iloc[0]["x"] == 2
