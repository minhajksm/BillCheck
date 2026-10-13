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
from flag_kinds import CitedFlagKind
from ocr import ExtractedBill, ExtractedRow, Observation
from review import review

ADMITTED = date(2026, 10, 9)


# The schema requires every field, so these helpers fill in the blanks a test
# doesn't care about. Keeping that here rather than in the model is the point:
# the reader has to send them, and nothing downstream may quietly default them.
def row(name: str, detail: str | None, amount: float) -> ExtractedRow:
    return ExtractedRow(name=name, detail=detail or "", quantity=None, amount=amount)


def observation(kind: str, rows: list[int], **given) -> Observation:
    blank = {
        "unit_price": "",
        "expected": "",
        "quantity": "",
        "usual": "",
        "stated": "",
        "summed": "",
        "confidence": "medium",
        "note": "",
        "why_en": "",
        "why_hi": "",
        "why_mr": "",
    }
    return Observation(kind=kind, row_positions=rows, **{**blank, **given})


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
    return observation(kind, rows, **kwargs)


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

    # Rows 2 and 3 carry the same out-of-stay date. The reader raised only row
    # 2; the stay check finds row 3 as well, which is the whole point of it.
    assert [flag.kind for flag in flags] == ["date_outside_stay", "date_outside_stay"]
    assert [flag.row_position for flag in flags] == [2, 3]
    assert {flag.reference_detail["row_date"] for flag in flags} == {"2026-10-11"}


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


