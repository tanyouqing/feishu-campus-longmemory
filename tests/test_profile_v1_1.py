from __future__ import annotations

import sqlalchemy as sa
from fastapi.testclient import TestClient

from feishu_campus_longmemory.config import Settings
from feishu_campus_longmemory.main import create_app
from feishu_campus_longmemory.memory.extractor import OpenAICompatibleMemoryCandidateExtractor
from feishu_campus_longmemory.profile.extractor import OpenAICompatibleUserProfilePatchExtractor
from feishu_campus_longmemory.profile.types import UserProfilePatch
from feishu_campus_longmemory.tables import user_profile_evidence_links


def _app_and_client(tmp_path, **settings_overrides):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'profile.db'}",
        ingest_token="test-token",
        log_level="ERROR",
        _env_file=None,
        **settings_overrides,
    )
    app = create_app(settings)
    return app, TestClient(app)


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


def _openclaw_payload(message_id: str, text: str) -> dict:
    return {
        "type": "message",
        "action": "received",
        "sessionKey": "session-1",
        "timestamp": "2026-05-05T12:00:00Z",
        "context": {
            "from": "ou_user",
            "content": text,
            "channelId": "feishu",
            "metadata": {"messageId": message_id, "senderId": "ou_user"},
        },
    }


def _disable_memory_llm(monkeypatch) -> None:
    monkeypatch.setattr(OpenAICompatibleMemoryCandidateExtractor, "extract_candidates", lambda self, text: [])


def test_llm_profile_extractor_writes_profile_and_markdown(tmp_path, monkeypatch) -> None:
    _disable_memory_llm(monkeypatch)

    def fake_extract(self, text: str) -> list[UserProfilePatch]:
        return [
            UserProfilePatch("work_identity", "用户当前负责飞书校园大赛项目", 0.88, "我现在负责飞书校园大赛项目"),
            UserProfilePatch("life_preferences", "用户喜欢清淡饮食", 0.72, "我喜欢清淡饮食"),
        ]

    monkeypatch.setattr(OpenAICompatibleUserProfilePatchExtractor, "extract_patches", fake_extract)
    _, client = _app_and_client(tmp_path, llm_extraction_enabled=True, llm_api_key="test-key")

    with client:
        event = client.post(
            "/events/ingest",
            json=_openclaw_payload("profile_msg_1", "我现在负责飞书校园大赛项目，我喜欢清淡饮食"),
            headers=_headers(),
        )
        profile = client.get("/profile/ou_user", headers=_headers())
        markdown = client.get("/profile/ou_user/markdown", headers=_headers())

    assert event.status_code == 200
    assert profile.status_code == 200
    payload = profile.json()
    assert payload["version"] == 1
    assert payload["last_event_id"] == event.json()["event_id"]
    assert payload["profile_json"]["dimensions"]["work_identity"]["claims"][0]["text"] == "用户当前负责飞书校园大赛项目"
    assert "用户当前负责飞书校园大赛项目" in payload["profile_markdown"]
    assert "用户喜欢清淡饮食" in markdown.json()["profile_markdown"]
    assert event.json()["event_id"] not in payload["profile_markdown"]


def test_profile_extractor_rejects_invalid_sensitive_and_delete_patches(tmp_path, monkeypatch) -> None:
    _disable_memory_llm(monkeypatch)

    def fake_extract(self, text: str) -> list[UserProfilePatch]:
        return [
            UserProfilePatch("unknown", "用户负责项目", 0.8, "我负责项目"),
            UserProfilePatch("work_identity", "用户邮箱是 someone@example.com", 0.8, "我负责项目"),
            UserProfilePatch("work_identity", "用户负责项目", 0.8, "不存在的证据"),
        ]

    monkeypatch.setattr(OpenAICompatibleUserProfilePatchExtractor, "extract_patches", fake_extract)
    _, client = _app_and_client(tmp_path, llm_extraction_enabled=True, llm_api_key="test-key")

    with client:
        client.post("/events/ingest", json=_openclaw_payload("profile_invalid_1", "我负责项目"), headers=_headers())
        rejected = client.get("/profile/ou_user", headers=_headers())
        client.post("/events/ingest", json=_openclaw_payload("profile_delete_1", "忘记我负责项目"), headers=_headers())
        delete_rejected = client.get("/profile/ou_user", headers=_headers())

    assert rejected.status_code == 404
    assert delete_rejected.status_code == 404


