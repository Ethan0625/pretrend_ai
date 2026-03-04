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
    # v2: 2D lookup (long_phase, mid_regime) → target ratio
    target_ratio_map_v2: Optional[Dict[Tuple[str, str], float]] = None
    # v3: 3D lookup 입력은 (long_phase, mid_regime) 기본 + next_step_bias 보정
    target_ratio_map_v3: Optional[Dict[Tuple[str, str], float]] = None
    # DCA: 매월 자금 추가액
    monthly_addition: float = 300.0
    # Text overlay (v2_text 계열)
    text_risk_on_adjust: float = 0.05
    text_risk_off_adjust: float = -0.05
    text_min_confidence: float = 0.0


_ALL_TACTICAL_GROUPS = ("SECTOR", "COMMODITY", "BOND", "COUNTRY")

PRESET_V0 = BacktestPreset(
    name="v0",
    description="Range-maintenance: [0.10, 0.60] 범위 유지, all tactical groups",
    target_ratio_map=None,
    tactical_groups=_ALL_TACTICAL_GROUPS,
)

PRESET_V1 = BacktestPreset(
    name="v1",
    description="Target-seeking: phase별 목표 비율 추적, all tactical groups",
    target_ratio_map={
        "EXPANSION": 0.60,
        "RECOVERY": 0.60,
        "LATE_CYCLE": 0.60,
        "SLOWDOWN": 0.20,
        "RECESSION": 0.10,
        "UNKNOWN": 0.40,
    },
    tactical_groups=_ALL_TACTICAL_GROUPS,
)

PRESET_V2 = BacktestPreset(
    name="v2",
    description="2D allocation: f(long_phase, mid_regime), all tactical groups",
    target_ratio_map=None,
    target_ratio_map_v2={
        ("EXPANSION", "RISK_ON"): 0.80, ("EXPANSION", "NEUTRAL"): 0.70,
        ("EXPANSION", "RISK_OFF"): 0.55, ("EXPANSION", "UNKNOWN"): 0.65,
        ("LATE_CYCLE", "RISK_ON"): 0.60, ("LATE_CYCLE", "NEUTRAL"): 0.45,
        ("LATE_CYCLE", "RISK_OFF"): 0.30, ("LATE_CYCLE", "UNKNOWN"): 0.45,
        ("SLOWDOWN", "RISK_ON"): 0.35, ("SLOWDOWN", "NEUTRAL"): 0.25,
        ("SLOWDOWN", "RISK_OFF"): 0.15, ("SLOWDOWN", "UNKNOWN"): 0.25,
        ("RECOVERY", "RISK_ON"): 0.70, ("RECOVERY", "NEUTRAL"): 0.60,
        ("RECOVERY", "RISK_OFF"): 0.45, ("RECOVERY", "UNKNOWN"): 0.60,
        ("RECESSION", "RISK_ON"): 0.20, ("RECESSION", "NEUTRAL"): 0.10,
        ("RECESSION", "RISK_OFF"): 0.05, ("RECESSION", "UNKNOWN"): 0.10,
        ("UNKNOWN", "RISK_ON"): 0.50, ("UNKNOWN", "NEUTRAL"): 0.40,
        ("UNKNOWN", "RISK_OFF"): 0.30, ("UNKNOWN", "UNKNOWN"): 0.40,
    },
    tactical_groups=_ALL_TACTICAL_GROUPS,
)

PRESET_V2_TEXT = BacktestPreset(
    name="v2_text",
    description="v2 + text overlay soft adjustment (+/- 0.05)",
    target_ratio_map=None,
    target_ratio_map_v2=dict(PRESET_V2.target_ratio_map_v2 or {}),
    tactical_groups=_ALL_TACTICAL_GROUPS,
)

PRESET_V2_TEXT_RISKOFF = BacktestPreset(
    name="v2_text_riskoff",
    description="v2 + text overlay (RISK_OFF only, -0.05)",
    target_ratio_map=None,
    target_ratio_map_v2=dict(PRESET_V2.target_ratio_map_v2 or {}),
    tactical_groups=_ALL_TACTICAL_GROUPS,
    text_risk_on_adjust=0.0,
    text_risk_off_adjust=-0.05,
    text_min_confidence=0.0,
)

