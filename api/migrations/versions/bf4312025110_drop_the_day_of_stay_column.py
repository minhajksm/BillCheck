"""drop the day of stay column

Revision ID: bf4312025110
Revises: c1d4a7f20b63
Create Date: 2026-10-23 14:45:16.200622

Bills were numbered by the day of the stay they covered -- "Day 3 interim
bill" -- and a case carried the day it had reached. Both are gone. The number
was derived from the admission date, so it was only ever as right as that
date, and it went conspicuously wrong on a bill read months later: a case
opened from a 2025 bill with no discharge date counts to today and reads "day
538". A bill is identified by its own date now, which is printed on it.

The downgrade puts the column back and recomputes it from the dates, which is
all it ever was. The column is added nullable first because the table is not
empty: adding a NOT NULL column with no default would fail outright.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bf4312025110"
down_revision: Union[str, Sequence[str], None] = "c1d4a7f20b63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column("bills", "day")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column("bills", sa.Column("day", sa.Integer(), nullable=True))
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "UPDATE bills AS b SET day = GREATEST(1, (b.bill_date - c.admitted_on) + 1) "
            "FROM cases AS c WHERE c.id = b.case_id"
        )
    else:
        op.execute("UPDATE bills SET day = 1")
    op.alter_column("bills", "day", nullable=False)
