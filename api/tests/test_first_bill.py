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
    assert opened["member"] is None, "nobody has said whose it is yet"


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


def test_a_bill_that_prints_no_admission_date_leaves_it_blank(analysis):
    """The bill's own date is not the admission date, and standing it in for
    one said so on screen. A real bill printed "Date: 04/05/2025" and line
    items dated two days after it: the case read "Admitted 4 May" while the
    reader was saying, correctly, that no admission date was printed."""
    case = case_from_analysis(header(analysis, admission_date="", bill_date="23-Oct-2018"), uuid.uuid4())
    assert case.admitted_on is None


def test_a_bill_with_no_date_at_all_leaves_it_blank_too(analysis):
    """Not today's date. A family would carry that to a billing desk."""
    case = case_from_analysis(header(analysis, admission_date="", bill_date=""), uuid.uuid4())
    assert case.admitted_on is None


def test_a_discharge_date_still_closes_a_stay_with_no_start(analysis):
    """The two are read apart. A bill that prints one and not the other says
    what it says, and neither fills in for the other."""
    case = case_from_analysis(
        header(analysis, admission_date="", bill_date="", discharge_date="23-Oct-2018"), uuid.uuid4()
    )
    assert case.admitted_on is None
    assert case.closed_on == date(2018, 10, 23)


def test_the_stay_check_is_off_until_someone_says_when_it_started(analysis):
    """Nothing can be outside a stay with no start, so nothing is flagged for
    being. The app asks the family for the date instead."""
    from review import flags_from_findings

    case = case_from_analysis(header(analysis, admission_date="", bill_date=""), uuid.uuid4())
    flags = flags_from_findings(analysis, [], case.admitted_on, case.closed_on)

    assert [flag for flag in flags if flag.kind == "date_outside_stay"] == []


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


# --- a bill from a stay that is already over --------------------------------
#
# Families go through a shoebox of old bills. Dating those from the clock put
# a 2018 admission on "day 2,913" and left the patient apparently still in
# hospital, eight years on.


def past(analysis: BillAnalysis) -> BillAnalysis:
    """The Pune bill's own dates: admitted the 22nd, discharged the 23rd."""
    return header(
        analysis,
        admission_date="22-Oct-18 10:45 AM",
        discharge_date="23-Oct-18 6:30 PM",
        bill_date="23-Oct-18",
    )


def test_the_stay_ends_where_the_bill_says_it_ended(analysis):
    case = case_from_analysis(past(analysis), uuid.uuid4())

    assert case.admitted_on == date(2018, 10, 22)
    assert case.closed_on == date(2018, 10, 23)


def test_a_bill_is_dated_from_the_bill(analysis):
    """Not from the day it was photographed."""
    from bills import bill_day

    assert bill_day(past(analysis), None) == date(2018, 10, 23)


def test_a_date_the_uploader_gives_still_wins(analysis):
    """The form field is the override for a bill whose own date can't be read."""
    from bills import bill_day

    assert bill_day(past(analysis), date(2018, 10, 22)) == date(2018, 10, 22)


def test_an_undated_bill_falls_back_to_today(analysis):
    from bills import bill_day
    from db import india_today

    assert bill_day(header(analysis, bill_date=""), None) == india_today()


# --- deciding whether the stay is still going -------------------------------


def test_a_discharge_date_settles_it(analysis):
    case = case_from_analysis(
        header(analysis, admission_date="22-Oct-18", discharge_date="25-Oct-18", bill_date="23-Oct-18"),
        uuid.uuid4(),
    )
    assert case.closed_on == date(2018, 10, 25), "the discharge, even past the bill's own date"


def test_an_old_bill_with_no_discharge_date_leaves_the_stay_open(analysis):
    """A bill that does not say when the stay ended does not get to decide.

    This used to close the case on the bill's own date, which reads as modest
    -- the last day the stay is known to have reached -- and is not, because
    `closed_on` is the upper bound of the stay check. An interim bill dated
    the day of admission made the stay one day long and every later charge on
    it "may belong to another visit".
    """
    case = case_from_analysis(
        header(analysis, admission_date="22-Oct-18", discharge_date="", bill_date="23-Oct-18"),
        uuid.uuid4(),
    )
    assert case.closed_on is None


