"""Fed/FOMC 어댑터 — 연준 공식 RSS + HTML 본문 파싱.

- RSS: https://www.federalreserve.gov/feeds/press_all.xml (접근 확인됨)
- 수집: title, pubDate, link → HTML 본문 다운로드
- 필터: 성명서, 의사록, 연설문 (policy 키워드 기반)
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable, List, Optional
from xml.etree import ElementTree as ET

import requests

from pretrend.pipeline.text.adapters.base import (
    RawDoc,
    TextSourceAdapter,
    compute_payload_hash,
)

logger = logging.getLogger(__name__)

_FED_RSS_URL = "https://www.federalreserve.gov/feeds/press_all.xml"
_FED_BASE_URL = "https://www.federalreserve.gov"

# 정책 관련 문서 키워드 필터 (title/description 포함 여부 기준)
_POLICY_KEYWORDS = (
    "federal open market committee",
    "fomc",
    "monetary policy",
    "federal funds rate",
    "balance sheet",
    "interest rate",
    "inflation",
    "employment",
    "economic outlook",
    "statement",
    "minutes",
    "speech",
    "testimony",
    "press release",
    "beige book",
)


def _is_policy_relevant(title: str, description: str = "") -> bool:
    text = (title + " " + description).lower()
    return any(kw in text for kw in _POLICY_KEYWORDS)


def _extract_source_doc_id(url: str) -> str:
    """URL 경로 마지막 세그먼트를 source_doc_id로 사용.

    예: .../pressreleases/monetary20241218a.htm → monetary20241218a
    """
    path = url.rstrip("/").split("?")[0]  # 쿼리스트링 제거
    filename = path.split("/")[-1]
    return filename.rsplit(".", 1)[0] if "." in filename else filename


class FedFomcAdapter(TextSourceAdapter):
    """연준 공식 RSS + HTML 본문 파싱 어댑터."""

    def __init__(
        self,
        rss_url: str = _FED_RSS_URL,
        request_delay_sec: float = 0.5,
        filter_policy_only: bool = True,
    ) -> None:
        self._rss_url = rss_url
        self._delay = request_delay_sec
        self._filter_policy = filter_policy_only
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "pretrend-ai research bot macosc0625@gmail.com",
            "Accept": "application/xml,text/html;q=0.9,*/*;q=0.8",
        })

    @property
    def source_name(self) -> str:
        return "fed_fomc"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch(self, start_dt: date, end_dt: date) -> Iterable[RawDoc]:
        """지정 기간 내 Fed RSS 공시 수집 → RawDoc 반환."""
        items = self._fetch_rss_items(start_dt, end_dt)
        for item in items:
            doc = self._fetch_article(item)
            if doc is not None:
                yield doc

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get(self, url: str, accept: Optional[str] = None) -> Optional[requests.Response]:
        headers = {}
        if accept:
            headers["Accept"] = accept
        try:
            resp = self._session.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            logger.warning("GET %s failed: %s", url, exc)
            return None
        finally:
            time.sleep(self._delay)

    def _fetch_rss_items(self, start_dt: date, end_dt: date) -> List[dict]:
        """RSS 피드 파싱 → 기간 필터 + 정책 필터 적용."""
        resp = self._get(self._rss_url, accept="application/xml")
        if resp is None:
            return []

        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError as exc:
            logger.error("RSS XML parse error: %s", exc)
            return []

        items: List[dict] = []
        for elem in root.findall(".//item"):
            title_el = elem.find("title")
            link_el = elem.find("link")
            pub_date_el = elem.find("pubDate")
            desc_el = elem.find("description")

            if title_el is None or link_el is None or pub_date_el is None:
                continue

            title = (title_el.text or "").strip()
            link = (link_el.text or "").strip()
            pub_date_str = (pub_date_el.text or "").strip()
            description = (desc_el.text or "").strip() if desc_el is not None else ""

            # URL 정규화: 상대 경로 처리
            if link and not link.startswith("http"):
                link = _FED_BASE_URL + link

            # pubDate 파싱 (RFC 2822)
            try:
                pub_dt: datetime = parsedate_to_datetime(pub_date_str)
            except Exception:
                logger.debug("Failed to parse pubDate: %r", pub_date_str)
                continue

            pub_date = pub_dt.date()
            if not (start_dt <= pub_date <= end_dt):
                continue

            if self._filter_policy and not _is_policy_relevant(title, description):
                continue

            items.append({
                "title": title,
                "link": link,
                "published_at": pub_dt,
                "description": description,
            })

        logger.info(
            "Fed RSS: %d policy-relevant items in [%s, %s]",
            len(items), start_dt, end_dt,
        )
        return items

    def _fetch_article(self, item: dict) -> Optional[RawDoc]:
        """HTML 본문 다운로드 → RawDoc 반환."""
        url: str = item["link"]
        resp = self._get(url, accept="text/html")
        if resp is None:
            return None

        body = resp.text
        now_utc = datetime.now(timezone.utc)
        pub_dt: datetime = item["published_at"]
        if pub_dt.tzinfo is None:
            pub_dt = pub_dt.replace(tzinfo=timezone.utc)

        source_doc_id = _extract_source_doc_id(url)

        return RawDoc(
            source=self.source_name,
            source_doc_id=source_doc_id,
            canonical_url=url,
            published_at=pub_dt,
            ingested_at=now_utc,
            title=item["title"],
            body=body,
            lang="en",
            raw_payload_hash=compute_payload_hash(body),
        )
