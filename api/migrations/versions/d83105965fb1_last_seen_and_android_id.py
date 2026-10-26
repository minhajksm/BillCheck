"""last seen and android id

Revision ID: d83105965fb1
Revises: b3f1c2d4e5a6
Create Date: 2026-10-26 09:00:00.000000

When each account last opened the app, and from where: `users.last_seen_at`,
`users.last_ip`, and `users.android_id_hash` (a keyed hash of the phone's
Android ID, never the ID itself). Each is overwritten at every sign-in and
launch, so only the latest is ever kept. Existing accounts start with none.

`upload_attempts.android_id_hash` lets the daily allowance be counted per
phone as well as per account. See device.py.

No new table, so nothing new to lock down.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d83105965fb1"
down_revision: Union[str, Sequence[str], None] = "b3f1c2d4e5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("users", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("android_id_hash", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("last_ip", sa.String(length=45), nullable=True))
    op.create_index(op.f("ix_users_android_id_hash"), "users", ["android_id_hash"], unique=False)
    op.add_column("upload_attempts", sa.Column("android_id_hash", sa.String(length=64), nullable=True))
    op.create_index(
        op.f("ix_upload_attempts_android_id_hash"), "upload_attempts", ["android_id_hash"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_upload_attempts_android_id_hash"), table_name="upload_attempts")
    op.drop_column("upload_attempts", "android_id_hash")
    op.drop_index(op.f("ix_users_android_id_hash"), table_name="users")
    op.drop_column("users", "last_ip")
    op.drop_column("users", "android_id_hash")
    op.drop_column("users", "last_seen_at")
