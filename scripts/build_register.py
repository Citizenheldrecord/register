#!/usr/bin/env python3
"""Build the Citizen-Held Register from the one canonical source, data/entries.csv.

  python3 scripts/build_register.py --date 2026-10-18              build into the repository
  python3 scripts/build_register.py --date 2026-10-18 --out-dir X  build into a scratch folder
  python3 scripts/build_register.py --date 2026-10-18 --draft      build into local/draft-build-<date>/ (scoring and staging jobs)
  python3 scripts/build_register.py --verify                       check the published files only

Guardrails (Barry go 27 Oct 2026):
  1. No overwrite of published files. Before anything is written, the dated outputs
     (public-live-rows-*, manifest/entry-hashes-v2-* and their .sha256) are compared with
     the published listing in local/published-files.txt (from GitHub; see
     scripts/check_published_unchanged.py). If a name is already published and the new
     bytes differ, the build stops. README.md and index.html are exempt.
     --allow-overwrite lifts this; it is never used by routines or scheduled jobs.
  2. --draft builds into local/draft-build-<date>/ and never touches the upload root.
     Scoring and staging jobs use --draft; only the upload step (on Barry's go) builds to the root.

Fails loudly (exit 1, every problem listed) if: a row breaks the data rules
(outcome, scoring date, owner, cost to date, sub-scores on resolved entries,
supersedes fields), house grammar fails anywhere public, a prior entry changed or
vanished against the previous manifest, or a printed checksum does not match.
Nothing is written to the repository unless every check passes.
"""
import subprocess
import argparse, csv, glob, hashlib, html, json, os, re, shutil, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import regcore as rc
import hash_entries as he
import reading_aids as ra

ROOT = rc.ROOT


def sha(b):
    return hashlib.sha256(b).hexdigest()


def one(pattern, repl, text, name, flags=0):
    new, n = re.subn(pattern, repl, text, flags=flags)
    if n == 0:
        raise rc.Fail("%s: template anchor not found: %s" % (name, pattern))
    return new


TABLE_COLS = "ID | Test | Owner | Scoring date | Date source | Status | Measure | Money | Funding | Argument | Cost to date | Hype | Means | Cost"
TABLE_KEYS = ["id", "test", "owner", "scoring_date", "date_source", "status", "measure", "money", "funding", "argument", "cost_to_date", "hype_score", "means_score", "cost_score"]
SECTION_HEADS = {
    "CANADA": "Canadian files (%d), in order of scoring date",
    "DESK": "This desk's own commitments (%d)",
    "WATCH": "Outside files we watch (%d)",
    "RECORDED": "Recorded facts and checkpoints (%d)",
}
RECORDED_LEAD = "These files record a fact, a status or a condition, or carry a reading or a scoring day the main table does not use. They are dated and kept, and are not counted in the main table.\n\n"


GROUPS = os.path.join(rc.ROOT, "data", "display-groups.csv")
GROUP_ORDER = ("government_promise", "also_watched", "recorded")
GROUP_HEADS = {"government_promise": "Government promises (%d)", "also_watched": "Also watched (%d)", "recorded": "Recorded (%d)"}
GROUP_LEADS = {
    "government_promise": "Promises with a government owner, a primary source and a scoring date. Each row also names its file section.\n\n",
    "also_watched": "Rows the register watches that are not government promises: the owner is not a government, or the row lacks a primary source link. Same rules apply.\n\n",
    "recorded": "Facts, results and checkpoints, recorded and kept. They are not counted as open promises.\n\n",
}


def load_groups(rows):
    """Display only: which page group each row sits in. Nothing in an entry changes.
    Returns None if there is no groups file or it does not cover every row (then the page uses file sections)."""
    import csv as _c
    if not os.path.exists(GROUPS):
        return None
    g = {r["id"]: r["display_group"] for r in _c.DictReader(open(GROUPS, encoding="utf-8"))}
    for r in rows:   # a new date, correction or scoring entry sits in the group of the entry it cites
        if r["id"] not in g and r.get("supersedes_id") in g:
            g[r["id"]] = g[r["supersedes_id"]]
    miss = [r["id"] for r in rows if r["id"] not in g]
    bad = sorted(k for k, v in g.items() if v not in GROUP_ORDER)
    if miss or bad:
        # 25 Oct 2026: never fall back silently; a row missing from the groups file left counts short.
        raise rc.Fail("display-groups.csv: rows not grouped %s; unknown groups %s" % (miss, bad))
    return g


NOTES = os.path.join(rc.ROOT, "data", "display-notes.csv")


def overlaps_md(rows):
    """Display only: 'Possible overlaps under review' from data/display-notes.csv. Nothing in an entry changes."""
    import csv as _c
    if not os.path.exists(NOTES):
        return None
    ids = {r["id"] for r in rows}
    notes = [n for n in _c.DictReader(open(NOTES, encoding="utf-8")) if n["kind"] == "possible_overlap"]
    bad = [i for n in notes for i in n["ids"].split(";") if i not in ids]
    if bad:
        raise rc.Fail("data/display-notes.csv names ids not in data/entries.csv: %s" % bad)
    if not notes:
        return None
    out = ["## Possible overlaps under review", "",
           "These pairs of entries may test the same thing. Both entries in each pair are kept and stay live while the overlap is under review. Nothing has been removed or changed in either entry.", ""]
    out += ["- **%s** (noted %s): %s" % (" and ".join(n["ids"].split(";")), n["noted"], n["text"]) for n in notes]
    return "\n".join(out)


RELATED_INTRO = "These rows are linked because they test related things. Each is scored on its own date; neither replaces the other."


def related_notes(rows):
    """Display only: see_also notes from data/display-notes.csv. Nothing in an entry changes."""
    import csv as _c
    if not os.path.exists(NOTES):
        return []
    ids = {r["id"] for r in rows}
    notes = [n for n in _c.DictReader(open(NOTES, encoding="utf-8")) if n["kind"] == "see_also"]
    bad = [i for n in notes for i in n["ids"].split(";") if i not in ids]
    if bad:
        raise rc.Fail("data/display-notes.csv names ids not in data/entries.csv: %s" % bad)
    return notes


def failure_rows():
    import csv as _c
    p = os.path.join(os.path.dirname(NOTES), "failure-log.csv")
    if not os.path.exists(p):
        return []
    return list(_c.DictReader(open(p, encoding="utf-8")))


