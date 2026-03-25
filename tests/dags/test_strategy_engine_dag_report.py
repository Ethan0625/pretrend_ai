from __future__ import annotations

from pretrend.pipeline.strategy_engine.report_delivery import (
    compose_strategy_report_messages,
)


def test_compose_strategy_report_messages_returns_single_message_when_short() -> None:
    main_lines = [
        "📊 <b>Pretrend</b>",
        "── 시장 컨텍스트 ──",
        "EXPANSION / RISK_ON / STABLE",
        "── 핵심 판단 해석 ──",
        "핵심 판단과 해석",
    ]
    support_lines = [
        "── 보조 운영 정보 ──",
        "다음 스텝",
        "시장 근거",
    ]

    messages = compose_strategy_report_messages(main_lines, support_lines)

    assert len(messages) == 1
    assert "핵심 판단 해석" in messages[0]
    assert "보조 운영 정보" in messages[0]


def test_compose_strategy_report_messages_splits_main_and_support_when_long() -> None:
    main_lines = [
        "📊 <b>Pretrend</b>",
        "── 시장 컨텍스트 ──",
        "핵심 판단" * 300,
        "── 핵심 판단 해석 ──",
        "AI 해석" * 300,
    ]
    support_lines = [
        "── 보조 운영 정보 ──",
        "다음 스텝" * 200,
        "시장 근거" * 200,
    ]

    messages = compose_strategy_report_messages(main_lines, support_lines)

    assert len(messages) == 2
    assert "핵심 판단 해석" in messages[0]
    assert "보조 운영 정보" not in messages[0]
    assert "보조 운영 정보" in messages[1]


def test_compose_strategy_report_messages_returns_main_only_when_support_empty() -> None:
    main_lines = ["📊 <b>Pretrend</b>", "핵심 판단 + AI 해석"]

    messages = compose_strategy_report_messages(main_lines, [])

    assert messages == ["📊 <b>Pretrend</b>\n핵심 판단 + AI 해석"]
