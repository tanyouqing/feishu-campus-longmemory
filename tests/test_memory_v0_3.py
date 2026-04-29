from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from feishu_campus_longmemory.config import Settings
from feishu_campus_longmemory.main import create_app
from feishu_campus_longmemory.memory.store import MemoryStore


def _app_and_client(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'memory.db'}",
        ingest_token="test-token",
        log_level="ERROR",
        _env_file=None,
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
        "timestamp": "2026-04-26T12:00:00Z",
        "context": {
            "from": "ou_user",
            "content": text,
            "channelId": "feishu",
            "metadata": {"messageId": message_id, "senderId": "ou_user"},
        },
    }


def test_openclaw_event_auto_extracts_work_preference_and_evidence_link(tmp_path) -> None:
    app, client = _app_and_client(tmp_path)

    with client:
        response = client.post(
            "/events/ingest",
            json=_openclaw_payload("msg_pref_1", "以后我的周报先写结论，再写风险"),
            headers=_headers(),
        )
        memories = MemoryStore(app.state.db_engine).list_memories("ou_user")
        detail = MemoryStore(app.state.db_engine).get_memory_detail(memories[0]["memory_id"])

    assert response.status_code == 200
    assert len(memories) == 1
    assert memories[0]["memory_category"] == "WorkPreferenceMemory"
    assert memories[0]["work_type"] == "weekly_report"
    assert memories[0]["status"] == "active"
    assert "周报先写结论" in memories[0]["content_json"]["summary"]
    assert detail is not None
    assert detail["evidence_event_ids"] == [response.json()["event_id"]]


def test_openclaw_event_auto_extracts_reminder_and_job(tmp_path) -> None:
    app, client = _app_and_client(tmp_path)

    with client:
        response = client.post(
            "/events/ingest",
            json=_openclaw_payload("msg_reminder_1", "每周五上午提醒我写周报"),
            headers=_headers(),
        )
        memories = MemoryStore(app.state.db_engine).list_memories("ou_user")
        detail = MemoryStore(app.state.db_engine).get_memory_detail(memories[0]["memory_id"])

    assert response.status_code == 200
    assert len(memories) == 1
    assert memories[0]["memory_category"] == "ReminderPreferenceMemory"
    assert detail is not None
    assert len(detail["reminder_jobs"]) == 1
    assert detail["reminder_jobs"][0]["schedule_type"] == "weekly"
    assert detail["reminder_jobs"][0]["status"] == "active"


def test_duplicate_event_does_not_duplicate_memory(tmp_path) -> None:
    app, client = _app_and_client(tmp_path)
    payload = _openclaw_payload("msg_pref_dup", "以后我的周报先写结论，再写风险")

    with client:
        first = client.post("/events/ingest", json=payload, headers=_headers())
        second = client.post("/events/ingest", json=payload, headers=_headers())
        memories = MemoryStore(app.state.db_engine).list_memories("ou_user")

    assert first.json()["created"] is True
    assert second.json()["created"] is False
    assert len(memories) == 1


def test_memory_write_update_get_and_forget(tmp_path) -> None:
    _, client = _app_and_client(tmp_path)

    with client:
        evidence = client.post(
            "/events/ingest",
            json=_openclaw_payload("msg_api_evidence", "真实 OpenClaw tool call evidence"),
            headers=_headers(),
        )
        write = client.post(
            "/memory/write",
            json={
                "user_id": "ou_user",
                "memory_category": "WorkPreferenceMemory",
                "work_type": "weekly_report",
                "content_json": {"summary": "周报使用三段式", "normalized_key": "weekly_report:preference"},
                "evidence_event_ids": [evidence.json()["event_id"]],
            },
            headers=_headers(),
        )
        memory_id = write.json()["memory_id"]
        update = client.post(
            "/memory/update",
            json={
                "memory_id": memory_id,
                "content_json": {"summary": "周报先结论后风险", "normalized_key": "weekly_report:preference"},
                "confidence": 0.95,
            },
            headers=_headers(),
        )
        detail = client.get(f"/memory/{memory_id}", headers=_headers())
        forget = client.post("/memory/forget", json={"memory_id": memory_id}, headers=_headers())
        deleted_detail = client.get(f"/memory/{memory_id}", headers=_headers())

    assert write.status_code == 200
    assert write.json()["created"] is True
    assert update.status_code == 200
    assert update.json()["memory"]["confidence"] == 0.95
    assert detail.status_code == 200
    assert detail.json()["evidence_event_ids"] == [evidence.json()["event_id"]]
    assert forget.json()["deleted_memory_ids"] == [memory_id]
    assert deleted_detail.json()["status"] == "deleted"


def test_reminder_schedule_api_and_forget_cancels_job(tmp_path) -> None:
    _, client = _app_and_client(tmp_path)
    next_run_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    with client:
        evidence = client.post(
            "/events/ingest",
            json=_openclaw_payload("msg_schedule_evidence", "真实 OpenClaw reminder tool call evidence"),
            headers=_headers(),
        )
        scheduled = client.post(
            "/reminder/schedule",
            json={
                "user_id": "ou_user",
                "reminder_text": "提醒我写周报",
                "schedule_type": "once",
                "next_run_at": next_run_at,
                "evidence_event_ids": [evidence.json()["event_id"]],
            },
            headers=_headers(),
        )
        memory_id = scheduled.json()["memory_id"]
        client.post("/memory/forget", json={"memory_id": memory_id}, headers=_headers())
        detail = client.get(f"/memory/{memory_id}", headers=_headers())

    assert scheduled.status_code == 200
    assert scheduled.json()["reminder_jobs"][0]["schedule_type"] == "once"
    assert detail.json()["status"] == "deleted"
    assert detail.json()["reminder_jobs"][0]["status"] == "cancelled"


def test_conflicting_preference_replaces_previous_memory(tmp_path) -> None:
    app, client = _app_and_client(tmp_path)

    with client:
        client.post(
            "/events/ingest",
            json=_openclaw_payload("msg_conflict_1", "以后我的周报先写结论，再写风险"),
            headers=_headers(),
        )
        client.post(
            "/events/ingest",
            json=_openclaw_payload("msg_conflict_2", "以后我的周报先写风险，再写结论"),
            headers=_headers(),
        )
        memories = MemoryStore(app.state.db_engine).list_memories("ou_user")

    statuses = sorted(memory["status"] for memory in memories)
    assert statuses == ["active", "replaced"]


def test_strong_sensitive_event_is_not_promoted_to_long_term_memory(tmp_path) -> None:
    app, client = _app_and_client(tmp_path)

    with client:
        response = client.post(
            "/events/ingest",
            json=_openclaw_payload("msg_secret", "以后记住 token=abc123456789secret"),
            headers=_headers(),
        )
        memories = MemoryStore(app.state.db_engine).list_memories("ou_user")

    assert response.status_code == 200
    assert response.json()["event"]["privacy_level"] == "sensitive"
    assert memories == []


def test_memory_api_requires_token(tmp_path) -> None:
    _, client = _app_and_client(tmp_path)

    with client:
        response = client.get("/memory/missing")

    assert response.status_code == 401

