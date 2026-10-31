#!/usr/bin/env python3
"""Display layer, added 30 Oct 2026 (Barry go t2573u). Reads data/entries.csv and sources/<id>.md,
never writes them. Writes data/row-annotations.csv (test origin, plain summary, primary source link)
and returns the front-door HTML block and the annotations JSON for index.html.
Classification is mechanical from each row's own date_source text and its sources record; where the
text does not show who set the date, the value is UNCLEAR."""
import csv, glob, html, io, json, os, re, sys, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import regcore as rc
ROOT = rc.ROOT
OUT = os.path.join(ROOT, "data", "row-annotations.csv")
MON = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
GOV_PREFIX = ("GOVERNMENT", "STATUTE", "STATUTORY", "SCHEDULED", "DOCKET", "HOUSE CALENDAR", "LEGAL DEADLINE",
              "HOLDER DATE", "INQUIRY REQUIREMENT", "DATE ANCHOR")
COMPANY = ("COMPANY", "PRIMARY: Sherritt", "Merck and Moderna")


def clean(s):
    s = s.replace("\u2014", ", ").replace("\u2013", " to ").replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    s = re.sub(r"(\d)\s*%", r"\1 per cent", s)
    return re.sub(r"\s+", " ", s).strip()


def iso_of(txt):
    m = re.match(r"(\d{1,2}) ([A-Za-z]{3})[a-z]* (\d{4})", txt)
    if not m or m.group(2).lower() not in MON: return None
    try: return datetime.date(int(m.group(3)), MON[m.group(2).lower()], int(m.group(1))).isoformat()
    except ValueError: return None


def first_public():
    seen = {}
    for p in sorted(glob.glob(os.path.join(ROOT, "public-live-rows-*.csv"))):
        tag = os.path.basename(p)[len("public-live-rows-"):-4]
        d = tag[:10]
        for r in csv.DictReader(open(p, encoding="utf-8", newline="")):
            i = r.get("id")
            if i and (i not in seen or d < seen[i]): seen[i] = d
    return seen


def origin(r, fp):
    ds = (r["date_source"] or "").strip(); up = ds.upper()
    head = up.split(":")[0]
    if up.startswith("DESK") or re.match(r"(DATE ANCHOR|PROPOSED): DESK", up):
        who, why = "DESK", "date source names a desk-set date"
    elif "DESK-SET" in up or "DESK-FIXED" in up or "DESK DATE" in up or "DESK TEST DATE" in up:
        who, why = "MIXED", "outside date with a scoring date or window set by the desk"
    elif ds.startswith(COMPANY):
        who, why = "UNCLEAR", "date set by a company, not a government"
    elif head.startswith(GOV_PREFIX):
        who, why = "GOVERNMENT", "date source cites a government, legislature, court or statute"
    else:
        who, why = "UNCLEAR", "date source does not show who set the date"
    when = "UNCLEAR"
    if who in ("DESK", "MIXED"):
        m = re.search(r"Barry go (\d{1,2} [A-Z][a-z]{2,8} \d{4})", ds)
        when = (m and iso_of(m.group(1))) or fp.get(r["id"]) or "UNCLEAR"
    elif who == "GOVERNMENT":
        m = re.search(r"(?:release|statement|remarks|order|notice|dated|published|announced|tabled|issued|letter|speech|plan|budget|report)[^.;]{0,40}?(?:of |on |, )?(\d{1,2} [A-Z][a-z]{2,8} \d{4})", ds)
        when = (m and iso_of(m.group(1))) or "UNCLEAR"
    return who, when, why


def source_link(r):
    p = os.path.join(ROOT, "sources", r["id"].replace("/", "-") + ".md")
    if not os.path.exists(p):
        p2 = os.path.join(ROOT, "sources", r["id"] + ".md")
        p = p2 if os.path.exists(p2) else None
    txt = open(p, encoding="utf-8").read() if p else ""
    for m in re.finditer(r"^- Primary URL:\s*(https?://\S+)", txt, re.M):
        return m.group(1).rstrip(").,;"), "primary"
    rowtxt = " ".join(r[k] for k in ("date_source", "measure", "money", "test"))
    if re.search(r"https?://", rowtxt) or re.search(r"https?://", txt):
        return "", "secondary source only"
    return "", "no source link yet"


