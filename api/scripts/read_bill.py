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
from references import get_reference_data  # noqa: E402
from review import flags_from_findings  # noqa: E402
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

    analysis = bill
    header = analysis.bill
    print(
        f"\n{header.hospital or 'hospital not read'}  bill {header.bill_no or '-'}  "
        f"dated {header.bill_date or '-'}"
    )
    print(
        f"stay {header.admission_date or '-'} to {header.discharge_date or '-'}"
        f"  room {header.room_category or '-'}"
        f"  confidence {header.extraction_confidence:.2f}"
    )

    print(f"\n{len(analysis.lines)} line(s):\n")
    summed = Decimal("0")
    for position, line in enumerate(analysis.lines, start=1):
        summed += Decimal(str(line.amount or 0))
        shown = line.description_verbatim[:44]
        extra = line.date or (f"{line.quantity:g} {line.unit}".strip() if line.quantity else line.unit)
        mrp = f"  MRP {rupees(line.mrp_printed)}" if line.mrp_printed is not None else ""
        mark = "  ?" if line.ambiguous else ""
        print(f"  {position:>3}. {shown:<44} {extra[:18]:<18} {rupees(line.amount or 0):>12}{mrp}{mark}")
        if args.verbose:
            # PHASE 2's own reading of the line: what kind of charge it is, and
            # whichever specification attributes the bill printed.
            spec = ", ".join(f"{key} {value}" for key, value in sorted(line.attributes.items()) if value)
            print(f"       {line.category}{'  [' + spec + ']' if spec else ''}")
            if line.ambiguous and line.ambiguity_reason:
                print(f"       ambiguous: {line.ambiguity_reason}")

    print(f"\n      {'lines add up to':<64} {rupees(summed):>12}")
    if header.total is not None:
        print(f"      {'bill states':<64} {rupees(header.total):>12}")

    print(
        f"\nStructural: consumables {analysis.structural.consumable_share_pct:.1f}%  "
        f"unitemised {analysis.structural.unitemised_share_pct:.1f}%  "
        f"unreadable lines {analysis.structural.unreadable_line_count}"
    )
    if analysis.requires_reference_price:
        print(f"Needs a reference price: {', '.join(analysis.requires_reference_price)}")
    if analysis.needs_human_review:
        print(f"Needs human review: {'; '.join(analysis.review_reasons) or 'no reason given'}")

    print(f"\n{len(analysis.findings)} finding(s):\n")
    for finding in analysis.findings:
        print(f"  [{finding.severity}] {finding.rule}  lines {finding.line_ids or '-'}")
        print(f"      {finding.statement}")
        print(f"      evidence: {finding.evidence_quoted}")
        print(f"      to confirm: {finding.confirmation_required}")

    reference_flags = audit.audit_bill(
        [
            audit.BillRow(
                position=position,
                name=line.description_verbatim,
                detail=line.date or line.unit or None,
                quantity=None if line.quantity is None else Decimal(str(line.quantity)),
                amount=Decimal(str(line.amount or 0)),
            )
            for position, line in enumerate(analysis.lines, start=1)
        ],
        get_reference_data(),
    )

    flags = flags_from_findings(
        analysis, reference_flags, args.admitted, args.closed, keep_all=settings.review_keep_all
    )
    if args.admitted is None:
        print("\n  No --admitted date: the out-of-stay check is off.")
    if not settings.review_keep_all:
        print("\n  REVIEW_KEEP_ALL is off: low-severity findings are dropped.")

    print(f"\nAfter review, {len(flags)} flag(s) would be shown:\n")
    for flag in flags:
        source = "price list" if flag.reference_source != "reader" else "reader"
        amount = f" {rupees(flag.excess)}" if flag.excess else ""
        print(f"  {flag.level:<6} {flag.kind:<18} row {flag.row_position:<4} ({source}){amount}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
