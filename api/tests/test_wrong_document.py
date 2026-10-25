"""A document that reads fine and is something else.

A scan report sent as a lab report, a prescription sent as a bill. Telling
the family to retake it "in better light" sends them to fix the wrong thing:
the photo was fine. They are told what it looks like instead, by its own
title, and nothing is kept.
"""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import ocr
from analysis_prompt import PROMPT as BILL_PROMPT
from lab_prompt import PROMPT as LAB_PROMPT
from ocr import OcrError, WrongDocument, _parse, _parse_lab
from tables import Case, LabReport
from tests.test_cases_and_bills import page

# The reader's actual answer to an obstetric ultrasound report, word for word.
ULTRASOUND = (
    "This document is an obstetric ultrasound scan report (OB 2/3 Trimester Scan Report from a "
    "diagnostic centre), not a laboratory report. This tool only explains laboratory reports. Please "
    "take this scan report to the doctor who referred the patient."
)


def answer(**fields) -> str:
    return json.dumps(fields)


def test_the_reader_s_sentence_about_a_scan_report_is_understood():
    with pytest.raises(WrongDocument) as caught:
        _parse_lab(answer(error=ULTRASOUND))
    assert caught.value.document == "", "a sentence carries no title to show"


def test_the_code_carries_the_page_s_own_title():
    with pytest.raises(WrongDocument) as caught:
        _parse_lab(answer(error="not_a_lab_report", document="OB 2/3 Trimester Scan Report"))
    assert caught.value.document == "OB 2/3 Trimester Scan Report"


def test_a_title_is_kept_short():
    with pytest.raises(WrongDocument) as caught:
        _parse_lab(answer(error="not_a_lab_report", document="x" * 500))
    assert len(caught.value.document) == 120


@pytest.mark.parametrize(
    "error",
    ["not_a_bill", "This is a prescription, not a hospital bill.", "The page is not an itemised bill."],
)
def test_a_bill_that_is_something_else(error: str):
    with pytest.raises(WrongDocument):
        _parse(answer(error=error, needs_human_review=True))


@pytest.mark.parametrize("error", ["unreadable", "The image is too blurred to read."])
def test_a_page_that_can_t_be_read_is_still_that(error: str):
    with pytest.raises(OcrError) as caught:
        _parse_lab(answer(error=error))
    assert not isinstance(caught.value, WrongDocument), "retaking the photo is the right advice here"


@pytest.mark.parametrize("prompt, code", [(BILL_PROMPT, "not_a_bill"), (LAB_PROMPT, "not_a_lab_report")])
def test_both_readers_are_asked_for_the_code_and_the_title(prompt: str, code: str):
    assert f'"error": "{code}"' in prompt
    assert '"document"' in prompt
    assert '"error": "unreadable"' in prompt


def test_a_scan_report_sent_as_a_lab_report_says_so_and_keeps_nothing(
    client: TestClient, auth_headers: dict, db: Session, monkeypatch: pytest.MonkeyPatch
):
    def wrong(self, pages):
        raise WrongDocument("not_a_lab_report", document="OB 2/3 Trimester Scan Report")

    monkeypatch.setattr(ocr.StubOcr, "read_lab_report", wrong)
    client.post("/lab-reports/consent", json={"consent": True}, headers=auth_headers)
    response = client.post("/lab-reports", files=[page()], headers=auth_headers)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "not_a_lab_report"
    assert response.json()["detail"]["document"] == "OB 2/3 Trimester Scan Report"
    assert db.scalar(select(func.count()).select_from(LabReport)) == 0


def test_a_lab_report_sent_as_a_bill_says_so_and_opens_no_case(
    client: TestClient, auth_headers: dict, db: Session, monkeypatch: pytest.MonkeyPatch
):
    def wrong(self, pages):
        raise WrongDocument("not_a_bill", document="Complete Blood Count")

    monkeypatch.setattr(ocr.StubOcr, "read_bill", wrong)
    response = client.post("/bills", files=[page()], headers=auth_headers)

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "not_a_bill",
        "message": "This doesn't look like a hospital bill.",
        "document": "Complete Blood Count",
    }
    assert db.scalar(select(func.count()).select_from(Case)) == 0
