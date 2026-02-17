"""add portion adjustment metadata fields

Revision ID: 0010_portion_adjust_meta
Revises: 0009_yield_assumption_reason
Create Date: 2026-02-16 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_portion_adjust_meta"
down_revision = "0009_yield_assumption_reason"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("recipes", sa.Column("portion_adjusted_auto", sa.Boolean(), nullable=True))
    op.add_column("recipes", sa.Column("portion_adjustment_code", sa.String(), nullable=True))
    op.add_column("recipes", sa.Column("portion_profile", sa.String(), nullable=True))
    op.add_column("recipes", sa.Column("target_portion_weight_g", sa.Float(), nullable=True))
    op.add_column("recipes", sa.Column("original_base_portions", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("recipes", "original_base_portions")
    op.drop_column("recipes", "target_portion_weight_g")
    op.drop_column("recipes", "portion_profile")
    op.drop_column("recipes", "portion_adjustment_code")
    op.drop_column("recipes", "portion_adjusted_auto")
