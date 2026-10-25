"""Shared rules for the Citizen-Held Register pipeline. Standard library only."""
import csv, io, re, sys, os
import datetime as _dt
from datetime import date, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "data", "entries.csv")
SECTION_ORDER = ["CANADA", "DESK", "WATCH", "RECORDED"]
SUBSCORE_COLS = ["hype_score", "means_score", "cost_score"]
FOLLOWS_COL = "follows_id"  # optional link to the entry this one follows (Barry 24 Oct 2026: PASS is not delivery); blank by default, not part of the fingerprint
REQUIRED = ["id", "section", "sort_date", "scoring_date", "test", "owner", "date_source", "status", "cost_to_date"] + SUBSCORE_COLS
SUBSCORE_VALUES = {"MATCHED", "MIXED", "FAILED", "OPEN"}
RULE_START = "2026-10-18"   # rules A and B apply to entries scored after this date
BAD_CHARS = re.compile("[\u2013\u2014\u2015\u2212\u2018\u2019\u201a\u201b\u201c\u201d\u201e\u201f]")
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]


class Fail(Exception):
    pass


def long_date(iso):
    d = datetime.strptime(iso, "%Y-%m-%d").date()
    return "%d %s %d" % (d.day, MONTHS[d.month - 1], d.year)


def short_date(iso):
    d = datetime.strptime(iso, "%Y-%m-%d").date()
    return "%d %s %d" % (d.day, MONTHS[d.month - 1][:3], d.year)


def parse_short(s):
    return datetime.strptime(s.strip(), "%d %b %Y").date().isoformat()


def read_source(path=SOURCE):
    with open(path, encoding="utf-8", newline="") as fh:
        rdr = csv.DictReader(fh)
        return list(rdr.fieldnames), list(rdr)


def write_csv_text(header, rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=header)
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def is_resolved(r):
    s = r.get("status", "").upper()
    return s.startswith("SCORED") or s.startswith("PASS") or s.startswith("FAILED")


def validate(header, rows):
    """Return a list of problems; empty means the data passes every rule."""
    errs = []
    for c in REQUIRED:
        if c not in header:
            errs.append("schema: column '%s' missing" % c)
    if errs:
        return errs
    seen = set()
    for n, r in enumerate(rows, start=2):
        rid = r.get("id", "").strip()
        where = "line %d (%s)" % (n, rid or "no id")
        if not rid:
            errs.append(where + ": no id")
        elif rid in seen:
            errs.append(where + ": duplicate id")
        seen.add(rid)
        if r["section"] not in SECTION_ORDER:
            errs.append(where + ": unknown section '%s'" % r["section"])
        for c in ("test", "scoring_date", "owner", "date_source", "status", "cost_to_date"):
            if not r.get(c, "").strip():
                errs.append(where + ": %s is empty" % c)
        if r["section"] != "RECORDED" and "PASS" not in r.get("test", ""):
            errs.append(where + ": test has no PASS outcome")
        try:
            datetime.strptime(r["sort_date"], "%Y-%m-%d")
        except ValueError:
            errs.append(where + ": sort_date '%s' is not YYYY-MM-DD" % r["sort_date"])
        for k, v in r.items():
            if v and BAD_CHARS.search(v):
                errs.append(where + ": house grammar, dash or curly quote in %s: %r" % (k, BAD_CHARS.findall(v)))
        sid, sh = r.get("supersedes_id", ""), r.get("supersedes_hash", "")
        if bool(sid) != bool(sh):
            errs.append(where + ": supersedes_id and supersedes_hash must both be set or both empty")
        if sid and sid not in seen and sid not in {x["id"] for x in rows}:
            errs.append(where + ": supersedes unknown id %s" % sid)
        fid = (r.get(FOLLOWS_COL) or "").strip()
        if fid:
            if fid == rid:
                errs.append(where + ": follows_id points at itself")
            elif fid not in {x["id"] for x in rows}:
                errs.append(where + ": follows unknown id %s" % fid)
        for c in SUBSCORE_COLS:
            if r.get(c, "") not in SUBSCORE_VALUES:
                errs.append(where + ": %s must be MATCHED, MIXED, FAILED or OPEN (got %r)" % (c, r.get(c, "")))
        if is_resolved(r) and r["sort_date"] > RULE_START:
            cd = r.get("cost_to_date", "")
            if not cd or cd.upper().startswith("OPEN"):
                errs.append(where + ": resolved entry needs cost to date (amount with source, or FAILED naming the holder)")
            if not sid:
                errs.append(where + ": a scoring entry must cite the scored entry (supersedes_id and supersedes_hash)")
    return errs


