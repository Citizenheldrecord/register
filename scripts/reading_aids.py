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
    c = rc.count_states(rows, iso)
    n = {k: sum(1 for v in c["state"].values() if v == k) for k in rc.STATE_ORDER}
    d0 = date.fromisoformat(iso)
    end = (d0 + timedelta(days=30)).isoformat()
    byid = {r["id"]: r for r in rows}
    past = sorted([byid[i] for i in c["due_days"]], key=lambda r: (r["sort_date"], r["id"]))
    soon = sorted([byid[i] for i, v in c["state"].items() if v == "Open" and byid[i]["sort_date"] <= end], key=lambda r: (r["sort_date"], r["id"]))
    secs = ", ".join("%s %d" % (s, sum(1 for r in rows if r["section"] == s)) for s in rc.SECTION_ORDER)
    a = lambda r: '<a href="#row-%s">%s</a>' % (E(r["id"]), E(r["id"]))
    def pl(r):
        p = rc.pending_reason(r["id"], iso)
        return "%s (%s%s)" % (a(r), E(r["scoring_date"]), ("; scoring pending, noted %s, read again by %s" % (E(rc.long_date(p["noted"])), E(rc.long_date(p["recheck_by"])))) if p else "")
    pastline = ", ".join(pl(r) for r in past) or "none"
    soonrows = "".join("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (E(r["scoring_date"]), a(r), E(r["section"]), E(display_fixes([r]).get(r["id"], {}).get("owner", r["owner"]))) for r in soon)
    basis = {}
    for r in rows:
        basis[date_basis(r)] = basis.get(date_basis(r), 0) + 1
    return ('<!-- STATUS-SUMMARY --><div class="panel summary"><b>Status at a glance, as at %s</b>'
            '<p>%d entries = %d promises + %d scoring entries. Of the %d promises: PASS %d, FAILED %d, recorded as fact %d, open %d, due %d, replaced %d, proposed %d, repeating %d. The same numbers, with their definitions, are in the count block on this page.</p>'
            '<p>By section: %s.</p>'
            '<p>Date basis: %d entries have a benchmark date set by the register, %d an outside date with a scoring window set by the register, %d a date set by an outside source. Each row is labelled in its date source cell.</p>'
            '<p><b>Past their scoring date and not yet scored: %s.</b></p>'
            '<details><summary>Due in the next 30 days (%d), to %s</summary><table><thead><tr><th>Scoring date</th><th>ID</th><th>Section</th><th>Owner</th></tr></thead><tbody>%s</tbody></table></details>'
            '<p class="small">Built from data/entries.csv each update. Display only: it changes no entry.</p></div><!-- /STATUS-SUMMARY -->\n'
            % (rc.long_date(iso), c["total"], c["promises"], c["scoring_entries"], c["promises"], n["PASS"], n["FAILED"], n["Recorded"], n["Open"], n["Due"],
               n["Replaced"], n["Proposed"], n["Repeating"], secs, basis.get("desk", 0), basis.get("mixed", 0), basis.get("outside", 0),
               pastline, len(soon), rc.long_date(end), soonrows or '<tr><td colspan="4" class="empty">None.</td></tr>'))


def how_to_read(rows, links):
    ex = next(r for r in rows if r["id"] == "HR5334")
    lk = links.get("HR5334")
    essay = '<a href="%s">%s</a>' % (E(lk["essay_url"]), E(lk["essay_title"])) if lk else "OPEN"
    return ('<!-- HOW-TO-READ --><div class="panel"><b>How to read this page</b>'
            '<p>Each row is one public promise turned into a test. It says what counts as a pass, the one date it is scored, and who answers for it. Nothing on the page argues. The essays argue; this page keeps the score.</p>'
            '<ul><li><b>LIVE</b>: the test is set and waiting for its date.</li>'
            '<li><b>PROPOSED</b>: drafted, not yet a live test.</li>'
            '<li><b>PASS</b> or <b>FAILED</b>: the result on the scoring date. A result is a new row; the old row is never edited. A scored row shows as CLOSED and links to the row that scored it.</li>'
            '<li><b>Follow-ups</b>: a PASS is not delivery. Each promise is tracked from the very start to total completion: every PASS gets a new follow-up row testing the next real step, linked back by its follows_id and shown as (follows ID), and the chain closes only at full delivery or at a recorded FAILED.</li>'
            '<li><b>Fill once</b>: a row\'s blank result cells are filled once, on or after its scoring date, each pointing to a dated entry added at the bottom; after that the row is frozen and any correction is a new dated entry.</li>'
            '<li><b>Date basis</b>: each date source cell starts with a label. A benchmark set by the register is a date this desk chose to test a promise against; it is not a date the owner set. Other dates come from a court, statute, government, company or scheduled release.</li>'
            '<li><b>OPEN</b> in a cell: not yet found in a public source. It is never filled with a guess.</li>'
            '<li><b>Sections</b>: Canadian files; this desk\'s own commitments; outside files we watch; recorded facts and checkpoints, which are dated records rather than pass or fail tests.</li>'
            '<li><b>Essay</b>: the column that names the essay that set the test, with a link once it is published.</li></ul>'
            '<p><b>One worked example.</b> Row <a href="#row-HR5334">HR5334</a>. The test: which applied on %s, a United States rate, a written waiver, or neither. Owner: %s. Date source: %s. Result: %s, recorded as fact. Essay: %s.</p>'
            '<p>To check a row yourself, download the CSV below and compare it with the checksum printed on this page. The rules underneath say exactly how.</p></div><!-- /HOW-TO-READ -->\n'
            % (E(ex["scoring_date"]), E(display_fixes([ex]).get(ex["id"], {}).get("owner", ex["owner"])), E(ex["date_source"]), E(ex["status"]), essay))


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
SCAN = re.compile(r"(drafts/|raw/|local/|\.md\b|\.py\b|\bSOFTS\b|\bCoS\b|\bledger \d{1,2} \w{3}\b|\broutine\b|\bdispatcher\b|DESK_DISPATCH|SCORING_CALENDAR|HOUSE_RULES|\b(?:PUBLISH|DRAFT|SIT|PRIME|CANON|JOIN|LIVE)-[\w\-]+)", re.I)
FIELDS = ("test", "owner", "date_source", "status", "measure", "money", "argument", "cost_to_date")


# Date basis label (25 October 2026). Display only, derived from the start of the date source field:
# no entry changes. DESK-SET at the start: the register chose the date as a benchmark. Any other
# prefix (DOCKET, STATUTE, SCHEDULED RELEASE, GOVERNMENT PROMISE, COMPANY TIMETABLE and so on):
# the date comes from an outside source; if DESK-SET appears later in the field, the register set
# the scoring window around that outside date.
BASIS = {"desk": "[Date basis: benchmark set by the register]",
         "mixed": "[Date basis: outside date, scoring window set by the register]",
         "outside": "[Date basis: set by an outside source]"}


def date_basis(r):
    d = (r.get("date_source") or "").strip()
    if d.upper().startswith("DESK-SET"):
        return "desk"
    return "mixed" if "DESK-SET" in d.upper() else "outside"


def display_fixes(rows):
    out = {}
    for r in rows:
        for f in FIELDS:
            v = r.get(f, "") or ""
            n = v
            for p in HIDE:
                n = p.sub(lambda m: (" " if m.group(0).startswith((" ", "(")) or m.group(0)[:1].isspace() else "") + MARK, n)
            n = n.replace("(CoS-assigned, unverified)", "(owner named by the register, unverified)")  # display only
            if f == "date_source":
                n = BASIS[date_basis(r)] + " " + n
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
            v = re.sub(r"https?://\S+", "", v)  # a public URL is not internal text (e.g. pm.gc.ca/.../prime-minister-...)
            m = SCAN.search(v)
            if m:
                errs.append("%s.%s shows internal text near %r" % (r["id"], f, v[max(0, m.start() - 20):m.end() + 20]))
    return errs


def fixes_json(rows):
    return json.dumps(display_fixes(rows), ensure_ascii=False).replace("</", "<\\/")
