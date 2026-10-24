"""A bill that discounts.

Indian hospital bills routinely print two money columns -- a gross "Amount"
and a "Net Amount" after a discount applied across the bill -- and three
totals under them: sub-total, discount, payable. We kept the sum of the gross
lines and called it the total, so a family handed a final bill for Rs 35,000
opened the report and read Rs 43,300.

The number a family already has in their head is what they paid. That is the
one the report leads with now, with the bill's own ledger under it.
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from analysis import AnalysedLine, BillAnalysis
from bills import bill_discount
from tests.test_cases_and_bills import JPEG, page

# Gross, net: three lines of the bill this was found on.
ROWS = [
    ("Complete Blood Count-CBC", 300.0, 242.0),
    ("ROOM CHARGES", 3900.0, 3152.0),
    ("Surgeon Charges", 13000.0, 10508.0),
]
SUBTOTAL = 17200
DISCOUNT = 3200
PAYABLE = 14000


def discounted(analysis: BillAnalysis, discount: float | None = float(DISCOUNT)) -> BillAnalysis:
    """The stub's bill, re-read as a bill with two money columns."""
    lines = [
        AnalysedLine(
            line_id=f"L{number}",
            description_verbatim=name,
            category="unclassified",
            quantity=1,
            unit="",
            rate=gross,
            amount=gross,
            net_amount=net,
            date="",
            mrp_printed=None,
        )
        for number, (name, gross, net) in enumerate(ROWS, start=1)
    ]
    return analysis.model_copy(
        update={
            "lines": lines,
            "bill": analysis.bill.model_copy(update={"discount": discount, "total": float(PAYABLE)}),
            "findings": [],
            "requires_reference_price": [],
        }
    )


@pytest.fixture
def read_as_discounted(monkeypatch: pytest.MonkeyPatch):
    """Makes the next upload read as the discounted bill above."""
    import ocr

    plain = ocr.StubOcr.read_bill

    def read(self, pages):
        return discounted(plain(self, pages))

    monkeypatch.setattr(ocr.StubOcr, "read_bill", read)


def upload(client: TestClient, headers: dict) -> dict:
    response = client.post("/bills", files=[page()], headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_the_total_is_what_the_hospital_asks_for(client: TestClient, auth_headers: dict, read_as_discounted):
    bill = upload(client, auth_headers)

    assert bill["total"] == PAYABLE, "the figure on the bill, and the one they paid"
    assert bill["subtotal"] == SUBTOTAL, "what the lines come to, before the discount"
    assert bill["discount"] == DISCOUNT


def test_a_line_keeps_both_figures(client: TestClient, auth_headers: dict, read_as_discounted):
    """Gross on the row, because that is what a family reads down beside their
    own copy, and what a rate checked against a price list is quoted at."""
    bill = upload(client, auth_headers)

    assert [item["amount"] for item in bill["line_items"]] == [gross for _, gross, _ in ROWS]
    assert [item["net_amount"] for item in bill["line_items"]] == [net for _, _, net in ROWS]


def test_the_case_counts_what_is_owed_not_the_gross(
    client: TestClient, auth_headers: dict, read_as_discounted
):
    """The running total on the case is a family's own running total."""
    bill = upload(client, auth_headers)
    case = client.get(f"/cases/{bill['case_id']}", headers=auth_headers).json()

    assert [daily["total"] for daily in case["bills"]] == [PAYABLE]


def test_a_bill_that_does_not_discount_reads_as_it_always_did(client: TestClient, auth_headers: dict):
    bill = upload(client, auth_headers)

    assert bill["discount"] is None
    assert bill["subtotal"] == bill["total"] == 42490
    assert all(item["net_amount"] is None for item in bill["line_items"])


def test_a_bill_read_before_this_still_reads(client: TestClient, auth_headers: dict, read_as_discounted):
    """An answer from a reader that never heard of these keys: both absent
    rather than null. A whole bill is not worth failing over a figure that is
    not on the page."""
    import json

    from ocr import _parse

    raw = json.loads(discounted(_stub(), discount=None).model_dump_json())
    raw["bill"].pop("discount")
    for line in raw["lines"]:
        line.pop("net_amount")

    analysis = _parse(json.dumps(raw))
    assert analysis.bill.discount is None
    assert [line.net_amount for line in analysis.lines] == [None, None, None]


def _stub() -> BillAnalysis:
    from ocr import BillPage, StubOcr

    return StubOcr().read_bill([BillPage(data=JPEG, content_type="image/jpeg")])


@pytest.mark.parametrize(
    ("discount", "kept"),
    [
        (None, None),
        (3200.0, Decimal("3200.0")),
        (float(SUBTOTAL), Decimal(SUBTOTAL)),
        # A discount is a figure off the bill. Outside that it is a misreading
        # -- the sub-total in the wrong field, a sign lost -- and taking it
        # would print a family a total larger than their bill, or a negative one.
        (0.0, None),
        (-500.0, None),
        (float(SUBTOTAL) + 1, None),
    ],
)
def test_only_a_discount_that_could_be_one_is_taken(discount: float | None, kept: Decimal | None):
    assert bill_discount(discounted(_stub(), discount), Decimal(SUBTOTAL)) == kept
