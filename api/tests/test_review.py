"""What the reader's findings are worth once they reach a family.

The reader states what the bill proves and writes its own sentence, so this
module no longer second-guesses the claim itself: there is no list of kinds to
re-check against. What it still decides is what reaches the screen, and the
tests here are about the parts that can still go wrong -- a finding naming
lines that aren't there, a price-list flag and a finding about the same line,
and the stay check, which the reader cannot make because it is never told when
the admission was.
"""

from datetime import date
from decimal import Decimal

import pytest

from analysis import AnalysedLine, BillAnalysis, BillHeader, Finding, Structural
from audit import Flag
from flag_kinds import CitedFlagKind
from review import flags_from_findings

ADMITTED = date(2026, 10, 9)


# The schema requires every field, so these helpers fill in the blanks a test
# doesn't care about. Keeping that here rather than in the model is the point:
# the reader has to send them, and nothing downstream may quietly default them.
def line(
    line_id: str,
    name: str,
    amount: float,
    *,
    on: str = "",
    quantity: float | None = None,
    unit: str = "",
) -> AnalysedLine:
    return AnalysedLine(
        line_id=line_id,
        page=1,
        section="",
        description_verbatim=name,
        item_name_plain=name,
        category="unclassified",
        attributes={},
        quantity=quantity,
        unit=unit,
        rate=None,
        amount=amount,
        date=on,
        mrp_printed=None,
        confidence=0.9,
        ambiguous=False,
        ambiguity_reason="",
    )


def finding(
    rule: str,
    line_ids: list[str],
    *,
    severity: str = "medium",
    statement: str = "The bill charges for this twice.",
    evidence: str = "Consultant visit, Dr. A. Mehta — 2,500 — twice",
    confirm: str = "The case sheet.",
) -> Finding:
    return Finding(
        finding_id="f1",
        rule=rule,
        severity=severity,  # type: ignore[arg-type]
        line_ids=line_ids,
        evidence_quoted=evidence,
        statement=statement,
        confirmation_required=confirm,
    )


LINES = [
    line("L1", "Room rent, twin sharing", 6500, quantity=1, unit="day"),
    line("L2", "Consultant visit, Dr. A. Mehta", 2500, on="11 Oct, 10:30 am"),
    line("L3", "Consultant visit, Dr. A. Mehta", 2500, on="11 Oct, 10:30 am"),
    line("L4", "Attendant meals", 450, quantity=3, unit="meals"),
]


def analysis(
    findings: list[Finding],
    *,
    lines: list[AnalysedLine] | None = None,
    bill_date: str = "2026-10-11",
    needs_human_review: bool = False,
    review_reasons: list[str] | None = None,
) -> BillAnalysis:
    rows = LINES if lines is None else lines
    return BillAnalysis(
        bill=BillHeader(
            hospital="City Care Hospital",
            bill_no="",
            bill_date=bill_date,
            admission_date="",
            discharge_date="",
            stay_days=None,
            room_category="",
            total=float(sum(row.amount or 0 for row in rows)),
            patient_name="Ramesh Sharma",
            ip_number="IP/4417",
            pages_processed=1,
            extraction_confidence=0.9,
        ),
        lines=list(rows),
        findings=findings,
        requires_reference_price=[],
        structural=Structural(consumable_share_pct=0.0, unitemised_share_pct=0.0, unreadable_line_count=0),
        needs_human_review=needs_human_review,
        review_reasons=review_reasons or [],
    )


# --- a finding becomes a flag ------------------------------------------------


def test_a_finding_reaches_the_family_as_one_flag():
    flags = flags_from_findings(analysis([finding("C. identical item billed twice", ["L2", "L3"])]), [])

    (flag,) = flags
    assert flag.kind == "analysis_finding", "the finding carries its own rule, so there is one kind"
    assert flag.row_position == 2, "the first line it names"
    assert flag.billed == Decimal("2500")
    assert flag.reference_source == "reader"


