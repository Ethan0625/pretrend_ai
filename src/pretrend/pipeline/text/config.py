"""Text Pipeline 설정 모음.

SOT: docs/architecture/text_observability_contract.md
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from pretrend.pipeline.text.adapters.sec_edgar import TEXT_SEC_SEED_TICKERS

DATA_ROOT = Path(os.getenv("PRETREND_DATA_ROOT", "data"))


@dataclass
class TextPipelineConfig:
    """Text 파이프라인 전체 설정."""

    data_root: Path = field(default_factory=lambda: DATA_ROOT)

    # SEC EDGAR
    sec_user_agent: str = field(
        default_factory=lambda: os.getenv(
            "SEC_USER_AGENT", "pretrend-ai macosc0625@gmail.com"
        )
    )
    sec_seed_tickers: List[str] = field(
        default_factory=lambda: list(TEXT_SEC_SEED_TICKERS)
    )
    # ticker → CIK 캐시 파일 (첫 실행 시 자동 생성)
    cik_cache_path: Path = field(
        default_factory=lambda: DATA_ROOT / "config" / "text_universe.json"
    )
    sec_request_delay_sec: float = 0.11  # 10 req/sec 상한

    # Fed/FOMC
    fed_rss_url: str = "https://www.federalreserve.gov/feeds/press_all.xml"
    fed_request_delay_sec: float = 0.5

    # Bronze
    bronze_root: Path = field(default_factory=lambda: DATA_ROOT / "bronze" / "text")

    # Silver
    silver_root: Path = field(default_factory=lambda: DATA_ROOT / "silver" / "text")

    # Gold
    gold_root: Path = field(default_factory=lambda: DATA_ROOT / "gold" / "text")

    @classmethod
    def default(cls) -> "TextPipelineConfig":
        return cls()
