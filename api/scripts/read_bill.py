"""Read one bill with the real reader and print what came back.

The quickest way to answer "can it actually read our bills?" without the app,
the database or a sign-in. It runs exactly the code the API runs.

    OCR_PROVIDER=claude ANTHROPIC_API_KEY=sk-... \\
      uv run python scripts/read_bill.py ../data/private/bill.pdf

Pass several pages of one bill together, in order:

    uv run python scripts/read_bill.py page1.jpg page2.jpg

It prints the rows, what the reader noticed, and then what survives review:
which observations the rows bore out, and which were dropped and why. The
dropped ones are the interesting column — they are either a misread page or a
reader that over-reports.

Keep real bills in data/private/, which is gitignored. Nothing here writes a
file, but a real bill must never end up in the repository.
"""

import argparse
import logging
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import audit  # noqa: E402
from ocr import BillPage, OcrError, get_ocr_provider  # noqa: E402
from references import get_reference_data, parse_bill_date  # noqa: E402
from review import review  # noqa: E402
from settings import get_settings  # noqa: E402

MEDIA = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".pdf": "application/pdf",
}


def _iso(value: str | None) -> bool:
    """Whether the reader gave us a date we can actually read."""
    try:
        return bool(value) and bool(date.fromisoformat(str(value)))
    except ValueError:
        return False


def rupees(value: Decimal | float) -> str:
    return f"{Decimal(str(value)):,.2f}".rstrip("0").rstrip(".")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pages", nargs="+", type=Path, help="Pages of one bill, in order.")
    parser.add_argument(
        "--admitted",
        type=date.fromisoformat,
        help="Admission date (YYYY-MM-DD). Without it the out-of-stay check is off.",
    )
    parser.add_argument(
        "--closed",
        type=date.fromisoformat,
        help="Discharge date (YYYY-MM-DD). Leave it out for a stay still open.",
    )
    parser.add_argument("--verbose", action="store_true", help="Show the reader's own reasoning.")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="  %(levelname)-7s %(name)s: %(message)s",
    )

    settings = get_settings()
    print(f"Provider: {settings.ocr_provider}", end="")
    if settings.ocr_provider == "claude":
        print(f"  model: {settings.ocr_model}  effort: {settings.ocr_effort}")
    else:
        print("\n\n  OCR_PROVIDER is 'stub', so this prints the sample bill, not your pages.")
        print("  Set OCR_PROVIDER=claude and ANTHROPIC_API_KEY to read for real.\n")

    pages = []
    for path in args.pages:
        media = MEDIA.get(path.suffix.lower())
        if media is None:
            print(f"Don't know what {path.suffix} is. Use {', '.join(sorted(MEDIA))}.", file=sys.stderr)
            return 2
        pages.append(BillPage(data=path.read_bytes(), content_type=media))
        print(f"  {path.name}: {len(pages[-1].data) / 1024:,.0f} KB, {media}")

    print("\nReading…")
    try:
        bill = get_ocr_provider().read_bill(pages)
    except OcrError as exc:
        print(f"\nCouldn't read it: {exc}", file=sys.stderr)
        return 1

    print(f"\n{len(bill.rows)} row(s), bill date {bill.bill_date or 'not read'}:\n")
    year = date.fromisoformat(bill.bill_date).year if _iso(bill.bill_date) else date.today().year
    summed = Decimal("0")
    for position, row in enumerate(bill.rows, start=1):
        summed += Decimal(str(row.amount))
        detail = f"  [{row.detail}]" if row.detail else ""
        print(f"  {position:>3}. {row.name[:48]:<48}{detail:<22} {rupees(row.amount):>12}")
    print(f"\n      {'rows add up to':<70} {rupees(summed):>12}")
    if bill.stated_total is not None:
        print(f"      {'bill states':<70} {rupees(bill.stated_total):>12}")

    print(f"\nThe reader noticed {len(bill.observations)}:\n")
    for observation in bill.observations:
        numbers = " ".join(f"{k}={v}" for k, v in observation.numbers().items())
        rows = str(observation.row_positions)
        print(f"  {observation.kind:<24} rows {rows:<10} {observation.confidence:<7} {numbers}")
        if observation.note:
            print(f"      {observation.note}")

    reference_flags = audit.audit_bill(
        [
            audit.BillRow(
                position=position,
                name=row.name,
                detail=row.detail,
                quantity=None if row.quantity is None else Decimal(str(row.quantity)),
                amount=Decimal(str(row.amount)),
            )
            for position, row in enumerate(bill.rows, start=1)
        ],
        get_reference_data(),
    )

    admitted, closed = args.admitted, args.closed
    if admitted is None:
        # Guessing an admission date would date every row of an older bill
        # outside the stay and flag the whole page. Take the window from the
        # rows instead, which flags nothing, and say the check is off.
        dated = [on for on in (parse_bill_date(row.detail, year) for row in bill.rows) if on]
        admitted, closed = (min(dated), max(dated)) if dated else (date.min, date.max)
        print("\n  No --admitted given, so the out-of-stay check is off.")
        print("  Pass --admitted and --closed to run it.")

    flags = review(bill, reference_flags, admitted, closed, keep_all=settings.review_keep_all)
    kept = {(flag.kind, flag.row_position) for flag in flags}

    if settings.review_keep_all:
        print("\n  REVIEW_KEEP_ALL is on: nothing the reader said is dropped.")
    print(f"\nAfter review, {len(flags)} flag(s) would be shown:\n")
    for flag in flags:
        source = "price list" if flag.reference_source != "reader" else "reader"
        if flag.reference_detail.get("unconfirmed"):
            source += ", unconfirmed"
        amount = f" {rupees(flag.excess)}" if flag.excess else ""
        print(f"  {flag.level:<6} {flag.kind:<24} row {flag.row_position:<4} ({source}){amount}")

    dropped = [
        observation
        for observation in bill.observations
        if not any(
            (observation.kind, position) in kept or (observation.kind, 0) in kept
            for position in (observation.row_positions or [0])
        )
    ]
    if dropped:
        print(f"\n{len(dropped)} observation(s) did not survive review:\n")
        for observation in dropped:
            print(f"  {observation.kind:<24} rows {observation.row_positions}  — {observation.note}")
        print("\n  Run with --verbose to see why each was dropped.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