def summary(r):
    t = clean(r["test"])
    m = re.match(r"(?:PASS:\s*)?(.*?)(?:\.\s*FAILED:.*)?$", t)
    p = m.group(1) if m else t
    if len(p) > 220: p = p[:220].rsplit(" ", 1)[0] + "..."
    st = clean(r["status"])
    return clean("%s; owner: %s; scored on %s. Status: %s." % (p.rstrip("."), r["owner"], r["scoring_date"], st))


def build():
    rows = rc.load_rows() if hasattr(rc, "load_rows") else list(csv.DictReader(open(os.path.join(ROOT, "data", "entries.csv"), encoding="utf-8", newline="")))
    fp = first_public()
    out = []
    for r in rows:
        who, when, why = origin(r, fp)
        link, flag = source_link(r)
        out.append({"id": r["id"], "test_set_by": who, "test_set_date": when, "test_set_basis": why,
                    "summary": summary(r), "primary_source_url": link, "source_flag": flag})
    return rows, out


def write_csv(out):
    b = io.StringIO(); w = csv.DictWriter(b, fieldnames=list(out[0]), lineterminator="\n"); w.writeheader(); w.writerows(out)
    open(OUT, "w", encoding="utf-8", newline="").write(b.getvalue())


TERMS = [
    ("PASS", "PASS", "the test was met by its scoring date, read against a primary source."),
    ("FAILED", "FAILED", "the test was not met by its scoring date. A failed entry is published within 30 days and names the layer that blocked it."),
    ("LIVE", "LIVE", "the test is set and waiting for its date."),
    ("Open", "Open", "live, not scored, scoring date on or after the count date."),
    ("Due", "Due", "live, not scored, scoring date before the count date."),
    ("PROPOSED", "PROPOSED", "drafted, not yet a live test."),
    ("SCORED", "SCORED", "a scoring entry: a new row that records the result against an earlier promise. The old row is never edited."),
    ("CLOSED", "CLOSED", "a promise that has been scored; it links to the row that scored it."),
    ("REPLACED", "Replaced", "an entry superseded by a later entry with a new date or a correction. The old entry stays in the record."),
    ("RECORDED", "Recorded as fact", "a dated fact or baseline kept in the record with no pass or fail line."),
    ("Repeating", "Repeating", "a test with no single scoring day."),
    ("Baseline", "Baseline", "a recorded starting point, not counted as PASS or FAILED."),
    ("OPEN", "OPEN (in a cell)", "no primary source yet shows the value; nothing is estimated."),
    ("DESK-SET", "DESK-SET", "the scoring date was chosen by this register, not by the government."),
    ("blocking layer", "Blocking layer", "the part of the system a FAILED entry names as the reason it failed, for example executive, financing, court, regulatory or political choice."),
    ("closers", "Closers", "four land-title fixes the register records party positions on: finality with transfer phase-down; a closed-versus-open register; an ICA-equivalent screen; statutory fee-simple certainty."),
    ("financed twice", "Financed twice", "a corridor or project that has reached a second construction financing, used as a test of whether capital comes back."),
    ("lender-readable", "Lender-readable title", "land title that a lender can rely on to finance a project."),
    ("title map", "Title map", "the map of unsettled land-title claims; a test passes when dated settlements make it smaller."),
    ("master clock", "Master clock", "a desk-set reference date that several related rows are tied to."),
    ("rooms", "Rooms", "summits, meetings and negotiating tables where promises are announced; what is said in a room is a lead, not a result."),
    ("SET-AND-WAIVED", "SET-AND-WAIVED", "recorded fact on HR5334: the duty was set at its legal rate and then waived in writing."),
    ("FA5", "FA5 (and other short codes)", "row IDs. Each ID names one test; search the table for it."),
    ("hype_score", "Hype, means and cost scores", "three sub-scores given when an entry is resolved, each MATCHED, MIXED, FAILED or OPEN. They never change the PASS or FAILED."),
    ("CASELOAD-COUPLED", "CASELOAD-COUPLED", "the budget line grows with the volume of the problem."),
    ("FIXED-OUTCOME", "FIXED-OUTCOME", "the money is tied to a named deliverable or milestone."),
    ("TIME-LIMITED", "TIME-LIMITED", "the money sunsets on a printed end date."),
    ("fingerprint", "Fingerprint", "the SHA-256 checksum of an entry's canonical text, taken the day it goes in, so any later edit shows."),
    ("GOVERNMENT", "Set by: GOVERNMENT / DESK / MIXED / UNCLEAR", "who named the deadline or target. GOVERNMENT: the government, a court or the law itself. DESK: this register chose it. MIXED: an outside date with a scoring window set by the register. UNCLEAR: the row's text does not show it."),
]


