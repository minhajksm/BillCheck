import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, StringConstraints

from analysis import Category
from flag_kinds import FlagKind
from phone import normalize_indian_mobile


def _indian_mobile(value: str) -> str:
    phone = normalize_indian_mobile(value)
    if phone is None:
        raise ValueError("Enter a 10-digit Indian mobile number.")
    return phone


IndianMobile = Annotated[str, AfterValidator(_indian_mobile)]


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    # Whether POST /auth/anonymous will be answered. The app asks before
    # offering "use it without signing in", so the two cannot disagree.
    anonymous_accounts: bool = False


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
    # None on an anonymous account, which is how the app knows to say the
    # bills are held on this phone alone.
    phone: str | None
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


class AnonymousAccount(BaseModel):
    consent: Literal[True] = Field(
        description="The user agreed to the consent text shown in the app (DPDP). Must be true."
    )


# --- cases ------------------------------------------------------------------


class CaseCreate(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    hospital_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    hospital_area: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    patient_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    ip_number: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
    bed: Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)] | None = None
    admitted_on: date


class CaseUpdate(BaseModel):
    """Correcting the admission details. Every field is optional: what is sent
    is what changes, so a field left out keeps its value and `bed: null`
    clears it."""

    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)] | None = (
        None
    )
    hospital_name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)] | None
    ) = None
    hospital_area: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)] | None
    ) = None
    patient_name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)] | None
    ) = None
    ip_number: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)] | None
    ) = None
    bed: Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)] | None = None
    admitted_on: date | None = None
    # Sent as null to reopen a stay. A bill with a discharge date on it closes
    # the case, and a family who is still in hospital has to be able to say so.
    closed_on: date | None = None


class MemberOut(BaseModel):
    id: uuid.UUID
    name: str
    is_you: bool


class DailyBillOut(BaseModel):
    id: uuid.UUID
    date: date
    item_count: int
    total: float
    flag_count: int
    open_flag_count: int


class CaseOut(BaseModel):
    id: uuid.UUID
    title: str
    hospital_name: str
    hospital_area: str
    patient_name: str
    ip_number: str
    bed: str | None
    admitted_on: date
    closed_on: date | None
    members: list[MemberOut]
    # Whether the caller is the one who started it. Only they can delete a case,
    # since it takes the bills away from everyone following it.
    is_owner: bool
    # Oldest first.
    bills: list[DailyBillOut]
    recovered_amount: float


class InviteCreated(BaseModel):
    """The code is shown once, here. Only its hash is stored."""

    id: uuid.UUID
    code: str
    expires_at: datetime


class InviteOut(BaseModel):
    id: uuid.UUID
    created_by: uuid.UUID
    created_at: datetime
    expires_at: datetime


class JoinCase(BaseModel):
    # In the body, not the URL, so it never lands in access logs.
    code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=8, max_length=64)]


# --- bills ------------------------------------------------------------------


class LineItemOut(BaseModel):
    id: uuid.UUID
    position: int
    name: str
    detail: str | None
    quantity: float | None
    amount: float
    category: Category


class FlagOut(BaseModel):
    """Facts only. The app turns these into copy in the family's language."""

    id: uuid.UUID
    position: int
    line_item_id: uuid.UUID | None
    kind: FlagKind
    level: Literal["red", "amber"]
    status: Literal["open", "corrected", "explained"]
    billed: float
    reference_amount: float
    reference_source: str
    reference_detail: dict
    excess: float


class BillOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    date: date
    page_count: int
    total: float
    line_items: list[LineItemOut]
    flags: list[FlagOut]


class FlagUpdate(BaseModel):
    status: Literal["open", "corrected", "explained"]
