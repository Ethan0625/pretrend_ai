"""
Walk-Forward 기간별 성과 분석 — 운영 안정화 검증.

동일 snapshot을 공유하므로 look-ahead bias가 존재한다.
목적: 여러 시장 국면에서 threshold=0.3 고정 전략의 일관성 파악.

SOT: docs/design/ (계획 문서)
출력/저장: report.py (print_walk_forward_summary, save_walk_forward)

Usage:
    python -m pretrend.pipeline.backtest.walk_forward \\
        --preset v2 --window-years 4 --step-years 2 [--save]
"""
from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from ._utils import load_strategy_snapshot
from .config import BacktestConfig
from .runner import BacktestRunner

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

# 고정 스키마 컬럼
WALK_FORWARD_COLUMNS: List[str] = [
    "window_start", "window_end",
    "cagr", "total_return", "max_drawdown",
    "sharpe_ratio", "benchmark_cagr", "excess_cagr",
    "diag_12slot_coverage", "diag_unknown_ratio", "diag_axis_consistency",
    "tier1_pass", "tier2_warning", "validation_status",
    "preset", "generated_at",
]

# Tier-1 성과 기준(1차 게이트)
_MIN_CAGR = 0.0
_MIN_SHARPE = 0.0
_MAX_MDD = -0.35

# Tier-2 진단 기준(2차 진단 KPI)
_MIN_DIAG_COVERAGE = 0.20
_MAX_UNKNOWN_RATIO = 0.80
_MIN_AXIS_CONSISTENCY = 0.50


@dataclass
class WalkForwardConfig:
    """Walk-Forward 실행 설정."""

    preset: str = "v2"
    windows: List[Tuple[date, date]] = field(default_factory=list)
    window_years: int = 4
    step_years: int = 2
    full_start: date = date(2006, 1, 3)
    full_end: date = date(2024, 6, 3)
    initial_capital: float = 1000.0


