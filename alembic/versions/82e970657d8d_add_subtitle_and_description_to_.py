"""add_subtitle_and_description_to_transactions

Revision ID: 82e970657d8d
Revises: 4345fde3acba
Create Date: 2026-07-05 22:20:26.732054

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '82e970657d8d'
down_revision: Union[str, Sequence[str], None] = '4345fde3acba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add subtitle and description columns to transactions table."""
    op.add_column('transactions', sa.Column('subtitle', sa.String(120), nullable=True))
    op.add_column('transactions', sa.Column('description', sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove subtitle and description columns from transactions table."""
    op.drop_column('transactions', 'description')
    op.drop_column('transactions', 'subtitle')