def front_door(rows, ann, iso, page_text):
    c = rc.count_states(rows, iso)
    st = c["state"]
    by = {a["id"]: a["test_set_by"] for a in ann}
    order = list(rc.STATE_ORDER)
    E = lambda s: html.escape(s, quote=False)
    def line(ids):
        return ", ".join("%s %d" % (k, sum(1 for i in ids if st[i] == k)) for k in order)
    allp = list(st)
    groups = [("Government-set", [i for i in allp if by.get(i) == "GOVERNMENT"]), ("Desk-set", [i for i in allp if by.get(i) == "DESK"]),
              ("Mixed", [i for i in allp if by.get(i) == "MIXED"]), ("Unclear", [i for i in allp if by.get(i) == "UNCLEAR"])]
    rows_html = "".join("<tr><td>%s</td><td>%d</td>%s</tr>" % (g, len(ids), "".join("<td>%d</td>" % sum(1 for i in ids if st[i] == k) for k in order)) for g, ids in groups)
    rows_html += "<tr><td><b>All promises</b></td><td><b>%d</b></td>%s</tr>" % (len(allp), "".join("<td><b>%d</b></td>" % sum(1 for i in allp if st[i] == k) for k in order))
    allrows = {"GOVERNMENT": 0, "DESK": 0, "MIXED": 0, "UNCLEAR": 0}
    for a in ann: allrows[a["test_set_by"]] += 1
    prim = sum(1 for a in ann if a["source_flag"] == "primary")
    d = datetime.date.fromisoformat(iso)
    hay = page_text
    gl = "".join("<li><b>%s</b>: %s</li>" % (E(n), E(dfn)) for key, n, dfn in TERMS if key in hay)
    return ('<!-- FRONT-DOOR --><section class="frontdoor" style="border:2px solid #333;padding:0.8em 1em;margin:1em 0">'
            "<h2>What this register is</h2>"
            "<p>Governments often announce promises without a checkable outcome, a date and a named owner, and the process of announcing stands in for results. "
            "This register writes each promise down as a test: what counts as done, the date it is scored and who answers for it. "
            "On that date it scores the test PASS or FAILED against primary sources, and it keeps every entry, changed or not, in a public record held by citizens.</p>"
            "<h3>The tally, counted from data/entries.csv on %d %s</h3>"
            "<p>%d entries = %d promises + %d scoring entries. Of the %d promises: %s.</p>"
            '<div style="overflow-x:auto"><table><thead><tr><th>Who set the test date</th><th>Promises</th>%s</tr></thead><tbody>%s</tbody></table></div>'
            "<p>All %d rows by who set the test: government %d, desk %d, mixed %d, unclear %d. Rows with a primary source link: %d; flagged with no primary link: %d. "
            'Per-row detail is in <a href="data/row-annotations.csv">data/row-annotations.csv</a>, a display layer; the fingerprinted entries are not changed.</p>'
            "<details><summary>Glossary of terms used on this page</summary><ul>%s</ul></details>"
            "</section><!-- /FRONT-DOOR -->\n") % (
        d.day, d.strftime("%B %Y"), c["total"], c["promises"], c["scoring_entries"], c["promises"], line(allp),
        "".join("<th>%s</th>" % k for k in order), rows_html,
        len(ann), allrows["GOVERNMENT"], allrows["DESK"], allrows["MIXED"], allrows["UNCLEAR"], prim, len(ann) - prim, gl)


def ann_json(ann):
    j = {a["id"]: {"by": a["test_set_by"], "on": a["test_set_date"], "s": a["summary"], "u": a["primary_source_url"], "f": a["source_flag"]} for a in ann}
    return '<script type="application/json" id="annotations">' + json.dumps(j, ensure_ascii=True).replace("</", "<\\/") + "</script>"


if __name__ == "__main__":
    rows, ann = build(); write_csv(ann)
    import collections
    print("row-annotations:", len(ann), dict(collections.Counter(a["test_set_by"] for a in ann)), dict(collections.Counter(a["source_flag"] for a in ann)))
