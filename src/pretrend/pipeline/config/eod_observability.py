"""
EOD Observability Set — Single Source of Truth (v1).

계약 문서: docs/architecture/eod_observability_contract.md

이 모듈은 Observability Set의 심볼/분류/라벨을 코드 수준에서 고정한다.
Bronze/Silver/Gold 모든 레이어가 이 SOT를 참조한다.
"""
from __future__ import annotations

from typing import Dict, FrozenSet, List, TypedDict


# ── ENUM ────────────────────────────────────────────────

ASSET_GROUP_ENUM: FrozenSet[str] = frozenset(
    {"INDEX", "COUNTRY", "COMMODITY", "BOND", "SECTOR"}
)


# ── TypedDict ───────────────────────────────────────────

class ObservabilityEntry(TypedDict):
    symbol: str
    asset_group: str
    asset_name: str
    asset_subtype: str


# ── Observability Set v1 (32 ETFs) ──────────────────────

OBSERVABILITY_SET_V1: List[ObservabilityEntry] = [  # 33 ETFs total
    # INDEX (6)
    {"symbol": "SPY",  "asset_group": "INDEX", "asset_name": "SP500",          "asset_subtype": "BROAD_MARKET"},
    {"symbol": "VOO",  "asset_group": "INDEX", "asset_name": "SP500",          "asset_subtype": "BROAD_MARKET"},
    {"symbol": "QQQ",  "asset_group": "INDEX", "asset_name": "NASDAQ100",      "asset_subtype": "GROWTH_TECH"},
    {"symbol": "DIA",  "asset_group": "INDEX", "asset_name": "DOW30",          "asset_subtype": "VALUE_INDUSTRIAL"},
    {"symbol": "SCHD", "asset_group": "INDEX", "asset_name": "US_DIVIDEND",    "asset_subtype": "DIVIDEND_GROWTH"},
    {"symbol": "IWM",  "asset_group": "INDEX", "asset_name": "RUSSELL2000",    "asset_subtype": "SMALL_CAP"},
    # COUNTRY (5)
    {"symbol": "EWY",  "asset_group": "COUNTRY", "asset_name": "SOUTH_KOREA",  "asset_subtype": "EM_ASIA"},
    {"symbol": "ASHR", "asset_group": "COUNTRY", "asset_name": "CHINA",        "asset_subtype": "CHINA_A_SHARES"},
    {"symbol": "CQQQ", "asset_group": "COUNTRY", "asset_name": "CHINA",        "asset_subtype": "CHINA_TECH"},
    {"symbol": "EWJ",  "asset_group": "COUNTRY", "asset_name": "JAPAN",        "asset_subtype": "DEVELOPED_ASIA"},
    {"symbol": "INDA", "asset_group": "COUNTRY", "asset_name": "INDIA",        "asset_subtype": "EM_ASIA"},
    # COMMODITY (7)
    {"symbol": "IAU",  "asset_group": "COMMODITY", "asset_name": "GOLD",           "asset_subtype": "PHYSICAL_GOLD"},
    {"symbol": "GDX",  "asset_group": "COMMODITY", "asset_name": "GOLD_MINERS",    "asset_subtype": "GOLD_EQUITY"},
    {"symbol": "SLV",  "asset_group": "COMMODITY", "asset_name": "SILVER",         "asset_subtype": "PHYSICAL_SILVER"},
    {"symbol": "USO",  "asset_group": "COMMODITY", "asset_name": "CRUDE_OIL",      "asset_subtype": "ENERGY_RAW"},
    {"symbol": "XOP",  "asset_group": "COMMODITY", "asset_name": "OIL_PRODUCERS",  "asset_subtype": "ENERGY_EQUITY"},
    {"symbol": "UNG",  "asset_group": "COMMODITY", "asset_name": "NATURAL_GAS",    "asset_subtype": "ENERGY_RAW"},
    {"symbol": "DBA",  "asset_group": "COMMODITY", "asset_name": "AGRICULTURE",    "asset_subtype": "SOFT_COMMODITY"},
    # BOND (1)
    {"symbol": "TLT",  "asset_group": "BOND", "asset_name": "US_TREASURY_20Y", "asset_subtype": "LONG_DURATION"},
    # SECTOR (14)
    {"symbol": "XLV",  "asset_group": "SECTOR", "asset_name": "HEALTH_CARE",              "asset_subtype": "DEFENSIVE"},
    {"symbol": "XLE",  "asset_group": "SECTOR", "asset_name": "ENERGY",                   "asset_subtype": "CYCLICAL"},
    {"symbol": "SOXX", "asset_group": "SECTOR", "asset_name": "SEMICONDUCTOR",            "asset_subtype": "TECH_INDUSTRY"},
    {"symbol": "XLF",  "asset_group": "SECTOR", "asset_name": "FINANCIALS",               "asset_subtype": "CYCLICAL"},
    {"symbol": "KRE",  "asset_group": "SECTOR", "asset_name": "REGIONAL_BANKS",           "asset_subtype": "SMALL_BANKS"},
    {"symbol": "NLR",  "asset_group": "SECTOR", "asset_name": "NUCLEAR",                  "asset_subtype": "CLEAN_ENERGY"},
    {"symbol": "XLK",  "asset_group": "SECTOR", "asset_name": "INFORMATION_TECH",         "asset_subtype": "TECH"},
    {"symbol": "XLB",  "asset_group": "SECTOR", "asset_name": "MATERIALS",                "asset_subtype": "CYCLICAL"},
    {"symbol": "XLY",  "asset_group": "SECTOR", "asset_name": "CONSUMER_DISCRETIONARY",   "asset_subtype": "CYCLICAL"},
    {"symbol": "XLP",  "asset_group": "SECTOR", "asset_name": "CONSUMER_STAPLES",         "asset_subtype": "DEFENSIVE"},
    {"symbol": "XLC",  "asset_group": "SECTOR", "asset_name": "COMMUNICATION_SERVICES",   "asset_subtype": "DEFENSIVE_GROWTH"},
    {"symbol": "XLRE", "asset_group": "SECTOR", "asset_name": "REAL_ESTATE",              "asset_subtype": "RATE_SENSITIVE"},
    {"symbol": "XLU",  "asset_group": "SECTOR", "asset_name": "UTILITIES",                "asset_subtype": "DEFENSIVE"},
    {"symbol": "XLI",  "asset_group": "SECTOR", "asset_name": "INDUSTRIALS",              "asset_subtype": "CYCLICAL"},
]