FL_KEYS = ["id", "original_deadline", "date_failed", "test", "layer", "cost", "chosen_instead"]


def failure_md(ld):
    fr = failure_rows()
    if not fr:
        return "No entries as at %s." % ld
    return "\n".join("%s" % " | ".join(r[k].replace("|", "/") for k in FL_KEYS) for r in fr) + "\n\nEntries as at %s: %d." % (ld, len(fr))


def failure_html(ld):
    fr = failure_rows()
    e = lambda s: html.escape(s, quote=True)
    if not fr:
        return '<tr><td colspan="7" class="empty">No entries as at %s.</td></tr>' % ld
    return "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % e(r[k]) for k in FL_KEYS) for r in fr)



def related_md(rows):
    notes = related_notes(rows)
    if not notes:
        return None
    out = ["## Related rows", "", RELATED_INTRO, ""]
    out += ["- **%s** (noted %s): %s" % (" and ".join(n["ids"].split(";")), n["noted"], n["text"]) for n in notes]
    return "\n".join(out)


def related_html(rows):
    notes = related_notes(rows)
    if not notes:
        return None
    e = lambda s: html.escape(s, quote=True)
    link = lambda i: '<a href="#row-%s">%s</a>' % (e(i), e(i))
    def text(n):
        t = e(n["text"])
        for i in sorted(n["ids"].split(";"), key=len, reverse=True):
            t = re.sub(r"(?<![A-Za-z0-9-])%s(?![A-Za-z0-9-])" % re.escape(e(i)), lambda m: link(i), t)
        return t
    lis = "".join('<li><strong>%s</strong> (noted %s): %s</li>' % (" and ".join(link(i) for i in n["ids"].split(";")), e(n["noted"]), text(n)) for n in notes)
    return '<h2>Related rows</h2><p>%s</p><ul>%s</ul>' % (e(RELATED_INTRO), lis)


def backlog_block(iso):
    """Display only: the counter's block, counted from data/entries.csv on the build date."""
    import backlog_counter as bc
    _, rows = rc.read_source(rc.SOURCE)
    return bc.block(rows, iso)[0]


def md_to_html(md):
    out, inlist, intable = [], False, False
    b = lambda s: re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html.escape(s, quote=False))
    for ln in md.split("\n"):
        if ln.startswith("- "):
            if not inlist: out.append("<ul>"); inlist = True
            out.append("<li>%s</li>" % b(ln[2:])); continue
        if inlist: out.append("</ul>"); inlist = False
        if ln.startswith("|"):
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if set("".join(cells)) <= set("-"): continue
            if not intable:
                out.append("<table><thead><tr>%s</tr></thead><tbody>" % "".join("<th>%s</th>" % b(c) for c in cells)); intable = True
            else:
                out.append("<tr>%s</tr>" % "".join("<td>%s</td>" % b(c) for c in cells))
            continue
        if intable: out.append("</tbody></table>"); intable = False
        if ln.startswith("## "): out.append("<h2>%s</h2>" % b(ln[3:]))
        elif ln.strip(): out.append("<p>%s</p>" % b(ln))
    if inlist: out.append("</ul>")
    if intable: out.append("</tbody></table>")
    return "".join(out)


def tables(rows):
    closers, replaced = rc.closed_by(rows), rc.replaced_by(rows)
    cell = lambda r, k: rc.display_status(r, closers, replaced) if k == "status" else (r["id"] + (" (follows %s)" % r[rc.FOLLOWS_COL] if r.get(rc.FOLLOWS_COL) else "")) if k == "id" else r.get(k, "")
    out = ""
    groups = load_groups(rows)
    if groups:
        for gk in GROUP_ORDER:
            rs = [r for r in rows if groups[r["id"]] == gk]
            out += GROUP_HEADS[gk] % len(rs) + "\n\n" + GROUP_LEADS[gk]
            out += "Section | " + TABLE_COLS + "\n\n" + "".join(SECTION_HEADS[r["section"]].split(" (")[0] + " | " + " | ".join(cell(r, k) for k in TABLE_KEYS) + "\n\n" for r in rs)
        return out
    for s in rc.SECTION_ORDER:
        rs = [r for r in rows if r["section"] == s]
        out += SECTION_HEADS[s] % len(rs) + "\n\n"
        if s == "RECORDED":
            out += RECORDED_LEAD
        out += TABLE_COLS + "\n\n" + "".join(" | ".join(cell(r, k) for k in TABLE_KEYS) + "\n\n" for r in rs)
    return out


GITHUB = "https://github.com/citizenheldrecord/register/blob/main/"


def build_stamp(uid, iso, src_sha, n):
    return ("Build stamp: update %s, counted as at %s, from data/entries.csv, %d rows, SHA-256 %s. "
            "The build stops if this file, its row count or any count on this page does not match." % (uid, rc.long_date(iso), n, src_sha))


SOURCES_COUNTS = os.path.join(rc.ROOT, "data", "sources-check-counts.csv")
SOURCES_NOTE = ("Note, 27 Oct 2026: This register's rule is that every row rests on a primary source, read against that row. "
    "On 27 Oct the desk began a row-by-row audit of that rule. It found that many rows were checked against wire reports such as Reuters "
    "rather than against the body that made the decision, and that in a few rows the wording went further than the source. "
    "Each row now gets its own sources record, listing the primary, the exact line it supports and the date it was read. "
    "A row shows as sourced only when that record backs its whole claim. As of this build: {S} rows are sourced, {X} secondary-sourced, {O} have their promise sourced with the outcome pending, "
    "{P} partly sourced and {U} unsourced, and {M} do not yet have a record. These counts will be updated with each build until every row is done. "
    "Corrections from the audit are entered as new dated lines, and no score has been changed.")


def sources_note(iso):
    """Page note staged 27 Oct 2026 (Barry go 14:18 CST). Shown only when data/sources-check-counts.csv was
    written by tools/check_sources.py --counts-out for this build date; older builds reproduce unchanged."""
    if not os.path.exists(SOURCES_COUNTS):
        return None
    with open(SOURCES_COUNTS, newline="") as f:
        r = list(csv.DictReader(f))
    if not r or r[0].get("date") != iso:
        print("SOURCES NOTE LEFT OUT: data/sources-check-counts.csv is not dated %s; run tools/check_sources.py --counts-out" % iso, file=sys.stderr)
        return None
    c = r[0]
    return SOURCES_NOTE.format(S=int(c["sourced"]), X=int(c.get("secondary_sourced") or 0), O=int(c.get("promise_outcome_pending") or 0), P=int(c["partly_sourced"]), U=int(c["unsourced"]), M=int(c["missing_record"]))