def sort_rows(rows):
    idx = {id(r): i for i, r in enumerate(rows)}
    return sorted(rows, key=lambda r: (SECTION_ORDER.index(r["section"]), r["sort_date"], idx[id(r)]))


def grammar_check_text(name, text):
    bad = BAD_CHARS.findall(text)
    return ["%s: house grammar, %d dash or curly quote characters %r" % (name, len(bad), sorted(set(bad)))] if bad else []


UID = re.compile(r"^(\d{4}-\d\d-\d\d)([a-z]?)$")


def split_uid(uid):
    """An update id is a date, plus a letter for a second update on the same day (2026-10-18b)."""
    m = UID.match(uid or "")
    if not m:
        raise Fail("update id must be YYYY-MM-DD or YYYY-MM-DD plus one letter, got %r" % uid)
    return m.group(1), m.group(2)


def closed_by(rows):
    """Display only: map scored entry id to the id of the scoring entry that closes it."""
    return {r["supersedes_id"]: r["id"] for r in rows if r.get("supersedes_id") and is_resolved(r)}


def replaced_by(rows):
    """Display only: map an entry id to the later non-scoring entry (new date or correction) that replaces it."""
    return {r["supersedes_id"]: r["id"] for r in rows if r.get("supersedes_id") and not is_resolved(r)}


CORRECTION_ID = re.compile(r"^(.+)-C(\d{8})$")
CORRECTION_NOTE = re.compile(r"CORRECTION (\d{1,2} [A-Z][a-z]{2} \d{4}):")


def is_correction(r, byid):
    """True only for an entry explicitly marked as a correction: id <ORIGINAL>-C<YYYYMMDD>, a dated
    'CORRECTION d Mon YYYY:' note in date_source, supersedes_id naming an existing unscored entry,
    and the same test, scoring date and section as that entry."""
    m = CORRECTION_ID.match(r.get("id", ""))
    o = byid.get(r.get("supersedes_id", ""))
    return bool(m and o and m.group(1) == o["id"] and CORRECTION_NOTE.search(r.get("date_source", ""))
                and not is_resolved(o) and not is_resolved(r) and r["test"] == o["test"]
                and r["scoring_date"] == o["scoring_date"] and r["sort_date"] == o["sort_date"] and r["section"] == o["section"])


def display_status(r, closers, replaced=None):
    if r["id"] in closers:
        return "CLOSED: scored in %s" % closers[r["id"]]
    if replaced and r["id"] in replaced:
        return "REPLACED by %s; this entry is kept" % replaced[r["id"]]
    return r["status"]


# --- Housekeeping (rule entry R-2026-10-24-A). Internal working notes may be removed from a row.
# Every removal is listed in data/housekeeping-log.csv with the row's fingerprint before and after,
# per fingerprint layout. The build accepts a changed fingerprint only when the log lists it, the
# change touches only HOUSEKEEPING_FIELDS, and each change only deletes text or replaces it with OPEN.
HOUSEKEEPING_LOG = os.path.join(ROOT, "data", "housekeeping-log.csv")
HOUSEKEEPING_COLS = ["date", "update", "id", "field", "action", "layout", "entry_sha256_before", "entry_sha256_after"]
HOUSEKEEPING_FIELDS = ("date_source", "measure", "money", "funding", "argument", "test")
# Rule entry R-2026-10-25-A extends the rule to the test field, for internal approval notes only:
# a test may only lose one stretch of text; it may never be replaced with OPEN.
NO_OPEN_FIELDS = ("test",)


def read_housekeeping(path=HOUSEKEEPING_LOG):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as fh:
        rdr = csv.DictReader(fh)
        if list(rdr.fieldnames or []) != HOUSEKEEPING_COLS:
            raise Fail("housekeeping-log.csv: header must be " + ",".join(HOUSEKEEPING_COLS))
        return list(rdr)


def is_removal(old, new, field=None):
    """True if new is old with one stretch of text deleted (whitespace normalised), or new is OPEN
    (OPEN is refused for NO_OPEN_FIELDS, rule entry R-2026-10-25-A)."""
    ws = re.compile(r"\s+")
    o, n = ws.sub(" ", old or "").strip(), ws.sub(" ", new or "").strip()
    if n == "OPEN":
        return field not in NO_OPEN_FIELDS
    if n == o or len(n) >= len(o):
        return False
    p = 0
    while p < len(n) and n[p] == o[p]:
        p += 1
    rest = n[p:]
    if o.endswith(rest):
        return True
    # allow the space either side of the deleted stretch to collapse
    return any((o[:k] + o[j:]).replace("  ", " ").strip() == n for k in range(max(0, p - 1), p + 1)
               for j in range(k, len(o) + 1))


