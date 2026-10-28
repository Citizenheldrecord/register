#!/usr/bin/env python3
"""Sources record check (staging only).

For every register row in <staging>/data/entries.csv, read <staging>/sources/<ROW-ID>.md,
count source blocks that count, derive a status and compare it with the status the row claims.

A block counts only if Primary URL, Exact supporting line and Read date are all filled and
Supports starts with "full" or "partial". Anything under "Leads (not sources)" never counts.

Claim coverage: the record header "Claim coverage: full|partial"; absent means partial.

Derived status: SOURCED (coverage full AND >=1 full block), PARTLY SOURCED (any counting
block otherwise),
UNSOURCED (no counting block), MISSING RECORD (no file).

RULE A (Barry go 27 Oct 2026 14:46 CST): SECONDARY-SOURCED sits between SOURCED and PARTLY
SOURCED. A block with "Supports: full (secondary)" is a secondary block (a named outlet read
against the row; the outlet is the block's "Outlet:" field, else its Publisher). It counts only
when no full primary block exists, the record carries a "Primary search:" line (date and what
was looked for), and the row text in data/entries.csv carries "as reported by <outlet>" or
"per <outlet> (secondary)". Otherwise the row is a FAIL (LABEL MISSING / NO PRIMARY SEARCH) and
derives from its primary blocks only. A secondary block never changes a score. Rows whose
Primary search date is more than 30 days before --audit-date are listed as STALE SECONDARY.

Claimed status: the record's own "Status:" header, plus an optional --claims CSV
(columns id,claimed_status) for any status shown on a page.

Exit 1 if any row claims more than its derived status, or any row has no record file.
--report-only always exits 0. Reads only; never edits rows or uploads anything.

FAILED ENTRY FIELDS (Barry go 27 Oct 2026 15:01 CST): every dated
entry in data/entries.csv whose status reads "SCORED <date>: FAILED" must carry five fields:
  1 Required / record on scoring date   2 Why still live   3 Accountable
  4 Closing document or promise (a URL with a quoted line, or "none on record")
  5 Next check (a YYYY-MM-DD date plus a follow-up row ID present in entries.csv, or "quarterly recheck")
The frozen entry is never edited (fill-once), so the fields live in append-only dated lines in
<staging>/sources/failed/<ENTRY-ID>.md, each line headed "## Line YYYY-MM-DD" (template:
sources/_FAILED_TEMPLATE.md). Fields are read across all lines; a later line may add a field, never
remove one. An entry missing any field, or with an empty, TBD or READ PENDING value, is FAILED ENTRY
INCOMPLETE; this blocks (exit 1) like an over-claim unless --report-only.
(Rule locked: Barry approval 27 Oct 2026 15:17 CST.)

HARD GATE (Barry approval 27 Oct 2026 15:17 CST; reports/HARD-GATE-PROPOSAL-2026-10-27.md, option 1).
With --allowlist <csv> (columns id,level,reason_class,primary_search_date,expires,renewals,listed)
every row below SECONDARY-SOURCED (UNSOURCED or PARTLY SOURCED) blocks unless it is on the list and
the entry is valid on --audit-date: not past "expires", listed on or before the gate date 2026-10-27
(new rows are never allow-listed), expires no later than 30 days after listing or renewal, and
renewals is 0, or 1 only for reason class "no primary exists yet" with a primary_search_date after
2026-10-27. A row with no record (MISSING RECORD) always blocks (record-before-entry). Over-claims,
LABEL MISSING, NO PRIMARY SEARCH and FAILED ENTRY INCOMPLETE are never allow-listed and always block.
The ids that may ever be allow-listed are frozen in data/sources-gate-allowlist-seed-2026-10-27.txt
(the rows failing on 27 Oct 2026); its SHA-256 is fixed below, so a changed seed or an id not in it blocks.
Removal from the allow-list is append-only: an id listed in any data/sources-gate-allowlist-removed-YYYY-MM-DD.csv
(columns id,removed,reason) is treated as not on the allow-list from its "removed" date and can never return.
The seed is never edited.

PROMISE SOURCED, OUTCOME PENDING (Barry go 27 Oct 2026 15:50 CST). A forward test cannot have outcome
evidence before its scoring date. A record headed "Claim coverage: promise full, outcome pending" derives
PROMISE SOURCED, OUTCOME PENDING only when (1) the promise or premise is backed by a full primary block, or by a
secondary block that passes RULE A (Primary search line and the row label); (2) the row's scoring date in
data/entries.csv (first "D Mon YYYY" date) is after --audit-date; (3) the row's test states both PASS and FAILED;
(4) the row is not yet scored. Otherwise it derives from its blocks as usual (a record whose Status claims the level
then over-claims). The level expires at the scoring date: from that date a row still not scored is a fail
(SCORING DATE PASSED, NOT SCORED) that blocks and is never allow-listed; a scored row derives
PROMISE SOURCED, OUTCOME SCORED, and a FAILED score needs its five-field entry as above. Both levels pass the gate,
so new forward rows pass. --selftest runs the forward-row fixtures (the build runs it on every build).
"""
import argparse, csv, os, re, sys

