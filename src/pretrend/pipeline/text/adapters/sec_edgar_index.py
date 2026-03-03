"""SEC EDGAR Full Index 백필 어댑터.

master.idx를 분기별로 내려받아 8-K 행만 추출한다.
filing_risk_burst는 8-K 일별 건수만 필요하므로, 공시 본문은 다운로드하지 않는다.
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, time as dt_time, timezone
from typing import Iterable, Iterator, List

import requests

from pretrend.pipeline.text.adapters.base import RawDoc, TextSourceAdapter, compute_payload_hash

logger = logging.getLogger(__name__)

_MASTER_INDEX_URL = "https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{quarter}/master.idx"


def _iter_quarters(start_dt: date, end_dt: date) -> List[tuple[int, int]]:
    quarters: List[tuple[int, int]] = []
    year = start_dt.year
    quarter = ((start_dt.month - 1) // 3) + 1
    end_key = (end_dt.year, ((end_dt.month - 1) // 3) + 1)
    while (year, quarter) <= end_key:
        quarters.append((year, quarter))
        quarter += 1
        if quarter > 4:
            quarter = 1
            year += 1
    return quarters


def _parse_master_idx(text: str) -> Iterator[dict]:
    seen_header = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if not seen_header:
            if line == "CIK|Company Name|Form Type|Date Filed|Filename":
                seen_header = True
            continue
        parts = line.split("|")
        if len(parts) != 5:
            continue
        cik, company_name, form_type, date_filed_str, filename = parts
        try:
            date_filed = date.fromisoformat(date_filed_str)
        except ValueError:
            continue
        yield {
            "cik": cik,
            "company_name": company_name,
            "form_type": form_type,
            "date_filed": date_filed,
            "filename": filename,
        }


def _download_index(url: str, user_agent: str, delay: float) -> str:
    resp = requests.get(url, headers={"User-Agent": user_agent}, timeout=60)
    try:
        resp.raise_for_status()
        return resp.content.decode("latin-1", errors="ignore")
    finally:
        time.sleep(delay)


class SECEdgarIndexAdapter(TextSourceAdapter):
    """EDGAR Full Index 기반 8-K 목록 수집 어댑터."""

    def __init__(self, user_agent: str, request_delay_sec: float = 0.11) -> None:
        self._user_agent = user_agent
        self._delay = request_delay_sec

    @property
    def source_name(self) -> str:
        return "sec_edgar"

    def fetch(self, start_dt: date, end_dt: date) -> Iterable[RawDoc]:
        for year, quarter in _iter_quarters(start_dt, end_dt):
            idx_url = _MASTER_INDEX_URL.format(year=year, quarter=quarter)
            text = _download_index(idx_url, user_agent=self._user_agent, delay=self._delay)
            for row in _parse_master_idx(text):
                if row["form_type"] != "8-K":
                    continue
                if not (start_dt <= row["date_filed"] <= end_dt):
                    continue
                filed_at = datetime.combine(row["date_filed"], dt_time.min, tzinfo=timezone.utc)
                body = (
                    f"[EDGAR index backfill] {row['company_name']} filed 8-K "
                    f"on {row['date_filed'].isoformat()}"
                )
                filename = row["filename"]
                yield RawDoc(
                    source=self.source_name,
                    source_doc_id=f"index:{filename}",
                    canonical_url=f"https://www.sec.gov/Archives/{filename}",
                    published_at=filed_at,
                    ingested_at=datetime.now(timezone.utc),
                    title=f"8-K: {row['company_name']}",
                    body=body,
                    lang="en",
                    raw_payload_hash=compute_payload_hash(filename),
                )
