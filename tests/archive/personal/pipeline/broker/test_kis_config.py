from __future__ import annotations

import pytest

from pretrend.pipeline.broker.kis_config import KISConfig


def test_kis_config_prefers_mock_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KIS_IS_MOCK", "true")
    monkeypatch.setenv("KIS_MOCK_APP_KEY", "mock_key")
    monkeypatch.setenv("KIS_MOCK_APP_SECRET", "mock_secret")
    monkeypatch.setenv("KIS_MOCK_ACCOUNT_NO", "11111111")
    monkeypatch.setenv("KIS_MOCK_PRODUCT_CODE", "01")
    cfg = KISConfig.from_env()
    assert cfg.is_mock is True
    assert cfg.app_key == "mock_key"
    assert cfg.app_secret == "mock_secret"
    assert cfg.account_no == "11111111"


def test_kis_config_fallback_legacy_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KIS_IS_MOCK", "true")
    monkeypatch.delenv("KIS_MOCK_APP_KEY", raising=False)
    monkeypatch.delenv("KIS_MOCK_APP_SECRET", raising=False)
    monkeypatch.delenv("KIS_MOCK_ACCOUNT_NO", raising=False)
    monkeypatch.setenv("KIS_APP_KEY", "legacy_key")
    monkeypatch.setenv("KIS_APP_SECRET", "legacy_secret")
    monkeypatch.setenv("KIS_ACCOUNT_NO", "22222222")
    cfg = KISConfig.from_env()
    assert cfg.app_key == "legacy_key"
    assert cfg.app_secret == "legacy_secret"
    assert cfg.account_no == "22222222"


def test_kis_config_missing_required_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KIS_IS_MOCK", "true")
    monkeypatch.delenv("KIS_MOCK_APP_KEY", raising=False)
    monkeypatch.delenv("KIS_MOCK_APP_SECRET", raising=False)
    monkeypatch.delenv("KIS_MOCK_ACCOUNT_NO", raising=False)
    monkeypatch.delenv("KIS_APP_KEY", raising=False)
    monkeypatch.delenv("KIS_APP_SECRET", raising=False)
    monkeypatch.delenv("KIS_ACCOUNT_NO", raising=False)
    with pytest.raises(ValueError):
        KISConfig.from_env()

