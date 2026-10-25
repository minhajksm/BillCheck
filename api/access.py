"""Who can see what.

Everything health-related belongs to a member, and every account following
that member can see all of it. The one exception is a scan nobody has said
whose it is yet: only whoever scanned it can see it, until they file it.

Anything the caller can't see answers exactly like something that doesn't
exist, so an id can't be probed for whether a stranger is in hospital.
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import exists, select
from sqlalchemy.orm import Session, selectinload

from models import FileUnder
from tables import Member, MemberFollower, User

ERRORS = {
    "member_not_found": "This person isn't available.",
}


def member_error(status_code: int, code: str) -> HTTPException:
    return HTTPException(status_code, detail={"code": code, "message": ERRORS[code]})


def follows(db: Session, member_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    return bool(
        db.scalar(
            select(exists().where(MemberFollower.member_id == member_id, MemberFollower.user_id == user_id))
        )
    )


def can_see(db: Session, member_id: uuid.UUID | None, owner_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Something filed under `member_id`, or not yet filed and scanned by `owner_id`."""
    if member_id is None:
        return owner_id == user_id
    return follows(db, member_id, user_id)


def load_member(db: Session, member_id: uuid.UUID, user: User) -> Member:
    """The member, or a 404 if the caller doesn't follow them."""
    member = db.scalar(
        select(Member)
        .where(Member.id == member_id)
        .options(selectinload(Member.followers).selectinload(MemberFollower.user))
    )
    if member is None or not any(f.user_id == user.id for f in member.followers):
        raise member_error(status.HTTP_404_NOT_FOUND, "member_not_found")
    return member


def new_member(db: Session, name: str, user: User) -> Member:
    """A member, with whoever added them as their first follower."""
    member = Member(name=name, created_by=user.id)
    member.followers.append(MemberFollower(user_id=user.id))
    db.add(member)
    db.flush()
    return member


def member_to_file_under(db: Session, body: FileUnder, user: User) -> Member:
    """Someone the caller follows, or someone new they are adding now."""
    if body.member_id is not None:
        return load_member(db, body.member_id, user)
    assert body.new_member_name is not None  # FileUnder takes exactly one
    return new_member(db, body.new_member_name, user)
