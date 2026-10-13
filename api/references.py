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
import re
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from settings import get_settings

_PUNCTUATION = re.compile(r"[^\w\s]")
_SPACES = re.compile(r"\s+")
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
    return _SPACES.sub(" ", _PUNCTUATION.sub(" ", name.lower())).strip()


def parse_quantity(detail: str | None) -> Decimal | None:
    """Reads the count off the quantity as printed: "6 vials" -> 6.

    Returns None when the detail is a date rather than a count. Bills print
    both in the same column, and "11 Oct, 10:30 am" read as eleven of
    something turns one consultant visit into a quantity to question.
    """
    if not detail or _DATE_LIKE.match(detail):
        return None
    match = _COUNT.match(detail)
    if match is None:
        return None
    unit = (match.group(2) or "").lower()
    if unit in _MONTHS:
        return None
    return Decimal(match.group(1))


@dataclass(frozen=True)
class ReferencePrice:
    name: str
    aliases: tuple[str, ...]
    unit: str
    mrp: Decimal | None
    nppa_ceiling: Decimal | None
    source: str

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
        return _match(item_name, self.prices)

    def norm_for(self, item_name: str) -> QuantityNorm | None:
        return _match(item_name, self.quantity_norms)


def _match[T: ReferencePrice | QuantityNorm](item_name: str, candidates: tuple[T, ...]) -> T | None:
    """Finds the most specific reference whose alias appears in the line.

    Longest alias first, so "meropenem 1g" is preferred over "meropenem" and a
    1g vial is never checked against a 500mg price.
    """
    folded = normalize(item_name)
    best: tuple[int, T] | None = None
    for candidate in candidates:
        for alias in candidate.aliases:
            if alias in folded and (best is None or len(alias) > best[0]):
                best = (len(alias), candidate)
    return best[1] if best else None


def _decimal(value: object) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def load_reference_data(path: Path) -> ReferenceData:
    raw = json.loads(path.read_text(encoding="utf-8"))
    prices = tuple(
        ReferencePrice(
            name=entry["name"],
            # Longest first so the most specific alias is tried first.
            aliases=tuple(sorted((normalize(a) for a in entry["aliases"]), key=len, reverse=True)),
            unit=entry["unit"],
            mrp=_decimal(entry.get("mrp")),
            nppa_ceiling=_decimal(entry.get("nppa_ceiling")),
            source=entry.get("source", "sample"),
        )
        for entry in raw.get("prices", [])
    )
    norms = tuple(
        QuantityNorm(
            name=entry["name"],
            aliases=tuple(sorted((normalize(a) for a in entry["aliases"]), key=len, reverse=True)),
            unit=entry["unit"],
            usual_max_per_day=Decimal(str(entry["usual_max_per_day"])),
            source=entry.get("source", "sample"),
        )
        for entry in raw.get("quantity_norms", [])
    )
    return ReferenceData(prices=prices, quantity_norms=norms)


@lru_cache
def get_reference_data() -> ReferenceData:
    """FastAPI dependency. Loaded once; the lists only change on deploy."""
    return load_reference_data(Path(get_settings().reference_data_path))
