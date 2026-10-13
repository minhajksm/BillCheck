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
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import audit  # noqa: E402
from ocr import BillPage, OcrError, get_ocr_provider  # noqa: E402
from references import get_reference_data  # noqa: E402
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


def rupees(value: Decimal | float) -> str:
    return f"{Decimal(str(value)):,.2f}".rstrip("0").rstrip(".")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pages", nargs="+", type=Path, help="Pages of one bill, in order.")
    parser.add_argument(
        "--admitted",
        type=date.fromisoformat,
        default=date.today() - timedelta(days=2),
        help="Admission date (YYYY-MM-DD), for the out-of-stay check.",
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

    flags = review(bill, reference_flags, args.admitted)
    kept = {(flag.kind, flag.row_position) for flag in flags}

    print(f"\nAfter review, {len(flags)} flag(s) would be shown:\n")
    for flag in flags:
        source = "price list" if flag.reference_source != "reader" else "reader"
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
