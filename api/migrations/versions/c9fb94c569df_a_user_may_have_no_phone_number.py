"""a user may have no phone number

Revision ID: c9fb94c569df
Revises: bf4312025110
Create Date: 2026-10-23 17:05:00.000000

An anonymous account is a user row with no phone number, for a family that
wants to check a bill before signing up for anything. Everything else in the
API is unchanged: a case still belongs to a user, so a case id still cannot
be used to find out whether a stranger is in hospital.

The downgrade cannot simply put the NOT NULL back, because the rows it would
reject are exactly the ones this migration allowed, and there is no number to
fill in -- that is what anonymous means. So it deletes them, and their cases
and bills with them by the foreign keys' own cascade. That is real data loss
and it is the only honest answer: a downgrade here says anonymous accounts
are not a thing any more, and those rows cannot be made into signed-in ones.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9fb94c569df"
down_revision: Union[str, Sequence[str], None] = "bf4312025110"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column("users", "phone", existing_type=sa.VARCHAR(length=16), nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DELETE FROM users WHERE phone IS NULL")
    op.alter_column("users", "phone", existing_type=sa.VARCHAR(length=16), nullable=False)
