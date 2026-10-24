"""How the reader is doing, and whether the last change to it helped.

    uv run python scripts/reader_report.py            # every reading
    uv run python scripts/reader_report.py --days 30  # the last month

Reads `bill_reads` and `reader_findings`, which `bills.py` writes for every
bill it stores. Nothing here is served to a family and nothing here writes.

It groups by prompt digest, because that is the thing that changes when the
reader changes. Two digests side by side with different drop rates is the
only evidence a prompt edit helped; one digest over a year of bills says
whether it holds up.

What to look at, in order:

  * dropped (lines)  -- findings naming lines the reader did not transcribe.
    It lost its own numbering. A family is shown nothing, and this is the
    clearest signal the reading itself is coming apart.
  * explained        -- findings a family took to a billing desk and was
    told were fine. Some of that is the hospital's answer and some is the
    reader asking about nothing; a rate that climbs is worth reading.
  * corrected        -- the hospital put it right. The reader was correct and
    a family got money back, which is what all of this is for.
  * review           -- bills the reader asked for a human on.

It prints one line per rule under the totals, because a drop rate is an
average and the rule that is dragging it is usually one.
"""

import argparse
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import Integer, create_engine, func, select  # noqa: E402

import tables  # noqa: E402, F401  (registers the tables on Base.metadata)
from db import engine_options, utcnow  # noqa: E402
from review import DROPPED_LOW_SEVERITY, DROPPED_UNKNOWN_LINES  # noqa: E402
from settings import get_settings  # noqa: E402
from tables import BillRead, Flag, ReaderFinding  # noqa: E402


def pct(part: int, whole: int) -> str:
    return "    -" if whole == 0 else f"{100 * part / whole:4.0f}%"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=0, help="only readings this recent; 0 for all")
    args = parser.parse_args()

    url = get_settings().database_url
    engine = create_engine(url, **engine_options(url))
    since = utcnow() - timedelta(days=args.days) if args.days else None

    with engine.connect() as connection:
        reads = select(
            BillRead.prompt_digest,
            BillRead.model,
            func.count().label("bills"),
            func.sum(func.cast(BillRead.needs_human_review, Integer)).label("review"),
            func.avg(BillRead.extraction_confidence).label("confidence"),
        ).group_by(BillRead.prompt_digest, BillRead.model)
        if since is not None:
            reads = reads.where(BillRead.created_at >= since)

        rows = connection.execute(reads.order_by(func.count().desc())).all()
        if not rows:
            print("No readings stored yet. Check a bill and run this again.")
            return 0

        print(f"{'prompt':<18}{'model':<22}{'bills':>7}{'review':>8}{'conf':>7}")
        for row in rows:
            confidence = "   -" if row.confidence is None else f"{float(row.confidence):.2f}"
            print(
                f"{row.prompt_digest:<18}{row.model:<22}{row.bills:>7}"
                f"{pct(int(row.review or 0), row.bills):>8}{confidence:>7}"
            )

        print()
        outcomes = select(
            ReaderFinding.rule,
            func.count().label("total"),
            func.sum(func.cast(ReaderFinding.outcome == DROPPED_UNKNOWN_LINES, Integer)).label("lost"),
            func.sum(func.cast(ReaderFinding.outcome == DROPPED_LOW_SEVERITY, Integer)).label("low"),
            func.sum(func.cast(Flag.status == "corrected", Integer)).label("corrected"),
            func.sum(func.cast(Flag.status == "explained", Integer)).label("explained"),
        ).join(Flag, Flag.id == ReaderFinding.flag_id, isouter=True)
        if since is not None:
            outcomes = outcomes.where(ReaderFinding.created_at >= since)

        found = connection.execute(outcomes.group_by(ReaderFinding.rule).order_by(func.count().desc())).all()
        total = sum(row.total for row in found)
        lost = sum(int(row.lost or 0) for row in found)
        shown = total - lost - sum(int(row.low or 0) for row in found)
        corrected = sum(int(row.corrected or 0) for row in found)
        explained = sum(int(row.explained or 0) for row in found)

        print(
            f"{total} findings: {shown} shown, {lost} dropped (lines), {total - lost - shown} dropped (low)"
        )
        print(f"of the shown: {corrected} corrected ({pct(corrected, shown).strip()}), {explained} explained")
        print()

        print(f"{'rule':<52}{'n':>5}{'lost':>7}{'corr':>7}{'expl':>7}")
        for row in found:
            print(
                f"{row.rule[:50]:<52}{row.total:>5}{pct(int(row.lost or 0), row.total):>7}"
                f"{pct(int(row.corrected or 0), row.total):>7}{pct(int(row.explained or 0), row.total):>7}"
            )

    engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
