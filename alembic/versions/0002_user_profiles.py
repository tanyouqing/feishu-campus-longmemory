"""Add user profile tables.

Revision ID: 0002_user_profiles
Revises: 0001_initial_schema
Create Date: 2026-05-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_user_profiles"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.String(length=128), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=True),
        sa.Column("profile_json", sa.JSON(), nullable=False),
        sa.Column("profile_markdown", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_event_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["last_event_id"], ["work_events.event_id"], ondelete="SET NULL"),
        sa.CheckConstraint("confidence >= 0 and confidence <= 1", name="ck_user_profiles_confidence"),
        sa.CheckConstraint("version >= 1", name="ck_user_profiles_version"),
    )
    op.create_index("ix_user_profiles_updated_at", "user_profiles", ["updated_at"])

    op.create_table(
        "user_profile_evidence_links",
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("relation_type", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["user_id"], ["user_profiles.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["work_events.event_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "event_id", "relation_type"),
    )
    op.create_index("ix_user_profile_evidence_links_event", "user_profile_evidence_links", ["event_id"])


def downgrade() -> None:
    op.drop_index("ix_user_profile_evidence_links_event", table_name="user_profile_evidence_links")
    op.drop_table("user_profile_evidence_links")
    op.drop_index("ix_user_profiles_updated_at", table_name="user_profiles")
    op.drop_table("user_profiles")
