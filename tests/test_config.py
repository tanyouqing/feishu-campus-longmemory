from __future__ import annotations

from feishu_campus_longmemory.config import Settings


def test_settings_defaults(monkeypatch) -> None:
    for name in (
        "LONGMEMORY_ENV",
        "LONGMEMORY_HOST",
        "LONGMEMORY_PORT",
        "LONGMEMORY_DATABASE_URL",
        "LONGMEMORY_LOG_LEVEL",
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
