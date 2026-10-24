"""lab reports, explained

Revision ID: 7a99b3331bcd
Revises: 8d852ac228a8
Create Date: 2026-10-24 07:30:00.000000

A lab report read and explained in plain words, kept so a family can open it
again and read it in the other language. The pages are not kept, as with
bills: the results as printed and the explanation of them are.

Two columns on `users` for a consent of its own. The one given at sign-up
covers the bills a person adds, used only to check them; a lab report is
neither, so it is asked for again before the first one, and the date and the
text agreed to are recorded the same way. Existing accounts start with none.

`lab_reports` cascades from the user, and is locked down like every other
table: the host serves the public schema over HTTP to anyone holding the
project's publishable key.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7a99b3331bcd"
down_revision: Union[str, Sequence[str], None] = "8d852ac228a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Read by tests/test_db_connection.py, which fails while a table is missing.
TABLES: tuple[str, ...] = ("lab_reports",)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "lab_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("lab_name", sa.String(length=200), nullable=False),
        sa.Column("patient_name", sa.String(length=80), nullable=False),
        sa.Column("report_date", sa.String(length=40), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("tests", sa.JSON(), nullable=False),
        sa.Column("summary_en", sa.Text(), nullable=False),
        sa.Column("summary_hi", sa.Text(), nullable=False),
        sa.Column("questions_en", sa.JSON(), nullable=False),
        sa.Column("questions_hi", sa.JSON(), nullable=False),
        sa.Column("urgent", sa.Boolean(), nullable=False),
        sa.Column("model", sa.String(length=60), nullable=False),
        sa.Column("effort", sa.String(length=10), nullable=False),
        sa.Column("prompt_digest", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_lab_reports_created_at"), "lab_reports", ["created_at"], unique=False)
    op.create_index(op.f("ix_lab_reports_user_id"), "lab_reports", ["user_id"], unique=False)
    op.add_column("users", sa.Column("lab_consent_version", sa.String(length=20), nullable=True))
    op.add_column("users", sa.Column("lab_consented_at", sa.DateTime(timezone=True), nullable=True))

    if op.get_bind().dialect.name != "postgresql":
        return
    for table in TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "lab_consented_at")
    op.drop_column("users", "lab_consent_version")
    op.drop_index(op.f("ix_lab_reports_user_id"), table_name="lab_reports")
    op.drop_index(op.f("ix_lab_reports_created_at"), table_name="lab_reports")
    op.drop_table("lab_reports")
