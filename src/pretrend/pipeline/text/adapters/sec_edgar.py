"""SEC EDGAR 어댑터 — data.sec.gov REST API 기반.

수집 절차:
1. ticker → CIK 매핑: company_tickers.json (1회 조회 + 캐시)
2. submissions API: data.sec.gov/submissions/CIK{:010d}.json → 8-K/10-Q/10-K 필터
3. 원문 다운로드: accessionNumber 기반 EDGAR Archives HTML/TXT
4. 제약: 10 req/sec 상한 (0.11s delay), User-Agent 헤더 필수
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import requests

from pretrend.pipeline.text.adapters.base import (
    RawDoc,
    TextSourceAdapter,
    compute_payload_hash,
)

logger = logging.getLogger(__name__)

_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
_ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/{primary_doc}"

FORM_TYPES = frozenset({"8-K", "10-Q", "10-K"})

# Observability SOT ETF 주요 구성종목 seed list (~100 대형주)
# XLK, XLV, XLF, XLE, XLI, XLU, XLB, XLY, XLP, XLC 섹터별 편입 대형주
TEXT_SEC_SEED_TICKERS: List[str] = [
    # XLK — Technology
    "AAPL", "MSFT", "NVDA", "AVGO", "CRM", "ORCL", "AMD", "ACN", "CSCO", "IBM",
    "INTU", "ADBE", "TXN", "QCOM", "NOW", "AMAT", "ADI", "PANW", "KLAC",
    # XLV — Healthcare
    "LLY", "UNH", "JNJ", "ABBV", "MRK", "TMO", "ABT", "ISRG", "DHR", "BMY",
    "AMGN", "MDT", "PFE", "ELV", "CI", "SYK", "BSX", "REGN", "VRTX", "ZTS",
    # XLF — Financials
    "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "BLK", "SPGI", "AXP",
    "C", "CB", "PGR", "MET", "AIG", "ICE", "COF",
    # XLE — Energy
    "XOM", "CVX", "EOG", "SLB", "MPC", "COP", "PSX", "VLO", "OXY", "HES",
    "DVN", "BKR", "KMI", "WMB", "HAL",
    # XLI — Industrials
    "GE", "RTX", "HON", "UNP", "CAT", "DE", "LMT", "UPS", "ETN", "EMR",
    "NSC", "ITW", "PH", "GD", "MMM", "FDX", "BA",
    # XLU — Utilities
    "NEE", "SO", "DUK", "AEP", "SRE", "D", "EXC", "XEL", "WEC",
    # XLB — Materials
    "LIN", "APD", "NEM", "SHW", "FCX", "ECL", "DD", "PPG",
    # XLY — Consumer Discretionary
    "AMZN", "TSLA", "HD", "MCD", "LOW", "NKE", "SBUX", "TJX", "BKNG", "CMG",
    # XLP — Consumer Staples
    "PG", "KO", "PEP", "WMT", "COST", "PM", "MO", "CL",
    # XLC — Communication Services
    "META", "GOOGL", "NFLX", "T", "VZ", "TMUS", "DIS", "CMCSA",
]


class SECEdgarAdapter(TextSourceAdapter):
    """SEC EDGAR data.sec.gov REST API 기반 어댑터."""

    def __init__(
        self,
        seed_tickers: Optional[List[str]] = None,
        user_agent: str = "pretrend-ai macosc0625@gmail.com",
        cik_cache_path: Optional[Path] = None,
        request_delay_sec: float = 0.11,
    ) -> None:
        self._seed_tickers = [t.upper() for t in (seed_tickers or TEXT_SEC_SEED_TICKERS)]
        self._user_agent = user_agent
        self._cik_cache_path = cik_cache_path
        self._delay = request_delay_sec
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": self._user_agent,
        })
        self._ticker_to_cik: Optional[Dict[str, int]] = None

    @property
    def source_name(self) -> str:
        return "sec_edgar"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch(self, start_dt: date, end_dt: date) -> Iterable[RawDoc]:
        """지정 기간 내 8-K/10-Q/10-K 공시를 수집하여 RawDoc 반환."""
        cik_map = self._get_cik_map()
        for ticker in self._seed_tickers:
            cik = cik_map.get(ticker)
            if cik is None:
                logger.debug("CIK not found for ticker %s — skipping", ticker)
                continue
            yield from self._fetch_filings_for_cik(ticker, cik, start_dt, end_dt)

    # ------------------------------------------------------------------
    # CIK mapping
    # ------------------------------------------------------------------

    def _get_cik_map(self) -> Dict[str, int]:
        """ticker → CIK 매핑. 캐시 파일이 있으면 우선 사용."""
        if self._ticker_to_cik is not None:
            return self._ticker_to_cik

        if self._cik_cache_path and self._cik_cache_path.exists():
            with open(self._cik_cache_path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            self._ticker_to_cik = {k.upper(): int(v) for k, v in raw.items()}
            logger.info(
                "CIK cache loaded from %s (%d entries)",
                self._cik_cache_path,
                len(self._ticker_to_cik),
            )
            return self._ticker_to_cik

        self._ticker_to_cik = self._fetch_cik_map_from_sec()
        if self._cik_cache_path and self._ticker_to_cik:
            self._cik_cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._cik_cache_path, "w", encoding="utf-8") as fh:
                json.dump(self._ticker_to_cik, fh, indent=2)
            logger.info("CIK cache saved → %s", self._cik_cache_path)

        return self._ticker_to_cik

    def _fetch_cik_map_from_sec(self) -> Dict[str, int]:
        """company_tickers.json에서 seed ticker에 해당하는 CIK만 추출."""
        # company_tickers.json은 www.sec.gov 도메인이므로 Host 헤더 조정
        sess = requests.Session()
        sess.headers.update({"User-Agent": self._user_agent})
        try:
            resp = sess.get(_COMPANY_TICKERS_URL, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Failed to fetch company_tickers.json: %s", exc)
            return {}
        finally:
            time.sleep(self._delay)

        data = resp.json()
        # 형식: {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
        seed_set = set(self._seed_tickers)
        result: Dict[str, int] = {}
        for entry in data.values():
            ticker = entry.get("ticker", "").upper()
            cik = entry.get("cik_str")
            if ticker in seed_set and cik is not None:
                result[ticker] = int(cik)

        logger.info(
            "CIK resolved: %d / %d seed tickers",
            len(result),
            len(seed_set),
        )
        return result

    # ------------------------------------------------------------------
    # Filing fetch & download
    # ------------------------------------------------------------------

    def _get(self, url: str) -> Optional[requests.Response]:
        try:
            resp = self._session.get(url, timeout=30)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            logger.warning("GET %s failed: %s", url, exc)
            return None
        finally:
            time.sleep(self._delay)

    def _fetch_filings_for_cik(
        self, ticker: str, cik: int, start_dt: date, end_dt: date
    ) -> Iterable[RawDoc]:
        """submissions API로 공시 목록 조회 → 기간 필터 → 본문 수집."""
        url = _SUBMISSIONS_URL.format(cik=cik)
        resp = self._get(url)
        if resp is None:
            return

        data = resp.json()
        recent = data.get("filings", {}).get("recent", {})
        if not recent:
            return

        forms = recent.get("form", [])
        filing_dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])

        for form, filing_date_str, accession, primary_doc in zip(
            forms, filing_dates, accessions, primary_docs
        ):
            if form not in FORM_TYPES:
                continue
            try:
                filing_date = date.fromisoformat(filing_date_str)
            except ValueError:
                continue
            if not (start_dt <= filing_date <= end_dt):
                continue
            if not primary_doc:
                continue

            doc = self._download_filing(
                ticker=ticker,
                cik=cik,
                form_type=form,
                filing_date=filing_date,
                accession=accession,
                primary_doc=primary_doc,
            )
            if doc is not None:
                yield doc

    def _download_filing(
        self,
        ticker: str,
        cik: int,
        form_type: str,
        filing_date: date,
        accession: str,
        primary_doc: str,
    ) -> Optional[RawDoc]:
        """공시 원문 HTML/TXT 다운로드 → RawDoc 반환."""
        acc_clean = accession.replace("-", "")
        url = _ARCHIVE_URL.format(cik=cik, acc_clean=acc_clean, primary_doc=primary_doc)

        resp = self._get(url)
        if resp is None:
            return None

        body = resp.text
        now_utc = datetime.now(timezone.utc)
        published_dt = datetime(
            filing_date.year, filing_date.month, filing_date.day, tzinfo=timezone.utc
        )
        source_doc_id = f"{cik}::{accession}"

        return RawDoc(
            source=self.source_name,
            source_doc_id=source_doc_id,
            canonical_url=url,
            published_at=published_dt,
            ingested_at=now_utc,
            title=f"{ticker} {form_type} {filing_date.isoformat()}",
            body=body,
            lang="en",
            raw_payload_hash=compute_payload_hash(body),
        )
