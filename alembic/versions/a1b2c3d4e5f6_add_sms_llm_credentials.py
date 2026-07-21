"""add_sms_llm_credentials

Separate per-user LLM key for the SMS-capture agent so it can run a
cheaper/faster (or different-provider) model than the conversational agent.

Revision ID: a1b2c3d4e5f6
Revises: f4663e7dbc38
Create Date: 2026-07-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f4663e7dbc38'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the sms_llm_credentials table (mirrors llm_credentials)."""
    op.create_table(
        'sms_llm_credentials',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(), nullable=False, server_default='google_genai'),
        sa.Column('encrypted_key', sa.String(), nullable=False),
        sa.Column('model', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
    )


def downgrade() -> None:
    op.drop_table('sms_llm_credentials')
