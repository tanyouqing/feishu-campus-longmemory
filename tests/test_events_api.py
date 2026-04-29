from __future__ import annotations

from fastapi.testclient import TestClient

from feishu_campus_longmemory.config import Settings
from feishu_campus_longmemory.main import create_app


def _client(tmp_path) -> TestClient:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'events.db'}",
        ingest_token="test-token",
        log_level="ERROR",
        _env_file=None,
    )
    app = create_app(settings)
    return TestClient(app)


def test_openclaw_ingest_deduplicates_and_queries_events(tmp_path) -> None:
    payload = {
        "type": "message",
        "action": "received",
        "sessionKey": "session-1",
        "timestamp": "2026-04-26T12:00:00Z",
        "context": {
            "from": "ou_sender",
            "content": "hello token=abc123456789",
            "channelId": "feishu",
            "metadata": {
                "messageId": "om_openclaw_1",
                "senderId": "ou_sender",
            },
        },
    }

    with _client(tmp_path) as client:
        headers = {"Authorization": "Bearer test-token"}
        first = client.post("/events/ingest", json=payload, headers=headers)
        second = client.post("/events/ingest", json=payload, headers=headers)
        listed = client.get("/events", params={"source": "openclaw", "user_id": "ou_sender"}, headers=headers)

    assert first.status_code == 200
    assert first.json()["created"] is True
    assert first.json()["event"]["privacy_level"] == "sensitive"
    assert "token=[REDACTED_SECRET]" in first.json()["event"]["content_json"]["summary"]["text"]

    assert second.status_code == 200
    assert second.json()["created"] is False
    assert second.json()["event_id"] == first.json()["event_id"]

    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["event_id"] == first.json()["event_id"]


def test_events_require_ingest_token(tmp_path) -> None:
    payload = {
        "type": "message",
        "action": "received",
        "sessionKey": "session-1",
        "context": {"from": "ou_sender", "content": "hello"},
    }

    with _client(tmp_path) as client:
        ingested = client.post("/events/ingest", json=payload)
        listed = client.get("/events")

    assert ingested.status_code == 401
    assert listed.status_code == 401


def test_events_return_configuration_error_without_ingest_token(tmp_path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'no-token.db'}",
        log_level="ERROR",
        _env_file=None,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        response = client.get("/events")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ingest_token_not_configured"

