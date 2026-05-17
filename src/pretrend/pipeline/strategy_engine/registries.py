"""
Strategy Engine registries — 정적 레지스트리 정의.

SOT: docs/architecture/strategy_engine_design.md §A3
Contract: docs/architecture/policy_config_contract.md
"""
from __future__ import annotations

from typing import Dict, List

from .config import PolicyProfile, DEFAULT_POLICY_V0


# ── Policy Profile Registry ───────────────────────────────
# policy_profile_id → PolicyProfile 매핑.
# v0에서는 RC_V0_DEFAULT 단일 정책만 등록.

POLICY_REGISTRY: Dict[str, PolicyProfile] = {
    DEFAULT_POLICY_V0.policy_profile_id: DEFAULT_POLICY_V0,
}


def resolve_policy(policy_profile_id: str) -> PolicyProfile:
    """Registry에서 정책을 조회한다. 미등록 시 KeyError (fail-fast)."""
    if policy_profile_id not in POLICY_REGISTRY:
        raise KeyError(
            f"Unknown policy_profile_id: {policy_profile_id!r}. "
            f"Registered: {list(POLICY_REGISTRY.keys())}"
        )
    return POLICY_REGISTRY[policy_profile_id]


# ── Core Hold Registry ─────────────────────────────────────
# 기본 보유 ETF 목록 (항상 포트폴리오에 포함되는 핵심 자산).
# v0: 2~3개 ETF 고정.

CORE_HOLD_REGISTRY: List[str] = [
    "SPY",   # US Large-Cap Index
    "SCHD",  # US Dividend (배당 핵심 CORE)
    "IAU",   # Gold
]


# ── Tactical Group Registry ────────────────────────────────
# 전술적 허용 그룹 + 그룹별 대표 ETF 매핑.
# asset_group은 Observability Contract ENUM과 일치.

TACTICAL_GROUP_REGISTRY: Dict[str, List[str]] = {
    "COUNTRY": ["EWJ", "EWZ", "EWY", "EWG", "INDA", "VWO"],
    "COMMODITY": ["USO", "DBA", "UNG", "SLV"],
    "BOND": ["TLT", "HYG", "LQD", "SHY", "TIP"],
    "SECTOR": ["XLV", "XLE", "XLF", "XLK", "XLI", "XLU", "XLRE"],
}

# 전체 허용 그룹 이름
TACTICAL_GROUPS_ALLOWED: List[str] = list(TACTICAL_GROUP_REGISTRY.keys())
