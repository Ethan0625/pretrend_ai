from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Iterable
from typing_extensions import TypedDict


class RawDoc(TypedDict):
    """Bronze 레이어 원문 문서 스키마."""
    source: str           # 출처 식별자 (sec_edgar, fed_fomc, ...)
    source_doc_id: str    # 소스 내부 문서 ID (멱등키 구성)
    canonical_url: str    # 원문 URL
    published_at: datetime  # 게시 시각 (UTC)
    ingested_at: datetime   # 수집 시각 (UTC)
    title: str
    body: str             # 원문 본문 (HTML 포함 가능)
    lang: str             # 언어 코드 (예: en)
    raw_payload_hash: str # body SHA-256 해시


def compute_payload_hash(body: str) -> str:
    """body 문자열의 SHA-256 해시 반환."""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def make_doc_id(source: str, source_doc_id: str) -> str:
    """멱등키 (source, source_doc_id) → doc_id 해시."""
    key = f"{source}::{source_doc_id}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class TextSourceAdapter(ABC):
    """텍스트 소스 어댑터 인터페이스.

    각 소스(SEC EDGAR, Fed/FOMC 등)는 이 ABC를 구현한다.
    fetch()는 지정 기간 내 수집 가능한 문서를 Iterable[RawDoc]으로 반환한다.
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """소스 식별자 (예: sec_edgar, fed_fomc)."""
        ...

    @abstractmethod
    def fetch(self, start_dt: date, end_dt: date) -> Iterable[RawDoc]:
        """지정 기간의 원문 문서를 수집하여 반환.

        Args:
            start_dt: 수집 시작일 (inclusive)
            end_dt: 수집 종료일 (inclusive)

        Yields:
            RawDoc 딕셔너리 (Bronze 스키마)
        """
        ...
