"""
Strategy Engine configuration.

Contract: docs/architecture/policy_config_contract.md
SOT: docs/strategy_engine_design.md
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PolicyProfile:
    """정적 정책 파라미터 (Policy Config).

    SOT: docs/architecture/policy_config_contract.md §3
    """

    policy_profile_id: str
    target_invested_lower: float
    target_invested_upper: float
    adjustment_limit: float
    step_size: float
    rounding_policy: str
    policy_version: str

    def __post_init__(self) -> None:
        if self.target_invested_lower > self.target_invested_upper:
            raise ValueError(
                f"target_invested_lower ({self.target_invested_lower}) "
                f"> target_invested_upper ({self.target_invested_upper})"
            )
        if self.adjustment_limit <= 0:
            raise ValueError(f"adjustment_limit must be > 0, got {self.adjustment_limit}")
        if self.step_size <= 0:
            raise ValueError(f"step_size must be > 0, got {self.step_size}")


DEFAULT_POLICY_V0 = PolicyProfile(
    policy_profile_id="RC_V0_DEFAULT",
    target_invested_lower=0.10,
    target_invested_upper=0.60,
    adjustment_limit=0.10,
    step_size=0.05,
    rounding_policy="ROUND_DOWN",
    policy_version="v0",
)


@dataclass
class StrategyEngineConfig:
    """Strategy Engine 실행 설정.

    SOT: docs/strategy_engine_design.md §E
    """

    data_root: Path
    meta_root: Path = field(default=None)

    def __post_init__(self) -> None:
        if self.meta_root is None:
            self.meta_root = self.data_root / "meta"

    @property
    def gold_macro_root(self) -> Path:
        return self.data_root / "gold" / "macro" / "macro_features"

    @property
    def gold_eod_root(self) -> Path:
        return self.data_root / "gold" / "eod" / "eod_features"

    @property
    def skew_gold_root(self) -> Path:
        return self.data_root / "gold" / "macro" / "skew" / "put_call"

    @property
    def gold_text_rule_root(self) -> Path:
        return self.data_root / "gold" / "text" / "text_daily_features"

    @property
    def gold_text_llm_root(self) -> Path:
        return self.data_root / "gold" / "text" / "text_llm_features"

    @property
    def strategy_output_root(self) -> Path:
        return self.data_root / "strategy"

    @property
    def strategy_job_log_path(self) -> Path:
        return self.meta_root / "strategy_engine_log.parquet"

    @classmethod
    def from_env(cls) -> StrategyEngineConfig:
        data_root = Path(os.getenv("PRETREND_DATA_ROOT", "data"))
        return cls(data_root=data_root)
