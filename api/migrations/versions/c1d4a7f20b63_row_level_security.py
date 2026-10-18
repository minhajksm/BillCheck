"""row level security on every table

Revision ID: c1d4a7f20b63
Revises: b3c71e52d9af
Create Date: 2026-10-18 11:20:00.000000

A hosted Postgres is not only a database. Supabase also serves every table in
the `public` schema over HTTP, and the key that reads it is published in client
apps by design -- that is what it is for. Nothing in BillCheck uses that API:
the app talks to this FastAPI service, which connects as the role that owns
these tables. So the HTTP side has no business reading them, and the only
thing standing between an anonymous request and a family's bill is row level
security.

Enabled with no policies, which means exactly that: no row is visible to any
role the policies don't name, and none are named. The owner of a table is
outside row level security unless it is FORCEd, which it deliberately is not
here, so this service goes on reading and writing as before. Supabase's own
dashboard also stays readable, since it connects as a role that bypasses this.

Postgres only. Tests run on SQLite, which has no such thing, and a local
Postgres in Docker serves nothing over HTTP -- but it costs nothing there and
keeps the two the same shape.

If a later deployment connects as some role that is not the owner, every query
here will return nothing until policies exist. That is the right failure: it
is visible on the first request, not after a leak.
"""

from collections.abc import Sequence
from typing import Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1d4a7f20b63"
down_revision: Union[str, Sequence[str], None] = "b3c71e52d9af"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Every table this application owns. A table missing from here is a table
# served to anyone who asks, so tests/test_db_connection.py checks the list
# against the models rather than trusting it.
TABLES: tuple[str, ...] = (
    "users",
    "otp_challenges",
    "sessions",
    "cases",
    "case_members",
    "case_invites",
    "bills",
    "upload_attempts",
    "line_items",
    "flags",
)


def upgrade() -> None:
    """Upgrade schema."""
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    """Downgrade schema."""
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in TABLES:
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
