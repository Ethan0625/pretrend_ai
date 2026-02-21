"""Gold feature 집계 테스트 — macro_hawkish_score 부호/범위, coverage_ratio 검증."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
import pytest

from pretrend.pipeline.text.config import TextPipelineConfig
from pretrend.pipeline.text.gold_build import (
    _hawkish_ratio,
    _GOLD_COLUMNS,
    run_text_gold_build,
)


# ---------------------------------------------------------------------------
# hawkish_ratio 단위 테스트
# ---------------------------------------------------------------------------

def test_hawkish_ratio_pure_hawkish():
    text = "The Fed will hike rates and tighten monetary policy aggressively, hawkish stance."
    ratio = _hawkish_ratio(text)
    assert ratio > 0.0, "hawkish 키워드 포함 → ratio > 0"
    assert ratio <= 1.0


def test_hawkish_ratio_neutral_text():
    ratio = _hawkish_ratio("The economy is growing at a moderate pace.")
    assert ratio == 0.0


def test_hawkish_ratio_empty():
    assert _hawkish_ratio("") == 0.0


# ---------------------------------------------------------------------------
# Silver mock 데이터 생성 헬퍼
# ---------------------------------------------------------------------------

def _make_silver_df(
    event_date: str,
    source: str,
    clean_text: str,
    title: str = "Test doc",
    n: int = 1,
) -> pd.DataFrame:
    rows = []
    for i in range(n):
        rows.append({
            "doc_id": uuid.uuid4().hex,
            "source": source,
            "canonical_url": f"https://example.com/doc{i}",
            "event_date": event_date,
            "title": title,
            "clean_text": clean_text,
            "asset_scope": "macro" if source == "fed_fomc" else "ticker",
            "quality_flags": "ok",
            "lang": "en",
            "enricher_version": "v0",
            "published_at": pd.Timestamp(f"{event_date}T00:00:00+00:00"),
        })
    return pd.DataFrame(rows)


def _write_silver(silver_root, event_date: str, df: pd.DataFrame) -> None:
    partition_dir = silver_root / "text_enriched" / f"event_date={event_date}"
    partition_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(partition_dir / f"silver_{event_date.replace('-', '')}.parquet", index=False)


# ---------------------------------------------------------------------------
# macro_hawkish_score 검증
# ---------------------------------------------------------------------------

def test_gold_hawkish_score_positive_for_hawkish_docs(tmp_path):
    """hawkish 텍스트 Fed 문서 → macro_hawkish_score > 0."""
    silver_root = tmp_path / "silver" / "text"
    hawkish_text = "The Federal Reserve will hike rates and tighten its balance sheet." * 5

    df = _make_silver_df("2026-02-20", "fed_fomc", hawkish_text)
    _write_silver(silver_root, "2026-02-20", df)

    cfg = TextPipelineConfig(
        data_root=tmp_path,
        bronze_root=tmp_path / "bronze" / "text",
        silver_root=silver_root,
        gold_root=tmp_path / "gold" / "text",
    )
    result = run_text_gold_build(
        start_date=date(2026, 2, 20),
        end_date=date(2026, 2, 20),
        cfg=cfg,
    )

    assert result.success

    pq_files = list((tmp_path / "gold" / "text").rglob("*.parquet"))
    assert pq_files, "Gold 파일이 생성되어야 함"

    gold_df = pd.concat([pd.read_parquet(p) for p in pq_files])
    hawkish_rows = gold_df[gold_df["feature_name"] == "macro_hawkish_score"]
    assert len(hawkish_rows) == 1
    assert hawkish_rows["feature_value"].iloc[0] > 0.0, "hawkish 문서 → score > 0"
    assert hawkish_rows["coverage_ratio"].iloc[0] > 0.0


def test_gold_hawkish_score_zero_for_neutral_docs(tmp_path):
    """중립 텍스트 Fed 문서 → macro_hawkish_score == 0."""
    silver_root = tmp_path / "silver" / "text"
    neutral_text = "The Federal Reserve held rates steady amid balanced economic conditions." * 5

    df = _make_silver_df("2026-02-20", "fed_fomc", neutral_text)
    _write_silver(silver_root, "2026-02-20", df)

    cfg = TextPipelineConfig(
        data_root=tmp_path,
        bronze_root=tmp_path / "bronze" / "text",
        silver_root=silver_root,
        gold_root=tmp_path / "gold" / "text",
    )
    result = run_text_gold_build(
        start_date=date(2026, 2, 20),
        end_date=date(2026, 2, 20),
        cfg=cfg,
    )

    gold_df = pd.concat([pd.read_parquet(p) for p in (tmp_path / "gold" / "text").rglob("*.parquet")])
    hawkish_rows = gold_df[gold_df["feature_name"] == "macro_hawkish_score"]
    assert hawkish_rows["feature_value"].iloc[0] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Gold 스키마 및 feature 목록 검증
# ---------------------------------------------------------------------------

def test_gold_all_three_features_present(tmp_path):
    """Gold에 3개 feature가 모두 존재해야 함."""
    silver_root = tmp_path / "silver" / "text"
    df = _make_silver_df("2026-02-20", "fed_fomc", "The Fed will hike rates." * 5)
    _write_silver(silver_root, "2026-02-20", df)

    cfg = TextPipelineConfig(
        data_root=tmp_path,
        bronze_root=tmp_path / "bronze" / "text",
        silver_root=silver_root,
        gold_root=tmp_path / "gold" / "text",
    )
    run_text_gold_build(date(2026, 2, 20), date(2026, 2, 20), cfg=cfg)

    gold_df = pd.concat([
        pd.read_parquet(p) for p in (tmp_path / "gold" / "text").rglob("*.parquet")
    ])
    features = set(gold_df["feature_name"].unique())
    assert "macro_hawkish_score" in features
    assert "filing_risk_burst" in features
    assert "policy_uncertainty_idx" in features


def test_gold_coverage_ratio_range(tmp_path):
    """coverage_ratio는 [0.0, 1.0] 범위여야 함."""
    silver_root = tmp_path / "silver" / "text"
    df = _make_silver_df("2026-02-20", "fed_fomc", "inflation rate hike tighten" * 5)
    _write_silver(silver_root, "2026-02-20", df)

    cfg = TextPipelineConfig(
        data_root=tmp_path,
        bronze_root=tmp_path / "bronze" / "text",
        silver_root=silver_root,
        gold_root=tmp_path / "gold" / "text",
    )
    run_text_gold_build(date(2026, 2, 20), date(2026, 2, 20), cfg=cfg)

    gold_df = pd.concat([
        pd.read_parquet(p) for p in (tmp_path / "gold" / "text").rglob("*.parquet")
    ])
    assert (gold_df["coverage_ratio"] >= 0.0).all()
    assert (gold_df["coverage_ratio"] <= 1.0).all()
