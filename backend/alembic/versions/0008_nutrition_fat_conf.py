"""add fat and confidence nutrition fields

Revision ID: 0008_nutrition_fat_conf
Revises: 0007_yield_context_general
Create Date: 2026-02-15 23:20:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "0008_nutrition_fat_conf"
down_revision = "0007_yield_context_general"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("recipes", sa.Column("nutrition_fat_g", sa.Float(), nullable=True))
    op.add_column("recipes", sa.Column("nutrition_confidence_score", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("recipes", "nutrition_confidence_score")
    op.drop_column("recipes", "nutrition_fat_g")
