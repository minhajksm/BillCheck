"""Bills: upload the pages, read them, check them, keep the result.

A bill goes in as photographs and comes back as line items and flags. The
photographs themselves are read in memory and dropped — never written to disk,
never stored in the database — so the only health data kept is the structured
bill the family can see and question.
"""

import logging
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

import audit
from analysis import AnalysedLine, BillAnalysis, BillHeader
from auth import CurrentUser, Db
from cases import load_case
from db import india_today, utcnow
from models import BillOut, FlagOut, FlagUpdate, LineItemOut
from ocr import BillPage, OcrError, OcrProvider, get_ocr_provider, to_decimal
from references import ReferenceData, get_reference_data, parse_bill_date
from review import flags_from_findings
from settings import get_settings
from tables import Bill, Case, CaseMember, Flag, LineItem, UploadAttempt

router = APIRouter(tags=["bills"])

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_PAGES = 12
CHUNK_BYTES = 1024 * 1024

logger = logging.getLogger("billcheck.bills")

HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1"}

ERRORS = {
    "bill_not_found": "This bill isn't available.",
    "flag_not_found": "This question isn't available.",
    "no_pages": "Add at least one page of the bill.",
    "too_many_pages": f"A bill can have up to {MAX_PAGES} pages.",
    "unreadable_bill": "This bill couldn't be read. Try again in better light, one page at a time.",
    "upload_limit": "That's a lot of bills for one day. Try again tomorrow.",
}


def check_upload_limit(db: Session, user_id: uuid.UUID) -> None:
    """Refuses once a person has sent the day's allowance, and records this one.

    Recorded before the read, so a bill that can't be read still counts: that
    read was paid for all the same.
    """
    now = utcnow()
    sent = db.scalar(
        select(func.count())
        .select_from(UploadAttempt)
        .where(UploadAttempt.user_id == user_id, UploadAttempt.created_at > now - timedelta(days=1))
    )
    if (sent or 0) >= get_settings().bill_uploads_per_day:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "upload_limit", "message": ERRORS["upload_limit"]},
            headers={"Retry-After": "3600"},
        )
    db.add(UploadAttempt(user_id=user_id, created_at=now))
    db.commit()


def bill_error(status_code: int, code: str) -> HTTPException:
    return HTTPException(status_code, detail={"code": code, "message": ERRORS[code]})


def sniff_image_type(head: bytes) -> str | None:
    """Detects the file type from its first bytes, since the client's
    Content-Type header can't be trusted."""
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[4:8] == b"ftyp" and head[8:12] in HEIF_BRANDS:
        return "image/heic"
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    return None


async def read_page(file: UploadFile, index: int) -> BillPage:
    chunks: list[bytes] = []
    size = 0
    while chunk := await file.read(CHUNK_BYTES):
        size += len(chunk)
        if size > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                detail={
                    "code": "page_too_large",
                    "message": f"Each page can be up to {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
                },
            )
        chunks.append(chunk)

    data = b"".join(chunks)
    if not data:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": "empty_page", "message": f"Page {index} is empty."},
        )

    content_type = sniff_image_type(data[:16])
    if content_type is None:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={
                "code": "unsupported_page",
                "message": "Upload a photo of the bill (JPEG, PNG, WebP or HEIC) or a PDF.",
            },
        )
    return BillPage(data=data, content_type=content_type)


def line_detail(line: AnalysedLine) -> str | None:
    """The quantity-or-date column, as the app has always shown it.

    The analysis splits what one column used to hold -- a count and its unit,
    or a date -- so this puts it back together for the screen. The date wins
    where the bill prints one, because that is what a family looks for.
    """
    if line.date:
        return line.date
    if line.quantity is None:
        return line.unit or None
    count = f"{line.quantity:g}"
    return f"{count} {line.unit}".strip() or None


