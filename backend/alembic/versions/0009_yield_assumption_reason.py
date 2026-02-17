"""add yield assumption reason field

Revision ID: 0009_yield_assumption_reason
Revises: 0008_nutrition_fat_conf
Create Date: 2026-02-16 00:05:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "0009_yield_assumption_reason"
down_revision = "0008_nutrition_fat_conf"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("recipes", sa.Column("yield_assumption_reason", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("recipes", "yield_assumption_reason")
