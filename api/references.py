"""The price lists a bill is checked against.

Two kinds of reference:

- a *price*, the most a unit should cost. The printed MRP, and where the drug
  is under price control, the NPPA ceiling price.
- a *quantity norm*, how much of something a ward stay usually uses. Going over
  it isn't wrong, only worth asking about.

Nothing here decides anything. It only answers "what should this have cost?",
so every flag can show the family what it was checked against.
"""

import json
import logging
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from settings import get_settings

logger = logging.getLogger("billcheck.references")

_PUNCTUATION = re.compile(r"[^\w\s]")
_SPACES = re.compile(r"\s+")
# "1 g" and "1g" are the same strength; fold them together so aliases match.
_SPACED_STRENGTH = re.compile(r"(\d)\s+(mcg|mg|gm|g|ml|l|iu)\b")
# A strength printed on a bill line: "1g", "0.5 g", "650mg", "500 ml".
_STRENGTH = re.compile(r"(\d+(?:\.\d+)?)\s*(mcg|mg|gm|g|ml|l|iu)\b")
_STRENGTH_SCALE = {
    "mcg": (Decimal("0.001"), "mg"),
    "mg": (Decimal("1"), "mg"),
    "g": (Decimal("1000"), "mg"),
    "gm": (Decimal("1000"), "mg"),
    "ml": (Decimal("1"), "ml"),
    "l": (Decimal("1000"), "ml"),
    "iu": (Decimal("1"), "iu"),
}
# Words on a bill line that say what form a medicine comes in. Prices differ
# by form far more than by brand, so a tablet price never checks an injection.
_FORM_WORDS = {
    "injectable": {"inj", "injection", "vial", "amp", "ampoule", "infusion", "iv"},
    "oral_solid": {"tab", "tabs", "tablet", "tablets", "cap", "caps", "capsule", "capsules"},
    "oral_liquid": {"syp", "syrup", "susp", "suspension"},
}
# The ways a bill writes a unit, folded to the spelling the price list uses.
_UNIT_SPELLINGS = {
    "vial": "vial vials",
    "ampoule": "amp amps ampoule ampoules ampule ampules",
    "tablet": "tab tabs tablet tablets",
    "capsule": "cap caps capsule capsules",
    "bottle": "bottle bottles btl btls",
    "strip": "strip strips",
    "pack": "pack packs packet packets box boxes",
    "pair": "pair pairs",
    "piece": "piece pieces pc pcs no nos",
    "visit": "visit visits",
}
_UNITS = {spelling: unit for unit, spellings in _UNIT_SPELLINGS.items() for spelling in spellings.split()}
# Sold in strips, so a bare count is as likely strips as single tablets. A
# price per tablet is only checked when the bill says it counted tablets.
PACKED_UNITS = frozenset({"tablet", "capsule"})
# How the price list names forms, mapped to the same groups.
_FORM_GROUPS = {
    "injection": "injectable",
    "iv fluid": "injectable",
    "tablet": "oral_solid",
    "capsule": "oral_solid",
    "syrup": "oral_liquid",
}
# A count is a number followed by what it counts. A month name after the
# number means the detail is a date, not a quantity.
_COUNT = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(?:x\s*)?([a-z]+)?", re.IGNORECASE)
_DATE_LIKE = re.compile(r"^\s*\d+\s*[/-]\s*\d")
_MONTHS = frozenset(
    "jan january feb february mar march apr april may jun june jul july "
    "aug august sep sept september oct october nov november dec december".split()
)


def normalize(name: str) -> str:
    """Folds a bill line down to something matchable: lowercase, no
    punctuation, single spaces. "Inj. Meropenem 1g" -> "inj meropenem 1g"."""
    folded = _SPACES.sub(" ", _PUNCTUATION.sub(" ", name.lower())).strip()
    return _SPACED_STRENGTH.sub(r"\1\2", folded)


Strength = tuple[Decimal, str]


def parse_strength(text: str) -> Strength:
    """Reads one strength: "1g" is (1000, "mg"), "500 ml" is (500, "ml"). Raises otherwise."""
    strengths = strengths_in(text)
    if len(strengths) != 1:
        raise ValueError(f"Expected one strength like '1g' or '500ml', got {text!r}")
    return next(iter(strengths))


def strengths_in(text: str) -> set[Strength]:
    """Every strength printed in a bill line, in mg, ml or IU, so "1g" and
    "1000mg" compare equal. Read before punctuation is folded away, which would
    turn "0.5g" into "0 5g"."""
    found: set[Strength] = set()
    for number, unit in _STRENGTH.findall(text.lower()):
        scale, base = _STRENGTH_SCALE[unit]
        found.add(((Decimal(number) * scale).normalize(), base))
    return found


def form_group(item_name: str) -> str | None:
    """Which form a bill line says it is, or None if it doesn't say, or says
    more than one."""
    words = set(normalize(item_name).split())
    groups = {group for group, markers in _FORM_WORDS.items() if words & markers}
    return groups.pop() if len(groups) == 1 else None


