"""Shared rules for the Citizen-Held Register pipeline. Standard library only."""
import csv, io, re, sys, os
from datetime import date, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "data", "entries.csv")
SECTION_ORDER = ["CANADA", "DESK", "WATCH", "RECORDED"]
SUBSCORE_COLS = ["hype_score", "means_score", "cost_score"]
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