def audit_md(uid, iso, src_sha, n):
    hk = rc.read_housekeeping()
    hk_sha = sha(open(rc.HOUSEKEEPING_LOG, "rb").read()) if os.path.exists(rc.HOUSEKEEPING_LOG) else "none"
    man = "manifest/entry-hashes-v2-%s.csv" % uid
    note = sources_note(iso)
    return "\n\n".join(([note] if note else []) + [
        "## How to check this update",
        build_stamp(uid, iso, src_sha, n),
        "Entry fingerprints for this update: [%s](%s%s). Housekeeping log: [data/housekeeping-log.csv](%sdata/housekeeping-log.csv), SHA-256 %s, %d lines." % (man, GITHUB, man, GITHUB, hk_sha, len(hk)),
        "How to check a housekeeping change. 1. Find the row in data/housekeeping-log.csv and note its layout and the two fingerprints. 2. Download the last dated CSV published before the change (for the changes of 24 October 2026, public-live-rows-2026-10-23c.csv) and run python3 scripts/hash_entries.py public-live-rows-2026-10-23c.csv --show ID to see the row's canonical text; the SHA-256 of that text is the before fingerprint. 3. Do the same on the current CSV for the after fingerprint. 4. Compare the two texts: only the logged field may differ, and only by deleted text or by OPEN.",
        "Append only, stated exactly: entries are append only for substance. Tests, owners, dates, results and sources are never edited or deleted; a new date, a correction or a result is a new dated entry. The exceptions are rule entries R-2026-10-24-A and R-2026-10-25-A: internal working notes may be removed (from a test, internal approval notes only), each removal logged with the row's fingerprint before and after, and earlier dated files stay as published.",
        "How entries get in (dated 25 October 2026). This register is a record of the tests this desk has published, not a census of government promises. An entry exists where an essay, report or desk note, or a Gazette or official-source sweep, set or found a dated, two-outcome test on a named owner; it then goes LIVE on Barry Sharp's go and is never removed. Government promises the desk has not written about are not here, and absence from the register means nothing about a promise. Entries in \"Government promises\" have a government owner; entries with a desk-set test or a non-government owner sit in \"Also watched\"; baselines sit in \"Recorded\". Dates: as at update 2026-10-25j, of 238 entries, 149 (about 63 per cent) carry a benchmark date set by the register, 2 an outside date with a scoring window set by the register, and 87 (about 37 per cent) a date set by an outside source (statute, court, scheduled release, government or company timetable). Every entry's date source is labelled. A desk-set date is a benchmark, not a legal deadline: a FAILED against it means the owner did not deliver by the date we chose and published in advance, nothing more. The share is recounted at each update.",
        "Provenance (rule R-2026-10-26-A, 26 October 2026). Posts and press reports are leads only. No row is scored on them alone: every row must rest on a primary, a publication by the body that made the decision or holds the record. A row whose date, fact or evidence rests only on a news report or post is flagged with a dated replacement task, the primary the desk will look for and the date by which it will look. A primary found later is recorded in a new dated line; the row's own cells are not edited. Flags and replacements are in the CORRECTIONS folder; the first six (C39-CTTE, C39-D1, S2, S7, MTL-CLOSE, NOV1) are in CORRECTIONS/2026-10-26-provenance-six-rows.md.",
        "Limits of this register. A fingerprint or checksum proves a file or row has not changed since it was published. It does not prove the evidence is complete, that the test is fair, or that a date set by the register is the right benchmark. Anyone may challenge any row: open an issue naming the row id and the reason, and the answer goes in as a dated entry.",
        '## How rows are chosen, and how to propose a test',
        "This is one citizen's ledger, kept by Barry Sharp. It is not an official record, and the choice of promises, tests and owners is one person's judgment.",
        'To find candidates, the desk runs a Gazette, LEGISinfo and official-source run every Monday, Wednesday and Saturday: Canada Gazette Part I and Part II, bills on LEGISinfo and official government releases. A weekday morning news-pattern sweep also checks the Gazette. A candidate needs a dated, two-outcome test, a named owner and a primary source.',
        'The selection rule is published as rule R-2026-10-25-E (How entries get in). Failures go in the append-only failure log. Every pass condition is written and dated before the result is known, and is never edited afterwards: a new date or correction is a new dated entry.',
        'Other observers may pick different tests, such as environmental conditions, Indigenous consent thresholds or fiscal risk. To propose one for the same promise, open an issue at https://github.com/citizenheldrecord/register/issues naming the row id and the test you would use. The answer goes in as a dated entry.',
    ])


