"""Bills: upload the pages, read them, check them, keep the result.

A bill goes in as photographs and comes back as line items and flags. The
photographs themselves are read in memory and dropped — never written to disk,
never stored in the database — so the only health data kept is the structured
bill the family can see and question.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

import audit
from auth import CurrentUser, Db
from cases import load_case
from db import utcnow
from models import BillOut, FlagOut, FlagUpdate, LineItemOut
from ocr import BillImage, ExtractedBill, OcrError, OcrProvider, get_ocr_provider, to_decimal
from references import ReferenceData, get_reference_data
from tables import Bill, Case, CaseMember, Flag, LineItem

router = APIRouter(tags=["bills"])

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_PAGES = 12
CHUNK_BYTES = 1024 * 1024

HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1"}

ERRORS = {
    "bill_not_found": "This bill isn't available.",
    "flag_not_found": "This question isn't available.",
    "no_pages": "Add at least one page of the bill.",
    "too_many_pages": f"A bill can have up to {MAX_PAGES} pages.",
    "unreadable_bill": "This bill couldn't be read. Try again in better light, one page at a time.",
}


def bill_error(status_code: int, code: str) -> HTTPException:
    return HTTPException(status_code, detail={"code": code, "message": ERRORS[code]})


def sniff_image_type(head: bytes) -> str | None:
    """Detects the image type from its first bytes, since the client's
    Content-Type header can't be trusted."""
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[4:8] == b"ftyp" and head[8:12] in HEIF_BRANDS:
        return "image/heic"
    return None


async def read_page(file: UploadFile, index: int) -> BillImage:
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
                "message": "Upload a JPEG, PNG, WebP, or HEIC photo of the bill.",
            },
        )
    return BillImage(data=data, content_type=content_type)


def store_bill(
    db: Session, case: Case, extracted: ExtractedBill, flags: list[audit.Flag], bill: Bill
) -> Bill:
    """Writes the line items and their flags, and totals the bill."""
    items_by_position: dict[int, LineItem] = {}
    total = Decimal("0")
    for position, extracted_row in enumerate(extracted.rows, start=1):
        amount = to_decimal(extracted_row.amount) or Decimal("0")
        item = LineItem(
            bill_id=bill.id,
            position=position,
            name=extracted_row.name[:200],
            detail=(extracted_row.detail or None),
            quantity=to_decimal(extracted_row.quantity),
            amount=amount,
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

    if not pages:
        raise bill_error(status.HTTP_400_BAD_REQUEST, "no_pages")
    if len(pages) > MAX_PAGES:
        raise bill_error(status.HTTP_400_BAD_REQUEST, "too_many_pages")

    images = [await read_page(page, index) for index, page in enumerate(pages, start=1)]

    try:
        # Reading a bill can take most of a minute, and the reader is a plain
        # blocking call. Run on the event loop, it would stall every other
        # request (sign-ins, other families' cases) until it finished.
        extracted = await run_in_threadpool(ocr.read_bill, images)
    except OcrError as exc:
        # Nothing is kept from a bill we couldn't read.
        raise bill_error(status.HTTP_422_UNPROCESSABLE_CONTENT, "unreadable_bill") from exc
    finally:
        del images

    on = bill_date or utcnow().date()
    rows = [
        audit.BillRow(
            position=position,
            name=row.name,
            detail=row.detail,
            quantity=to_decimal(row.quantity),
            amount=to_decimal(row.amount) or Decimal("0"),
        )
        for position, row in enumerate(extracted.rows, start=1)
    ]
    flags = audit.audit_bill(rows, references)

    bill = Bill(
        case_id=case.id,
        bill_date=on,
        day=max(1, (on - case.admitted_on).days + 1),
        page_count=len(pages),
        uploaded_by=user.id,
    )
    db.add(bill)
    db.flush()
    store_bill(db, case, extracted, flags, bill)
    db.commit()

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
