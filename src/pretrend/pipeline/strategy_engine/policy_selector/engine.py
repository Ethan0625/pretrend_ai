"""
Policy Selector Engine — Market Position + Policy Config → Composer 출력.

Registry에서 정책을 resolve하여 Market Position에 정책 파라미터를 부착한다.
Composer 계약의 최종 출력을 생성하는 단계.

SOT: docs/strategy_engine_design.md §A3
Contract:
  - docs/architecture/market_structure_composer_contract.md
  - docs/architecture/policy_config_contract.md

v0: RC_V0_DEFAULT 단일 정책만 사용. resolve 실패 시 fail-fast.
"""
from __future__ import annotations

import logging

import pandas as pd

from ..registries import resolve_policy
from .schema import POLICY_SELECTION_COLUMNS

logger = logging.getLogger(__name__)


def build_policy_selection(
    market_position: pd.DataFrame,
    policy_profile_id: str = "RC_V0_DEFAULT",
    run_id: str = "",
) -> pd.DataFrame:
    """Market Position에 Policy Config를 resolve하여 최종 출력을 생성한다.

    Parameters
    ----------
    market_position : DataFrame
        build_market_position() 출력.
    policy_profile_id : str
        적용할 정책 식별자. 미등록 시 KeyError (fail-fast).
    run_id : str
        Lineage run ID.

    Returns
    -------
    DataFrame with POLICY_SELECTION_COLUMNS.

    Raises
    ------
    KeyError
        policy_profile_id가 POLICY_REGISTRY에 등록되지 않은 경우.
    """
    if market_position.empty:
        logger.warning("[PolicySelector] Empty market position")
        return pd.DataFrame(columns=POLICY_SELECTION_COLUMNS)

    # Resolve policy (fail-fast)
    policy = resolve_policy(policy_profile_id)

    result = market_position.copy()
    result["policy_profile_id"] = policy.policy_profile_id
    result["target_invested_lower"] = policy.target_invested_lower
    result["target_invested_upper"] = policy.target_invested_upper
    result["adjustment_limit"] = policy.adjustment_limit
    result["step_size"] = policy.step_size
    result["policy_version"] = policy.policy_version

    if "source_run_id" not in result.columns:
        result["source_run_id"] = run_id
    else:
        result["source_run_id"] = result["source_run_id"].fillna(run_id)

    # 컬럼 정렬
    for col in POLICY_SELECTION_COLUMNS:
        if col not in result.columns:
            result[col] = None

    result = result[POLICY_SELECTION_COLUMNS]

    logger.info("[PolicySelector] Resolved policy: %s for %d rows",
                policy_profile_id, len(result))
    return result
