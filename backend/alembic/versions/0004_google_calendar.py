"""add google calendar tokens

Revision ID: 0004_google_calendar
Revises: 0003_user_names
Create Date: 2026-02-03 00:40:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "0004_google_calendar"
down_revision = "0003_user_names"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "google_calendar_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("token_type", sa.String(), nullable=True),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("calendar_id", sa.String(), nullable=True),
        sa.Column("calendar_summary", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("owner_id", name="uq_google_calendar_owner"),
    )
    op.create_index("ix_google_calendar_tokens_owner_id", "google_calendar_tokens", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_google_calendar_tokens_owner_id", table_name="google_calendar_tokens")
    op.drop_table("google_calendar_tokens")
