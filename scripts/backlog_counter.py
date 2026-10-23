#!/usr/bin/env python3
"""Count where the public register stands, from its canonical data file.

Reads data/entries.csv of the register staging copy (the file the public
page and CSV are built from). Every number printed comes from that file.
Usage: backlog_counter.py [entries.csv] [YYYY-MM-DD as-of date]
Prints a markdown block for the public page, then (on stderr) parse notes.
"""
import csv, sys, re, datetime, pathlib, collections

DEFAULT = "/workspace/register-staging-2026-10-22-display/data/entries.csv"
MONTHS = {m: i for i, m in enumerate(
    "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}

def plain_date(s):
    """Return a date if scoring_date is exactly 'D Mon YYYY', else None."""
    m = re.fullmatch(r"(\d{1,2}) ([A-Z][a-z]{2}) (\d{4})", s.strip())
    if not m or m.group(2) not in MONTHS:
        return None
    return datetime.date(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1)))

def main():
    path = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT)
    today = (datetime.date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2
             else datetime.date.today())
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    by_id = {r["id"]: r for r in rows}
    notes = []

    score_entries = {}   # scored id -> scoring entry
    redated = {}         # old id -> new id
    for r in rows:
        sup = r["supersedes_id"].strip()
        if not sup:
            continue
        if r["status"].upper().startswith("SCORED"):
            score_entries[sup] = r
        else:
            redated[sup] = r["id"]
        if sup not in by_id:
            notes.append(f"{r['id']} cites {sup}, which is not in the file")

    tests = [r for r in rows if r["id"] not in {e["id"] for e in score_entries.values()}]
    passed, failed, recorded, proposed, replaced = [], [], [], [], []
    open_future, due, unparsed = [], [], []

    for r in tests:
        rid, st = r["id"], r["status"].strip()
        if rid in redated:
            replaced.append(rid); continue
        result = None
        if rid in score_entries:
            result = score_entries[rid]["status"]
        elif st.upper().startswith("SCORED"):
            result = st
        if result is not None:
            u = result.upper()
            if "PASS" in u: passed.append(rid)
            elif "FAIL" in u: failed.append(rid)
            else: recorded.append(rid)
            continue
        if st.upper() == "PROPOSED":
            proposed.append(rid); continue
        if st.upper() != "LIVE":
            unparsed.append((rid, f"status {st!r} not recognised")); continue
        d = plain_date(r["scoring_date"])
        if d is None:
            try:
                sd = datetime.date.fromisoformat(r["sort_date"])
            except ValueError:
                sd = None
            if sd is None or sd.year == 9999:
                unparsed.append((rid, f"scoring date {r['scoring_date']!r} has no single fixed day"))
                continue
            notes.append(f"{rid}: scoring date {r['scoring_date']!r} read as sort date {sd}")
            d = sd
        if d < today:
            due.append((rid, (today - d).days, d))
        else:
            open_future.append(rid)

    due.sort(key=lambda x: -x[1])
    total = len(rows)
    n_tests = len(tests)
    out = []
    out.append("## Where the register stands")
    out.append("")
    out.append(f"Counted on {today.day} {today.strftime('%B %Y')} from the register's data file, which holds {total} entries.")
    out.append("")
    k = total - n_tests
    out.append(f"- **Promises entered:** {n_tests}. " + ("One further entry records a result against an earlier promise." if k == 1 else f"{k} further entries record results against earlier promises."))
    out.append(f"- **Scored PASS:** {len(passed)}" + (f" ({', '.join(passed)})." if passed else "."))
    out.append(f"- **Scored FAILED:** {len(failed)}" + (f" ({', '.join(failed)})." if failed else "."))
    if recorded:
        out.append(f"- **Recorded as fact, with no pass or fail line:** {len(recorded)} ({', '.join(recorded)}).")
    out.append(f"- **Open and not yet due:** {len(open_future)}.")
    if due:
        lst = "; ".join(f"{rid}, {n} day{'s' if n != 1 else ''} past its date" for rid, n, _ in due)
        out.append(f"- **Due or past due and not yet scored:** {len(due)} ({lst}).")
    else:
        out.append("- **Due or past due and not yet scored:** 0.")
    over14 = [x for x in due if x[1] > 14]
    out.append(f"- **More than 14 days past due:** {len(over14)}. "
               + ("No new promises are added until these are scored." if over14
                  else "New promises can be added."))
    if replaced:
        out.append(f"- **Replaced by a later entry (a new date or a correction):** {len(replaced)} ({', '.join(replaced)}). The old entry stays in the record; its newer entry is counted above.")
    if proposed:
        out.append(f"- **Proposed, not yet live:** {len(proposed)} ({', '.join(proposed)}).")
    if unparsed:
        out.append(f"- **Repeating, with no single scoring day:** {len(unparsed)} ({', '.join(r for r, _ in unparsed)}).")
    out.append("")
    check = len(passed) + len(failed) + len(recorded) + len(open_future) + len(due) + len(replaced) + len(proposed) + len(unparsed)
    out.append(f"These lines add up to the {n_tests} promises entered.")
    if check != n_tests:
        notes.append(f"COUNT MISMATCH: categories sum to {check}, tests {n_tests}")
    # per display section (display only; reads the groups file, never changes entries)
    gpath = pathlib.Path(sys.argv[3]) if len(sys.argv) > 3 else None
    if gpath is None:
        import glob
        c = sorted(glob.glob(str(pathlib.Path(__file__).resolve().parent.parent / "register-display" / "display-groups-*.csv")))
        gpath = pathlib.Path(c[-1]) if c else None
    if gpath is not None:
        grp = {r["id"]: r["display_group"] for r in csv.DictReader(gpath.open(encoding="utf-8"))}
        cat = {}
        for lst, name in ((passed, "PASS"), (failed, "FAILED"), (recorded, "Recorded"), (open_future, "Open"),
                          ([x[0] for x in due], "Due"), (replaced, "Replaced"), (proposed, "Proposed"),
                          ([x[0] for x in unparsed], "Repeating")):
            for rid in lst: cat[rid] = name
        cols = ["PASS", "FAILED", "Recorded", "Open", "Due", "Replaced", "Proposed", "Repeating"]
        names = {"government_promise": "Government promises", "also_watched": "Also watched", "recorded": "Recorded entries"}
        out.append("")
        out.append("By section:")
        out.append("")
        out.append("| Section | Promises | " + " | ".join(cols) + " |")
        out.append("|---" * (len(cols) + 2) + "|")
        tot = 0
        for gk in ("government_promise", "also_watched", "recorded"):
            ids = [t["id"] for t in tests if grp.get(t["id"]) == gk]
            tot += len(ids)
            out.append(f"| {names[gk]} | {len(ids)} | " + " | ".join(str(sum(1 for i in ids if cat.get(i) == c)) for c in cols) + " |")
        missing = [t["id"] for t in tests if t["id"] not in grp]
        if missing or tot != n_tests:
            notes.append(f"SECTION MISMATCH: {tot} of {n_tests} promises grouped; ungrouped {missing}")
        sys.stderr.write(f"groups: {gpath}\n")
    print("\n".join(out))
    sys.stderr.write(f"source: {path}\n")
    for rid, why in unparsed:
        sys.stderr.write(f"UNPARSED {rid}: {why}\n")
    for n in notes:
        sys.stderr.write(f"NOTE {n}\n")
    return 0

if __name__ == "__main__":
    sys.exit(main())
