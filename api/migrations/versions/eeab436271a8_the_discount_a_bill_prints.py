"""the discount a bill prints

Revision ID: eeab436271a8
Revises: c9fb94c569df
Create Date: 2026-10-24 03:15:07.000000

A bill that discounts prints two money columns and three totals, and we kept
one of each: the sum of the gross lines, which on a discounted bill is not
what anybody paid. A family handed a bill for Rs 35,000 was shown Rs 43,300.

Both columns are nullable, and rows read before this carry null in both --
correctly, because nothing was read about a discount then. `bills.total`
changes meaning rather than value: it was the sum of the lines and is now the
sum less the discount, which for every existing row is the same number.

The downgrade puts the discount back into `total` before dropping it, so the
column means what it meant before: the gross sum. The figure a family was
actually asked for is what is lost, which is the whole of what this adds.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "eeab436271a8"
down_revision: Union[str, Sequence[str], None] = "c9fb94c569df"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("bills", sa.Column("discount", sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column("line_items", sa.Column("net_amount", sa.Numeric(precision=12, scale=2), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("UPDATE bills SET total = total + discount WHERE discount IS NOT NULL")
    op.drop_column("line_items", "net_amount")
    op.drop_column("bills", "discount")
