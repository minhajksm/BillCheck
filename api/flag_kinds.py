"""Every flag kind, and everything the code needs to know about each one.

This is the one place a kind is declared. Adding one used to mean editing the
reader's schema, the prompt, three sets in `review.py` and the API's response
model, and missing any of them failed somewhere else entirely: a kind absent
from the response model saved to the database fine and then broke serialising
the bill back out, with the type checker silenced on the field that would have
caught it.

So a kind is one entry in `READER_KINDS` below. The prompt's own list, the sets
`review.py` works from, and the Literals the schema and the API validate
against are all derived from it.

Two things still live outside this file, because they cannot be derived:

- The prompt's framing around the list, in `ocr.py`.
- The family-facing copy, in the app, which has to exist in three languages.
  `tests/test_flag_kinds.py` checks the app's list still matches this one.
"""

from dataclasses import dataclass
from typing import Literal, get_args

# Checked against a published price list, so the family can be shown where the
# number came from. These are the only kinds that are ever red.
CitedFlagKind = Literal["above_mrp", "duplicate", "quantity"]

# Noticed by the reader. None has a published reference behind it, so none is
# ever red; `reference_source` is "reader" for all of them.
ReaderFlagKind = Literal[
    # Contradictions on the page itself.
    "total_mismatch",
    "duplicate_line",
    "equipment_hours_exceed_stay",
    "date_outside_stay",
    "implant_without_identity",
    "rounded_amounts",
    "advance_not_deducted",
    # What an experienced eye notices.
    "unit_price_high",
    "branded_drug_margin",
    "capped_item_above_ceiling",
    "non_medical_item",
    "package_overlap",
    "nursing_billed_with_room",
    "service_charge_on_room",
    "quantity_high",
    "visits_in_one_day",
    "same_test_two_names",
    "same_drug_twice_sources",
    "room_rate_vs_ward",
    "icu_rate_on_ward_day",
    "tax_on_exempt_item",
]

FlagKind = CitedFlagKind | ReaderFlagKind

Group = Literal["contradiction", "judgment"]


@dataclass(frozen=True)
class KindSpec:
    """One kind: how it is described to the reader, and what it is worth."""

    description: str
    """The line the prompt gives the reader. One sentence, no trailing period
    rules — it is wrapped into the prompt as written."""

    group: Group
    """`contradiction` needs nothing but the bill. `judgment` rests on what the
    reader knows, which is why nothing can confirm it."""

    checkable: bool = False
    """`review.py` re-checks this against the rows and drops it if they
    disagree. Only add a kind here once there is a `_confirm_*` for it."""

    bill_level: bool = False
    """About the bill rather than a row, so citing no row is fine. For every
    other kind, no row means a reader that lost its own numbering."""

    whole_line: bool = False
    """A correction gives the whole line back, so the line's amount is the
    excess. For judgments of degree there is no defensible figure, and taking
    the reader's own estimate would dress a guess up as an amount."""

    covered_by: CitedFlagKind | None = None
    """A cited kind that says the same thing better. Where a price list has
    already flagged the row, that flag wins and this one is dropped, so the
    family is asked once."""


