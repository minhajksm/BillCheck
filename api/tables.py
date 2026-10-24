import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
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
    # What read it, and everything it found. Nothing serves these; they are
    # deleted with the bill rather than left to the database's own cascade,
    # so a case that goes takes its reading with it under either engine.
    reads: Mapped[list["BillRead"]] = relationship(back_populates="bill", cascade="all, delete-orphan")
    reader_findings: Mapped[list["ReaderFinding"]] = relationship(
        back_populates="bill", cascade="all, delete-orphan"
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


class BillRead(Base):
    """What read one bill, and what it said about its own reading.

    None of this reaches a family. It is here so the reader can be judged
    across bills and over time: a run of poor readings is only attributable
    if the model, the effort and the prompt that produced them are on the row
    beside them. A version number would have to be remembered by whoever
    edits the prompt, so the prompt's own digest stands in for one.

    One row per bill, and it goes when the bill does.
    """

    __tablename__ = "bill_reads"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    bill_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bills.id", ondelete="CASCADE"), unique=True, index=True
    )
    # "claude" or "stub", and which model and effort it was asked for.
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(60))
    effort: Mapped[str] = mapped_column(String(10))
    prompt_digest: Mapped[str] = mapped_column(String(16), index=True)
    # The reader's own account of the reading: how sure it was, whether it
    # asked for a human, and why. Nothing acts on these today.
    extraction_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    needs_human_review: Mapped[bool] = mapped_column(Boolean, default=False)
    review_reasons: Mapped[list] = mapped_column(JSON, default=list)
    # PHASE 3's structural observations: the shape of the bill as a whole.
    consumable_share_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    unitemised_share_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    unreadable_line_count: Mapped[int] = mapped_column(Integer, default=0)
    lines_read: Mapped[int] = mapped_column(Integer, default=0)
    pages_processed: Mapped[int] = mapped_column(Integer, default=0)
    # How many findings came back, and how many a family was shown. The gap
    # is what `reader_findings` explains row by row.
    findings_returned: Mapped[int] = mapped_column(Integer, default=0)
    findings_shown: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)

    bill: Mapped[Bill] = relationship(back_populates="reads")


class ReaderFinding(Base):
    """Every finding the reader returned for a bill, shown to a family or not.

    The dropped ones are the point. A finding the reader itself called low
    severity, or one naming lines that aren't in its own transcription, used
    to go to a log line and nowhere else -- so the two questions worth asking
    of a reader, how often it does that and whether it got better, had no
    answer. Both are a `GROUP BY` away now.

    `flag_id` is the flag a shown finding became, which is how the family's
    own verdict -- corrected, explained, or left open -- is reachable from
    here. It is cleared rather than cascaded if that flag ever goes: what the
    reader said is still a fact about the reading.
    """

    __tablename__ = "reader_findings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    bill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bills.id", ondelete="CASCADE"), index=True)
    flag_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("flags.id", ondelete="SET NULL"))
    # The reader's own id for it, which nothing promises is unique.
    finding_id: Mapped[str] = mapped_column(String(40))
    rule: Mapped[str] = mapped_column(String(200), index=True)
    severity: Mapped[str] = mapped_column(String(10), index=True)
    # "shown", "dropped_low_severity" or "dropped_unknown_lines". See review.py.
    outcome: Mapped[str] = mapped_column(String(24), index=True)
    # The reader's own words. Without them a dropped finding cannot be judged,
    # which is the whole of what this table is for.
    statement: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text)
    confirmation_required: Mapped[str] = mapped_column(Text)
    # The reader's line ids, and the same lines as the family would see them
    # numbered. Empty numbers on a finding about the bill as a whole.
    line_ids: Mapped[str] = mapped_column(String(300))
    line_numbers: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    bill: Mapped[Bill] = relationship(back_populates="reader_findings")
