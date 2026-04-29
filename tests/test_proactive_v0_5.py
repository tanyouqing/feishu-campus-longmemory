from __future__ import annotations

from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from fastapi.testclient import TestClient

from feishu_campus_longmemory.config import Settings
from feishu_campus_longmemory.main import create_app
from feishu_campus_longmemory.proactive.feishu import FeishuDeliveryError
from feishu_campus_longmemory.proactive.types import FeishuSendResult
from feishu_campus_longmemory.tables import reminder_jobs


class FakeFeishuSender:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict[str, str]] = []

    def send_text(self, *, receive_id: str, receive_id_type: str, text: str, uuid: str) -> FeishuSendResult:
        self.calls.append(
            {
                "receive_id": receive_id,
                "receive_id_type": receive_id_type,
                "text": text,
                "uuid": uuid,
            }
        )
        if self.fail:
            raise FeishuDeliveryError("fake feishu failure", log_id="log-test")
        return FeishuSendResult(message_id=f"om_{len(self.calls)}", chat_id="oc_chat", log_id="log-test")


def _app_and_client(tmp_path, *, feishu_configured: bool = False):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'proactive.db'}",
        ingest_token="test-token",
        log_level="ERROR",
        feishu_app_id="cli_test" if feishu_configured else None,
        feishu_app_secret="test-secret" if feishu_configured else None,
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


def _create_due_reminder(client: TestClient, *, schedule_type: str, reminder_text: str = "提醒我写周报") -> dict:
    evidence = client.post(
        "/events/ingest",
        json=_openclaw_payload(f"msg_{schedule_type}_{datetime.now(timezone.utc).timestamp()}", "真实 reminder evidence"),
        headers=_headers(),
    )
    assert evidence.status_code == 200
    scheduled = client.post(
        "/reminder/schedule",
        json={
            "user_id": "ou_user",
            "reminder_text": reminder_text,
            "schedule_type": schedule_type,
            "next_run_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
            "evidence_event_ids": [evidence.json()["event_id"]],
        },
        headers=_headers(),
    )
    assert scheduled.status_code == 200
    return scheduled.json()["reminder_jobs"][0]


def _job_row(app, job_id: str) -> dict:
    with app.state.db_engine.connect() as connection:
        row = connection.execute(sa.select(reminder_jobs).where(reminder_jobs.c.job_id == job_id)).mappings().one()
    return dict(row)


def _first_job_id(app) -> str:
    with app.state.db_engine.connect() as connection:
        return connection.execute(sa.select(reminder_jobs.c.job_id)).scalar_one()


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _as_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)


def test_once_reminder_sends_feishu_message_and_records_evidence(tmp_path) -> None:
    app, client = _app_and_client(tmp_path, feishu_configured=True)
    fake = FakeFeishuSender()

    with client:
        app.state.reminder_sender = fake
        job = _create_due_reminder(client, schedule_type="once")
        response = client.post("/proactive/trigger", json={"job_id": job["job_id"]}, headers=_headers())
        row = _job_row(app, job["job_id"])
        event = client.get(f"/events/{response.json()['results'][0]['work_event_id']}", headers=_headers())

    assert response.status_code == 200
    assert response.json()["processed"] == 1
    assert response.json()["results"][0]["status"] == "sent"
    assert response.json()["results"][0]["message_id"] == "om_1"
    assert row["status"] == "triggered"
    assert row["payload_json"]["delivery_status"] == "sent"
    assert fake.calls[0]["receive_id"] == "ou_user"
    assert fake.calls[0]["receive_id_type"] == "open_id"
    assert event.json()["source"] == "feishu"
    assert event.json()["event_type"] == "im.message.create_v1"


def test_weekly_reminder_remains_active_and_advances_next_run(tmp_path) -> None:
    app, client = _app_and_client(tmp_path, feishu_configured=True)
    fake = FakeFeishuSender()

    with client:
        app.state.reminder_sender = fake
        job = _create_due_reminder(client, schedule_type="weekly")
        response = client.post("/proactive/trigger", json={"job_id": job["job_id"]}, headers=_headers())
        row = _job_row(app, job["job_id"])

    assert response.status_code == 200
    assert response.json()["results"][0]["status"] == "sent"
    assert row["status"] == "active"
    assert row["last_run_at"] is not None
    assert _as_utc(row["next_run_at"]) > _parse_datetime(job["next_run_at"])


def test_feishu_send_failure_pauses_job_and_records_failed_evidence(tmp_path) -> None:
    app, client = _app_and_client(tmp_path, feishu_configured=True)
    fake = FakeFeishuSender(fail=True)

    with client:
        app.state.reminder_sender = fake
        job = _create_due_reminder(client, schedule_type="once")
        response = client.post("/proactive/trigger", json={"job_id": job["job_id"]}, headers=_headers())
        row = _job_row(app, job["job_id"])
        event = client.get(f"/events/{response.json()['results'][0]['work_event_id']}", headers=_headers())

    assert response.status_code == 200
    assert response.json()["results"][0]["status"] == "failed"
    assert "fake feishu failure" in response.json()["results"][0]["error"]
    assert row["status"] == "paused"
    assert row["payload_json"]["delivery_status"] == "failed"
    assert event.json()["source"] == "longmemory"
    assert event.json()["event_type"] == "reminder.delivery.failed"


def test_proactive_trigger_returns_config_error_without_feishu_app_credentials(tmp_path) -> None:
    _, client = _app_and_client(tmp_path)

    with client:
        response = client.post("/proactive/trigger", json={"limit": 1}, headers=_headers())

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "feishu_sender_not_configured"


def test_proactive_trigger_requires_token(tmp_path) -> None:
    _, client = _app_and_client(tmp_path, feishu_configured=True)

    with client:
        response = client.post("/proactive/trigger", json={"limit": 1})

    assert response.status_code == 401


def test_reminder_cancel_feedback_deletes_memory_and_cancels_job(tmp_path) -> None:
    app, client = _app_and_client(tmp_path)

    with client:
        client.post(
            "/events/ingest",
            json=_openclaw_payload("msg_cancel_create", "每周五上午提醒我写周报"),
            headers=_headers(),
        )
        before = _job_row(app, _first_job_id(app))
        response = client.post(
            "/events/ingest",
            json=_openclaw_payload("msg_cancel_feedback", "以后别提醒这个了"),
            headers=_headers(),
        )
        after = _job_row(app, before["job_id"])

    assert response.status_code == 200
    assert before["status"] == "active"
    assert after["status"] == "cancelled"


def test_sensitive_reminder_is_not_sent_and_records_failed_evidence(tmp_path) -> None:
    app, client = _app_and_client(tmp_path, feishu_configured=True)
    fake = FakeFeishuSender()

    with client:
        app.state.reminder_sender = fake
        job = _create_due_reminder(client, schedule_type="once", reminder_text="提醒我 token=abc123456789secret")
        response = client.post("/proactive/trigger", json={"job_id": job["job_id"]}, headers=_headers())
        row = _job_row(app, job["job_id"])
        event = client.get(f"/events/{response.json()['results'][0]['work_event_id']}", headers=_headers())

    assert fake.calls == []
    assert response.json()["results"][0]["status"] == "failed"
    assert row["status"] == "paused"
    assert row["payload_json"]["delivery_status"] == "failed"
    assert event.json()["privacy_level"] == "sensitive"
    assert "[REDACTED_SECRET]" in event.json()["content_json"]["summary"]["text"]