PROMISE = "PROMISE SOURCED, OUTCOME PENDING"
PROMISE_SCORED = "PROMISE SOURCED, OUTCOME SCORED"
RANK = {"MISSING RECORD": 0, "UNSOURCED": 0, "PARTLY SOURCED": 1, PROMISE: 1.5, PROMISE_SCORED: 1.5, "SECONDARY-SOURCED": 2, "SOURCED": 3}
CLAIM_MAP = {"SOURCED": "SOURCED", "PARTIAL": "PARTLY SOURCED", "PARTLY SOURCED": "PARTLY SOURCED",
             "NOT FOUND": "UNSOURCED", "UNSOURCED": "UNSOURCED",
             "SECONDARY-SOURCED": "SECONDARY-SOURCED", "SECONDARY SOURCED": "SECONDARY-SOURCED",
             PROMISE: PROMISE, "PROMISE SOURCED": PROMISE, PROMISE_SCORED: PROMISE_SCORED}
DMY = re.compile(r"\b(\d{1,2}) (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* (\d{4})\b")

def scoring_date(v):
    import datetime
    m = DMY.search(v or "")
    if not m:
        return None
    return datetime.datetime.strptime("%s %s %s" % m.groups(), "%d %b %Y").date()
EMPTY = {"", "-", "none", "n/a", "tbd", "open"}

def field(block, name):
    m = re.search(r"^- " + re.escape(name) + r"[^:\n]*:[ \t]*(.*)$", block, re.M)
    return m.group(1).strip() if m else ""

def filled(v):
    return v.strip().strip('"').strip().lower() not in EMPTY

def parse_record(text):
    m = re.search(r"^Status:\s*(.+)$", text, re.M)
    claimed = m.group(1).strip().upper() if m else ""
    m = re.search(r"^Claim coverage:\s*(full|partial)\b", text, re.M | re.I)
    coverage = m.group(1).lower() if m else "partial"
    if re.search(r"^Claim coverage:\s*promise full,\s*outcome pending\b", text, re.M | re.I):
        coverage = "promise"
    # Leads section and everything after it is excluded
    body = re.split(r"^##\s+Leads\b.*$", text, maxsplit=1, flags=re.M)[0]
    blocks = re.split(r"^##\s+Source\b.*$", body, flags=re.M)[1:]
    m = re.search(r"^Primary search:[ \t]*(.*)$", text, re.M)
    psearch = m.group(1).strip() if m and filled(m.group(1)) else ""
    full = partial = 0
    outlets = []
    for b in blocks:
        b = re.split(r"^##\s", b, maxsplit=1, flags=re.M)[0]
        if not (filled(field(b, "Primary URL")) and filled(field(b, "Exact supporting line"))
                and filled(field(b, "Read date"))):
            continue
        sup = field(b, "Supports").lower()
        if sup.startswith("full") and "secondary" in sup:
            outlets.append(field(b, "Outlet") or field(b, "Publisher"))
        elif sup.startswith("full"):
            full += 1
        elif sup.startswith("partial"):
            partial += 1
    return claimed, coverage, len(blocks), full, partial, outlets, psearch

