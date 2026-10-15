"""line item category

Revision ID: b3c71e52d9af
Revises: a76bb097ae45
Create Date: 2026-10-15 09:40:00.000000

The reader already classifies every line in PHASE 2 of the analysis; nothing
kept it, so the report could not group the bill. This keeps it.

Bills read before this column have no category to recover -- the pages were
dropped once read -- so they take the reader's own fallback, "unclassified",
and show in the report's last group.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3c71e52d9af"
down_revision: Union[str, Sequence[str], None] = "a76bb097ae45"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "line_items",
        sa.Column(
            "category",
            sa.String(length=24),
            nullable=False,
            server_default="unclassified",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("line_items", "category")