def render_readme(tpl, rows, csv_name, csv_sha, iso):
    ld = rc.long_date(iso)
    t = one(r"Entries as at \d+ \w+ \d{4}\. Last change: \d+ \w+ \d{4}\.", "Entries as at %s. Last change: %s." % (ld, ld), tpl, "README")
    t = one(r"Checksum for this update: SHA-256 of public-live-rows-\d{4}-\d\d-\d\d[a-z]?\.csv \(all \d+ rows\) is [0-9a-f]{64}",
            "Checksum for this update: SHA-256 of %s (all %d rows) is %s" % (csv_name, len(rows), csv_sha), t, "README")
    t = one(r"<!-- FAILLOG -->.*?<!-- /FAILLOG -->|No entries as at \d+ \w+ \d{4}\.", lambda m: "<!-- FAILLOG -->\n\n%s\n\n<!-- /FAILLOG -->" % failure_md(ld), t, "README", re.S)
    bl = backlog_block(iso)
    if bl:
        if "<!-- BACKLOG -->" in t:
            t = one(r"<!-- BACKLOG -->.*?<!-- /BACKLOG -->\n\n", lambda m: "<!-- BACKLOG -->\n\n%s\n\n<!-- /BACKLOG -->\n\n" % bl, t, "README", re.S)
        else:
            k = t.find("\n\n") + 2
            t = t[:k] + "<!-- BACKLOG -->\n\n%s\n\n<!-- /BACKLOG -->\n\n" % bl + t[k:]
    starts = [x for x in (t.find("Canadian files ("), t.find("Government promises (")) if x >= 0]
    a, b = (min(starts) if starts else -1), t.find("Failure log\n")
    if a < 0 or b < a:
        raise rc.Fail("README: table block anchors not found")
    fx = ra.display_fixes(rows)
    drows = [dict(r, **fx.get(r["id"], {})) for r in rows]
    t = t[:a] + tables(drows) + t[b:]
    au = "<!-- AUDIT -->\n\n%s\n\n<!-- /AUDIT -->\n\n" % audit_md(STAMP["uid"], iso, STAMP["sha"], STAMP["n"])
    if "<!-- AUDIT -->" in t:
        t = one(r"<!-- AUDIT -->.*?<!-- /AUDIT -->\n\n", lambda m: au, t, "README", re.S)
    else:
        k = t.find("Failure log\n")
        if k < 0:
            raise rc.Fail("README: Failure log anchor not found")
        t = t[:k] + au + t[k:]
    ov = overlaps_md(rows)
    if ov:
        blk = "<!-- OVERLAPS -->\n\n%s\n\n<!-- /OVERLAPS -->\n\n" % ov
        if "<!-- OVERLAPS -->" in t:
            t = one(r"<!-- OVERLAPS -->.*?<!-- /OVERLAPS -->\n\n", lambda m: blk, t, "README", re.S)
        else:
            k = t.find("<!-- /BACKLOG -->\n\n")
            k = k + len("<!-- /BACKLOG -->\n\n") if k >= 0 else t.find("\n\n") + 2
            t = t[:k] + blk + t[k:]
    rl = related_md(rows)
    if rl:
        rb = "<!-- RELATED -->\n\n%s\n\n<!-- /RELATED -->\n\n" % rl
        if "<!-- RELATED -->" in t:
            t = one(r"<!-- RELATED -->.*?<!-- /RELATED -->\n\n", lambda m: rb, t, "README", re.S)
        elif "<!-- /OVERLAPS -->\n\n" in t:
            t = t.replace("<!-- /OVERLAPS -->\n\n", "<!-- /OVERLAPS -->\n\n" + rb, 1)
        else:
            raise rc.Fail("README: anchor for Related rows not found")
    return t


def next_on_clock(rows, iso, n=5):
    """Display only (rule entry R-2026-10-19-F): the n nearest LIVE entries not yet scored,
    on or after the build date, plus one line naming entries past their date and not yet scored."""
    closers, replaced = rc.closed_by(rows), rc.replaced_by(rows)
    open_ = [r for r in rows if r["status"] == "LIVE" and r["id"] not in closers and r["id"] not in replaced and not rc.is_resolved(r)]
    nxt = sorted([r for r in open_ if r["sort_date"] >= iso], key=lambda r: (r["sort_date"], r["id"]))[:n]
    past = sorted([r for r in open_ if r["sort_date"] < iso], key=lambda r: (r["sort_date"], r["id"]))
    cells = "".join("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
        html.escape(r["scoring_date"]), html.escape(r["id"]), html.escape(r["section"]), html.escape(ra.display_fixes([r]).get(r["id"], {}).get("owner", r["owner"]))) for r in nxt)
    pd = ("Past their scoring date and not yet scored: %s." % ", ".join("%s (%s)" % (html.escape(r["id"]), html.escape(r["scoring_date"])) for r in past)) if past else "Past their scoring date and not yet scored: none."
    return ('<!-- NEXT-ON-CLOCK --><h2>Next on the clock</h2><p>The five nearest entries still to be scored, by scoring date, as at %s.</p>'
            '<table><thead><tr><th>Scoring date</th><th>ID</th><th>Section</th><th>Owner</th></tr></thead><tbody>%s</tbody></table><p>%s</p><!-- /NEXT-ON-CLOCK -->\n'
            % (rc.long_date(iso), cells, pd))


CODEBERG = "https://codeberg.org/citizen-held-record/register"


def copies_line(uid):
    """Display only (rule entry R-2026-10-19-J): names the copies and the update the Codeberg copy is refreshed to."""
    return ('<!-- COPIES --><p class="copies">Copies of this record: GitHub (this site) and Codeberg, <a href="%s">%s</a> '
            '(manual copy; the desk refreshes it to update %s after each push and checks the checksum below).</p><!-- /COPIES -->'
            % (CODEBERG, CODEBERG, html.escape(uid)))


CC_BY = "https://creativecommons.org/licenses/by/4.0/"
FOOTER = ('<!-- COPYRIGHT --><footer class="copyright"><p class="small">&copy; 2026 Barry Sharp. Sovereign Realism register. '
          'Licensed under <a href="%s" rel="license">CC BY 4.0</a>: share and adapt with credit. '
          'Full licence text: <a href="LICENSE">LICENSE</a>.</p></footer><!-- /COPYRIGHT -->\n' % CC_BY)


def apply_footer(t, name):
    """Copyright notice and CC BY 4.0 licence line (Barry approval 27 Oct 2026 16:30 CST), on both register pages."""
    if "<!-- COPYRIGHT -->" in t:
        return one(r"<!-- COPYRIGHT -->.*?<!-- /COPYRIGHT -->\n", lambda m: FOOTER, t, name, re.S)
    if t.count("</body>") != 1:
        raise rc.Fail("%s: </body> anchor for the copyright footer not found" % name)
    return t.replace("</body>", FOOTER + "</body>", 1)