SEED_SHA256 = "df475255ab9c359f2cacb71354330a2bade6f2d6d65d3641457328f803bbd9e1"   # data/sources-gate-allowlist-seed-2026-10-27.txt, 177 ids, frozen 27 Oct 2026

FAILED_FIELDS = [("1", "Required / record on scoring date"), ("2", "Why still live"), ("3", "Accountable"),
                 ("4", "Closing document or promise"), ("5", "Next check")]
FAILED_STATUS = re.compile(r"^\s*SCORED\b[^:]*:\s*FAILED\b", re.I)
PENDING = re.compile(r"^\s*(tbd|read pending|pending|open|none|-|n/a)?\s*\.?\s*$", re.I)

def failed_entry_gaps(fid, text, ids):
    """Return the list of missing field numbers (with reason) for one FAILED entry record text."""
    vals = {}
    for line in re.split(r"^##\s+Line\b.*$", text or "", flags=re.M)[1:]:
        for num, label in FAILED_FIELDS:
            m = re.search(r"^-\s*" + num + r"\.?\s*" + re.escape(label) + r"[^:\n]*:[ \t]*(.*)$", line, re.M | re.I)
            if m and not PENDING.match(m.group(1)):
                vals[num] = vals.get(num, "") + " " + m.group(1).strip()
    gaps = []
    for num, label in FAILED_FIELDS:
        v = vals.get(num, "").strip()
        if not v:
            gaps.append(num)
        elif num == "4" and not (re.search(r"https?://", v) or "none on record" in v.lower()):
            gaps.append("4 (no URL and not 'none on record')")
        elif num == "5":
            has_date = re.search(r"\d{4}-\d{2}-\d{2}", v)
            has_link = "quarterly recheck" in v.lower() or any(re.search(r"(?<![\w-])" + re.escape(i) + r"(?![\w-])", v) for i in ids if i != fid)
            if not (has_date and has_link):
                gaps.append("5 (needs a date and a follow-up row ID or 'quarterly recheck')")
    return gaps

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--staging", default="/workspace/register-staging-2026-10-22-display")
    ap.add_argument("--claims", help="optional CSV id,claimed_status (status shown on a page)")
    ap.add_argument("--report", help="write Markdown report (with CSV block) here")
    ap.add_argument("--counts-out", help="write date,sourced,partly_sourced,unsourced,missing_record,rows CSV (read by the build for the page note)")
    ap.add_argument("--counts-date", help="build date YYYY-MM-DD for --counts-out (default today)")
    ap.add_argument("--audit-date", help="YYYY-MM-DD for the 30 day stale-secondary check (default today)")
    ap.add_argument("--report-only", action="store_true", help="never fail; show the full picture")
    ap.add_argument("--allowlist", help="hard gate: CSV of currently failing rows allowed until their expiry")
    ap.add_argument("--selftest", action="store_true", help="run the forward-row gate fixtures and exit")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest(a.staging)

    with open(os.path.join(a.staging, "data", "entries.csv"), newline="") as f:
        rowtext = {}
        for r in csv.DictReader(f):
            rowtext[r["id"]] = rowtext.get(r["id"], "") + " " + " ".join(v or "" for v in r.values())
        ids = list(rowtext)
    with open(os.path.join(a.staging, "data", "entries.csv"), newline="") as f:
        meta = {}
        for r in csv.DictReader(f):
            meta.setdefault(r["id"], r)
        failed_ids = [i for i, r in meta.items() if FAILED_STATUS.match(r.get("status", ""))]
        # 28 Oct 2026 (Barry go pt2242u): the register is append-only, so a forward row is scored by a later SCORED
        # entry that supersedes it; the original row's own status never changes. Count both.
        scored_by = {(r.get("supersedes_id") or "").strip() for r in meta.values()
                     if (r.get("status") or "").strip().upper().startswith("SCORED") and (r.get("supersedes_id") or "").strip()}
    extra = {}
    if a.claims:
        with open(a.claims, newline="") as f:
            extra = {r["id"]: r["claimed_status"].strip().upper() for r in csv.DictReader(f)}
    src = os.path.join(a.staging, "sources")
    orphans = sorted(fn[:-3] for fn in os.listdir(src)
                     if fn.endswith(".md") and not fn.startswith("_") and fn[:-3] not in ids)

    import datetime
    today = datetime.date.fromisoformat(a.audit_date) if a.audit_date else datetime.date.today()
    rows, fails, stale = [], [], []
    for rid in ids:
        p = os.path.join(src, rid + ".md")
        if not os.path.exists(p):
            derived, claimed, cov, nb, fu, pa, outs, ps = "MISSING RECORD", "", "", 0, 0, 0, [], ""
        else:
            claimed, cov, nb, fu, pa, outs, ps = parse_record(open(p, encoding="utf-8").read())
            derived = "SOURCED" if (fu and cov == "full") else "PARTLY SOURCED" if (fu or pa) else "UNSOURCED"
        sec_fail = ""
        if outs and derived != "SOURCED":
            low = re.sub(r"\s+", " ", rowtext.get(rid, "")).lower()
            labelled = all(("as reported by " + o.lower()) in low or ("per " + o.lower() + " (secondary)") in low for o in outs if o)
            if not ps:
                sec_fail = "NO PRIMARY SEARCH"
            if not labelled:
                sec_fail = (sec_fail + "; " if sec_fail else "") + "LABEL MISSING (" + ", ".join(outs) + ")"
            if not sec_fail:
                derived = "SECONDARY-SOURCED"
                m = re.search(r"\d{4}-\d{2}-\d{2}", ps)
                if not m or (today - datetime.date.fromisoformat(m.group(0))).days > 30:
                    stale.append((rid, ps))
        reason = sec_fail
        if cov == "promise" and derived != "MISSING RECORD":
            r0 = meta.get(rid, {})
            sd = scoring_date(r0.get("scoring_date", ""))
            test = r0.get("test", "")
            scored = (r0.get("status", "").strip().upper().startswith("SCORED")) or rid in scored_by
            backed = fu > 0 or derived == "SECONDARY-SOURCED"
            if backed and sd and re.search(r"\bPASS\b", test) and re.search(r"\bFAIL", test):
                if scored:
                    derived = PROMISE_SCORED
                elif sd > today:
                    derived = PROMISE
                else:
                    reason = (reason + "; " if reason else "") + "SCORING DATE PASSED, NOT SCORED (%s; promise-sourced level expired)" % sd.isoformat()
        claims = [c for c in (claimed, extra.get(rid, "")) if c]
        if derived == "MISSING RECORD":
            reason = "no record file"
        for c in claims:
            norm = CLAIM_MAP.get(c)
            if norm is None:
                reason = (reason + "; " if reason else "") + "unknown claimed status " + c
            elif RANK[norm] > RANK[derived]:
                reason = (reason + "; " if reason else "") + "claims %s, derived %s" % (norm, derived)
        rows.append((rid, " / ".join(claims), derived, cov, nb, fu, pa, reason))
        if reason:
            fails.append((rid, reason))

    fdir = os.path.join(src, "failed")
    failed_rows = []
    for fid in failed_ids:
        fp = os.path.join(fdir, fid + ".md")
        gaps = failed_entry_gaps(fid, open(fp, encoding="utf-8").read() if os.path.exists(fp) else "", ids)
        failed_rows.append((fid, "yes" if os.path.exists(fp) else "no", "; ".join(gaps)))
    incomplete = [(fid, g) for fid, _, g in failed_rows if g]

    gate = []
    if a.allowlist:
        GATE_DATE = datetime.date(2026, 10, 27)
        seed_p = os.path.join(os.path.dirname(os.path.abspath(a.allowlist)), "sources-gate-allowlist-seed-2026-10-27.txt")
        seed_b = open(seed_p, "rb").read() if os.path.exists(seed_p) else b""
        import hashlib
        seed_ok = hashlib.sha256(seed_b).hexdigest() == SEED_SHA256
        seed = set(seed_b.decode("utf-8").split()) if seed_ok else set()
        if not seed_ok:
            gate.append(("(allow-list seed)", "seed file missing or changed; SHA-256 must be " + SEED_SHA256))
        allow = {}
        with open(a.allowlist, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                allow[r["id"]] = r
        import glob
        removed = {}
        for rp in sorted(glob.glob(os.path.join(os.path.dirname(os.path.abspath(a.allowlist)), "sources-gate-allowlist-removed-*.csv"))):
            with open(rp, newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    try:
                        if datetime.date.fromisoformat(r["removed"].strip()) <= today:
                            removed.setdefault(r["id"].strip(), r["removed"].strip())
                    except ValueError:
                        gate.append(("(allow-list removal %s)" % os.path.basename(rp), "row %s has no valid removed date" % r.get("id")))
        def bad_entry(r):
            try:
                exp = datetime.date.fromisoformat(r["expires"]); listed = datetime.date.fromisoformat(r["listed"])
            except ValueError:
                return "allow-list entry has no valid expires/listed date"
            if exp < today:
                return "ALLOW-LIST EXPIRED %s" % r["expires"]
            if listed > GATE_DATE:
                return "listed %s, after the gate date; new rows are never allow-listed" % r["listed"]
            ren = (r.get("renewals") or "0").strip()
            if ren == "0":
                if (exp - listed).days > 30:
                    return "expiry more than 30 days after listing"
            elif ren == "1":
                if r["reason_class"].strip().lower() != "no primary exists yet":
                    return "renewal allowed only for 'no primary exists yet'"
                m = re.match(r"\d{4}-\d{2}-\d{2}$", (r.get("primary_search_date") or "").strip())
                if not m or datetime.date.fromisoformat(m.group(0)) <= GATE_DATE:
                    return "renewal needs a new primary_search_date after 2026-10-27"
                if (exp - datetime.date.fromisoformat(m.group(0))).days > 30:
                    return "renewed expiry more than 30 days after the new primary search"
            else:
                return "renewals must be 0 or 1 (renews once only)"
            if r["id"] in removed:
                return "removed from the allow-list %s (append-only removal; never returns)" % removed[r["id"]]
            if r["id"] not in seed:
                return "not in the frozen 27 Oct 2026 seed; new rows are never allow-listed"
            return ""
        for rid, _, derived, *_ in rows:
            if derived == "MISSING RECORD":
                gate.append((rid, "NO RECORD (record-before-entry; never allow-listed)"))
            elif derived in ("UNSOURCED", "PARTLY SOURCED"):
                if rid not in allow:
                    gate.append((rid, "%s, not on the allow-list" % derived))
                else:
                    why = bad_entry(allow[rid])
                    if why:
                        gate.append((rid, "%s, %s" % (derived, why)))
    counts = {k: sum(1 for r in rows if r[2] == k) for k in ("SOURCED", "SECONDARY-SOURCED", PROMISE, PROMISE_SCORED, "PARTLY SOURCED", "UNSOURCED", "MISSING RECORD")}
    secfails = [(r, why) for r, why in fails if "LABEL MISSING" in why or "NO PRIMARY SEARCH" in why]
    overclaims = [(r, why) for r, why in fails if "claims" in why or "unknown" in why]
    expired = [(r, why) for r, why in fails if "SCORING DATE PASSED" in why]
    summary = "rows %d | sourced %d | secondary-sourced %d | promise sourced outcome pending %d | promise sourced outcome scored %d | partly sourced %d | unsourced %d | missing record %d | over-claims %d | secondary fails %d | failed entries %d | failed entry incomplete %d" % (
        len(rows), counts["SOURCED"], counts["SECONDARY-SOURCED"], counts[PROMISE], counts[PROMISE_SCORED], counts["PARTLY SOURCED"], counts["UNSOURCED"], counts["MISSING RECORD"], len(overclaims), len(secfails), len(failed_rows), len(incomplete))
    summary += " | scoring date passed not scored %d" % len(expired)
    print(summary)
    for r, why in overclaims:
        print("OVER-CLAIM", r, why)
    for r, why in secfails:
        print("FAIL", r, why)
    for r, why in expired:
        print("FORWARD EXPIRED", r, why)
    for r, ps in stale:
        print("STALE SECONDARY", r, ps)
    for fid, g in incomplete:
        print("FAILED ENTRY INCOMPLETE", fid, "missing", g)
    for r, why in gate:
        print("GATE BLOCK", r, why)
    if a.allowlist:
        print("gate: %d blocked (allow-list %s)" % (len(gate), a.allowlist))
    if orphans:
        print("records with no register row:", ", ".join(orphans))

    if a.counts_out:
        d = a.counts_date or datetime.date.today().isoformat()
        with open(a.counts_out, "w", encoding="utf-8") as f:
            f.write("date,sourced,secondary_sourced,partly_sourced,unsourced,missing_record,rows,failed_entries,failed_entry_incomplete,promise_outcome_pending,promise_outcome_scored\n%s,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d\n" % (
                d, counts["SOURCED"], counts["SECONDARY-SOURCED"], counts["PARTLY SOURCED"], counts["UNSOURCED"], counts["MISSING RECORD"], len(rows), len(failed_rows), len(incomplete), counts[PROMISE], counts[PROMISE_SCORED]))
    if a.report:
        with open(a.report, "w", encoding="utf-8") as f:
            f.write("# Sources check report\n\n")
            f.write("Generated by tools/check_sources.py%s against %s.\n\n" % (" --report-only" if a.report_only else "", a.staging))
            f.write("Summary: " + summary + "\n\n")
            f.write("A block counts only with Primary URL, Exact supporting line and Read date filled and Supports full or partial. Leads never count. SOURCED also needs Claim coverage: full (absent means partial).\n\n")
            f.write("## Over-claims (would fail)\n\n")
            f.write("".join("- %s: %s\n" % o for o in overclaims) or "- none\n")
            f.write("\n## Secondary fails (rule A: label missing or no primary search)\n\n")
            f.write("".join("- %s: %s\n" % o for o in secfails) or "- none\n")
            f.write("\n## Stale secondary (primary search more than 30 days old; hunt again)\n\n")
            f.write("".join("- %s: %s\n" % o for o in stale) or "- none\n")
            f.write("\n## FAILED entry incomplete (five-field rule; blocks)\n\n")
            f.write("".join("- %s: missing %s\n" % o for o in incomplete) or "- none\n")
            f.write("\n```csv\nfailed_entry,fields_file,missing\n")
            csv.writer(f, lineterminator="\n").writerows(failed_rows)
            f.write("```\n")
            if a.allowlist:
                f.write("\n## Gate blocks (allow-list %s)\n\n" % a.allowlist)
                f.write("".join("- %s: %s\n" % g for g in gate) or "- none\n")
            if orphans:
                f.write("\n## Records with no register row\n\n" + "".join("- %s\n" % o for o in orphans))
            f.write("\n## Every row\n\n```csv\nid,claimed,derived,coverage,source_blocks,full,partial,fail_reason\n")
            w = csv.writer(f, lineterminator="\n")
            w.writerows(rows)
            f.write("```\n")
    if a.report_only:
        return 0
    return 1 if (fails or incomplete or gate) else 0

FIXTURE_HEAD = "section,sort_date,scoring_date,id,test,owner,date_source,status\n"
FIXTURE_REC = """# SOURCES RECORD: {id}

Status: {status}
Claim coverage: promise full, outcome pending
Claim tested (row wording, verbatim): fixture

## Source 1
- Row ID: {id}
- Primary URL: https://example.invalid/{id}
- Exact supporting line (verbatim, straight quotes): "fixture promise line"
- Supports: {sup}
- Read date: 2026-10-27

## Leads (not sources)
- none
"""

def selftest(staging):
    """Forward-row gate fixtures (Barry go 27 Oct 2026 15:50 CST). Built in a temporary tree with the real frozen
    seed and an empty allow-list; never touches the staging tree. Exit 0 only if every fixture behaves."""
    import tempfile, shutil, io, contextlib
    seed_src = os.path.join(staging, "data", "sources-gate-allowlist-seed-2026-10-27.txt")
    cases = [  # id, scoring date, status, Supports, record Status, audit date, expect exit, expect in output
        ("FX-FWD-OK", "4 Dec 2026", "LIVE", "full", PROMISE, "2026-10-27", 0, "promise sourced outcome pending 1"),
        ("FX-FWD-PAST", "4 Dec 2026", "LIVE", "full", PROMISE, "2026-12-05", 1, "FORWARD EXPIRED FX-FWD-PAST"),
        ("FX-FWD-ONDATE", "4 Dec 2026", "LIVE", "full", PROMISE, "2026-12-04", 1, "FORWARD EXPIRED FX-FWD-ONDATE"),
        ("FX-FWD-PARTIAL", "4 Dec 2026", "LIVE", "partial", PROMISE, "2026-10-27", 1, "GATE BLOCK FX-FWD-PARTIAL PARTLY SOURCED"),
        ("FX-FWD-SCORED", "4 Dec 2026", "SCORED 4 Dec 2026: PASS", "full", PROMISE_SCORED, "2026-12-05", 0, "promise sourced outcome scored 1"),
    ]
    bad = 0
    for cid, sd, st, sup, rst, aud, want, needle in cases:
        d = tempfile.mkdtemp(prefix="sources-selftest-")
        try:
            os.makedirs(os.path.join(d, "data")); os.makedirs(os.path.join(d, "sources", "failed"))
            shutil.copy(seed_src, os.path.join(d, "data"))
            open(os.path.join(d, "data", "sources-gate-allowlist.csv"), "w").write("id,level,reason_class,primary_search_date,expires,renewals,listed\n")
            with open(os.path.join(d, "data", "entries.csv"), "w", newline="") as ef:
                w = csv.writer(ef, lineterminator="\n")
                w.writerow(FIXTURE_HEAD.strip().split(",")); w.writerow(["FIX", "", sd, cid, "PASS: x. FAILED: y", "o", "s", st])
            open(os.path.join(d, "sources", cid + ".md"), "w").write(FIXTURE_REC.format(id=cid, sup=sup, status=rst))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                got = main(["--staging", d, "--allowlist", os.path.join(d, "data", "sources-gate-allowlist.csv"), "--audit-date", aud])
            ok = got == want and needle in out.getvalue()
            bad += not ok
            print("SELFTEST %s %s: exit %d (want %d)" % ("ok" if ok else "FAIL", cid, got, want))
        finally:
            shutil.rmtree(d)
    # 28 Oct 2026: the append-only case. Original row stays LIVE; a SCORED entry supersedes it after the date.
    d = tempfile.mkdtemp(prefix="sources-selftest-")
    try:
        os.makedirs(os.path.join(d, "data")); os.makedirs(os.path.join(d, "sources", "failed"))
        shutil.copy(seed_src, os.path.join(d, "data"))
        open(os.path.join(d, "data", "sources-gate-allowlist.csv"), "w").write("id,level,reason_class,primary_search_date,expires,renewals,listed\n")
        with open(os.path.join(d, "data", "entries.csv"), "w", newline="") as ef:
            w = csv.writer(ef, lineterminator="\n")
            w.writerow(FIXTURE_HEAD.strip().split(",") + ["supersedes_id"])
            w.writerow(["FIX", "", "4 Dec 2026", "FX-FWD-SUPERSEDED", "PASS: x. FAILED: y", "o", "s", "LIVE", ""])
            w.writerow(["FIX", "", "4 Dec 2026", "FX-FWD-SUPERSEDED-SCORED", "PASS: x. FAILED: y", "o", "s", "SCORED 4 Dec 2026: PASS", "FX-FWD-SUPERSEDED"])
        open(os.path.join(d, "sources", "FX-FWD-SUPERSEDED.md"), "w").write(FIXTURE_REC.format(id="FX-FWD-SUPERSEDED", sup="full", status=PROMISE))
        open(os.path.join(d, "sources", "FX-FWD-SUPERSEDED-SCORED.md"), "w").write(FIXTURE_REC.format(id="FX-FWD-SUPERSEDED-SCORED", sup="full", status=PROMISE_SCORED))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            got = main(["--staging", d, "--allowlist", os.path.join(d, "data", "sources-gate-allowlist.csv"), "--audit-date", "2026-12-05"])
        ok = got == 0 and "FORWARD EXPIRED" not in out.getvalue() and "promise sourced outcome scored 2" in out.getvalue()
        bad += not ok; cases.append(None)
        print("SELFTEST %s FX-FWD-SUPERSEDED: exit %d (want 0)" % ("ok" if ok else "FAIL", got))
        if not ok: print(out.getvalue())
    finally:
        shutil.rmtree(d)
    print("selftest: %d fixtures, %d failed" % (len(cases), bad))
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main())
