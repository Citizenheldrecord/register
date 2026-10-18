#!/usr/bin/env python3
"""Entry fingerprints for the Citizen-Held Register (rule entry of 18 Oct 2026, Rule A).

Reads the register CSV, builds the canonical text of every entry and prints or
writes a manifest of SHA-256 fingerprints. Standard library only.

Canonical text. Current layout chr-entry-v2 (rule entry R-2026-10-18-C); chr-entry-v1
(rule entry R-2026-10-18-A) is kept so the 18 Oct v1 manifest can still be checked.
Layout v2 is identical to v1 except for the tag and three extra fields at the end:
hype_score, means_score, cost_score.
  1. Line 1 is the literal layout tag: chr-entry-v2 (or chr-entry-v1)
  2. Then one line per field, in exactly this order:
       id, section, scoring_date, sort_date, test, owner, date_source, status,
       measure, money, funding, argument, cost_to_date, supersedes_id, supersedes_hash
     and, in chr-entry-v2 only, then: hype_score, means_score, cost_score
     Each line is the field name, "=", then the value.
  3. A field missing from the data file is an empty value.
  4. Each value is Unicode NFC normalised; every run of whitespace (space, tab,
     carriage return, line feed, no-break space and other Unicode whitespace) is
     replaced by one space; leading and trailing whitespace is removed.
  5. Lines are joined with a single line feed (0x0A). No trailing line feed.
  6. The text is encoded as UTF-8 without a byte order mark.
  7. The fingerprint is the SHA-256 of those bytes, written as 64 lowercase hex characters.

Usage:
  python3 scripts/hash_entries.py DATA.csv [--date YYYY-MM-DD] [--out MANIFEST.csv]
  python3 scripts/hash_entries.py DATA.csv --show ID      (print one entry's canonical text)
  python3 scripts/hash_entries.py DATA.csv --check MANIFEST.csv
"""
import argparse, csv, hashlib, re, sys, unicodedata

FIELDS_V1 = ["id", "section", "scoring_date", "sort_date", "test", "owner",
             "date_source", "status", "measure", "money", "funding", "argument",
             "cost_to_date", "supersedes_id", "supersedes_hash"]
# chr-entry-v2 (rule entry R-2026-10-18-C): v1 fields, then the three sub-scores.
FIELDS_V2 = FIELDS_V1 + ["hype_score", "means_score", "cost_score"]
LAYOUTS = {"chr-entry-v1": FIELDS_V1, "chr-entry-v2": FIELDS_V2}
VERSION = "chr-entry-v2"          # current layout
FIELDS = FIELDS_V2
WS = re.compile(r"\s+", re.UNICODE)


def norm(value):
    value = unicodedata.normalize("NFC", value or "")
    return WS.sub(" ", value).strip()


def canonical(row, version=None):
    version = version or VERSION
    lines = [version] + ["%s=%s" % (f, norm(row.get(f, ""))) for f in LAYOUTS[version]]
    return "\n".join(lines)


def fingerprint(row, version=None):
    return hashlib.sha256(canonical(row, version).encode("utf-8")).hexdigest()


def manifest_version(path):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("# canonical_version:"):
                return line.split(":", 1)[1].strip()
    return "chr-entry-v1"


def file_sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def load(path):
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    ids = [r.get("id", "") for r in rows]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        sys.exit("duplicate ids: " + ", ".join(dupes))
    if any(not norm(i) for i in ids):
        sys.exit("an entry has no id")
    return rows


def manifest_text(path, rows, date, version=None):
    version = version or VERSION
    out = ["# Citizen-Held Register entry fingerprints",
           "# canonical_version: " + version,
           "# manifest_date: " + date,
           "# source_file: " + path.split("/")[-1],
           "# source_file_sha256: " + file_sha256(path),
           "# entries: %d" % len(rows),
           "manifest_date,id,section,scoring_date,entry_sha256,supersedes_id,supersedes_hash"]
    for r in rows:
        out.append(",".join([date, norm(r["id"]), norm(r.get("section", "")),
                             '"%s"' % norm(r.get("scoring_date", "")), fingerprint(r, version),
                             norm(r.get("supersedes_id", "")), norm(r.get("supersedes_hash", ""))]))
    return "\n".join(out) + "\n"


def check(path, rows, manifest):
    version = manifest_version(manifest)
    want = {}
    with open(manifest, encoding="utf-8") as fh:
        body = [l for l in fh if not l.startswith("#")]
    for rec in csv.DictReader(body):
        want[rec["id"]] = rec["entry_sha256"]
    bad = 0
    for r in rows:
        got, exp = fingerprint(r, version), want.get(r["id"])
        if exp is None:
            print("NEW      %s %s" % (r["id"], got)); continue
        if got != exp:
            bad += 1; print("CHANGED  %s manifest %s now %s" % (r["id"], exp, got))
    for i in sorted(set(want) - {r["id"] for r in rows}):
        bad += 1; print("MISSING  %s (append only: an entry may not disappear)" % i)
    print("checked %d entries against %s (%s), %d problems" % (len(rows), manifest.split("/")[-1], version, bad))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("--date", default=None)
    ap.add_argument("--out")
    ap.add_argument("--show")
    ap.add_argument("--check")
    ap.add_argument("--layout", choices=sorted(LAYOUTS), default=VERSION)
    a = ap.parse_args()
    rows = load(a.data)
    if a.show:
        r = [x for x in rows if x["id"] == a.show]
        if not r: sys.exit("no such id")
        sys.stdout.write(canonical(r[0], a.layout)); return 0
    if a.check:
        return check(a.data, rows, a.check)
    if not a.date:
        sys.exit("--date YYYY-MM-DD is required (the update date, never inferred)")
    text = manifest_text(a.data, rows, a.date, a.layout)
    if a.out:
        with open(a.out, "w", encoding="utf-8", newline="\n") as fh: fh.write(text)
        print("wrote %s (%d entries), manifest sha256 %s" % (a.out, len(rows), file_sha256(a.out)))
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
