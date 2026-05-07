from __future__ import annotations

from fastapi.testclient import TestClient

from feishu_campus_longmemory.config import Settings
from feishu_campus_longmemory.main import create_app


def test_health_returns_ok(tmp_path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'health.db'}",
        log_level="ERROR",
        _env_file=None,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "feishu-campus-longmemory",
        "version": "1.1.0",
        "database": "ok",
    }