def reference_flag(kind: CitedFlagKind, position: int) -> Flag:
    return Flag(
        kind=kind,
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


# --- the stay check, which nobody has to propose ----------------------------
#
# The reader is never told when the admission was, so it cannot raise this.
# These run over every row of every bill, which makes the rows that must *not*
# be flagged the more important half.


def dated(detail: str | None, name: str = "Pathology Services") -> ExtractedRow:
    return ExtractedRow(name=name, detail=detail or "", quantity=None, amount=430.0)


def dated_bill(details: list[str | None], bill_date: str | None = "2026-10-11") -> ExtractedBill:
    return ExtractedBill(
        bill_date=bill_date,
        stated_total=None,
        rows=[dated(detail) for detail in details],
        observations=[],
    )


def test_flags_a_row_dated_before_the_admission():
    flags = review(dated_bill(["2/10/2026, 9:00 am"]), [], ADMITTED)

    (flag,) = flags
    assert flag.kind == "date_outside_stay"
    assert flag.level == "amber", "read off a photograph, so still a question"
    assert flag.reference_detail["row_date"] == "2026-10-02"
    assert flag.reference_detail["admitted_on"] == "2026-10-09"
    assert flag.excess == Decimal("430"), "if the charge isn't ours, the line comes off"


def test_flags_a_row_dated_after_discharge():
    flags = review(dated_bill(["20 Oct, 9:00 am"]), [], ADMITTED, date(2026, 10, 15))
    assert [flag.reference_detail["row_date"] for flag in flags] == ["2026-10-20"]


def test_leaves_rows_inside_the_stay_alone():
    flags = review(
        dated_bill(["11 Oct, 10:30 am", "9 Oct, 8:00 am", "15/10/2026"]), [], ADMITTED, date(2026, 10, 15)
    )
    assert flags == [], "the admission and discharge days are inside the stay"


def test_reads_an_undated_row_in_the_bill_s_own_year():
    """The bug this check was written for: "11 Oct" with no year, on a bill
    from years ago. Dating it in the current year would flag every row."""
    old = dated_bill(["22 Oct, 10:20 am", "23 Oct, 1:30 pm"], bill_date="2018-10-23")
    assert review(old, [], date(2018, 10, 22), date(2018, 10, 23)) == []


def test_ignores_quantity_details_that_are_not_dates():
    quantities = ["1 day", "6 vials", "80 pairs", "1 set", "4 bottles", "3 meals", "---", None]
    assert review(dated_bill(quantities), [], ADMITTED) == []


def test_does_not_ask_twice_when_the_reader_raised_it_too():
    """The reader's own claim is confirmed by _confirm_date; the scan must not
    add a second flag for the same row."""
    bill = dated_bill(["2/10/2026, 9:00 am"])
    bill.observations = [observe("date_outside_stay", [1])]

    flags = review(bill, [], ADMITTED)
    assert len(flags) == 1


def test_scans_rows_the_reader_said_nothing_about():
    bill = dated_bill(["11 Oct, 10:30 am", "2/10/2026, 9:00 am"])
    bill.observations = [observe("non_medical_item", [1])]

    flags = review(bill, [], ADMITTED)
    assert {flag.kind for flag in flags} == {"non_medical_item", "date_outside_stay"}
    assert [flag.row_position for flag in flags] == [1, 2]


def test_an_open_stay_has_no_upper_bound():
    """Mid-admission, there is no discharge date yet, so nothing is "after"."""
    assert review(dated_bill(["20 Oct, 9:00 am"]), [], ADMITTED) == []


# --- the wider set of kinds --------------------------------------------------


@pytest.mark.parametrize("kind", ["rounded_amounts", "advance_not_deducted"])
def test_a_bill_level_claim_may_name_no_rows(kind: str):
    """These are about the bill, not a row, so citing none is not a reader that
    lost its numbering."""
    flags = review(bill([observe(kind, [])]), [], ADMITTED)
    assert [flag.kind for flag in flags] == [kind]
    assert flags[0].excess == Decimal("0"), "no figure we could defend"


@pytest.mark.parametrize("kind", ["tax_on_exempt_item", "icu_rate_on_ward_day"])
def test_a_row_level_claim_still_has_to_name_a_row(kind: str):
    assert review(bill([observe(kind, [])]), [], ADMITTED) == []


def test_the_whole_line_comes_off_a_tax_on_an_exempt_item():
    flags = review(bill([observe("tax_on_exempt_item", [4])]), [], ADMITTED)
    assert flags[0].excess == Decimal("450"), "if the tax shouldn't be there, it all comes off"


def test_a_drug_billed_twice_from_two_places_is_worth_the_repeat():
    flags = review(bill([observe("same_drug_twice_sources", [2, 3])]), [], ADMITTED)
    assert flags[0].excess == Decimal("2500")


@pytest.mark.parametrize(
    "kind", ["room_rate_vs_ward", "branded_drug_margin", "capped_item_above_ceiling", "visits_in_one_day"]
)
def test_the_new_judgments_of_degree_claim_no_amount(kind: str):
    """ "This looks dear" has no defensible figure behind it, whichever way the
    reader phrases it."""
    flags = review(bill([observe(kind, [1])]), [], ADMITTED)
    assert flags[0].excess == Decimal("0")
    assert flags[0].level == "amber"


def test_a_cited_price_flag_wins_over_the_reader_s_ceiling_claim():
    """Asked once. The price list can show the family the ceiling; the reader
    can only remember it."""
    flags = review(
        bill([observe("capped_item_above_ceiling", [1])]), [reference_flag("above_mrp", 1)], ADMITTED
    )
    assert [flag.reference_source for flag in flags] == ["mrp"]


# --- the sentence the reader writes for the family ---------------------------


def test_the_reader_s_own_words_reach_the_flag():
    """The one line on screen we don't write. It rides in reference_detail, per
    language, for the app to show in place of its own wording."""
    flags = review(
        bill(
            [
                observe(
                    "non_medical_item",
                    [4],
                    why_en="The bill lists meals for the attendant.",
                    why_hi="बिल में परिचारक के भोजन का शुल्क है।",
                    why_mr="बिलात सोबत्याच्या जेवणाचा समावेश आहे.",
                )
            ]
        ),
        [],
        ADMITTED,
    )

    (flag,) = flags
    assert flag.reference_detail["why_en"] == "The bill lists meals for the attendant."
    assert flag.reference_detail["why_hi"] == "बिल में परिचारक के भोजन का शुल्क है।"
    assert flag.reference_detail["why_mr"] == "बिलात सोबत्याच्या जेवणाचा समावेश आहे."


def test_a_reader_that_writes_nothing_leaves_the_app_its_own_wording():
    flags = review(bill([observe("non_medical_item", [4])]), [], ADMITTED)
    assert not any(key.startswith("why_") for key in flags[0].reference_detail)


def test_blank_explanations_are_not_carried_as_empty_strings():
    """An empty string would read as "the reader wrote nothing to say", and the
    app would show a blank line instead of falling back."""
    flags = review(bill([observe("non_medical_item", [4], why_en="  ", why_hi="")]), [], ADMITTED)
    assert not any(key.startswith("why_") for key in flags[0].reference_detail)


def test_a_dropped_claim_takes_its_words_with_it():
    """The explanation is only as good as the claim. One the rows contradict
    reaches nobody, sentence and all."""
    assert (
        review(bill([observe("duplicate_line", [1, 2], why_en="These two look the same.")]), [], ADMITTED)
        == []
    )


# --- keeping everything, for watching the reader ------------------------------
#
# REVIEW_KEEP_ALL is a development switch: it shows what the reader said on a
# bill, including the claims this module exists to withhold. Production refuses
# to start with it on, so these tests are about the switch, not the product.


def test_keeps_a_claim_the_rows_contradict():
    """Normally dropped: the reader called two different rows the same charge."""
    bill_ = bill([observe("duplicate_line", [1, 2])])

    assert review(bill_, [], ADMITTED) == []
    (kept,) = review(bill_, [], ADMITTED, keep_all=True)
    assert kept.kind == "duplicate_line"
    assert kept.reference_detail["unconfirmed"] == "true"


def test_keeps_what_the_reader_was_unsure_of():
    bill_ = bill([observe("nursing_billed_with_room", [1], confidence="low")])

    assert review(bill_, [], ADMITTED) == []
    (kept,) = review(bill_, [], ADMITTED, keep_all=True)
    assert kept.reference_detail["unconfirmed"] == "true"
    assert kept.reference_detail["confidence"] == "low"


def test_keeps_a_claim_a_price_list_already_covers():
    cited = [reference_flag("above_mrp", 1)]
    bill_ = bill([observe("unit_price_high", [1])])

    assert [f.reference_source for f in review(bill_, cited, ADMITTED)] == ["mrp"]
    kept = review(bill_, cited, ADMITTED, keep_all=True)
    assert [f.reference_source for f in kept] == ["mrp", "reader"]


def test_still_drops_a_claim_about_a_row_that_is_not_there():
    """The one thing keep_all cannot keep: there is no line to hang it on."""
    assert review(bill([observe("non_medical_item", [9])]), [], ADMITTED, keep_all=True) == []


def test_a_claim_that_stands_on_its_own_is_not_marked_unconfirmed():
    (flag,) = review(bill([observe("non_medical_item", [4])]), [], ADMITTED, keep_all=True)
    assert "unconfirmed" not in flag.reference_detail