_TIME = re.compile(r"\b\d{1,2}[:.]\d{2}\b|\b(?:am|pm)\b", re.IGNORECASE)
_DATE = re.compile(r"\b\d{1,2}\s*[/-]\s*\d{1,2}(?:\s*[/-]\s*\d{2,4})?\b")


def is_timed(detail: str | None) -> bool:
    """Whether a detail pins a charge to a moment: "11 Oct, 10:30 am",
    "11/10", "10:30". Only then is a repeated line the same charge twice;
    "1 vial" twice is usually a morning and an evening dose."""
    if not detail:
        return False
    if _TIME.search(detail) or _DATE.search(detail):
        return True
    return any(word in _MONTHS for word in normalize(detail).split())


_MONTH_NUMBER = {
    name: number
    for number, names in enumerate(
        [
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ],
        start=1,
    )
    for name in names
}
# "11 Oct", "23-Oct-18", "23/Oct/2018", "2 Sept 2019", "11 Oct, 10:30 am",
# "22-Oct-18 10:45 AM". Hospital software writes the month as a word about as
# often as a number, and hyphenates it as readily as it spaces it.
#
# The year is optional, and the two lookaheads are what tell a year from a
# time. `(?!\d)` stops it taking the front of a longer number. `(?!\s*:)`
# stops "11 Oct, 10:30 am" reading its "10" as the year and dating the line in
# 2010 -- a time is the number with a colon straight after it, which is why
# the check cannot simply reject a year with digits following: "22-Oct-18
# 10:45 AM" is a year and then a time, and is how bills date their lines.
_DAY_MONTH = re.compile(
    r"\b(\d{1,2})[\s./-]*([a-z]{3,9})\.?(?:[\s.,/-]*(\d{2,4})(?!\d)(?!\s*:))?",
    re.IGNORECASE,
)
_NUMERIC_DATE = re.compile(r"\b(\d{1,2})\s*[/-]\s*(\d{1,2})(?:\s*[/-]\s*(\d{2,4}))?\b")
# Year first, which is how a reader that tidies dates writes them. Without
# this, "2026-10-15" reads as the 20th of the 26th month and comes back as no
# date at all -- and the stay check, which is the one caller that matters,
# would quietly stop finding anything.
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")


def parse_bill_date(detail: str | None, year: int | None = None) -> date | None:
    """Reads the date a row is dated, where it has one: "11 Oct, 10:30 am",
    "11/10/2026" or "2026-10-11". Bills often print no year, so the caller's
    `year` fills in.

    Returns None for anything that isn't a date, which is most details.
    """
    if not detail:
        return None

    iso = _ISO_DATE.search(detail)
    if iso:
        on_year, month, day = (int(part) for part in iso.groups())
        return _safe_date(on_year, month, day)

    numeric = _NUMERIC_DATE.search(detail)
    if numeric:
        day, month, maybe_year = numeric.groups()
        on_year = int(maybe_year) if maybe_year else (year or date.today().year)
        if on_year < 100:
            on_year += 2000
        return _safe_date(on_year, int(month), int(day))

    worded = _DAY_MONTH.search(detail)
    if worded:
        day, month_name, maybe_year = worded.groups()
        month = _MONTH_NUMBER.get(month_name.lower())
        if month is not None:
            if maybe_year:
                on_year = int(maybe_year)
                return _safe_date(on_year + 2000 if on_year < 100 else on_year, month, int(day))
            return _safe_date(year or date.today().year, month, int(day))
    return None


def _safe_date(year: int, month: int, day: int) -> date | None:
    """A misread "31 Feb" is not a date; it is a misread."""
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_quantity(detail: str | None) -> Decimal | None:
    """Reads the count off the quantity as printed: "6 vials" -> 6.

    Returns None when the detail is a date rather than a count. Bills print
    both in the same column, and "11 Oct, 10:30 am" read as eleven of
    something turns one consultant visit into a quantity to question.
    """
    return parse_count(detail)[0]


def parse_count(detail: str | None) -> tuple[Decimal | None, str | None]:
    """The count and what it counts: "2 strips" -> (2, "strip").

    The unit is folded to one spelling ("tabs" and "tablets" are both
    "tablet"); a word we don't know is kept as written, so it never matches a
    price list unit by accident. No unit printed gives (count, None).
    """
    if not detail or _DATE_LIKE.match(detail):
        return None, None
    match = _COUNT.match(detail)
    if match is None:
        return None, None
    word = (match.group(2) or "").lower()
    if word in _MONTHS:
        return None, None
    return Decimal(match.group(1)), (_UNITS.get(word, word) if word else None)


