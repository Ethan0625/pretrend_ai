"""
Backtest Engine configuration + Preset registry.

SOT: docs/strategy_engine_design.md
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple


VALID_TACTICAL_GROUPS = frozenset({"SECTOR", "COMMODITY", "BOND", "COUNTRY"})


# ── Preset ──────────────────────────────────────────────────


@dataclass(frozen=True)
class BacktestPreset:
    """백테스트 전략 프리셋 — allocation + tactical 설정 묶음."""

    name: str
    description: str
    target_ratio_map: Optional[Dict[str, float]]
    allocation_adjustment_limit: float = 0.10
    allocation_step_size: float = 0.05
    tactical_groups: Tuple[str, ...] = ("SECTOR",)


PRESET_V0 = BacktestPreset(
    name="v0",
    description="Range-maintenance: [0.10, 0.60] 범위 유지, SECTOR only",
    target_ratio_map=None,
    tactical_groups=("SECTOR",),
)

PRESET_V1 = BacktestPreset(
    name="v1",
    description="Target-seeking: phase별 목표 비율 추적, SECTOR only",
    target_ratio_map={
        "EXPANSION": 0.60,
        "RECOVERY": 0.60,
        "LATE_CYCLE": 0.60,
        "SLOWDOWN": 0.20,
        "RECESSION": 0.10,
        "UNKNOWN": 0.40,
    },
    tactical_groups=("SECTOR",),
)

PRESET_REGISTRY: Dict[str, BacktestPreset] = {
    "v0": PRESET_V0,
    "v1": PRESET_V1,
}

# 호환용 alias
DEFAULT_TARGET_RATIO_MAP_V1 = PRESET_V1.target_ratio_map


# ── Config ──────────────────────────────────────────────────


@dataclass
class BacktestConfig:
    """백테스트 실행 설정."""

    start_date: date
    end_date: date
    initial_capital: float = 1000.0  # USD
    initial_invested_ratio: float = 0.60

    # Core weights (invested 기준, 합계=1.0)
    initial_weights: Dict[str, float] = field(
        default_factory=lambda: {"SCHD": 0.50, "SPY": 0.30, "IAU": 0.20}
    )

    # SCHD 미출시 기간 (2006-2010) → SPY 대체
    schd_start_date: date = date(2011, 10, 24)
    pre_schd_weights: Dict[str, float] = field(
        default_factory=lambda: {"SPY": 0.80, "IAU": 0.20}
    )

    # 리밸런싱
    rebalance_freq: str = "monthly"  # 매월 첫 영업일

    # 전술 포지션
    max_tactical_slots: int = 2
    tactical_weight: float = 0.15  # 전술 1개당 비중
    tactical_groups: List[str] = field(
        default_factory=lambda: ["SECTOR"]
    )

    # Allocation v1: 시장 상태 → 목표 투자비율 매핑
    # None = v0 (range-maintenance), dict = v1 (target-seeking)
    target_ratio_map: Optional[Dict[str, float]] = None
    allocation_adjustment_limit: float = 0.10
    allocation_step_size: float = 0.05

    # 벤치마크
    benchmark_symbol: str = "SPY"

    # 데이터 경로
    data_root: Path = field(default_factory=lambda: Path("data"))

    # 프리셋 추적
    preset_name: Optional[str] = None

    def __post_init__(self) -> None:
        if self.start_date >= self.end_date:
            raise ValueError(
                f"start_date ({self.start_date}) must be before end_date ({self.end_date})"
            )
        if self.initial_capital <= 0:
            raise ValueError(f"initial_capital must be > 0, got {self.initial_capital}")
        if not (0.0 <= self.initial_invested_ratio <= 1.0):
            raise ValueError(
                f"initial_invested_ratio must be in [0, 1], got {self.initial_invested_ratio}"
            )
        if self.target_ratio_map is not None:
            for phase, ratio in self.target_ratio_map.items():
                if not (0.0 <= ratio <= 1.0):
                    raise ValueError(
                        f"target_ratio_map[{phase!r}] must be in [0, 1], got {ratio}"
                    )
        for grp in self.tactical_groups:
            if grp not in VALID_TACTICAL_GROUPS:
                raise ValueError(f"Unknown tactical group: {grp!r}")

    @classmethod
    def from_preset(
        cls,
        preset_name: str,
        start_date: date,
        end_date: date,
        **overrides,
    ) -> BacktestConfig:
        """프리셋 기반 설정 생성 (개별 override 가능)."""
        preset = PRESET_REGISTRY[preset_name]
        defaults = {
            "target_ratio_map": preset.target_ratio_map,
            "allocation_adjustment_limit": preset.allocation_adjustment_limit,
            "allocation_step_size": preset.allocation_step_size,
            "tactical_groups": list(preset.tactical_groups),
            "preset_name": preset.name,
        }
        defaults.update(overrides)
        return cls(start_date=start_date, end_date=end_date, **defaults)

    def active_weights(self, trade_date: date) -> Dict[str, float]:
        """trade_date 기준 적용할 core weights 반환."""
        if trade_date < self.schd_start_date:
            return dict(self.pre_schd_weights)
        return dict(self.initial_weights)

    @property
    def gold_eod_root(self) -> Path:
        return self.data_root / "gold" / "eod" / "eod_features"

    @property
    def strategy_root(self) -> Path:
        return self.data_root / "strategy"
