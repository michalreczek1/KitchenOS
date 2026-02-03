"""add recipe ratings

Revision ID: 0002_recipe_ratings
Revises: 0001_initial
Create Date: 2026-02-03 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "0002_recipe_ratings"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recipe_ratings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("recipe_id", sa.Integer(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("owner_id", "recipe_id", name="uq_recipe_ratings_owner_recipe"),
    )
    op.create_index("ix_recipe_ratings_owner_id", "recipe_ratings", ["owner_id"])
    op.create_index("ix_recipe_ratings_recipe_id", "recipe_ratings", ["recipe_id"])


def downgrade() -> None:
    op.drop_index("ix_recipe_ratings_recipe_id", table_name="recipe_ratings")
    op.drop_index("ix_recipe_ratings_owner_id", table_name="recipe_ratings")
    op.drop_table("recipe_ratings")
