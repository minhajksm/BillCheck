"""The bill's own arithmetic, checked in code.

The reader transcribes; this adds up. Every sum on the page -- quantity x
rate on a line, the lines against the sub-total, the discount, the payable
total, the deposits against what is paid and what is still due -- has an
answer that needs nothing but the bill, so it is worked out here rather than
asked of a model, which gets long bills wrong and reports a two-rupee
rounding difference as a finding.

What comes out is two things. A list of checks, which is what the report
shows a family whatever the bill: "everything on this bill adds up", with
the ticks that prove it. And a flag for each check that fails, which joins
the rest of the questions.

One principle decides what fails: **a check fails only when the bill asks
for more than its own numbers support.** A line billed below quantity x rate
is usually a discount on that line, and a total below the sum of its lines
is in the family's favour; neither is a question for the billing desk, so
both pass, and claim nothing. A failure is never a verdict either: the
figures were read off a photograph, and the flag says to check them against
the paper first.

Indian bills round each line to the paisa or the rupee, so sums drift by a
rupee or two across a bill. A difference within a rupee a line is rounding,
said out loud as such, never a question.
"""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from analysis import BillAnalysis
from audit import Flag
from flag_kinds import FlagKind
from ocr import to_decimal

ONE_RUPEE = Decimal("1")
PAISA = Decimal("0.01")
# The GST rates a line amount may already include on top of quantity x rate,
# as pharmacy bills often print it. A line matching any of them adds up.
GST_RATES = (Decimal("0.05"), Decimal("0.12"), Decimal("0.18"))
# A discount is "on every line" if each line's net is within this many
# percentage points of the bill's overall rate.
UNIFORM_POINTS = Decimal("1")


@dataclass(frozen=True)
class Check:
    """One sum on the bill, and how it came out.

    `status` is "ok", "mismatch" (the bill asks for more than its own numbers
    give), or "note" (said for clarity, never a question: rounding). The
    figures are the ones the app shows beside the check.
    """

    kind: str
    status: str
    amount: Decimal | None = None
    expected: Decimal | None = None
    printed: Decimal | None = None
    checked: int | None = None
    of: int | None = None
    count: int | None = None
    percent: Decimal | None = None
    uniform: bool | None = None
    positions: tuple[int, ...] = ()

    def as_dict(self) -> dict:
        """Stored as JSON on the bill: money as strings, as everywhere else."""
        out: dict = {"kind": self.kind, "status": self.status}
        for name in ("amount", "expected", "printed", "percent"):
            value = getattr(self, name)
            if value is not None:
                out[name] = str(value)
        for name in ("checked", "of", "count", "uniform"):
            value = getattr(self, name)
            if value is not None:
                out[name] = value
        if self.positions:
            out["positions"] = list(self.positions)
        return out


@dataclass(frozen=True)
class Arithmetic:
    """Everything the bill's own numbers say, worked out once."""

    checks: list[Check]
    flags: list[Flag]
    # What has been paid and what is still due: the bill's own figures where
    # it prints them, else what its deposits add up to.
    paid: Decimal | None
    balance: Decimal | None
    payments: list[dict] = field(default_factory=list)


def _money(value: Decimal) -> Decimal:
    return value.quantize(PAISA, rounding=ROUND_HALF_UP)


def _tolerance(lines: int) -> Decimal:
    """A rupee a line, and never less than a rupee."""
    return max(ONE_RUPEE, ONE_RUPEE * lines)


def _line_adds_up(quantity: Decimal, rate: Decimal, amount: Decimal) -> bool:
    """At or below quantity x rate, or quantity x rate plus a standard GST rate."""
    base = quantity * rate
    if amount <= base + ONE_RUPEE:
        return True
    return any(abs(amount - base * (1 + gst)) <= ONE_RUPEE for gst in GST_RATES)


def _flag(kind: FlagKind, row: int, billed: Decimal, expected: Decimal, detail: dict) -> Flag:
    """A question raised by the bill's own arithmetic.

    Amber: the sum is certain, but its figures were read off a photograph,
    and the copy says to check them against the paper before asking.
    """
    return Flag(
        kind=kind,
        level="amber",
        row_position=row,
        billed=_money(billed),
        reference_amount=_money(expected),
        reference_source="bill",
        excess=_money(billed - expected),
        reference_detail=detail,
    )


