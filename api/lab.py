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

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select

from auth import CurrentUser, Db
from bills import MAX_PAGES, check_upload_limit, read_page
from db import utcnow
from lab_analysis import LabAnalysis, recheck
from lab_prompt import PROMPT_DIGEST
from models import LabConsent, LabReportOut, LabReportSummaryOut, LabTestOut
from ocr import OcrError, OcrProvider, get_ocr_provider
from settings import get_settings
from tables import LabReport, User

router = APIRouter(prefix="/lab-reports", tags=["lab reports"])

logger = logging.getLogger("billcheck.lab")

# Which consent text was agreed to. Change it when the words in the app do.
LAB_CONSENT_VERSION = "2026-10-lab"

ERRORS = {
    "lab_consent_required": "Agree to lab reports being stored and explained first.",
    "lab_report_not_found": "This report isn't available.",
    "no_pages": "Add at least one page of the report.",
    "too_many_pages": f"A report can have up to {MAX_PAGES} pages.",
    "unreadable_lab_report": "This report couldn't be read. Try again in better light, one page at a time.",
}

ERROR_RESPONSES: dict[int | str, dict] = {
    403: {"description": "lab_consent_required"},
    404: {"description": "lab_report_not_found"},
    422: {"description": "unreadable_lab_report"},
}


def lab_error(status_code: int, code: str) -> HTTPException:
    return HTTPException(status_code, detail={"code": code, "message": ERRORS[code]})


def report_out(report: LabReport) -> LabReportOut:
    return LabReportOut(
        id=report.id,
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


def load_report(db: Db, report_id: uuid.UUID, user: User) -> LabReport:
    """The report, if it is theirs. Someone else's is not found, not forbidden:
    an id must not tell anyone whether a stranger has had blood taken."""
    report = db.get(LabReport, report_id)
    if report is None or report.user_id != user.id:
        raise lab_error(status.HTTP_404_NOT_FOUND, "lab_report_not_found")
    return report


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
) -> LabReportOut:
    """Reads a lab report and explains it, in English and in Hindi.

    Counts against the same daily allowance as bills: both are a paid read.
    A report that can't be read leaves nothing behind.
    """
    if not user.lab_consent:
        raise lab_error(status.HTTP_403_FORBIDDEN, "lab_consent_required")
    if not pages:
        raise lab_error(status.HTTP_400_BAD_REQUEST, "no_pages")
    if len(pages) > MAX_PAGES:
        raise lab_error(status.HTTP_400_BAD_REQUEST, "too_many_pages")

    images = [await read_page(page, index) for index, page in enumerate(pages, start=1)]
    check_upload_limit(db, user.id)

    try:
        # As with a bill, a blocking call that can take most of a minute.
        analysis: LabAnalysis = await run_in_threadpool(ocr.read_lab_report, images)
    except OcrError as exc:
        logger.warning("Couldn't read a lab report for user %s: %s", user.id, exc)
        raise lab_error(status.HTTP_422_UNPROCESSABLE_CONTENT, "unreadable_lab_report") from exc
    finally:
        del images

    settings = get_settings()
    header = analysis.report
    report = LabReport(
        user_id=user.id,
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
    """Their reports, newest first."""
    reports = db.scalars(
        select(LabReport).where(LabReport.user_id == user.id).order_by(LabReport.created_at.desc())
    ).all()
    return [
        LabReportSummaryOut(
            id=report.id,
            lab_name=report.lab_name,
            report_date=report.report_date,
            test_count=len(report.tests),
            outside_range=sum(1 for test in report.tests if test.get("status") in ("low", "high")),
            urgent=report.urgent,
            created_at=report.created_at,
        )
        for report in reports
    ]


@router.get("/{report_id}", response_model=LabReportOut, responses=ERROR_RESPONSES)
def read_lab_report(report_id: uuid.UUID, db: Db, user: CurrentUser) -> LabReportOut:
    return report_out(load_report(db, report_id, user))


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT, responses=ERROR_RESPONSES)
def delete_lab_report(report_id: uuid.UUID, db: Db, user: CurrentUser) -> Response:
    """Gone for good. Minimal retention means a family can always take it back."""
    db.delete(load_report(db, report_id, user))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