@dataclass(frozen=True)
class ReferencePrice:
    name: str
    aliases: tuple[str, ...]
    unit: str
    mrp: Decimal | None
    nppa_ceiling: Decimal | None
    source: str
    strength: Strength
    # One of the _FORM_GROUPS values, e.g. "injectable".
    form: str

    def fits(self, item_name: str) -> bool:
        """Whether a bill line is this exact product: the same single
        strength, and not a different form. A price for the 1g vial says
        nothing about a 2g vial, and a tablet price nothing about an infusion,
        so anything less certain is left unchecked rather than flagged."""
        if strengths_in(item_name) != {self.strength}:
            return False
        line_form = form_group(item_name)
        return line_form is None or line_form == self.form

    def ceiling(self) -> tuple[Decimal, str]:
        """The price to check against, and which list it came from. The NPPA
        ceiling wins when it is lower, since it is the legal maximum."""
        if self.nppa_ceiling is not None and (self.mrp is None or self.nppa_ceiling < self.mrp):
            return self.nppa_ceiling, "nppa"
        assert self.mrp is not None
        return self.mrp, "mrp"


@dataclass(frozen=True)
class QuantityNorm:
    name: str
    aliases: tuple[str, ...]
    unit: str
    usual_max_per_day: Decimal
    source: str


@dataclass(frozen=True)
class ReferenceData:
    prices: tuple[ReferencePrice, ...]
    quantity_norms: tuple[QuantityNorm, ...]

    def price_for(self, item_name: str) -> ReferencePrice | None:
        """The price for exactly this product, or None. Only a price whose
        strength and form fit the line is a candidate at all."""
        fitting = tuple(price for price in self.prices if price.fits(item_name))
        return _match(item_name, fitting)

    def norm_for(self, item_name: str) -> QuantityNorm | None:
        return _match(item_name, self.quantity_norms)


def _match[T: ReferencePrice | QuantityNorm](item_name: str, candidates: tuple[T, ...]) -> T | None:
    """Finds the most specific reference whose alias appears in the line as
    whole words. Longest alias wins, so the most specific entry is used."""
    folded = normalize(item_name)
    best: tuple[int, T] | None = None
    for candidate in candidates:
        for alias in candidate.aliases:
            if _contains_words(folded, alias) and (best is None or len(alias) > best[0]):
                best = (len(alias), candidate)
    return best[1] if best else None


def _contains_words(folded: str, alias: str) -> bool:
    """Whole words only: "gloves" is in "surgical gloves", "iv" is not in "ivermectin"."""
    return re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", folded) is not None


def _decimal(value: object) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _price(entry: dict) -> ReferencePrice:
    """A price entry must say its strength and form. Without them it would be
    checked against every strength of the drug, which is how a 2g vial ends up
    "above the MRP" of a 1g one."""
    name = entry["name"]
    try:
        strength = parse_strength(entry["strength"])
        form = _FORM_GROUPS[entry["form"]]
    except (KeyError, ValueError) as exc:
        raise ValueError(
            f"Price entry {name!r} needs a 'strength' like '1g' and a 'form', one of {sorted(_FORM_GROUPS)}"
        ) from exc
    return ReferencePrice(
        name=name,
        # Longest first so the most specific alias is tried first.
        aliases=tuple(sorted((normalize(a) for a in entry["aliases"]), key=len, reverse=True)),
        unit=entry["unit"],
        mrp=_decimal(entry.get("mrp")),
        nppa_ceiling=_decimal(entry.get("nppa_ceiling")),
        source=entry.get("source", SAMPLE),
        strength=strength,
        form=form,
    )


SAMPLE = "sample"


def load_reference_data(path: Path, *, allow_sample_prices: bool = False) -> ReferenceData:
    """The lists at `path`. Prices marked "sample" -- or not marked at all,
    which reads as sample -- are left out unless `allow_sample_prices`.

    Every entry is still checked first, so a malformed sample is refused
    rather than quietly skipped: the file has to be right either way.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    every_price = tuple(_price(entry) for entry in raw.get("prices", []))
    prices = tuple(price for price in every_price if allow_sample_prices or price.source != SAMPLE)
    if len(prices) < len(every_price):
        logger.warning(
            "Left out %d sample price(s) from %s: illustrative figures raise no flag here",
            len(every_price) - len(prices),
            path,
        )
    norms = tuple(
        QuantityNorm(
            name=entry["name"],
            aliases=tuple(sorted((normalize(a) for a in entry["aliases"]), key=len, reverse=True)),
            unit=entry["unit"],
            usual_max_per_day=Decimal(str(entry["usual_max_per_day"])),
            source=entry.get("source", SAMPLE),
        )
        for entry in raw.get("quantity_norms", [])
    )
    return ReferenceData(prices=prices, quantity_norms=norms)


@lru_cache
def get_reference_data() -> ReferenceData:
    """FastAPI dependency. Loaded once; the lists only change on deploy."""
    settings = get_settings()
    return load_reference_data(
        Path(settings.reference_data_path), allow_sample_prices=settings.allow_sample_prices
    )
