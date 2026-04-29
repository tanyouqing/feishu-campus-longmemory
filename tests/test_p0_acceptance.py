from __future__ import annotations

from pathlib import Path


SCRIPT_PATH = Path("scripts/p0_acceptance.ps1")


def test_p0_acceptance_script_exists_and_declares_required_parameters() -> None:
    content = SCRIPT_PATH.read_text(encoding="utf-8")

    assert SCRIPT_PATH.exists()
    assert "[string]$BaseUrl" in content
    assert "[string]$IngestToken" in content
    assert "[string]$UserId" in content
    assert "[string]$JobId" in content


def test_p0_acceptance_script_does_not_create_mock_events_or_fake_success() -> None:
    content = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "/events/ingest" not in content
    assert "/integrations/feishu/events" not in content
    assert "type = \"message\"" not in content
    assert "action = \"received\"" not in content
    assert "does not fake success" in content


def test_p0_acceptance_script_has_no_hardcoded_secret_values() -> None:
    content = SCRIPT_PATH.read_text(encoding="utf-8").lower()
    forbidden = ["cli_", "app_secret", "local-dev-token", "test-token"]

    for value in forbidden:
        assert value not in content


def test_openclaw_context_plugin_passes_config_to_user_id_resolver() -> None:
    content = Path("integrations/openclaw/longmemory-context-plugin/index.ts").read_text(encoding="utf-8")

    assert "resolveUserId(event, config)" in content
    assert "resolveUserId(event))" not in content