def render_index(tpl, rows, csv_text, csv_name, json_name, csv_sha, iso):
    ld = rc.long_date(iso)
    t = one(r'(id="csvdata"[^>]*>).*?(</script>)', lambda m: m.group(1) + json.dumps(csv_text, ensure_ascii=False).replace("</", "<\\/") + m.group(2), tpl, "index.html", re.S)
    t = one(r'(<span id="printed">)[0-9a-f]{64}', r"\g<1>" + csv_sha, t, "index.html")
    t = one(r"SHA-256 of public-live-rows-\d{4}-\d\d-\d\d[a-z]?\.csv \(all \d+ rows\)", "SHA-256 of %s (all %d rows)" % (csv_name, len(rows)), t, "index.html")
    t = one(r'"public-live-rows-\d{4}-\d\d-\d\d[a-z]?\.csv"', '"%s"' % csv_name, t, "index.html")
    t = one(r'"public-live-rows-\d{4}-\d\d-\d\d[a-z]?\.json"', '"%s"' % json_name, t, "index.html")
    t = one(r"<!-- COPIES -->.*?<!-- /COPIES -->", lambda m: copies_line(csv_name[len("public-live-rows-"):-4]), t, "index.html", re.S)
    strip = next_on_clock(rows, iso)
    if "<!-- NEXT-ON-CLOCK -->" in t:
        t = one(r"<!-- NEXT-ON-CLOCK -->.*?<!-- /NEXT-ON-CLOCK -->\n", lambda m: strip, t, "index.html", re.S)
    else:
        t = t.replace("<h2>Entries (", strip + "<h2>Entries (", 1)
    # Display-only reading aids (proposed rule entry R-2026-10-22-A): summary, how to read, essay links.
    links = ra.load_links()
    errs = ra.check_links(rows, links)
    if errs:
        raise rc.Fail("\n".join(errs))
    blocks = (("STATUS-SUMMARY", ra.status_summary(rows, iso), "<h1>The Register</h1>\n", True),
              ("HOW-TO-READ", ra.how_to_read(rows, links), "<details><summary>The rules</summary>", False),
              ("ESSAYS", ra.essays_index(rows, links), "<h2>Failure log</h2>", False),
              ("AUDIT", "<!-- AUDIT --><section class=\"audit\">%s</section><!-- /AUDIT -->\n" % md_to_html(re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", audit_md(STAMP["uid"], iso, STAMP["sha"], STAMP["n"]))).replace("open an issue at https://github.com/citizenheldrecord/register/issues ", 'open an issue at <a href="https://github.com/citizenheldrecord/register/issues">https://github.com/citizenheldrecord/register/issues</a> '), "<h2>Failure log</h2>", False))
    bl = backlog_block(iso)
    if bl:
        blocks = blocks + (("BACKLOG", "<!-- BACKLOG --><section class=\"backlog\">%s</section><!-- /BACKLOG -->\n" % md_to_html(bl), "<h1>The Register</h1>\n", True),)
    if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "plain-english.html")):
        blocks = blocks + (("PLAIN-LINK", '<!-- PLAIN-LINK --><p><a href="plain-english.html">Read the register in plain English</a></p><!-- /PLAIN-LINK -->\n', "<h1>The Register</h1>\n", True),)
    for mark, blk, anchor, after in blocks:
        if "<!-- %s -->" % mark in t:
            t = one(r"<!-- %s -->.*?<!-- /%s -->\n" % (mark, mark), lambda m, b=blk: b, t, "index.html", re.S)
        else:
            if anchor not in t:
                raise rc.Fail("index.html: anchor for %s not found" % mark)
            t = t.replace(anchor, (anchor + blk) if after else (blk + anchor), 1)
    lj = '<script type="application/json" id="essaylinks">%s</script>' % ra.links_json(links)
    if 'id="essaylinks"' in t:
        t = one(r'<script type="application/json" id="essaylinks">.*?</script>', lambda m: lj, t, "index.html", re.S)
    else:
        t = t.replace("<script>\n", lj + "\n<script>\n", 1)
    fj = '<script type="application/json" id="displayfix">%s</script>' % ra.fixes_json(rows)
    if 'id="displayfix"' in t:
        t = one(r'<script type="application/json" id="displayfix">.*?</script>', lambda m: fj, t, "index.html", re.S)
    else:
        t = t.replace(lj, lj + "\n" + fj, 1)
    # Baseline label (correction of 25 October 2026), display only: a scored row whose own test says it is
    # recorded, not scored, and its scoring entry, show "Baseline" in the status cell. No row changes.
    scorer_of = {r["supersedes_id"].strip(): r["id"] for r in rows if r.get("supersedes_id", "").strip() and r["status"].upper().startswith("SCORED")}
    base = set()
    for r in rows:
        if rc.is_baseline(r) and r["id"] in scorer_of:
            base.update((r["id"], scorer_of[r["id"]]))
    bj = '<script type="application/json" id="baselines">%s</script>' % json.dumps(sorted(base))
    if 'id="baselines"' in t:
        t = one(r'<script type="application/json" id="baselines">.*?</script>', lambda m: bj, t, "index.html", re.S)
    else:
        t = t.replace(fj, fj + "\n" + bj, 1)
    js_old = '</td><td class="test">'
    js_new = '${BASE.has(r.id)?\' <span class="badge BASELINE">Baseline</span> <span class="small">recorded baseline, not counted as PASS or FAILED</span>\':\'\'}</td><td class="test">'
    if js_new not in t:
        if t.count(js_old) != 1:
            raise rc.Fail("index.html: id cell template for the Baseline label not found")
        t = t.replace(js_old, js_new, 1)
        t = t.replace('const OWN=r=>', 'const BASE=new Set(JSON.parse((document.getElementById("baselines")||{textContent:"[]"}).textContent));const OWN=r=>', 1)
    ov = overlaps_md(rows)
    if ov:
        ob = '<!-- OVERLAPS --><section class="overlaps">%s</section><!-- /OVERLAPS -->\n' % md_to_html(ov)
        if "<!-- OVERLAPS -->" in t:
            t = one(r"<!-- OVERLAPS -->.*?<!-- /OVERLAPS -->\n", lambda m: ob, t, "index.html", re.S)
        else:
            t = t.replace("<h2>Entries (", ob + "<h2>Entries (", 1)
    rh = related_html(rows)
    if rh:
        rbk = '<!-- RELATED --><section class="related">%s</section><!-- /RELATED -->\n' % rh
        if "<!-- RELATED -->" in t:
            t = one(r"<!-- RELATED -->.*?<!-- /RELATED -->\n", lambda m: rbk, t, "index.html", re.S)
        else:
            t = t.replace("<h2>Entries (", rbk + "<h2>Entries (", 1)
    left = ra.scan_internal(rows)
    if left:
        raise rc.Fail("internal text still displayed: " + "; ".join(left))
    groups = load_groups(rows)
    gj = '<script type="application/json" id="displaygroups">%s</script>' % json.dumps(groups or {}, ensure_ascii=False)
    if 'id="displaygroups"' in t:
        t = one(r'<script type="application/json" id="displaygroups">.*?</script>', lambda m: gj, t, "index.html", re.S)
    else:
        t = t.replace(fj, fj + "\n" + gj, 1)
    t = one(r"Last updated \d+ \w+ \d{4} \(update \d{4}-\d\d-\d\d[a-z]?\)\.", "Last updated %s (update %s)." % (ld, STAMP["uid"]), t, "index.html")
    t = one(r"<h2>Entries \(\d+\)</h2>", "<h2>Entries (%d)</h2>" % len(rows), t, "index.html")
    t = one(r"Entries as at \d+ \w+ \d{4}\. Last change: \d+ \w+ \d{4}\.", "Entries as at %s. Last change: %s." % (ld, ld), t, "index.html")
    t = apply_footer(t, "index.html")
    t = one(r"<!-- FAILLOG -->.*?<!-- /FAILLOG -->|<tr><td colspan=\"7\" class=\"empty\">No entries as at \d+ \w+ \d{4}\.</td></tr>", lambda m: "<!-- FAILLOG -->%s<!-- /FAILLOG -->" % failure_html(ld), t, "index.html", re.S)
    return t


def stamp_checks(readme, index, source):
    """25 Oct 2026: the build stamp must name the data file as it is, and the count block must be the one
    count_states() gives for that file on the stamped date."""
    errs = []
    m = re.search(r"Build stamp: update ([^,\s]+), counted as at (\d+ \w+ \d{4}), from data/entries.csv, (\d+) rows, SHA-256 ([0-9a-f]{64})\.", readme)
    if not m:
        return ["README: no build stamp"]
    uid, ld, n, h = m.groups()
    if build_stamp(uid, rc.split_uid(uid)[0], h, int(n)) not in index.replace("&#x27;", "'"):
        errs.append("index.html build stamp differs from README")
    if not os.path.exists(source):
        return errs + ["build stamp: %s not found" % source]
    if sha(open(source, "rb").read()) != h:
        errs.append("build stamp SHA-256 %s does not match data/entries.csv" % h)
    _, rows = rc.read_source(source)
    if len(rows) != int(n):
        errs.append("build stamp says %s rows, data/entries.csv has %d" % (n, len(rows)))
    import backlog_counter as bc
    iso = rc.split_uid(uid)[0]
    try:
        blk = bc.block(rows, iso)[0]
        if blk not in readme:
            errs.append("README count block is not the block computed from data/entries.csv as at %s" % iso)
        if md_to_html(blk) not in index:
            errs.append("index.html count block is not the block computed from data/entries.csv as at %s" % iso)
    except rc.Fail as e:
        errs.append(str(e))
    if rc.long_date(iso) != ld:
        errs.append("build stamp date %s does not match update %s" % (ld, uid))
    return errs


def printed_checks(folder, iso=None, source=None):
    """Every printed checksum must equal the CSV it names. Returns problems."""
    errs = []
    readme = open(os.path.join(folder, "README.md"), encoding="utf-8").read()
    index = open(os.path.join(folder, "index.html"), encoding="utf-8").read()
    errs += stamp_checks(readme, index, source or os.path.join(folder, "data", "entries.csv"))
    m = re.search(r"SHA-256 of (public-live-rows-[\da-z-]+\.csv) \(all (\d+) rows\) is ([0-9a-f]{64})", readme)
    if not m:
        return ["README: no printed checksum line"]
    name, n, printed = m.groups()
    path = os.path.join(folder, name)
    if not os.path.exists(path):
        return ["README names %s, which is not in the folder" % name]
    raw = open(path, "rb").read()
    real = sha(raw)
    if printed != real:
        errs.append("README printed %s but %s hashes to %s" % (printed, name, real))
    side = open(path + ".sha256").read().split()[0] if os.path.exists(path + ".sha256") else None
    if side != real:
        errs.append("%s.sha256 says %s, file hashes to %s" % (name, side, real))
    mi = re.search(r'<span id="printed">([0-9a-f]{64})', index)
    if not mi or mi.group(1) != real:
        errs.append("index.html printed %s, CSV hashes to %s" % (mi.group(1) if mi else None, real))
    me = re.search(r'id="csvdata"[^>]*>(.*?)</script>', index, re.S)
    emb = json.loads(me.group(1)) if me else None
    if emb is None or sha(emb.encode("utf-8")) != real:
        errs.append("index.html embedded CSV does not match %s" % name)
    jn = path[:-4] + ".json"
    import csv as _c, io as _io
    rows = list(_c.DictReader(_io.StringIO(raw.decode("utf-8"), newline="")))
    if int(n) != len(rows):
        errs.append("README says %s rows, CSV has %d" % (n, len(rows)))
    if os.path.exists(jn) and json.load(open(jn, encoding="utf-8")) != rows:
        errs.append("%s does not match the CSV" % os.path.basename(jn))
    return errs


def previous_manifests(folder, uid):
    """Latest manifest of each layout at or before this update (v1 and v2 are both checked)."""
    out = []
    for pat, rx in (("entry-hashes-v2-*.csv", r"entry-hashes-v2-(.+)\.csv$"), ("entry-hashes-2*.csv", r"entry-hashes-(2.+)\.csv$")):
        ms = []
        for m in glob.glob(os.path.join(folder, "manifest", pat)):
            u = re.search(rx, os.path.basename(m)).group(1)
            if u <= uid:
                ms.append((u, m))
        if ms:
            out.append(sorted(ms)[-1][1])
    return out


def housekeeping_ok(manifest, version, rid, before, after, rows):
    """Rule entries R-2026-10-24-A and R-2026-10-25-A. True if the change is a logged housekeeping edit; an error string if it
    is logged but breaks the rule; None if it is not logged (then it is an ordinary CHANGED error)."""
    log = [h for h in rc.read_housekeeping() if h["id"] == rid and h["layout"] == version]
    if not log:
        return None
    if not any(h["entry_sha256_before"] == before and h["entry_sha256_after"] == after for h in log):
        return "HOUSEKEEPING %s: log lists it but not fingerprint %s -> %s (%s)" % (rid, before, after, os.path.basename(manifest))
    src = None
    for line in open(manifest, encoding="utf-8"):
        if line.startswith("# source_file:"):
            src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(manifest))), line.split(":", 1)[1].strip())
    if not src or not os.path.exists(src):
        return "HOUSEKEEPING %s: cannot read the published file named by %s" % (rid, os.path.basename(manifest))
    import csv as _c
    old = next((r for r in _c.DictReader(open(src, encoding="utf-8", newline="")) if r["id"] == rid), None)
    new = next(r for r in rows if r["id"] == rid)
    if old is None or he.fingerprint(old, version) != before:
        return "HOUSEKEEPING %s: published row in %s does not match fingerprint %s" % (rid, os.path.basename(src), before)
    diff = [f for f in he.LAYOUTS[version] if he.norm(old.get(f, "")) != he.norm(new.get(f, ""))]
    logged = {h["field"] for h in rc.read_housekeeping() if h["id"] == rid}
    bad = [f for f in diff if f not in rc.HOUSEKEEPING_FIELDS or f not in logged or not rc.is_removal(old.get(f, ""), new.get(f, ""), f)]
    if bad:
        return "HOUSEKEEPING %s: not a housekeeping removal in %s (only %s may lose text or become OPEN, the test field may only lose text, and each must be logged)" % (rid, ", ".join(bad), ", ".join(rc.HOUSEKEEPING_FIELDS))
    return True


