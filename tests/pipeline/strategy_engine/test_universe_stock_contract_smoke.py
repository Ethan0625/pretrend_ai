"""
Universe-Stock(U0~U3) 계약 초안 스모크 테스트.

목적:
- Universe-ETF(Execution)와 Universe-Stock(Research) 경계 문서가 최소 구조를 갖췄는지 확인
- 데이터/코드 구현 없이 계약 인터페이스 정합성만 검증
"""
from __future__ import annotations

from pathlib import Path


DOC_PATH = Path("docs/architecture/universe_contract.md")


def test_universe_stock_extension_section_exists() -> None:
    text = DOC_PATH.read_text(encoding="utf-8")

    assert "## 8. Universe-Stock(U0~U3) Extension Port (Research)" in text
    assert "U0" in text and "U1" in text and "U2" in text and "U3" in text


def test_execution_research_grain_isolation_defined() -> None:
    text = DOC_PATH.read_text(encoding="utf-8")

    assert "Universe-ETF(Execution) grain: `(rebalance_date, symbol)`" in text
    assert "U3: `(as_of_date, symbol)`" in text
    assert "동일 테이블/파티션을 공유하지 않는다" in text