READER_KINDS: dict[ReaderFlagKind, KindSpec] = {
    # --- Contradictions on the page -----------------------------------------
    "total_mismatch": KindSpec(
        "the rows you transcribed don't add up to the printed total.",
        "contradiction",
        checkable=True,
        bill_level=True,
    ),
    "duplicate_line": KindSpec(
        "the same charge appears twice for the same moment.",
        "contradiction",
        checkable=True,
        whole_line=True,
        covered_by="duplicate",
    ),
    "equipment_hours_exceed_stay": KindSpec(
        'billed hours for a machine exceed the stay, e.g. "Ventilator, 120 hrs" on a three-day admission.',
        "contradiction",
    ),
    "date_outside_stay": KindSpec(
        "a row is dated before admission or after discharge.",
        "contradiction",
        checkable=True,
        whole_line=True,
    ),
    "implant_without_identity": KindSpec(
        "an implant or device billed with no brand, batch or manufacturer where the bill "
        "records those for other items.",
        "contradiction",
    ),
    "rounded_amounts": KindSpec(
        "the amounts are implausibly round across the bill, as if each line were rounded up "
        "rather than priced.",
        "contradiction",
        bill_level=True,
    ),
    "advance_not_deducted": KindSpec(
        "the bill itself shows a deposit or advance paid, and the amount due does not take it off.",
        "contradiction",
        bill_level=True,
    ),
    # --- What an experienced eye notices ------------------------------------
    "unit_price_high": KindSpec(
        "a consumable or drug priced well above what it usually costs, including a drug that "
        "looks above its MRP.",
        "judgment",
        covered_by="above_mrp",
    ),
    "branded_drug_margin": KindSpec(
        "a brand billed at a large margin where you recognise the molecule and know the "
        "generic costs far less.",
        "judgment",
    ),
    "capped_item_above_ceiling": KindSpec(
        "a stent, knee implant or scheduled drug billed above the government ceiling you know applies to it.",
        "judgment",
        covered_by="above_mrp",
    ),
    "non_medical_item": KindSpec(
        "an item that isn't treatment, e.g. a carry bag or an attendant's meals.",
        "judgment",
        whole_line=True,
    ),
    "package_overlap": KindSpec(
        "something billed separately that a package named on this bill would normally already "
        "cover — OT charges, PPE, consumables beside a stent package.",
        "judgment",
        whole_line=True,
    ),
    "nursing_billed_with_room": KindSpec(
        "nursing billed as its own line where the room rate normally includes it.",
        "judgment",
        whole_line=True,
    ),
    "service_charge_on_room": KindSpec(
        "a service or administration charge on top of room rent.",
        "judgment",
        whole_line=True,
    ),
    "quantity_high": KindSpec(
        "far more of something than a stay like this uses, e.g. 80 pairs of gloves for one ward day.",
        "judgment",
        covered_by="quantity",
    ),
    "visits_in_one_day": KindSpec(
        "more consultant visits on one date than a day plausibly holds.",
        "judgment",
    ),
    "same_test_two_names": KindSpec(
        'one test billed twice under different names, e.g. "CBC" and "Complete Blood Count".',
        "judgment",
        whole_line=True,
    ),
    "same_drug_twice_sources": KindSpec(
        "the same drug billed once from the pharmacy and again as a ward charge for the same date.",
        "judgment",
        whole_line=True,
        covered_by="duplicate",
    ),
    "room_rate_vs_ward": KindSpec(
        "the room rate doesn't match the ward the bill names, e.g. a general ward at a private-room rate.",
        "judgment",
    ),
    "icu_rate_on_ward_day": KindSpec(
        "an ICU rate charged for a date the bill shows the patient in a ward.",
        "judgment",
    ),
    "tax_on_exempt_item": KindSpec(
        "tax charged against a line whose category does not normally carry it.",
        "judgment",
        whole_line=True,
    ),
}

# A kind in the Literal but not the table would reach the reader with no
# description and no handling, which is the drift this module exists to stop.
assert set(READER_KINDS) == set(get_args(ReaderFlagKind)), (
    f"READER_KINDS and ReaderFlagKind disagree: {set(get_args(ReaderFlagKind)) ^ set(READER_KINDS)}"
)

CHECKABLE = frozenset(kind for kind, spec in READER_KINDS.items() if spec.checkable)
BILL_LEVEL = frozenset(kind for kind, spec in READER_KINDS.items() if spec.bill_level)
WHOLE_LINE = frozenset(kind for kind, spec in READER_KINDS.items() if spec.whole_line)
COVERED_BY_REFERENCES: dict[str, str] = {
    kind: spec.covered_by for kind, spec in READER_KINDS.items() if spec.covered_by
}


GROUPS: dict[Group, tuple[str, str]] = {
    "contradiction": (
        "Contradictions on the page",
        "These need nothing but the bill in front of you. Add the column, compare "
        "two fields, look for an entry that should be there and isn't.",
    ),
    "judgment": (
        "What an experienced eye notices",
        "No second document, but these rest on what you know: roughly what things "
        "cost in India, what a ward uses in a day, what a package normally covers. "
        "You cannot prove any of them from the page, so they are questions, and a "
        "wrong one costs a family more than a missed one.",
    ),
}


def prompt_section(width: int = 78) -> str:
    """The list of kinds as the prompt states it, built from the table above.

    Generated rather than written out a second time: a kind described to the
    reader but missing from the schema is rejected on the way back, and a kind
    in the schema the reader was never told about is never reported.
    """
    import textwrap

    parts = []
    for group, (heading, blurb) in GROUPS.items():
        parts.append(f"### {heading}\n")
        parts.append(textwrap.fill(blurb, width=width))
        parts.append("")
        for kind, spec in READER_KINDS.items():
            if spec.group != group:
                continue
            parts.append(
                textwrap.fill(
                    f"- `{kind}`: {spec.description}",
                    width=width,
                    subsequent_indent="  ",
                )
            )
        parts.append("")
    return "\n".join(parts).rstrip()
