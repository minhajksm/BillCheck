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
