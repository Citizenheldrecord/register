#!/usr/bin/env python3
"""Overdue guard (25 October 2026). Standard library only.

Every promise in data/entries.csv whose scoring date has passed and that has no scoring entry must
have a dated line in data/scoring-pending.csv (id, noted, reason, recheck_by): noted on or after its
scoring date, with a recheck date not yet passed. One day of grace is allowed after a scoring date.

Optional --calendar FILE: a plain text schedule kept by whoever scores the register. Every LIVE id
that is not yet scored or replaced must appear in it as a whole word; missing ids are listed.

Usage: python3 scripts/check_overdue.py YYYY-MM-DD [--source data/entries.csv] [--calendar FILE]
Exit 0 when clean, 1 when any row is overdue without a current reason or missing from the calendar.
"""
import argparse, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import regcore as rc


def calendar_missing(rows, iso, text):
    c = rc.count_states(rows, iso)
    want = [r["id"] for r in rows if r["status"] == "LIVE" and c["state"].get(r["id"]) in ("Open", "Due")]
    return [i for i in want if not re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(i), text)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date")
    ap.add_argument("--source", default=rc.SOURCE)
    ap.add_argument("--pending", default=rc.PENDING)
    ap.add_argument("--calendar")
    a = ap.parse_args()
    _, rows = rc.read_source(a.source)
    c = rc.count_states(rows, a.date)
    errs = rc.overdue_problems(rows, a.date, rc.read_pending(a.pending))
    for rid, k in sorted(c["due_days"].items()):
        if k <= rc.GRACE_DAYS:
            print("WARN %s: scoring date passed %d day ago, not scored yet (grace)" % (rid, k))
    if a.calendar:
        miss = calendar_missing(rows, a.date, open(a.calendar, encoding="utf-8").read())
        errs += ["NOT IN CALENDAR %s" % i for i in miss]
    for e in errs:
        print(e)
    print("OVERDUE CHECK %s: %d due, %d problems" % ("OK" if not errs else "FAILED", len(c["due_days"]), len(errs)))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