def store_bill(db: Session, case: Case, analysis: BillAnalysis, flags: list[audit.Flag], bill: Bill) -> Bill:
    """Writes the line items and their flags, and totals the bill."""
    items_by_position: dict[int, LineItem] = {}
    total = Decimal("0")
    for position, line in enumerate(analysis.lines, start=1):
        amount = to_decimal(line.amount) or Decimal("0")
        item = LineItem(
            bill_id=bill.id,
            position=position,
            # Verbatim, because it is what a family will find on their copy.
            name=line.description_verbatim[:200],
            detail=(line_detail(line) or None),
            quantity=to_decimal(line.quantity),
            amount=amount,
            category=line.category,
        )
        db.add(item)
        items_by_position[position] = item
        total += amount

    bill.total = total
    db.flush()

    for position, flag in enumerate(flags, start=1):
        item = items_by_position.get(flag.row_position)
        db.add(
            Flag(
                bill_id=bill.id,
                line_item_id=item.id if item else None,
                position=position,
                kind=flag.kind,
                level=flag.level,
                billed=flag.billed,
                reference_amount=flag.reference_amount,
                reference_source=flag.reference_source,
                reference_detail=flag.reference_detail,
                excess=flag.excess,
            )
        )
    return bill


def bill_out(bill: Bill) -> BillOut:
    return BillOut(
        id=bill.id,
        case_id=bill.case_id,
        date=bill.bill_date,
        day=bill.day,
        page_count=bill.page_count,
        total=float(bill.total),
        line_items=[
            LineItemOut(
                id=item.id,
                position=item.position,
                name=item.name,
                detail=item.detail,
                quantity=float(item.quantity) if item.quantity is not None else None,
                amount=float(item.amount),
                category=item.category,  # type: ignore[arg-type]
            )
            for item in bill.line_items
        ],
        flags=[
            FlagOut(
                id=flag.id,
                position=flag.position,
                line_item_id=flag.line_item_id,
                kind=flag.kind,
                level=flag.level,
                status=flag.status,
                billed=float(flag.billed),
                reference_amount=float(flag.reference_amount),
                reference_source=flag.reference_source,
                reference_detail=flag.reference_detail or {},
                excess=float(flag.excess),
            )
            for flag in bill.flags
        ],
    )


def load_bill(db: Session, bill_id: uuid.UUID, user_id: uuid.UUID) -> Bill:
    bill = db.scalar(
        select(Bill)
        .where(Bill.id == bill_id)
        .options(selectinload(Bill.line_items), selectinload(Bill.flags))
    )
    if bill is None:
        raise bill_error(status.HTTP_404_NOT_FOUND, "bill_not_found")
    member = db.scalar(
        select(CaseMember).where(CaseMember.case_id == bill.case_id, CaseMember.user_id == user_id)
    )
    if member is None:
        raise bill_error(status.HTTP_404_NOT_FOUND, "bill_not_found")
    return bill


def _split_hospital(printed: str) -> tuple[str, str]:
    """A hospital's name and where it is, from the one line a bill prints.

    Bills print the lot together: "Sample Polyclinic, 12/4, Example Road,
    Pune - 411023". The name comes first, so the first comma splits it well
    enough for a family to recognise their own case in a list -- and the whole
    thing is editable afterwards, which is what that screen is for.
    """
    name, _, area = printed.partition(",")
    return name.strip()[:120], area.strip()[:120]


def bill_day(analysis: BillAnalysis, supplied: date | None) -> date:
    """The date this bill covers.

    The bill's own date, not the day it was photographed. Families go through
    a shoebox of old bills, and dating a 2018 bill today would put it on day
    2,913 of a stay that ended years ago.
    """
    return supplied or parse_bill_date(analysis.bill.bill_date) or india_today()


def closed_on(header: BillHeader, admitted_on: date) -> date | None:
    """When the stay ended, or None where the bill doesn't say.

    Only a printed discharge date closes it. This used to fall back to the
    bill's own date for any bill older than today, on the reasoning that the
    stay is not known to have gone further -- which is true, and was the wrong
    thing to do with it.

    `closed_on` is the upper bound of the stay check, so guessing one tells a
    family that charges after it "may belong to another visit". On an interim
    bill -- issued during an admission, which is most of them -- the guess
    makes the stay one day long and every later charge a question. A real
    bill: admitted 4 May, interim bill dated 4 May, no discharge printed, and
    most of its rows flagged.

    So the guess is gone. A bill that doesn't say when the stay ended leaves
    it open, and the family can close the case themselves on the case screen.
    Nothing is invented from a date the hospital didn't print.
    """
    discharged = parse_bill_date(header.discharge_date)
    return max(discharged, admitted_on) if discharged is not None else None


