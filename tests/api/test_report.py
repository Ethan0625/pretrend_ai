from __future__ import annotations

import pytest

from pretrend.api.routers.report import analyze_strategy_report
from pretrend.api.schemas import StrategyReportAnalyzeRequest


@pytest.mark.anyio
async def test_strategy_report_analyze_uses_api_runtime(
    async_client,
    api_headers,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    def _fake_generate(payload, *, model: str, base_url: str, timeout: int):
        calls.append(
            {
                "payload": payload,
                "model": model,
                "base_url": base_url,
                "timeout": timeout,
            }
        )
        return "analysis text"

    monkeypatch.setattr(
        "pretrend.api.routers.report.generate_llm_analysis",
        _fake_generate,
    )

    response = await async_client.post(
        "/api/v1/report/strategy/analyze",
        headers=api_headers,
        json={
            "payload": {"decision_date": "2026-05-14"},
            "model": "test-model",
            "base_url": "http://llm.local",
            "timeout": 12,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"analysis_text": "analysis text"}
    assert calls == [
        {
            "payload": {"decision_date": "2026-05-14"},
            "model": "test-model",
            "base_url": "http://llm.local",
            "timeout": 12,
        }
    ]


@pytest.mark.anyio
async def test_ofs_003_strategy_report_analyze_sanitizes_non_finite_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OFS-003: report API는 NaN/Inf payload를 provider 호출 전에 null로 낮춘다."""
    calls: list[dict] = []

    def _fake_generate(payload, *, model: str, base_url: str, timeout: int):
        calls.append(payload)
        return None

    monkeypatch.setattr(
        "pretrend.api.routers.report.generate_llm_analysis",
        _fake_generate,
    )

    response = await analyze_strategy_report(
        StrategyReportAnalyzeRequest(
            payload={
                "decision_date": "2026-05-14",
                "relative_strength": float("nan"),
                "bad": float("inf"),
            }
        )
    )

    assert response.analysis_text is None
    assert calls == [
        {
            "decision_date": "2026-05-14",
            "relative_strength": None,
            "bad": None,
        }
    ]


@pytest.mark.anyio
async def test_ofs_003_strategy_report_analyze_fail_open_on_provider_error(
    async_client,
    api_headers,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OFS-003: provider/analyzer 예외는 보고서 API 500이 아니라 analysis_text=null이다."""

    def _raise(*_args, **_kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(
        "pretrend.api.routers.report.generate_llm_analysis",
        _raise,
    )

    response = await async_client.post(
        "/api/v1/report/strategy/analyze",
        headers=api_headers,
        json={"payload": {"decision_date": "2026-05-14"}},
    )

    assert response.status_code == 200
    assert response.json() == {"analysis_text": None}


@pytest.mark.anyio
async def test_strategy_report_analyze_requires_api_key(async_client) -> None:
    response = await async_client.post(
        "/api/v1/report/strategy/analyze",
        json={"payload": {}},
    )

    assert response.status_code == 401


@pytest.mark.anyio
async def test_explainability_analyze_uses_codex_analyzer_endpoint(
    async_client,
    api_headers,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    def _fake_generate_json(*, system_prompt: str, user_prompt: str, timeout: int):
        calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "timeout": timeout,
            }
        )
        return '{"query_date":"2026-05-14"}'

    monkeypatch.setattr(
        "pretrend.api.routers.report.generate_json_via_analyzer",
        _fake_generate_json,
    )

    response = await async_client.post(
        "/api/v1/report/explainability/analyze",
        headers=api_headers,
        json={
            "system_prompt": "system",
            "user_prompt": "user",
            "timeout": 12,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"raw_text": '{"query_date":"2026-05-14"}'}
    assert calls == [
        {
            "system_prompt": "system",
            "user_prompt": "user",
            "timeout": 12,
        }
    ]


@pytest.mark.anyio
async def test_explainability_analyze_requires_api_key(async_client) -> None:
    response = await async_client.post(
        "/api/v1/report/explainability/analyze",
        json={"system_prompt": "system", "user_prompt": "user"},
    )

    assert response.status_code == 401