HOUSEKEPT = {}   # manifest path -> ids accepted as logged housekeeping edits (printed, never silent)


def manifest_problems(manifest, rows):
    version = he.manifest_version(manifest)
    want = {}
    with open(manifest, encoding="utf-8") as fh:
        import csv as _c
        for rec in _c.DictReader([l for l in fh if not l.startswith("#")]):
            want[rec["id"]] = rec["entry_sha256"]
    have = {r["id"]: he.fingerprint(r, version) for r in rows}
    errs, housekept = [], []
    for i, h in want.items():
        if i not in have:
            errs.append("VANISHED %s (in %s). The record is append only." % (i, os.path.basename(manifest)))
        elif have[i] != h:
            hk = housekeeping_ok(manifest, version, i, h, have[i], rows)
            if hk is True:
                housekept.append(i)
                continue
            if hk:
                errs.append(hk)
                continue
            sup = [r["id"] for r in rows if r.get("supersedes_id") == i]
            errs.append("CHANGED %s: fingerprint %s in %s, now %s. Prior entries are never edited; enter a new dated entry citing it%s." %
                        (i, h, os.path.basename(manifest), have[i], " (superseded by %s, but the original must stay unchanged)" % ", ".join(sup) if sup else ""))
    new = [i for i in have if i not in want]
    HOUSEKEPT[manifest] = housekept
    return errs, new