def test_a_printed_discharge_date_still_closes_the_stay(analysis):
    case = case_from_analysis(
        header(analysis, admission_date="22-Oct-18", discharge_date="25-Oct-18", bill_date="23-Oct-18"),
        uuid.uuid4(),
    )
    assert case.closed_on == date(2018, 10, 25)


def test_a_bill_from_today_leaves_the_stay_open(analysis):
    """Someone at a counter during an admission, which is what the daily-bill
    flow is for. This is the one case where the patient really is still in."""
    from db import india_today

    today = india_today().strftime("%d-%b-%y")
    case = case_from_analysis(
        header(analysis, admission_date="", discharge_date="", bill_date=today), uuid.uuid4()
    )
    assert case.closed_on is None


def test_a_bill_with_no_dates_at_all_leaves_the_stay_open(analysis):
    """Nothing read means nothing known, and closing a live admission is the
    worse of the two mistakes: it takes the family out of the daily flow."""
    case = case_from_analysis(
        header(analysis, admission_date="", discharge_date="", bill_date=""), uuid.uuid4()
    )
    assert case.closed_on is None


def test_a_stay_never_ends_before_it_starts(analysis):
    """A misread discharge date must not make the arithmetic negative."""
    case = case_from_analysis(
        header(analysis, admission_date="23-Oct-18", discharge_date="22-Oct-18", bill_date="23-Oct-18"),
        uuid.uuid4(),
    )
    assert case.closed_on == date(2018, 10, 23)


def test_a_family_can_say_the_patient_is_still_in(client: TestClient, auth_headers: dict):
    """Closing the case from the bill is a reading, not a verdict. Before this
    there was no way back: `close` only closed."""
    bill = check_first_bill(client, auth_headers)
    case_id = bill["case_id"]
    client.patch(f"/cases/{case_id}", json={"closed_on": "2026-10-11"}, headers=auth_headers)
    assert client.get(f"/cases/{case_id}", headers=auth_headers).json()["closed_on"] == "2026-10-11"

    reopened = client.patch(f"/cases/{case_id}", json={"closed_on": None}, headers=auth_headers)

    assert reopened.status_code == 200
    assert reopened.json()["closed_on"] is None


def test_an_interim_bill_does_not_flag_the_days_it_covers(analysis):
    """The whole bug, on the path it actually took.

    A real bill: OLIVE Multispeciality, admitted 4 May 2025, interim bill
    dated the same day, no discharge printed. `closed_on` was guessed from the
    bill's own date, so the stay came out one day long, and every charge the
    bill covered after that day was returned as "may belong to another visit"
    -- most of the rows on it. An interim bill is issued during a stay; the
    date it carries is not the day the patient left.

    Both halves together, because neither is wrong on its own: the guess only
    does damage once it reaches the stay check, which is how it survived.
    """
    from analysis import AnalysedLine
    from review import flags_from_findings

    def row(line_id: str, name: str, amount: float, on: str) -> AnalysedLine:
        return AnalysedLine(
            line_id=line_id,
            description_verbatim=name,
            category="unclassified",
            quantity=None,
            unit="",
            rate=None,
            amount=amount,
            net_amount=None,
            date=on,
            mrp_printed=None,
        )

    interim = header(
        analysis,
        admission_date="04/05/2025",
        discharge_date="",
        bill_date="04/05/2025",
    ).model_copy(
        update={
            "lines": [
                row("L1", "Complete Blood Count-CBC", 300, "04/05/2025"),
                row("L2", "Room rent", 4500, "05/05/2025"),
                row("L3", "DOCTOR VISIT CHARGES", 4500, "06/05/2025"),
                row("L4", "Nursing charges", 1200, "07/05/2025"),
            ]
        }
    )

    case = case_from_analysis(interim, uuid.uuid4())
    assert case.closed_on is None, "no discharge date was printed on it"

    # Exactly what bills.py hands the review.
    flags = flags_from_findings(interim, [], case.admitted_on, case.closed_on)
    assert [flag for flag in flags if flag.kind == "date_outside_stay"] == []
