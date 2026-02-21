"""Fail-open 테스트 — 소스 어댑터 장애 시 파이프라인 완료 + 결측 플래그 확인."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Iterable

import numpy as np
import pandas as pd
import pytest

from pretrend.pipeline.text.adapters.base import RawDoc
from pretrend.pipeline.text.bronze_ingest import run_text_bronze_ingest
from pretrend.pipeline.text.config import TextPipelineConfig
from pretrend.pipeline.text.gold_build import run_text_gold_build
from pretrend.pipeline.text.silver_build import run_text_silver_build


# ---------------------------------------------------------------------------
# Mock 어댑터: 빈 응답 (장애 시뮬레이션)
# ---------------------------------------------------------------------------

class _EmptyAdapter:
    """아무것도 반환하지 않는 어댑터 (소스 무응답 시뮬레이션)."""
    source_name = "mock_empty"

    def fetch(self, start_dt, end_dt) -> Iterable[RawDoc]:
        return iter([])  # 빈 반환


class _RaisingAdapter:
    """fetch 시 예외 발생 어댑터 (소스 오류 시뮬레이션)."""
    source_name = "mock_error"

    def fetch(self, start_dt, end_dt) -> Iterable[RawDoc]:
        raise ConnectionError("Simulated connection error")


# ---------------------------------------------------------------------------
# Bronze: 빈 어댑터 → 0건 기록, 에러 없음
# ---------------------------------------------------------------------------

def test_bronze_empty_adapter_returns_success(tmp_path, monkeypatch):
    """빈 어댑터 → Bronze 결과는 success (0건 기록)."""
    import pretrend.pipeline.text.bronze_ingest as mod
    monkeypatch.setattr(mod, "_build_adapter", lambda src, cfg: _EmptyAdapter())

    cfg = TextPipelineConfig(
        data_root=tmp_path,
        bronze_root=tmp_path / "bronze" / "text",
        silver_root=tmp_path / "silver" / "text",
        gold_root=tmp_path / "gold" / "text",
    )
    results = run_text_bronze_ingest(
        sources=["sec"],
        start_date=date(2026, 2, 20),
        end_date=date(2026, 2, 20),
        cfg=cfg,
    )

    assert len(results) == 1
    r = results[0]
    assert r.success, "빈 어댑터는 에러가 아님"
    assert r.docs_fetched == 0
    assert r.docs_written == 0


def test_bronze_raising_adapter_records_error(tmp_path, monkeypatch):
    """예외 발생 어댑터 → Bronze 결과에 error 기록, 파이프라인은 계속."""
    import pretrend.pipeline.text.bronze_ingest as mod
    monkeypatch.setattr(mod, "_build_adapter", lambda src, cfg: _RaisingAdapter())

    cfg = TextPipelineConfig(
        data_root=tmp_path,
        bronze_root=tmp_path / "bronze" / "text",
        silver_root=tmp_path / "silver" / "text",
        gold_root=tmp_path / "gold" / "text",
    )
    results = run_text_bronze_ingest(
        sources=["sec"],
        start_date=date(2026, 2, 20),
        end_date=date(2026, 2, 20),
        cfg=cfg,
    )

    assert len(results) == 1
    r = results[0]
    assert not r.success
    assert r.error is not None  # 에러 메시지 기록됨


# ---------------------------------------------------------------------------
# Gold: Silver 데이터 없음 → coverage_ratio=0.0, NaN feature_value
# ---------------------------------------------------------------------------

def test_gold_failopen_no_silver_data(tmp_path):
    """Silver 데이터 없어도 Gold 생성 완료 + coverage_ratio=0.0."""
    cfg = TextPipelineConfig(
        data_root=tmp_path,
        bronze_root=tmp_path / "bronze" / "text",
        silver_root=tmp_path / "silver" / "text",
        gold_root=tmp_path / "gold" / "text",
    )
    result = run_text_gold_build(
        start_date=date(2026, 2, 20),
        end_date=date(2026, 2, 20),
        cfg=cfg,
    )

    assert result.success, "Silver 데이터 없어도 Gold 생성 완료"
    assert result.feature_rows > 0, "feature rows가 생성되어야 함"

    pq_files = list((tmp_path / "gold" / "text").rglob("*.parquet"))
    assert pq_files, "Gold 파일 존재"

    gold_df = pd.concat([pd.read_parquet(p) for p in pq_files])
    hawkish_rows = gold_df[gold_df["feature_name"] == "macro_hawkish_score"]
    assert not hawkish_rows.empty
    # 데이터 없음 → coverage_ratio=0.0, feature_value=NaN
    assert hawkish_rows["coverage_ratio"].iloc[0] == pytest.approx(0.0)
    assert np.isnan(hawkish_rows["feature_value"].iloc[0])


def test_silver_failopen_no_bronze_data(tmp_path):
    """Bronze 데이터 없어도 Silver 빌드가 성공."""
    cfg = TextPipelineConfig(
        data_root=tmp_path,
        bronze_root=tmp_path / "bronze" / "text",
        silver_root=tmp_path / "silver" / "text",
        gold_root=tmp_path / "gold" / "text",
    )
    result = run_text_silver_build(
        start_date=date(2026, 2, 20),
        end_date=date(2026, 2, 20),
        cfg=cfg,
    )

    assert result.success, "Bronze 없어도 Silver 빌드 성공"
    assert result.docs_input == 0
    assert result.docs_output == 0
