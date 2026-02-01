"""initial schema

Revision ID: 0001_initial
Revises: None
Create Date: 2026-02-01 22:25:00.000000
"""
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
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "recipes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("image_url", sa.String(), nullable=True),
        sa.Column("ingredients", sa.JSON(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("base_portions", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("owner_id", "url", name="uq_recipes_owner_url"),
    )
    op.create_index("ix_recipes_owner_id", "recipes", ["owner_id"])
    op.create_index("ix_recipes_title", "recipes", ["title"])

    op.create_table(
        "plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("owner_id", name="uq_plans_owner"),
    )
    op.create_index("ix_plans_owner_id", "plans", ["owner_id"])

    op.create_table(
        "parse_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("domain", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_parse_logs_owner_id", "parse_logs", ["owner_id"])
    op.create_index("ix_parse_logs_domain", "parse_logs", ["domain"])


def downgrade() -> None:
    op.drop_index("ix_parse_logs_domain", table_name="parse_logs")
    op.drop_index("ix_parse_logs_owner_id", table_name="parse_logs")
    op.drop_table("parse_logs")

    op.drop_index("ix_plans_owner_id", table_name="plans")
    op.drop_table("plans")

    op.drop_index("ix_recipes_title", table_name="recipes")
    op.drop_index("ix_recipes_owner_id", table_name="recipes")
    op.drop_table("recipes")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
