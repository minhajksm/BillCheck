"""The one table of kinds, and everything that has to agree with it.

A kind used to be declared in four places by hand. The failure that followed
was quiet in the worst way: a kind missing from the API's response model saved
to the database fine, and then broke serialising the bill back out, with the
type checker silenced on the one field that would have caught it. 221 tests,
two linters and a typecheck all passed on code that was certain to 500.

So these tests check the things that cannot drift silently.
"""

import re
import uuid
from pathlib import Path
from typing import get_args

import pytest
from pydantic import ValidationError

from flag_kinds import (
    CHECKABLE,
    COVERED_BY_REFERENCES,
    READER_KINDS,
    WHOLE_LINE,
    CitedFlagKind,
    ReaderFlagKind,
    prompt_section,
)
from models import FlagOut
from ocr import PROMPT, ExtractedBill

READER = get_args(ReaderFlagKind)
CITED = get_args(CitedFlagKind)


def flag_out(kind: str) -> FlagOut:
    return FlagOut(
        id=uuid.uuid4(),
        position=1,
        line_item_id=None,
        kind=kind,  # type: ignore[arg-type]
        level="amber",
        status="open",
        billed=100.0,
        reference_amount=0.0,
        reference_source="reader",
        reference_detail={},
        excess=0.0,
    )


# --- the bug this file exists for -------------------------------------------


@pytest.mark.parametrize("kind", READER + CITED)
def test_every_kind_survives_the_trip_back_to_the_app(kind: str):
    """The exact failure: review made a `nursing_billed_with_room` flag, the
    database took it, and FlagOut rejected it on the way out."""
    assert flag_out(kind).kind == kind


def test_an_invented_kind_is_still_rejected():
    with pytest.raises(ValidationError):
        flag_out("definitely_not_a_kind")


# --- the table and the schema -----------------------------------------------


def test_the_table_covers_exactly_the_declared_kinds():
    assert set(READER_KINDS) == set(READER)


def test_the_reader_s_schema_allows_exactly_the_declared_kinds():
    schema = ExtractedBill.model_json_schema()
    assert set(schema["$defs"]["Observation"]["properties"]["kind"]["enum"]) == set(READER)


@pytest.mark.parametrize("kind", READER)
def test_the_prompt_describes_every_kind_it_allows(kind: str):
    """A kind in the schema the reader was never told about is never reported;
    one described but not in the schema is rejected on the way back."""
    assert f"`{kind}`" in PROMPT
    # The prompt wraps each line, so compare with the wrapping taken out.
    flattened = " ".join(prompt_section().split())
    assert f"`{kind}`: {READER_KINDS[kind].description}" in flattened


# --- the sets review works from ---------------------------------------------


def test_only_kinds_with_a_confirm_step_are_checkable():
    """`review.py` matches on these by name. A kind marked checkable with no
    `_confirm_*` behind it would fall to the date branch and be dropped."""
    assert CHECKABLE == {"total_mismatch", "duplicate_line", "date_outside_stay"}


def test_what_a_correction_gives_back_is_only_claimed_for_whole_line_kinds():
    degree = {"unit_price_high", "quantity_high", "branded_drug_margin", "room_rate_vs_ward"}
    assert not (degree & WHOLE_LINE), "a judgment of degree has no defensible figure"


@pytest.mark.parametrize("kind,cited", sorted(COVERED_BY_REFERENCES.items()))
def test_a_kind_is_only_covered_by_a_real_cited_kind(kind: str, cited: str):
    assert cited in CITED


# --- the copy that cannot be derived ----------------------------------------


def test_the_app_knows_the_same_kinds():
    """The app's own list is a separate language, so nothing but a test keeps
    it honest. A kind the app doesn't know falls through to generic copy."""
    types_ts = Path(__file__).resolve().parents[2] / "app" / "src" / "data" / "types.ts"
    source = types_ts.read_text(encoding="utf-8")

    block = re.search(r"export type ReaderFlagKind =(.*?);", source, re.S)
    assert block, "ReaderFlagKind is not declared in types.ts any more"
    in_app = set(re.findall(r"'([a-z_]+)'", block.group(1)))

    assert in_app == set(READER), (
        f"app/src/data/types.ts is out of step with flag_kinds.py: {in_app ^ set(READER)}"
    )
