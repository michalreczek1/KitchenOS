"""add user names

Revision ID: 0003_user_names
Revises: 0002_recipe_ratings
Create Date: 2026-02-03 00:10:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "0003_user_names"
down_revision = "0002_recipe_ratings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("first_name", sa.String(), nullable=True))
    op.add_column("users", sa.Column("last_name", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")
