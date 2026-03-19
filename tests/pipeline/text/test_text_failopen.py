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
from pretrend.pipeline.text.gold_llm_build import run_text_gold_llm_build
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


class _OneDocAdapter:
    """1건 반환 어댑터 (정상 소스 시뮬레이션)."""

    def __init__(self, source_name: str = "mock_ok") -> None:
        self.source_name = source_name

    def fetch(self, start_dt, end_dt) -> Iterable[RawDoc]:
        return iter(
            [
                RawDoc(
                    source=self.source_name,
                    source_doc_id="doc-1",
                    canonical_url="https://example.com/doc-1",
                    published_at=datetime(2026, 2, 20, 1, 0, tzinfo=timezone.utc),
                    ingested_at=datetime(2026, 2, 20, 2, 0, tzinfo=timezone.utc),
                    title="sample",
                    body="sample body",
                    lang="en",
                    raw_payload_hash="hash-1",
                )
            ]
        )


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


def test_bronze_failopen_mixed_sources_continue(tmp_path, monkeypatch):
    """한 소스 실패 + 다른 소스 성공 시 전체 ingest는 계속되어야 한다."""
    import pretrend.pipeline.text.bronze_ingest as mod

    def _build(src, cfg):
        if src == "sec":
            return _RaisingAdapter()
        if src == "fed":
            return _OneDocAdapter(source_name="mock_ok")
        return _EmptyAdapter()

    monkeypatch.setattr(mod, "_build_adapter", _build)

    cfg = TextPipelineConfig(
        data_root=tmp_path,
        bronze_root=tmp_path / "bronze" / "text",
        silver_root=tmp_path / "silver" / "text",
        gold_root=tmp_path / "gold" / "text",
    )
    results = run_text_bronze_ingest(
        sources=["sec", "fed"],
        start_date=date(2026, 2, 20),
        end_date=date(2026, 2, 20),
        cfg=cfg,
    )

    assert len(results) == 2
    by_source = {r.source: r for r in results}
    assert by_source["sec"].success is False
    assert by_source["fed"].success is True
    assert by_source["fed"].docs_written == 1


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


def _write_silver_doc(tmp_path, event_date: str = "2026-02-20", n: int = 1) -> TextPipelineConfig:
    silver_root = tmp_path / "silver" / "text"
    partition_dir = silver_root / "text_enriched" / f"event_date={event_date}"
    partition_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for i in range(n):
        rows.append(
            {
                "doc_id": f"doc-{i}",
                "source": "fed_fomc",
                "canonical_url": f"https://example.com/doc-{i}",
                "event_date": event_date,
                "title": f"sample-{i}",
                "clean_text": "The Federal Reserve may hike rates." * 5,
                "asset_scope": "macro",
                "quality_flags": "ok",
                "lang": "en",
                "enricher_version": "v0",
                "published_at": pd.Timestamp(f"{event_date}T00:00:00+00:00"),
            }
        )
    pd.DataFrame(rows).to_parquet(partition_dir / f"silver_{event_date.replace('-', '')}.parquet", index=False)
    return TextPipelineConfig(
        data_root=tmp_path,
        bronze_root=tmp_path / "bronze" / "text",
        silver_root=silver_root,
        gold_root=tmp_path / "gold" / "text",
        gold_llm_root=tmp_path / "gold" / "text",
    )


def test_gold_llm_ollama_unavailable_does_not_block_pipeline(tmp_path, monkeypatch):
    cfg = _write_silver_doc(tmp_path)
    monkeypatch.setattr("pretrend.pipeline.text.gold_llm_build._check_ollama_available", lambda *_a, **_kw: False)

    llm_result = run_text_gold_llm_build(
        start_date=date(2026, 2, 20),
        end_date=date(2026, 2, 20),
        cfg=cfg,
    )
    assert llm_result.success
    assert llm_result.docs_processed == 0

    gold_result = run_text_gold_build(
        start_date=date(2026, 2, 20),
        end_date=date(2026, 2, 20),
        cfg=cfg,
    )
    assert gold_result.success
    assert list((cfg.gold_root / "text_daily_features").rglob("*.parquet"))


def test_gold_llm_partial_doc_failure_continues(tmp_path, monkeypatch):
    cfg = _write_silver_doc(tmp_path, n=3)
    monkeypatch.setattr("pretrend.pipeline.text.gold_llm_build._check_ollama_available", lambda *_a, **_kw: True)
    seen = {"count": 0}

    def _mock_chat(*_a, **_kw):
        seen["count"] += 1
        if seen["count"] == 2:
            raise TimeoutError("mock timeout")
        return '{"summary":"ok","tone":"hawkish","topics":["sp500"],"tags":["hike"],"confidence":0.7}'

    monkeypatch.setattr("pretrend.pipeline.text.gold_llm_build._ollama_chat", _mock_chat)

    result = run_text_gold_llm_build(
        start_date=date(2026, 2, 20),
        end_date=date(2026, 2, 20),
        cfg=cfg,
    )
    assert result.success
    assert result.docs_input == 3
    assert result.docs_processed == 2
    assert result.docs_skipped == 1
    assert result.coverage_ratio == pytest.approx(2 / 3)


def test_gold_llm_json_parse_failure_skips_doc(tmp_path, monkeypatch):
    cfg = _write_silver_doc(tmp_path, n=2)
    monkeypatch.setattr("pretrend.pipeline.text.gold_llm_build._check_ollama_available", lambda *_a, **_kw: True)
    seen = {"count": 0}

    def _mock_chat(*_a, **_kw):
        seen["count"] += 1
        if seen["count"] == 1:
            return "not valid json {{"
        return '{"summary":"ok","tone":"neutral","topics":[],"tags":[],"confidence":0.6}'

    monkeypatch.setattr("pretrend.pipeline.text.gold_llm_build._ollama_chat", _mock_chat)

    result = run_text_gold_llm_build(
        start_date=date(2026, 2, 20),
        end_date=date(2026, 2, 20),
        cfg=cfg,
    )
    assert result.success
    assert result.docs_processed == 1
    assert result.docs_skipped == 1


def test_gold_llm_no_parquet_when_ollama_down(tmp_path, monkeypatch):
    cfg = _write_silver_doc(tmp_path)
    monkeypatch.setattr("pretrend.pipeline.text.gold_llm_build._check_ollama_available", lambda *_a, **_kw: False)

    result = run_text_gold_llm_build(
        start_date=date(2026, 2, 20),
        end_date=date(2026, 2, 20),
        cfg=cfg,
    )

    assert result.success
    assert not list((cfg.gold_llm_root / "text_llm_features").rglob("*.parquet"))
