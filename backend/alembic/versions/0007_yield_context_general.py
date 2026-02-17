"""add generalized yield context fields

Revision ID: 0007_yield_context_general
Revises: 0006_recipe_nutrition_calories
Create Date: 2026-02-15 21:20:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "0007_yield_context_general"
down_revision = "0006_recipe_nutrition_calories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("recipes", sa.Column("yield_display_label", sa.String(), nullable=True))
    op.add_column("recipes", sa.Column("total_weight_g", sa.Float(), nullable=True))
    op.add_column("recipes", sa.Column("portion_weight_g", sa.Float(), nullable=True))
    op.add_column("recipes", sa.Column("piece_weight_g", sa.Float(), nullable=True))
    op.add_column("recipes", sa.Column("pan_diameter_min_cm", sa.Float(), nullable=True))
    op.add_column("recipes", sa.Column("pan_diameter_max_cm", sa.Float(), nullable=True))
    op.add_column("recipes", sa.Column("nutrition_source", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("recipes", "nutrition_source")
    op.drop_column("recipes", "pan_diameter_max_cm")
    op.drop_column("recipes", "pan_diameter_min_cm")
    op.drop_column("recipes", "piece_weight_g")
    op.drop_column("recipes", "portion_weight_g")
    op.drop_column("recipes", "total_weight_g")
    op.drop_column("recipes", "yield_display_label")