def case_from_analysis(analysis: BillAnalysis, user_id: uuid.UUID) -> Case:
    """A case opened from what the bill itself says.

    Nothing here is invented. Every field is the reader's own transcription or
    is left empty for the family to fill in, because a case is the record of a
    real admission and a plausible-looking guess in it is worse than a blank.
    """
    header = analysis.bill
    hospital_name, hospital_area = _split_hospital(header.hospital)

    # The admission is what the stay is counted from, so a readable date on the
    # bill beats the bill's own date, which beats today.
    admitted_on = parse_bill_date(header.admission_date) or parse_bill_date(header.bill_date) or india_today()

    # The bill's own words for a label, so nothing of ours needs translating
    # into a case title. Blank where the bill says neither, and the app shows
    # its own placeholder.
    patient_name = header.patient_name.strip()[:80]
    title = patient_name or hospital_name

    case = Case(
        title=title,
        hospital_name=hospital_name,
        hospital_area=hospital_area,
        patient_name=patient_name,
        ip_number=header.ip_number.strip()[:40],
        bed=None,
        admitted_on=admitted_on,
        closed_on=closed_on(header, admitted_on),
        created_by=user_id,
    )
    case.members.append(CaseMember(user_id=user_id))
    return case


async def read_pages(
    pages: list[UploadFile],
    db: Session,
    user_id: uuid.UUID,
    ocr: OcrProvider,
    case_id: uuid.UUID | None = None,
) -> BillAnalysis:
    """The pages, read. Raises the one error a family can act on.

    The photographs are held in memory, read, and dropped: nothing is written
    to disk and nothing but the structured bill is kept.
    """
    if not pages:
        raise bill_error(status.HTTP_400_BAD_REQUEST, "no_pages")
    if len(pages) > MAX_PAGES:
        raise bill_error(status.HTTP_400_BAD_REQUEST, "too_many_pages")

    images = [await read_page(page, index) for index, page in enumerate(pages, start=1)]
    check_upload_limit(db, user_id)

    try:
        # Reading a bill can take most of a minute, and the reader is a plain
        # blocking call. Run on the event loop, it would stall every other
        # request (sign-ins, other families' cases) until it finished.
        return await run_in_threadpool(ocr.read_bill, images)
    except OcrError as exc:
        # The family is told one thing -- try again in better light -- because
        # there is nothing useful they can do with the rest. Whoever is running
        # this needs the rest: a refusal, a truncated answer and a dead API key
        # all look identical from outside, and the chained exception never
        # prints because the HTTPException is handled.
        logger.warning("Couldn't read a bill for case %s: %s", case_id or "(new)", exc)
        # Nothing is kept from a bill we couldn't read.
        raise bill_error(status.HTTP_422_UNPROCESSABLE_CONTENT, "unreadable_bill") from exc
    finally:
        del images


def check_and_store(
    db: Session,
    case: Case,
    analysis: BillAnalysis,
    references: ReferenceData,
    *,
    on: date,
    page_count: int,
    uploaded_by: uuid.UUID,
) -> Bill:
    """Prices the lines against the published lists, then keeps the result."""
    # The prompt refuses to price anything and hands the lines over instead.
    # This is the pricing system it means: the published lists in references.py.
    rows = [
        audit.BillRow(
            position=position,
            name=line.description_verbatim,
            detail=line_detail(line),
            quantity=to_decimal(line.quantity),
            amount=to_decimal(line.amount) or Decimal("0"),
        )
        for position, line in enumerate(analysis.lines, start=1)
    ]
    reference_flags = audit.audit_bill(rows, references)
    flags = flags_from_findings(
        analysis,
        reference_flags,
        case.admitted_on,
        case.closed_on,
        keep_all=get_settings().review_keep_all,
    )

    bill = Bill(
        case_id=case.id,
        bill_date=on,
        day=max(1, (on - case.admitted_on).days + 1),
        page_count=page_count,
        uploaded_by=uploaded_by,
    )
    db.add(bill)
    db.flush()
    store_bill(db, case, analysis, flags, bill)
    db.commit()
    return bill


