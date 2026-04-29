from __future__ import annotations

import hashlib
import json

from fastapi.testclient import TestClient

from feishu_campus_longmemory.config import Settings
from feishu_campus_longmemory.main import create_app


def _client(tmp_path) -> TestClient:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'feishu.db'}",
        ingest_token="test-token",
        feishu_verification_token="verify-token",
        feishu_encrypt_key="encrypt-key",
        log_level="ERROR",
        _env_file=None,
    )
    app = create_app(settings)
    return TestClient(app)


def test_feishu_url_verification_uses_official_sdk_path(tmp_path) -> None:
    payload = {
        "schema": "2.0",
        "header": {
            "event_id": "evt_verify",
            "event_type": "url_verification",
            "create_time": "1714118400000",
            "token": "verify-token",
        },
        "challenge": "challenge-code",
    }

    with _client(tmp_path) as client:
        response = client.post("/integrations/feishu/events", json=payload)

    assert response.status_code == 200
    assert response.json() == {"challenge": "challenge-code"}


def test_feishu_message_event_is_stored_as_work_event(tmp_path) -> None:
    payload = {
        "schema": "2.0",
        "header": {
            "event_id": "evt_message",
            "event_type": "im.message.receive_v1",
            "create_time": "1714118400000",
            "token": "verify-token",
            "tenant_key": "tenant_1",
        },
        "event": {
            "sender": {
                "sender_id": {"open_id": "ou_feishu_user"},
                "sender_type": "user",
                "tenant_key": "tenant_1",
            },
            "message": {
                "message_id": "om_feishu_1",
                "create_time": 1714118400000,
                "chat_id": "oc_chat",
                "chat_type": "p2p",
                "message_type": "text",
                "content": "{\"text\":\"hello from feishu\"}",
            },
        },
    }
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = _feishu_signature_headers(body)

    with _client(tmp_path) as client:
        response = client.post("/integrations/feishu/events", content=body, headers=headers)
        listed = client.get(
            "/events",
            params={"source": "feishu", "event_type": "im.message.receive_v1"},
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    assert response.json() == {"msg": "success"}
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    event = listed.json()[0]
    assert event["user_id"] == "ou_feishu_user"
    assert event["tenant_id"] == "tenant_1"
    assert event["object_id"] == "om_feishu_1"
    assert event["content_json"]["summary"]["text"] == "hello from feishu"


def _feishu_signature_headers(body: bytes) -> dict[str, str]:
    timestamp = "1714118400"
    nonce = "nonce"
    signature = hashlib.sha256((timestamp + nonce + "encrypt-key").encode("utf-8") + body).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-Lark-Request-Timestamp": timestamp,
        "X-Lark-Request-Nonce": nonce,
        "X-Lark-Signature": signature,
    }
