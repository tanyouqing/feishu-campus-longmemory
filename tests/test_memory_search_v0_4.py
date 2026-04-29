from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import sqlalchemy as sa
from fastapi.testclient import TestClient

from feishu_campus_longmemory.config import Settings
from feishu_campus_longmemory.main import create_app
from feishu_campus_longmemory.tables import personal_memories


def _app_and_client(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'memory-search.db'}",
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


def _create_evidence(client: TestClient, message_id: str, text: str) -> str:
    response = client.post("/events/ingest", json=_openclaw_payload(message_id, text), headers=_headers())
    assert response.status_code == 200
    return response.json()["event_id"]


def _write_memory(
    client: TestClient,
    evidence_id: str,
    *,
    summary: str,
    normalized_key: str,
    work_type: str = "weekly_report",
    memory_category: str = "WorkPreferenceMemory",
    status: str = "active",
    confidence: float = 0.85,
) -> str:
    response = client.post(
        "/memory/write",
        json={
            "user_id": "ou_user",
            "memory_category": memory_category,
            "work_type": work_type,
            "status": status,
            "confidence": confidence,
            "content_json": {
                "summary": summary,
                "normalized_key": normalized_key,
                "source_text": "完整 evidence 正文不应进入 context pack",
            },
            "evidence_event_ids": [evidence_id],
        },
        headers=_headers(),
    )
    assert response.status_code == 200
    return response.json()["memory_id"]


