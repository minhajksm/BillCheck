"""Members: the people an account looks after, who follows them, and filing.

A member is a person. Their admissions and lab reports belong to them, and
family follow the person: whoever joins "Papa" sees every stay and every
report of his. A scan made before choosing anyone is read first and waits,
seen only by whoever made it, until they say whose it is.
"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tables import Bill, Case, LabReport, MemberInvite, UploadAttempt
from tests.conftest import FakeSms, sign_up
from tests.test_cases_and_bills import follow, headers_for, new_case, new_member, page

ANITA = "+919123456780"
VIJAY = "+919123456781"


def anita(client: TestClient, sms: FakeSms) -> dict:
    return sign_up(client, sms, phone=ANITA, name="Anita Sharma")


def scan_bill(client: TestClient, headers: dict, **form) -> dict:
    response = client.post("/bills", files=[page()], data=form or None, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def scan_lab_report(client: TestClient, headers: dict, **form) -> dict:
    client.post("/lab-reports/consent", json={"consent": True}, headers=headers)
    response = client.post("/lab-reports", files=[page()], data=form or None, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


# --- members -----------------------------------------------------------------


def test_adds_a_member_with_whoever_added_them_following(client: TestClient, auth_headers: dict):
    papa = new_member(client, auth_headers, "Papa")

    assert papa["name"] == "Papa"
    assert papa["is_owner"] is True
    assert [(f["name"], f["is_you"]) for f in papa["followers"]] == [("Rohan Sharma", True)]
    assert papa["cases"] == [] and papa["lab_reports"] == []


def test_a_member_needs_a_name(client: TestClient, auth_headers: dict):
    assert client.post("/members", json={"name": "  "}, headers=auth_headers).status_code == 422


def test_lists_everyone_you_follow_with_someone_in_hospital_first(client: TestClient, auth_headers: dict):
    new_member(client, auth_headers, "Mummy")
    papa = new_member(client, auth_headers, "Papa")
    new_case(client, auth_headers, member_id=papa["id"])  # admitted, not discharged
    new_member(client, auth_headers, "Aai")

    listed = client.get("/members", headers=auth_headers).json()

    assert [m["name"] for m in listed] == ["Papa", "Aai", "Mummy"]
    assert listed[0]["admission_count"] == 1 and listed[0]["open_admission_count"] == 1


def test_the_list_counts_what_is_under_each_member(client: TestClient, auth_headers: dict):
    papa = new_member(client, auth_headers)
    case = new_case(client, auth_headers, member_id=papa["id"])
    client.post(f"/cases/{case['id']}/bills", files=[page()], headers=auth_headers)
    scan_lab_report(client, auth_headers, member_id=papa["id"])

    (row,) = client.get("/members", headers=auth_headers).json()

    assert row["admission_count"] == 1
    assert row["open_flag_count"] > 0, "the stub bill raises questions"
    assert row["lab_report_count"] == 1


def test_a_member_you_do_not_follow_reads_as_missing(client: TestClient, auth_headers: dict, sms: FakeSms):
    papa = new_member(client, auth_headers)
    stranger = headers_for(anita(client, sms))

    response = client.get(f"/members/{papa['id']}", headers=stranger)
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "member_not_found"
    assert client.get("/members", headers=stranger).json() == []


def test_any_follower_can_rename(client: TestClient, auth_headers: dict, sms: FakeSms):
    """ "Papa" to one of them is "Ramesh Sharma" on a bill."""
    papa = new_member(client, auth_headers)
    her = headers_for(anita(client, sms))
    follow(client, auth_headers, papa["id"], her)

    renamed = client.patch(f"/members/{papa['id']}", json={"name": "Ramesh Sharma"}, headers=her)
    assert renamed.status_code == 200
    assert client.get(f"/members/{papa['id']}", headers=auth_headers).json()["name"] == "Ramesh Sharma"


# --- following ---------------------------------------------------------------


def test_family_follow_the_person_and_see_everything_under_them(
    client: TestClient, auth_headers: dict, sms: FakeSms
):
    papa = new_member(client, auth_headers)
    case = new_case(client, auth_headers, member_id=papa["id"])
    bill = client.post(f"/cases/{case['id']}/bills", files=[page()], headers=auth_headers).json()
    report = scan_lab_report(client, auth_headers, member_id=papa["id"])
    her = headers_for(anita(client, sms))

    follow(client, auth_headers, papa["id"], her)

    seen = client.get(f"/members/{papa['id']}", headers=her).json()
    assert sorted(f["name"] for f in seen["followers"]) == ["Anita Sharma", "Rohan Sharma"]
    assert [c["id"] for c in seen["cases"]] == [case["id"]]
    assert [r["id"] for r in seen["lab_reports"]] == [report["id"]]
    assert client.get(f"/bills/{bill['id']}", headers=her).status_code == 200
    assert client.get(f"/lab-reports/{report['id']}", headers=her).status_code == 200


def test_what_is_added_later_is_seen_too(client: TestClient, auth_headers: dict, sms: FakeSms):
    """The point of following the person rather than one admission."""
    papa = new_member(client, auth_headers)
    her = headers_for(anita(client, sms))
    follow(client, auth_headers, papa["id"], her)

    later = new_case(client, auth_headers, member_id=papa["id"])

    assert client.get(f"/cases/{later['id']}", headers=her).status_code == 200
    assert [c["id"] for c in client.get("/cases", headers=her).json()] == [later["id"]]


def test_a_follower_can_add_to_the_member(client: TestClient, auth_headers: dict, sms: FakeSms):
    papa = new_member(client, auth_headers)
    her = headers_for(anita(client, sms))
    follow(client, auth_headers, papa["id"], her)

    hers = scan_bill(client, her, member_id=papa["id"])

    assert client.get(f"/bills/{hers['id']}", headers=auth_headers).status_code == 200


def test_the_member_id_alone_is_not_enough_to_follow(client: TestClient, auth_headers: dict, sms: FakeSms):
    """Ids appear in links and server logs."""
    papa = new_member(client, auth_headers)
    stranger = headers_for(anita(client, sms))

    assert client.post("/members/join", json={"code": papa["id"]}, headers=stranger).status_code == 404
    assert client.get(f"/members/{papa['id']}", headers=stranger).status_code == 404


def test_following_twice_is_harmless(client: TestClient, auth_headers: dict):
    papa = new_member(client, auth_headers)
    code = client.post(f"/members/{papa['id']}/invites", headers=auth_headers).json()["code"]

    again = client.post("/members/join", json={"code": code}, headers=auth_headers)
    assert again.status_code == 200
    assert len(again.json()["followers"]) == 1


def test_only_followers_can_create_invites(client: TestClient, auth_headers: dict, sms: FakeSms):
    papa = new_member(client, auth_headers)
    stranger = headers_for(anita(client, sms))
    assert client.post(f"/members/{papa['id']}/invites", headers=stranger).status_code == 404


def test_an_invite_expires(
    client: TestClient, auth_headers: dict, sms: FakeSms, monkeypatch: pytest.MonkeyPatch
):
    import members

    papa = new_member(client, auth_headers)
    code = client.post(f"/members/{papa['id']}/invites", headers=auth_headers).json()["code"]
    her = headers_for(anita(client, sms))

    later = members.utcnow() + members.INVITE_TTL + timedelta(minutes=1)
    monkeypatch.setattr(members, "utcnow", lambda: later)
    response = client.post("/members/join", json={"code": code}, headers=her)
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "invite_invalid"


def test_a_withdrawn_invite_stops_working(client: TestClient, auth_headers: dict, sms: FakeSms):
    papa = new_member(client, auth_headers)
    code = client.post(f"/members/{papa['id']}/invites", headers=auth_headers).json()["code"]
    (listed,) = client.get(f"/members/{papa['id']}/invites", headers=auth_headers).json()
    assert "code" not in listed, "the code is shown once, when it is made"

    revoked = client.post(f"/members/{papa['id']}/invites/{listed['id']}/revoke", headers=auth_headers)
    assert revoked.status_code == 204
    assert client.get(f"/members/{papa['id']}/invites", headers=auth_headers).json() == []
    her = headers_for(anita(client, sms))
    assert client.post("/members/join", json={"code": code}, headers=her).status_code == 404


def test_invite_codes_are_not_stored_in_plain_text(client: TestClient, auth_headers: dict, db: Session):
    papa = new_member(client, auth_headers)
    code = client.post(f"/members/{papa['id']}/invites", headers=auth_headers).json()["code"]

    stored = db.scalars(select(MemberInvite)).one().code_hash
    assert code not in stored and len(stored) == 64


def test_a_follower_can_stop_following(client: TestClient, auth_headers: dict, sms: FakeSms):
    papa = new_member(client, auth_headers)
    case = new_case(client, auth_headers, member_id=papa["id"])
    her_body = anita(client, sms)
    her = headers_for(her_body)
    follow(client, auth_headers, papa["id"], her)

    left = client.post(f"/members/{papa['id']}/followers/{her_body['user']['id']}/remove", headers=her)
    assert left.status_code == 204
    assert client.get(f"/members/{papa['id']}", headers=her).status_code == 404
    assert client.get(f"/cases/{case['id']}", headers=her).status_code == 404


def test_only_whoever_added_the_member_can_remove_someone(
    client: TestClient, auth_headers: dict, sms: FakeSms
):
    papa = new_member(client, auth_headers)
    her = headers_for(anita(client, sms))
    vijay_body = sign_up(client, sms, phone=VIJAY, name="Vijay Sharma")
    for headers in (her, headers_for(vijay_body)):
        follow(client, auth_headers, papa["id"], headers)
    remove = f"/members/{papa['id']}/followers/{vijay_body['user']['id']}/remove"

    assert client.post(remove, headers=her).status_code == 403
    assert client.post(remove, headers=auth_headers).status_code == 204
    assert client.get(f"/members/{papa['id']}", headers=headers_for(vijay_body)).status_code == 404


def test_whoever_added_the_member_cannot_stop_following(client: TestClient, auth_headers: dict, sms: FakeSms):
    papa = new_member(client, auth_headers)
    owner_id = client.get("/auth/me", headers=auth_headers).json()["id"]
    her = headers_for(anita(client, sms))
    follow(client, auth_headers, papa["id"], her)
    remove = f"/members/{papa['id']}/followers/{owner_id}/remove"

    assert client.post(remove, headers=auth_headers).status_code == 409
    assert client.post(remove, headers=her).status_code == 403


# --- deleting ----------------------------------------------------------------


def test_deleting_a_member_takes_everything_about_them(client: TestClient, auth_headers: dict, db: Session):
    """Health data is kept only while a family wants it kept."""
    papa = new_member(client, auth_headers)
    case = new_case(client, auth_headers, member_id=papa["id"])
    client.post(f"/cases/{case['id']}/bills", files=[page()], headers=auth_headers)
    scan_lab_report(client, auth_headers, member_id=papa["id"])

    assert client.delete(f"/members/{papa['id']}", headers=auth_headers).status_code == 204

    assert client.get(f"/members/{papa['id']}", headers=auth_headers).status_code == 404
    for table in (Case, Bill, LabReport):
        assert db.scalar(select(func.count()).select_from(table)) == 0, table.__tablename__


def test_only_whoever_added_the_member_can_delete_them(client: TestClient, auth_headers: dict, sms: FakeSms):
    papa = new_member(client, auth_headers)
    her = headers_for(anita(client, sms))
    follow(client, auth_headers, papa["id"], her)

    assert client.delete(f"/members/{papa['id']}", headers=her).status_code == 403
    assert client.get(f"/members/{papa['id']}", headers=her).status_code == 200


# --- scanning from a member --------------------------------------------------


def test_a_bill_scanned_from_a_member_is_theirs_from_the_start(client: TestClient, auth_headers: dict):
    papa = new_member(client, auth_headers)

    bill = scan_bill(client, auth_headers, member_id=papa["id"])

    case = client.get(f"/cases/{bill['case_id']}", headers=auth_headers).json()
    assert case["member"] == {"id": papa["id"], "name": "Papa"}
    assert client.get("/unfiled", headers=auth_headers).json()["cases"] == []


def test_scanning_for_someone_you_do_not_follow_reads_nothing(
    client: TestClient, auth_headers: dict, sms: FakeSms, db: Session
):
    """Refused before the read, which is slow and paid for."""
    theirs = new_member(client, headers_for(anita(client, sms)))

    response = client.post("/bills", files=[page()], data={"member_id": theirs["id"]}, headers=auth_headers)

    assert response.status_code == 404
    assert db.scalar(select(func.count()).select_from(UploadAttempt)) == 0
    assert db.scalar(select(func.count()).select_from(Case)) == 0


def test_a_lab_report_scanned_from_a_member_is_theirs(client: TestClient, auth_headers: dict):
    papa = new_member(client, auth_headers)

    report = scan_lab_report(client, auth_headers, member_id=papa["id"])

    assert report["member"] == {"id": papa["id"], "name": "Papa"}


# --- scanning first, then saying whose it is ---------------------------------


def test_a_bill_scanned_first_waits_to_be_filed(client: TestClient, auth_headers: dict):
    bill = scan_bill(client, auth_headers)

    case = client.get(f"/cases/{bill['case_id']}", headers=auth_headers).json()
    assert case["member"] is None
    assert case["patient_name"] == "Ramesh Sharma", "offered as the answer to whose it is"
    assert [c["id"] for c in client.get("/unfiled", headers=auth_headers).json()["cases"]] == [case["id"]]


def test_filing_under_someone_already_there(client: TestClient, auth_headers: dict):
    papa = new_member(client, auth_headers)
    bill = scan_bill(client, auth_headers)

    filed = client.post(
        f"/cases/{bill['case_id']}/member", json={"member_id": papa["id"]}, headers=auth_headers
    )

    assert filed.status_code == 200
    assert filed.json()["member"] == {"id": papa["id"], "name": "Papa"}
    assert client.get("/unfiled", headers=auth_headers).json()["cases"] == []
    member = client.get(f"/members/{papa['id']}", headers=auth_headers).json()
    assert [c["id"] for c in member["cases"]] == [bill["case_id"]]


def test_filing_under_someone_new_named_as_the_bill_names_them(client: TestClient, auth_headers: dict):
    bill = scan_bill(client, auth_headers)

    filed = client.post(
        f"/cases/{bill['case_id']}/member", json={"new_member_name": "Ramesh Sharma"}, headers=auth_headers
    ).json()

    (member,) = client.get("/members", headers=auth_headers).json()
    assert member["name"] == "Ramesh Sharma" and member["is_owner"]
    assert filed["member"]["id"] == member["id"]


@pytest.mark.parametrize(
    "body", [{}, {"member_id": "bb1b4a8c-0000-0000-0000-000000000000", "new_member_name": "Papa"}]
)
def test_filing_takes_exactly_one_answer(client: TestClient, auth_headers: dict, body: dict):
    bill = scan_bill(client, auth_headers)
    assert client.post(f"/cases/{bill['case_id']}/member", json=body, headers=auth_headers).status_code == 422


def test_family_see_a_bill_once_it_is_filed_and_not_before(
    client: TestClient, auth_headers: dict, sms: FakeSms
):
    papa = new_member(client, auth_headers)
    her = headers_for(anita(client, sms))
    follow(client, auth_headers, papa["id"], her)
    bill = scan_bill(client, auth_headers)

    assert client.get(f"/bills/{bill['id']}", headers=her).status_code == 404
    client.post(f"/cases/{bill['case_id']}/member", json={"member_id": papa["id"]}, headers=auth_headers)
    assert client.get(f"/bills/{bill['id']}", headers=her).status_code == 200


def test_only_whoever_scanned_it_can_file_it(client: TestClient, auth_headers: dict, sms: FakeSms):
    bill = scan_bill(client, auth_headers)
    her = headers_for(anita(client, sms))
    hers = new_member(client, her)

    filed = client.post(f"/cases/{bill['case_id']}/member", json={"member_id": hers["id"]}, headers=her)
    assert filed.status_code == 404


def test_nothing_is_filed_under_someone_you_do_not_follow(
    client: TestClient, auth_headers: dict, sms: FakeSms
):
    """Or a stranger could put a bill in front of another family."""
    bill = scan_bill(client, auth_headers)
    theirs = new_member(client, headers_for(anita(client, sms)))

    filed = client.post(
        f"/cases/{bill['case_id']}/member", json={"member_id": theirs["id"]}, headers=auth_headers
    )
    assert filed.status_code == 404
    assert client.get(f"/cases/{bill['case_id']}", headers=auth_headers).json()["member"] is None


def test_a_filed_admission_can_be_moved_to_someone_else(client: TestClient, auth_headers: dict):
    papa = new_member(client, auth_headers, "Papa")
    mummy = new_member(client, auth_headers, "Mummy")
    case = new_case(client, auth_headers, member_id=papa["id"])

    moved = client.post(f"/cases/{case['id']}/member", json={"member_id": mummy["id"]}, headers=auth_headers)

    assert moved.json()["member"]["name"] == "Mummy"
    assert client.get(f"/members/{papa['id']}", headers=auth_headers).json()["cases"] == []


def test_a_lab_report_scanned_first_is_filed_the_same_way(client: TestClient, auth_headers: dict):
    report = scan_lab_report(client, auth_headers)
    assert report["member"] is None
    (waiting,) = client.get("/unfiled", headers=auth_headers).json()["lab_reports"]
    assert waiting["patient_name"] == report["patient_name"], "offered as the answer"

    filed = client.post(
        f"/lab-reports/{report['id']}/member", json={"new_member_name": "Papa"}, headers=auth_headers
    ).json()

    assert filed["member"]["name"] == "Papa"
    assert client.get("/unfiled", headers=auth_headers).json()["lab_reports"] == []


def test_an_unfiled_lab_report_is_seen_only_by_whoever_scanned_it(
    client: TestClient, auth_headers: dict, sms: FakeSms
):
    report = scan_lab_report(client, auth_headers)
    her = headers_for(anita(client, sms))

    assert client.get(f"/lab-reports/{report['id']}", headers=her).status_code == 404
    assert client.get("/lab-reports", headers=her).json() == []


def test_a_follower_cannot_delete_someone_else_s_lab_report(
    client: TestClient, auth_headers: dict, sms: FakeSms
):
    """It goes for the whole family: whoever added it can delete it, and so
    can whoever added the member."""
    papa = new_member(client, auth_headers)
    her = headers_for(anita(client, sms))
    follow(client, auth_headers, papa["id"], her)
    mine = scan_lab_report(client, auth_headers, member_id=papa["id"])
    hers = scan_lab_report(client, her, member_id=papa["id"])

    assert client.delete(f"/lab-reports/{mine['id']}", headers=her).status_code == 403
    assert client.delete(f"/lab-reports/{hers['id']}", headers=her).status_code == 204
    assert client.delete(f"/lab-reports/{mine['id']}", headers=auth_headers).status_code == 204


# --- details -----------------------------------------------------------------


def test_details_are_optional_and_kept_when_given(client: TestClient, auth_headers: dict):
    bare = new_member(client, auth_headers, "Papa")
    assert (bare["date_of_birth"], bare["age"], bare["phone"], bare["email"], bare["address"]) == (
        None,
        None,
        None,
        None,
        None,
    )

    made = client.post(
        "/members",
        json={
            "name": "Mummy",
            "date_of_birth": "1958-03-14",
            "phone": "98765 43210",
            "email": "Sunita.Sharma@Example.com",
            "address": "  12 Example Road, Pune  ",
        },
        headers=auth_headers,
    ).json()

    assert made["date_of_birth"] == "1958-03-14"
    assert made["phone"] == "+919876543210", "stored the way the account's own number is"
    assert made["email"] == "sunita.sharma@example.com"
    assert made["address"] == "12 Example Road, Pune"


def test_age_is_worked_out_from_the_date_of_birth():
    from datetime import date

    from members import age_on

    born = date(1958, 3, 14)
    assert age_on(born, date(2026, 3, 13)) == 67, "the day before the birthday"
    assert age_on(born, date(2026, 3, 14)) == 68, "on the birthday"
    assert age_on(None, date(2026, 3, 14)) is None


def test_age_is_served_on_the_member_and_in_the_list(client: TestClient, auth_headers: dict):
    from db import india_today

    # 1 January, so the birthday has always come by today.
    born = f"{india_today().year - 40}-01-01"
    made = client.post("/members", json={"name": "Papa", "date_of_birth": born}, headers=auth_headers).json()

    assert made["age"] == 40
    assert client.get("/members", headers=auth_headers).json()[0]["age"] == 40


@pytest.mark.parametrize(
    "field, value",
    [
        ("date_of_birth", "2999-01-01"),
        ("date_of_birth", "1850-01-01"),
        ("date_of_birth", "14/03/1958"),
        ("phone", "12345"),
        ("email", "not-an-email"),
        ("address", "x" * 301),
    ],
)
def test_a_detail_that_is_not_one_is_refused(client: TestClient, auth_headers: dict, field: str, value: str):
    response = client.post("/members", json={"name": "Papa", field: value}, headers=auth_headers)
    assert response.status_code == 422, (field, value)


def test_editing_changes_what_is_sent_and_clears_what_is_emptied(client: TestClient, auth_headers: dict):
    made = client.post(
        "/members",
        json={"name": "Papa", "phone": "9876543210", "email": "papa@example.com"},
        headers=auth_headers,
    ).json()

    edited = client.patch(
        f"/members/{made['id']}",
        json={"date_of_birth": "1952-08-01", "email": ""},
        headers=auth_headers,
    ).json()

    assert edited["name"] == "Papa", "left out, so kept"
    assert edited["phone"] == "+919876543210", "left out, so kept"
    assert edited["date_of_birth"] == "1952-08-01"
    assert edited["email"] is None, "sent empty, so cleared"


def test_a_name_can_be_changed_but_not_cleared(client: TestClient, auth_headers: dict):
    papa = new_member(client, auth_headers)

    assert client.patch(f"/members/{papa['id']}", json={"name": ""}, headers=auth_headers).status_code == 422
    kept = client.patch(f"/members/{papa['id']}", json={"name": None}, headers=auth_headers).json()
    assert kept["name"] == "Papa"


def test_family_see_the_details_too(client: TestClient, auth_headers: dict, sms: FakeSms):
    papa = client.post("/members", json={"name": "Papa", "phone": "9876543210"}, headers=auth_headers).json()
    her = headers_for(anita(client, sms))
    follow(client, auth_headers, papa["id"], her)

    assert client.get(f"/members/{papa['id']}", headers=her).json()["phone"] == "+919876543210"


# --- the discharge date ------------------------------------------------------


def test_an_admission_can_be_opened_with_its_discharge_date(client: TestClient, auth_headers: dict):
    case = new_case(client, auth_headers, admitted_on="2026-05-04", closed_on="2026-05-06")
    assert case["closed_on"] == "2026-05-06"


def test_a_discharge_before_the_admission_is_refused(client: TestClient, auth_headers: dict):
    papa = new_member(client, auth_headers)
    body = {
        "member_id": papa["id"],
        "title": "x",
        "hospital_name": "x",
        "hospital_area": "x",
        "patient_name": "x",
        "ip_number": "1",
        "admitted_on": "2026-05-04",
        "closed_on": "2026-05-03",
    }
    assert client.post("/cases", json=body, headers=auth_headers).status_code == 422

    case = new_case(client, auth_headers, admitted_on="2026-05-04")
    moved = client.patch(f"/cases/{case['id']}", json={"closed_on": "2026-05-01"}, headers=auth_headers)
    assert moved.status_code == 422
    assert moved.json()["detail"]["code"] == "discharge_before_admission"
    assert client.get(f"/cases/{case['id']}", headers=auth_headers).json()["closed_on"] is None, "unchanged"


def test_the_discharge_date_can_be_corrected_and_cleared(client: TestClient, auth_headers: dict):
    case = new_case(client, auth_headers, admitted_on="2026-05-04", closed_on="2026-05-06")

    corrected = client.patch(f"/cases/{case['id']}", json={"closed_on": "2026-05-07"}, headers=auth_headers)
    assert corrected.json()["closed_on"] == "2026-05-07"
    reopened = client.patch(f"/cases/{case['id']}", json={"closed_on": None}, headers=auth_headers)
    assert reopened.json()["closed_on"] is None, "still in hospital after all"