class WalkForwardRunner:
    """Walk-Forward 기간별 성과 분석 실행기."""

    def run(self, config: WalkForwardConfig) -> pd.DataFrame:
        """기간별 백테스트를 실행하고 성과 DataFrame을 반환한다.

        Parameters
        ----------
        config : WalkForwardConfig
            실행 설정.

        Returns
        -------
        DataFrame with WALK_FORWARD_COLUMNS.
        """
        windows = config.windows if config.windows else self._generate_windows(config)
        if not windows:
            logger.warning("[WalkForward] No windows to run.")
            return pd.DataFrame(columns=WALK_FORWARD_COLUMNS)

        logger.info("[WalkForward] preset=%s, %d windows", config.preset, len(windows))
        generated_at = datetime.now().isoformat(timespec="seconds")
        rows = []
        ahs_df = self._load_ahs_snapshot_for_diagnostics()

        for i, (ws, we) in enumerate(windows, 1):
            logger.info("[WalkForward] Window %d/%d: %s ~ %s", i, len(windows), ws, we)
            bt_config = BacktestConfig.from_preset(
                config.preset,
                start_date=ws,
                end_date=we,
                initial_capital=config.initial_capital,
            )
            result = BacktestRunner().run(bt_config)
            m = result.metrics
            diag = self._compute_12slot_diagnostics(ahs_df, ws, we)
            tier1 = self._is_tier1_pass(m)
            tier2_warn = self._is_tier2_warning(diag)
            status = self._resolve_validation_status(tier1, tier2_warn)

            rows.append({
                "window_start": ws,
                "window_end": we,
                "cagr": m.get("cagr", 0.0),
                "total_return": m.get("total_return", 0.0),
                "max_drawdown": m.get("max_drawdown", 0.0),
                "sharpe_ratio": m.get("sharpe_ratio", 0.0),
                "benchmark_cagr": m.get("benchmark_cagr", 0.0),
                "excess_cagr": m.get("excess_cagr", 0.0),
                "diag_12slot_coverage": diag["coverage"],
                "diag_unknown_ratio": diag["unknown_ratio"],
                "diag_axis_consistency": diag["axis_consistency"],
                "tier1_pass": tier1,
                "tier2_warning": tier2_warn,
                "validation_status": status,
                "preset": config.preset,
                "generated_at": generated_at,
            })

        df = pd.DataFrame(rows, columns=WALK_FORWARD_COLUMNS)
        logger.info("[WalkForward] Done — %d windows", len(df))
        return df

    def _load_ahs_snapshot_for_diagnostics(self) -> Optional[pd.DataFrame]:
        """전역 AHS snapshot를 로드한다. 없으면 None."""
        try:
            df = load_strategy_snapshot(Path("data/strategy"), "axis_horizon_state")
            if df is None or df.empty:
                return None
            if "trade_date" in df.columns:
                df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
            return df
        except Exception:
            return None

    @staticmethod
    def _safe_json(raw) -> Dict:
        import json
        if raw is None:
            return {}
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        return {}

    def _compute_12slot_diagnostics(
        self,
        ahs_df: Optional[pd.DataFrame],
        window_start: date,
        window_end: date,
    ) -> Dict[str, float]:
        """4축×3horizon(12셀) 진단 KPI를 계산한다."""
        if ahs_df is None or ahs_df.empty:
            return {"coverage": float("nan"), "unknown_ratio": float("nan"), "axis_consistency": float("nan")}

        wdf = ahs_df[(ahs_df["trade_date"] >= window_start) & (ahs_df["trade_date"] <= window_end)]
        if wdf.empty:
            return {"coverage": float("nan"), "unknown_ratio": float("nan"), "axis_consistency": float("nan")}

        known = 0
        total = 12 * len(wdf)
        bias_scores: List[float] = []

        for _, row in wdf.iterrows():
            ld = self._safe_json(row.get("long_detail_json"))
            md = self._safe_json(row.get("mid_detail_json"))
            sd = self._safe_json(row.get("short_detail_json"))

            # macro cells
            if ld.get("regime_mode") is not None or ld.get("delta_6m_z_mean") is not None:
                known += 1
            if md.get("macro_signal") is not None:
                known += 1

            # price cells
            if md.get("price_signal") is not None:
                known += 1
            if sd.get("primary_panic") is not None or sd.get("primary_relief") is not None:
                known += 1

            # flow cells
            if md.get("breadth_signal") is not None:
                known += 1
            if (
                sd.get("secondary_confirm_count") is not None
                or sd.get("smallcap_stress") is not None
                or sd.get("secondary_confirmations") is not None
            ):
                known += 1

            # sentiment cell (short only in current impl)
            if sd.get("risk_on_confirm") is not None:
                known += 1

            # 축별 일관성 근사값 계산
            axis_votes: List[int] = []
            macro_sig = md.get("macro_signal")
            if macro_sig == "RISK_ON":
                axis_votes.append(1)
            elif macro_sig == "RISK_OFF":
                axis_votes.append(-1)

            price_sig = md.get("price_signal")
            if price_sig == "RISK_ON":
                axis_votes.append(1)
            elif price_sig == "RISK_OFF":
                axis_votes.append(-1)

            breadth_sig = md.get("breadth_signal")
            if breadth_sig == "RISK_ON":
                axis_votes.append(1)
            elif breadth_sig == "RISK_OFF":
                axis_votes.append(-1)

            roc = sd.get("risk_on_confirm")
            if roc is True:
                axis_votes.append(1)

            if axis_votes:
                pos = sum(1 for v in axis_votes if v > 0)
                neg = sum(1 for v in axis_votes if v < 0)
                bias_scores.append(max(pos, neg) / len(axis_votes))

        coverage = known / total if total > 0 else float("nan")
        unknown_ratio = 1.0 - coverage if total > 0 else float("nan")
        axis_consistency = sum(bias_scores) / len(bias_scores) if bias_scores else float("nan")

        return {
            "coverage": coverage,
            "unknown_ratio": unknown_ratio,
            "axis_consistency": axis_consistency,
        }

    def _is_tier1_pass(self, metrics: Dict[str, float]) -> bool:
        cagr = float(metrics.get("cagr", 0.0))
        sharpe = float(metrics.get("sharpe_ratio", 0.0))
        mdd = float(metrics.get("max_drawdown", 0.0))
        return cagr >= _MIN_CAGR and sharpe >= _MIN_SHARPE and mdd >= _MAX_MDD

    def _is_tier2_warning(self, diag: Dict[str, float]) -> bool:
        cov = diag.get("coverage")
        un = diag.get("unknown_ratio")
        cons = diag.get("axis_consistency")
        # 진단 데이터가 없으면 경고 강제하지 않고 fallback 처리
        if pd.isna(cov) or pd.isna(un) or pd.isna(cons):
            return False
        return cov < _MIN_DIAG_COVERAGE or un > _MAX_UNKNOWN_RATIO or cons < _MIN_AXIS_CONSISTENCY

    @staticmethod
    def _resolve_validation_status(tier1_pass: bool, tier2_warning: bool) -> str:
        if not tier1_pass:
            return "FAIL"
        if tier2_warning:
            return "PASS_WITH_WARNING"
        return "PASS"

    def _generate_windows(
        self, config: WalkForwardConfig
    ) -> List[Tuple[date, date]]:
        """full_start~full_end 를 window_years/step_years 기준으로 분할한다."""
        from dateutil.relativedelta import relativedelta  # type: ignore[import]

        windows = []
        ws = config.full_start
        while True:
            we_candidate = date(
                ws.year + config.window_years,
                ws.month,
                ws.day,
            )
            we = min(we_candidate, config.full_end)
            if we <= ws:
                break
            windows.append((ws, we))
            if we >= config.full_end:
                break
            next_ws = date(ws.year + config.step_years, ws.month, ws.day)
            if next_ws >= config.full_end:
                break
            ws = next_ws

        return windows


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Walk-Forward 기간별 성과 분석 (운영 안정화 검증)"
    )
    parser.add_argument("--preset", default="v2", choices=["v0", "v1", "v2"],
                        help="백테스트 preset (default: v2)")
    parser.add_argument("--window-years", type=int, default=4,
                        help="자동 생성 시 창 크기(년, default: 4)")
    parser.add_argument("--step-years", type=int, default=2,
                        help="자동 생성 시 슬라이드 폭(년, default: 2)")
    parser.add_argument("--windows", nargs="*", metavar="YYYY-YYYY",
                        help="명시적 기간 목록. 예: 2006-2012 2012-2018")
    parser.add_argument("--capital", type=float, default=1000.0,
                        help="초기 자본 (default: 1000.0)")
    parser.add_argument("--save", action="store_true",
                        help="결과를 파일로 저장")
    parser.add_argument("--output-dir", default="data/backtest/reports/walk_forward",
                        help="저장 디렉토리 (default: data/backtest/reports/walk_forward)")
    args = parser.parse_args()

    # 명시적 기간 파싱
    explicit_windows: List[Tuple[date, date]] = []
    if args.windows:
        for w in args.windows:
            start_y, end_y = w.split("-")
            explicit_windows.append((
                date(int(start_y), 1, 3),
                date(int(end_y), 6, 3),
            ))

    config = WalkForwardConfig(
        preset=args.preset,
        windows=explicit_windows,
        window_years=args.window_years,
        step_years=args.step_years,
        initial_capital=args.capital,
    )

    runner = WalkForwardRunner()
    df = runner.run(config)

    # 결과 출력
    from .report import print_walk_forward_summary, save_walk_forward
    print_walk_forward_summary(df)

    if args.save:
        out_dir = Path(args.output_dir)
        saved = save_walk_forward(df, preset=args.preset, base_dir=out_dir)
        print(f"결과 저장 완료: {saved}")


if __name__ == "__main__":
    main()
