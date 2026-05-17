from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from pretrend.ops.backfill_once import (
    BackfillSettings,
    _previous_weekday,
    run_backfill_once,
)


@dataclass
class _TaskResult:
    row_count: int


@dataclass
class _MacroResult:
    run_id: str = "macro_run"
    bronze_result: _TaskResult = field(default_factory=lambda: _TaskResult(10))
    silver_result: _TaskResult = field(default_factory=lambda: _TaskResult(8))
    gold_macro_result: _TaskResult = field(default_factory=lambda: _TaskResult(6))


@dataclass
class _EodResult:
    run_id: str = "eod_run"
    bronze_result: _TaskResult = field(default_factory=lambda: _TaskResult(20))
    silver_result: _TaskResult = field(default_factory=lambda: _TaskResult(18))
    gold_result: _TaskResult = field(default_factory=lambda: _TaskResult(16))


class _MacroRunner:
    def __init__(self, calls: list[tuple[str, Any]]) -> None:
        self.calls = calls

    def run(self, start_date: date, end_date: date) -> _MacroResult:
        self.calls.append(("macro", start_date, end_date))
        return _MacroResult()


class _EodRunner:
    def __init__(self, calls: list[tuple[str, Any]]) -> None:
        self.calls = calls

    def run(
        self,
        start_date: date,
        end_date: date,
        symbols: list[str] | None = None,
    ) -> _EodResult:
        self.calls.append(("eod", start_date, end_date, symbols))
        return _EodResult()


def _settings(marker_path: Path, *, force: bool = False) -> BackfillSettings:
    return BackfillSettings(
        enabled=True,
        force=force,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 5, 15),
        marker_path=marker_path,
        run_macro=True,
        run_eod=True,
        sync_postgres=True,
        symbols=["SPY", "XLK"],
    )


def test_previous_weekday_skips_weekend() -> None:
    assert _previous_weekday(date(2026, 5, 18)) == date(2026, 5, 15)
    assert _previous_weekday(date(2026, 5, 16)) == date(2026, 5, 15)


def test_run_backfill_once_runs_pipelines_syncs_and_writes_marker(tmp_path: Path) -> None:
    """OFS-002: marker가 없으면 Macro/EOD backfill과 Postgres sync를 먼저 수행한다."""
    calls: list[tuple[str, Any]] = []
    marker_path = tmp_path / "meta" / "bootstrap_backfill_once.json"

    result = run_backfill_once(
        _settings(marker_path),
        macro_runner_factory=lambda: _MacroRunner(calls),
        eod_runner_factory=lambda: _EodRunner(calls),
        sync_macro_func=lambda: {"table": "gold_macro_features", "rows_upserted": 6},
        sync_eod_func=lambda: {"table": "gold_eod_features", "rows_upserted": 16},
    )

    assert marker_path.exists()
    assert result["status"] == "completed"
    assert result["macro"]["gold_rows"] == 6
    assert result["eod"]["gold_rows"] == 16
    assert result["postgres_sync"]["macro"]["rows_upserted"] == 6
    assert calls == [
        ("macro", date(2026, 1, 1), date(2026, 5, 15)),
        ("eod", date(2026, 1, 1), date(2026, 5, 15), ["SPY", "XLK"]),
    ]


def test_run_backfill_once_skips_when_marker_exists(tmp_path: Path) -> None:
    """OFS-002: bootstrap marker가 있으면 반복 backfill을 실행하지 않는다."""
    marker_path = tmp_path / "bootstrap_backfill_once.json"
    marker_path.write_text("{}", encoding="utf-8")

    def fail_factory() -> Any:
        raise AssertionError("pipeline should not run when marker exists")

    result = run_backfill_once(
        _settings(marker_path),
        macro_runner_factory=fail_factory,
        eod_runner_factory=fail_factory,
    )

    assert result["status"] == "skipped_marker"


def test_run_backfill_once_rejects_inverted_date_range(tmp_path: Path) -> None:
    settings = BackfillSettings(
        enabled=True,
        force=False,
        start_date=date(2026, 5, 15),
        end_date=date(2026, 1, 1),
        marker_path=tmp_path / "marker.json",
        run_macro=True,
        run_eod=True,
        sync_postgres=True,
        symbols=None,
    )

    with pytest.raises(ValueError, match="PRETREND_BACKFILL_END_DATE"):
        run_backfill_once(settings)
