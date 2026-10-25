"""Members: the people an account looks after, and who else follows them.

A member is a person -- Papa, Mummy, a friend, the account holder themselves
-- and everything health-related belongs to one: their admissions and their
lab reports. Family follow the member, not one admission at a time, so
whoever joins "Papa" sees every stay and every report of his, including the
ones still to come.

Family join with an invite code a follower creates: it expires, can be
withdrawn, and is stored only as a hash. The member id is never enough to
join, since ids show up in links and logs.
"""

import hashlib
import secrets
import uuid
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from access import load_member, new_member
from auth import CurrentUser, Db
from cases import NEWEST_FIRST, case_out
from db import utcnow
from lab import summary_out
from models import (
    FollowerOut,
    InviteCreated,
    InviteOut,
    JoinMember,
    MemberCreate,
    MemberOut,
    MemberSummaryOut,
    MemberUpdate,
    UnfiledOut,
)
from tables import Bill, Case, Flag, LabReport, Member, MemberFollower, MemberInvite, User

router = APIRouter(tags=["members"])

INVITE_TTL = timedelta(days=7)

ERRORS = {
    "invite_invalid": "This invite has expired or was withdrawn. Ask for a new one.",
    "follower_not_found": "That person doesn't follow this member.",
    "not_member_owner": "Only the person who added this member can do that.",
    "owner_cannot_leave": "You added this member, so you can't stop following them.",
}


def follower_error(status_code: int, code: str) -> HTTPException:
    return HTTPException(status_code, detail={"code": code, "message": ERRORS[code]})


def followers_out(member: Member, user: User) -> list[FollowerOut]:
    return [
        FollowerOut(id=f.user_id, name=f.user.name, is_you=f.user_id == user.id) for f in member.followers
    ]


def summary(db: Session, member: Member, user: User) -> MemberSummaryOut:
    def count(query) -> int:
        return db.scalar(query) or 0

    return MemberSummaryOut(
        id=member.id,
        name=member.name,
        is_owner=member.created_by == user.id,
        followers=followers_out(member, user),
        admission_count=count(select(func.count()).select_from(Case).where(Case.member_id == member.id)),
        open_admission_count=count(
            select(func.count())
            .select_from(Case)
            .where(Case.member_id == member.id, Case.closed_on.is_(None))
        ),
        open_flag_count=count(
            select(func.count())
            .select_from(Flag)
            .join(Bill, Bill.id == Flag.bill_id)
            .join(Case, Case.id == Bill.case_id)
            .where(Case.member_id == member.id, Flag.status == "open")
        ),
        lab_report_count=count(
            select(func.count()).select_from(LabReport).where(LabReport.member_id == member.id)
        ),
    )


def member_out(db: Session, member: Member, user: User) -> MemberOut:
    cases = db.scalars(
        select(Case)
        .where(Case.member_id == member.id)
        .options(selectinload(Case.member), selectinload(Case.bills))
        .order_by(*NEWEST_FIRST)
    ).all()
    reports = db.scalars(
        select(LabReport)
        .where(LabReport.member_id == member.id)
        .options(selectinload(LabReport.member))
        .order_by(LabReport.created_at.desc())
    ).all()
    return MemberOut(
        id=member.id,
        name=member.name,
        is_owner=member.created_by == user.id,
        followers=followers_out(member, user),
        cases=[case_out(db, case, user) for case in cases],
        lab_reports=[summary_out(report) for report in reports],
    )


@router.post("/members", status_code=status.HTTP_201_CREATED, response_model=MemberOut)
def create_member(body: MemberCreate, db: Db, user: CurrentUser) -> MemberOut:
    """Adds someone to look after. Whoever adds them is their first follower."""
    member = new_member(db, body.name, user)
    db.commit()
    return member_out(db, load_member(db, member.id, user), user)


@router.get("/members", response_model=list[MemberSummaryOut])
def list_members(db: Db, user: CurrentUser) -> list[MemberSummaryOut]:
    """Everyone the caller follows: anyone in hospital now first, then by name."""
    members = db.scalars(
        select(Member)
        .join(MemberFollower, MemberFollower.member_id == Member.id)
        .where(MemberFollower.user_id == user.id)
        .options(selectinload(Member.followers).selectinload(MemberFollower.user))
    ).all()
    rows = [summary(db, member, user) for member in members]
    return sorted(rows, key=lambda row: (row.open_admission_count == 0, row.name.casefold()))


@router.get("/unfiled", response_model=UnfiledOut)
def list_unfiled(db: Db, user: CurrentUser) -> UnfiledOut:
    """What the caller scanned before choosing anyone and hasn't filed yet.

    Normally empty: the app asks whose it is as soon as it is read. This is
    where a scan lands if the app was closed before the answer.
    """
    cases = db.scalars(
        select(Case)
        .where(Case.member_id.is_(None), Case.created_by == user.id)
        .options(selectinload(Case.member), selectinload(Case.bills))
        .order_by(*NEWEST_FIRST)
    ).all()
    reports = db.scalars(
        select(LabReport)
        .where(LabReport.member_id.is_(None), LabReport.user_id == user.id)
        .options(selectinload(LabReport.member))
        .order_by(LabReport.created_at.desc())
    ).all()
    return UnfiledOut(
        cases=[case_out(db, case, user) for case in cases],
        lab_reports=[summary_out(report) for report in reports],
    )


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


