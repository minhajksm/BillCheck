"""Cases: one hospital admission, shared with family.

Everything about a case is visible to its members and to nobody else. Family
join with an invite code a member creates: it expires, can be withdrawn, and is
stored only as a hash. The case id is never enough to join, since ids show up
in links and logs.
"""

import hashlib
import secrets
import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session, selectinload

from auth import CurrentUser, Db
from db import utcnow
from models import CaseCreate, CaseOut, DailyBillOut, InviteCreated, InviteOut, JoinCase, MemberOut
from tables import Bill, Case, CaseInvite, CaseMember, Flag, LineItem, User

router = APIRouter(prefix="/cases", tags=["cases"])

INVITE_TTL = timedelta(days=7)

ERRORS = {
    "case_not_found": "This case isn't available.",
    "invite_invalid": "This invite has expired or was withdrawn. Ask for a new one.",
    "member_not_found": "That person doesn't follow this case.",
    "not_case_owner": "Only the person who started the case can remove someone.",
    "owner_cannot_leave": "You started this case, so you can't leave it.",
}


def case_error(status_code: int, code: str) -> HTTPException:
    return HTTPException(status_code, detail={"code": code, "message": ERRORS[code]})


def day_of_stay(admitted_on: date, closed_on: date | None, today: date) -> int:
    """Day 1 is the admission day. A closed case stops counting on its last day."""
    end = closed_on if closed_on is not None else today
    return max(1, (end - admitted_on).days + 1)


def load_case(db: Session, case_id: uuid.UUID, user: User) -> Case:
    """The case, or a 404 if it isn't the caller's.

    A case the caller doesn't follow answers exactly like one that doesn't
    exist, so an id can't be probed for whether a patient is in hospital.
    """
    case = db.scalar(
        select(Case)
        .where(Case.id == case_id)
        .options(
            selectinload(Case.members).selectinload(CaseMember.user),
            selectinload(Case.bills),
        )
    )
    if case is None or not any(member.user_id == user.id for member in case.members):
        raise case_error(status.HTTP_404_NOT_FOUND, "case_not_found")
    return case


