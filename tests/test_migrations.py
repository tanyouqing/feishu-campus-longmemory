from __future__ import annotations

from sqlalchemy import create_engine, inspect

from feishu_campus_longmemory.config import Settings
from feishu_campus_longmemory.db import run_migrations


def test_migrations_create_v0_1_tables(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'migration.db'}"
    settings = Settings(database_url=database_url, _env_file=None)

    run_migrations(settings)

    engine = create_engine(database_url, future=True)
    inspector = inspect(engine)

    assert {
        "work_events",
        "personal_memories",
        "memory_evidence_links",
        "reminder_jobs",
        "memory_audit_logs",
        "user_profiles",
        "user_profile_evidence_links",
    }.issubset(set(inspector.get_table_names()))
