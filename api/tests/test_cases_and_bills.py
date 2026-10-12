"""Cases, bill upload, and tracking what the hospital said.

Uploads use the stub OCR, so these exercise the whole path — pages in, line
items and flags out — without a key or a real bill.
"""

import io
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from tests.conftest import FakeSms, sign_up

# A one-pixel JPEG: enough for the upload to sniff a real image type.
JPEG = bytes.fromhex("ffd8ffe000104a46494600010100000100010000ffdb004300ff") + b"\x00" * 64


def page(name: str = "page1.jpg") -> tuple[str, tuple[str, io.BytesIO, str]]:
    return ("pages", (name, io.BytesIO(JPEG), "image/jpeg"))


def new_case(client: TestClient, headers: dict, **overrides) -> dict:
    body = {
        "title": "Papa's admission",
        "hospital_name": "City Care Hospital",
        "hospital_area": "Andheri",
        "patient_name": "Ramesh Sharma",
        "ip_number": "20841",
        "bed": "412",
        "admitted_on": str(date.today() - timedelta(days=2)),
    } | overrides
    response = client.post("/cases", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


# --- cases -------------------------------------------------------------------


def test_creates_a_case_with_its_creator_as_a_member(client: TestClient, auth_headers: dict):
    created = new_case(client, auth_headers)

    assert created["title"] == "Papa's admission"
    assert created["day_of_stay"] == 3, "admitted the day before yesterday is day 3"
    assert [m["name"] for m in created["members"]] == ["Rohan Sharma"]
    assert created["members"][0]["is_you"] is True
    assert created["bills"] == []
    assert created["recovered_amount"] == 0


def test_lists_only_your_own_cases(client: TestClient, auth_headers: dict, sms: FakeSms):
    new_case(client, auth_headers, title="Papa's admission")

    other = sign_up(client, sms, phone="+919123456780", name="Someone Else")
    other_headers = {"Authorization": f"Bearer {other['token']}"}

    assert [c["title"] for c in client.get("/cases", headers=auth_headers).json()] == ["Papa's admission"]
    assert client.get("/cases", headers=other_headers).json() == []


def test_a_case_you_do_not_follow_reads_as_missing(client: TestClient, auth_headers: dict, sms: FakeSms):
    """Not 403: whether a patient is in hospital isn't something an id should
    be able to confirm."""
    case = new_case(client, auth_headers)
    other = sign_up(client, sms, phone="+919123456780", name="Someone Else")

    response = client.get(f"/cases/{case['id']}", headers={"Authorization": f"Bearer {other['token']}"})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "case_not_found"


def test_family_joins_from_the_invite_link(client: TestClient, auth_headers: dict, sms: FakeSms):
    case = new_case(client, auth_headers)
    anita = sign_up(client, sms, phone="+919123456780", name="Anita Sharma")
    anita_headers = {"Authorization": f"Bearer {anita['token']}"}

    joined = client.post(f"/cases/{case['id']}/join", headers=anita_headers)
    assert joined.status_code == 200
    assert sorted(m["name"] for m in joined.json()["members"]) == ["Anita Sharma", "Rohan Sharma"]

    # And now she can see it like any other member.
    assert client.get(f"/cases/{case['id']}", headers=anita_headers).status_code == 200


def test_joining_twice_is_harmless(client: TestClient, auth_headers: dict):
    case = new_case(client, auth_headers)
    again = client.post(f"/cases/{case['id']}/join", headers=auth_headers)
    assert again.status_code == 200
    assert len(again.json()["members"]) == 1


def test_closing_a_case_stops_the_day_count(client: TestClient, auth_headers: dict):
    case = new_case(client, auth_headers)
    closed = client.post(f"/cases/{case['id']}/close", headers=auth_headers).json()

    assert closed["closed_on"] == str(date.today())
    assert closed["day_of_stay"] == 3


def test_cases_need_a_signed_in_user(client: TestClient):
    assert client.get("/cases").status_code == 401
    assert client.post("/cases", json={}).status_code == 401


# --- uploading a bill --------------------------------------------------------


def test_uploading_a_bill_returns_line_items_and_flags(client: TestClient, auth_headers: dict):
    case = new_case(client, auth_headers)

    response = client.post(f"/cases/{case['id']}/bills", files=[page()], headers=auth_headers)
    assert response.status_code == 201, response.text
    bill = response.json()

    assert len(bill["line_items"]) == 11
    assert bill["total"] == 42490, "the eleven rows add up to the prototype's day 3 total"
    assert [(f["kind"], f["level"]) for f in bill["flags"]] == [
        ("duplicate", "red"),
        ("above_mrp", "red"),
        ("quantity", "amber"),
    ]
    assert all(f["status"] == "open" for f in bill["flags"])


def test_every_flag_carries_its_reasoning_and_reference(client: TestClient, auth_headers: dict):
    """CLAUDE.md: a flag must show what it was checked against."""
    case = new_case(client, auth_headers)
    bill = client.post(f"/cases/{case['id']}/bills", files=[page()], headers=auth_headers).json()

    for flag in bill["flags"]:
        assert flag["billed"] > 0
        assert flag["reference_source"], "a flag with no reference is an accusation"
        assert flag["reference_detail"], "the app needs the numbers to explain the flag"
        assert flag["line_item_id"], "a flag must point at the line it came from"

    above_mrp = next(f for f in bill["flags"] if f["kind"] == "above_mrp")
    assert above_mrp["reference_detail"]["unit_price_reference"] == "1840.00"
    assert above_mrp["excess"] == 6660


def test_a_bill_lands_on_its_case(client: TestClient, auth_headers: dict):
    case = new_case(client, auth_headers)
    client.post(f"/cases/{case['id']}/bills", files=[page()], headers=auth_headers)

    refreshed = client.get(f"/cases/{case['id']}", headers=auth_headers).json()
    (summary,) = refreshed["bills"]
    assert summary["item_count"] == 11
    assert summary["flag_count"] == 3
    assert summary["open_flag_count"] == 3
    assert summary["total"] == 42490


def test_accepts_several_pages(client: TestClient, auth_headers: dict):
    case = new_case(client, auth_headers)
    bill = client.post(
        f"/cases/{case['id']}/bills",
        files=[page("p1.jpg"), page("p2.jpg"), page("p3.jpg")],
        headers=auth_headers,
    ).json()
    assert bill["page_count"] == 3


def test_rejects_a_file_that_is_not_an_image(client: TestClient, auth_headers: dict):
    case = new_case(client, auth_headers)
    response = client.post(
        f"/cases/{case['id']}/bills",
        files=[("pages", ("notes.txt", io.BytesIO(b"just text"), "image/jpeg"))],
        headers=auth_headers,
    )
    assert response.status_code == 415
    assert response.json()["detail"]["code"] == "unsupported_page"


def test_rejects_an_empty_page(client: TestClient, auth_headers: dict):
    case = new_case(client, auth_headers)
    response = client.post(
        f"/cases/{case['id']}/bills",
        files=[("pages", ("empty.jpg", io.BytesIO(b""), "image/jpeg"))],
        headers=auth_headers,
    )
    assert response.status_code == 400


def test_cannot_upload_to_someone_elses_case(client: TestClient, auth_headers: dict, sms: FakeSms):
    case = new_case(client, auth_headers)
    other = sign_up(client, sms, phone="+919123456780", name="Someone Else")

    response = client.post(
        f"/cases/{case['id']}/bills",
        files=[page()],
        headers={"Authorization": f"Bearer {other['token']}"},
    )
    assert response.status_code == 404


def test_bill_day_counts_from_admission(client: TestClient, auth_headers: dict):
    case = new_case(client, auth_headers, admitted_on=str(date.today() - timedelta(days=2)))
    bill = client.post(f"/cases/{case['id']}/bills", files=[page()], headers=auth_headers).json()
    assert bill["day"] == 3


# --- what the hospital said --------------------------------------------------


@pytest.fixture
def bill_with_flags(client: TestClient, auth_headers: dict) -> dict:
    case = new_case(client, auth_headers)
    bill = client.post(f"/cases/{case['id']}/bills", files=[page()], headers=auth_headers).json()
    return {"case_id": case["id"], "bill": bill}


def test_marking_a_flag_corrected_counts_as_recovered(
    client: TestClient, auth_headers: dict, bill_with_flags: dict
):
    flag = next(f for f in bill_with_flags["bill"]["flags"] if f["kind"] == "above_mrp")

    updated = client.patch(f"/flags/{flag['id']}", json={"status": "corrected"}, headers=auth_headers)
    assert updated.status_code == 200
    assert updated.json()["status"] == "corrected"

    case = client.get(f"/cases/{bill_with_flags['case_id']}", headers=auth_headers).json()
    assert case["recovered_amount"] == 6660
    assert case["bills"][0]["open_flag_count"] == 2


def test_an_explained_flag_is_settled_but_not_recovered(
    client: TestClient, auth_headers: dict, bill_with_flags: dict
):
    """The hospital gave a reason. The question is closed; no money came back."""
    flag = next(f for f in bill_with_flags["bill"]["flags"] if f["kind"] == "quantity")
    client.patch(f"/flags/{flag['id']}", json={"status": "explained"}, headers=auth_headers)

    case = client.get(f"/cases/{bill_with_flags['case_id']}", headers=auth_headers).json()
    assert case["recovered_amount"] == 0
    assert case["bills"][0]["open_flag_count"] == 2


def test_a_question_can_be_reopened(client: TestClient, auth_headers: dict, bill_with_flags: dict):
    flag = bill_with_flags["bill"]["flags"][0]
    client.patch(f"/flags/{flag['id']}", json={"status": "corrected"}, headers=auth_headers)
    reopened = client.patch(f"/flags/{flag['id']}", json={"status": "open"}, headers=auth_headers)

    assert reopened.json()["status"] == "open"
    case = client.get(f"/cases/{bill_with_flags['case_id']}", headers=auth_headers).json()
    assert case["recovered_amount"] == 0


def test_cannot_resolve_a_flag_on_someone_elses_case(
    client: TestClient, auth_headers: dict, sms: FakeSms, bill_with_flags: dict
):
    other = sign_up(client, sms, phone="+919123456780", name="Someone Else")
    flag = bill_with_flags["bill"]["flags"][0]

    response = client.patch(
        f"/flags/{flag['id']}",
        json={"status": "corrected"},
        headers={"Authorization": f"Bearer {other['token']}"},
    )
    assert response.status_code == 404


def test_reading_a_bill_back(client: TestClient, auth_headers: dict, bill_with_flags: dict):
    bill_id = bill_with_flags["bill"]["id"]
    again = client.get(f"/bills/{bill_id}", headers=auth_headers).json()
    assert again["id"] == bill_id
    assert len(again["line_items"]) == 11


def test_an_invalid_status_is_rejected(client: TestClient, auth_headers: dict, bill_with_flags: dict):
    flag = bill_with_flags["bill"]["flags"][0]
    response = client.patch(f"/flags/{flag['id']}", json={"status": "sorted"}, headers=auth_headers)
    assert response.status_code == 422
