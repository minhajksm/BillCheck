"""Cases: one hospital admission of one member.

A case is seen by everyone following its member (see access.py), and shared
by sharing the member: family follow the person, not one stay at a time.
"""

import uuid
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from access import can_see, load_member, member_to_file_under
from auth import CurrentUser, Db
from db import india_today
from models import CaseCreate, CaseOut, CaseUpdate, DailyBillOut, FileUnder, MemberRef
from stay import recheck_stay
from tables import Bill, Case, Flag, LineItem, MemberFollower, User

router = APIRouter(prefix="/cases", tags=["cases"])

ERRORS = {
    "case_not_found": "This case isn't available.",
    "not_case_owner": "Only the person who started the case can delete it.",
}


def case_error(status_code: int, code: str) -> HTTPException:
    return HTTPException(status_code, detail={"code": code, "message": ERRORS[code]})


def load_case(db: Session, case_id: uuid.UUID, user: User) -> Case:
    """The case, or a 404 if the caller can't see it.

    A case the caller can't see answers exactly like one that doesn't exist,
    so an id can't be probed for whether a patient is in hospital.
    """
    case = db.scalar(
        select(Case).where(Case.id == case_id).options(selectinload(Case.member), selectinload(Case.bills))
    )
    if case is None or not can_see(db, case.member_id, case.created_by, user.id):
        raise case_error(status.HTTP_404_NOT_FOUND, "case_not_found")
    return case


def visible_cases(user: User):
    """Cases under a member the caller follows, and their own not yet filed."""
    followed = select(MemberFollower.member_id).where(MemberFollower.user_id == user.id)
    return or_(
        Case.member_id.in_(followed),
        (Case.member_id.is_(None)) & (Case.created_by == user.id),
    )


# Newest admission first. A case whose bill printed no admission date has
# none to sort by and is almost always one just opened, so it goes to the
# top; `created_at` breaks the tie, and both engines agree rather than SQLite
# and Postgres disagreeing about where nulls land.
NEWEST_FIRST = (Case.admitted_on.desc().nullsfirst(), Case.created_at.desc())


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
        member=MemberRef(id=case.member.id, name=case.member.name) if case.member else None,
        is_owner=case.created_by == user.id,
        bills=[
            DailyBillOut(
                id=bill.id,
                date=bill.bill_date,
                item_count=counts.get(bill.id, (0, 0, 0))[0],
                total=float(bill.total),
                flag_count=counts.get(bill.id, (0, 0, 0))[1],
                open_flag_count=counts.get(bill.id, (0, 0, 0))[2],
            )
            for bill in sorted(case.bills, key=lambda b: (b.bill_date, b.created_at))
        ],
        recovered_amount=float(recovered_amount(db, case.id)),
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CaseOut)
def create_case(body: CaseCreate, db: Db, user: CurrentUser) -> CaseOut:
    """Opens an admission under a member the caller follows."""
    member = load_member(db, body.member_id, user)
    case = Case(
        member_id=member.id,
        title=body.title,
        hospital_name=body.hospital_name,
        hospital_area=body.hospital_area,
        patient_name=body.patient_name,
        ip_number=body.ip_number,
        bed=body.bed or None,
        admitted_on=body.admitted_on,
        created_by=user.id,
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return case_out(db, case, user)


@router.get("", response_model=list[CaseOut])
def list_cases(db: Db, user: CurrentUser) -> list[CaseOut]:
    """Every case the caller can see, most recently admitted first."""
    cases = db.scalars(
        select(Case)
        .where(visible_cases(user))
        .options(selectinload(Case.member), selectinload(Case.bills))
        .order_by(*NEWEST_FIRST)
    ).all()
    return [case_out(db, case, user) for case in cases]


@router.get("/{case_id}", response_model=CaseOut)
def read_case(case_id: uuid.UUID, db: Db, user: CurrentUser) -> CaseOut:
    return case_out(db, load_case(db, case_id, user), user)


@router.patch("/{case_id}", response_model=CaseOut)
def update_case(case_id: uuid.UUID, body: CaseUpdate, db: Db, user: CurrentUser) -> CaseOut:
    """Corrects the admission details.

    Any follower can, as with closing: these are facts about one admission that
    whoever is at the hospital that day is best placed to fix, and a wrong bed
    number shouldn't wait for whoever started the case.

    Changing either end of the stay moves what was derived from it, so the
    bills are re-checked against the new dates. See stay.py for what that does
    and does not touch.
    """
    case = load_case(db, case_id, user)
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        return case_out(db, case, user)

    # Either end of the stay moving changes which rows fall outside it.
    moved = any(
        field in changes and changes[field] != getattr(case, field) for field in ("admitted_on", "closed_on")
    )
    for field, value in changes.items():
        setattr(case, field, value)

    if moved:
        recheck_stay(db, case)
    db.commit()
    db.refresh(case)
    return case_out(db, case, user)


@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_case(case_id: uuid.UUID, db: Db, user: CurrentUser) -> Response:
    """Deletes the case and everything under it, for everyone following it.

    Only whoever started the case: it takes the bills away from the whole
    family.

    The bills, line items and flags go with it, by the foreign keys' own
    cascade. That is the point rather than a side effect — health data is kept
    only while a family wants it kept, and "delete" has to mean deleted.
    """
    case = load_case(db, case_id, user)
    if user.id != case.created_by:
        raise case_error(status.HTTP_403_FORBIDDEN, "not_case_owner")
    db.delete(case)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{case_id}/member", response_model=CaseOut)
def file_case(case_id: uuid.UUID, body: FileUnder, db: Db, user: CurrentUser) -> CaseOut:
    """Says whose admission this is: someone the caller follows, or someone
    new, usually named as the bill names them.

    For a bill scanned before choosing anyone, which is read first so the
    name on it can be offered. A filed case can be moved the same way, to
    anyone else the caller follows.
    """
    case = load_case(db, case_id, user)
    member = member_to_file_under(db, body, user)
    case.member_id = member.id
    db.commit()
    db.refresh(case)
    return case_out(db, case, user)


@router.post("/{case_id}/close", response_model=CaseOut)
def close_case(case_id: uuid.UUID, db: Db, user: CurrentUser) -> CaseOut:
    """Marks the stay as over. Reports stay readable afterwards."""
    case = load_case(db, case_id, user)
    if case.closed_on is None:
        case.closed_on = india_today()
        db.commit()
        db.refresh(case)
    return case_out(db, case, user)
