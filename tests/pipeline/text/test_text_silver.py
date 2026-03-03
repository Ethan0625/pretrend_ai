"""Silver dedup 테스트 — 동일 doc_id 중복 제거 + clean_text 생성 확인."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd
import pytest

from pretrend.pipeline.text.adapters.base import compute_payload_hash, make_doc_id
from pretrend.pipeline.text.bronze_ingest import _BRONZE_COLUMNS, _docs_to_df, _write_partition
from pretrend.pipeline.text.silver_build import (
    _strip_html,
    _detect_asset_scope,
    _compute_quality_flags,
    run_text_silver_build,
)
from pretrend.pipeline.text.config import TextPipelineConfig
from pretrend.pipeline.text.adapters.base import RawDoc


# ---------------------------------------------------------------------------
# HTML 정제
# ---------------------------------------------------------------------------

def test_strip_html_removes_tags():
    html = "<p>Hello <b>world</b>!</p>"
    result = _strip_html(html)
    assert "<" not in result
    assert "Hello" in result
    assert "world" in result


def test_strip_html_collapses_whitespace():
    html = "<p>  Multiple   spaces  </p>"
    result = _strip_html(html)
    assert "  " not in result  # 연속 공백 없음


# ---------------------------------------------------------------------------
# asset_scope 감지
# ---------------------------------------------------------------------------

def test_asset_scope_fed_fomc_is_macro():
    scope = _detect_asset_scope("fed_fomc", "FOMC Statement", "interest rate decision")
    assert scope == "macro"


def test_asset_scope_sec_edgar_is_ticker():
    scope = _detect_asset_scope("sec_edgar", "AAPL 8-K 2026-02-20", "quarterly earnings")
    assert scope == "ticker"


# ---------------------------------------------------------------------------
# quality_flags
# ---------------------------------------------------------------------------

def test_quality_flags_ok_for_normal_doc():
    flags = _compute_quality_flags("This is a normal document body. " * 5, "en", "plain text")
    assert flags == "ok"


def test_quality_flags_body_too_short():
    flags = _compute_quality_flags("Short", "en", "Short")
    assert "body_too_short" in flags


def test_quality_flags_has_html_markup():
    body = "<html><body>content</body></html>"
    flags = _compute_quality_flags("<html>content</html>" * 20, "en", body)
    assert "has_html_markup" in flags


def test_quality_flags_html_body_stripped_clean():
    flags = _compute_quality_flags(
        "The Federal Reserve raised rates by 25bp. " * 4,
        "en",
        "<html><body>The Federal Reserve raised rates by 25bp.</body></html>",
    )
    assert flags == "ok"


# ---------------------------------------------------------------------------
# run_text_silver_build — 크로스 파티션 dedup
# ---------------------------------------------------------------------------

def _write_bronze_doc(
    bronze_root, source, source_doc_id, ingest_date_str, body="Some text content here."
):
    """테스트용 Bronze parquet 생성."""
    doc = RawDoc(
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
    df = _docs_to_df([doc])
    ingest_date = date.fromisoformat(ingest_date_str)
    _write_partition(df, source, ingest_date, bronze_root)
    return df


def test_silver_dedup_same_doc_two_bronze_partitions(tmp_path):
    """동일 doc_id가 서로 다른 ingest_date 파티션에 존재 → Silver 1건으로 병합."""
    bronze_root = tmp_path / "bronze" / "text"
    silver_root = tmp_path / "silver" / "text"

    # 같은 문서를 2개의 다른 ingest_date 파티션에 저장 (예: 재수집 시나리오)
    _write_bronze_doc(bronze_root, "fed_fomc", "monetary20260120a", "2026-02-19")
    _write_bronze_doc(bronze_root, "fed_fomc", "monetary20260120a", "2026-02-20")

    cfg = TextPipelineConfig(
        data_root=tmp_path,
        bronze_root=bronze_root,
        silver_root=silver_root,
        gold_root=tmp_path / "gold" / "text",
    )
    result = run_text_silver_build(
        start_date=date(2026, 2, 19),
        end_date=date(2026, 2, 20),
        cfg=cfg,
    )

    assert result.success
    assert result.docs_deduped == 1, "동일 doc_id 크로스 파티션 dedup 1건"

    # Silver 파일 확인
    pq_files = list(silver_root.rglob("*.parquet"))
    assert len(pq_files) >= 1
    dfs = pd.concat([pd.read_parquet(p) for p in pq_files], ignore_index=True)
    assert dfs["doc_id"].nunique() == 1, "Silver에는 동일 문서 1건만 있어야 함"


def test_silver_clean_text_populated(tmp_path):
    """Silver에 clean_text가 채워지는지 확인."""
    bronze_root = tmp_path / "bronze" / "text"
    silver_root = tmp_path / "silver" / "text"

    _write_bronze_doc(
        bronze_root, "fed_fomc", "monetary20260120b", "2026-02-20",
        body="<p>The Federal Reserve <b>raised rates</b> by 25bp.</p>" * 10,
    )

    cfg = TextPipelineConfig(
        data_root=tmp_path,
        bronze_root=bronze_root,
        silver_root=silver_root,
        gold_root=tmp_path / "gold" / "text",
    )
    result = run_text_silver_build(
        start_date=date(2026, 2, 20),
        end_date=date(2026, 2, 20),
        cfg=cfg,
    )

    assert result.success
    pq_files = list(silver_root.rglob("*.parquet"))
    df = pd.concat([pd.read_parquet(p) for p in pq_files])

    assert "clean_text" in df.columns
    assert df["clean_text"].iloc[0] != "", "clean_text는 비어있지 않아야 함"
    assert "<" not in df["clean_text"].iloc[0], "HTML 태그가 제거되어야 함"
