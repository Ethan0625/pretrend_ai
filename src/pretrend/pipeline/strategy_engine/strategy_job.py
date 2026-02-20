"""
Strategy Engine E2E Runner + CLI.

Gold Macro/EOD → Axis Features → Axis×Horizon State → Market Position
→ Policy Selection → Universe → Allocation → Sell Plan → Snapshot Write.

SOT: docs/strategy_engine_design.md
패턴: macro_job.py (Config/Runner/Result/CLI)

Usage:
    python -m pretrend.pipeline.strategy_engine.strategy_job --date 2026-02-12
"""
from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from .config import StrategyEngineConfig, DEFAULT_POLICY_V0
from .io import load_gold_macro, load_gold_eod, write_snapshot_atomic
from .axis_features.macro_policy import build_macro_policy_axis
from .axis_features.price_volatility import build_price_volatility_axis
from .axis_features.flow_structure import build_flow_structure_axis
from .axis_features.sentiment import build_sentiment_proxy_axis
from .axis_features.schema import AxisFeatureBundle
from .axis_horizon_state.builder import build_axis_horizon_state
from .market_position.engine import build_market_position
from .policy_selector.engine import build_policy_selection
from .universe.engine import build_universe
from .allocation.engine import build_allocation
from .sell_planner.engine import build_sell_plan

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )


@dataclass
class StrategyStageResult:
    """각 단계의 결과 메타 정보."""
    row_count: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyJobResult:
    """전체 Strategy Engine 실행 결과."""
    decision_date: date
    run_id: str
    axis_features: StrategyStageResult = field(default_factory=StrategyStageResult)
    axis_horizon_state: StrategyStageResult = field(default_factory=StrategyStageResult)
    market_position: StrategyStageResult = field(default_factory=StrategyStageResult)
    policy_selection: StrategyStageResult = field(default_factory=StrategyStageResult)
    universe: StrategyStageResult = field(default_factory=StrategyStageResult)
    allocation: StrategyStageResult = field(default_factory=StrategyStageResult)
    sell_plan: StrategyStageResult = field(default_factory=StrategyStageResult)


