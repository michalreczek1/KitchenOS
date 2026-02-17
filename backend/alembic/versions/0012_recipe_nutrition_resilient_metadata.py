"""add nutrition resilient metadata

Revision ID: 0012_nutrition_resilient
Revises: 0011_recipe_process_and_category
Create Date: 2026-02-16 23:45:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0012_nutrition_resilient"
down_revision = "0011_recipe_process_and_category"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("recipes", sa.Column("nutrition_failure_reason", sa.String(), nullable=True))
    op.add_column("recipes", sa.Column("nutrition_generation_mode", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("recipes", "nutrition_generation_mode")
    op.drop_column("recipes", "nutrition_failure_reason")