def test_profile_store_deduplicates_claims_and_links_evidence(tmp_path, monkeypatch) -> None:
    _disable_memory_llm(monkeypatch)

    def fake_extract(self, text: str) -> list[UserProfilePatch]:
        return [UserProfilePatch("current_work_stage", "用户正在推进用户建模版本", 0.8, "我正在推进用户建模版本")]

    monkeypatch.setattr(OpenAICompatibleUserProfilePatchExtractor, "extract_patches", fake_extract)
    app, client = _app_and_client(tmp_path, llm_extraction_enabled=True, llm_api_key="test-key")

    with client:
        first = client.post(
            "/events/ingest",
            json=_openclaw_payload("profile_dup_1", "我正在推进用户建模版本"),
            headers=_headers(),
        )
        second = client.post(
            "/events/ingest",
            json=_openclaw_payload("profile_dup_2", "我正在推进用户建模版本"),
            headers=_headers(),
        )
        profile = client.get("/profile/ou_user", headers=_headers())

    claims = profile.json()["profile_json"]["dimensions"]["current_work_stage"]["claims"]
    assert len(claims) == 1
    assert profile.json()["version"] == 1
    with app.state.db_engine.connect() as connection:
        linked_events = connection.execute(
            sa.select(user_profile_evidence_links.c.event_id).where(user_profile_evidence_links.c.user_id == "ou_user")
        ).scalars().all()
    assert sorted(linked_events) == sorted([first.json()["event_id"], second.json()["event_id"]])


def test_context_build_combines_profile_and_memory_without_internal_ids(tmp_path, monkeypatch) -> None:
    _disable_memory_llm(monkeypatch)

    def fake_extract(self, text: str) -> list[UserProfilePatch]:
        return [UserProfilePatch("communication_style", "用户偏好简洁直接", 0.86, "我偏好简洁直接")]

    monkeypatch.setattr(OpenAICompatibleUserProfilePatchExtractor, "extract_patches", fake_extract)
    _, client = _app_and_client(tmp_path, llm_extraction_enabled=True, llm_api_key="test-key")

    with client:
        evidence = client.post(
            "/events/ingest",
            json=_openclaw_payload("profile_context_1", "我偏好简洁直接"),
            headers=_headers(),
        )
        memory = client.post(
            "/memory/write",
            json={
                "user_id": "ou_user",
                "memory_category": "WorkPreferenceMemory",
                "work_type": "weekly_report",
                "content_json": {"summary": "周报先写结论", "normalized_key": "weekly_report:profile_context"},
                "evidence_event_ids": [evidence.json()["event_id"]],
            },
            headers=_headers(),
        )
        context = client.post(
            "/context/build",
            json={"user_id": "ou_user", "query": "帮我写周报", "limit": 5},
            headers=_headers(),
        )

    assert memory.status_code == 200
    assert context.status_code == 200
    pack = context.json()["context_pack"]
    assert "User Profile Context" in pack
    assert "用户偏好简洁直接" in pack
    assert "Memory Context Pack" in pack
    assert "周报先写结论" in pack
    assert context.json()["profile_included"] is True
    assert memory.json()["memory_id"] not in pack
    assert evidence.json()["event_id"] not in pack


def test_profile_api_requires_token(tmp_path) -> None:
    _, client = _app_and_client(tmp_path)

    with client:
        response = client.get("/profile/ou_user")

    assert response.status_code == 401
