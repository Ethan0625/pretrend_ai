"""
Backtest 공통 유틸리티.

현재 위치: pipeline/backtest/_utils.py
승격 정책: 여러 pipeline에서 재사용 확인 시 src/pretrend/utils/ 로 이전.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


def load_strategy_snapshot(
    root: Path,
    stage_name: str,
) -> Optional[pd.DataFrame]:
    """Strategy Engine 스냅샷 parquet를 로드한다.

    Hive 파티션 경로(`decision_date=YYYY-MM-DD/`)에서 decision_date를 추출해
    DataFrame 컬럼으로 복원한다. trade_date / rebalance_date / decision_date는
    모두 Python date 타입으로 정규화된다.

    Parameters
    ----------
    root : Path
        Strategy 루트 디렉토리 (예: data/strategy/).
    stage_name : str
        스테이지 이름 (예: "policy_selection", "what_to_hold").

    Returns
    -------
    DataFrame or None
        스냅샷 데이터. 파일이 없으면 None.
    """
    stage_root = root / stage_name
    if not stage_root.exists():
        logger.warning("[load_strategy_snapshot] No snapshot dir: %s", stage_root)
        return None

    files = list(stage_root.rglob("*.parquet"))
    if not files:
        return None

    frames = []
    for f in files:
        chunk = pd.read_parquet(f)
        # decision_date 컬럼이 없으면 Hive 파티션 경로에서 복원
        if "decision_date" not in chunk.columns:
            dd_str = next(
                (part.split("=", 1)[1] for part in f.parts if part.startswith("decision_date=")),
                None,
            )
            chunk["decision_date"] = dd_str
        frames.append(chunk)

    df = pd.concat(frames, ignore_index=True)

    # trade_date, rebalance_date, decision_date → date 타입 정규화
    for col in ("trade_date", "rebalance_date", "decision_date"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col]).dt.date

    return df
