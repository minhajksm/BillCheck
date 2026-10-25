"""member details

Revision ID: 58ec9b92278c
Revises: e2ba719eb6e8
Create Date: 2026-10-25 08:30:00.000000

A member's date of birth, phone, email and address. All optional, filled in
only where the family knows them, so existing members start with none. Age
is not a column: it is worked out from the date of birth when asked for, so
it cannot go stale.

No new table, so nothing new to lock down: `members` already has row level
security on.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "58ec9b92278c"
down_revision: Union[str, Sequence[str], None] = "e2ba719eb6e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("members", sa.Column("date_of_birth", sa.Date(), nullable=True))
    op.add_column("members", sa.Column("phone", sa.String(length=16), nullable=True))
    op.add_column("members", sa.Column("email", sa.String(length=254), nullable=True))
    op.add_column("members", sa.Column("address", sa.String(length=300), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("members", "address")
    op.drop_column("members", "email")
    op.drop_column("members", "phone")
    op.drop_column("members", "date_of_birth")
