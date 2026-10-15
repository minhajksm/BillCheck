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

from analysis import BillAnalysis
from flag_kinds import READER_KINDS, CitedFlagKind, KindSpec, ReaderFlagKind
from models import FlagOut

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


def test_the_reader_s_schema_no_longer_names_a_kind():
    """The reader states its own rule and writes its own sentence, so there is
    no enum of ours for it to pick from. A `kind` back in that schema would
    mean the taxonomy had crept back in by the side door."""
    schema = BillAnalysis.model_json_schema()
    assert "kind" not in schema["$defs"]["Finding"]["properties"]


def test_the_kinds_the_code_still_raises_are_declared():
    """Not every kind is produced any more -- the older ones are kept so a
    stored flag still serialises -- but these two are raised on every bill."""
    assert {"analysis_finding", "date_outside_stay"} <= set(READER)


@pytest.mark.parametrize("kind,spec", sorted(READER_KINDS.items()))
def test_every_kind_says_what_it_means(kind: str, spec: KindSpec):
    """Whoever reads a stored flag years from now has only this to go on."""
    assert spec.description.strip(), kind


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
