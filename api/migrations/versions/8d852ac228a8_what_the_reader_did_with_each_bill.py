"""what the reader did with each bill

Revision ID: 8d852ac228a8
Revises: c01414384738
Create Date: 2026-10-24 05:20:00.000000

Two tables nothing serves, for judging the reader rather than showing it.

`bill_reads` is one row per bill: which model, effort and prompt produced the
reading, what the reader said about its own confidence, and the shape of the
bill it found. The prompt is identified by a digest of its own text, because
a version number is something a person has to remember to change.

`reader_findings` is every finding it returned, shown or not. The dropped
ones are the point: a finding the reader called low severity, or one naming
lines that aren't in its own transcription, went to a log line and nowhere
else, so "how often does it lose its own numbering, and is it getting better"
had no answer. `flag_id` reaches the flag a shown finding became, and through
it the family's verdict -- corrected, explained, still open.

Both cascade from the bill. There is no separate lifetime to remember and
nothing to purge: deleting a case takes the reading with it, which is what
minimal retention means here.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8d852ac228a8"
down_revision: Union[str, Sequence[str], None] = "c01414384738"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The host serves the public schema over HTTP to anyone holding the project's
# publishable key, so a new table is readable by the world until this runs.
# tests/test_db_connection.py reads this tuple and fails while a table is
# missing from it.
TABLES: tuple[str, ...] = ("bill_reads", "reader_findings")


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "bill_reads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("bill_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=60), nullable=False),
        sa.Column("effort", sa.String(length=10), nullable=False),
        sa.Column("prompt_digest", sa.String(length=16), nullable=False),
        sa.Column("extraction_confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("needs_human_review", sa.Boolean(), nullable=False),
        sa.Column("review_reasons", sa.JSON(), nullable=False),
        sa.Column("consumable_share_pct", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("unitemised_share_pct", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("unreadable_line_count", sa.Integer(), nullable=False),
        sa.Column("lines_read", sa.Integer(), nullable=False),
        sa.Column("pages_processed", sa.Integer(), nullable=False),
        sa.Column("findings_returned", sa.Integer(), nullable=False),
        sa.Column("findings_shown", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["bill_id"], ["bills.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_bill_reads_bill_id"), "bill_reads", ["bill_id"], unique=True)
    op.create_index(op.f("ix_bill_reads_created_at"), "bill_reads", ["created_at"], unique=False)
    op.create_index(op.f("ix_bill_reads_prompt_digest"), "bill_reads", ["prompt_digest"], unique=False)
    op.create_table(
        "reader_findings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("bill_id", sa.Uuid(), nullable=False),
        sa.Column("flag_id", sa.Uuid(), nullable=True),
        sa.Column("finding_id", sa.String(length=40), nullable=False),
        sa.Column("rule", sa.String(length=200), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False),
        sa.Column("outcome", sa.String(length=24), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("confirmation_required", sa.Text(), nullable=False),
        sa.Column("line_ids", sa.String(length=300), nullable=False),
        sa.Column("line_numbers", sa.String(length=300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["bill_id"], ["bills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["flag_id"], ["flags.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_reader_findings_bill_id"), "reader_findings", ["bill_id"], unique=False)
    op.create_index(op.f("ix_reader_findings_outcome"), "reader_findings", ["outcome"], unique=False)
    op.create_index(op.f("ix_reader_findings_rule"), "reader_findings", ["rule"], unique=False)
    op.create_index(op.f("ix_reader_findings_severity"), "reader_findings", ["severity"], unique=False)

    if op.get_bind().dialect.name != "postgresql":
        return
    for table in TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("reader_findings")
    op.drop_table("bill_reads")
