"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-02
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("education_level", sa.String(length=255), nullable=False),
        sa.Column("faculty", sa.String(length=255), nullable=False),
        sa.Column("course", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.String(length=255), nullable=False),
        sa.Column("group_name", sa.String(length=255), nullable=False),
        sa.Column("notifications_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)
    op.create_index("ix_users_group_id", "users", ["group_id"], unique=False)

    op.create_table(
        "groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("education_level", sa.String(length=255), nullable=True),
        sa.Column("faculty", sa.String(length=255), nullable=True),
        sa.Column("course", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_groups_external_id", "groups", ["external_id"], unique=True)

    op.create_table(
        "schedule_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("schedule_date", sa.Date(), nullable=False),
        sa.Column("group_id", sa.String(length=255), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("lesson_number", sa.Integer(), nullable=True),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("subject", sa.String(length=512), nullable=True),
        sa.Column("subject_raw", sa.String(length=512), nullable=False),
        sa.Column("teacher", sa.String(length=512), nullable=True),
        sa.Column("classroom", sa.String(length=255), nullable=True),
        sa.Column("lesson_type", sa.String(length=64), nullable=True),
        sa.Column("source_number", sa.String(length=64), nullable=True),
        sa.Column("note", sa.String(length=512), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "group_id", "schedule_date", "source_id", name="uq_entry_group_date_source"
        ),
    )
    op.create_index("ix_schedule_entries_schedule_date", "schedule_entries", ["schedule_date"])
    op.create_index("ix_schedule_entries_source_hash", "schedule_entries", ["source_hash"])
    op.create_index("ix_entry_group_date", "schedule_entries", ["group_id", "schedule_date"])

    op.create_table(
        "notification_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("schedule_date", sa.Date(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="sent"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "schedule_date", name="uq_notification_user_date"),
    )
    op.create_index("ix_notification_log_user_id", "notification_log", ["user_id"])

    op.create_table(
        "schedule_fetch_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scope_key", sa.String(length=255), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ok"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("entries_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_url", sa.String(length=512), nullable=True),
        sa.Column("source_hash", sa.String(length=64), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_schedule_fetch_log_scope_key", "schedule_fetch_log", ["scope_key"], unique=True)


def downgrade() -> None:
    op.drop_table("schedule_fetch_log")
    op.drop_table("notification_log")
    op.drop_table("schedule_entries")
    op.drop_table("groups")
    op.drop_table("users")