# ── Derived lookups ─────────────────────────────────────

OBSERVABILITY_SYMBOLS_V1: List[str] = [
    entry["symbol"] for entry in OBSERVABILITY_SET_V1
]

LABEL_BY_SYMBOL_V1: Dict[str, ObservabilityEntry] = {
    entry["symbol"]: entry for entry in OBSERVABILITY_SET_V1
}


# ── Validation ──────────────────────────────────────────

def validate_observability_set() -> None:
    """
    import 시점에 SOT 무결성을 검증한다.

    Raises:
        ValueError: symbol 중복, 대문자 위반, ENUM 위반 시.
    """
    symbols = [e["symbol"] for e in OBSERVABILITY_SET_V1]

    # symbol 중복 검사
    if len(symbols) != len(set(symbols)):
        dupes = [s for s in symbols if symbols.count(s) > 1]
        raise ValueError(f"Duplicate symbols in OBSERVABILITY_SET_V1: {set(dupes)}")

    for entry in OBSERVABILITY_SET_V1:
        sym = entry["symbol"]

        # 대문자 검사
        if sym != sym.upper():
            raise ValueError(f"Symbol must be uppercase: {sym}")

        # ENUM 검사
        if entry["asset_group"] not in ASSET_GROUP_ENUM:
            raise ValueError(
                f"{sym}: asset_group={entry['asset_group']} "
                f"not in {ASSET_GROUP_ENUM}"
            )


# import 시 자동 검증
validate_observability_set()
