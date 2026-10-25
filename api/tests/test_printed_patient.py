"""The patient's details as a page prints them, offered when it is filed.

A family scanning a bill before saying whose it is gets the answer offered
back: the name, the age, the mobile and the address are usually on the page.
What is offered has to hold up -- a real date of birth, an Indian mobile, a
valid email -- and nothing is worked out from anything else. Once filed, the
page's copy is dropped.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from analysis_prompt import PROMPT as BILL_PROMPT
from lab_prompt import PROMPT as LAB_PROMPT
from printed_patient import printed, suggestion
from tables import Case, LabReport, Member
from tests.test_cases_and_bills import new_member, page

# --- what the page printed, made into a suggestion ---------------------------


@pytest.mark.parametrize(
    "printed_age, years",
    [("68", 68), ("68 Yrs", 68), ("68Y 3M", 68), ("68 years", 68), ("45 Y", 45), ("68 yrs.", 68)],
)
def test_an_age_is_read_in_the_ways_pages_print_it(printed_age: str, years: int):
    assert suggestion({"age": printed_age}, "Papa").age == years  # type: ignore[union-attr]


@pytest.mark.parametrize("printed_age", ["6 M", "6 months", "10 days", "6M", "150", "Adult", ""])
def test_a_baby_s_months_are_never_read_as_years(printed_age: str):
    suggested = suggestion({"age": printed_age}, "Baby")
    assert suggested is not None and suggested.age is None


def test_an_age_is_never_turned_into_a_date_of_birth():
    suggested = suggestion({"age": "68 Yrs"}, "Papa")
    assert suggested is not None and suggested.date_of_birth is None


def test_a_date_of_birth_only_where_it_is_one_in_the_past():
    assert suggestion({"dob": "14/03/1958"}, "Papa").date_of_birth == date(1958, 3, 14)  # type: ignore[union-attr]
    # A two-digit year can't be placed: "58" reads as 2058, which is no birth.
    assert suggestion({"dob": "14/03/58"}, "Papa").date_of_birth is None  # type: ignore[union-attr]
    assert suggestion({"dob": "not printed"}, "Papa").date_of_birth is None  # type: ignore[union-attr]


def test_only_an_indian_mobile_is_offered_as_the_phone():
    assert suggestion({"phone": "98765 43210"}, "Papa").phone == "+919876543210"  # type: ignore[union-attr]
    assert suggestion({"phone": "020-2567 1234"}, "Papa").phone is None  # type: ignore[union-attr]


def test_an_email_only_where_it_is_one():
    assert suggestion({"email": "Papa@Example.com"}, "Papa").email == "papa@example.com"  # type: ignore[union-attr]
    assert suggestion({"email": "papa at example"}, "Papa").email is None  # type: ignore[union-attr]


def test_an_address_is_kept_to_what_a_member_holds():
    assert len(suggestion({"address": "x" * 500}, "Papa").address or "") == 300  # type: ignore[union-attr]


def test_a_page_that_printed_nothing_suggests_nothing():
    assert printed(age="", dob="  ", phone="", email="", address="") is None
    assert suggestion(None, "") is None
    assert suggestion(None, "Ramesh Sharma").name == "Ramesh Sharma"  # type: ignore[union-attr]


@pytest.mark.parametrize("prompt", [BILL_PROMPT, LAB_PROMPT])
def test_both_readers_are_asked_for_the_patient_s_details_and_not_the_hospital_s(prompt: str):
    for key in ("patient_age", "patient_dob", "patient_phone", "patient_email", "patient_address"):
        assert f'"{key}"' in prompt, key
    assert "not the patient's" in prompt
    assert "Never work one out from another" in prompt or "Never work\none out from another" in prompt


# --- end to end --------------------------------------------------------------


def scan_bill(client: TestClient, headers: dict, **form) -> dict:
    response = client.post("/bills", files=[page()], data=form or None, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_a_bill_scanned_first_offers_who_it_is_about(client: TestClient, auth_headers: dict):
    bill = scan_bill(client, auth_headers)

    case = client.get(f"/cases/{bill['case_id']}", headers=auth_headers).json()
    assert case["suggested_member"] == {
        "name": "Ramesh Sharma",
        "date_of_birth": None,
        "age": 68,
        "phone": "+919876543210",
        "email": None,
        "address": "12 Example Road, Andheri, Mumbai 400058",
    }


def test_a_bill_scanned_from_a_member_keeps_no_copy(client: TestClient, auth_headers: dict, db: Session):
    papa = new_member(client, auth_headers)
    bill = scan_bill(client, auth_headers, member_id=papa["id"])

    assert client.get(f"/cases/{bill['case_id']}", headers=auth_headers).json()["suggested_member"] is None
    assert db.scalars(select(Case)).one().printed_patient is None


def test_someone_new_takes_the_details_accepted(client: TestClient, auth_headers: dict, db: Session):
    bill = scan_bill(client, auth_headers)

    filed = client.post(
        f"/cases/{bill['case_id']}/member",
        json={
            "new_member_name": "Ramesh Sharma",
            "details": {"phone": "+919876543210", "address": "12 Example Road, Andheri, Mumbai 400058"},
        },
        headers=auth_headers,
    ).json()

    member = client.get(f"/members/{filed['member']['id']}", headers=auth_headers).json()
    assert member["phone"] == "+919876543210"
    assert member["address"] == "12 Example Road, Andheri, Mumbai 400058"
    assert filed["suggested_member"] is None
    assert db.scalars(select(Case)).one().printed_patient is None, "dropped once filed"


def test_someone_already_there_gains_only_what_they_lack(client: TestClient, auth_headers: dict):
    papa = client.post("/members", json={"name": "Papa", "phone": "9123456780"}, headers=auth_headers).json()
    bill = scan_bill(client, auth_headers)

    client.post(
        f"/cases/{bill['case_id']}/member",
        json={"member_id": papa["id"], "details": {"phone": "+919876543210", "address": "12 Example Road"}},
        headers=auth_headers,
    )

    member = client.get(f"/members/{papa['id']}", headers=auth_headers).json()
    assert member["phone"] == "+919123456780", "what the family typed is never replaced"
    assert member["address"] == "12 Example Road"


def test_details_accepted_are_checked_like_any_other(client: TestClient, auth_headers: dict):
    bill = scan_bill(client, auth_headers)
    response = client.post(
        f"/cases/{bill['case_id']}/member",
        json={"new_member_name": "Papa", "details": {"phone": "12345"}},
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_filing_without_the_details_drops_them_too(client: TestClient, auth_headers: dict, db: Session):
    bill = scan_bill(client, auth_headers)
    client.post(f"/cases/{bill['case_id']}/member", json={"new_member_name": "Papa"}, headers=auth_headers)

    assert db.scalars(select(Member)).one().phone is None, "declined, so not added"
    assert db.scalars(select(Case)).one().printed_patient is None


def test_a_lab_report_scanned_first_offers_who_it_is_about(
    client: TestClient, auth_headers: dict, db: Session
):
    client.post("/lab-reports/consent", json={"consent": True}, headers=auth_headers)
    report = client.post("/lab-reports", files=[page()], headers=auth_headers).json()

    assert report["suggested_member"]["age"] == 45
    assert report["suggested_member"]["name"] == "TEST PATIENT"

    client.post(f"/lab-reports/{report['id']}/member", json={"new_member_name": "Papa"}, headers=auth_headers)
    assert db.scalars(select(LabReport)).one().printed_patient is None
