from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from pretrend.pipeline.sync.gold_postgres import (
    _file_in_scope,
    _filter_by_lower_bound,
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