class StrategyJobRunner:
    """Strategy Engine End-to-End Runner."""

    def __init__(
        self,
        config: StrategyEngineConfig,
        policy_profile_id: str = "RC_V0_DEFAULT",
        current_invested_ratio: float = 0.0,
        long_z_threshold: float = 0.0,
    ) -> None:
        self.config = config
        self.policy_profile_id = policy_profile_id
        self.current_invested_ratio = current_invested_ratio
        self.long_z_threshold = long_z_threshold

    def run(self, decision_date: date) -> StrategyJobResult:
        """전체 Strategy Engine 파이프라인 실행."""
        run_id = datetime.now().strftime("strategy_%Y%m%dT%H%M%S")
        logger.info("[StrategyJob] Starting run_id=%s, decision_date=%s", run_id, decision_date)

        result = StrategyJobResult(decision_date=decision_date, run_id=run_id)

        # 1) Load Gold inputs
        df_gold_macro = load_gold_macro(self.config.gold_macro_root, end_date=decision_date)
        df_gold_eod = load_gold_eod(self.config.gold_eod_root, end_date=decision_date)
        logger.info("[StrategyJob] Loaded Gold Macro=%d, Gold EOD=%d rows",
                    len(df_gold_macro), len(df_gold_eod))

        # 2) Build Axis Features
        macro_policy = build_macro_policy_axis(df_gold_macro)
        price_vol = build_price_volatility_axis(df_gold_eod)
        flow = build_flow_structure_axis(df_gold_eod)
        sentiment = build_sentiment_proxy_axis(df_gold_eod)

        bundle = AxisFeatureBundle(
            macro_policy=macro_policy,
            price_volatility=price_vol,
            flow_structure=flow,
            sentiment=sentiment,
        )
        result.axis_features = StrategyStageResult(
            row_count=len(macro_policy) + len(price_vol) + len(flow) + len(sentiment),
        )

        # 3) Build Axis×Horizon State (12-slot)
        df_ahs = build_axis_horizon_state(bundle, run_id=run_id, long_z_threshold=self.long_z_threshold)
        result.axis_horizon_state = StrategyStageResult(row_count=len(df_ahs))
        if not df_ahs.empty:
            write_snapshot_atomic(
                df_ahs, self.config.strategy_output_root,
                "axis_horizon_state", decision_date, run_id,
            )

        # 4) Build Market Position
        df_mp = build_market_position(df_ahs, run_id=run_id)
        result.market_position = StrategyStageResult(row_count=len(df_mp))
        if not df_mp.empty:
            write_snapshot_atomic(
                df_mp, self.config.strategy_output_root,
                "market_position", decision_date, run_id,
            )

        # 5) Build Policy Selection
        df_ps = build_policy_selection(df_mp, self.policy_profile_id, run_id=run_id)
        result.policy_selection = StrategyStageResult(row_count=len(df_ps))
        if not df_ps.empty:
            write_snapshot_atomic(
                df_ps, self.config.strategy_output_root,
                "policy_selection", decision_date, run_id,
            )

        # 6) Build Universe (WHAT_TO_HOLD) — decision_date 하루치만 저장
        #    df_ps 전체(전 기간)를 넘기면 스냅샷에 누적 이력이 쌓이는 문제 방지.
        df_ps_today = df_ps[df_ps["trade_date"] == decision_date]
        df_universe = build_universe(df_ps_today, df_gold_eod)
        result.universe = StrategyStageResult(row_count=len(df_universe))
        if not df_universe.empty:
            write_snapshot_atomic(
                df_universe, self.config.strategy_output_root,
                "what_to_hold", decision_date, run_id,
            )

        # 7) Build Allocation (HOW_MUCH_EXPOSURE)
        df_alloc = build_allocation(df_ps, self.current_invested_ratio)
        result.allocation = StrategyStageResult(row_count=len(df_alloc))
        if not df_alloc.empty:
            write_snapshot_atomic(
                df_alloc, self.config.strategy_output_root,
                "exposure", decision_date, run_id,
            )

        # 8) Build Sell Plan (HOW_MUCH_TO_SELL)
        df_sell = build_sell_plan(df_alloc, df_ps, df_universe)
        result.sell_plan = StrategyStageResult(row_count=len(df_sell))
        if not df_sell.empty:
            write_snapshot_atomic(
                df_sell, self.config.strategy_output_root,
                "sell_plan", decision_date, run_id,
            )

        # 9) Meta log
        self._write_meta_log(result)

        logger.info("[StrategyJob] Completed run_id=%s", run_id)
        return result

    def _write_meta_log(self, result: StrategyJobResult) -> None:
        """메타 로그 기록."""
        log_path = self.config.strategy_job_log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)

        log_row = pd.DataFrame([{
            "decision_date": result.decision_date,
            "run_id": result.run_id,
            "ahs_rows": result.axis_horizon_state.row_count,
            "mp_rows": result.market_position.row_count,
            "ps_rows": result.policy_selection.row_count,
            "universe_rows": result.universe.row_count,
            "allocation_rows": result.allocation.row_count,
            "sell_plan_rows": result.sell_plan.row_count,
            "completed_at": pd.Timestamp.now("UTC"),
        }])

        if log_path.exists():
            existing = pd.read_parquet(log_path)
            log_row = pd.concat([existing, log_row], ignore_index=True)

        log_row.to_parquet(log_path, index=False)
        logger.info("[StrategyJob] Meta log: %s", log_path)


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Strategy Engine E2E Runner")
    parser.add_argument("--date", required=True, help="Decision date (YYYY-MM-DD)")
    parser.add_argument("--invested-ratio", type=float, default=0.0,
                        help="Current invested ratio (default: 0.0)")
    parser.add_argument("--policy", default="RC_V0_DEFAULT",
                        help="Policy profile ID (default: RC_V0_DEFAULT)")
    parser.add_argument("--long-z-threshold", type=float, default=0.0,
                        help="Long Engine z-score threshold (default: 0.0). "
                             "Positive values reduce SLOWDOWN/RECESSION sensitivity.")
    args = parser.parse_args()

    decision_date = date.fromisoformat(args.date)
    config = StrategyEngineConfig.from_env()
    runner = StrategyJobRunner(
        config=config,
        policy_profile_id=args.policy,
        current_invested_ratio=args.invested_ratio,
        long_z_threshold=args.long_z_threshold,
    )
    result = runner.run(decision_date)
    print(f"Strategy Engine completed: run_id={result.run_id}, "
          f"AHS={result.axis_horizon_state.row_count}, "
          f"Universe={result.universe.row_count}, "
          f"Allocation={result.allocation.row_count}")


if __name__ == "__main__":
    main()
