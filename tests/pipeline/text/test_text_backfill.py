from __future__ import annotations

from datetime import date

import pandas as pd

from pretrend.pipeline.text.adapters.fed_fomc_archive import (
    FedFomcArchiveAdapter,
    _build_calendar_url,
    _parse_date_from_url,
)
from pretrend.pipeline.text.adapters.sec_edgar_index import (
    SECEdgarIndexAdapter,
    _iter_quarters,
    _parse_master_idx,
)
from pretrend.pipeline.text.backfill import run_text_backfill
from pretrend.pipeline.text.config import TextPipelineConfig


def test_iter_quarters_range():
    quarters = _iter_quarters(date(2006, 1, 1), date(2006, 12, 31))
    assert quarters == [(2006, 1), (2006, 2), (2006, 3), (2006, 4)]


def test_parse_master_idx_extracts_8k_rows():
    text = "\n".join(
        [
            "Description: Master Index of EDGAR Dissemination Feed",
            "CIK|Company Name|Form Type|Date Filed|Filename",
            "1000180|SANDISK CORP|8-K|2006-01-25|edgar/data/1000180/x.txt",
            "1000045|NICHOLAS FINANCIAL INC|10-Q|2006-02-13|edgar/data/1000045/y.txt",
        ]
    )
    rows = list(_parse_master_idx(text))
    assert len(rows) == 2
    assert rows[0]["form_type"] == "8-K"
    assert rows[0]["date_filed"] == date(2006, 1, 25)


def test_sec_index_adapter_yields_rawdoc_with_8k_title(monkeypatch):
    sample = "\n".join(
        [
            "CIK|Company Name|Form Type|Date Filed|Filename",
            "1000180|SANDISK CORP|8-K|2006-01-25|edgar/data/1000180/x.txt",
        ]
    )

    import pretrend.pipeline.text.adapters.sec_edgar_index as mod

    monkeypatch.setattr(mod, "_download_index", lambda url, user_agent, delay: sample)
    adapter = SECEdgarIndexAdapter(user_agent="UA", request_delay_sec=0.0)
    docs = list(adapter.fetch(date(2006, 1, 1), date(2006, 1, 31)))
    assert len(docs) == 1
    assert docs[0]["source"] == "sec_edgar"
    assert "8-K" in docs[0]["title"]
    assert docs[0]["source_doc_id"].startswith("index:")


def test_sec_index_source_doc_id_no_collision(monkeypatch):
    sample = "\n".join(
        [
            "CIK|Company Name|Form Type|Date Filed|Filename",
            "1000180|SANDISK CORP|8-K|2006-01-25|edgar/data/1000180/x.txt",
        ]
    )

    import pretrend.pipeline.text.adapters.sec_edgar_index as mod

    monkeypatch.setattr(mod, "_download_index", lambda url, user_agent, delay: sample)
    adapter = SECEdgarIndexAdapter(user_agent="UA", request_delay_sec=0.0)
    doc = list(adapter.fetch(date(2006, 1, 1), date(2006, 1, 31)))[0]
    assert doc["source_doc_id"] == "index:edgar/data/1000180/x.txt"


def test_fomc_archive_adapter_yields_rawdoc_with_body(monkeypatch):
    import pretrend.pipeline.text.adapters.fed_fomc_archive as mod

    monkeypatch.setattr(mod, "_extract_statement_links", lambda url, delay, user_agent: [
        "https://www.federalreserve.gov/newsevents/pressreleases/monetary20060131a.htm"
    ])
    monkeypatch.setattr(mod, "_download_html", lambda url, delay, user_agent: "<html>statement</html>")
    adapter = FedFomcArchiveAdapter(request_delay_sec=0.0, user_agent="UA")
    docs = list(adapter.fetch(date(2006, 1, 1), date(2006, 12, 31)))
    assert len(docs) == 1
    assert docs[0]["source"] == "fed_fomc"
    assert docs[0]["body"] == "<html>statement</html>"


def test_build_calendar_url_uses_historical_page_before_2015():
    assert _build_calendar_url(2006).endswith("fomchistorical2006.htm")
    assert _build_calendar_url(2020).endswith("fomchistorical2020.htm")
    assert _build_calendar_url(2021).endswith("fomccalendars.htm")


def test_backfill_checkpoint_skips_existing_partition(tmp_path, monkeypatch):
    cfg = TextPipelineConfig(
        data_root=tmp_path,
        bronze_root=tmp_path / "bronze" / "text",
        silver_root=tmp_path / "silver" / "text",
        gold_root=tmp_path / "gold" / "text",
    )
    partition = cfg.bronze_root / "sec_index" / "ingest_date=2006-12-31"
    partition.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"x": 1}]).to_parquet(partition / "bronze_sec_index_20061231.parquet")

    import pretrend.pipeline.text.backfill as mod

    calls = []
    monkeypatch.setattr(mod, "run_text_bronze_ingest", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(mod, "run_text_silver_build", lambda **kwargs: None)
    monkeypatch.setattr(mod, "run_text_gold_build", lambda **kwargs: None)

    run_text_backfill(
        sources=["sec_index"],
        start_dt=date(2006, 1, 1),
        end_dt=date(2006, 12, 31),
        chunk_years=1,
        cfg=cfg,
    )

    assert calls == []
