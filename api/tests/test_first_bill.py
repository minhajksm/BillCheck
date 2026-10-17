"""Checking a bill with no case behind it.

The way in for a family standing at a counter with a bill in their hand and
nothing set up. Everything a case needs -- the hospital, the admission date,
the patient, the IP number -- is printed on the bill they are holding, so
asking them to type it first is asking twice.

What these tests are really about is the line between reading and inventing.
A case is the record of a real admission; a plausible-looking guess in one is
worse than a blank, because a family would carry it to a billing desk.
"""

import io
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from analysis import BillAnalysis
from bills import case_from_analysis
from tests.test_cases_and_bills import JPEG, page


def check_first_bill(client: TestClient, headers: dict, **form) -> dict:
    response = client.post("/bills", files=[page()], data=form or None, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


# --- the way in --------------------------------------------------------------


def test_a_bill_on_its_own_opens_a_case(client: TestClient, auth_headers: dict):
    assert client.get("/cases", headers=auth_headers).json() == [], "nothing set up"

    bill = check_first_bill(client, auth_headers)

    (opened,) = client.get("/cases", headers=auth_headers).json()
    assert opened["id"] == bill["case_id"]
    assert len(bill["line_items"]) == 11, "and the bill is read in the same request"


def test_the_case_is_filled_in_from_the_bill(client: TestClient, auth_headers: dict):
    """Nothing typed, and nothing invented: every field is the reader's own
    transcription of the page."""
    bill = check_first_bill(client, auth_headers)
    opened = client.get(f"/cases/{bill['case_id']}", headers=auth_headers).json()

    assert opened["hospital_name"] == "City Care Hospital"
    assert opened["patient_name"] == "Ramesh Sharma"
    assert opened["ip_number"] == "IP/2026/4417"
    assert opened["title"] == "Ramesh Sharma", "the bill's own words, so nothing of ours needs translating"


def test_whoever_checked_the_bill_owns_the_case(client: TestClient, auth_headers: dict):
    bill = check_first_bill(client, auth_headers)
    opened = client.get(f"/cases/{bill['case_id']}", headers=auth_headers).json()

    assert opened["is_owner"], "they can delete it, as with any case they started"
    assert [member["is_you"] for member in opened["members"]] == [True]


def test_the_bill_is_checked_as_any_other_would_be(client: TestClient, auth_headers: dict):
    """Same reading, same price lists, same flags. Only the case is new."""
    bill = check_first_bill(client, auth_headers)

    assert bill["total"] == 42490
    kinds = [flag["kind"] for flag in bill["flags"]]
    assert "above_mrp" in kinds and "analysis_finding" in kinds


def test_an_unreadable_bill_leaves_no_empty_case_behind(
    client: TestClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
):
    """The case is written only once the bill reads. Otherwise a family's list
    fills up with cases they never made and cannot explain."""
    from ocr import OcrError, StubOcr, get_ocr_provider

    def refuse(self, pages):
        raise OcrError("This is not a hospital bill.")

    monkeypatch.setattr(StubOcr, "read_bill", refuse)
    get_ocr_provider.cache_clear()

    response = client.post("/bills", files=[page()], headers=auth_headers)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "unreadable_bill"
    assert client.get("/cases", headers=auth_headers).json() == [], "no case to clean up"
    get_ocr_provider.cache_clear()


def test_a_second_bill_goes_on_the_case_that_is_there(client: TestClient, auth_headers: dict):
    """Checking a bill the hard way still works, and is how day 2 arrives."""
    first = check_first_bill(client, auth_headers)
    second = client.post(f"/cases/{first['case_id']}/bills", files=[page()], headers=auth_headers)

    assert second.status_code == 201
    assert second.json()["case_id"] == first["case_id"]
    assert len(client.get("/cases", headers=auth_headers).json()) == 1, "one admission, one case"


def test_it_needs_a_page_like_any_other_upload(client: TestClient, auth_headers: dict):
    response = client.post(
        "/bills", files=[("pages", ("x.txt", io.BytesIO(b"hello"), "text/plain"))], headers=auth_headers
    )
    assert response.status_code == 415


def test_someone_else_cannot_see_the_case_it_opened(client: TestClient, auth_headers: dict, sms):
    from tests.conftest import sign_up
    from tests.test_cases_and_bills import headers_for

    bill = check_first_bill(client, auth_headers)
    other = headers_for(sign_up(client, sms, phone="+919123456780", name="Someone Else"))

    assert client.get(f"/cases/{bill['case_id']}", headers=other).status_code == 404
    assert client.get("/cases", headers=other).json() == []


# --- what the case is built from, line by line ------------------------------
#
# `case_from_analysis` is where a transcription becomes a record of someone's
# admission, so each field is checked on its own.


def header(analysis: BillAnalysis, **changes) -> BillAnalysis:
    return analysis.model_copy(update={"bill": analysis.bill.model_copy(update=changes)})


@pytest.fixture
def analysis() -> BillAnalysis:
    from ocr import BillPage, StubOcr

    return StubOcr().read_bill([BillPage(data=JPEG, content_type="image/jpeg")])


def test_the_hospital_s_name_is_split_from_its_address(analysis):
    """Bills print the lot on one line. The name comes first."""
    case = case_from_analysis(
        header(analysis, hospital="Sample Polyclinic, 12/4, Example Road, Pune - 411023"),
        uuid.uuid4(),
    )
    assert case.hospital_name == "Sample Polyclinic"
    assert case.hospital_area == "12/4, Example Road, Pune - 411023"


def test_a_hospital_with_no_address_still_has_a_name(analysis):
    case = case_from_analysis(header(analysis, hospital="City Care Hospital"), uuid.uuid4())
    assert case.hospital_name == "City Care Hospital"
    assert case.hospital_area == ""


def test_the_admission_date_is_what_the_stay_is_counted_from(analysis):
    case = case_from_analysis(header(analysis, admission_date="22-10-2018"), uuid.uuid4())
    assert case.admitted_on == date(2018, 10, 22)


def test_the_bill_s_own_date_stands_in_for_an_unprinted_admission(analysis):
    """Many interim bills print no admission date. Dating the stay from the
    bill is wrong by at most the length of the stay; dating it from today
    would make every line of an old bill fall outside it."""
    case = case_from_analysis(header(analysis, admission_date="", bill_date="23-Oct-2018"), uuid.uuid4())
    assert case.admitted_on == date(2018, 10, 23)


def test_a_bill_with_no_date_at_all_is_dated_today(analysis):
    from db import india_today

    case = case_from_analysis(header(analysis, admission_date="", bill_date=""), uuid.uuid4())
    assert case.admitted_on == india_today()


def test_a_patient_the_bill_does_not_name_is_left_blank(analysis):
    """Not "Unknown", not the account holder's name. The family fills it in,
    and until they do the app shows its own placeholder in their language."""
    case = case_from_analysis(header(analysis, patient_name="", ip_number=""), uuid.uuid4())
    assert case.patient_name == ""
    assert case.ip_number == ""
    assert case.title == "City Care Hospital", "the hospital, so the case is findable in a list"


def test_the_fields_are_cut_to_what_the_columns_hold(analysis):
    """A reader that transcribes a whole letterhead into one field must not
    fail the insert."""
    case = case_from_analysis(
        header(analysis, hospital="H" * 400, patient_name="P" * 400, ip_number="I" * 400),
        uuid.uuid4(),
    )
    assert len(case.hospital_name) == 120
    assert len(case.patient_name) == 80
    assert len(case.ip_number) == 40


def test_no_bed_is_claimed(analysis):
    """A bill prints a bed number, but the patient moves. It is left for the
    family, who know where they are."""
    assert case_from_analysis(analysis, uuid.uuid4()).bed is None
