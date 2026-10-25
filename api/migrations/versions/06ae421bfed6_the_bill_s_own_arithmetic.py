"""the bill's own arithmetic

Revision ID: 06ae421bfed6
Revises: 7a99b3331bcd
Create Date: 2026-10-25 06:00:00.000000

What the code worked out from the bill's own figures, kept on the bill: the
checks (each sum the bill prints, and how it came out), the deposits it
lists, and what has been paid and is still due. See arithmetic.py.

Every existing bill gets empty lists and nulls -- correctly, since none was
checked -- and the app shows those the way it always has. Nothing here can be
backfilled: the figures the checks need were never kept.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "06ae421bfed6"
down_revision: Union[str, Sequence[str], None] = "7a99b3331bcd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("bills", sa.Column("checks", sa.JSON(), server_default="[]", nullable=False))
    op.add_column("bills", sa.Column("payments", sa.JSON(), server_default="[]", nullable=False))
    op.add_column("bills", sa.Column("paid", sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column("bills", sa.Column("balance", sa.Numeric(precision=12, scale=2), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("bills", "balance")
    op.drop_column("bills", "paid")
    op.drop_column("bills", "payments")
    op.drop_column("bills", "checks")