def is_member(db: Session, case_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    return bool(
        db.scalar(select(exists().where(CaseMember.case_id == case_id, CaseMember.user_id == user_id)))
    )


def _counts(db: Session, case_id: uuid.UUID) -> dict[uuid.UUID, tuple[int, int, int]]:
    """Per bill: how many line items, how many flags, how many still open."""
    items = dict(
        db.execute(
            select(LineItem.bill_id, func.count())
            .join(Bill, Bill.id == LineItem.bill_id)
            .where(Bill.case_id == case_id)
            .group_by(LineItem.bill_id)
        ).all()
    )
    flags = dict(
        db.execute(
            select(Flag.bill_id, func.count())
            .join(Bill, Bill.id == Flag.bill_id)
            .where(Bill.case_id == case_id)
            .group_by(Flag.bill_id)
        ).all()
    )
    open_flags = dict(
        db.execute(
            select(Flag.bill_id, func.count())
            .join(Bill, Bill.id == Flag.bill_id)
            .where(Bill.case_id == case_id, Flag.status == "open")
            .group_by(Flag.bill_id)
        ).all()
    )
    return {
        bill_id: (items.get(bill_id, 0), flags.get(bill_id, 0), open_flags.get(bill_id, 0))
        for bill_id in db.scalars(select(Bill.id).where(Bill.case_id == case_id))
    }


def recovered_amount(db: Session, case_id: uuid.UUID) -> Decimal:
    """What the hospital has actually corrected, across every bill on the case."""
    return db.scalar(
        select(func.coalesce(func.sum(Flag.excess), 0))
        .join(Bill, Bill.id == Flag.bill_id)
        .where(Bill.case_id == case_id, Flag.status == "corrected")
    ) or Decimal("0")


def case_out(db: Session, case: Case, user: User) -> CaseOut:
    counts = _counts(db, case.id)
    return CaseOut(
        id=case.id,
        title=case.title,
        hospital_name=case.hospital_name,
        hospital_area=case.hospital_area,
        patient_name=case.patient_name,
        ip_number=case.ip_number,
        bed=case.bed,
        admitted_on=case.admitted_on,
        closed_on=case.closed_on,
        day_of_stay=day_of_stay(case.admitted_on, case.closed_on, utcnow().date()),
        members=[
            MemberOut(id=member.user_id, name=member.user.name, is_you=member.user_id == user.id)
            for member in case.members
        ],
        bills=[
            DailyBillOut(
                id=bill.id,
                date=bill.bill_date,
                day=bill.day,
                item_count=counts.get(bill.id, (0, 0, 0))[0],
                total=float(bill.total),
                flag_count=counts.get(bill.id, (0, 0, 0))[1],
                open_flag_count=counts.get(bill.id, (0, 0, 0))[2],
            )
            for bill in sorted(case.bills, key=lambda b: (b.bill_date, b.day))
        ],
        recovered_amount=float(recovered_amount(db, case.id)),
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CaseOut)
def create_case(body: CaseCreate, db: Db, user: CurrentUser) -> CaseOut:
    """Opens a case. Whoever opens it is its first member."""
    case = Case(
        title=body.title,
        hospital_name=body.hospital_name,
        hospital_area=body.hospital_area,
        patient_name=body.patient_name,
        ip_number=body.ip_number,
        bed=body.bed or None,
        admitted_on=body.admitted_on,
        created_by=user.id,
    )
    case.members.append(CaseMember(user_id=user.id))
    db.add(case)
    db.commit()
    db.refresh(case)
    return case_out(db, case, user)


@router.get("", response_model=list[CaseOut])
def list_cases(db: Db, user: CurrentUser) -> list[CaseOut]:
    """Every case the caller follows, most recently admitted first."""
    cases = db.scalars(
        select(Case)
        .join(CaseMember, CaseMember.case_id == Case.id)
        .where(CaseMember.user_id == user.id)
        .options(
            selectinload(Case.members).selectinload(CaseMember.user),
            selectinload(Case.bills),
        )
        .order_by(Case.admitted_on.desc())
    ).all()
    return [case_out(db, case, user) for case in cases]


@router.get("/{case_id}", response_model=CaseOut)
def read_case(case_id: uuid.UUID, db: Db, user: CurrentUser) -> CaseOut:
    return case_out(db, load_case(db, case_id, user), user)


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def _load_case_by_id(db: Session, case_id: uuid.UUID) -> Case | None:
    return db.scalar(
        select(Case)
        .where(Case.id == case_id)
        .options(selectinload(Case.members).selectinload(CaseMember.user), selectinload(Case.bills))
    )


@router.post("/join", response_model=CaseOut)
def join_case(body: JoinCase, db: Db, user: CurrentUser) -> CaseOut:
    """Joins a case with an invite code from a family member.

    An unknown, expired, or withdrawn code all answer the same way, so a code
    can't be tested for whether it once existed.
    """
    invite = db.scalar(select(CaseInvite).where(CaseInvite.code_hash == _hash_code(body.code)))
    if invite is None or invite.revoked_at is not None or invite.expires_at <= utcnow():
        raise case_error(status.HTTP_404_NOT_FOUND, "invite_invalid")
    case = _load_case_by_id(db, invite.case_id)
    if case is None:
        raise case_error(status.HTTP_404_NOT_FOUND, "invite_invalid")
    if not any(member.user_id == user.id for member in case.members):
        db.add(CaseMember(case_id=case.id, user_id=user.id))
        db.commit()
        db.refresh(case)
    return case_out(db, case, user)


@router.post("/{case_id}/invites", status_code=status.HTTP_201_CREATED, response_model=InviteCreated)
def create_invite(case_id: uuid.UUID, db: Db, user: CurrentUser) -> InviteCreated:
    """A new invite code for this case, valid for 7 days. Members only.

    The code is returned once and stored only as a hash; share it, and
    withdraw it if it goes to the wrong person.
    """
    case = load_case(db, case_id, user)
    code = secrets.token_urlsafe(16)
    invite = CaseInvite(
        case_id=case.id, code_hash=_hash_code(code), created_by=user.id, expires_at=utcnow() + INVITE_TTL
    )
    db.add(invite)
    db.commit()
    return InviteCreated(id=invite.id, code=code, expires_at=invite.expires_at)


@router.get("/{case_id}/invites", response_model=list[InviteOut])
def list_invites(case_id: uuid.UUID, db: Db, user: CurrentUser) -> list[InviteOut]:
    """The invites still usable, so one sent to the wrong person can be withdrawn."""
    case = load_case(db, case_id, user)
    invites = db.scalars(
        select(CaseInvite)
        .where(
            CaseInvite.case_id == case.id, CaseInvite.revoked_at.is_(None), CaseInvite.expires_at > utcnow()
        )
        .order_by(CaseInvite.created_at)
    ).all()
    return [
        InviteOut(id=i.id, created_by=i.created_by, created_at=i.created_at, expires_at=i.expires_at)
        for i in invites
    ]


@router.post("/{case_id}/invites/{invite_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invite(case_id: uuid.UUID, invite_id: uuid.UUID, db: Db, user: CurrentUser) -> Response:
    """Withdraws an invite. Anyone who already joined stays a member."""
    case = load_case(db, case_id, user)
    invite = db.get(CaseInvite, invite_id)
    if invite is None or invite.case_id != case.id:
        raise case_error(status.HTTP_404_NOT_FOUND, "invite_invalid")
    if invite.revoked_at is None:
        invite.revoked_at = utcnow()
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{case_id}/members/{member_id}/remove", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(case_id: uuid.UUID, member_id: uuid.UUID, db: Db, user: CurrentUser) -> Response:
    """Takes someone off the case. Anyone can leave; only whoever started the
    case can remove someone else, and they can't leave it themselves."""
    case = load_case(db, case_id, user)
    member = next((m for m in case.members if m.user_id == member_id), None)
    if member is None:
        raise case_error(status.HTTP_404_NOT_FOUND, "member_not_found")
    if member_id != user.id and user.id != case.created_by:
        raise case_error(status.HTTP_403_FORBIDDEN, "not_case_owner")
    if member_id == case.created_by:
        raise case_error(status.HTTP_409_CONFLICT, "owner_cannot_leave")
    db.delete(member)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{case_id}/close", response_model=CaseOut)
def close_case(case_id: uuid.UUID, db: Db, user: CurrentUser) -> CaseOut:
    """Marks the stay as over. Reports stay readable afterwards."""
    case = load_case(db, case_id, user)
    if case.closed_on is None:
        case.closed_on = utcnow().date()
        db.commit()
        db.refresh(case)
    return case_out(db, case, user)
