"""What the reader did with a bill, kept so it can be judged later.

None of this is served to anybody. It answers the two questions a reader has
to be asked if it is ever going to get better -- how often does it lose its
own line numbering, and did the last prompt change help -- which used to be
answerable only from Cloud Run's logs, which is to say not answerable.
"""

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from analysis_prompt import PROMPT_DIGEST
from review import DROPPED_LOW_SEVERITY, DROPPED_UNKNOWN_LINES, SHOWN
from tables import BillRead, Flag, ReaderFinding
from tests.test_cases_and_bills import page


def upload(client: TestClient, headers: dict) -> dict:
    response = client.post("/bills", files=[page()], headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def readings(db: Session) -> list[BillRead]:
    return list(db.scalars(select(BillRead)))


def recorded(db: Session) -> list[ReaderFinding]:
    return list(db.scalars(select(ReaderFinding).order_by(ReaderFinding.finding_id)))


# --- the reading -------------------------------------------------------------


def test_a_bill_records_what_read_it(client: TestClient, auth_headers: dict, db: Session):
    """Without the model, the effort and the prompt on the row, a month of
    worse readings cannot be told from a month of worse bills."""
    upload(client, auth_headers)

    (read,) = readings(db)
    assert read.provider == "stub"
    assert read.model == "claude-haiku-5-5"
    assert read.effort == "low"
    assert read.prompt_digest == PROMPT_DIGEST
    assert len(read.prompt_digest) == 16, "short enough to group by"


def test_the_reader_s_own_account_of_the_reading_is_kept(client: TestClient, auth_headers: dict, db: Session):
    """How sure it was, whether it asked for a human, and the shape it found.
    All four were parsed and dropped on the floor before."""
    upload(client, auth_headers)

    (read,) = readings(db)
    assert read.extraction_confidence == Decimal("0.900")
    assert read.needs_human_review is False
    assert read.review_reasons == []
    assert read.consumable_share_pct == Decimal("18.90")
    assert read.unreadable_line_count == 0
    assert read.lines_read == 11
    assert read.pages_processed == 1


def test_the_count_shown_is_the_count_a_family_saw(client: TestClient, auth_headers: dict, db: Session):
    bill = upload(client, auth_headers)

    (read,) = readings(db)
    assert read.findings_returned == 2
    assert read.findings_shown == 2
    reader_flags = [flag for flag in bill["flags"] if flag["kind"] == "analysis_finding"]
    assert len(reader_flags) == read.findings_shown


# --- every finding, shown or not ---------------------------------------------


def test_every_finding_is_recorded_with_the_reader_s_own_words(
    client: TestClient, auth_headers: dict, db: Session
):
    upload(client, auth_headers)

    first, second = recorded(db)
    assert first.rule == "B. billed rate above printed MRP"
    assert first.severity == "high"
    assert first.outcome == SHOWN
    assert "MRP of Rs 1,840" in first.statement
    assert first.evidence == "Inj. Meropenem 1g — rate 2,950 — MRP 1,840"
    assert first.confirmation_required == "The MRP printed on the pack supplied."
    assert second.line_ids == "L3,L4", "every line it named, not just the one it hangs on"
    assert second.line_numbers == "3,4"


def test_a_shown_finding_reaches_the_flag_a_family_answered(
    client: TestClient, auth_headers: dict, db: Session
):
    """The family's verdict is the only judgement of a finding worth having,
    and it lives on the flag. This is the join to it."""
    bill = upload(client, auth_headers)
    flag = next(one for one in bill["flags"] if one["kind"] == "analysis_finding")
    assert (
        client.patch(f"/flags/{flag['id']}", json={"status": "explained"}, headers=auth_headers).status_code
        == 200
    )

    found = db.scalars(select(ReaderFinding).where(ReaderFinding.flag_id == uuid.UUID(flag["id"]))).one()
    assert found.outcome == SHOWN
    answered = db.get(Flag, found.flag_id)
    assert answered is not None and answered.status == "explained"


def test_a_finding_the_family_never_saw_is_still_recorded(
    client: TestClient, auth_headers: dict, db: Session, monkeypatch: pytest.MonkeyPatch
):
    """REVIEW_KEEP_ALL off drops what the reader itself called low severity.
    Dropped from the report, not from the record: how often it fires, and on
    what, is exactly what tuning the prompt needs to know."""
    import ocr
    from settings import get_settings

    monkeypatch.setenv("REVIEW_KEEP_ALL", "false")
    get_settings.cache_clear()
    plain = ocr.StubOcr.read_bill

    def read(self, pages):
        analysis = plain(self, pages)
        findings = [one.model_copy(update={"severity": "low"}) for one in analysis.findings]
        return analysis.model_copy(update={"findings": findings})

    monkeypatch.setattr(ocr.StubOcr, "read_bill", read)
    try:
        bill = upload(client, auth_headers)
    finally:
        get_settings.cache_clear()

    assert [one for one in bill["flags"] if one["kind"] == "analysis_finding"] == [], "none shown"
    (read_row,) = readings(db)
    assert read_row.findings_returned == 2
    assert read_row.findings_shown == 0
    assert [one.outcome for one in recorded(db)] == [DROPPED_LOW_SEVERITY] * 2
    assert all(one.flag_id is None for one in recorded(db)), "no flag to point at"


def test_a_reader_that_loses_its_own_numbering_is_recorded_as_such(
    client: TestClient, auth_headers: dict, db: Session, monkeypatch: pytest.MonkeyPatch
):
    """A finding naming lines that aren't in its own transcription. The family
    is shown nothing, and "how often does this happen" is now a GROUP BY."""
    import ocr

    plain = ocr.StubOcr.read_bill

    def read(self, pages):
        analysis = plain(self, pages)
        lost = analysis.findings[0].model_copy(update={"line_ids": ["L99"]})
        return analysis.model_copy(update={"findings": [lost, analysis.findings[1]]})

    monkeypatch.setattr(ocr.StubOcr, "read_bill", read)
    upload(client, auth_headers)

    first, second = recorded(db)
    assert first.outcome == DROPPED_UNKNOWN_LINES
    assert first.line_ids == "L99", "what it said, so it can be read back"
    assert first.line_numbers == "", "and nothing on the bill it landed on"
    assert second.outcome == SHOWN


# --- and no separate lifetime to remember ------------------------------------


def test_deleting_the_case_takes_the_reading_with_it(client: TestClient, auth_headers: dict, db: Session):
    """DPDP minimal retention: there is nothing here to purge on its own."""
    bill = upload(client, auth_headers)
    assert readings(db) and recorded(db)

    assert client.delete(f"/cases/{bill['case_id']}", headers=auth_headers).status_code == 204

    db.expire_all()
    assert readings(db) == []
    assert recorded(db) == []
