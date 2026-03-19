"""계약 회귀 테스트 — Bronze/Silver/Gold 필수 컬럼 존재 + 타입 일치."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pandas as pd
import pytest

from pretrend.pipeline.text.adapters.base import (
    RawDoc,
    TextSourceAdapter,
    compute_payload_hash,
    make_doc_id,
)
from pretrend.pipeline.text.bronze_ingest import (
    _BRONZE_COLUMNS,
    _docs_to_df,
    _write_partition,
    run_text_bronze_ingest,
)
from pretrend.pipeline.text.config import TextPipelineConfig
from pretrend.pipeline.text.gold_build import _GOLD_COLUMNS, run_text_gold_build
from pretrend.pipeline.text.silver_build import _SILVER_COLUMNS, run_text_silver_build


# ---------------------------------------------------------------------------
# Bronze 계약
# ---------------------------------------------------------------------------

def test_bronze_schema_columns():
    """_docs_to_df 출력에 Bronze 필수 컬럼이 모두 존재."""
    body = "Federal Reserve rate decision announcement."
    doc = RawDoc(
        source="fed_fomc",
        source_doc_id="monetary20260120a",
        canonical_url="https://federalreserve.gov/pressreleases/monetary20260120a.htm",
        published_at=datetime(2026, 1, 20, tzinfo=timezone.utc),
        ingested_at=datetime(2026, 1, 20, tzinfo=timezone.utc),
        title="FOMC Statement",
        body=body,
        lang="en",
        raw_payload_hash=compute_payload_hash(body),
    )
    df = _docs_to_df([doc])

    for col in _BRONZE_COLUMNS:
        assert col in df.columns, f"Bronze 필수 컬럼 누락: {col}"


def test_bronze_doc_id_is_deterministic():
    """동일 (source, source_doc_id) → 동일 doc_id."""
    body = "Some content"
    doc1 = RawDoc(
        source="fed_fomc", source_doc_id="abc123",
        canonical_url="https://example.com/abc123",
        published_at=datetime(2026, 1, 20, tzinfo=timezone.utc),
        ingested_at=datetime(2026, 1, 20, tzinfo=timezone.utc),
        title="Doc", body=body, lang="en",
        raw_payload_hash=compute_payload_hash(body),
    )
    doc2 = RawDoc(
        source="fed_fomc", source_doc_id="abc123",
        canonical_url="https://example.com/abc123",
        published_at=datetime(2026, 2, 1, tzinfo=timezone.utc),   # 날짜 달라도
        ingested_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
        title="Doc Updated", body="different body", lang="en",
        raw_payload_hash=compute_payload_hash("different body"),
    )
    assert make_doc_id(doc1["source"], doc1["source_doc_id"]) == \
           make_doc_id(doc2["source"], doc2["source_doc_id"]), \
           "동일 (source, source_doc_id) → doc_id 동일해야 함"


def test_bronze_written_parquet_schema(tmp_path):
    """Bronze parquet 파일에 필수 컬럼이 존재하고 dtypes가 유효."""
    body = "Test body content for contract testing."
    doc = RawDoc(
        source="fed_fomc", source_doc_id="test001",
        canonical_url="https://example.com/test001",
        published_at=datetime(2026, 2, 20, tzinfo=timezone.utc),
        ingested_at=datetime(2026, 2, 20, tzinfo=timezone.utc),
        title="Contract Test", body=body, lang="en",
        raw_payload_hash=compute_payload_hash(body),
    )
    df = _docs_to_df([doc])
    out = _write_partition(df, "fed_fomc", date(2026, 2, 20), tmp_path)

    read_df = pd.read_parquet(out)
    for col in _BRONZE_COLUMNS:
        assert col in read_df.columns, f"Bronze parquet 필수 컬럼 누락: {col}"

    # 타입 검사 (parquet은 StringDtype 또는 object 둘 다 허용)
    assert pd.api.types.is_string_dtype(read_df["doc_id"]), "doc_id는 string 타입"
    assert pd.api.types.is_string_dtype(read_df["source"])
    assert pd.api.types.is_string_dtype(read_df["lang"])


# ---------------------------------------------------------------------------
# Silver 계약
# ---------------------------------------------------------------------------

def _setup_bronze_for_silver(tmp_path):
    """Silver 테스트용 Bronze 데이터 준비."""
    bronze_root = tmp_path / "bronze" / "text"
    body = "<p>The Federal Reserve raised interest rates.</p>" * 10
    doc = RawDoc(
        source="fed_fomc", source_doc_id="monetary20260220a",
        canonical_url="https://federalreserve.gov/monetary20260220a.htm",
        published_at=datetime(2026, 2, 20, tzinfo=timezone.utc),
        ingested_at=datetime(2026, 2, 20, tzinfo=timezone.utc),
        title="FOMC Statement February 2026",
        body=body, lang="en",
        raw_payload_hash=compute_payload_hash(body),
    )
    df = _docs_to_df([doc])
    _write_partition(df, "fed_fomc", date(2026, 2, 20), bronze_root)
    return bronze_root


def test_silver_schema_columns(tmp_path):
    """Silver parquet에 필수 컬럼이 모두 존재."""
    bronze_root = _setup_bronze_for_silver(tmp_path)
    silver_root = tmp_path / "silver" / "text"

    cfg = TextPipelineConfig(
        data_root=tmp_path,
        bronze_root=bronze_root,
        silver_root=silver_root,
        gold_root=tmp_path / "gold" / "text",
    )
    run_text_silver_build(date(2026, 2, 20), date(2026, 2, 20), cfg=cfg)

    pq_files = list(silver_root.rglob("*.parquet"))
    assert pq_files, "Silver parquet 파일 존재"
    df = pd.concat([pd.read_parquet(p) for p in pq_files])

    for col in _SILVER_COLUMNS:
        assert col in df.columns, f"Silver 필수 컬럼 누락: {col}"

    # asset_scope 값 검증
    assert df["asset_scope"].isin(["macro", "theme", "ticker", "unknown"]).all()
    # enricher_version 존재
    assert (df["enricher_version"] == "v0").all()


# ---------------------------------------------------------------------------
# Gold 계약
# ---------------------------------------------------------------------------

def _setup_silver_for_gold(tmp_path):
    """Gold 테스트용 Silver 데이터 준비."""
    silver_root = tmp_path / "silver" / "text"
    partition_dir = silver_root / "text_enriched" / "event_date=2026-02-20"
    partition_dir.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame([{
        "doc_id": uuid.uuid4().hex,
        "source": "fed_fomc",
        "canonical_url": "https://federalreserve.gov/monetary20260220a.htm",
        "event_date": "2026-02-20",
        "title": "FOMC Statement",
        "clean_text": "The Federal Reserve will hike rates to tighten monetary policy." * 5,
        "asset_scope": "macro",
        "quality_flags": "ok",
        "lang": "en",
        "enricher_version": "v0",
        "published_at": pd.Timestamp("2026-02-20T00:00:00+00:00"),
    }])
    df.to_parquet(partition_dir / "silver_20260220.parquet", index=False)
    return silver_root


def test_gold_schema_columns(tmp_path):
    """Gold parquet에 필수 컬럼이 모두 존재."""
    silver_root = _setup_silver_for_gold(tmp_path)

    cfg = TextPipelineConfig(
        data_root=tmp_path,
        bronze_root=tmp_path / "bronze" / "text",
        silver_root=silver_root,
        gold_root=tmp_path / "gold" / "text",
    )
    run_text_gold_build(date(2026, 2, 20), date(2026, 2, 20), cfg=cfg)

    pq_files = list((tmp_path / "gold" / "text").rglob("*.parquet"))
    assert pq_files, "Gold parquet 파일 존재"
    df = pd.concat([pd.read_parquet(p) for p in pq_files])

    for col in _GOLD_COLUMNS:
        assert col in df.columns, f"Gold 필수 컬럼 누락: {col}"

    # feature_version 확인
    assert (df["feature_version"] == "v0").all()
    # staleness_days는 정수형 가능 값
    assert (df["staleness_days"] >= 0).all()


def test_gold_long_format(tmp_path):
    """Gold는 wide 아닌 long 포맷: (trade_date, feature_name) 조합으로 구성."""
    silver_root = _setup_silver_for_gold(tmp_path)

    cfg = TextPipelineConfig(
        data_root=tmp_path,
        bronze_root=tmp_path / "bronze" / "text",
        silver_root=silver_root,
        gold_root=tmp_path / "gold" / "text",
    )
    run_text_gold_build(date(2026, 2, 20), date(2026, 2, 20), cfg=cfg)

    gold_df = pd.concat([
        pd.read_parquet(p)
        for p in (tmp_path / "gold" / "text").rglob("*.parquet")
    ])

    # 하루에 3개 feature → 3 rows
    day_rows = gold_df[gold_df["trade_date"] == "2026-02-20"]
    assert len(day_rows) == 3, f"trade_date당 3 feature rows 기대, 실제: {len(day_rows)}"

    features = set(day_rows["feature_name"].tolist())
    assert features == {"macro_hawkish_score", "filing_risk_burst", "policy_uncertainty_idx"}


def test_text_source_adapter_abc():
    """TextSourceAdapter를 직접 인스턴스화하면 TypeError."""
    with pytest.raises(TypeError):
        TextSourceAdapter()  # type: ignore[abstract]
