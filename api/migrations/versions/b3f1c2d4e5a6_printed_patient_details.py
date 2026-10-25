"""printed patient details

Revision ID: b3f1c2d4e5a6
Revises: 58ec9b92278c
Create Date: 2026-10-25 10:00:00.000000

The patient's age, date of birth, phone, email and address as a bill or lab
report printed them, on `cases.printed_patient` and
`lab_reports.printed_patient`. Kept only while a scan waits to be filed, so
they can be offered as the member's details, and set to null the moment it
is filed. Existing rows start with none.

No new table, so nothing new to lock down.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3f1c2d4e5a6"
down_revision: Union[str, Sequence[str], None] = "58ec9b92278c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("cases", sa.Column("printed_patient", sa.JSON(), nullable=True))
    op.add_column("lab_reports", sa.Column("printed_patient", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("lab_reports", "printed_patient")
    op.drop_column("cases", "printed_patient")
