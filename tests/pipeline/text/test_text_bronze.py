"""Bronze 멱등성 테스트 — 동일 문서 재수집 시 중복 미발생."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Iterable, List

import pandas as pd
import pytest

from pretrend.pipeline.text.adapters.base import RawDoc, compute_payload_hash
from pretrend.pipeline.text.bronze_ingest import (
    _docs_to_df,
    _write_partition,
    run_text_bronze_ingest,
)
from pretrend.pipeline.text.config import TextPipelineConfig


def _make_doc(source: str, source_doc_id: str, body: str = "hello world") -> RawDoc:
    return RawDoc(
        source=source,
        source_doc_id=source_doc_id,
        canonical_url=f"https://example.com/{source_doc_id}",
        published_at=datetime(2026, 2, 20, tzinfo=timezone.utc),
        ingested_at=datetime(2026, 2, 20, tzinfo=timezone.utc),
        title=f"Doc {source_doc_id}",
        body=body,
        lang="en",
        raw_payload_hash=compute_payload_hash(body),
    )


# ---------------------------------------------------------------------------
# 1. 동일 문서 2회 제공 → _docs_to_df 내 중복 제거
# ---------------------------------------------------------------------------

def test_docs_to_df_deduplicates_same_doc():
    doc = _make_doc("fed_fomc", "monetary20260120a")
    df = _docs_to_df([doc, doc])  # 동일 문서 2회

    assert len(df) == 1, "동일 doc_id는 1건으로 줄어야 한다"
    assert "doc_id" in df.columns


def test_docs_to_df_different_docs_both_kept():
    doc1 = _make_doc("fed_fomc", "monetary20260120a")
    doc2 = _make_doc("fed_fomc", "monetary20260220a")
    df = _docs_to_df([doc1, doc2])

    assert len(df) == 2, "서로 다른 두 문서는 모두 유지"


# ---------------------------------------------------------------------------
# 2. 파티션 쓰기 후 재실행 → 파일 덮어쓰기, doc_id 중복 없음
# ---------------------------------------------------------------------------

def test_write_partition_idempotent(tmp_path):
    doc = _make_doc("fed_fomc", "monetary20260120a")
    df = _docs_to_df([doc])
    ingest_date = date(2026, 2, 20)

    # 1회 기록
    out1 = _write_partition(df, "fed_fomc", ingest_date, tmp_path)
    assert out1.exists()

    # 2회 기록 (동일 파티션 덮어쓰기)
    out2 = _write_partition(df, "fed_fomc", ingest_date, tmp_path)
    result = pd.read_parquet(out2)

    assert len(result) == 1, "덮어쓰기 후 중복 없어야 함"
    assert result["doc_id"].nunique() == 1


# ---------------------------------------------------------------------------
# 3. run_text_bronze_ingest — Mock 어댑터로 멱등성 확인
# ---------------------------------------------------------------------------

class _MockAdapter:
    """테스트용 어댑터: 고정 문서 반환."""
    source_name = "mock"

    def __init__(self, docs: List[RawDoc]):
        self._docs = docs

    def fetch(self, start_dt, end_dt) -> Iterable[RawDoc]:
        return iter(self._docs)


def test_run_bronze_ingest_no_duplicates(tmp_path, monkeypatch):
    """run_text_bronze_ingest: 동일 문서 2회 fetch → 1건 기록."""
    doc = _make_doc("sec_edgar", "320193::0001234567-26-000001")
    docs = [doc, doc]  # 의도적으로 동일 문서 2회

    # _build_adapter를 패치하여 Mock 어댑터 반환
    import pretrend.pipeline.text.bronze_ingest as mod
    monkeypatch.setattr(mod, "_build_adapter", lambda src, cfg: _MockAdapter(docs))

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
        ingest_date=date(2026, 2, 20),
    )

    assert len(results) == 1
    r = results[0]
    assert r.success
    assert r.docs_fetched == 2
    assert r.docs_written == 1  # 중복 1건 제거
    assert r.docs_skipped_duplicate == 1

    # 실제 파일 확인
    pq_files = list((tmp_path / "bronze" / "text").rglob("*.parquet"))
    assert len(pq_files) == 1
    df = pd.read_parquet(pq_files[0])
    assert df["doc_id"].nunique() == 1
