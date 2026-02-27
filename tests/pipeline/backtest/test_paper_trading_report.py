from __future__ import annotations

import pytest

from pretrend.pipeline.backtest.paper_trading_report import (
    PAPER_RESULT_REQUIRED_FIELDS,
    build_paper_result_payload,
    format_paper_result_message,
    validate_paper_result_payload,
)
from pretrend.pipeline.paper.report import save_paper_result_payload
from pretrend.pipeline.utils.result_registry import query_registry


def test_build_payload_contains_required_fields() -> None:
    payload = build_paper_result_payload(
        source_job="paper_trading_dag",
        decision_date="2026-02-25",
        simulation_date="2026-02-25",
        action="INCREASE",
        next_invested_ratio=0.8,
        delta_ratio=0.1,
    )
    for key in PAPER_RESULT_REQUIRED_FIELDS:
        assert key in payload
    assert payload["message_type"] == "PAPER_RESULT"
    assert payload["initial_capital"] == 1_000_000.0
    assert payload["monthly_addition"] == 300_000.0
    assert payload["schd_sell_locked"] is True


def test_format_message_includes_fixed_sections_and_fallbacks() -> None:
    payload = build_paper_result_payload(
        source_job="paper_trading_dag",
        decision_date="2026-02-25",
        simulation_date="2026-02-25",
        action="HOLD",
        next_invested_ratio=0.6,
        delta_ratio=0.0,
        virtual_fills=["체결 없음 (HOLD)"],
        daily_pnl=None,
        cumulative_pnl=None,
        nav=None,
        total_invested_capital=None,
        top_positions=[],
        position_changes=[],
        risk_warnings=[],
    )
    msg = format_paper_result_message(payload)
    assert "message_type=PAPER_RESULT" in msg
    assert "가상 체결 요약" in msg
    assert "PnL 요약" in msg
    assert "운영 조건" in msg
    assert "Paper 시작일: N/A" in msg
    assert "초기자금: 1,000,000원" in msg
    assert "월 첫 거래일 DCA: 300,000원" in msg
    assert "환산환율: 1 USD = 1,300 KRW" in msg
    assert "SCHD 매도: 금지" in msg
    assert "당일: 집계 데이터 없음" in msg
    assert "누적: 집계 데이터 없음" in msg
    assert "NAV: 집계 데이터 없음" in msg
    assert "총투입원금: 집계 데이터 없음" in msg
    assert "포지션 변화 없음" in msg


def test_format_message_renders_top_positions() -> None:
    payload = build_paper_result_payload(
        source_job="paper_trading_dag",
        decision_date="2026-02-25",
        simulation_date="2026-02-25",
        action="INCREASE",
        next_invested_ratio=0.7,
        delta_ratio=0.1,
        nav=1_250_000.0,
        total_invested_capital=1_300_000.0,
        top_positions=[
            {
                "symbol": "SPY",
                "shares": 10.0,
                "avg_cost": 100.0,
                "eod_price": 102.0,
                "market_value": 1020.0,
                "gain_pct": 0.02,
            }
        ],
    )
    msg = format_paper_result_message(payload)
    assert "상위 보유 종목" in msg
    assert "SPY 10.00주" in msg
    assert "평단 $100.00" in msg
    assert "현재가 $102.00" in msg
    assert "손익 +2.0%" in msg


def test_format_message_includes_gate_and_strength_section() -> None:
    payload = build_paper_result_payload(
        source_job="paper_trading_dag",
        decision_date="2026-02-25",
        simulation_date="2026-02-25",
        action="INCREASE",
        next_invested_ratio=0.7,
        delta_ratio=0.1,
        effective_bias="RISK_OFF_BIAS",
        bias_source="OVERRIDE",
        override_reason="PANIC",
        bias_state_source="OVERLAY",
        bias_switch_flag=True,
        bias_switch_reason="SHORT_PANIC",
        bias_cooldown_left=3,
        cooldown_compressed_flag=True,
        cooldown_compressed_reason="RELIEF_STREAK",
        hard_gate_exit_assist_flag=True,
        hard_gate_exit_assist_reason="RUN_UNIVERSE_RECOVERY_RELIEF",
        hard_gate_run_universe=False,
        hard_gate_risk_gate=True,
        effective_max_tactical_slots=0,
        effective_tactical_weight=0.0,
        hazard_10d=0.88,
        group_gate_applied_groups=["BOND", "SECTOR"],
        group_gate_reduced_groups=["COMMODITY"],
        group_gate_source="SNAPSHOT",
        fx_usdkrw=1400,
        paper_start_date="2026-01-01",
    )
    msg = format_paper_result_message(payload)
    assert "게이트/강도" in msg
    assert "적용 Bias: RISK_OFF_BIAS (source=OVERRIDE)" in msg
    assert "Override 사유: PANIC" in msg
    assert "Bias 상태: source=OVERLAY, switch=Y, reason=SHORT_PANIC, cooldown=3" in msg
    assert "Cooldown 압축: Y (reason=RELIEF_STREAK)" in msg
    assert "Hard-gate Exit Assist: Y (reason=RUN_UNIVERSE_RECOVERY_RELIEF)" in msg
    assert "run_universe=제한" in msg
    assert "risk_gate=허용" in msg
    assert "전술 강도: slots=0, weight=0.00x" in msg
    assert "10D 전환위험: +88.0%" in msg
    assert "전술 적용 근거" in msg
    assert "적용 그룹: BOND, SECTOR" in msg
    assert "축소 그룹: COMMODITY" in msg
    assert "그룹 게이트 소스: SNAPSHOT" in msg
    assert "환산환율: 1 USD = 1,400 KRW" in msg
    assert "Paper 시작일: 2026-01-01" in msg


def test_format_message_gate_section_fallback_unknown() -> None:
    payload = build_paper_result_payload(
        source_job="paper_trading_dag",
        decision_date="2026-02-25",
        simulation_date="2026-02-25",
        action="HOLD",
        next_invested_ratio=0.6,
        delta_ratio=0.0,
    )
    msg = format_paper_result_message(payload)
    assert "적용 Bias: UNKNOWN (source=UNKNOWN)" in msg
    assert "Bias 상태: source=UNKNOWN, switch=N, reason=UNKNOWN, cooldown=N/A" in msg
    assert "run_universe=UNKNOWN" in msg
    assert "risk_gate=UNKNOWN" in msg
    assert "전술 강도: slots=N/A, weight=N/A" in msg
    assert "10D 전환위험: N/A" in msg
    assert "적용 그룹: N/A" in msg
    assert "축소 그룹: 없음" in msg
    assert "그룹 게이트 소스: UNKNOWN" in msg


def test_validate_payload_raises_when_required_missing() -> None:
    with pytest.raises(ValueError):
        validate_paper_result_payload({"message_type": "PAPER_RESULT"})


def test_save_paper_result_payload_writes_registry(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PRETREND_RESULT_ROOT", str(tmp_path / "result"))
    payload = build_paper_result_payload(
        source_job="paper_trading_dag",
        decision_date="2026-02-25",
        simulation_date="2026-02-25",
        action="HOLD",
        next_invested_ratio=0.6,
        delta_ratio=0.0,
        daily_pnl=0.01,
        cumulative_pnl=0.05,
        nav=1_100_000.0,
    )
    out = save_paper_result_payload(payload)
    assert out.exists()
    reg = query_registry(tmp_path / "result" / "backtest" / "registry", pipeline="paper")
    assert not reg.empty
