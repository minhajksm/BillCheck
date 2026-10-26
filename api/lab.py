"""Lab reports: read one, explain it in plain words, keep it to read again.

A family in hospital is handed lab reports as well as bills, and the two have
the same problem: a page of figures they cannot read, about someone they are
worried for. This reads the report and explains each result against the
range the report itself prints -- what the test measures, and whether the
value is inside that range -- in English and in Hindi.

It explains; it never diagnoses. lab_prompt.py holds the rules the reader is
given and lab_analysis.py the one claim of its that is checked here.

Nothing is read before the person has agreed to it. The consent given at
sign-up covers "the bills I add", used "only to check my bills", and a lab
report is neither: so it is asked for again, once, as its own act.
"""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from access import can_see, load_member, member_to_file_under
from auth import CurrentUser, Db
from bills import MAX_PAGES, check_upload_limit, read_page
from db import utcnow
from device import AndroidIdHash
from lab_analysis import LabAnalysis, recheck
from lab_prompt import PROMPT_DIGEST
from models import FileUnder, LabConsent, LabReportOut, LabReportSummaryOut, LabTestOut, MemberRef
from ocr import OcrError, OcrProvider, WrongDocument, get_ocr_provider
from printed_patient import printed, suggestion
from settings import get_settings
from tables import LabReport, MemberFollower, User

router = APIRouter(prefix="/lab-reports", tags=["lab reports"])

logger = logging.getLogger("faircare.lab")

# Which consent text was agreed to. Change it when the words in the app do.
LAB_CONSENT_VERSION = "2026-10-lab-faircare"

ERRORS = {
    "lab_consent_required": "Agree to lab reports being stored and explained first.",
    "lab_report_not_found": "This report isn't available.",
    "not_report_owner": "Only whoever added the report, or the person who added this member, can delete it.",
    "no_pages": "Add at least one page of the report.",
    "too_many_pages": f"A report can have up to {MAX_PAGES} pages.",
    "unreadable_lab_report": "This report couldn't be read. Try again in better light, one page at a time.",
    "not_a_lab_report": "This doesn't look like a lab report.",
}

ERROR_RESPONSES: dict[int | str, dict] = {
    403: {"description": "lab_consent_required"},
    404: {"description": "lab_report_not_found"},
    422: {"description": "unreadable_lab_report, or not_a_lab_report with the page's own title"},
}


def lab_error(status_code: int, code: str) -> HTTPException:
    return HTTPException(status_code, detail={"code": code, "message": ERRORS[code]})


def member_ref(report: LabReport) -> MemberRef | None:
    return MemberRef(id=report.member.id, name=report.member.name) if report.member else None


def report_out(report: LabReport) -> LabReportOut:
    return LabReportOut(
        id=report.id,
        member=member_ref(report),
        suggested_member=None
        if report.member_id
        else suggestion(report.printed_patient, report.patient_name),
        lab_name=report.lab_name,
        patient_name=report.patient_name,
        report_date=report.report_date,
        page_count=report.page_count,
        # `reader_status` stays in the database. It is a record of the reader
        # getting it wrong, and a family has no use for the wrong answer.
        tests=[LabTestOut.model_validate(test) for test in report.tests],
        summary_en=report.summary_en,
        summary_hi=report.summary_hi,
        questions_en=list(report.questions_en),
        questions_hi=list(report.questions_hi),
        urgent=report.urgent,
        created_at=report.created_at,
    )


def summary_out(report: LabReport) -> LabReportSummaryOut:
    return LabReportSummaryOut(
        id=report.id,
        lab_name=report.lab_name,
        patient_name=report.patient_name,
        report_date=report.report_date,
        member=member_ref(report),
        test_count=len(report.tests),
        outside_range=sum(1 for test in report.tests if test.get("status") in ("low", "high")),
        urgent=report.urgent,
        created_at=report.created_at,
    )


def load_report(db: Session, report_id: uuid.UUID, user: User) -> LabReport:
    """The report, if the caller can see it. Someone else's is not found, not
    forbidden: an id must not tell anyone whether a stranger has had blood
    taken."""
    report = db.get(LabReport, report_id)
    if report is None or not can_see(db, report.member_id, report.user_id, user.id):
        raise lab_error(status.HTTP_404_NOT_FOUND, "lab_report_not_found")
    return report


def visible_reports(user: User):
    """Reports about a member the caller follows, and their own not yet filed."""
    followed = select(MemberFollower.member_id).where(MemberFollower.user_id == user.id)
    return or_(
        LabReport.member_id.in_(followed),
        (LabReport.member_id.is_(None)) & (LabReport.user_id == user.id),
    )