def test_memory_search_recalls_weekly_report_preference_and_context_pack(tmp_path) -> None:
    _, client = _app_and_client(tmp_path)

    with client:
        client.post(
            "/events/ingest",
            json=_openclaw_payload("msg_pref_search", "以后我的周报先写结论，再写风险"),
            headers=_headers(),
        )
        response = client.post(
            "/memory/search",
            json={"user_id": "ou_user", "query": "帮我写这周周报", "limit": 5},
            headers=_headers(),
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["detected_work_type"] == "weekly_report"
    assert payload["empty"] is False
    assert payload["memories"][0]["work_type"] == "weekly_report"
    assert "周报先写结论" in payload["context_pack"]
    assert "当前用户请求优先" in payload["context_pack"]
    assert payload["memories"][0]["memory_id"] not in payload["context_pack"]
    assert "content_json" not in payload["context_pack"]


def test_memory_search_ranks_exact_work_type_before_general_fallback(tmp_path) -> None:
    _, client = _app_and_client(tmp_path)

    with client:
        evidence_id = _create_evidence(client, "msg_rank_exact", "真实写入 evidence")
        general_id = _write_memory(
            client,
            evidence_id,
            summary="输出尽量简洁",
            normalized_key="general:style",
            work_type="general",
        )
        weekly_id = _write_memory(
            client,
            evidence_id,
            summary="周报先写结论，再写风险",
            normalized_key="weekly_report:format",
            work_type="weekly_report",
        )
        response = client.post(
            "/memory/search",
            json={"user_id": "ou_user", "query": "帮我写这周周报", "work_type": "general", "limit": 5},
            headers=_headers(),
        )

    memory_ids = [item["memory_id"] for item in response.json()["memories"]]
    assert memory_ids[0] == weekly_id
    assert general_id in memory_ids


def test_memory_search_weights_status_confidence_evidence_and_freshness(tmp_path) -> None:
    app, client = _app_and_client(tmp_path)

    with client:
        evidence_id = _create_evidence(client, "msg_rank_status", "真实写入 evidence")
        candidate_id = _write_memory(
            client,
            evidence_id,
            summary="周报候选规则",
            normalized_key="weekly_report:candidate",
            status="candidate",
            confidence=1.0,
        )
        active_id = _write_memory(
            client,
            evidence_id,
            summary="周报高置信规则",
            normalized_key="weekly_report:active",
            status="active",
            confidence=0.1,
        )
        reinforced_id = _write_memory(
            client,
            evidence_id,
            summary="周报强化规则",
            normalized_key="weekly_report:reinforced",
            status="reinforced",
            confidence=0.1,
        )
        response = client.post(
            "/memory/search",
            json={"user_id": "ou_user", "query": "周报", "limit": 5},
            headers=_headers(),
        )

    memory_ids = [item["memory_id"] for item in response.json()["memories"]]
    assert memory_ids.index(reinforced_id) < memory_ids.index(candidate_id)
    assert memory_ids.index(active_id) < memory_ids.index(candidate_id)

    old_time = datetime.now(timezone.utc) - timedelta(days=60)
    with app.state.db_engine.begin() as connection:
        connection.execute(
            sa.update(personal_memories)
            .where(personal_memories.c.memory_id == active_id)
            .values(updated_at=old_time)
        )

    with client:
        refreshed = client.post(
            "/memory/search",
            json={"user_id": "ou_user", "query": "周报", "limit": 5},
            headers=_headers(),
        )

    refreshed_ids = [item["memory_id"] for item in refreshed.json()["memories"]]
    assert refreshed_ids.index(reinforced_id) < refreshed_ids.index(active_id)


def test_memory_search_empty_and_excludes_deleted_replaced_outdated(tmp_path) -> None:
    _, client = _app_and_client(tmp_path)

    with client:
        evidence_id = _create_evidence(client, "msg_deleted", "真实写入 evidence")
        deleted_id = _write_memory(
            client,
            evidence_id,
            summary="周报删除规则",
            normalized_key="weekly_report:deleted",
        )
        client.post("/memory/forget", json={"memory_id": deleted_id}, headers=_headers())
        first = _write_memory(
            client,
            evidence_id,
            summary="周报旧规则",
            normalized_key="weekly_report:replace",
        )
        second = _write_memory(
            client,
            evidence_id,
            summary="周报新规则",
            normalized_key="weekly_report:replace",
        )
        outdated = _write_memory(
            client,
            evidence_id,
            summary="周报过期规则",
            normalized_key="weekly_report:outdated",
        )
        client.post("/memory/update", json={"memory_id": outdated, "status": "outdated"}, headers=_headers())
        response = client.post(
            "/memory/search",
            json={"user_id": "ou_user", "query": "周报", "limit": 10},
            headers=_headers(),
        )
        empty = client.post(
            "/memory/search",
            json={"user_id": "ou_unknown", "query": "帮我写这周周报", "limit": 5},
            headers=_headers(),
        )

    memory_ids = [item["memory_id"] for item in response.json()["memories"]]
    assert deleted_id not in memory_ids
    assert first not in memory_ids
    assert outdated not in memory_ids
    assert second in memory_ids
    assert empty.json()["empty"] is True
    assert empty.json()["context_pack"] == ""
    assert empty.json()["memories"] == []


def test_memory_search_context_pack_does_not_expose_evidence_or_internal_json(tmp_path) -> None:
    _, client = _app_and_client(tmp_path)

    with client:
        evidence_id = _create_evidence(client, "msg_no_leak", "完整 evidence 正文不应进入 context pack")
        memory_id = _write_memory(
            client,
            evidence_id,
            summary="周报只保留摘要",
            normalized_key="weekly_report:no_leak",
        )
        response = client.post(
            "/memory/search",
            json={"user_id": "ou_user", "query": "周报", "limit": 5},
            headers=_headers(),
        )

    context_pack = response.json()["context_pack"]
    assert "周报只保留摘要" in context_pack
    assert "完整 evidence 正文" not in context_pack
    assert "content_json" not in context_pack
    assert memory_id not in context_pack


def test_memory_search_requires_token(tmp_path) -> None:
    _, client = _app_and_client(tmp_path)

    with client:
        response = client.post("/memory/search", json={"user_id": "ou_user", "query": "周报"})

    assert response.status_code == 401


def test_openclaw_integration_declares_ingest_hook_and_context_plugin() -> None:
    hook_dir = Path("integrations/openclaw/longmemory-ingest")
    handler = (hook_dir / "handler.ts").read_text(encoding="utf-8")
    metadata = (hook_dir / "HOOK.md").read_text(encoding="utf-8")
    plugin_dir = Path("integrations/openclaw/longmemory-context-plugin")
    plugin_index = (plugin_dir / "index.ts").read_text(encoding="utf-8")
    plugin_manifest = (plugin_dir / "openclaw.plugin.json").read_text(encoding="utf-8")
    plugin_package = (plugin_dir / "package.json").read_text(encoding="utf-8")

    assert "message:preprocessed" in metadata
    assert "/events/ingest" in handler
    assert "before_prompt_build" in plugin_index
    assert "/memory/search" in plugin_index
    assert "prependSystemContext" in plugin_index
    assert "longmemory-context" in plugin_manifest
    assert "openclaw" in plugin_package
    assert "contextLimit" in plugin_index
    assert "ingestToken" in plugin_manifest
    assert "resolveUserId(event))" not in plugin_index
