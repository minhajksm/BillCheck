import pytest
from pydantic import ValidationError

from phone import mask_phone, normalize_indian_mobile
from settings import Settings


@pytest.mark.parametrize(
    "raw",
    [
        "9876543210",
        "98765 43210",
        "+91 98765-43210",
        "+919876543210",
        "09876543210",
        "919876543210",
        "0091 98765 43210",
    ],
)
def test_normalizes_common_formats(raw: str):
    assert normalize_indian_mobile(raw) == "+919876543210"


@pytest.mark.parametrize(
    "raw", ["", "12345", "5876543210", "987654321", "98765432100", "+14155550100", "abcdefghij"]
)
def test_rejects_non_mobiles(raw: str):
    assert normalize_indian_mobile(raw) is None


def test_mask_phone():
    assert mask_phone("+919876543210") == "+91******3210"


def test_production_refuses_dev_defaults():
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(environment="production")
    with pytest.raises(ValidationError, match="OTP_DELIVERY"):
        Settings(environment="production", secret_key="x" * 40)


def test_production_refuses_the_stub_ocr():
    """The stub returns a sample bill. Shipping it would show a real family
    charges that aren't on their bill."""
    with pytest.raises(ValidationError, match="OCR_PROVIDER"):
        Settings(
            environment="production",
            secret_key="x" * 40,
            otp_delivery="msg91",
            msg91_auth_key="key",
            msg91_template_id="t",
        )


def test_claude_ocr_needs_a_key():
    with pytest.raises(ValidationError, match="ANTHROPIC_API_KEY"):
        Settings(ocr_provider="claude", anthropic_api_key="")


def test_production_refuses_to_start_showing_unconfirmed_questions(monkeypatch: pytest.MonkeyPatch):
    """REVIEW_KEEP_ALL is for watching the reader on a laptop. Left on, it would
    show a family questions the rows already answered."""
    for name, value in {
        "ENVIRONMENT": "production",
        "SECRET_KEY": "x" * 48,
        "OTP_DELIVERY": "msg91",
        "MSG91_AUTH_KEY": "k",
        "MSG91_TEMPLATE_ID": "t",
        "OCR_PROVIDER": "claude",
        "ANTHROPIC_API_KEY": "sk-test",
        "REVIEW_KEEP_ALL": "true",
    }.items():
        monkeypatch.setenv(name, value)

    with pytest.raises(ValidationError, match="REVIEW_KEEP_ALL"):
        Settings(_env_file=None)

    monkeypatch.setenv("REVIEW_KEEP_ALL", "false")
    assert Settings(_env_file=None).review_keep_all is False
