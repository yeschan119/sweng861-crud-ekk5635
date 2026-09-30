"""add coverages, owned by users

No separate index on owner_id: the unique constraint is backed by a B-tree on
(owner_id, cik), and Postgres uses it for a lookup on owner_id alone, which
EXPLAIN confirms. The check constraint is rendered from the CoverageStatus
enum in models.py, so the two cannot drift.

Revision ID: b78ab3e25a4a
Revises: 8bef134737bd
Create Date: 2026-09-08 17:37:43.308940

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b78ab3e25a4a'
down_revision: Union[str, Sequence[str], None] = '8bef134737bd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('coverages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=16), server_default='draft', nullable=False),
    sa.Column('ticker', sa.String(length=10), nullable=True),
    sa.Column('cik', sa.CHAR(length=10), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('draft', 'active', 'archived')", name='ck_coverages_status'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('owner_id', 'cik', name='uq_coverages_owner_cik')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('coverages')