PRESET_V2_TEXT_RISKOFF_GUARDED = BacktestPreset(
    name="v2_text_riskoff_guarded",
    description="v2 + text overlay (RISK_OFF only, conf>=0.7, -0.025)",
    target_ratio_map=None,
    target_ratio_map_v2=dict(PRESET_V2.target_ratio_map_v2 or {}),
    tactical_groups=_ALL_TACTICAL_GROUPS,
    text_risk_on_adjust=0.0,
    text_risk_off_adjust=-0.025,
    text_min_confidence=0.7,
)

PRESET_V3 = BacktestPreset(
    name="v3",
    description="3D allocation: f(long_phase, mid_regime, next_step_bias)",
    target_ratio_map=None,
    target_ratio_map_v2=None,
    target_ratio_map_v3=dict(PRESET_V2.target_ratio_map_v2 or {}),
    tactical_groups=_ALL_TACTICAL_GROUPS,
)

PRESET_V3_1 = BacktestPreset(
    name="v3.1",
    description="v3 + monthly bias lock (20D bias fixed per month)",
    target_ratio_map=None,
    target_ratio_map_v2=None,
    target_ratio_map_v3=dict(PRESET_V2.target_ratio_map_v2 or {}),
    tactical_groups=_ALL_TACTICAL_GROUPS,
)

PRESET_V3_2 = BacktestPreset(
    name="v3.2",
    description="v3.1 + shock override (PANIC/RISK_OFF streak + cooldown)",
    target_ratio_map=None,
    target_ratio_map_v2=None,
    target_ratio_map_v3=dict(PRESET_V2.target_ratio_map_v2 or {}),
    tactical_groups=_ALL_TACTICAL_GROUPS,
)

PRESET_V3_3 = BacktestPreset(
    name="v3.3",
    description="v3.2 + hazard-aware override (10d transition hazard gate)",
    target_ratio_map=None,
    target_ratio_map_v2=None,
    target_ratio_map_v3=dict(PRESET_V2.target_ratio_map_v2 or {}),
    tactical_groups=_ALL_TACTICAL_GROUPS,
)

PRESET_V3_4 = BacktestPreset(
    name="v3.4",
    description="v3.3 + tactical asset-group transition gate",
    target_ratio_map=None,
    target_ratio_map_v2=None,
    target_ratio_map_v3=dict(PRESET_V2.target_ratio_map_v2 or {}),
    tactical_groups=_ALL_TACTICAL_GROUPS,
)

PRESET_V3_4_1 = BacktestPreset(
    name="v3.4.1",
    description="v3.4 + recovery-aware re-entry gate (WEAK>=2, RELIEF streak/MID RISK_ON)",
    target_ratio_map=None,
    target_ratio_map_v2=None,
    target_ratio_map_v3=dict(PRESET_V2.target_ratio_map_v2 or {}),
    tactical_groups=_ALL_TACTICAL_GROUPS,
)

PRESET_V3_4_2_PHASE = BacktestPreset(
    name="v3.4.2-phase",
    description="v3.4.1 + phase-aware bias state machine (RECOVERY baseline=RISK_ON)",
    target_ratio_map=None,
    target_ratio_map_v2=None,
    target_ratio_map_v3=dict(PRESET_V2.target_ratio_map_v2 or {}),
    tactical_groups=_ALL_TACTICAL_GROUPS,
)

PRESET_V3_4_2A = BacktestPreset(
    name="v3.4.2a",
    description="v3.4.2-phase + conditional cooldown compression + hard-gate exit assist",
    target_ratio_map=None,
    target_ratio_map_v2=None,
    target_ratio_map_v3=dict(PRESET_V2.target_ratio_map_v2 or {}),
    tactical_groups=_ALL_TACTICAL_GROUPS,
)