def test_the_reader_s_own_sentence_is_what_the_app_shows():
    """The one line on screen we don't write. It rides in reference_detail as
    `why_en`, which is the field the app prefers over its own wording."""
    flags = flags_from_findings(
        analysis(
            [
                finding(
                    "C. identical item billed twice",
                    ["L2", "L3"],
                    statement="Two consultant visits by the same doctor are billed for 11 Oct.",
                    evidence="Consultant visit, Dr. A. Mehta — 2,500 — twice",
                    confirm="The case sheet showing two separate visits.",
                )
            ]
        ),
        [],
    )

    detail = flags[0].reference_detail
    assert detail["why_en"] == "Two consultant visits by the same doctor are billed for 11 Oct."
    assert detail["rule"] == "C. identical item billed twice"
    assert detail["evidence"] == "Consultant visit, Dr. A. Mehta — 2,500 — twice"
    assert detail["confirm"] == "The case sheet showing two separate visits."
    assert detail["lines"] == "L2,L3", "every line it named, not just the one it hangs on"


def test_a_finding_never_claims_an_amount_back():
    """The prompt forbids pricing anything, so a finding has no figure behind
    it. Putting one on screen would dress the reader's reading up as money the
    family is owed; that is the price lists' job."""
    flags = flags_from_findings(analysis([finding("B. rate above printed MRP", ["L1"])]), [])
    assert flags[0].excess == Decimal("0")


@pytest.mark.parametrize(
    "severity,level",
    [("high", "red"), ("medium", "amber"), ("low", "amber")],
)
def test_only_what_the_bill_proves_is_red(severity: str, level: str):
    """The prompt reserves "high" for a finding the page itself settles. Those
    are as hard as a price-list flag; the rest are questions."""
    flags = flags_from_findings(analysis([finding("A. check", ["L1"], severity=severity)]), [])
    assert flags[0].level == level


def test_a_bill_level_finding_may_name_no_line():
    """Checks about the bill as a whole -- a total that doesn't add up, an
    advance not deducted -- are about no one line."""
    flags = flags_from_findings(analysis([finding("A. total does not add up", [])]), [])
    assert [flag.kind for flag in flags] == ["analysis_finding"]
    assert flags[0].row_position == 0
    assert flags[0].billed == Decimal("0"), "no line to take an amount from"


def test_no_findings_means_no_reader_flags():
    assert flags_from_findings(analysis([]), []) == []


# --- a reader that loses the thread -----------------------------------------


def test_drops_a_finding_about_a_line_that_is_not_there():
    """L9 of a four-line bill means the reader lost its own numbering, which is
    reason enough to show the family nothing about it."""
    assert flags_from_findings(analysis([finding("A. check", ["L9"])]), []) == []


def test_keeps_the_half_of_a_finding_that_is_there():
    """Unlike the duplicate check it replaces, a finding is one statement about
    whatever lines it names: half the ids landing is still a line to show."""
    flags = flags_from_findings(analysis([finding("C. billed twice", ["L2", "L99"])]), [])
    assert [flag.row_position for flag in flags] == [2]


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


def test_a_reader_that_says_nothing_leaves_the_cited_flags_alone():
    cited = [reference_flag("above_mrp", 1)]
    assert flags_from_findings(analysis([]), cited) == cited


def test_red_comes_before_amber():
    flags = flags_from_findings(
        analysis(
            [
                finding("G. non-medical item", ["L4"], severity="low"),
                finding("C. billed twice", ["L2", "L3"]),
            ]
        ),
        [reference_flag("above_mrp", 1)],
    )
    assert [flag.level for flag in flags] == ["red", "amber", "amber"]
    assert [flag.row_position for flag in flags] == [1, 2, 4], "then the bill's own order"


# --- severity, and the switch that keeps everything --------------------------


def test_keeping_everything_is_the_default():
    """REVIEW_KEEP_ALL on: nothing the reader said is withheld, so a bill can
    be read in full while the prompt is being worked on."""
    kept = flags_from_findings(analysis([finding("A. check", ["L1"], severity="low")]), [])
    assert len(kept) == 1


def test_the_switch_off_drops_what_the_reader_itself_called_low():
    dropped = flags_from_findings(analysis([finding("A. check", ["L1"], severity="low")]), [], keep_all=False)
    assert dropped == []


