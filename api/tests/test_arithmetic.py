"""The bill's own arithmetic, checked in code.

Built around one real final bill's figures -- nine lines, a 19% discount
applied to each, three deposits -- with every name taken off. It is the
bill on which the reader, asked to look for discrepancies, reported a two-
rupee rounding difference across nine lines as a finding.
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from analysis import AnalysedLine, BillAnalysis, BillHeader, Payment, Structural
from arithmetic import check_bill

# description, quantity, rate, gross amount, net amount
FINAL_BILL = [
    ("Complete Blood Count-CBC", 1, 300, 300, 242),
    ("ROOM CHARGES", 3, 1300, 3900, 3152),
    ("RMO CHARGES", 3, 700, 2100, 1697),
    ("NURSING CHARGES", 3, 500, 1500, 1212),
    ("DOCTOR VISIT CHARGES", 3, 1500, 4500, 3637),
    ("Anesthesia Charges", 1, 7000, 7000, 5658),
    ("ASSISTANT CHARGES", 1, 6000, 6000, 4850),
    ("OT Charges", 1, 5000, 5000, 4042),
    ("Surgeon Charges", 1, 13000, 13000, 10508),
]
Money = float | None

DEPOSITS = [("04/05/2025", "Cash", 5000), ("06/05/2025", "Cash", 25000), ("06/05/2025", "UPI", 5000)]


def line(n: int, name: str, quantity: Money, rate: Money, amount: Money, net: Money = None) -> AnalysedLine:
    return AnalysedLine(
        line_id=f"L{n}",
        description_verbatim=name,
        category="unclassified",
        quantity=quantity,
        unit="",
        rate=rate,
        amount=amount,
        net_amount=net,
        date="",
        mrp_printed=None,
    )


def bill(
    rows: list = FINAL_BILL,
    *,
    subtotal: Money = 43300,
    discount: Money = 8300,
    total: Money = 35000,
    paid: Money = 35000,
    balance: Money = 0,
    deposits: list = DEPOSITS,
) -> BillAnalysis:
    return BillAnalysis(
        bill=BillHeader(
            hospital="Sample Multispeciality Hospital",
            bill_no="",
            bill_date="",
            admission_date="",
            discharge_date="",
            room_category="",
            subtotal=subtotal,
            discount=discount,
            total=total,
            amount_paid=paid,
            balance=balance,
            patient_name="TEST PATIENT",
            ip_number="",
            pages_processed=1,
            extraction_confidence=0.9,
        ),
        payments=[Payment(date=d, mode=m, amount=a) for d, m, a in deposits],
        lines=[line(n, *row) for n, row in enumerate(rows, start=1)],
        findings=[],
        requires_reference_price=[],
        structural=Structural(consumable_share_pct=0, unitemised_share_pct=0, unreadable_line_count=0),
        needs_human_review=False,
        review_reasons=[],
    )


def by_kind(result) -> dict[str, dict]:
    return {check.kind: check.as_dict() for check in result.checks}


# --- a bill that adds up -----------------------------------------------------


def test_a_bill_that_adds_up_says_so_check_by_check():
    result = check_bill(bill())
    checks = by_kind(result)

    assert result.flags == [], "nothing to ask about the arithmetic"
    assert checks["lines"] == {"kind": "lines", "status": "ok", "checked": 9, "of": 9}
    assert checks["subtotal"] == {"kind": "subtotal", "status": "ok", "amount": "43300.00"}
    assert checks["discount"]["percent"] == "19"
    assert checks["discount"]["uniform"] is True, "the same 19% off every line"
    assert checks["payable"]["status"] == "ok"
    assert checks["paid"] == {"kind": "paid", "status": "ok", "amount": "35000.00", "count": 3}
    assert checks["balance"] == {"kind": "balance", "status": "ok", "amount": "0.00"}


def test_the_two_rupees_is_rounding_said_plainly_never_a_question():
    """The net column comes to 34,998 against a total of 35,000: each of nine
    lines rounded to the rupee. The reader reported it as a finding."""
    result = check_bill(bill())

    rounding = by_kind(result)["rounding"]
    assert rounding["status"] == "note"
    assert rounding["expected"] == "34998.00"
    assert rounding["amount"] == "35000.00"
    assert not [flag for flag in result.flags if flag.kind == "total_mismatch"]


def test_what_was_paid_and_what_is_left_come_out_of_it():
    result = check_bill(bill())

    assert result.paid == Decimal("35000.00")
    assert result.balance == Decimal("0.00")
    assert [p["mode"] for p in result.payments] == ["Cash", "Cash", "UPI"]


# --- a line ------------------------------------------------------------------


def test_a_line_charging_more_than_quantity_times_rate_is_a_question():
    rows = [*FINAL_BILL[:3], ("NURSING CHARGES", 3, 500, 1800, None), *FINAL_BILL[4:]]
    result = check_bill(bill(rows, subtotal=43600, discount=None, total=43600, paid=None, deposits=[]))

    (flag,) = result.flags
    assert flag.kind == "line_math"
    assert flag.level == "amber", "the sum is certain; the figures were read off a photo"
    assert flag.row_position == 4
    assert flag.excess == Decimal("300.00")
    assert flag.reference_detail["computed"] == "1500.00"
    assert by_kind(result)["lines"]["positions"] == [4]


def test_a_line_below_quantity_times_rate_passes_and_claims_nothing():
    """Usually a discount on that line, and never a question for the desk."""
    rows = [("Dressing", 2, 100, 150, None)]
    result = check_bill(bill(rows, subtotal=150, discount=None, total=150, paid=None, deposits=[]))

    assert result.flags == []
    assert by_kind(result)["lines"]["status"] == "ok"


@pytest.mark.parametrize("gst", [Decimal("1.05"), Decimal("1.12"), Decimal("1.18")])
def test_a_line_with_gst_folded_in_adds_up(gst: Decimal):
    """Pharmacy bills often print the amount with GST on top of quantity x rate."""
    amount = float((Decimal("6") * Decimal("58.50") * gst).quantize(Decimal("0.01")))
    rows = [("Inj. Pantoprazole 40mg", 6, 58.50, amount, None)]
    result = check_bill(bill(rows, subtotal=amount, discount=None, total=amount, paid=None, deposits=[]))

    assert result.flags == []


def test_a_line_without_a_rate_is_not_counted_as_checked():
    rows = [*FINAL_BILL[:8], ("Surgeon Charges", None, None, 13000, 10508)]
    result = check_bill(bill(rows))

    assert by_kind(result)["lines"] == {"kind": "lines", "status": "ok", "checked": 8, "of": 9}


# --- the totals --------------------------------------------------------------


def test_a_sub_total_above_its_lines_is_a_question():
    """Including the commonest cause: a line the photo didn't show, which is
    why the flag says to check the paper first."""
    result = check_bill(bill(subtotal=44300, total=36000, paid=36000))

    (flag,) = [f for f in result.flags if f.kind == "total_mismatch"]
    assert flag.reference_detail == {"summed": "43300.00", "stated": "44300.00", "difference": "1000.00"}
    assert by_kind(result)["subtotal"]["status"] == "mismatch"


def test_a_sub_total_within_a_rupee_a_line_is_rounding():
    result = check_bill(bill(subtotal=43305, total=35005, paid=35005))

    assert by_kind(result)["subtotal"]["status"] == "ok"
    assert not [f for f in result.flags if f.kind == "total_mismatch"]


def test_a_total_above_the_sub_total_less_the_discount_is_a_question():
    result = check_bill(bill(total=35500, paid=35500))

    (flag,) = [f for f in result.flags if f.kind == "total_mismatch"]
    assert flag.reference_detail["summed"] == "35000.00"
    assert flag.reference_detail["stated"] == "35500.00"
    assert flag.reference_detail["discount"] == "8300.00"
    assert by_kind(result)["payable"]["status"] == "mismatch"


def test_a_total_below_its_lines_passes_and_claims_nothing():
    result = check_bill(
        bill(subtotal=43000, total=34700, paid=34700, deposits=[("06/05/2025", "Cash", 34700)])
    )

    assert result.flags == []


def test_a_bill_with_no_discount_checks_its_lines_against_the_total():
    rows = [("Room rent", 2, 1000, 2000, None), ("Consultation", 1, 800, 800, None)]
    result = check_bill(bill(rows, subtotal=None, discount=None, total=3800, paid=None, deposits=[]))

    (flag,) = result.flags
    assert flag.kind == "total_mismatch"
    assert flag.excess == Decimal("1000.00")
    assert "discount" not in by_kind(result)


# --- what was paid -----------------------------------------------------------


def test_deposits_the_bill_does_not_credit_are_a_question():
    """Three deposits come to 35,000; the bill credits 30,000."""
    result = check_bill(bill(paid=30000, balance=5000))

    flags = [f for f in result.flags if f.kind == "advance_not_deducted"]
    assert flags[0].reference_detail == {"deposits": "35000.00", "credited": "30000.00", "count": "3"}
    assert by_kind(result)["paid"]["status"] == "mismatch"


def test_a_balance_that_does_not_take_off_what_was_paid_is_a_question():
    result = check_bill(bill(balance=5000))

    (flag,) = [f for f in result.flags if f.kind == "advance_not_deducted"]
    assert flag.reference_detail == {"due": "5000.00", "expected_due": "0.00", "paid": "35000.00"}
    assert result.balance == Decimal("5000.00"), "what the bill asks for, shown as it is"


def test_a_bill_with_no_deposits_says_nothing_about_them():
    result = check_bill(bill(paid=None, balance=None, deposits=[]))

    assert "paid" not in by_kind(result)
    assert "balance" not in by_kind(result)
    assert result.paid is None and result.balance is None


def test_paid_falls_back_to_what_the_deposits_add_up_to():
    result = check_bill(bill(paid=None, balance=None))

    assert result.paid == Decimal("35000.00")
    assert result.balance == Decimal("0.00")


# --- end to end --------------------------------------------------------------


def test_a_checked_bill_reaches_the_app(
    client: TestClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
):
    import ocr
    from tests.test_cases_and_bills import page

    monkeypatch.setattr(ocr.StubOcr, "read_bill", lambda self, pages: bill())
    response = client.post("/bills", files=[page()], headers=auth_headers)

    assert response.status_code == 201, response.text
    body = response.json()
    assert [c["kind"] for c in body["checks"]] == [
        "lines",
        "subtotal",
        "discount",
        "payable",
        "rounding",
        "paid",
        "balance",
    ]
    assert body["paid"] == 35000 and body["balance"] == 0
    assert [p["mode"] for p in body["payments"]] == ["Cash", "Cash", "UPI"]
    assert body["payments"][0] == {"date": "04/05/2025", "mode": "Cash", "amount": 5000.0}


def test_a_line_that_does_not_add_up_reaches_the_app_as_a_question(
    client: TestClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
):
    import ocr
    from tests.test_cases_and_bills import page

    rows = [*FINAL_BILL[:3], ("NURSING CHARGES", 3, 500, 1800, None), *FINAL_BILL[4:]]
    analysis = bill(rows, subtotal=43600, discount=None, total=43600, paid=None, deposits=[])
    monkeypatch.setattr(ocr.StubOcr, "read_bill", lambda self, pages: analysis)
    body = client.post("/bills", files=[page()], headers=auth_headers).json()

    (flag,) = [f for f in body["flags"] if f["kind"] == "line_math"]
    nursing = next(item for item in body["line_items"] if item["name"] == "NURSING CHARGES")
    assert flag["line_item_id"] == nursing["id"], "on the line it is about"
    assert flag["reference_source"] == "bill"
