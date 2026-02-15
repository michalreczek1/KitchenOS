"""add recipe nutrition calories field

Revision ID: 0006_recipe_nutrition_calories
Revises: 0005_recipe_nutrition
Create Date: 2026-02-15 20:40:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "0006_recipe_nutrition_calories"
down_revision = "0005_recipe_nutrition"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("recipes", sa.Column("nutrition_calories_kcal", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("recipes", "nutrition_calories_kcal")
