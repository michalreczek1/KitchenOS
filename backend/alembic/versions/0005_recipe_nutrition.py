"""add recipe nutrition fields

Revision ID: 0005_recipe_nutrition
Revises: 0004_google_calendar
Create Date: 2026-02-15 17:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "0005_recipe_nutrition"
down_revision = "0004_google_calendar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("recipes", sa.Column("servings_unit", sa.String(), nullable=False, server_default="servings"))
    op.add_column("recipes", sa.Column("nutrition_protein_g", sa.Float(), nullable=True))
    op.add_column("recipes", sa.Column("nutrition_carbs_g", sa.Float(), nullable=True))
    op.add_column("recipes", sa.Column("nutrition_fiber_g", sa.Float(), nullable=True))
    op.add_column("recipes", sa.Column("nutrition_glycemic_load", sa.Float(), nullable=True))
    op.alter_column("recipes", "servings_unit", server_default=None)


def downgrade() -> None:
    op.drop_column("recipes", "nutrition_glycemic_load")
    op.drop_column("recipes", "nutrition_fiber_g")
    op.drop_column("recipes", "nutrition_carbs_g")
    op.drop_column("recipes", "nutrition_protein_g")
    op.drop_column("recipes", "servings_unit")
