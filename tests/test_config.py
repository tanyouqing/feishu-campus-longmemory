from __future__ import annotations

from feishu_campus_longmemory.config import Settings


def test_settings_defaults(monkeypatch) -> None:
    for name in (
        "LONGMEMORY_ENV",
        "LONGMEMORY_HOST",
        "LONGMEMORY_PORT",
        "LONGMEMORY_DATABASE_URL",
        "LONGMEMORY_LOG_LEVEL",
        "LONGMEMORY_LLM_EXTRACTION_ENABLED",
        "LONGMEMORY_LLM_BASE_URL",
        "LONGMEMORY_LLM_MODEL",
        "LONGMEMORY_LLM_API_KEY",
        "LONGMEMORY_LLM_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)

    assert settings.env == "local"
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.database_url == "sqlite:///./data/longmemory.db"
    assert settings.log_level == "INFO"
    assert settings.ingest_token is None
    assert settings.feishu_verification_token is None
    assert settings.feishu_encrypt_key is None
    assert settings.llm_extraction_enabled is False
    assert settings.llm_base_url == "https://ark.cn-beijing.volces.com/api/v3"
    assert settings.llm_model == "doubao-seed-2-0-lite-260215"
    assert settings.llm_api_key is None
    assert settings.llm_timeout_seconds == 10