STAMP = {}


import check_published_unchanged as cpu

DATED_OUTPUT = re.compile(r"^(public-live-rows-.+\.(csv|json)|manifest/entry-hashes-v2-.+\.csv)(\.sha256)?$")


def published_conflicts(stage, rels):
    """Guardrail 1: dated outputs whose name is already published with different bytes."""
    if not os.path.exists(cpu.CACHE):
        raise rc.Fail("published-files list %s is missing; run scripts/check_published_unchanged.py --refresh first "
                      "(refusing to build without knowing what is already published)" % os.path.relpath(cpu.CACHE, ROOT))
    pub = cpu.read_cache()
    out = []
    for rel in rels:
        if DATED_OUTPUT.match(rel) and rel in pub:
            if cpu.blob_sha(open(os.path.join(stage, rel), "rb").read()) != pub[rel][0]:
                out.append(rel)
    return out


def sources_gate(iso, out_dir):
    """Hard gate (Barry approval 27 Oct 2026 15:17 CST): scripts/check_sources.py without --report-only, after the
    row checks and before any page is written. A build into the upload root also writes data/sources-check-counts.csv
    for the page note; draft and --out-dir builds run the gate read-only so the upload root stays untouched."""
    gate = [sys.executable, os.path.join(ROOT, "scripts", "check_sources.py"), "--staging", ROOT,
            "--allowlist", os.path.join(ROOT, "data", "sources-gate-allowlist.csv"), "--audit-date", iso]
    if os.path.abspath(out_dir) == os.path.abspath(ROOT):
        gate += ["--counts-out", SOURCES_COUNTS, "--counts-date", iso]
    # Forward-row fixtures (Barry go 27 Oct 2026 15:50 CST) run on every build, before the real gate.
    t = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "check_sources.py"), "--staging", ROOT, "--selftest"],
                       capture_output=True, text=True)
    if t.returncode != 0:
        raise rc.Fail("SOURCES GATE SELFTEST FAILED (forward-row fixtures)\n%s%s" % (t.stdout, t.stderr))
    g = subprocess.run(gate, capture_output=True, text=True)
    if g.returncode != 0:
        raise rc.Fail("SOURCES GATE FAILED (scripts/check_sources.py exit %d)\n%s%s" % (g.returncode, g.stdout, g.stderr))
    print("SOURCES GATE OK: " + g.stdout.splitlines()[0])


