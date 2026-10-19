#!/usr/bin/env python3
"""Append one entry to data/entries.csv. Never edits or removes an existing row.

New commitment:
  python3 scripts/add_entry.py commit --id X --section CANADA --scoring-date "30 Nov 2026" \
      --test "PASS: ... FAILED: ..." --owner "..." --date-source "DESK-SET: ..." \
      [--measure URL] [--money ...] [--funding OPEN] [--argument URL]

New date for an existing test (the old entry stays):
  python3 scripts/add_entry.py redate --supersedes OLD --id NEW --scoring-date "15 Jan 2027" --date-source "..."

Scoring (a new dated entry; the scored entry stays unchanged):
  python3 scripts/add_entry.py score --supersedes OLD --result PASS|FAILED --scored-on 2026-10-30 \
      --evidence URL --cost-to-date "amount, source, URL, read DATE" or "FAILED: no public figure; held by ..." \
      --hype MATCHED --means OPEN --cost MIXED [--layer courts] [--id OLD-SCORED-20261030]

Put --dry-run before the subcommand to print the row without writing.
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import regcore as rc
import hash_entries as he

LAYERS = ["title", "courts", "regulation", "financing", "statute", "political choice"]


XFER_CAP = 5   # R-2026-10-19-B; change only with a dated public rule entry (R-2026-10-19-H)


def die(msg):
    print("ADD FAILED: " + msg, file=sys.stderr)
    sys.exit(1)


def append(header, rows, new, path, dry):
    for k in header:
        new.setdefault(k, "")
    extra = [k for k in new if k not in header]
    if extra:
        die("fields not in schema: %s" % extra)
    errs = rc.validate(header, rows + [new])
    if errs:
        die("\n".join(errs))
    if dry:
        print(he.canonical(new)); print("fingerprint", he.fingerprint(new)); return
    text = open(path, encoding="utf-8", newline="").read()
    if not text.endswith("\r\n"):
        die("source file does not end with a line break; refusing to append")
    line = rc.write_csv_text(header, [new]).split("\r\n", 1)[1]
    with open(path, "a", encoding="utf-8", newline="") as fh:
        fh.write(line)
    print("appended %s (fingerprint %s). Run scripts/preflight.sh next." % (new["id"], he.fingerprint(new)))


def add_subscore_columns(path):
    header, rows = rc.read_source(path)
    if all(c in header for c in rc.SUBSCORE_COLS):
        print("sub-score columns already present"); return
    header += [c for c in rc.SUBSCORE_COLS if c not in header]
    for r in rows:
        for c in rc.SUBSCORE_COLS:
            r[c] = r.get(c) or "OPEN"
    open(path, "w", encoding="utf-8", newline="").write(rc.write_csv_text(header, rows))
    print("added columns %s (OPEN on existing rows)" % rc.SUBSCORE_COLS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=rc.SOURCE)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--add-subscore-columns", action="store_true", help="schema change, Barry call: adds hype_score, means_score, cost_score")
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("commit")
    for f in ("id", "section", "scoring-date", "test", "owner", "date-source"):
        c.add_argument("--" + f, required=True)
    for f, d in (("measure", "OPEN"), ("money", "OPEN"), ("funding", "OPEN"), ("argument", "OPEN"), ("status", "LIVE")):
        c.add_argument("--" + f, default=d)
    r = sub.add_parser("redate")
    for f in ("supersedes", "id", "scoring-date", "date-source"):
        r.add_argument("--" + f, required=True)
    r.add_argument("--test")
    s = sub.add_parser("score")
    for f in ("supersedes", "result", "scored-on", "evidence", "cost-to-date", "hype", "means", "cost"):
        s.add_argument("--" + f, required=True)
    s.add_argument("--layer")
    s.add_argument("--id")
    a = ap.parse_args()

    if a.add_subscore_columns:
        add_subscore_columns(a.source)
        if not a.cmd: return
    if not a.cmd:
        ap.print_help(); sys.exit(1)
    header, rows = rc.read_source(a.source)
    byid = {x["id"]: x for x in rows}

    if a.cmd == "commit":
        try:
            iso = rc.parse_short(a.scoring_date)
        except ValueError:
            die("--scoring-date must look like '30 Nov 2026'")
        new = {"section": a.section, "sort_date": iso, "scoring_date": a.scoring_date, "id": a.id, "test": a.test,
               "owner": a.owner, "date_source": a.date_source, "status": a.status, "measure": a.measure,
               "money": a.money, "funding": a.funding, "argument": a.argument,
               "cost_to_date": "OPEN until scoring date %s" % a.scoring_date,
               "hype_score": "OPEN", "means_score": "OPEN", "cost_score": "OPEN"}
        if a.id in byid: die("id %s already exists" % a.id)
        if a.id.upper().startswith("XFER-"):
            closers = rc.closed_by(rows)
            open_x = [r["id"] for r in rows if r["id"].upper().startswith("XFER-") and r["status"] == "LIVE"
                      and r["id"] not in closers and not rc.is_resolved(r)]
            if len(open_x) >= XFER_CAP:
                die("transfer cap: %d open transfer entries (%s); the cap of %d (rule entry B of 19 October 2026) is raised only by a new dated public rule entry (R-2026-10-19-H)" % (len(open_x), ", ".join(open_x), XFER_CAP))
        append(header, rows, new, a.source, a.dry_run)

    elif a.cmd == "redate":
        old = byid.get(a.supersedes) or die("no entry %s" % a.supersedes)
        if a.id in byid: die("id %s already exists" % a.id)
        iso = rc.parse_short(a.scoring_date)
        new = dict(old)
        new.update({"id": a.id, "scoring_date": a.scoring_date, "sort_date": iso, "date_source": a.date_source,
                    "status": "LIVE", "cost_to_date": "OPEN until scoring date %s" % a.scoring_date,
                    "supersedes_id": old["id"], "supersedes_hash": he.fingerprint(old)})
        for k in rc.SUBSCORE_COLS:
            new[k] = "OPEN"
        if a.test: new["test"] = a.test
        append(header, rows, new, a.source, a.dry_run)

    elif a.cmd == "score":
        old = byid.get(a.supersedes) or die("no entry %s" % a.supersedes)
        if rc.is_resolved(old): die("%s is itself a scoring entry" % old["id"])
        if any(x.get("supersedes_id") == old["id"] and rc.is_resolved(x) for x in rows):
            die("%s already has a scoring entry" % old["id"])
        if a.result not in ("PASS", "FAILED"): die("--result must be PASS or FAILED")
        for k in ("hype", "means", "cost"):
            if getattr(a, k) not in rc.SUBSCORE_VALUES: die("--%s must be MATCHED, MIXED, FAILED or OPEN" % k)
        if a.result == "FAILED" and not a.layer:
            die("a FAILED entry names the blocking layer (--layer: %s, or another layer named in full)" % ", ".join(LAYERS))
        if not a.evidence.startswith("http"): die("--evidence must be a URL")
        if a.cost_to_date.upper().startswith("OPEN"): die("on the scoring date cost to date is a sourced figure or FAILED, never OPEN")
        if not all(c in header for c in rc.SUBSCORE_COLS):
            die("schema has no sub-score columns. Barry call: rerun with --add-subscore-columns (adds %s)" % rc.SUBSCORE_COLS)
        d = rc.short_date(a.scored_on)
        status = "SCORED %s: %s" % (d, a.result) + (" (blocking layer: %s)" % a.layer if a.layer else "")
        new = dict(old)
        new.update({"id": a.id or "%s-SCORED-%s" % (old["id"], a.scored_on.replace("-", "")), "status": status,
                    "measure": a.evidence, "cost_to_date": a.cost_to_date, "hype_score": a.hype,
                    "means_score": a.means, "cost_score": a.cost, "sort_date": max(old["sort_date"], a.scored_on),
                    "supersedes_id": old["id"], "supersedes_hash": he.fingerprint(old)})
        if new["id"] in byid: die("id %s already exists" % new["id"])
        append(header, rows, new, a.source, a.dry_run)


if __name__ == "__main__":
    main()