@router.post(
    "/bills",
    status_code=status.HTTP_201_CREATED,
    response_model=BillOut,
    summary="Check a bill, opening a case for it",
)
async def upload_first_bill(
    db: Db,
    user: CurrentUser,
    ocr: Annotated[OcrProvider, Depends(get_ocr_provider)],
    references: Annotated[ReferenceData, Depends(get_reference_data)],
    pages: Annotated[list[UploadFile], File(description="Photos of the bill, in order.")],
    bill_date: Annotated[date | None, Form()] = None,
) -> BillOut:
    """Reads a bill with no case behind it, and opens one from what it says.

    The way in for a family with a bill in their hand and nothing set up: the
    hospital, the admission date, the patient and the IP number are all printed
    on the bill, so asking them to type it first is asking twice. The case is
    theirs to correct afterwards.

    The case is written only once the bill reads. A bill that can't be read
    leaves nothing behind -- no empty case in the family's list to explain.
    """
    analysis = await read_pages(pages, db, user.id, ocr)

    case = case_from_analysis(analysis, user.id)
    db.add(case)
    db.flush()
    logger.info("Opened case %s from a bill at %s", case.id, case.hospital_name or "(unnamed)")

    bill = check_and_store(
        db,
        case,
        analysis,
        references,
        on=bill_day(analysis, bill_date),
        page_count=len(pages),
        uploaded_by=user.id,
    )
    return bill_out(load_bill(db, bill.id, user.id))


@router.post(
    "/cases/{case_id}/bills",
    status_code=status.HTTP_201_CREATED,
    response_model=BillOut,
    summary="Add one day's bill",
)
async def upload_bill(
    case_id: uuid.UUID,
    db: Db,
    user: CurrentUser,
    ocr: Annotated[OcrProvider, Depends(get_ocr_provider)],
    references: Annotated[ReferenceData, Depends(get_reference_data)],
    pages: Annotated[list[UploadFile], File(description="Photos of the bill, in order.")],
    bill_date: Annotated[date | None, Form()] = None,
) -> BillOut:
    """Reads the pages into line items, checks them, and keeps the result.

    The photographs are dropped once read.
    """
    case = load_case(db, case_id, user)
    analysis = await read_pages(pages, db, user.id, ocr, case_id)
    bill = check_and_store(
        db,
        case,
        analysis,
        references,
        on=bill_day(analysis, bill_date),
        page_count=len(pages),
        uploaded_by=user.id,
    )
    return bill_out(load_bill(db, bill.id, user.id))


@router.get("/bills/{bill_id}", response_model=BillOut, tags=["bills"])
def read_bill(bill_id: uuid.UUID, db: Db, user: CurrentUser) -> BillOut:
    return bill_out(load_bill(db, bill_id, user.id))


@router.patch("/flags/{flag_id}", response_model=FlagOut, tags=["bills"])
def update_flag(flag_id: uuid.UUID, body: FlagUpdate, db: Db, user: CurrentUser) -> FlagOut:
    """Records what the hospital said: corrected, explained, or still open.

    A corrected flag's difference is what the family got back; an explained one
    stops counting as an overcharge without pretending it never came up.
    """
    flag = db.get(Flag, flag_id)
    if flag is None:
        raise bill_error(status.HTTP_404_NOT_FOUND, "flag_not_found")
    load_bill(db, flag.bill_id, user.id)

    flag.status = body.status
    flag.resolved_at = None if body.status == "open" else utcnow()
    db.commit()
    db.refresh(flag)

    return FlagOut(
        id=flag.id,
        position=flag.position,
        line_item_id=flag.line_item_id,
        kind=flag.kind,
        level=flag.level,
        status=flag.status,
        billed=float(flag.billed),
        reference_amount=float(flag.reference_amount),
        reference_source=flag.reference_source,
        reference_detail=flag.reference_detail or {},
        excess=float(flag.excess),
    )
