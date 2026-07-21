"""add_sms_capture_columns

Revision ID: f4663e7dbc38
Revises: 82e970657d8d
Create Date: 2026-07-11 14:07:00.366690

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4663e7dbc38'
down_revision: Union[str, Sequence[str], None] = '82e970657d8d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add SMS capture columns to transactions table."""
    op.add_column('transactions', sa.Column('confidence', sa.Float(), nullable=True))
    op.add_column('transactions', sa.Column('reviewed', sa.Boolean(), nullable=False, server_default='f'))
    op.add_column('transactions', sa.Column('lat', sa.Float(), nullable=True))
    op.add_column('transactions', sa.Column('lng', sa.Float(), nullable=True))
    op.add_column('transactions', sa.Column('location_label', sa.String(), nullable=True))


def downgrade() -> None:
    """Remove SMS capture columns from transactions table."""
    op.drop_column('transactions', 'location_label')
    op.drop_column('transactions', 'lng')
    op.drop_column('transactions', 'lat')
    op.drop_column('transactions', 'reviewed')
    op.drop_column('transactions', 'confidence')