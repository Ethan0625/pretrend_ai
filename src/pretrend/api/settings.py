from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from pretrend.config import Settings as DBSettings
from pretrend.config import get_settings as get_db_settings


class APISettings(BaseSettings):
    api_key: str = Field(alias="PRETREND_API_KEY")
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        alias="PRETREND_API_CORS_ORIGINS",
    )
    trusted_hosts: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["*"],
        alias="PRETREND_API_TRUSTED_HOSTS",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @field_validator("cors_origins", "trusted_hosts", mode="before")
    @classmethod
    def _parse_csv_list(cls, value: object) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, list):
            return value
        return [str(value)]

    @property
    def db(self) -> DBSettings:
        return get_db_settings()


@lru_cache
def get_api_settings() -> APISettings:
    return APISettings()
