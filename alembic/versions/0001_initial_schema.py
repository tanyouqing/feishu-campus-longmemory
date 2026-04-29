"""Create V0.1 memory middleware schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-04-26
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "work_events",
        sa.Column("event_id", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("actor_type", sa.String(length=64), nullable=False),
        sa.Column("object_type", sa.String(length=64), nullable=True),
        sa.Column("object_id", sa.String(length=256), nullable=True),
        sa.Column("work_type", sa.String(length=64), nullable=False, server_default="general"),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("privacy_level", sa.String(length=32), nullable=False, server_default="normal"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("actor_type in ('user', 'agent_on_behalf_of_user', 'system')", name="ck_work_events_actor_type"),
    )
    op.create_index("ix_work_events_user_timestamp", "work_events", ["user_id", "timestamp"])
    op.create_index("ix_work_events_source_type", "work_events", ["source", "event_type"])
    op.create_index("ix_work_events_object", "work_events", ["object_type", "object_id"])

    op.create_table(
        "personal_memories",
        sa.Column("memory_id", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("memory_category", sa.String(length=64), nullable=False),
        sa.Column("work_type", sa.String(length=64), nullable=False, server_default="general"),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("source_channel", sa.String(length=64), nullable=False),
        sa.Column("source_signal_type", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="candidate"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("confidence >= 0 and confidence <= 1", name="ck_personal_memories_confidence"),
        sa.CheckConstraint(
            "memory_category in ('WorkPreferenceMemory', 'WorkTimePatternMemory', 'WorkBehaviorMemory', 'ReminderPreferenceMemory')",
            name="ck_personal_memories_category",
        ),
        sa.CheckConstraint(
            "status in ('candidate', 'active', 'reinforced', 'outdated', 'replaced', 'deleted')",
            name="ck_personal_memories_status",
        ),
    )
    op.create_index("ix_personal_memories_user_status", "personal_memories", ["user_id", "status"])
    op.create_index("ix_personal_memories_user_category", "personal_memories", ["user_id", "memory_category"])
    op.create_index("ix_personal_memories_work_type", "personal_memories", ["work_type"])
    op.create_index("ix_personal_memories_updated_at", "personal_memories", ["updated_at"])

    op.create_table(
        "memory_evidence_links",
        sa.Column("memory_id", sa.String(length=64), nullable=False),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("relation_type", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["memory_id"], ["personal_memories.memory_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["work_events.event_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("memory_id", "event_id", "relation_type"),
    )
    op.create_index("ix_memory_evidence_links_event", "memory_evidence_links", ["event_id"])

    op.create_table(
        "reminder_jobs",
        sa.Column("job_id", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("memory_id", sa.String(length=64), nullable=False),
        sa.Column("schedule_type", sa.String(length=32), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="Asia/Shanghai"),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["memory_id"], ["personal_memories.memory_id"], ondelete="CASCADE"),
        sa.CheckConstraint("schedule_type in ('once', 'weekly', 'daily', 'cron_like')", name="ck_reminder_jobs_schedule_type"),
        sa.CheckConstraint("status in ('active', 'paused', 'triggered', 'cancelled')", name="ck_reminder_jobs_status"),
    )
    op.create_index("ix_reminder_jobs_due", "reminder_jobs", ["status", "next_run_at"])
    op.create_index("ix_reminder_jobs_user", "reminder_jobs", ["user_id"])

    op.create_table(
        "memory_audit_logs",
        sa.Column("audit_id", sa.String(length=64), primary_key=True),
        sa.Column("memory_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("before_json", sa.JSON(), nullable=True),
        sa.Column("after_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["memory_id"], ["personal_memories.memory_id"], ondelete="CASCADE"),
        sa.CheckConstraint("action in ('create', 'update', 'replace', 'delete', 'restore')", name="ck_memory_audit_logs_action"),
    )
    op.create_index("ix_memory_audit_logs_memory", "memory_audit_logs", ["memory_id"])
    op.create_index("ix_memory_audit_logs_user_created", "memory_audit_logs", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_memory_audit_logs_user_created", table_name="memory_audit_logs")
    op.drop_index("ix_memory_audit_logs_memory", table_name="memory_audit_logs")
    op.drop_table("memory_audit_logs")

    op.drop_index("ix_reminder_jobs_user", table_name="reminder_jobs")
    op.drop_index("ix_reminder_jobs_due", table_name="reminder_jobs")
    op.drop_table("reminder_jobs")

    op.drop_index("ix_memory_evidence_links_event", table_name="memory_evidence_links")
    op.drop_table("memory_evidence_links")

    op.drop_index("ix_personal_memories_updated_at", table_name="personal_memories")
    op.drop_index("ix_personal_memories_work_type", table_name="personal_memories")
    op.drop_index("ix_personal_memories_user_category", table_name="personal_memories")
    op.drop_index("ix_personal_memories_user_status", table_name="personal_memories")
    op.drop_table("personal_memories")

    op.drop_index("ix_work_events_object", table_name="work_events")
    op.drop_index("ix_work_events_source_type", table_name="work_events")
    op.drop_index("ix_work_events_user_timestamp", table_name="work_events")
    op.drop_table("work_events")