# --- One set of counts (correction of 25 October 2026). Every count printed on the page and in the
# README comes from count_states(); nothing else counts. Definitions, used everywhere:
#   promise: an entry that sets a test (every entry except one that records a result against an earlier entry)
#   open:    a promise that is LIVE, not scored, not replaced, whose scoring date is on or after the count date
#   due:     a promise that is LIVE, not scored, not replaced, whose scoring date is before the count date
PENDING = os.path.join(ROOT, "data", "scoring-pending.csv")
PENDING_COLS = ["id", "noted", "reason", "recheck_by"]
GRACE_DAYS = 1   # a result is normally entered on its scoring date; one day of grace before the guard stops a build
STATE_ORDER = ["PASS", "FAILED", "Recorded", "Open", "Due", "Replaced", "Proposed", "Repeating"]


def read_pending(path=PENDING):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as fh:
        rdr = csv.DictReader(fh)
        if list(rdr.fieldnames or []) != PENDING_COLS:
            raise Fail("scoring-pending.csv: header must be " + ",".join(PENDING_COLS))
        return list(rdr)


def _plain_date(s):
    m = re.fullmatch(r"(\d{1,2}) ([A-Z][a-z]{2}) (\d{4})", (s or "").strip())
    if not m:
        return None
    try:
        return _dt.datetime.strptime(m.group(0), "%d %b %Y").date()
    except ValueError:
        return None


def count_states(rows, iso):
    """Returns {"total", "promises", "scoring_entries", "state": {id: state}, "due_days": {id: days}}."""
    today = _dt.date.fromisoformat(iso)
    scorers, redated = {}, {}
    for r in rows:
        sup = r.get("supersedes_id", "").strip()
        if sup:
            (scorers if r["status"].upper().startswith("SCORED") else redated)[sup] = r
    scoring_ids = {r["id"] for r in scorers.values()}
    state, due_days = {}, {}
    for r in rows:
        rid, st = r["id"], r["status"].strip().upper()
        if rid in scoring_ids:
            continue
        if rid in redated:
            state[rid] = "Replaced"; continue
        res = scorers[rid]["status"].upper() if rid in scorers else (st if st.startswith("SCORED") else None)
        if res is not None:
            state[rid] = "PASS" if "PASS" in res else "FAILED" if "FAIL" in res else "Recorded"; continue
        if st == "PROPOSED":
            state[rid] = "Proposed"; continue
        d = _plain_date(r["scoring_date"])
        if d is None:
            try:
                sd = _dt.date.fromisoformat(r["sort_date"])
            except ValueError:
                sd = None
            if sd is None or sd.year == 9999:
                state[rid] = "Repeating"; continue
            d = sd
        if d < today:
            state[rid] = "Due"; due_days[rid] = (today - d).days
        else:
            state[rid] = "Open"
    n = len(state)
    if n + len(scoring_ids) != len(rows):
        raise Fail("COUNT MISMATCH: %d promises + %d scoring entries != %d entries" % (n, len(scoring_ids), len(rows)))
    return {"total": len(rows), "promises": n, "scoring_entries": len(scoring_ids), "state": state, "due_days": due_days}


def overdue_problems(rows, iso, pending=None):
    """Guard (25 October 2026): every promise past its scoring date and not scored must have a dated
    line in data/scoring-pending.csv, noted on or after its scoring date and with a recheck date not
    already passed. Returns a list of problems (empty when clean)."""
    pending = read_pending() if pending is None else pending
    c = count_states(rows, iso)
    byid = {r["id"]: r for r in rows}
    pmap = {}
    for p in pending:
        pmap.setdefault(p["id"], []).append(p)
    errs = []
    for p in pending:
        if p["id"] not in byid:
            errs.append("scoring-pending.csv: %s is not an entry" % p["id"])
        for k in ("noted", "recheck_by"):
            try:
                _dt.date.fromisoformat(p[k])
            except ValueError:
                errs.append("scoring-pending.csv: %s %s %r is not YYYY-MM-DD" % (p["id"], k, p[k]))
    for rid, days in sorted(c["due_days"].items()):
        if days <= GRACE_DAYS:
            continue
        sd = (_dt.date.fromisoformat(iso) - _dt.timedelta(days=days)).isoformat()
        ok = [p for p in pmap.get(rid, []) if p["noted"] >= sd and p["recheck_by"] >= iso and p["reason"].strip()]
        if not ok:
            errs.append("OVERDUE %s: scoring date %s passed %d days ago, not scored, no dated scoring-pending reason current on %s" % (rid, byid[rid]["scoring_date"], days, iso))
    return errs


def pending_reason(rid, iso, pending=None):
    pending = read_pending() if pending is None else pending
    ok = sorted([p for p in pending if p["id"] == rid and p["recheck_by"] >= iso], key=lambda p: p["noted"])
    return ok[-1] if ok else None
