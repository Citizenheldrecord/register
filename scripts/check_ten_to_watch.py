#!/usr/bin/env python3
"""Ten-to-watch guard (proposed for the batch after 2026-10-25a). Standard library only.

Reads the ten ids from the Ten to watch list in plain-english.html (each <li> carries data-id="ID")
and looks each up in data/entries.csv. The build fails, naming the id, when an id is:
  MISSING   not in data/entries.csv (or an <li> has no data-id, or the list is not exactly ten)
  SCORED    the entry is resolved, or a later scoring entry closes it
  REPLACED  a later non-scoring entry (new date or correction) supersedes it
  PAST      its scoring date has passed by more than rc.GRACE_DAYS with no result
  DATE      the item's printed "Scored:" date is missing, unreadable, or differs from the leading
            date of the row's scoring_date cell (added 25 October 2026)
A failure means the list needs a swap (a dated line and Barry's go); this script never edits it.

Usage: python3 scripts/check_ten_to_watch.py YYYY-MM-DD [--page plain-english.html] [--source data/entries.csv]
Exit 0 when all ten are current, 1 otherwise.
"""
import argparse, datetime as dt, html, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import regcore as rc


_MON = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def leading_date(s):
    """The first date at the start of a cell: '2026-11-06...' or '6 Nov 2026...' (also 'Fri 6 Nov 2026', '6 November 2026')."""
    s = re.sub(r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*\.? ", "", (s or "").strip())
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    try:
        if m:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        m = re.match(r"(\d{1,2}) ([A-Z][a-z]{2})[a-z]*\.? (\d{4})", s)
        if m and m.group(2) in _MON:
            return dt.date(int(m.group(3)), _MON[m.group(2)], int(m.group(1)))
    except ValueError:
        return None
    return None


def ten_items(text):
    """[(id, plain text of the item)] in list order."""
    m = re.search(r"<h2>Ten to watch</h2>.*?<ol>(.*?)</ol>", text, re.S)
    if not m:
        raise rc.Fail("plain-english.html: no Ten to watch <ol> found")
    out = []
    for attrs, body in re.findall(r"<li\b([^>]*)>(.*?)</li>", m.group(1), re.S):
        a = re.search(r'data-id="([^"]+)"', attrs)
        out.append((html.unescape(a.group(1)) if a else None, html.unescape(re.sub(r"<[^>]+>", "", body))))
    return out


def date_problems(items, rows):
    byid = {r["id"]: r for r in rows}
    errs = []
    for n, (i, body) in enumerate(items, 1):
        r = byid.get(i)
        if not i or r is None:
            continue
        m = re.search(r"Scored: (.*)", body)
        printed = leading_date(m.group(1)) if m else None
        want = leading_date(r["scoring_date"])
        if want is None:
            try:
                want = dt.date.fromisoformat(r["sort_date"])
            except ValueError:
                want = None
        if printed is None:
            errs.append("DATE %s (item %d): no readable 'Scored:' date printed" % (i, n))
        elif want is None:
            errs.append("DATE %s (item %d): row scoring date %r is not readable" % (i, n, r["scoring_date"]))
        elif printed != want:
            errs.append("DATE %s (item %d): page prints %s, row scoring_date reads %r" % (i, n, printed, r["scoring_date"]))
    return errs


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
    errs = problems(ids, rows, a.date[:10]) + date_problems(ten_items(open(a.page, encoding="utf-8").read()), rows)
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
