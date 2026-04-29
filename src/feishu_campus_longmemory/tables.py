from __future__ import annotations

import sqlalchemy as sa

metadata = sa.MetaData()

work_events = sa.Table(
    "work_events",
    metadata,
    sa.Column("event_id", sa.String(length=64), primary_key=True),
    sa.Column("user_id", sa.String(length=128), nullable=False),
    sa.Column("tenant_id", sa.String(length=128), nullable=True),
    sa.Column("source", sa.String(length=64), nullable=False),
    sa.Column("event_type", sa.String(length=128), nullable=False),
    sa.Column("actor_type", sa.String(length=64), nullable=False),
    sa.Column("object_type", sa.String(length=64), nullable=True),
    sa.Column("object_id", sa.String(length=256), nullable=True),
    sa.Column("work_type", sa.String(length=64), nullable=False),
    sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
    sa.Column("content_json", sa.JSON(), nullable=False),
    sa.Column("privacy_level", sa.String(length=32), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

personal_memories = sa.Table(
    "personal_memories",
    metadata,
    sa.Column("memory_id", sa.String(length=64), primary_key=True),
    sa.Column("user_id", sa.String(length=128), nullable=False),
    sa.Column("memory_category", sa.String(length=64), nullable=False),
    sa.Column("work_type", sa.String(length=64), nullable=False),
    sa.Column("content_json", sa.JSON(), nullable=False),
    sa.Column("source_channel", sa.String(length=64), nullable=False),
    sa.Column("source_signal_type", sa.String(length=64), nullable=False),
    sa.Column("confidence", sa.Float(), nullable=False),
    sa.Column("status", sa.String(length=32), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

memory_evidence_links = sa.Table(
    "memory_evidence_links",
    metadata,
    sa.Column("memory_id", sa.String(length=64), nullable=False),
    sa.Column("event_id", sa.String(length=64), nullable=False),
    sa.Column("relation_type", sa.String(length=64), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

reminder_jobs = sa.Table(
    "reminder_jobs",
    metadata,
    sa.Column("job_id", sa.String(length=64), primary_key=True),
    sa.Column("user_id", sa.String(length=128), nullable=False),
    sa.Column("memory_id", sa.String(length=64), nullable=False),
    sa.Column("schedule_type", sa.String(length=32), nullable=False),
    sa.Column("timezone", sa.String(length=64), nullable=False),
    sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("payload_json", sa.JSON(), nullable=False),
    sa.Column("status", sa.String(length=32), nullable=False),
    sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

memory_audit_logs = sa.Table(
    "memory_audit_logs",
    metadata,
    sa.Column("audit_id", sa.String(length=64), primary_key=True),
    sa.Column("memory_id", sa.String(length=64), nullable=False),
    sa.Column("user_id", sa.String(length=128), nullable=False),
    sa.Column("action", sa.String(length=32), nullable=False),
    sa.Column("before_json", sa.JSON(), nullable=True),
    sa.Column("after_json", sa.JSON(), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)
