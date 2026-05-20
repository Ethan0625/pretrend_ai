from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from pretrend.pipeline.sync.gold_postgres import (
    _file_in_scope,
    _filter_by_lower_bound,
    _load_eod_parquet,
    _load_macro_parquet,
    _sync_lower_bound,
)


def test_sync_lower_bound_defaults_to_watermark_lookback(monkeypatch: pytest.MonkeyPatch) -> None:
    """OFS-001: 일반 증분 sync는 watermark lookback 범위만 다시 읽는다."""
    monkeypatch.delenv("PRETREND_GOLD_SYNC_FULL", raising=False)
    monkeypatch.delenv("PRETREND_GOLD_SYNC_START_DATE", raising=False)

    assert _sync_lower_bound(date(2024, 6, 11), 35) == date(2024, 5, 7)


def test_sync_lower_bound_can_force_historical_start(monkeypatch: pytest.MonkeyPatch) -> None:
    """OFS-001: historical backfill은 최신 watermark보다 과거 구간도 sync해야 한다."""
    monkeypatch.delenv("PRETREND_GOLD_SYNC_FULL", raising=False)
    monkeypatch.setenv("PRETREND_GOLD_SYNC_START_DATE", "2003-01-01")

    assert _sync_lower_bound(date(2024, 6, 11), 0) == date(2002, 12, 31)


def test_sync_lower_bound_full_resync(monkeypatch: pytest.MonkeyPatch) -> None:
    """OFS-001: full resync는 watermark lower bound를 비활성화한다."""
    monkeypatch.setenv("PRETREND_GOLD_SYNC_FULL", "1")
    monkeypatch.setenv("PRETREND_GOLD_SYNC_START_DATE", "2003-01-01")

    assert _sync_lower_bound(date(2024, 6, 11), 0) is None


def test_ofs_001_default_incremental_scope_excludes_historical_prepend(
    tmp_path: Path,
) -> None:
    """OFS-001: 일반 증분 sync는 오래된 prepend 파티션을 읽지 않는다."""
    root = tmp_path / "gold" / "macro" / "macro_features"
    old_file = root / "year=2003" / "month=01" / "gold_macro_features_200301.parquet"
    new_file = root / "year=2024" / "month=06" / "gold_macro_features_202406.parquet"

    assert _file_in_scope(old_file, lower_bound=date(2024, 6, 1)) is False
    assert _file_in_scope(new_file, lower_bound=date(2024, 6, 1)) is True

    df = pd.DataFrame(
        [
            {"trade_date": date(2003, 1, 31)},
            {"trade_date": date(2024, 6, 11)},
        ]
    )
    filtered = _filter_by_lower_bound(df, lower_bound=date(2024, 6, 1))
    assert filtered["trade_date"].tolist() == [date(2024, 6, 11)]


def test_ofs_001_historical_start_scope_includes_prepended_partition(
    tmp_path: Path,
) -> None:
    """OFS-001: historical start가 있으면 과거 prepend 파티션을 sync 입력에 포함한다."""
    root = tmp_path / "gold" / "macro" / "macro_features"
    old_file = root / "year=2003" / "month=01" / "gold_macro_features_200301.parquet"
    new_file = root / "year=2024" / "month=06" / "gold_macro_features_202406.parquet"

    assert _file_in_scope(old_file, lower_bound=date(2002, 12, 31)) is True
    assert _file_in_scope(new_file, lower_bound=date(2002, 12, 31)) is True

    df = pd.DataFrame(
        [
            {"trade_date": date(2003, 1, 31)},
            {"trade_date": date(2024, 6, 11)},
        ]
    )
    filtered = _filter_by_lower_bound(df, lower_bound=date(2002, 12, 31))

    assert filtered["trade_date"].tolist() == [
        date(2003, 1, 31),
        date(2024, 6, 11),
    ]


def test_ofs_001_macro_sync_loader_does_not_read_excluded_partitions(
    tmp_path: Path,
) -> None:
    """OFS-001: sync loader must prune files before parquet reads."""
    root = tmp_path / "gold" / "macro" / "macro_features"
    current_dir = root / "year=2024" / "month=06"
    current_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "indicator_id": "CPI_US_ALL_ITEMS_SA",
                "trade_date": date(2024, 6, 11),
                "selected_value": 305.0,
            }
        ]
    ).to_parquet(
        current_dir / "gold_macro_features_202406.parquet",
        index=False,
    )

    old_dir = root / "year=2003" / "month=01"
    old_dir.mkdir(parents=True, exist_ok=True)
    (old_dir / "gold_macro_features_200301.parquet").write_text(
        "not a parquet file",
        encoding="utf-8",
    )

    loaded = _load_macro_parquet(root, lower_bound=date(2024, 6, 1))

    assert len(loaded) == 1
    assert loaded.iloc[0]["trade_date"] == date(2024, 6, 11)


def test_ofs_001_eod_sync_loader_does_not_read_excluded_partitions(
    tmp_path: Path,
) -> None:
    """OFS-001: symbol-partitioned sync loader must prune before parquet reads."""
    root = tmp_path / "gold" / "eod" / "eod_features"
    current_dir = root / "symbol=SPY" / "year=2024" / "month=06"
    current_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "symbol": "SPY",
                "trade_date": date(2024, 6, 11),
                "close": 100.0,
            }
        ]
    ).to_parquet(
        current_dir / "gold_eod_features_202406.parquet",
        index=False,
    )

    old_dir = root / "symbol=SPY" / "year=2003" / "month=01"
    old_dir.mkdir(parents=True, exist_ok=True)
    (old_dir / "gold_eod_features_200301.parquet").write_text(
        "not a parquet file",
        encoding="utf-8",
    )

    loaded = _load_eod_parquet(root, lower_bound=date(2024, 6, 1))

    assert len(loaded) == 1
    assert loaded.iloc[0]["trade_date"] == date(2024, 6, 11)
