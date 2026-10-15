"""The reader's categories, and the three places that have to agree on them.

PHASE 2 of the analysis classifies every line; the report groups the bill by
that, so a family can see what the consumables came to. Three lists have to
match for that to work, in two languages and one database column, and only a
test keeps them honest:

- `analysis.Category`, which the reader is constrained to
- `CATEGORY_ORDER`, the order the report shows them in
- the app's `LineCategory`, which is TypeScript and cannot be derived

The failure if they drift is quiet in the way this project has been bitten by
before: a category the app doesn't know would file a line under the wrong
heading, and a column too narrow would reject it on the way in.
"""

import re
from pathlib import Path
from typing import get_args

import pytest
from sqlalchemy import String

from analysis import CATEGORY_ORDER, Category
from tables import LineItem

DECLARED = get_args(Category)
APP = Path(__file__).resolve().parents[2] / "app"


def app_list(source: str, name: str) -> set[str]:
    declaration = rf"(?:export type {name} =|const {name}: LineCategory\[\] = \[)"
    block = re.search(rf"{declaration}(.*?)[;\]]", source, re.S)
    assert block, f"{name} is not declared where this test looks for it"
    return set(re.findall(r"'([a-z_]+)'", block.group(1)))


def test_the_order_covers_exactly_the_declared_categories():
    """A category missing from the order would be filtered out of the report,
    taking its lines with it."""
    assert set(CATEGORY_ORDER) == set(DECLARED)
    assert len(CATEGORY_ORDER) == len(DECLARED), "no category twice"


def test_unclassified_is_last():
    """It is the reader's own fallback and what older bills carry, so it reads
    as the catch-all it is rather than opening the report."""
    assert CATEGORY_ORDER[-1] == "unclassified"


def test_the_column_fits_every_category():
    """The widest is `consumable_disposable`. A column a character short would
    reject the commonest group on a hospital bill."""
    column = LineItem.__table__.c.category.type
    assert isinstance(column, String)
    assert column.length is not None
    assert column.length >= max(len(category) for category in DECLARED)


def test_the_column_defaults_to_the_catch_all():
    """Bills read before this column existed have no category to recover, so
    they must still group somewhere."""
    assert LineItem.__table__.c.category.server_default.arg == "unclassified"


@pytest.mark.parametrize("name", ["LineCategory", "CATEGORY_ORDER"])
def test_the_app_knows_the_same_categories(name: str):
    """The app's list is a separate language, declared twice -- once as the
    type, once as the display order -- and nothing but this keeps either in
    step with Python."""
    source = {
        "LineCategory": APP / "src" / "data" / "types.ts",
        "CATEGORY_ORDER": APP / "src" / "app" / "bills" / "[billId].tsx",
    }[name].read_text(encoding="utf-8")

    in_app = app_list(source, name)
    assert in_app == set(DECLARED), f"{name} is out of step with analysis.py: {in_app ^ set(DECLARED)}"


def test_the_app_shows_them_in_the_same_order():
    source = (APP / "src" / "app" / "bills" / "[billId].tsx").read_text(encoding="utf-8")
    block = re.search(r"const CATEGORY_ORDER: LineCategory\[\] = \[(.*?)\]", source, re.S)
    assert block
    assert re.findall(r"'([a-z_]+)'", block.group(1)) == list(CATEGORY_ORDER)


@pytest.mark.parametrize("language", ["en", "hi", "mr"])
def test_every_category_has_copy_in_every_language(language: str):
    """CLAUDE.md: all user-facing strings go through i18n. A heading with no
    translation would show a family the raw key."""
    import json

    locale = json.loads((APP / "src" / "i18n" / "locales" / f"{language}.json").read_text(encoding="utf-8"))
    labels = locale["report"]["categories"]

    assert set(labels) == set(DECLARED), f"{language} is missing {set(DECLARED) - set(labels)}"
    assert all(label.strip() for label in labels.values())
