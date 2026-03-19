from __future__ import annotations

import pytest

from pretrend.pipeline.paper.report import (
    PAPER_RESULT_REQUIRED_FIELDS,
    build_paper_result_payload,
    validate_paper_result_payload,
)


def _minimal_payload() -> dict:
    return build_paper_result_payload(
        source_job="paper_trading_dag",
        decision_date="2026-02-27",
        simulation_date="2026-02-27",
        action="HOLD",
        next_invested_ratio=0.4,
        delta_ratio=0.0,
    )


def test_validate_paper_result_payload_required_fields() -> None:
    payload = _minimal_payload()

    for field in PAPER_RESULT_REQUIRED_FIELDS:
        assert field in payload

    validate_paper_result_payload(payload)


def test_build_paper_result_payload_minimal() -> None:
    payload = _minimal_payload()

    assert payload["message_type"] == "PAPER_RESULT"
    assert payload["source_job"] == "paper_trading_dag"
    assert payload["sell_tranches"] == [0.50, 0.30, 0.20]
    assert payload["schd_sell_locked"] is True


def test_validate_paper_result_payload_missing_field_raises() -> None:
    payload = _minimal_payload()
    payload.pop("action")

    with pytest.raises(ValueError, match="missing required fields"):
        validate_paper_result_payload(payload)


def test_paper_result_payload_enum_values() -> None:
    for action in ["INCREASE", "DECREASE", "HOLD"]:
        payload = build_paper_result_payload(
            source_job="paper_trading_dag",
            decision_date="2026-02-27",
            simulation_date="2026-02-27",
            action=action,
            next_invested_ratio=0.5,
            delta_ratio=0.1,
            effective_bias="RISK_OFF_BIAS",
        )
        validate_paper_result_payload(payload)
        assert payload["action"] == action
        assert payload["effective_bias"] == "RISK_OFF_BIAS"
