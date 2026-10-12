import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, StringConstraints

from phone import normalize_indian_mobile


def _indian_mobile(value: str) -> str:
    phone = normalize_indian_mobile(value)
    if phone is None:
        raise ValueError("Enter a 10-digit Indian mobile number.")
    return phone


IndianMobile = Annotated[str, AfterValidator(_indian_mobile)]


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class LineItem(BaseModel):
    """One row of an itemized hospital bill. Amounts are in rupees."""

    name: str
    detail: str | None = Field(default=None, description='Quantity or date as printed, e.g. "6 vials".')
    amount: float


class BillUploadResponse(BaseModel):
    id: str
    status: Literal["received"]
    content_type: str
    size_bytes: int
    line_items: list[LineItem] = Field(
        default_factory=list,
        description="Structured rows from the bill. Empty until OCR is wired up.",
    )


class ApiError(BaseModel):
    """Error body. `code` is stable so the app can show translated copy."""

    code: str
    message: str


class OtpRequest(BaseModel):
    phone: IndianMobile = Field(examples=["+919876543210"])


class OtpRequestResponse(BaseModel):
    expires_in_seconds: int
    resend_after_seconds: int


class OtpVerify(BaseModel):
    phone: IndianMobile
    code: Annotated[str, StringConstraints(pattern=r"^\d{6}$")]


class UserOut(BaseModel):
    id: uuid.UUID
    phone: str
    name: str


class LoggedIn(BaseModel):
    status: Literal["logged_in"] = "logged_in"
    token: str
    expires_at: datetime
    user: UserOut


class SignupRequired(BaseModel):
    """The number is verified but has no account. Finish with POST /auth/signup."""

    status: Literal["signup_required"] = "signup_required"
    signup_token: str
    expires_at: datetime


OtpVerifyResponse = Annotated[LoggedIn | SignupRequired, Field(discriminator="status")]


class Signup(BaseModel):
    signup_token: str
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    consent: Literal[True] = Field(
        description="The user agreed to the consent text shown in the app (DPDP). Must be true."
    )
