"""Cases, bill upload, and tracking what the hospital said.

Uploads use the stub OCR, so these exercise the whole path — pages in, line
items and flags out — without a key or a real bill.
"""

import io
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from db import india_today
from tests.conftest import FakeSms, sign_up

# A one-pixel JPEG: enough for the upload to sniff a real image type.
JPEG = bytes.fromhex("ffd8ffe000104a46494600010100000100010000ffdb004300ff") + b"\x00" * 64


def page(name: str = "page1.jpg") -> tuple[str, tuple[str, io.BytesIO, str]]:
    return ("pages", (name, io.BytesIO(JPEG), "image/jpeg"))


def new_member(client: TestClient, headers: dict, name: str = "Papa") -> dict:
    response = client.post("/members", json={"name": name}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def new_case(client: TestClient, headers: dict, **overrides) -> dict:
    """An admission, under a new member unless `member_id` names one."""
    if "member_id" not in overrides:
        overrides["member_id"] = new_member(client, headers)["id"]
    body = {
        "title": "Papa's admission",
        "hospital_name": "City Care Hospital",
        "hospital_area": "Andheri",
        "patient_name": "Ramesh Sharma",
        "ip_number": "20841",
        "bed": "412",
        "admitted_on": str(india_today() - timedelta(days=2)),
    } | overrides
    response = client.post("/cases", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


# --- cases -------------------------------------------------------------------


def test_creates_a_case_under_a_member(client: TestClient, auth_headers: dict):
    papa = new_member(client, auth_headers)
    created = new_case(client, auth_headers, member_id=papa["id"])

    assert created["title"] == "Papa's admission"
    assert created["member"] == {"id": papa["id"], "name": "Papa"}
    assert created["is_owner"] is True
    assert created["bills"] == []
    assert created["recovered_amount"] == 0


def test_a_case_needs_a_member_the_caller_follows(client: TestClient, auth_headers: dict, sms: FakeSms):
    """Opening an admission under someone else's member would put it in front
    of their family."""
    theirs = new_member(client, headers_for(sign_up(client, sms, phone="+919123456780", name="Other")))

    with pytest.raises(AssertionError):
        new_case(client, auth_headers, member_id=theirs["id"])
    assert client.post("/cases", json={"title": "x"}, headers=auth_headers).status_code == 422


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


def headers_for(body: dict) -> dict:
    return {"Authorization": f"Bearer {body['token']}"}


def follow(client: TestClient, headers: dict, member_id: str, follower: dict) -> None:
    """`follower` joins the member with a code from `headers`."""
    code = client.post(f"/members/{member_id}/invites", headers=headers).json()["code"]
    assert client.post("/members/join", json={"code": code}, headers=follower).status_code == 200


def test_closing_a_case_records_the_day_it_ended(client: TestClient, auth_headers: dict):
    case = new_case(client, auth_headers)
    closed = client.post(f"/cases/{case['id']}/close", headers=auth_headers).json()

    assert closed["closed_on"] == str(india_today())


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
        # The price lists first: they can show a family where the number came
        # from, so they are the ones that are ever red on their own account.
        ("duplicate", "red"),
        ("above_mrp", "red"),
        # The reader's own findings. "High" is what the bill itself proves, so
        # it is red too; everything else is a question. Both groups are in the
        # bill's own order, which is why row 5 precedes row 3 here only
        # because red precedes amber.
        ("analysis_finding", "red"),
        ("analysis_finding", "amber"),
        ("quantity", "amber"),
    ]
    reader = next(f for f in bill["flags"] if f["reference_source"] == "reader")
    # The prompt forbids pricing anything, so a finding adds nothing to the
    # total a family is told they might get back.
    assert reader["excess"] == 0
    assert all(f["status"] == "open" for f in bill["flags"])


def test_every_line_carries_the_kind_of_charge_it_is(client: TestClient, auth_headers: dict):
    """The report groups the bill by this, so every line needs one. The
    reader classifies them in PHASE 2; nothing used to keep it."""
    case = new_case(client, auth_headers)
    bill = client.post(f"/cases/{case['id']}/bills", files=[page()], headers=auth_headers).json()

    assert all(row["category"] for row in bill["line_items"]), "a line with no category groups nowhere"
    by_name = {row["name"]: row["category"] for row in bill["line_items"]}
    assert by_name["Room rent, twin sharing"] == "room_and_nursing"
    assert by_name["Inj. Meropenem 1g"] == "pharmacy_drug"
    assert by_name["Surgical gloves"] == "consumable_disposable"


def test_the_kind_of_charge_survives_reading_the_bill_back(client: TestClient, auth_headers: dict):
    """It is stored, not recomputed: the pages are dropped once read, so a
    category lost on the way in is lost for good."""
    case = new_case(client, auth_headers)
    bill = client.post(f"/cases/{case['id']}/bills", files=[page()], headers=auth_headers).json()

    again = client.get(f"/bills/{bill['id']}", headers=auth_headers).json()
    assert [row["category"] for row in again["line_items"]] == [row["category"] for row in bill["line_items"]]


def test_every_flag_says_which_lines_of_the_bill_it_is_about(client: TestClient, auth_headers: dict):
    """A family reads the question with their own bill in front of them, so
    "Lines 2 and 4" is the difference between an answerable question and a
    hunt. Every producer of a flag has to supply it: the price lists, the
    reader's findings, and the stay check."""
    case = new_case(client, auth_headers)
    bill = client.post(f"/cases/{case['id']}/bills", files=[page()], headers=auth_headers).json()
    positions = {row["id"]: row["position"] for row in bill["line_items"]}

    for flag in bill["flags"]:
        numbers = flag["reference_detail"].get("line_numbers")
        assert numbers, f"{flag['kind']} does not say which line it is about"
        assert all(part.isdigit() for part in numbers.split(",")), numbers
        if flag["line_item_id"]:
            assert str(positions[flag["line_item_id"]]) in numbers.split(",")


def test_a_duplicate_names_both_of_its_lines(client: TestClient, auth_headers: dict):
    """The one kind where a single number is useless: the family is being told
    two entries are the same, so they need to find both."""
    case = new_case(client, auth_headers)
    bill = client.post(f"/cases/{case['id']}/bills", files=[page()], headers=auth_headers).json()

    duplicate = next(flag for flag in bill["flags"] if flag["kind"] == "duplicate")
    assert duplicate["reference_detail"]["line_numbers"] == "3,4", "the two consultant visits"


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
    assert summary["flag_count"] == 5
    assert summary["open_flag_count"] == 5
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
    assert case["bills"][0]["open_flag_count"] == 4


def test_an_explained_flag_is_settled_but_not_recovered(
    client: TestClient, auth_headers: dict, bill_with_flags: dict
):
    """The hospital gave a reason. The question is closed; no money came back."""
    flag = next(f for f in bill_with_flags["bill"]["flags"] if f["kind"] == "quantity")
    client.patch(f"/flags/{flag['id']}", json={"status": "explained"}, headers=auth_headers)

    case = client.get(f"/cases/{bill_with_flags['case_id']}", headers=auth_headers).json()
    assert case["recovered_amount"] == 0
    assert case["bills"][0]["open_flag_count"] == 4


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


# --- India time ----------------------------------------------------------------


def test_india_today_is_ahead_of_utc_after_6_30_pm(monkeypatch: pytest.MonkeyPatch):
    """20:00 UTC on 11 Oct is 01:30 on 12 Oct in India."""
    import db

    monkeypatch.setattr(db, "utcnow", lambda: datetime(2026, 10, 11, 20, 0, tzinfo=UTC))
    assert db.india_today() == date(2026, 10, 12)
    monkeypatch.setattr(db, "utcnow", lambda: datetime(2026, 10, 11, 18, 0, tzinfo=UTC))
    assert db.india_today() == date(2026, 10, 11)


def test_a_bill_after_midnight_in_india_lands_on_the_new_day(
    client: TestClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
):
    """Photographed at 01:30 on 12 Oct in Mumbai, which is still 11 Oct in UTC."""
    import db

    case = new_case(client, auth_headers, admitted_on="2026-10-10")
    monkeypatch.setattr(db, "utcnow", lambda: datetime(2026, 10, 11, 20, 0, tzinfo=UTC))
    bill = client.post(f"/cases/{case['id']}/bills", files=[page()], headers=auth_headers).json()
    assert bill["date"] == "2026-10-12"


# --- upload limit ---------------------------------------------------------------


def test_bill_uploads_are_capped_per_day(
    client: TestClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
):
    """Every read is a paid call, so one account can't send bills without end."""
    from settings import get_settings

    monkeypatch.setattr(get_settings(), "bill_uploads_per_day", 2)
    case = new_case(client, auth_headers)
    for _ in range(2):
        assert (
            client.post(f"/cases/{case['id']}/bills", files=[page()], headers=auth_headers).status_code == 201
        )

    refused = client.post(f"/cases/{case['id']}/bills", files=[page()], headers=auth_headers)
    assert refused.status_code == 429
    assert refused.json()["detail"]["code"] == "upload_limit"
    assert "Retry-After" in refused.headers


def test_an_unreadable_bill_still_counts(
    client: TestClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
):
    """A failed read was paid for too, so retrying a bad photo can't go on forever."""
    from main import app
    from ocr import OcrError, get_ocr_provider
    from settings import get_settings

    class Unreadable:
        def read_bill(self, pages):
            raise OcrError("blurry")

    monkeypatch.setattr(get_settings(), "bill_uploads_per_day", 1)
    app.dependency_overrides[get_ocr_provider] = lambda: Unreadable()
    case = new_case(client, auth_headers)
    assert client.post(f"/cases/{case['id']}/bills", files=[page()], headers=auth_headers).status_code == 422
    assert client.post(f"/cases/{case['id']}/bills", files=[page()], headers=auth_headers).status_code == 429


def test_a_rejected_file_does_not_count(
    client: TestClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
):
    """Nothing was sent to the reader, so nothing was spent."""
    from settings import get_settings

    monkeypatch.setattr(get_settings(), "bill_uploads_per_day", 1)
    case = new_case(client, auth_headers)
    # A zip, not a bill: refused before it reaches the reader. A PDF would be
    # accepted now, so it can no longer stand in for a rejected file here.
    not_a_bill = ("pages", ("notes.zip", io.BytesIO(b"PK\x03\x04" + b"\x00" * 64), "image/jpeg"))
    assert (
        client.post(f"/cases/{case['id']}/bills", files=[not_a_bill], headers=auth_headers).status_code == 415
    )
    assert client.post(f"/cases/{case['id']}/bills", files=[page()], headers=auth_headers).status_code == 201
