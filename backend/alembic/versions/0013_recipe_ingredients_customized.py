"""add recipe ingredients customized flag

Revision ID: 0013_recipe_ing_custom
Revises: 0012_nutrition_resilient
Create Date: 2026-02-28 19:05:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0013_recipe_ing_custom"
down_revision = "0012_nutrition_resilient"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "recipes",
        sa.Column("ingredients_customized", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("recipes", "ingredients_customized", server_default=None)


def downgrade() -> None:
    op.drop_column("recipes", "ingredients_customized")
