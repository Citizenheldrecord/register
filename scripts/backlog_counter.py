#!/usr/bin/env python3
"""Count where the public register stands, from its canonical data file.

Every number comes from regcore.count_states(), the one counter the page and README use.
Usage: backlog_counter.py [entries.csv] [YYYY-MM-DD count date]
Prints a markdown block for the public page.
"""
import csv, os, sys, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import regcore as rc

SECTION_NAMES = {"CANADA": "Canadian files", "DESK": "This desk's own commitments",
                 "WATCH": "Outside files we watch", "RECORDED": "Recorded facts and checkpoints"}


def block(rows, iso, pending=None):
    c = rc.count_states(rows, iso)
    st, dd = c["state"], c["due_days"]
    ids = lambda s: sorted(i for i, v in st.items() if v == s)
    n = {s: len(ids(s)) for s in rc.STATE_ORDER}
    d = datetime.date.fromisoformat(iso)
    o = ["## Where the register stands", "",
         "Counted on %d %s from data/entries.csv, which holds %d entries." % (d.day, d.strftime("%B %Y"), c["total"]), "",
         "Definitions used for every count on this page. A promise is an entry that sets a test. A scoring entry records a result against an earlier promise. Open: live, not scored, scoring date on or after the count date. Due: live, not scored, scoring date before the count date.", "",
         "- **Entries:** %d = %d promises + %d scoring entries." % (c["total"], c["promises"], c["scoring_entries"]),
         "- **Scored PASS:** %d%s" % (n["PASS"], " (%s)." % ", ".join(ids("PASS")) if n["PASS"] else "."),
         "- **Scored FAILED:** %d%s" % (n["FAILED"], " (%s)." % ", ".join(ids("FAILED")) if n["FAILED"] else "."),
         "- **Recorded as fact, with no pass or fail line:** %d%s" % (n["Recorded"], " (%s)." % ", ".join(ids("Recorded")) if n["Recorded"] else "."),
         "- **Open:** %d." % n["Open"]]
    if dd:
        parts = []
        for rid, k in sorted(dd.items(), key=lambda x: (-x[1], x[0])):
            pr = rc.pending_reason(rid, iso, pending)
            parts.append("%s, %d day%s past its date%s" % (rid, k, "" if k == 1 else "s",
                         ("; scoring pending, noted %s: %s" % (rc.long_date(pr["noted"]), pr["reason"].rstrip("."))) if pr else ""))
        o.append("- **Due:** %d (%s)." % (n["Due"], "; ".join(parts)))
    else:
        o.append("- **Due:** 0.")
    over = [r for r, k in dd.items() if k > 14]
    o.append("- **More than 14 days past due:** %d. %s" % (len(over), "No new promises are added until these are scored." if over else "New promises can be added."))
    o.append("- **Replaced by a later entry (a new date or a correction):** %d%s The old entry stays in the record; its newer entry is counted above." % (n["Replaced"], " (%s)." % ", ".join(ids("Replaced")) if n["Replaced"] else "."))
    o.append("- **Proposed, not yet live:** %d%s" % (n["Proposed"], " (%s)." % ", ".join(ids("Proposed")) if n["Proposed"] else "."))
    o.append("- **Repeating, with no single scoring day:** %d%s" % (n["Repeating"], " (%s)." % ", ".join(ids("Repeating")) if n["Repeating"] else "."))
    o += ["", "Check: %d promises = %s." % (c["promises"], " + ".join("%d %s" % (n[s], s.lower() if s not in ("PASS", "FAILED") else s) for s in rc.STATE_ORDER)), "",
          "By section of the data file (every entry counted once; the four sections add up to all %d entries):" % c["total"], "",
          "| Section | Entries | Scoring entries | Promises | " + " | ".join(rc.STATE_ORDER) + " |",
          "|---" * (len(rc.STATE_ORDER) + 4) + "|"]
    tot = [0] * (len(rc.STATE_ORDER) + 3)
    for s in rc.SECTION_ORDER:
        rs = [r for r in rows if r["section"] == s]
        pr = [r["id"] for r in rs if r["id"] in st]
        vals = [len(rs), len(rs) - len(pr), len(pr)] + [sum(1 for i in pr if st[i] == k) for k in rc.STATE_ORDER]
        tot = [a + b for a, b in zip(tot, vals)]
        o.append("| %s | " % SECTION_NAMES[s] + " | ".join(map(str, vals)) + " |")
    o.append("| Total | " + " | ".join(map(str, tot)) + " |")
    if tot[0] != c["total"] or tot[2] != c["promises"] or sum(n.values()) != c["promises"]:
        raise rc.Fail("COUNT MISMATCH in the count block: sections %d/%d, states %d, promises %d" % (tot[0], tot[2], sum(n.values()), c["promises"]))
    return "\n".join(o), c


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else rc.SOURCE
    iso = sys.argv[2] if len(sys.argv) > 2 else datetime.date.today().isoformat()
    rows = list(csv.DictReader(open(path, encoding="utf-8", newline="")))
    try:
        print(block(rows, iso)[0])
    except rc.Fail as e:
        sys.stderr.write(str(e) + "\n"); return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
