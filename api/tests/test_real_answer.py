"""A real answer from a real bill, kept because it broke the parser.

`tests/data/pune_polyclinic_answer.json` is what the reader sent back for a
one-night admission at a Pune polyclinic, and the parser rejected all of it
with 26 validation errors. The JSON was fine. The model was stricter than the
prompt: it would not take the nulls ABSOLUTE CONSTRAINT 3 asks for, nor a
quantity transcribed verbatim as PHASE 1 asks for.

Names and the address are replaced; the shape, the nulls and the figures are
the reader's own. A bill the reader can read and this cannot is the failure
that costs a family the most, because nothing on the screen says why.
"""

import json
from pathlib import Path

import pytest

from ocr import _parse

ANSWER = Path(__file__).parent / "data" / "pune_polyclinic_answer.json"


@pytest.fixture(scope="module")
def analysis():
    return _parse(ANSWER.read_text(encoding="utf-8"))


def test_the_answer_that_broke_the_parser_now_parses(analysis):
    assert len(analysis.lines) == 15
    assert len(analysis.findings) == 3


def test_a_null_the_prompt_asks_for_is_not_a_failure(analysis):
    """ABSOLUTE CONSTRAINT 3: "If a field is unreadable, output null". Every
    one of the 15 lines sent `"unit": null`, and seven sent no ambiguity
    reason. That was 22 of the 26 errors."""
    assert all(line.unit == "" for line in analysis.lines)
    assert analysis.lines[2].ambiguity_reason == ""
    assert analysis.lines[6].date == "", "the bill printed '---' here"


def test_a_quantity_is_read_as_the_bill_prints_it(analysis):
    """PHASE 1: transcribe verbatim. This hospital bills part-days as
    fractions, so a bed is "1 1/4" and not a number `float()` will take."""
    private_room, icu = analysis.lines[0], analysis.lines[1]
    assert private_room.quantity == 1.25
    assert icu.quantity == 0.25
    assert private_room.rate == 1000.0, "the rate is a plain figure and stays one"


def test_a_stay_of_part_days_is_not_a_whole_number(analysis):
    """31 hours 45 minutes. The reader answered 1.32 and was right to."""
    assert analysis.bill.stay_days == 1.32


def test_attributes_arrive_with_the_keys_the_bill_used(analysis):
    """Not one of PHASE 2's eight: this bill states a room, so the reader
    sent a room. An open map is the only way that survives."""
    assert analysis.lines[0].attributes == {"room": "PRI001"}
    assert analysis.lines[2].attributes == {"doctor": "Dr. A. Example"}


def test_fields_the_reader_added_are_ignored_not_fatal(analysis):
    """It also sent `printed_summary`, `printed_totals`, `payment`,
    `consulting_doctors` and a `stay_days_note` on the header. None is in the
    format, so none is read -- but inventing extra detail is not a reason to
    throw away the bill."""
    raw = json.loads(ANSWER.read_text(encoding="utf-8"))
    assert "printed_summary" in raw["bill"], "the fixture still has the extras"
    assert not hasattr(analysis.bill, "printed_summary")
    assert analysis.bill.total == 5150.0


def test_the_lines_add_up_to_the_printed_total(analysis):
    """The arithmetic the reader checked, checked again here: if the figures
    came through wrong, this is where it shows."""
    assert sum(line.amount or 0 for line in analysis.lines) == analysis.bill.total


def test_a_bill_the_reader_wants_looked_at_is_still_shown(analysis):
    """`needs_human_review` was true -- a poorly legible last digit, and an
    unprintable billing unit. The bill was read all the same, and the lines
    are what a family came for."""
    assert analysis.needs_human_review
    assert len(analysis.review_reasons) == 2
    assert analysis.unreadable() == ""


def test_the_findings_keep_their_severities(analysis):
    """F4 is high, the catch-all medicines line the bill cannot support; the
    others are questions. These are what decide red against amber."""
    assert [finding.severity for finding in analysis.findings] == ["medium", "high", "low"]
    assert analysis.findings[2].line_ids == [], "a whole-bill finding names no line"


def test_the_whole_bill_reaches_a_family(analysis):
    """What this is all for. Every line the reader transcribed becomes a line
    on the report, grouped by what kind of charge it is."""
    from collections import Counter

    groups = Counter(line.category for line in analysis.lines)
    assert groups == {
        "professional_fees": 4,
        "procedure_or_ot": 3,
        "non_medical": 3,
        "room_and_nursing": 3,
        "pharmacy_drug": 1,
        "investigation": 1,
    }
    assert sum(groups.values()) == 15
