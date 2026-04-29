from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from feishu_campus_longmemory import __version__


class Settings(BaseSettings):
    service_name: str = "feishu-campus-longmemory"
    version: str = __version__
    env: str = "local"
    host: str = "127.0.0.1"
    port: int = 8000
    database_url: str = "sqlite:///./data/longmemory.db"
    log_level: str = Field(default="INFO", pattern=r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    ingest_token: str | None = None
    feishu_verification_token: str | None = None
    feishu_encrypt_key: str | None = None
    feishu_app_id: str | None = None
    feishu_app_secret: str | None = None
    feishu_domain: str = Field(default="feishu", pattern=r"^(feishu|lark)$")
    feishu_default_receive_id_type: str = "open_id"
    reminder_scheduler_enabled: bool = False
    reminder_poll_interval_seconds: int = Field(default=30, ge=1, le=3600)
    reminder_batch_size: int = Field(default=10, ge=1, le=100)

    model_config = SettingsConfigDict(
        env_prefix="LONGMEMORY_",
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
