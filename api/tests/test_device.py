"""Which phone, and from where: kept for the record, and to count uploads.

The Android ID is kept only as a keyed hash; the address and the time are
only ever the latest. Neither grants anything: a header can say anything.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.requests import Request

from device import android_id_hash, client_ip
from tables import User
from tests.conftest import FakeSms
from tests.test_cases_and_bills import page

PHONE_A = "a1b2c3d4e5f60718"
PHONE_B = "0f1e2d3c4b5a6978"


@pytest.fixture
def no_sign_in(monkeypatch: pytest.MonkeyPatch):
    """REQUIRE_SIGN_IN=false, as the app runs now."""
    import settings

    settings.get_settings.cache_clear()
    monkeypatch.setenv("REQUIRE_SIGN_IN", "false")
    yield
    settings.get_settings.cache_clear()


def start(client: TestClient, android_id: str | None = None, ip: str | None = None) -> dict:
    headers = {}
    if android_id:
        headers["X-Android-Id"] = android_id
    if ip:
        headers["X-Forwarded-For"] = ip
    response = client.post("/auth/anonymous", json={"consent": True}, headers=headers)
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def user(db: Session) -> User:
    db.expire_all()
    return db.scalars(select(User)).one()


# --- the Android ID -----------------------------------------------------------


def test_the_same_phone_hashes_the_same_every_time():
    assert android_id_hash(PHONE_A) == android_id_hash(PHONE_A.upper()) == android_id_hash(f" {PHONE_A} ")
    assert android_id_hash(PHONE_A) != android_id_hash(PHONE_B)


def test_the_id_itself_is_never_what_is_kept():
    hashed = android_id_hash(PHONE_A)
    assert hashed is not None and PHONE_A not in hashed and len(hashed) == 64


@pytest.mark.parametrize("sent", [None, "", "not-an-id", "<script>", "abc"])
def test_anything_that_isn_t_an_android_id_is_ignored(sent: str | None):
    assert android_id_hash(sent) is None


# --- the address --------------------------------------------------------------


def request_with(headers: dict[str, str], client_host: str = "10.0.0.1") -> Request:
    raw = [(name.lower().encode(), value.encode()) for name, value in headers.items()]
    return Request({"type": "http", "headers": raw, "client": (client_host, 1234)})


def test_the_address_is_the_one_google_s_front_end_saw():
    """The last entry: anything before it the phone could have written."""
    assert client_ip(request_with({"X-Forwarded-For": "1.1.1.1, 203.0.113.7"})) == "203.0.113.7"


def test_without_a_proxy_the_address_is_the_connection_s():
    assert client_ip(request_with({}, "192.0.2.5")) == "192.0.2.5"


# --- what is recorded ---------------------------------------------------------


def test_starting_without_an_account_records_when_and_from_where(client: TestClient, db: Session, no_sign_in):
    start(client, PHONE_A, "203.0.113.7")

    seen = user(db)
    assert seen.last_seen_at is not None
    assert seen.last_ip == "203.0.113.7"
    assert seen.android_id_hash == android_id_hash(PHONE_A)


def test_every_launch_records_it_again(client: TestClient, db: Session, no_sign_in):
    headers = start(client, PHONE_A, "203.0.113.7")
    first = user(db).last_seen_at

    client.get("/auth/me", headers={**headers, "X-Forwarded-For": "198.51.100.9"})

    seen = user(db)
    assert seen.last_seen_at is not None and first is not None and seen.last_seen_at >= first
    assert seen.last_ip == "198.51.100.9", "only the latest is kept"
    assert seen.android_id_hash == android_id_hash(PHONE_A), "a launch without the ID keeps the last one"


def test_signing_up_with_a_number_records_it_too(client: TestClient, sms: FakeSms, db: Session):
    """Signing up and signing in both start a session the same way."""
    client.post("/auth/otp/request", json={"phone": "9876543210"})
    verified = client.post("/auth/otp/verify", json={"phone": "9876543210", "code": sms.last_code()}).json()
    client.post(
        "/auth/signup",
        json={"signup_token": verified["signup_token"], "name": "Rohan Sharma", "consent": True},
        headers={"X-Android-Id": PHONE_B, "X-Forwarded-For": "198.51.100.9"},
    )

    seen = user(db)
    assert seen.last_seen_at is not None
    assert seen.android_id_hash == android_id_hash(PHONE_B)
    assert seen.last_ip == "198.51.100.9"


def test_none_of_it_is_sent_back_to_the_app(client: TestClient, no_sign_in):
    headers = start(client, PHONE_A, "203.0.113.7")
    me = client.get("/auth/me", headers=headers).json()
    assert not {"last_ip", "last_seen_at", "android_id_hash"} & set(me)


# --- the daily allowance, per phone -------------------------------------------


@pytest.fixture
def two_a_day(monkeypatch: pytest.MonkeyPatch, no_sign_in):
    from settings import get_settings

    monkeypatch.setattr(get_settings(), "bill_uploads_per_day", 2)


def upload(client: TestClient, headers: dict, android_id: str | None = None) -> int:
    extra = {"X-Android-Id": android_id} if android_id else {}
    return client.post("/bills", files=[page()], headers={**headers, **extra}).status_code


def test_a_new_account_on_the_same_phone_does_not_start_a_new_allowance(client: TestClient, two_a_day):
    """Clearing the app's data makes a new account. It used to make a new
    allowance too, so the cap on paid reads was no cap at all."""
    first = start(client, PHONE_A)
    assert [upload(client, first, PHONE_A) for _ in range(2)] == [201, 201]

    again = start(client, PHONE_A)
    assert upload(client, again, PHONE_A) == 429


def test_another_phone_has_its_own_allowance(client: TestClient, two_a_day):
    first = start(client, PHONE_A)
    for _ in range(2):
        upload(client, first, PHONE_A)

    assert upload(client, start(client, PHONE_B), PHONE_B) == 201


def test_a_phone_that_says_nothing_is_counted_by_account(client: TestClient, two_a_day):
    first = start(client)
    assert [upload(client, first) for _ in range(3)] == [201, 201, 429]
    assert upload(client, start(client)) == 201


def test_lab_reports_count_against_the_same_allowance(client: TestClient, two_a_day):
    first = start(client, PHONE_A)
    for _ in range(2):
        upload(client, first, PHONE_A)

    again = start(client, PHONE_A)
    client.post("/lab-reports/consent", json={"consent": True}, headers=again)
    report = client.post("/lab-reports", files=[page()], headers={**again, "X-Android-Id": PHONE_A})
    assert report.status_code == 429


def test_a_browser_may_send_the_header(client: TestClient):
    """Allowed in CORS, or the browser refuses the request before it is sent."""
    preflight = client.options(
        "/auth/me",
        headers={
            "Origin": "http://localhost:8081",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,x-android-id",
        },
    )
    assert preflight.status_code == 200
    assert "x-android-id" in preflight.headers["access-control-allow-headers"].lower()
