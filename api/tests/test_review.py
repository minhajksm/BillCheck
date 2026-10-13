"""What the reader's observations are worth.

The reader says what it noticed; this decides what a family is shown. The point
of every test here is the same: a claim that the rows don't bear out must not
reach the family, because a charge that was correct, questioned at a counter,
costs them more than a charge we missed.
"""

from datetime import date
from decimal import Decimal

import pytest

from audit import Flag
from ocr import ExtractedBill, ExtractedRow, Observation
from review import review

ADMITTED = date(2026, 10, 9)


def row(name: str, detail: str | None, amount: float) -> ExtractedRow:
    return ExtractedRow(name=name, detail=detail, quantity=None, amount=amount)


ROWS = [
    row("Room rent, twin sharing", "1 day", 6500),
    row("Consultant visit, Dr. A. Mehta", "11 Oct, 10:30 am", 2500),
    row("Consultant visit, Dr. A. Mehta", "11 Oct, 10:30 am", 2500),
    row("Attendant meals", "3 meals", 450),
]


def bill(observations: list[Observation], stated_total: float | None = 11950.0) -> ExtractedBill:
    return ExtractedBill(
        bill_date="2026-10-11",
        stated_total=stated_total,
        rows=list(ROWS),
        observations=observations,
    )


def observe(kind: str, rows: list[int], **kwargs) -> Observation:
    return Observation(kind=kind, row_positions=rows, **kwargs)


# --- claims the rows can check ----------------------------------------------


def test_keeps_a_duplicate_the_rows_bear_out():
    flags = review(bill([observe("duplicate_line", [2, 3])]), [], ADMITTED)

    (flag,) = flags
    assert flag.kind == "duplicate_line"
    assert flag.level == "amber", "read off a photograph, so still a question"
    assert flag.billed == Decimal("2500")
    assert flag.excess == Decimal("2500"), "the repeat is what a correction gives back"
    assert flag.reference_source == "reader"


def test_drops_a_duplicate_the_rows_contradict():
    """The reader called two different rows the same charge. The rows say
    otherwise, so the family is told nothing."""
    flags = review(bill([observe("duplicate_line", [1, 2])]), [], ADMITTED)
    assert flags == []


def test_keeps_a_total_that_really_does_not_add_up():
    flags = review(bill([observe("total_mismatch", [])], stated_total=13000.0), [], ADMITTED)

    (flag,) = flags
    assert flag.kind == "total_mismatch"
    assert flag.reference_detail["summed"] == "11950"
    assert flag.reference_detail["stated"] == "13000"
    assert flag.excess == Decimal("1050")


def test_drops_a_total_that_does_add_up():
    """The commonest false alarm: the reader miscounts, the rows are fine."""
    flags = review(bill([observe("total_mismatch", [])], stated_total=11950.0), [], ADMITTED)
    assert flags == []


def test_tolerates_rounding_in_the_total():
    """A rupee either way is rounding on the bill, not a billing error."""
    flags = review(bill([observe("total_mismatch", [])], stated_total=11950.75), [], ADMITTED)
    assert flags == []


def test_drops_a_total_claim_when_the_bill_prints_no_total():
    flags = review(bill([observe("total_mismatch", [])], stated_total=None), [], ADMITTED)
    assert flags == []


def test_keeps_a_date_outside_the_stay():
    flags = review(bill([observe("date_outside_stay", [2])]), [], date(2026, 10, 20), date(2026, 10, 25))
    (flag,) = flags
    assert flag.kind == "date_outside_stay"
    assert flag.reference_detail["row_date"] == "2026-10-11"


def test_drops_a_date_inside_the_stay():
    flags = review(bill([observe("date_outside_stay", [2])]), [], ADMITTED, date(2026, 10, 15))
    assert flags == []


def test_drops_a_date_claim_about_a_row_with_no_date():
    flags = review(bill([observe("date_outside_stay", [1])]), [], ADMITTED)
    assert flags == []


# --- claims nothing can check ------------------------------------------------


def test_keeps_a_judgment_as_a_question():
    flags = review(bill([observe("non_medical_item", [4])]), [], ADMITTED)

    (flag,) = flags
    assert flag.kind == "non_medical_item"
    assert flag.level == "amber"
    assert flag.billed == Decimal("450")
    assert flag.excess == Decimal("450")


def test_a_judgment_of_degree_claims_no_amount():
    """ "This looks dear" has no defensible figure behind it. Putting one on
    screen would dress the reader's guess up as an amount."""
    flags = review(
        bill([observe("unit_price_high", [1], unit_price="6500", expected="3000")]),
        [],
        ADMITTED,
    )
    (flag,) = flags
    assert flag.excess == Decimal("0")
    assert flag.billed == Decimal("6500")
    # The reader's own figures are kept for the app to show as an expectation.
    assert flag.reference_detail["expected"] == "3000"


def test_drops_what_the_reader_was_unsure_of():
    flags = review(bill([observe("non_medical_item", [4], confidence="low")]), [], ADMITTED)
    assert flags == []


@pytest.mark.parametrize("confidence", ["medium", "high"])
def test_keeps_what_the_reader_was_sure_of(confidence: str):
    flags = review(bill([observe("non_medical_item", [4], confidence=confidence)]), [], ADMITTED)
    assert len(flags) == 1


# --- not stepping on the cited flags ----------------------------------------


def reference_flag(kind: str, position: int) -> Flag:
    return Flag(
        kind=kind,  # type: ignore[arg-type]
        level="red",
        row_position=position,
        billed=Decimal("17700"),
        reference_amount=Decimal("11040"),
        reference_source="mrp",
        excess=Decimal("6660"),
        reference_detail={},
    )


def test_a_cited_flag_wins_over_the_same_claim():
    """Asked once. The price list can show the family where its number came
    from; the reader can't."""
    flags = review(bill([observe("unit_price_high", [1])]), [reference_flag("above_mrp", 1)], ADMITTED)
    assert [flag.reference_source for flag in flags] == ["mrp"]


def test_the_reader_still_speaks_about_other_rows():
    flags = review(bill([observe("unit_price_high", [4])]), [reference_flag("above_mrp", 1)], ADMITTED)
    assert [flag.reference_source for flag in flags] == ["mrp", "reader"]


def test_red_comes_before_amber():
    flags = review(
        bill([observe("non_medical_item", [4]), observe("duplicate_line", [2, 3])]),
        [reference_flag("above_mrp", 1)],
        ADMITTED,
    )
    assert [flag.level for flag in flags] == ["red", "amber", "amber"]


# --- a reader that loses the thread -----------------------------------------


def test_drops_a_claim_about_a_row_that_is_not_there():
    """Row 9 of a 4-row bill means the reader lost its own numbering, which is
    reason enough to show the family nothing about it."""
    flags = review(bill([observe("non_medical_item", [9])]), [], ADMITTED)
    assert flags == []


def test_drops_the_out_of_range_half_of_a_claim():
    flags = review(bill([observe("duplicate_line", [2, 99])]), [], ADMITTED)
    assert flags == []


def test_no_observations_means_no_reader_flags():
    assert review(bill([]), [], ADMITTED) == []


def test_a_reader_that_says_nothing_leaves_the_cited_flags_alone():
    cited = [reference_flag("above_mrp", 1)]
    assert review(bill([]), cited, ADMITTED) == cited
