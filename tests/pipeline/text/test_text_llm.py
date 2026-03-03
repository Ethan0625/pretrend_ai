from __future__ import annotations

import json
import uuid
from datetime import date

import pandas as pd

from pretrend.pipeline.text.config import TextPipelineConfig
from pretrend.pipeline.text.gold_llm_build import (
    TAG_TAXONOMY,
    TOPIC_TAXONOMY,
    _TAG_ALLOWLIST,
    _TAG_TO_CATEGORY,
    _TOPIC_ALLOWLIST,
    _TOPIC_TO_CATEGORY,
    _filter_response,
    _parse_llm_response,
    _prepare_text_for_llm,
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


def test_prepare_text_for_llm_skips_boilerplate() -> None:
    """콘텐츠 마커 앞의 보일러플레이트를 건너뛴다."""
    boilerplate = "Navigation menu items and CSS styles " * 200  # ~7,400 chars
    content = "The Committee decided to raise the target range for the federal funds rate."
    text = boilerplate + content
    result = _prepare_text_for_llm(text, max_chars=4096)
    assert "The Committee" in result
    assert len(result) <= 4096


def test_prepare_text_for_llm_no_marker() -> None:
    """마커가 없으면 원문 그대로 사용."""
    text = "Some random financial text without any FOMC markers." * 10
    result = _prepare_text_for_llm(text, max_chars=4096)
    assert result.startswith("Some random")


def test_prepare_text_for_llm_marker_near_start() -> None:
    """마커가 200자 이내이면 건너뛰지 않는다."""
    text = "Short intro. The Committee decided to hold rates."
    result = _prepare_text_for_llm(text, max_chars=4096)
    assert result.startswith("Short intro")


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
    assert filtered["topics"] == [{"category": "index", "item": "sp500"}]
    assert filtered["tags"] == [{"category": "policy_action", "item": "hike"}]


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
            "topics": [{"category": "index", "item": "sp500"}],
            "tags": [{"category": "policy_action", "item": "hike"}],
            "confidence": 0.9,
        },
        model_id="llama3.1:latest",
        prompt_version="text_annotation_v2",
    )
    assert len(rows) == 4
    assert {r["feature_name"] for r in rows} == {"llm_tone", "llm_topics", "llm_tags", "llm_summary"}


def test_filter_response_topics_with_category() -> None:
    filtered = _filter_response(
        {
            "summary": "test",
            "tone": "hawkish",
            "topics": ["sp500", "inflation"],
            "tags": ["hike"],
            "confidence": 0.8,
        }
    )
    assert filtered["topics"] == [
        {"category": "index", "item": "sp500"},
        {"category": "macro", "item": "inflation"},
    ]
    assert filtered["tags"] == [{"category": "policy_action", "item": "hike"}]


def test_filter_response_invalid_topic_filtered() -> None:
    filtered = _filter_response(
        {
            "summary": "test",
            "tone": "neutral",
            "topics": ["Federal Reserve", "sp500"],
            "tags": [],
            "confidence": 0.5,
        }
    )
    assert filtered["topics"] == [{"category": "index", "item": "sp500"}]


def test_taxonomy_consistency() -> None:
    for category, items in TOPIC_TAXONOMY.items():
        for item in items:
            assert item in _TOPIC_ALLOWLIST
            assert _TOPIC_TO_CATEGORY[item] == category

    for category, items in TAG_TAXONOMY.items():
        for item in items:
            assert item in _TAG_ALLOWLIST
            assert _TAG_TO_CATEGORY[item] == category


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


def test_source_filter(tmp_path, monkeypatch) -> None:
    """source_filter를 지정하면 해당 소스의 문서만 처리된다."""
    cfg = TextPipelineConfig(
        data_root=tmp_path,
        bronze_root=tmp_path / "bronze" / "text",
        silver_root=tmp_path / "silver" / "text",
        gold_root=tmp_path / "gold" / "text",
        gold_llm_root=tmp_path / "gold" / "text",
    )
    fomc_df = _make_silver_df("2026-02-20", n=2)
    sec_df = fomc_df.copy()
    sec_df["source"] = "sec_edgar"
    sec_df["doc_id"] = [uuid.uuid4().hex for _ in range(len(sec_df))]
    combined = pd.concat([fomc_df, sec_df], ignore_index=True)
    _write_silver(cfg.silver_root, "2026-02-20", combined)

    monkeypatch.setattr("pretrend.pipeline.text.gold_llm_build._check_ollama_available", lambda *_a, **_kw: True)
    monkeypatch.setattr(
        "pretrend.pipeline.text.gold_llm_build._ollama_chat",
        lambda *_a, **_kw: json.dumps(
            {"summary": "test", "tone": "neutral", "topics": [], "tags": [], "confidence": 0.5}
        ),
    )

    result = run_text_gold_llm_build(
        date(2026, 2, 20), date(2026, 2, 20), cfg=cfg, source_filter="fed_fomc",
    )
    assert result.docs_input == 2  # fomc only, not 4


def test_max_workers_parallel(tmp_path, monkeypatch) -> None:
    """max_workers>1 병렬 처리도 동일한 결과를 생성한다."""
    cfg = TextPipelineConfig(
        data_root=tmp_path,
        bronze_root=tmp_path / "bronze" / "text",
        silver_root=tmp_path / "silver" / "text",
        gold_root=tmp_path / "gold" / "text",
        gold_llm_root=tmp_path / "gold" / "text",
    )
    _write_silver(cfg.silver_root, "2026-02-20", _make_silver_df("2026-02-20", n=4))
    monkeypatch.setattr("pretrend.pipeline.text.gold_llm_build._check_ollama_available", lambda *_a, **_kw: True)
    monkeypatch.setattr(
        "pretrend.pipeline.text.gold_llm_build._ollama_chat",
        lambda *_a, **_kw: json.dumps(
            {"summary": "hawkish Fed", "tone": "hawkish", "topics": ["fed_policy"], "tags": ["hike"], "confidence": 0.9}
        ),
    )

    result = run_text_gold_llm_build(
        date(2026, 2, 20), date(2026, 2, 20), cfg=cfg, max_workers=2,
    )
    assert result.success
    assert result.docs_input == 4
    assert result.docs_processed == 4
    assert result.feature_rows == 16