def check_bill(analysis: BillAnalysis) -> Arithmetic:
    header = analysis.bill
    lines = analysis.lines
    checks: list[Check] = []
    flags: list[Flag] = []

    # --- each line: quantity x rate ------------------------------------------
    checkable = 0
    over: list[int] = []
    for position, line in enumerate(lines, start=1):
        quantity, rate, amount = to_decimal(line.quantity), to_decimal(line.rate), to_decimal(line.amount)
        if quantity is None or rate is None or amount is None or quantity <= 0:
            continue
        checkable += 1
        if not _line_adds_up(quantity, rate, amount):
            over.append(position)
            expected = quantity * rate
            flags.append(
                _flag(
                    "line_math",
                    position,
                    amount,
                    expected,
                    {
                        "line_numbers": str(position),
                        "quantity": str(quantity.normalize()),
                        "rate": str(_money(rate)),
                        "computed": str(_money(expected)),
                        "stated": str(_money(amount)),
                        "difference": str(_money(amount - expected)),
                    },
                )
            )
    if checkable:
        checks.append(
            Check(
                "lines",
                "mismatch" if over else "ok",
                checked=checkable,
                of=len(lines),
                positions=tuple(over),
            )
        )

    # --- the lines against the sub-total -------------------------------------
    amounts = [to_decimal(line.amount) for line in lines]
    summed = _money(sum((a for a in amounts if a is not None), Decimal("0")))
    tolerance = _tolerance(len(lines))
    discount = to_decimal(header.discount)
    subtotal_printed = to_decimal(header.subtotal)
    total_printed = to_decimal(header.total)
    # With no discount and no sub-total printed, the total is the sum the
    # lines should reach.
    target = (
        subtotal_printed if subtotal_printed is not None else (total_printed if discount is None else None)
    )
    if lines and target is not None:
        if target - summed > tolerance:
            checks.append(Check("subtotal", "mismatch", expected=summed, printed=_money(target)))
            flags.append(
                _flag(
                    "total_mismatch",
                    0,
                    target,
                    summed,
                    {
                        "summed": str(summed),
                        "stated": str(_money(target)),
                        "difference": str(_money(target - summed)),
                    },
                )
            )
        else:
            checks.append(Check("subtotal", "ok", amount=summed))

    # --- the discount, and the payable total ---------------------------------
    gross = subtotal_printed if subtotal_printed is not None else summed
    if discount is not None and discount > 0 and gross > 0:
        percent = (discount * 100 / gross).quantize(ONE_RUPEE, rounding=ROUND_HALF_UP)
        rates = [
            (to_decimal(line.net_amount) or Decimal("0")) / amount
            for line, amount in zip(lines, amounts, strict=True)
            if line.net_amount is not None and amount
        ]
        overall = 1 - discount / gross
        uniform = (
            len(rates) == len(lines)
            and len(rates) > 0
            and all(abs(rate - overall) * 100 <= UNIFORM_POINTS for rate in rates)
        )
        checks.append(Check("discount", "ok", amount=_money(discount), percent=percent, uniform=uniform))

        if total_printed is not None:
            expected_total = _money(gross - discount)
            if total_printed - expected_total > ONE_RUPEE:
                checks.append(
                    Check("payable", "mismatch", expected=expected_total, printed=_money(total_printed))
                )
                flags.append(
                    _flag(
                        "total_mismatch",
                        0,
                        total_printed,
                        expected_total,
                        {
                            "summed": str(expected_total),
                            "stated": str(_money(total_printed)),
                            "difference": str(_money(total_printed - expected_total)),
                            "discount": str(_money(discount)),
                        },
                    )
                )
            else:
                checks.append(Check("payable", "ok", amount=_money(total_printed)))

    # The net column against the total: within a rupee a line it is the
    # rounding of each line to the rupee, said so plainly, and never a flag.
    # A reader asked to look for discrepancies reported exactly this as one.
    nets = [to_decimal(line.net_amount) for line in lines]
    if total_printed is not None and lines and all(net is not None for net in nets):
        net_sum = _money(sum((net for net in nets if net is not None), Decimal("0")))
        difference = _money(total_printed - net_sum)
        if difference != 0 and abs(difference) <= tolerance:
            checks.append(Check("rounding", "note", amount=_money(total_printed), expected=net_sum))

    # --- what has been paid, and what is still due ---------------------------
    payments = [
        {"date": p.date, "mode": p.mode, "amount": str(_money(amount))}
        for p in analysis.payments
        if (amount := to_decimal(p.amount)) is not None and amount > 0
    ]
    deposits = _money(sum((Decimal(p["amount"]) for p in payments), Decimal("0")))
    paid_printed = to_decimal(header.amount_paid)

    if payments and paid_printed is not None and deposits - paid_printed > ONE_RUPEE:
        # The deposits listed come to more than the bill credits as paid.
        checks.append(
            Check("paid", "mismatch", expected=deposits, printed=_money(paid_printed), count=len(payments))
        )
        flags.append(
            _flag(
                "advance_not_deducted",
                0,
                deposits,
                paid_printed,
                {
                    "deposits": str(deposits),
                    "credited": str(_money(paid_printed)),
                    "count": str(len(payments)),
                },
            )
        )
    elif payments:
        checks.append(Check("paid", "ok", amount=deposits, count=len(payments)))

    paid = _money(paid_printed) if paid_printed is not None else (deposits if payments else None)
    payable = _money(total_printed) if total_printed is not None else None
    balance_printed = to_decimal(header.balance)
    balance: Decimal | None = None
    if payable is not None and paid is not None:
        expected_balance = _money(max(payable - paid, Decimal("0")))
        if balance_printed is not None and balance_printed - expected_balance > ONE_RUPEE:
            checks.append(
                Check("balance", "mismatch", expected=expected_balance, printed=_money(balance_printed))
            )
            flags.append(
                _flag(
                    "advance_not_deducted",
                    0,
                    balance_printed,
                    expected_balance,
                    {
                        "due": str(_money(balance_printed)),
                        "expected_due": str(expected_balance),
                        "paid": str(paid),
                    },
                )
            )
            balance = _money(balance_printed)
        else:
            balance = _money(balance_printed) if balance_printed is not None else expected_balance
            checks.append(Check("balance", "ok", amount=balance))
    elif balance_printed is not None:
        balance = _money(balance_printed)

    return Arithmetic(checks=checks, flags=flags, paid=paid, balance=balance, payments=payments)
