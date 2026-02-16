"""add recipe process and category metadata

Revision ID: 0011_recipe_process_and_category
Revises: 0010_portion_adjust_meta
Create Date: 2026-02-16 22:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_recipe_process_and_category"
down_revision = "0010_portion_adjust_meta"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("recipes", sa.Column("declared_category", sa.String(), nullable=True))
    op.add_column("recipes", sa.Column("process_class", sa.String(), nullable=True))
    op.add_column("recipes", sa.Column("raw_weight_g", sa.Float(), nullable=True))
    op.add_column("recipes", sa.Column("final_weight_estimation_source", sa.String(), nullable=True))
    op.add_column("recipes", sa.Column("final_weight_confidence", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("recipes", "final_weight_confidence")
    op.drop_column("recipes", "final_weight_estimation_source")
    op.drop_column("recipes", "raw_weight_g")
    op.drop_column("recipes", "process_class")
    op.drop_column("recipes", "declared_category")
