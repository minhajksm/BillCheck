"""MSG91 delivery. No test here touches the network: every request is served
by an httpx.MockTransport, so the real HTTP layer runs against a stub."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from settings import Settings
from sms import ConsoleSmsSender, Msg91SmsSender, SmsDeliveryError, get_sms_sender
from tests.conftest import PHONE

SUCCESS = {"message": "3abc-def", "type": "success"}


def sender(handler, **kwargs) -> Msg91SmsSender:
    return Msg91SmsSender(
        auth_key="test-key",
        template_id="template-123",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def test_sends_the_code_in_msg91s_shape():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=SUCCESS)

    sender(handler).send_otp(PHONE, "482913")

    (request,) = seen
    assert request.method == "POST"
    assert str(request.url) == "https://control.msg91.com/api/v5/flow/"  # the default
    assert request.headers["authkey"] == "test-key"
    assert json.loads(request.content) == {
        "template_id": "template-123",
        "short_url": 0,
        # MSG91 wants the country code without the "+".
        "recipients": [{"mobiles": "919876543210", "otp": "482913"}],
    }


def test_includes_sender_id_only_when_set():
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=SUCCESS)

    sender(handler).send_otp(PHONE, "111111")
    sender(handler, sender_id="BILCHK").send_otp(PHONE, "222222")

    assert "sender" not in bodies[0]
    assert bodies[1]["sender"] == "BILCHK"


@pytest.mark.parametrize("status_code", [400, 401, 429, 500])
def test_http_error_becomes_delivery_error(status_code: int):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"type": "error", "message": "no"})

    with pytest.raises(SmsDeliveryError):
        sender(handler).send_otp(PHONE, "482913")


def test_refusal_with_200_becomes_delivery_error():
    """MSG91 answers 200 for some refusals, so the body has to decide."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"type": "error", "message": "invalid template"})

    with pytest.raises(SmsDeliveryError, match="invalid template"):
        sender(handler).send_otp(PHONE, "482913")


def test_unreachable_provider_becomes_delivery_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    with pytest.raises(SmsDeliveryError, match="request failed"):
        sender(handler).send_otp(PHONE, "482913")


def test_non_json_body_becomes_delivery_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>maintenance</html>")

    with pytest.raises(SmsDeliveryError):
        sender(handler).send_otp(PHONE, "482913")


def test_never_logs_the_code(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=SUCCESS)

    with caplog.at_level("DEBUG"):
        sender(handler).send_otp(PHONE, "482913")

    assert "482913" not in caplog.text
    assert PHONE not in caplog.text, "log the masked number, not the full one"


def test_console_sender_prints_the_code(caplog):
    """The development path is the opposite: the code has to be readable."""
    with caplog.at_level("DEBUG"):
        ConsoleSmsSender().send_otp(PHONE, "482913")

    assert "482913" in caplog.text
    assert PHONE not in caplog.text


# --- settings ---------------------------------------------------------------


def test_msg91_needs_credentials():
    with pytest.raises(ValidationError, match="MSG91_AUTH_KEY"):
        Settings(otp_delivery="msg91", msg91_auth_key="", msg91_template_id="")
    with pytest.raises(ValidationError, match="MSG91_AUTH_KEY"):
        Settings(otp_delivery="msg91", msg91_auth_key="key", msg91_template_id="")


def test_msg91_satisfies_the_production_check():
    settings = Settings(
        environment="production",
        secret_key="x" * 40,
        otp_delivery="msg91",
        msg91_auth_key="key",
        msg91_template_id="template-123",
        # Production also refuses the stub OCR, which returns a sample bill,
        # and the switch that shows questions the rows already contradicted.
        ocr_provider="claude",
        anthropic_api_key="key",
        review_keep_all=False,
    )
    assert settings.otp_delivery == "msg91"


@pytest.mark.parametrize(
    ("delivery", "expected"),
    [("console", ConsoleSmsSender), ("msg91", Msg91SmsSender)],
)
def test_delivery_setting_picks_the_sender(monkeypatch, delivery: str, expected: type):
    """Doesn't read the developer's own .env: builds the settings here."""
    settings = Settings(otp_delivery=delivery, msg91_auth_key="key", msg91_template_id="template-123")
    monkeypatch.setattr("sms.get_settings", lambda: settings)
    get_sms_sender.cache_clear()
    try:
        assert isinstance(get_sms_sender(), expected)
    finally:
        get_sms_sender.cache_clear()


# --- the endpoint's behaviour when sending fails ----------------------------


def test_request_otp_reports_a_send_failure(client: TestClient):
    """A failed SMS must not look like success: the app shows `sms_failed`."""

    class Failing:
        def send_otp(self, phone: str, code: str) -> None:
            raise SmsDeliveryError("provider down")

    from main import app

    app.dependency_overrides[get_sms_sender] = Failing
    response = client.post("/auth/otp/request", json={"phone": PHONE})

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "sms_failed"


def test_failed_send_leaves_no_cooldown(client: TestClient, sms):
    """The dropped challenge means the user can ask again straight away,
    instead of waiting out a cooldown for a code that never arrived."""

    class Failing:
        def send_otp(self, phone: str, code: str) -> None:
            raise SmsDeliveryError("provider down")

    from main import app

    app.dependency_overrides[get_sms_sender] = Failing
    assert client.post("/auth/otp/request", json={"phone": PHONE}).status_code == 502

    # Back to a working provider: no 429, and the code that arrives works.
    app.dependency_overrides[get_sms_sender] = lambda: sms
    assert client.post("/auth/otp/request", json={"phone": PHONE}).status_code == 202

    verify = client.post("/auth/otp/verify", json={"phone": PHONE, "code": sms.last_code()})
    assert verify.json()["status"] == "signup_required"
