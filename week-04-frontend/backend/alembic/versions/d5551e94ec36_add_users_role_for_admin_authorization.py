"""add users.role for admin authorization

Autogenerate wrote the column and nothing else. It does not compare CHECK
constraints, so ck_users_role - which models.py declares - was absent from the
generated file, and running it would have left the model asserting a rule the
database did not hold. The constraint is added here by hand, and the result is
compared against the real table rather than trusted, which is the practice the
baseline revision established.

The column is filled before it is constrained: existing rows predate the
column, take the server default, and are all valid, but stating the order makes
it clear this is not a migration that can strand a row outside the CHECK.

Revision ID: d5551e94ec36
Revises: cb97e84ddbfe
Create Date: 2026-09-11 13:22:01.167016

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5551e94ec36'
down_revision: Union[str, Sequence[str], None] = 'cb97e84ddbfe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Spelled out rather than imported from models.py. A migration describes the
# schema at one point in history; importing the enum would make this file
# change meaning later, when the application's idea of a role has moved on.
ROLES = ("user", "admin")


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column("role", sa.String(length=16), server_default="user", nullable=False),
    )
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN (%s)" % ", ".join(f"'{r}'" for r in ROLES),
    )


def downgrade() -> None:
    """Downgrade schema."""
    # The constraint is dropped first: it depends on the column, and Postgres
    # would drop it silently with the column anyway. Naming it keeps the
    # downgrade readable as the exact inverse of the upgrade.
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.drop_column("users", "role")
