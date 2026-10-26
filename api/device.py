"""Which phone a request comes from, and from where, for the record.

Two things, kept apart because they are used apart:

- The phone's Android ID, sent by the app as `X-Android-Id`. It survives
  clearing the app's data and reinstalling it -- only a factory reset changes
  it -- so it is what the daily upload allowance is counted against: an
  account costs nothing to make, and a fresh one every morning would
  otherwise mean a fresh allowance. It is never stored as sent. A keyed
  hash is kept instead, which matches the same phone every time and can't
  be turned back into the ID. It is not a login: anyone can send any value
  in a header, so it limits and records, and never grants access.

- The address a request came from, kept as the last one seen. For the
  record only: nothing is decided by it. Indian mobile networks put many
  people behind one address, and it changes often.

Both are personal data under DPDP, which is why the first is hashed and
the second is only ever the latest one, overwritten each time.
"""

import hashlib
import hmac
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, Header, Request

from db import utcnow
from settings import get_settings

if TYPE_CHECKING:
    from tables import User

# Android IDs are 16 hex digits. Anything else is ignored rather than refused:
# an old app, a web browser, or a phone that sends none still works.
_ANDROID_ID = re.compile(r"[0-9a-fA-F]{8,64}")


def android_id_hash(x_android_id: Annotated[str | None, Header()] = None) -> str | None:
    """The keyed hash of the phone's Android ID, or None if it sent none."""
    if not x_android_id or not _ANDROID_ID.fullmatch(x_android_id.strip()):
        return None
    key = get_settings().secret_key.encode()
    return hmac.new(key, b"android-id:" + x_android_id.strip().lower().encode(), hashlib.sha256).hexdigest()


AndroidIdHash = Annotated[str | None, Depends(android_id_hash)]


def client_ip(request: Request) -> str | None:
    """The address the request came from.

    Behind Cloud Run, Google's front end adds the address it saw to the end
    of X-Forwarded-For, so the last entry is the real one; anything before it
    the phone could have written itself. Uvicorn's own `--proxy-headers`
    reads the first entry, which is why this doesn't use `request.client`
    when the header is there.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    entries = [entry.strip() for entry in forwarded.split(",") if entry.strip()]
    if entries:
        return entries[-1][:45]
    return request.client.host[:45] if request.client else None


ClientIp = Annotated[str | None, Depends(client_ip)]


@dataclass(frozen=True)
class Visit:
    """Where a request came from: the phone's hashed Android ID and the address."""

    android_id_hash: str | None
    ip: str | None

    def record(self, user: "User") -> None:
        """Notes that the app was opened on this account just now, and from where.

        A phone that sent no Android ID leaves the last one known in place.
        """
        user.last_seen_at = utcnow()
        user.last_ip = self.ip
        if self.android_id_hash is not None:
            user.android_id_hash = self.android_id_hash


def visit(android_id: AndroidIdHash, ip: ClientIp) -> Visit:
    return Visit(android_id_hash=android_id, ip=ip)


CurrentVisit = Annotated[Visit, Depends(visit)]