def test_the_switch_off_keeps_the_rest():
    for severity in ("high", "medium"):
        flags = flags_from_findings(
            analysis([finding("A. check", ["L1"], severity=severity)]), [], keep_all=False
        )
        assert len(flags) == 1, severity


def test_a_reader_asking_for_a_human_still_hands_its_findings_over(caplog):
    """`needs_human_review` is for whoever is running this, not a reason to
    show the family nothing: the findings are what they came for."""
    with caplog.at_level("WARNING"):
        flags = flags_from_findings(
            analysis(
                [finding("A. check", ["L1"])],
                needs_human_review=True,
                review_reasons=["page 2 is cut off"],
            ),
            [],
        )
    assert len(flags) == 1
    assert "page 2 is cut off" in caplog.text


# --- the stay check, which the reader cannot make ---------------------------
#
# The reader is given the bill and nothing else, so it is never told when the
# admission was. This runs over every line of every bill, which makes the lines
# that must *not* be flagged the more important half.


def dated(details: list[str], bill_date: str = "2026-10-11") -> BillAnalysis:
    return analysis(
        [],
        lines=[line(f"L{n}", "Pathology Services", 430, on=on) for n, on in enumerate(details, start=1)],
        bill_date=bill_date,
    )


def test_flags_a_line_dated_before_the_admission():
    flags = flags_from_findings(dated(["2/10/2026, 9:00 am"]), [], ADMITTED)

    (flag,) = flags
    assert flag.kind == "date_outside_stay"
    assert flag.level == "amber", "read off a photograph, so still a question"
    assert flag.reference_detail["row_date"] == "2026-10-02"
    assert flag.reference_detail["admitted_on"] == "2026-10-09"
    assert flag.excess == Decimal("430"), "if the charge isn't ours, the line comes off"


def test_flags_a_line_dated_after_discharge():
    flags = flags_from_findings(dated(["20 Oct, 9:00 am"]), [], ADMITTED, date(2026, 10, 15))
    assert [flag.reference_detail["row_date"] for flag in flags] == ["2026-10-20"]
    assert flags[0].reference_detail["closed_on"] == "2026-10-15"


def test_leaves_lines_inside_the_stay_alone():
    flags = flags_from_findings(
        dated(["11 Oct, 10:30 am", "9 Oct, 8:00 am", "15/10/2026"]), [], ADMITTED, date(2026, 10, 15)
    )
    assert flags == [], "the admission and discharge days are inside the stay"


def test_reads_an_undated_line_in_the_bill_s_own_year():
    """The bug this check was written for: "11 Oct" with no year, on a bill
    from years ago. Dating it in the current year would flag every line."""
    old = dated(["22 Oct, 10:20 am", "23 Oct, 1:30 pm"], bill_date="2018-10-23")
    assert flags_from_findings(old, [], date(2018, 10, 22), date(2018, 10, 23)) == []


def test_an_open_stay_has_no_upper_bound():
    """Mid-admission, there is no discharge date yet, so nothing is "after"."""
    assert flags_from_findings(dated(["20 Oct, 9:00 am"]), [], ADMITTED) == []


def test_a_line_with_no_date_is_not_a_date_outside_the_stay():
    """Most lines carry a quantity where this one carries a date, and the
    analysis keeps those apart, so there is nothing to misread."""
    assert flags_from_findings(analysis([]), [], ADMITTED) == []


def test_no_admission_date_turns_the_check_off():
    """What `scripts/read_bill.py` does when it is handed pages and no case."""
    assert flags_from_findings(dated(["2/10/2026, 9:00 am"]), []) == []


def test_the_stay_check_runs_beside_the_reader_s_own_findings():
    bill = dated(["11 Oct, 10:30 am", "2/10/2026, 9:00 am"])
    bill.findings = [finding("G. non-medical item", ["L1"])]

    flags = flags_from_findings(bill, [], ADMITTED)
    assert {flag.kind for flag in flags} == {"analysis_finding", "date_outside_stay"}
    assert [flag.row_position for flag in flags] == [1, 2]
