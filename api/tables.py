import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Date, ForeignKey, Integer, Numeric, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base, UTCDateTime, utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # E.164, e.g. "+919876543210". None for an anonymous account, which has
    # no way to be recovered and is held only by the token on one device.
    phone: Mapped[str | None] = mapped_column(String(16), unique=True, nullable=True)
    # Empty for an anonymous account; the app greets those without a name.
    name: Mapped[str] = mapped_column(String(80))
    # DPDP: which consent text the user agreed to, and when.
    consent_version: Mapped[str] = mapped_column(String(20))
    consented_at: Mapped[datetime] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class OtpChallenge(Base):
    """One code sent to one phone number. Codes are stored only as HMACs."""

    __tablename__ = "otp_challenges"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    phone: Mapped[str] = mapped_column(String(16), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # Set when a verified number has no account yet: lets the app finish sign-up.
    signup_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    signup_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    signup_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class AuthSession(Base):
    """A signed-in device. The app holds the token; we keep only its hash."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Case(Base):
    """One hospital admission, followed by one or more family members."""

    __tablename__ = "cases"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(120))
    hospital_name: Mapped[str] = mapped_column(String(120))
    hospital_area: Mapped[str] = mapped_column(String(120))
    patient_name: Mapped[str] = mapped_column(String(80))
    ip_number: Mapped[str] = mapped_column(String(40))
    bed: Mapped[str | None] = mapped_column(String(20))
    # Null where the bill a case was opened from printed no admission date.
    # A case is the record of a real admission and a plausible-looking guess
    # in one is worse than a blank: the family is asked for it instead, and
    # the stay check stays off until they give it.
    admitted_on: Mapped[date | None] = mapped_column(Date)
    closed_on: Mapped[date | None] = mapped_column(Date)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    members: Mapped[list["CaseMember"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", order_by="CaseMember.joined_at"
    )
    bills: Mapped[list["Bill"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", order_by="Bill.bill_date"
    )


class CaseMember(Base):
    """A family member who can see and add to a case."""

    __tablename__ = "case_members"
    __table_args__ = (UniqueConstraint("case_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    joined_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    case: Mapped[Case] = relationship(back_populates="members")
    user: Mapped[User] = relationship()


class CaseInvite(Base):
    """A code a member shares so family can join the case.

    Separate from the case id on purpose: the id shows up in links and logs,
    while a code can expire and be withdrawn. Only its hash is kept.
    """

    __tablename__ = "case_invites"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Bill(Base):
    """One day's itemized bill.

    The photographed pages are never stored: they are read into line items at
    upload and discarded, so the only health data kept is the structured bill.
    """

    __tablename__ = "bills"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    bill_date: Mapped[date] = mapped_column(Date)
    page_count: Mapped[int] = mapped_column(Integer, default=1)
    # The discount the bill prints across the whole of it, where it prints one.
    # Null covers both a bill with no discount and one read before this column.
    discount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    # What the hospital is asking for: the lines' own amounts less the
    # discount. Not the sum of the lines, on a bill that discounts them.
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    case: Mapped[Case] = relationship(back_populates="bills")
    line_items: Mapped[list["LineItem"]] = relationship(
        back_populates="bill", cascade="all, delete-orphan", order_by="LineItem.position"
    )
    flags: Mapped[list["Flag"]] = relationship(
        back_populates="bill", cascade="all, delete-orphan", order_by="Flag.position"
    )


class UploadAttempt(Base):
    """One bill sent to the reader, kept to cap how many a person can send.

    Counted per attempt, not per saved bill: a read that fails still costs a
    paid call, so failures count too. Holds no bill content.
    """

    __tablename__ = "upload_attempts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)


class LineItem(Base):
    """One row of the itemized bill, as printed."""

    __tablename__ = "line_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    bill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bills.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(200))
    # Quantity or date as printed, e.g. "6 vials" or "11 Oct, 10:30 am".
    detail: Mapped[str | None] = mapped_column(String(120))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    # Gross, as the line prints it. A rate checked against a price list is
    # quoted gross, so this is the figure the audit compares.
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    # The same line after the bill's discount, where the bill prints a second
    # money column for it. Null where it prints only one.
    net_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    # What kind of charge this is, from the reader's PHASE 2 categories (see
    # analysis.Category). The report groups the bill by it, so a family can
    # see what the consumables came to. "unclassified" is both the reader's
    # own fallback and what bills read before this column carry.
    category: Mapped[str] = mapped_column(String(24), server_default="unclassified")

    bill: Mapped[Bill] = relationship(back_populates="line_items")


class Flag(Base):
    """A charge worth asking about.

    Holds the facts only: what was billed, what it was checked against, and by
    how much they differ. The app turns those into translated copy, so no
    user-facing sentence is stored here.
    """

    __tablename__ = "flags"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    bill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bills.id", ondelete="CASCADE"), index=True)
    line_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("line_items.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    # What was noticed: "above_mrp", "duplicate" and "quantity" come from the
    # price lists, "analysis_finding" from the reader's own analysis, and
    # "date_outside_stay" from the stay check. See flag_kinds.py, which also
    # keeps the older kinds bills read before that change carry.
    kind: Mapped[str] = mapped_column(String(30))
    # "red" for a clear issue, "amber" for one worth asking about.
    level: Mapped[str] = mapped_column(String(10))
    # "open", "corrected" or "explained".
    status: Mapped[str] = mapped_column(String(12), default="open")
    billed: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    reference_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    # What the charge was checked against, e.g. "mrp", "nppa", "quantity_norm".
    reference_source: Mapped[str] = mapped_column(String(30))
    # The reference's own numbers, for the app to put in its copy: unit MRP,
    # the usual quantity range, and so on.
    reference_detail: Mapped[dict] = mapped_column(JSON, default=dict)
    excess: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    bill: Mapped[Bill] = relationship(back_populates="flags")
    line_item: Mapped[LineItem | None] = relationship()