PRESET_REGISTRY: Dict[str, BacktestPreset] = {
    "v0": PRESET_V0,
    "v1": PRESET_V1,
    "v2": PRESET_V2,
    "v2_text": PRESET_V2_TEXT,
    "v2_text_riskoff": PRESET_V2_TEXT_RISKOFF,
    "v2_text_riskoff_guarded": PRESET_V2_TEXT_RISKOFF_GUARDED,
    "v3": PRESET_V3,
    "v3.1": PRESET_V3_1,
    "v3.2": PRESET_V3_2,
    "v3.3": PRESET_V3_3,
    "v3.4": PRESET_V3_4,
    "v3.4.1": PRESET_V3_4_1,
    "v3.4.2-phase": PRESET_V3_4_2_PHASE,
    "v3.4.2a": PRESET_V3_4_2A,
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

    # SCHD 미출시 기간 (2006-2011-10) → DVY 25% + VIG 25% + SPY 30% + IAU 20% 대체
    # SCHD 출시(2011-10-24) 이후 → 3주 단계 매도 (50/30/20%) 후 SCHD로 전환
    schd_start_date: date = date(2011, 10, 24)
    pre_schd_weights: Dict[str, float] = field(
        default_factory=lambda: {"DVY": 0.25, "VIG": 0.25, "SPY": 0.30, "IAU": 0.20}
    )

    # 리밸런싱
    rebalance_freq: str = "monthly"  # 매월 첫 영업일

    # 전술 포지션
    max_tactical_slots: int = 2
    tactical_weight: float = 0.15  # 전술 1개당 비중
    tactical_groups: List[str] = field(
        default_factory=lambda: ["SECTOR", "COMMODITY", "BOND", "COUNTRY"]
    )

    # DCA: 매월 첫 거래일 자금 추가액
    monthly_addition: float = 300.0

    # Allocation v1: 시장 상태 → 목표 투자비율 매핑
    # None = v0 (range-maintenance), dict = v1 (target-seeking)
    target_ratio_map: Optional[Dict[str, float]] = None
    # Allocation v2: 2D lookup (long_phase, mid_regime) → target ratio
    target_ratio_map_v2: Optional[Dict[Tuple[str, str], float]] = None
    # Allocation v3: v2 base map + next_step_bias adjustment
    target_ratio_map_v3: Optional[Dict[Tuple[str, str], float]] = None
    text_risk_on_adjust: float = 0.05
    text_risk_off_adjust: float = -0.05
    text_min_confidence: float = 0.0
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
        if self.monthly_addition < 0:
            raise ValueError(f"monthly_addition must be >= 0, got {self.monthly_addition}")
        if self.target_ratio_map is not None:
            for phase, ratio in self.target_ratio_map.items():
                if not (0.0 <= ratio <= 1.0):
                    raise ValueError(
                        f"target_ratio_map[{phase!r}] must be in [0, 1], got {ratio}"
                    )
        if self.target_ratio_map_v2 is not None:
            for (lp, mr), ratio in self.target_ratio_map_v2.items():
                if not isinstance(lp, str) or not isinstance(mr, str):
                    raise ValueError(
                        f"target_ratio_map_v2 key must be Tuple[str, str], got ({lp!r}, {mr!r})"
                    )
                if not (0.0 <= ratio <= 1.0):
                    raise ValueError(
                        f"target_ratio_map_v2[({lp!r}, {mr!r})] must be in [0, 1], got {ratio}"
                    )
        if self.target_ratio_map_v3 is not None:
            for (lp, mr), ratio in self.target_ratio_map_v3.items():
                if not isinstance(lp, str) or not isinstance(mr, str):
                    raise ValueError(
                        f"target_ratio_map_v3 key must be Tuple[str, str], got ({lp!r}, {mr!r})"
                    )
                if not (0.0 <= ratio <= 1.0):
                    raise ValueError(
                        f"target_ratio_map_v3[({lp!r}, {mr!r})] must be in [0, 1], got {ratio}"
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
            "target_ratio_map_v2": preset.target_ratio_map_v2,
            "target_ratio_map_v3": preset.target_ratio_map_v3,
            "allocation_adjustment_limit": preset.allocation_adjustment_limit,
            "allocation_step_size": preset.allocation_step_size,
            "tactical_groups": list(preset.tactical_groups),
            "preset_name": preset.name,
            "monthly_addition": preset.monthly_addition,
            "text_risk_on_adjust": preset.text_risk_on_adjust,
            "text_risk_off_adjust": preset.text_risk_off_adjust,
            "text_min_confidence": preset.text_min_confidence,
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
