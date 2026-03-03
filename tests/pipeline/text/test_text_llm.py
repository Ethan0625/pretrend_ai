from __future__ import annotations

import json
import uuid
from datetime import date

import pandas as pd

from pretrend.pipeline.text.config import TextPipelineConfig
from pretrend.pipeline.text.gold_llm_build import (
    _filter_response,
    _parse_llm_response,
    _to_long_format,
    run_text_gold_llm_build,
)


def _write_silver(silver_root, event_date: str, df: pd.DataFrame) -> None:
    partition_dir = silver_root / "text_enriched" / f"event_date={event_date}"
    partition_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(partition_dir / f"silver_{event_date.replace('-', '')}.parquet", index=False)


def _make_silver_df(event_date: str, n: int = 1) -> pd.DataFrame:
    rows = []
    for i in range(n):
        rows.append(
            {
                "doc_id": uuid.uuid4().hex,
                "source": "fed_fomc",
                "canonical_url": f"https://example.com/doc{i}",
                "event_date": event_date,
                "title": "FOMC Statement",
                "clean_text": "The Federal Reserve signaled a possible rate hike." * 5,
                "asset_scope": "macro",
                "quality_flags": "ok",
                "lang": "en",
                "enricher_version": "v0",
                "published_at": pd.Timestamp(f"{event_date}T00:00:00+00:00"),
            }
        )
    return pd.DataFrame(rows)


def test_parse_llm_response_valid_json() -> None:
    parsed = _parse_llm_response('{"summary":"x","tone":"hawkish","topics":[],"tags":[],"confidence":0.8}')
    assert parsed is not None
    assert parsed["tone"] == "hawkish"


def test_parse_llm_response_invalid_json() -> None:
    assert _parse_llm_response("not valid json {{") is None


def test_filter_response_allowlist_and_invalid_tone() -> None:
    filtered = _filter_response(
        {
            "summary": "test",
            "tone": "aggressive",
            "topics": ["sp500", "not_allowed"],
            "tags": ["hike", "foobar"],
            "confidence": 0.8,
        }
    )
    assert filtered["tone"] == "neutral"
    assert filtered["topics"] == ["sp500"]
    assert filtered["tags"] == ["hike"]


def test_filter_response_confidence_clamps_to_default() -> None:
    filtered = _filter_response({"summary": "x", "tone": "hawkish", "confidence": 3.5})
    assert filtered["confidence"] == 0.5


def test_to_long_format_produces_4_rows() -> None:
    rows = _to_long_format(
        doc_id="doc1",
        trade_date="2026-02-20",
        filtered={
            "summary": "summary",
            "tone": "hawkish",
            "topics": ["sp500"],
            "tags": ["hike"],
            "confidence": 0.9,
        },
        model_id="llama3.1:latest",
        prompt_version="text_annotation_v1",
    )
    assert len(rows) == 4
    assert {r["feature_name"] for r in rows} == {"llm_tone", "llm_topics", "llm_tags", "llm_summary"}


def test_run_gold_llm_build_ollama_unavailable(tmp_path, monkeypatch) -> None:
    cfg = TextPipelineConfig(
        data_root=tmp_path,
        bronze_root=tmp_path / "bronze" / "text",
        silver_root=tmp_path / "silver" / "text",
        gold_root=tmp_path / "gold" / "text",
        gold_llm_root=tmp_path / "gold" / "text",
    )
    _write_silver(cfg.silver_root, "2026-02-20", _make_silver_df("2026-02-20", n=1))
    monkeypatch.setattr("pretrend.pipeline.text.gold_llm_build._check_ollama_available", lambda *_a, **_kw: False)

    result = run_text_gold_llm_build(date(2026, 2, 20), date(2026, 2, 20), cfg=cfg)

    assert result.success
    assert result.docs_processed == 0
    assert not list((cfg.gold_llm_root / "text_llm_features").rglob("*.parquet"))


def test_run_gold_llm_build_with_mock_ollama(tmp_path, monkeypatch) -> None:
    cfg = TextPipelineConfig(
        data_root=tmp_path,
        bronze_root=tmp_path / "bronze" / "text",
        silver_root=tmp_path / "silver" / "text",
        gold_root=tmp_path / "gold" / "text",
        gold_llm_root=tmp_path / "gold" / "text",
    )
    _write_silver(cfg.silver_root, "2026-02-20", _make_silver_df("2026-02-20", n=2))
    monkeypatch.setattr("pretrend.pipeline.text.gold_llm_build._check_ollama_available", lambda *_a, **_kw: True)
    monkeypatch.setattr(
        "pretrend.pipeline.text.gold_llm_build._ollama_chat",
        lambda *_a, **_kw: json.dumps(
            {
                "summary": "Fed is hawkish",
                "tone": "hawkish",
                "topics": ["sp500", "not_allowed"],
                "tags": ["hike", "not_allowed"],
                "confidence": 0.87,
            }
        ),
    )

    result = run_text_gold_llm_build(date(2026, 2, 20), date(2026, 2, 20), cfg=cfg)

    assert result.success
    assert result.docs_input == 2
    assert result.docs_processed == 2
    assert result.feature_rows == 8
    pq_files = list((cfg.gold_llm_root / "text_llm_features").rglob("*.parquet"))
    assert pq_files
    df = pd.concat([pd.read_parquet(p) for p in pq_files], ignore_index=True)
    assert set(df.columns) == {
        "trade_date",
        "doc_id",
        "feature_name",
        "feature_value",
        "feature_str",
        "confidence",
        "feature_version",
        "model_id",
        "prompt_version",
        "coverage_ratio",
        "staleness_days",
    }
    assert len(df) == 8
    assert (df["feature_version"] == "v1").all()
    assert (df["model_id"] == "llama3.1:latest").all()
