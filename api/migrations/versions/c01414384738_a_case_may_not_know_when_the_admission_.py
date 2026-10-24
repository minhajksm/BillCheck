"""a case may not know when the admission began

Revision ID: c01414384738
Revises: eeab436271a8
Create Date: 2026-10-24 04:10:00.000000

A case opened from a bill took its admission date from the bill's own date,
and from today where the bill printed neither. Both are guesses, and the
column being NOT NULL is why they existed. One real bill printed only
"Date: 04/05/2025", two days before its own line items: the case read
"Admitted 4 May" as fact while the reader was saying, correctly, that no
admission date was printed on it.

Nothing is backfilled and no existing row changes: every case already carries
a date, right or guessed, and this only lets new ones carry none.

The downgrade has to put a date back where there is none, and there is none
to put. It takes the earliest bill on the case, and the day the case was made
where there are no bills -- the same shape of guess this removes, which is
the honest cost of going back.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c01414384738"
down_revision: Union[str, Sequence[str], None] = "eeab436271a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column("cases", "admitted_on", existing_type=sa.Date(), nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        """
        UPDATE cases SET admitted_on = COALESCE(
            (SELECT MIN(b.bill_date) FROM bills b WHERE b.case_id = cases.id),
            cases.created_at::date
        )
        WHERE admitted_on IS NULL
        """
    )
    op.alter_column("cases", "admitted_on", existing_type=sa.Date(), nullable=False)
