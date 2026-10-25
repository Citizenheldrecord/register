#!/usr/bin/env python3
"""Ten-to-watch guard (proposed for the batch after 2026-10-25a). Standard library only.

Reads the ten ids from the Ten to watch list in plain-english.html (each <li> carries data-id="ID")
and looks each up in data/entries.csv. The build fails, naming the id, when an id is:
  MISSING   not in data/entries.csv (or an <li> has no data-id, or the list is not exactly ten)
  SCORED    the entry is resolved, or a later scoring entry closes it
  REPLACED  a later non-scoring entry (new date or correction) supersedes it
  PAST      its scoring date has passed by more than rc.GRACE_DAYS with no result
A failure means the list needs a swap (a dated line and Barry's go); this script never edits it.

Usage: python3 scripts/check_ten_to_watch.py YYYY-MM-DD [--page plain-english.html] [--source data/entries.csv]
Exit 0 when all ten are current, 1 otherwise.
"""
import argparse, datetime as dt, html, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import regcore as rc


def ten_ids(text):
    m = re.search(r"<h2>Ten to watch</h2>.*?<ol>(.*?)</ol>", text, re.S)
    if not m:
        raise rc.Fail("plain-english.html: no Ten to watch <ol> found")
    items = re.findall(r"<li\b([^>]*)>", m.group(1))
    ids = []
    for n, attrs in enumerate(items, 1):
        a = re.search(r'data-id="([^"]+)"', attrs)
        ids.append(html.unescape(a.group(1)) if a else None)
    return ids


def problems(ids, rows, iso):
    byid = {r["id"]: r for r in rows}
    cb, rb = rc.closed_by(rows), rc.replaced_by(rows)
    today = dt.date.fromisoformat(iso)
    errs = []
    if len(ids) != 10:
        errs.append("LIST has %d items, not 10" % len(ids))
    for n, i in enumerate(ids, 1):
        if not i:
            errs.append("MISSING item %d has no data-id" % n); continue
        r = byid.get(i)
        if r is None:
            errs.append("MISSING %s (item %d) is not in data/entries.csv" % (i, n)); continue
        if rc.is_resolved(r) or i in cb:
            errs.append("SCORED %s (item %d): %s" % (i, n, ("closed by " + cb[i]) if i in cb else r["status"])); continue
        if i in rb:
            errs.append("REPLACED %s (item %d): replaced by %s" % (i, n, rb[i])); continue
        try:
            sd = dt.date.fromisoformat(r["sort_date"])
        except ValueError:
            errs.append("MISSING %s (item %d): scoring date %r is not readable" % (i, n, r["sort_date"])); continue
        late = (today - sd).days
        if late > rc.GRACE_DAYS:
            errs.append("PAST %s (item %d): scoring date %s passed %d days ago with no result" % (i, n, sd, late))
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date")
    ap.add_argument("--page", default=os.path.join(rc.ROOT, "plain-english.html"))
    ap.add_argument("--source", default=rc.SOURCE)
    a = ap.parse_args()
    _, rows = rc.read_source(a.source)
    ids = ten_ids(open(a.page, encoding="utf-8").read())
    errs = problems(ids, rows, a.date[:10])
    for e in errs:
        print("TEN-TO-WATCH FAIL " + e)
    bad = len([e for e in errs if not e.startswith("LIST")])
    print("TEN-TO-WATCH %s: %d of %d current (%s)" % ("OK" if not errs else "NO-GO", len(ids) - bad, len(ids), ", ".join(i or "?" for i in ids)))
    return 1 if errs else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except rc.Fail as e:
        print("TEN-TO-WATCH FAIL %s" % e); sys.exit(1)
