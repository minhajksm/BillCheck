"""Every flag kind, and everything the code needs to know about each one.

This is the one place a kind is declared. Adding one used to mean editing the
reader's schema, the prompt, three sets in `review.py` and the API's response
model, and missing any of them failed somewhere else entirely: a kind absent
from the response model saved to the database fine and then broke serialising
the bill back out, with the type checker silenced on the field that would have
caught it.

So a kind is one entry in `READER_KINDS` below, and the Literals the API and
the database column validate against are derived from it.

What the reader reports is no longer one of these. `analysis.py` and
`analysis_prompt.py` have it state its own rule, quote its evidence and write
its own sentence, so every finding arrives as the one kind
`analysis_finding` carrying those words. The named kinds below are kept for
two reasons: `date_outside_stay` is still raised here, by the stay check the
reader cannot make; and bills read before the change have the older kinds on
disk, so `FlagOut` has to keep accepting them or a stored report 500s on the
way out.

The family-facing copy lives in the app, which has to carry it in three
languages. `tests/test_flag_kinds.py` checks the app's list still matches
this one.
"""

from dataclasses import dataclass
from typing import Literal, get_args

# Checked against a published price list, so the family can be shown where the
# number came from. These are the only kinds that are ever red.
CitedFlagKind = Literal["above_mrp", "duplicate", "quantity"]

# Noticed by the reader. None has a published reference behind it, so none is
# ever red; `reference_source` is "reader" for all of them.
ReaderFlagKind = Literal[
    # What the reader's analysis produces now. The finding carries its own
    # rule, evidence and wording, so there is nothing for a fixed taxonomy to
    # add: this is the one kind every finding arrives as.
    "analysis_finding",
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
    """One kind, and what it means."""

    description: str
    """What the kind says, in one sentence. Written for whoever reads a stored
    flag later and has to work out what it was about."""

    group: Group
    """`contradiction` needs nothing but the bill. `judgment` rests on what the
    reader knows, which is why nothing can confirm it."""


READER_KINDS: dict[ReaderFlagKind, KindSpec] = {
    "analysis_finding": KindSpec(
        "produced by the analysis prompt, which supplies its own rule and wording.",
        "contradiction",
    ),
    # --- Contradictions on the page -----------------------------------------
    "total_mismatch": KindSpec(
        "the rows you transcribed don't add up to the printed total.",
        "contradiction",
    ),
    "duplicate_line": KindSpec(
        "the same charge appears twice for the same moment.",
        "contradiction",
    ),
    "equipment_hours_exceed_stay": KindSpec(
        'billed hours for a machine exceed the stay, e.g. "Ventilator, 120 hrs" on a three-day admission.',
        "contradiction",
    ),
    "date_outside_stay": KindSpec(
        "a row is dated before admission or after discharge.",
        "contradiction",
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
    ),
    "advance_not_deducted": KindSpec(
        "the bill itself shows a deposit or advance paid, and the amount due does not take it off.",
        "contradiction",
    ),
    # --- What an experienced eye notices ------------------------------------
    "unit_price_high": KindSpec(
        "a consumable or drug priced well above what it usually costs, including a drug that "
        "looks above its MRP.",
        "judgment",
    ),
    "branded_drug_margin": KindSpec(
        "a brand billed at a large margin where you recognise the molecule and know the "
        "generic costs far less.",
        "judgment",
    ),
    "capped_item_above_ceiling": KindSpec(
        "a stent, knee implant or scheduled drug billed above the government ceiling you know applies to it.",
        "judgment",
    ),
    "non_medical_item": KindSpec(
        "an item that isn't treatment, e.g. a carry bag or an attendant's meals.",
        "judgment",
    ),
    "package_overlap": KindSpec(
        "something billed separately that a package named on this bill would normally already "
        "cover — OT charges, PPE, consumables beside a stent package.",
        "judgment",
    ),
    "nursing_billed_with_room": KindSpec(
        "nursing billed as its own line where the room rate normally includes it.",
        "judgment",
    ),
    "service_charge_on_room": KindSpec(
        "a service or administration charge on top of room rent.",
        "judgment",
    ),
    "quantity_high": KindSpec(
        "far more of something than a stay like this uses, e.g. 80 pairs of gloves for one ward day.",
        "judgment",
    ),
    "visits_in_one_day": KindSpec(
        "more consultant visits on one date than a day plausibly holds.",
        "judgment",
    ),
    "same_test_two_names": KindSpec(
        'one test billed twice under different names, e.g. "CBC" and "Complete Blood Count".',
        "judgment",
    ),
    "same_drug_twice_sources": KindSpec(
        "the same drug billed once from the pharmacy and again as a ward charge for the same date.",
        "judgment",
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
    ),
}

# A kind in the Literal but not the table would reach the reader with no
# description, which is the drift this module exists to stop.
assert set(READER_KINDS) == set(get_args(ReaderFlagKind)), (
    f"READER_KINDS and ReaderFlagKind disagree: {set(get_args(ReaderFlagKind)) ^ set(READER_KINDS)}"
)
