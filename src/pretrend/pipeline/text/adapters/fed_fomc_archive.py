"""Fed/FOMC historical archive 백필 어댑터."""
from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime, time as dt_time, timezone
from typing import Iterable, List
from urllib.parse import urljoin

import requests

from pretrend.pipeline.text.adapters.base import RawDoc, TextSourceAdapter, compute_payload_hash

logger = logging.getLogger(__name__)

_FED_BASE_URL = "https://www.federalreserve.gov"
_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
_DATE_RE = re.compile(r"(20\d{2})(\d{2})(\d{2})")


def _build_calendar_url(year: int) -> str:
    if year >= 2021:
        return "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
    return f"https://www.federalreserve.gov/monetarypolicy/fomchistorical{year}.htm"


def _extract_statement_links(url: str, delay: float, user_agent: str) -> List[str]:
    resp = requests.get(url, headers={"User-Agent": user_agent}, timeout=60)
    try:
        resp.raise_for_status()
        html = resp.text
    finally:
        time.sleep(delay)

    links: List[str] = []
    for href in _HREF_RE.findall(html):
        href_lower = href.lower()
        if "newsevents/pressreleases/monetary" not in href_lower and "newsevents/press/monetary" not in href_lower:
            continue
        if not href_lower.endswith((".htm", ".html")):
            continue
        links.append(urljoin(_FED_BASE_URL, href))
    return sorted(set(links))


def _parse_date_from_url(url: str) -> date:
    match = _DATE_RE.search(url)
    if match is None:
        raise ValueError(f"Could not parse date from URL: {url}")
    return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _download_html(url: str, delay: float, user_agent: str) -> str:
    resp = requests.get(url, headers={"User-Agent": user_agent}, timeout=60)
    try:
        resp.raise_for_status()
        return resp.text
    finally:
        time.sleep(delay)


class FedFomcArchiveAdapter(TextSourceAdapter):
    """Fed historical calendar/statement archive 어댑터."""

    def __init__(
        self,
        request_delay_sec: float = 0.5,
        user_agent: str = "pretrend-ai research bot macosc0625@gmail.com",
    ) -> None:
        self._delay = request_delay_sec
        self._user_agent = user_agent

    @property
    def source_name(self) -> str:
        return "fed_fomc"

    def fetch(self, start_dt: date, end_dt: date) -> Iterable[RawDoc]:
        seen_links = set()
        for year in range(start_dt.year, end_dt.year + 1):
            cal_url = _build_calendar_url(year)
            for link in _extract_statement_links(cal_url, self._delay, self._user_agent):
                if link in seen_links:
                    continue
                seen_links.add(link)
                try:
                    pub_date = _parse_date_from_url(link)
                except ValueError:
                    logger.debug("Skipping FOMC link with no parsable date: %s", link)
                    continue
                if not (start_dt <= pub_date <= end_dt):
                    continue
                body = _download_html(link, self._delay, self._user_agent)
                yield RawDoc(
                    source=self.source_name,
                    source_doc_id=f"archive:{link}",
                    canonical_url=link,
                    published_at=datetime.combine(pub_date, dt_time.min, tzinfo=timezone.utc),
                    ingested_at=datetime.now(timezone.utc),
                    title=f"FOMC Statement {pub_date.isoformat()}",
                    body=body,
                    lang="en",
                    raw_payload_hash=compute_payload_hash(body),
                )
