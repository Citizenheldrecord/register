"""Display-only reading aids (proposed rule entry R-2026-10-22-A, staged, needs Barry's go).
Nothing here changes an entry, a status, a date, a score or a fingerprint. It reads
data/entries.csv and data/essay-links.csv and writes page furniture only."""
import csv, html, json, os, re
from datetime import date, timedelta
import regcore as rc

LINKS = os.path.join(rc.ROOT, "data", "essay-links.csv")
E = html.escape


def load_links(path=LINKS):
    if not os.path.exists(path):
        return {}
    return {r["id"]: r for r in csv.DictReader(open(path, encoding="utf-8"))}


def check_links(rows, links):
    ids = {r["id"] for r in rows}
    errs = ["essay-links.csv: id %s is not an entry" % i for i in links if i not in ids]
    errs += ["essay-links.csv: %s url is not a barryesharp.substack.com essay" % i for i, l in links.items() if not l["essay_url"].startswith("https://barryesharp.substack.com/p/")]
    return errs


def _open(rows):
    closers = rc.closed_by(rows)
    return [r for r in rows if r["status"] == "LIVE" and r["id"] not in closers and not rc.is_resolved(r)], closers


def status_summary(rows, iso):
    open_, closers = _open(rows)
    d0 = date.fromisoformat(iso)
    end = (d0 + timedelta(days=30)).isoformat()
    proposed = [r for r in rows if r["status"] == "PROPOSED"]
    scoring = [r for r in rows if rc.is_resolved(r)]
    passes = [r for r in scoring if "PASS" in r["status"]]
    fails = [r for r in scoring if "FAILED" in r["status"]]
    past = sorted([r for r in open_ if r["sort_date"] < iso], key=lambda r: (r["sort_date"], r["id"]))
    soon = sorted([r for r in open_ if iso <= r["sort_date"] <= end], key=lambda r: (r["sort_date"], r["id"]))
    secs = ", ".join("%s %d" % (s, sum(1 for r in rows if r["section"] == s)) for s in rc.SECTION_ORDER)
    a = lambda r: '<a href="#row-%s">%s</a>' % (E(r["id"]), E(r["id"]))
    pastline = ", ".join("%s (%s)" % (a(r), E(r["scoring_date"])) for r in past) or "none"
    soonrows = "".join("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (E(r["scoring_date"]), a(r), E(r["section"]), E(r["owner"])) for r in soon)
    return ('<!-- STATUS-SUMMARY --><div class="panel summary"><b>Status at a glance, as at %s</b>'
            '<p>%d entries. Open and waiting for their scoring date: %d. Closed by a scoring entry: %d. Scoring entries: %d (PASS %d, FAILED %d, recorded as fact %d). Proposed, not yet live: %d.</p>'
            '<p>By section: %s.</p>'
            '<p><b>Past their scoring date and not yet scored: %s.</b></p>'
            '<details><summary>Due in the next 30 days (%d), to %s</summary><table><thead><tr><th>Scoring date</th><th>ID</th><th>Section</th><th>Owner</th></tr></thead><tbody>%s</tbody></table></details>'
            '<p class="small">Built from the table below each update. Display only: it changes no entry.</p></div><!-- /STATUS-SUMMARY -->\n'
            % (rc.long_date(iso), len(rows), len(open_), len(closers), len(scoring), len(passes), len(fails), len(scoring) - len(passes) - len(fails),
               len(proposed), secs, pastline, len(soon), rc.long_date(end), soonrows or '<tr><td colspan="4" class="empty">None.</td></tr>'))


def how_to_read(rows, links):
    ex = next(r for r in rows if r["id"] == "HR5334")
    lk = links.get("HR5334")
    essay = '<a href="%s">%s</a>' % (E(lk["essay_url"]), E(lk["essay_title"])) if lk else "OPEN"
    return ('<!-- HOW-TO-READ --><div class="panel"><b>How to read this page</b>'
            '<p>Each row is one public promise turned into a test. It says what counts as a pass, the one date it is scored, and who answers for it. Nothing on the page argues. The essays argue; this page keeps the score.</p>'
            '<ul><li><b>LIVE</b>: the test is set and waiting for its date.</li>'
            '<li><b>PROPOSED</b>: drafted, not yet a live test.</li>'
            '<li><b>PASS</b> or <b>FAILED</b>: the result on the scoring date. A result is a new row; the old row is never edited. A scored row shows as CLOSED and links to the row that scored it.</li>'
            '<li><b>OPEN</b> in a cell: not yet found in a public source. It is never filled with a guess.</li>'
            '<li><b>Sections</b>: Canadian files; this desk\'s own commitments; outside files we watch; recorded facts and checkpoints, which are dated records rather than pass or fail tests.</li>'
            '<li><b>Essay</b>: the column that names the essay that set the test, with a link once it is published.</li></ul>'
            '<p><b>One worked example.</b> Row <a href="#row-HR5334">HR5334</a>. The test: which applied on %s, a United States rate, a written waiver, or neither. Owner: %s. Date source: %s. Result: %s, recorded as fact. Essay: %s.</p>'
            '<p>To check a row yourself, download the CSV below and compare it with the checksum printed on this page. The rules underneath say exactly how.</p></div><!-- /HOW-TO-READ -->\n'
            % (E(ex["scoring_date"]), E(ex["owner"]), E(ex["date_source"]), E(ex["status"]), essay))


def essays_index(rows, links):
    by = {}
    for r in rows:
        l = links.get(r["id"])
        if l:
            by.setdefault((l["essay_url"], l["essay_title"], l["essay_live_date"]), []).append(r["id"])
    items = sorted(by.items(), key=lambda kv: (rc.parse_short(kv[0][2]) if hasattr(rc, "parse_short") else kv[0][2]), reverse=True)
    lis = "".join('<li><a href="%s">%s</a> (%s): %s</li>' % (E(u), E(t), E(d), ", ".join('<a href="#row-%s">%s</a>' % (E(i), E(i)) for i in ids)) for (u, t, d), ids in items)
    pending = sorted({re.sub(r"[\[\]]", "", r["argument"]) for r in rows if r["argument"].startswith("[publishes") and r["id"] not in links})
    return ('<!-- ESSAYS --><h2>Essays that set tests</h2><p>Each published essay and the rows it set. Rows whose essay is not yet published read OPEN or show the planned date in the essay column.</p><ul>%s</ul><!-- /ESSAYS -->\n' % lis)


def links_json(links):
    return json.dumps({i: {"t": l["essay_title"], "u": l["essay_url"], "d": l["essay_live_date"]} for i, l in links.items()}, ensure_ascii=False).replace("</", "<\\/")


# --- Display-only hiding of internal desk references (rule R-2026-10-22-A; correction 22 Oct 2026).
# Generic patterns only: the hidden text itself is never written to the page's display layer.
MARK = "[internal desk reference hidden in display, 22 Oct 2026]"
HIDE = [
    re.compile(r"(?:drafts|raw|local)/[\w.\-/]+"),
    re.compile(r"\b[\w\-]+\.(?:md|py|txt)\b"),
    re.compile(r"\s*\((?:[^()]*\bSOFTS\b[^()]*)\)"),
    re.compile(r"\s*\((?:[^()]*\bledger \d{1,2} \w{3}\b[^()]*)\)"),
]
SCAN = re.compile(r"(drafts/|raw/|local/|\.md\b|\.py\b|\bSOFTS\b|\bledger \d{1,2} \w{3}\b|\broutine\b|\bdispatcher\b|DESK_DISPATCH|SCORING_CALENDAR|HOUSE_RULES|\b(?:PUBLISH|DRAFT|SIT|PRIME|CANON|JOIN|LIVE)-[\w\-]+)", re.I)
FIELDS = ("test", "owner", "date_source", "status", "measure", "money", "argument", "cost_to_date")


def display_fixes(rows):
    out = {}
    for r in rows:
        for f in FIELDS:
            v = r.get(f, "") or ""
            n = v
            for p in HIDE:
                n = p.sub(lambda m: (" " if m.group(0).startswith((" ", "(")) or m.group(0)[:1].isspace() else "") + MARK, n)
            if n != v:
                out.setdefault(r["id"], {})[f] = n.strip()
    return out


def scan_internal(rows):
    """Problems: any displayed field that still shows an internal reference after hiding."""
    fx = display_fixes(rows)
    errs = []
    for r in rows:
        for f in FIELDS:
            v = fx.get(r["id"], {}).get(f, r.get(f, "") or "")
            m = SCAN.search(v)
            if m:
                errs.append("%s.%s shows internal text near %r" % (r["id"], f, v[max(0, m.start() - 20):m.end() + 20]))
    return errs


def fixes_json(rows):
    return json.dumps(display_fixes(rows), ensure_ascii=False).replace("</", "<\\/")