def build(uid, out_dir, source, allow_overwrite=False):
    header, rows = rc.read_source(source)
    STAMP.update(uid=uid, sha=sha(open(source, "rb").read()), n=len(rows))
    errs = rc.validate(header, rows)
    rows = rc.sort_rows(rows)
    iso, _ = rc.split_uid(uid)
    prevs = previous_manifests(ROOT, uid)
    new_ids = []
    for k, prev in enumerate(prevs):
        e2, n2 = manifest_problems(prev, rows)
        errs += e2
        if k == 0:
            new_ids = n2      # new since the latest manifest of the current layout
    if not prevs:
        errs.append("no previous manifest found in manifest/ (refusing to build without one)")
    od = rc.overdue_problems(rows, iso)
    if od and os.environ.get("REGISTER_OVERDUE") == "warn":   # tests of unrelated rules only; preflight never sets it
        print("OVERDUE GUARD SET TO WARN (test use only):\n" + "\n".join(od), file=sys.stderr)
    else:
        errs += od
    if errs:
        raise rc.Fail("\n".join(errs))
    sources_gate(iso, out_dir)
    csv_text = rc.write_csv_text(header, rows)
    csv_name, json_name = "public-live-rows-%s.csv" % uid, "public-live-rows-%s.json" % uid
    csv_sha = sha(csv_text.encode("utf-8"))
    readme = render_readme(open(os.path.join(ROOT, "README.md"), encoding="utf-8").read(), rows, csv_name, csv_sha, iso)
    index = render_index(open(os.path.join(ROOT, "index.html"), encoding="utf-8").read(), rows, csv_text, csv_name, json_name, csv_sha, iso)
    pe_path = os.path.join(ROOT, "plain-english.html")
    plain = apply_footer(open(pe_path, encoding="utf-8").read(), "plain-english.html") if os.path.exists(pe_path) else None
    json_text = json.dumps(rows, ensure_ascii=False, indent=1)
    for name, text in (("README.md", readme), ("index.html", index), (csv_name, csv_text), (json_name, json_text)) + ((("plain-english.html", plain),) if plain else ()):
        errs += rc.grammar_check_text(name, text)
    if errs:
        raise rc.Fail("\n".join(errs))
    stage = tempfile.mkdtemp(prefix="register-build-")
    os.makedirs(os.path.join(stage, "manifest"))
    open(os.path.join(stage, csv_name), "w", encoding="utf-8", newline="").write(csv_text)
    open(os.path.join(stage, csv_name + ".sha256"), "w").write("%s  %s\n" % (csv_sha, csv_name))
    open(os.path.join(stage, json_name), "w", encoding="utf-8").write(json_text)
    open(os.path.join(stage, "README.md"), "w", encoding="utf-8").write(readme)
    open(os.path.join(stage, "index.html"), "w", encoding="utf-8").write(index)
    if plain:
        open(os.path.join(stage, "plain-english.html"), "w", encoding="utf-8").write(plain)
    mname = "manifest/entry-hashes-v2-%s.csv" % uid
    mtext = he.manifest_text(os.path.join(stage, csv_name), rows, uid, "chr-entry-v2")
    if os.path.exists(rc.HOUSEKEEPING_LOG):
        hk = rc.read_housekeeping()
        hl = "# housekeeping_log: data/housekeeping-log.csv sha256 %s, %d logged removals in %d entries (rule entries R-2026-10-24-A and R-2026-10-25-A)\n" % (
            sha(open(rc.HOUSEKEEPING_LOG, "rb").read()), len({(h["id"], h["field"]) for h in hk}), len({h["id"] for h in hk}))
        mtext = mtext.replace("\nmanifest_date,id,", "\n" + hl + "manifest_date,id,", 1)
    open(os.path.join(stage, mname), "w", encoding="utf-8", newline="\n").write(mtext)
    open(os.path.join(stage, mname + ".sha256"), "w").write("%s  %s\n" % (sha(mtext.encode()), mname))
    errs = printed_checks(stage, source=source)
    e3, _ = manifest_problems(os.path.join(stage, mname), rows)
    errs += e3
    if errs:
        raise rc.Fail("post-build check failed:\n" + "\n".join(errs))
    rels = ("README.md", "index.html", csv_name, csv_name + ".sha256", json_name, mname, mname + ".sha256") + (("plain-english.html",) if plain else ())
    clash = [] if allow_overwrite else published_conflicts(stage, rels)
    if clash:
        shutil.rmtree(stage)
        raise rc.Fail("REFUSED: update id %s would overwrite already-published file(s) with different bytes: %s. "
                      "Published files are never replaced. Use the next free letter (for example --date %s<letter>), "
                      "or, only on Barry's explicit go, --allow-overwrite." % (uid, ", ".join(clash), uid))
    if allow_overwrite:
        print("WARNING: --allow-overwrite set; published-file guard skipped", file=sys.stderr)
    os.makedirs(os.path.join(out_dir, "manifest"), exist_ok=True)
    written = []
    for rel in rels:
        dst = os.path.join(out_dir, rel)
        if os.path.exists(dst) and open(dst, "rb").read() == open(os.path.join(stage, rel), "rb").read():
            status = "unchanged"
        else:
            status = "written"
        shutil.copyfile(os.path.join(stage, rel), dst)
        written.append((status, rel))
    shutil.rmtree(stage)
    return rows, csv_sha, prevs, new_ids, written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="update id YYYY-MM-DD, or YYYY-MM-DD plus a letter for a second update that day (required; never inferred)")
    ap.add_argument("--out-dir", default=ROOT)
    ap.add_argument("--source", default=rc.SOURCE)
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--draft", action="store_true", help="build into local/draft-build-<date>/; never writes the upload root (scoring and staging jobs)")
    ap.add_argument("--allow-overwrite", action="store_true", help="replace an already-published dated file; only on Barry's explicit go, never in routines")
    a = ap.parse_args()
    try:
        if a.verify:
            errs = printed_checks(ROOT)
            for n in ("README.md", "index.html"):
                errs += rc.grammar_check_text(n, open(os.path.join(ROOT, n), encoding="utf-8").read())
            if errs:
                raise rc.Fail("\n".join(errs))
            print("VERIFY OK: printed checksums match, grammar clean")
            return 0
        if not a.date:
            raise rc.Fail("--date YYYY-MM-DD is required")
        out_dir = os.path.abspath(a.out_dir)
        if a.draft:
            if out_dir != os.path.abspath(ROOT):
                raise rc.Fail("--draft and --out-dir are exclusive")
            out_dir = os.path.join(ROOT, "local", "draft-build-%s" % a.date)
        rows, csv_sha, prevs, new_ids, written = build(a.date, out_dir, a.source, a.allow_overwrite)
        if a.draft:
            print("DRAFT build in %s (upload root untouched)" % os.path.relpath(out_dir, ROOT))
        print("BUILD OK %s: %d entries, CSV sha256 %s" % (a.date, len(rows), csv_sha))
        for prev in prevs:
            hk = HOUSEKEPT.get(prev, [])
            print("checked against previous manifest %s (%s): 0 changed, 0 vanished%s" % (os.path.relpath(prev, ROOT), he.manifest_version(prev),
                  ", %d housekeeping edits as logged in data/housekeeping-log.csv %s" % (len(hk), hk) if hk else ""))
        print("%d new since the latest manifest %s" % (len(new_ids), new_ids if new_ids else ""))
        for s, rel in written:
            print("  %-9s %s" % (s, rel))
        return 0
    except rc.Fail as e:
        print("BUILD FAILED\n" + str(e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
