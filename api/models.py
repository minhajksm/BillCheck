import uuid
from datetime import date, datetime
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, BaseModel, Field, StringConstraints, model_validator

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
    # Whether they have agreed to lab reports. The app asks once, before the
    # first, because the sign-up consent covers bills and only bills.
    lab_consent: bool = False


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
    member_id: uuid.UUID
    """Whose admission this is. A case is always opened under a member."""
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


class FollowerOut(BaseModel):
    """An account following a member. `id` is the user's."""

    id: uuid.UUID
    name: str
    is_you: bool


class MemberRef(BaseModel):
    """Whose a case or a report is, for a heading."""

    id: uuid.UUID
    name: str


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
    admitted_on: date | None
    """Null where the bill printed none and nobody has filled it in yet."""
    closed_on: date | None
    member: MemberRef | None
    """Null until the family says whose admission it is. See tables.Case."""
    # Whether the caller is the one who started it. Only they can delete a case,
    # since it takes the bills away from everyone following the member.
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


class JoinMember(BaseModel):
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
    """Gross, as the line prints it."""
    net_amount: float | None
    """The same line after the bill's discount, where it prints one. Else null."""
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


class CheckOut(BaseModel):
    """One sum on the bill, checked in code. Only the fields its kind uses are set."""

    kind: Literal["lines", "subtotal", "discount", "payable", "rounding", "paid", "balance"]
    status: Literal["ok", "mismatch", "note"]
    """"mismatch": the bill asks for more than its own numbers give. "note": said
    for clarity and never a question, e.g. rounding."""
    amount: float | None = None
    expected: float | None = None
    printed: float | None = None
    checked: int | None = None
    of: int | None = None
    count: int | None = None
    percent: float | None = None
    uniform: bool | None = None
    positions: list[int] = []


class PaymentOut(BaseModel):
    """A deposit, advance or receipt, as the bill lists it."""

    date: str
    mode: str
    amount: float


class BillOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    date: date
    page_count: int
    subtotal: float
    """What the lines come to, before any discount."""
    discount: float | None
    """The discount the bill prints across the whole of it. Null when none."""
    total: float
    """What the hospital is asking for: the sub-total less the discount."""
    checks: list[CheckOut] = []
    """The bill's own arithmetic, checked in code. Empty on bills read before it."""
    payments: list[PaymentOut] = []
    paid: float | None = None
    balance: float | None = None
    """Still due. 0 is "nothing left to pay"; null, the bill doesn't say."""
    line_items: list[LineItemOut]
    flags: list[FlagOut]


class FlagUpdate(BaseModel):
    status: Literal["open", "corrected", "explained"]


class LabConsent(BaseModel):
    """Agreeing to lab reports being stored and explained. Only `true` is a body."""

    consent: Literal[True]


class LabTestOut(BaseModel):
    """One result, verbatim, and what it is. Never what it means for the patient."""

    name: str
    value: str
    unit: str
    range: str
    """Exactly as the report prints it. Empty where it prints none."""
    status: Literal["low", "high", "in_range", "no_range"]
    """Against the printed range only. Checked by arithmetic where both are numbers."""
    explanation_en: str
    explanation_hi: str


class LabReportOut(BaseModel):
    id: uuid.UUID
    member: MemberRef | None
    """Null until the family says whose report it is."""
    lab_name: str
    patient_name: str
    report_date: str
    """As printed. Never parsed."""
    page_count: int
    tests: list[LabTestOut]
    summary_en: str
    summary_hi: str
    questions_en: list[str]
    questions_hi: list[str]
    urgent: bool
    """The report itself marked a result critical: show it to a doctor today."""
    created_at: datetime


class LabReportSummaryOut(BaseModel):
    """A row in the list of saved reports."""

    id: uuid.UUID
    lab_name: str
    patient_name: str
    report_date: str
    member: MemberRef | None
    test_count: int
    outside_range: int
    urgent: bool
    created_at: datetime


# --- members ----------------------------------------------------------------


MemberName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class MemberCreate(BaseModel):
    name: MemberName


class MemberUpdate(BaseModel):
    name: MemberName


class MemberSummaryOut(BaseModel):
    """A row in the list of members."""

    id: uuid.UUID
    name: str
    is_owner: bool
    followers: list[FollowerOut]
    admission_count: int
    # Admissions with no discharge yet: someone is in hospital.
    open_admission_count: int
    open_flag_count: int
    lab_report_count: int


class MemberOut(BaseModel):
    """A member and everything under them."""

    id: uuid.UUID
    name: str
    # Whether the caller added this member. Only they can delete it or remove
    # someone, since it takes everything away from everyone following.
    is_owner: bool
    followers: list[FollowerOut]
    # Newest admission first.
    cases: list[CaseOut]
    # Newest first.
    lab_reports: list[LabReportSummaryOut]


class FileUnder(BaseModel):
    """Whose a bill or a report is: someone already there, or someone new.

    Exactly one. A new member is named here, usually with the name the bill
    or report printed, which the app offers as the answer.
    """

    member_id: uuid.UUID | None = None
    new_member_name: MemberName | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> Self:
        if (self.member_id is None) == (self.new_member_name is None):
            raise ValueError("Give either member_id or new_member_name.")
        return self


class UnfiledOut(BaseModel):
    """What the caller scanned and has not yet said whose it is."""

    cases: list[CaseOut]
    lab_reports: list[LabReportSummaryOut]
