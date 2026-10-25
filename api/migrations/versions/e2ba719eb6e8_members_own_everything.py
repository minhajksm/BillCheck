"""members own everything

Revision ID: e2ba719eb6e8
Revises: 06ae421bfed6
Create Date: 2026-10-25 06:50:25.075837

A member is a person an account looks after -- Papa, Mummy, a friend, the
account holder themselves -- and their admissions and lab reports now belong
to them. Family follow the member rather than one admission at a time, so
`case_members` and `case_invites` give way to `member_followers` and
`member_invites`.

`cases.member_id` and `lab_reports.member_id` are null only for a scan that
has been read but not yet filed under anyone; until then only whoever scanned
it can see it.

**This starts fresh: every existing case and lab report is deleted**, with
their bills, line items, flags and reading records by the foreign keys' own
cascade. Accounts are kept. Decided on 2026-10-25, while everything stored
was test data; nothing here guesses which member an old case belonged to.

The downgrade cannot bring that data back, and deletes whatever was stored
under members since, since nothing in the old shape could see it.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e2ba719eb6e8"
down_revision: Union[str, Sequence[str], None] = "06ae421bfed6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Read by tests/test_db_connection.py, which fails while a table is missing.
TABLES: tuple[str, ...] = ("members", "member_followers", "member_invites")


def upgrade() -> None:
    """Upgrade schema."""
    # Start fresh. Bills, line items, flags and reading records cascade.
    op.execute("DELETE FROM lab_reports")
    op.execute("DELETE FROM cases")

    op.create_table(
        "members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "member_followers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("member_id", "user_id"),
    )
    op.create_index(op.f("ix_member_followers_member_id"), "member_followers", ["member_id"], unique=False)
    op.create_index(op.f("ix_member_followers_user_id"), "member_followers", ["user_id"], unique=False)
    op.create_table(
        "member_invites",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_hash"),
    )
    op.create_index(op.f("ix_member_invites_member_id"), "member_invites", ["member_id"], unique=False)

    op.drop_index(op.f("ix_case_invites_case_id"), table_name="case_invites")
    op.drop_table("case_invites")
    op.drop_index(op.f("ix_case_members_case_id"), table_name="case_members")
    op.drop_index(op.f("ix_case_members_user_id"), table_name="case_members")
    op.drop_table("case_members")

    op.add_column("cases", sa.Column("member_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_cases_member_id"), "cases", ["member_id"], unique=False)
    op.create_foreign_key(
        "cases_member_id_fkey", "cases", "members", ["member_id"], ["id"], ondelete="CASCADE"
    )
    op.add_column("lab_reports", sa.Column("member_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_lab_reports_member_id"), "lab_reports", ["member_id"], unique=False)
    op.create_foreign_key(
        "lab_reports_member_id_fkey", "lab_reports", "members", ["member_id"], ["id"], ondelete="CASCADE"
    )

    if op.get_bind().dialect.name != "postgresql":
        return
    for table in TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    """Downgrade schema."""
    # Nothing in the old shape could see what is filed under a member.
    op.execute("DELETE FROM lab_reports")
    op.execute("DELETE FROM cases")

    op.drop_constraint("lab_reports_member_id_fkey", "lab_reports", type_="foreignkey")
    op.drop_index(op.f("ix_lab_reports_member_id"), table_name="lab_reports")
    op.drop_column("lab_reports", "member_id")
    op.drop_constraint("cases_member_id_fkey", "cases", type_="foreignkey")
    op.drop_index(op.f("ix_cases_member_id"), table_name="cases")
    op.drop_column("cases", "member_id")

    op.create_table(
        "case_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_id", "user_id"),
    )
    op.create_index(op.f("ix_case_members_user_id"), "case_members", ["user_id"], unique=False)
    op.create_index(op.f("ix_case_members_case_id"), "case_members", ["case_id"], unique=False)
    op.create_table(
        "case_invites",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_hash"),
    )
    op.create_index(op.f("ix_case_invites_case_id"), "case_invites", ["case_id"], unique=False)

    op.drop_index(op.f("ix_member_invites_member_id"), table_name="member_invites")
    op.drop_table("member_invites")
    op.drop_index(op.f("ix_member_followers_user_id"), table_name="member_followers")
    op.drop_index(op.f("ix_member_followers_member_id"), table_name="member_followers")
    op.drop_table("member_followers")
    op.drop_table("members")

    if op.get_bind().dialect.name != "postgresql":
        return
    for table in ("case_members", "case_invites"):
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
