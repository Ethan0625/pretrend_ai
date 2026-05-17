"""
Registries 계약 테스트.

SOT: docs/architecture/strategy_engine_design.md §A3
Contract: docs/architecture/policy_config_contract.md
"""
from __future__ import annotations

import pytest

from pretrend.pipeline.strategy_engine.config import DEFAULT_POLICY_V0
from pretrend.pipeline.strategy_engine.registries import (
    POLICY_REGISTRY,
    resolve_policy,
    CORE_HOLD_REGISTRY,
    TACTICAL_GROUP_REGISTRY,
    TACTICAL_GROUPS_ALLOWED,
)


class TestPolicyRegistry:
    def test_default_policy_registered(self):
        assert "RC_V0_DEFAULT" in POLICY_REGISTRY

    def test_resolve_default(self):
        p = resolve_policy("RC_V0_DEFAULT")
        assert p is DEFAULT_POLICY_V0

    def test_resolve_unknown_raises(self):
        with pytest.raises(KeyError, match="Unknown policy_profile_id"):
            resolve_policy("NONEXISTENT")

    def test_registry_immutability(self):
        """v0에서는 단일 정책만 등록."""
        assert len(POLICY_REGISTRY) == 1


class TestCoreHoldRegistry:
    def test_core_holds_exist(self):
        assert len(CORE_HOLD_REGISTRY) >= 2
        assert "SPY" in CORE_HOLD_REGISTRY
        assert "SCHD" in CORE_HOLD_REGISTRY   # 배당 핵심 CORE
        assert "IAU" in CORE_HOLD_REGISTRY
        assert "TLT" not in CORE_HOLD_REGISTRY  # TLT는 BOND tactical로 이동

    def test_core_holds_are_strings(self):
        for sym in CORE_HOLD_REGISTRY:
            assert isinstance(sym, str)


class TestTacticalGroupRegistry:
    def test_groups_present(self):
        expected = {"COUNTRY", "COMMODITY", "BOND", "SECTOR"}
        assert set(TACTICAL_GROUP_REGISTRY.keys()) == expected

    def test_each_group_has_symbols(self):
        for group, symbols in TACTICAL_GROUP_REGISTRY.items():
            assert len(symbols) >= 1, f"Group {group} is empty"
            for sym in symbols:
                assert isinstance(sym, str)

    def test_allowed_matches_keys(self):
        assert set(TACTICAL_GROUPS_ALLOWED) == set(TACTICAL_GROUP_REGISTRY.keys())

    def test_no_overlap_with_core(self):
        """Core hold ETF는 Tactical group에 포함되지 않음."""
        all_tactical = {
            sym
            for symbols in TACTICAL_GROUP_REGISTRY.values()
            for sym in symbols
        }
        overlap = set(CORE_HOLD_REGISTRY) & all_tactical
        assert not overlap, f"Overlap: {overlap}"
