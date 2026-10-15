"""Correcting a case's details, and deleting one.

The details are typed at a counter, so they get corrected later. Two things
follow from that and are what these tests are really about: a corrected
admission date has to move everything derived from it, and "delete" has to
mean the bills are gone.
"""

from datetime import date, timedelta

from fastapi.testclient import TestClient

from tests.conftest import FakeSms, sign_up
from tests.test_cases_and_bills import headers_for, invite, new_case, page


def upload(client: TestClient, headers: dict, case_id: str) -> dict:
    response = client.post(f"/cases/{case_id}/bills", files=[page()], headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def date_flags(bill: dict) -> list[dict]:
    return [flag for flag in bill["flags"] if flag["kind"] == "date_outside_stay"]


def test_the_reader_s_words_survive_the_trip_to_the_app(client: TestClient, auth_headers: dict):
    """FlagOut has to carry reference_detail through untouched. The last two
    bugs here were both in a seam like this one, so it is worth asserting
    rather than assuming."""
    case = new_case(client, auth_headers)
    bill = upload(client, auth_headers, case["id"])

    noticed = next(f for f in bill["flags"] if f["reference_source"] == "reader")
    detail = noticed["reference_detail"]
    # The sentence the app shows in place of its own wording.
    assert detail["why_en"].startswith("The bill charges")
    # And what it was: the rule that fired, the words quoted off the bill, and
    # what the hospital would have to produce to settle it.
    assert detail["rule"].startswith("B.")
    assert detail["evidence"]
    assert detail["confirm"]
    assert detail["lines"] == "L5", "the lines the finding named, as the reader numbered them"


# --- correcting the details --------------------------------------------------


def test_corrects_what_was_sent_and_leaves_the_rest(client: TestClient, auth_headers: dict):
    case = new_case(client, auth_headers)

    updated = client.patch(
        f"/cases/{case['id']}", json={"bed": "308", "hospital_area": "Bandra"}, headers=auth_headers
    )

    assert updated.status_code == 200
    assert updated.json()["bed"] == "308"
    assert updated.json()["hospital_area"] == "Bandra"
    assert updated.json()["patient_name"] == case["patient_name"], "untouched by this request"
    assert updated.json()["title"] == case["title"]


def test_sending_nothing_changes_nothing(client: TestClient, auth_headers: dict):
    case = new_case(client, auth_headers)
    updated = client.patch(f"/cases/{case['id']}", json={}, headers=auth_headers)
    assert updated.status_code == 200
    assert updated.json()["title"] == case["title"]


def test_a_bed_can_be_cleared(client: TestClient, auth_headers: dict):
    """A patient moved out of a named bed. Null means cleared, not "unchanged"."""
    case = new_case(client, auth_headers)
    updated = client.patch(f"/cases/{case['id']}", json={"bed": None}, headers=auth_headers)
    assert updated.json()["bed"] is None


def test_any_member_can_correct_the_details(client: TestClient, auth_headers: dict, sms: FakeSms):
    """Whoever is at the hospital today is best placed to fix a bed number."""
    case = new_case(client, auth_headers)
    code = invite(client, auth_headers, case["id"])
    anita = headers_for(sign_up(client, sms, phone="+919123456780", name="Anita Sharma"))
    client.post("/cases/join", json={"code": code}, headers=anita)

    updated = client.patch(f"/cases/{case['id']}", json={"bed": "309"}, headers=anita)
    assert updated.status_code == 200
    assert updated.json()["bed"] == "309"


def test_a_stranger_cannot_even_see_that_it_exists(client: TestClient, auth_headers: dict, sms: FakeSms):
    case = new_case(client, auth_headers)
    stranger = headers_for(sign_up(client, sms, phone="+919123456781", name="Someone Else"))

    assert client.patch(f"/cases/{case['id']}", json={"bed": "1"}, headers=stranger).status_code == 404


# --- what a corrected admission date moves -----------------------------------


def test_moving_the_admission_re_checks_the_bills(client: TestClient, auth_headers: dict):
    """The stub bill has rows dated during the stay, so nothing is flagged for
    its date. Move the admission a month later and those rows are before it."""
    case = new_case(client, auth_headers)
    bill = upload(client, auth_headers, case["id"])
    assert date_flags(bill) == [], "dated inside the stay as created"

    moved = str(date.fromisoformat(bill["date"]) + timedelta(days=30))
    client.patch(f"/cases/{case['id']}", json={"admitted_on": moved}, headers=auth_headers)

    after = client.get(f"/bills/{bill['id']}", headers=auth_headers).json()
    assert len(date_flags(after)) == 2, "both consultant visits are now before the admission"
    assert all(flag["level"] == "amber" for flag in date_flags(after))


def test_correcting_the_date_back_drops_the_flags_again(client: TestClient, auth_headers: dict):
    case = new_case(client, auth_headers)
    bill = upload(client, auth_headers, case["id"])
    moved = str(date.fromisoformat(bill["date"]) + timedelta(days=30))

    client.patch(f"/cases/{case['id']}", json={"admitted_on": moved}, headers=auth_headers)
    client.patch(f"/cases/{case['id']}", json={"admitted_on": case["admitted_on"]}, headers=auth_headers)

    after = client.get(f"/bills/{bill['id']}", headers=auth_headers).json()
    assert date_flags(after) == [], "a typo corrected should leave no trace"


def test_a_settled_question_survives_a_date_correction(client: TestClient, auth_headers: dict):
    """The hospital already answered this one. What happened, happened, and the
    amount recovered stays recovered whatever the dates say later."""
    case = new_case(client, auth_headers)
    bill = upload(client, auth_headers, case["id"])
    moved = str(date.fromisoformat(bill["date"]) + timedelta(days=30))
    client.patch(f"/cases/{case['id']}", json={"admitted_on": moved}, headers=auth_headers)

    raised = date_flags(client.get(f"/bills/{bill['id']}", headers=auth_headers).json())
    client.patch(f"/flags/{raised[0]['id']}", json={"status": "corrected"}, headers=auth_headers)

    client.patch(f"/cases/{case['id']}", json={"admitted_on": case["admitted_on"]}, headers=auth_headers)
    after = date_flags(client.get(f"/bills/{bill['id']}", headers=auth_headers).json())
    assert [flag["status"] for flag in after] == ["corrected"]


def test_the_day_of_the_stay_moves_with_the_admission(client: TestClient, auth_headers: dict):
    case = new_case(client, auth_headers)
    bill = upload(client, auth_headers, case["id"])
    assert bill["day"] == 3

    later = str(date.fromisoformat(case["admitted_on"]) + timedelta(days=1))
    client.patch(f"/cases/{case['id']}", json={"admitted_on": later}, headers=auth_headers)

    after = client.get(f"/cases/{case['id']}", headers=auth_headers).json()
    assert after["bills"][0]["day"] == 2, "a day later admitted is a day earlier in the stay"


def test_the_report_stays_numbered_from_one(client: TestClient, auth_headers: dict):
    case = new_case(client, auth_headers)
    bill = upload(client, auth_headers, case["id"])
    moved = str(date.fromisoformat(bill["date"]) + timedelta(days=30))

    client.patch(f"/cases/{case['id']}", json={"admitted_on": moved}, headers=auth_headers)
    after = client.get(f"/bills/{bill['id']}", headers=auth_headers).json()

    positions = sorted(flag["position"] for flag in after["flags"])
    assert positions == list(range(1, len(positions) + 1)), "no gaps for the report to show"


# --- deleting ----------------------------------------------------------------


def test_deleting_takes_the_bills_with_it(client: TestClient, auth_headers: dict):
    case = new_case(client, auth_headers)
    bill = upload(client, auth_headers, case["id"])

    assert client.delete(f"/cases/{case['id']}", headers=auth_headers).status_code == 204
    assert client.get(f"/cases/{case['id']}", headers=auth_headers).status_code == 404
    assert client.get(f"/bills/{bill['id']}", headers=auth_headers).status_code == 404
    assert client.get("/cases", headers=auth_headers).json() == []


def test_only_whoever_started_the_case_can_delete_it(client: TestClient, auth_headers: dict, sms: FakeSms):
    """It takes the bills from the whole family. Someone who only wants out can
    leave instead."""
    case = new_case(client, auth_headers)
    code = invite(client, auth_headers, case["id"])
    anita = headers_for(sign_up(client, sms, phone="+919123456780", name="Anita Sharma"))
    client.post("/cases/join", json={"code": code}, headers=anita)

    assert client.delete(f"/cases/{case['id']}", headers=anita).status_code == 403
    assert client.get(f"/cases/{case['id']}", headers=anita).status_code == 200


def test_a_stranger_cannot_delete_or_learn_it_exists(client: TestClient, auth_headers: dict, sms: FakeSms):
    case = new_case(client, auth_headers)
    stranger = headers_for(sign_up(client, sms, phone="+919123456781", name="Someone Else"))

    assert client.delete(f"/cases/{case['id']}", headers=stranger).status_code == 404