@router.post("/members/join", response_model=MemberOut)
def join_member(body: JoinMember, db: Db, user: CurrentUser) -> MemberOut:
    """Follows a member with an invite code from family.

    An unknown, expired, or withdrawn code all answer the same way, so a code
    can't be tested for whether it once existed.
    """
    invite = db.scalar(select(MemberInvite).where(MemberInvite.code_hash == _hash_code(body.code)))
    if invite is None or invite.revoked_at is not None or invite.expires_at <= utcnow():
        raise follower_error(status.HTTP_404_NOT_FOUND, "invite_invalid")
    member = db.get(Member, invite.member_id)
    if member is None:
        raise follower_error(status.HTTP_404_NOT_FOUND, "invite_invalid")
    if not any(f.user_id == user.id for f in member.followers):
        member.followers.append(MemberFollower(user_id=user.id))
        db.commit()
    return member_out(db, load_member(db, member.id, user), user)


@router.get("/members/{member_id}", response_model=MemberOut)
def read_member(member_id: uuid.UUID, db: Db, user: CurrentUser) -> MemberOut:
    return member_out(db, load_member(db, member_id, user), user)


@router.patch("/members/{member_id}", response_model=MemberOut)
def rename_member(member_id: uuid.UUID, body: MemberUpdate, db: Db, user: CurrentUser) -> MemberOut:
    """Any follower can: "Papa" to one of them is "Ramesh Sharma" on a bill."""
    member = load_member(db, member_id, user)
    member.name = body.name
    db.commit()
    return member_out(db, member, user)


@router.delete("/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_member(member_id: uuid.UUID, db: Db, user: CurrentUser) -> Response:
    """Deletes the member and everything about them, for everyone following.

    Only whoever added them: it takes every admission and report away from
    the whole family. "Delete" has to mean deleted -- health data is kept only
    while a family wants it kept -- so their cases, bills and lab reports go
    with them.
    """
    member = load_member(db, member_id, user)
    if member.created_by != user.id:
        raise follower_error(status.HTTP_403_FORBIDDEN, "not_member_owner")
    db.delete(member)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/members/{member_id}/invites", status_code=status.HTTP_201_CREATED, response_model=InviteCreated
)
def create_invite(member_id: uuid.UUID, db: Db, user: CurrentUser) -> InviteCreated:
    """A new invite code for this member, valid for 7 days. Followers only.

    The code is returned once and stored only as a hash; share it, and
    withdraw it if it goes to the wrong person.
    """
    member = load_member(db, member_id, user)
    code = secrets.token_urlsafe(16)
    invite = MemberInvite(
        member_id=member.id, code_hash=_hash_code(code), created_by=user.id, expires_at=utcnow() + INVITE_TTL
    )
    db.add(invite)
    db.commit()
    return InviteCreated(id=invite.id, code=code, expires_at=invite.expires_at)


@router.get("/members/{member_id}/invites", response_model=list[InviteOut])
def list_invites(member_id: uuid.UUID, db: Db, user: CurrentUser) -> list[InviteOut]:
    """The invites still usable, so one sent to the wrong person can be withdrawn."""
    member = load_member(db, member_id, user)
    invites = db.scalars(
        select(MemberInvite)
        .where(
            MemberInvite.member_id == member.id,
            MemberInvite.revoked_at.is_(None),
            MemberInvite.expires_at > utcnow(),
        )
        .order_by(MemberInvite.created_at)
    ).all()
    return [
        InviteOut(id=i.id, created_by=i.created_by, created_at=i.created_at, expires_at=i.expires_at)
        for i in invites
    ]


@router.post("/members/{member_id}/invites/{invite_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invite(member_id: uuid.UUID, invite_id: uuid.UUID, db: Db, user: CurrentUser) -> Response:
    """Withdraws an invite. Anyone who already joined keeps following."""
    member = load_member(db, member_id, user)
    invite = db.get(MemberInvite, invite_id)
    if invite is None or invite.member_id != member.id:
        raise follower_error(status.HTTP_404_NOT_FOUND, "invite_invalid")
    if invite.revoked_at is None:
        invite.revoked_at = utcnow()
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/members/{member_id}/followers/{user_id}/remove", status_code=status.HTTP_204_NO_CONTENT)
def remove_follower(member_id: uuid.UUID, user_id: uuid.UUID, db: Db, user: CurrentUser) -> Response:
    """Stops someone following. Anyone can stop following; only whoever added
    the member can remove someone else, and they can't stop themselves."""
    member = load_member(db, member_id, user)
    follower = next((f for f in member.followers if f.user_id == user_id), None)
    if follower is None:
        raise follower_error(status.HTTP_404_NOT_FOUND, "follower_not_found")
    if user_id != user.id and user.id != member.created_by:
        raise follower_error(status.HTTP_403_FORBIDDEN, "not_member_owner")
    if user_id == member.created_by:
        raise follower_error(status.HTTP_409_CONFLICT, "owner_cannot_leave")
    db.delete(follower)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
