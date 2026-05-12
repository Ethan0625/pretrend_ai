from __future__ import annotations

import pytest
from pydantic import ValidationError

from pretrend.config import Settings, get_settings


def _set_required_env(monkeypatch: pytest.MonkeyPatch, *, app_env: str = "dev") -> None:
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv("POSTGRES_HOST", "localhost")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_USER", "pretrend")
    monkeypatch.setenv("POSTGRES_PASSWORD", "pretrend_dev")
    monkeypatch.setenv("POSTGRES_DB", "pretrend_obs")


def test_settings_load_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required_env(monkeypatch)

    settings = Settings(_env_file=None)

    assert settings.app_env == "dev"
    assert settings.database_url == "postgresql+psycopg2://pretrend:pretrend_dev@localhost:5432/pretrend_obs"
    assert settings.database_url_async == "postgresql+asyncpg://pretrend:pretrend_dev@localhost:5432/pretrend_obs"
    assert settings.postgres_host == "localhost"
    assert settings.postgres_port == 5432


def test_settings_require_postgres_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POSTGRES_HOST", raising=False)
    monkeypatch.delenv("POSTGRES_PORT", raising=False)
    monkeypatch.delenv("POSTGRES_USER", raising=False)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    monkeypatch.delenv("POSTGRES_DB", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_get_settings_returns_cached_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    _set_required_env(monkeypatch)

    first = get_settings()
    second = get_settings()

    assert first is second
    get_settings.cache_clear()


def test_settings_support_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required_env(monkeypatch, app_env="test")

    settings = Settings(_env_file=None)

    assert settings.app_env == "test"
