from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

import auth
from db import utcnow
from tests.conftest import PHONE, FakeSms, sign_up


def error_code(response) -> str:
    return response.json()["detail"]["code"]


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch):
    """Lets a test move time forward: clock.advance(minutes=6)."""

    class Clock:
        offset = timedelta()

        def advance(self, **kwargs: float) -> None:
            self.offset += timedelta(**kwargs)

    c = Clock()
    monkeypatch.setattr(auth, "utcnow", lambda: utcnow() + c.offset)
    return c


def request_code(client: TestClient, phone: str = PHONE):
    return client.post("/auth/otp/request", json={"phone": phone})


def verify(client: TestClient, code: str, phone: str = PHONE):
    return client.post("/auth/otp/verify", json={"phone": phone, "code": code})


def test_request_sends_a_six_digit_code(client: TestClient, sms: FakeSms):
    response = request_code(client, "98765 43210")
    assert response.status_code == 202
    assert response.json() == {"expires_in_seconds": 300, "resend_after_seconds": 30}
    phone, code = sms.sent[0]
    assert phone == PHONE
    assert len(code) == 6 and code.isdigit()


@pytest.mark.parametrize("phone", ["12345", "5876543210", "+1 415 555 0100", "98765432101"])
def test_request_rejects_non_indian_mobiles(client: TestClient, sms: FakeSms, phone: str):
    assert request_code(client, phone).status_code == 422
    assert sms.sent == []


def test_new_number_must_finish_signup(client: TestClient, sms: FakeSms):
    request_code(client)
    response = verify(client, sms.last_code())
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "signup_required"
    assert body["signup_token"]


def test_signup_creates_account_and_session(client: TestClient, sms: FakeSms):
    body = sign_up(client, sms, name="  Rohan Sharma  ")
    assert body["status"] == "logged_in"
    assert body["user"]["phone"] == PHONE
    assert body["user"]["name"] == "Rohan Sharma"

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert me.status_code == 200
    assert me.json()["name"] == "Rohan Sharma"


def test_signup_requires_consent(client: TestClient, sms: FakeSms):
    request_code(client)
    token = verify(client, sms.last_code()).json()["signup_token"]
    response = client.post("/auth/signup", json={"signup_token": token, "name": "Rohan", "consent": False})
    assert response.status_code == 422


def test_signup_requires_a_name(client: TestClient, sms: FakeSms):
    request_code(client)
    token = verify(client, sms.last_code()).json()["signup_token"]
    response = client.post("/auth/signup", json={"signup_token": token, "name": "   ", "consent": True})
    assert response.status_code == 422


def test_signup_token_works_once(client: TestClient, sms: FakeSms):
    request_code(client)
    token = verify(client, sms.last_code()).json()["signup_token"]
    body = {"signup_token": token, "name": "Rohan", "consent": True}
    assert client.post("/auth/signup", json=body).status_code == 201
    second = client.post("/auth/signup", json=body)
    assert second.status_code == 400
    assert error_code(second) == "signup_token_invalid"


def test_signup_token_expires(client: TestClient, sms: FakeSms, clock):
    request_code(client)
    token = verify(client, sms.last_code()).json()["signup_token"]
    clock.advance(minutes=16)
    response = client.post("/auth/signup", json={"signup_token": token, "name": "Rohan", "consent": True})
    assert error_code(response) == "signup_token_invalid"


def test_existing_user_logs_in(client: TestClient, sms: FakeSms, clock):
    sign_up(client, sms)
    clock.advance(seconds=31)
    request_code(client)
    response = verify(client, sms.last_code())
    body = response.json()
    assert body["status"] == "logged_in"
    assert body["user"]["name"] == "Rohan Sharma"


def test_wrong_code_is_rejected_then_locks(client: TestClient, sms: FakeSms):
    request_code(client)
    right = sms.last_code()
    wrong = "000000" if right != "000000" else "111111"
    for _ in range(auth.MAX_ATTEMPTS - 1):
        assert error_code(verify(client, wrong)) == "otp_invalid"
    assert error_code(verify(client, wrong)) == "otp_locked"
    # Even the right code no longer works once locked.
    assert error_code(verify(client, right)) == "otp_locked"


def test_code_expires(client: TestClient, sms: FakeSms, clock):
    request_code(client)
    clock.advance(minutes=6)
    assert error_code(verify(client, sms.last_code())) == "otp_expired"


def test_code_works_once(client: TestClient, sms: FakeSms):
    request_code(client)
    code = sms.last_code()
    assert verify(client, code).status_code == 200
    assert error_code(verify(client, code)) == "otp_expired"


def test_only_the_latest_code_counts(client: TestClient, sms: FakeSms, clock):
    request_code(client)
    first = sms.last_code()
    clock.advance(seconds=31)
    request_code(client)
    if first != sms.last_code():
        assert error_code(verify(client, first)) == "otp_invalid"
    assert verify(client, sms.last_code()).status_code == 200


def test_resend_cooldown(client: TestClient, sms: FakeSms, clock):
    request_code(client)
    response = request_code(client)
    assert response.status_code == 429
    assert error_code(response) == "otp_cooldown"
    assert int(response.headers["Retry-After"]) <= 30
    clock.advance(seconds=31)
    assert request_code(client).status_code == 202


def test_hourly_limit(client: TestClient, sms: FakeSms, clock):
    for _ in range(auth.MAX_CODES_PER_HOUR):
        assert request_code(client).status_code == 202
        clock.advance(seconds=31)
    response = request_code(client)
    assert response.status_code == 429
    assert error_code(response) == "otp_rate_limited"
    clock.advance(hours=1)
    assert request_code(client).status_code == 202


def test_codes_are_not_stored_in_plain_text(client: TestClient, sms: FakeSms):
    request_code(client)
    from db import get_db
    from main import app
    from tables import OtpChallenge

    db = next(app.dependency_overrides[get_db]())
    stored = db.query(OtpChallenge).one().code_hash
    assert sms.last_code() not in stored
    assert len(stored) == 64


def test_me_requires_a_valid_token(client: TestClient):
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_logout_revokes_the_session(client: TestClient, auth_headers: dict[str, str]):
    assert client.post("/auth/logout", headers=auth_headers).status_code == 204
    assert client.get("/auth/me", headers=auth_headers).status_code == 401


def test_session_expires(client: TestClient, auth_headers: dict[str, str], clock):
    clock.advance(days=31)
    assert client.get("/auth/me", headers=auth_headers).status_code == 401