@router.post("/consent", status_code=status.HTTP_204_NO_CONTENT, responses=ERROR_RESPONSES)
def give_consent(body: LabConsent, db: Db, user: CurrentUser) -> Response:
    """Records agreement to lab reports being stored and explained.

    Its own request, not a field on the upload, so agreeing is a thing the
    person did rather than a checkbox that rode along with a photograph.
    Agreeing again is harmless and keeps the first date.
    """
    if user.lab_consented_at is None:
        user.lab_consent_version = LAB_CONSENT_VERSION
        user.lab_consented_at = utcnow()
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=LabReportOut, responses=ERROR_RESPONSES)
async def upload_lab_report(
    db: Db,
    user: CurrentUser,
    ocr: Annotated[OcrProvider, Depends(get_ocr_provider)],
    pages: Annotated[list[UploadFile], File(description="Photos or a PDF of the report, in order.")],
    android_id: AndroidIdHash,
    member_id: Annotated[
        uuid.UUID | None,
        Form(description="Whose report it is. Left out, it waits to be filed."),
    ] = None,
) -> LabReportOut:
    """Reads a lab report and explains it, in English and in Hindi.

    Counts against the same daily allowance as bills: both are a paid read.
    A report that can't be read leaves nothing behind. Uploaded before
    choosing anyone, it waits for POST /lab-reports/{id}/member, as a bill does.
    """
    if not user.lab_consent:
        raise lab_error(status.HTTP_403_FORBIDDEN, "lab_consent_required")
    if member_id is not None:
        load_member(db, member_id, user)
    if not pages:
        raise lab_error(status.HTTP_400_BAD_REQUEST, "no_pages")
    if len(pages) > MAX_PAGES:
        raise lab_error(status.HTTP_400_BAD_REQUEST, "too_many_pages")

    images = [await read_page(page, index) for index, page in enumerate(pages, start=1)]
    check_upload_limit(db, user.id, android_id)

    try:
        # As with a bill, a blocking call that can take most of a minute.
        analysis: LabAnalysis = await run_in_threadpool(ocr.read_lab_report, images)
    except WrongDocument as exc:
        # Readable, and not a lab report: a scan report, a prescription. The
        # family is told what it looks like, not to take the photo again.
        logger.warning("Not a lab report, for user %s: %s", user.id, exc)
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "not_a_lab_report",
                "message": ERRORS["not_a_lab_report"],
                "document": exc.document,
            },
        ) from exc
    except OcrError as exc:
        logger.warning("Couldn't read a lab report for user %s: %s", user.id, exc)
        raise lab_error(status.HTTP_422_UNPROCESSABLE_CONTENT, "unreadable_lab_report") from exc
    finally:
        del images

    settings = get_settings()
    header = analysis.report
    report = LabReport(
        user_id=user.id,
        member_id=member_id,
        # As for a bill: kept only while nobody has said whose report it is.
        printed_patient=None
        if member_id is not None
        else printed(
            age=header.patient_age,
            dob=header.patient_dob,
            phone=header.patient_phone,
            email=header.patient_email,
            address=header.patient_address,
        ),
        lab_name=header.lab_name[:200],
        patient_name=header.patient_name[:80],
        report_date=header.report_date[:40],
        page_count=len(pages),
        tests=recheck(analysis),
        summary_en=analysis.summary_en,
        summary_hi=analysis.summary_hi,
        questions_en=list(analysis.questions_en),
        questions_hi=list(analysis.questions_hi),
        urgent=analysis.urgent,
        model=settings.ocr_model,
        effort=settings.ocr_effort,
        prompt_digest=PROMPT_DIGEST,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report_out(report)


@router.get("", response_model=list[LabReportSummaryOut])
def list_lab_reports(db: Db, user: CurrentUser) -> list[LabReportSummaryOut]:
    """Every report the caller can see, newest first."""
    reports = db.scalars(
        select(LabReport)
        .where(visible_reports(user))
        .options(selectinload(LabReport.member))
        .order_by(LabReport.created_at.desc())
    ).all()
    return [summary_out(report) for report in reports]


@router.get("/{report_id}", response_model=LabReportOut, responses=ERROR_RESPONSES)
def read_lab_report(report_id: uuid.UUID, db: Db, user: CurrentUser) -> LabReportOut:
    return report_out(load_report(db, report_id, user))


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT, responses=ERROR_RESPONSES)
def delete_lab_report(report_id: uuid.UUID, db: Db, user: CurrentUser) -> Response:
    """Gone for good, for everyone following the member. Minimal retention
    means a family can always take it back: whoever added it can, and so can
    whoever added the member."""
    report = load_report(db, report_id, user)
    if user.id not in (report.user_id, report.member.created_by if report.member else None):
        raise lab_error(status.HTTP_403_FORBIDDEN, "not_report_owner")
    db.delete(report)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{report_id}/member", response_model=LabReportOut, responses=ERROR_RESPONSES)
def file_lab_report(report_id: uuid.UUID, body: FileUnder, db: Db, user: CurrentUser) -> LabReportOut:
    """Says whose report this is: someone the caller follows, or someone new,
    usually named as the report names them. As for a bill's case."""
    report = load_report(db, report_id, user)
    member = member_to_file_under(db, body, user)
    report.member_id = member.id
    report.printed_patient = None
    db.commit()
    db.refresh(report)
    return report_out(report)
