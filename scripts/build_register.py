#!/usr/bin/env python3
"""Build the Citizen-Held Register from the one canonical source, data/entries.csv.

  python3 scripts/build_register.py --date 2026-10-18              build into the repository
  python3 scripts/build_register.py --date 2026-10-18 --out-dir X  build into a scratch folder
  python3 scripts/build_register.py --verify                       check the published files only

Fails loudly (exit 1, every problem listed) if: a row breaks the data rules
(outcome, scoring date, owner, cost to date, sub-scores on resolved entries,
supersedes fields), house grammar fails anywhere public, a prior entry changed or
vanished against the previous manifest, or a printed checksum does not match.
Nothing is written to the repository unless every check passes.
"""
import argparse, glob, hashlib, json, os, re, shutil, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import regcore as rc
import hash_entries as he

ROOT = rc.ROOT


def sha(b):
    return hashlib.sha256(b).hexdigest()


def one(pattern, repl, text, name, flags=0):
    new, n = re.subn(pattern, repl, text, flags=flags)
    if n == 0:
        raise rc.Fail("%s: template anchor not found: %s" % (name, pattern))
    return new


TABLE_COLS = "ID | Test | Owner | Scoring date | Date source | Status | Measure | Money | Funding | Argument | Cost to date"
TABLE_KEYS = ["id", "test", "owner", "scoring_date", "date_source", "status", "measure", "money", "funding", "argument", "cost_to_date"]
SECTION_HEADS = {
    "CANADA": "Canadian files (%d), in order of scoring date",
    "DESK": "This desk's own commitments (%d)",
    "WATCH": "Outside files we watch (%d)",
    "RECORDED": "Recorded facts and checkpoints (%d)",
}
RECORDED_LEAD = "These files record a fact, a status or a condition, or carry a reading or a scoring day the main table does not use. They are dated and kept, and are not counted in the main table.\n\n"


def tables(rows):
    closers = rc.closed_by(rows)
    cell = lambda r, k: rc.display_status(r, closers) if k == "status" else r.get(k, "")
    out = ""
    for s in rc.SECTION_ORDER:
        rs = [r for r in rows if r["section"] == s]
        out += SECTION_HEADS[s] % len(rs) + "\n\n"
        if s == "RECORDED":
            out += RECORDED_LEAD
        out += TABLE_COLS + "\n\n" + "".join(" | ".join(cell(r, k) for k in TABLE_KEYS) + "\n\n" for r in rs)
    return out


def render_readme(tpl, rows, csv_name, csv_sha, iso):
    ld = rc.long_date(iso)
    t = one(r"Entries as at \d+ \w+ \d{4}\. Last change: \d+ \w+ \d{4}\.", "Entries as at %s. Last change: %s." % (ld, ld), tpl, "README")
    t = one(r"Checksum for this update: SHA-256 of public-live-rows-\d{4}-\d\d-\d\d[a-z]?\.csv \(all \d+ rows\) is [0-9a-f]{64}",
            "Checksum for this update: SHA-256 of %s (all %d rows) is %s" % (csv_name, len(rows), csv_sha), t, "README")
    t = one(r"No entries as at \d+ \w+ \d{4}\.", "No entries as at %s." % ld, t, "README")
    a, b = t.find("Canadian files ("), t.find("Failure log\n")
    if a < 0 or b < a:
        raise rc.Fail("README: table block anchors not found")
    return t[:a] + tables(rows) + t[b:]


def render_index(tpl, rows, csv_text, csv_name, json_name, csv_sha, iso):
    ld = rc.long_date(iso)
    t = one(r'(id="csvdata"[^>]*>).*?(</script>)', lambda m: m.group(1) + json.dumps(csv_text, ensure_ascii=False).replace("</", "<\\/") + m.group(2), tpl, "index.html", re.S)
    t = one(r'(<span id="printed">)[0-9a-f]{64}', r"\g<1>" + csv_sha, t, "index.html")
    t = one(r"SHA-256 of public-live-rows-\d{4}-\d\d-\d\d[a-z]?\.csv \(all \d+ rows\)", "SHA-256 of %s (all %d rows)" % (csv_name, len(rows)), t, "index.html")
    t = one(r'"public-live-rows-\d{4}-\d\d-\d\d[a-z]?\.csv"', '"%s"' % csv_name, t, "index.html")
    t = one(r'"public-live-rows-\d{4}-\d\d-\d\d[a-z]?\.json"', '"%s"' % json_name, t, "index.html")
    t = one(r"<h2>Entries \(\d+\)</h2>", "<h2>Entries (%d)</h2>" % len(rows), t, "index.html")
    t = one(r"Entries as at \d+ \w+ \d{4}\. Last change: \d+ \w+ \d{4}\.", "Entries as at %s. Last change: %s." % (ld, ld), t, "index.html")
    t = one(r"No entries as at \d+ \w+ \d{4}\.", "No entries as at %s." % ld, t, "index.html")
    return t


def printed_checks(folder, iso=None):
    """Every printed checksum must equal the CSV it names. Returns problems."""
    errs = []
    readme = open(os.path.join(folder, "README.md"), encoding="utf-8").read()
    index = open(os.path.join(folder, "index.html"), encoding="utf-8").read()
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


def manifest_problems(manifest, rows):
    version = he.manifest_version(manifest)
    want = {}
    with open(manifest, encoding="utf-8") as fh:
        import csv as _c
        for rec in _c.DictReader([l for l in fh if not l.startswith("#")]):
            want[rec["id"]] = rec["entry_sha256"]
    have = {r["id"]: he.fingerprint(r, version) for r in rows}
    errs = []
    for i, h in want.items():
        if i not in have:
            errs.append("VANISHED %s (in %s). The record is append only." % (i, os.path.basename(manifest)))
        elif have[i] != h:
            sup = [r["id"] for r in rows if r.get("supersedes_id") == i]
            errs.append("CHANGED %s: fingerprint %s in %s, now %s. Prior entries are never edited; enter a new dated entry citing it%s." %
                        (i, h, os.path.basename(manifest), have[i], " (superseded by %s, but the original must stay unchanged)" % ", ".join(sup) if sup else ""))
    new = [i for i in have if i not in want]
    return errs, new


def build(uid, out_dir, source):
    header, rows = rc.read_source(source)
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
    if errs:
        raise rc.Fail("\n".join(errs))
    csv_text = rc.write_csv_text(header, rows)
    csv_name, json_name = "public-live-rows-%s.csv" % uid, "public-live-rows-%s.json" % uid
    csv_sha = sha(csv_text.encode("utf-8"))
    readme = render_readme(open(os.path.join(ROOT, "README.md"), encoding="utf-8").read(), rows, csv_name, csv_sha, iso)
    index = render_index(open(os.path.join(ROOT, "index.html"), encoding="utf-8").read(), rows, csv_text, csv_name, json_name, csv_sha, iso)
    json_text = json.dumps(rows, ensure_ascii=False, indent=1)
    for name, text in (("README.md", readme), ("index.html", index), (csv_name, csv_text), (json_name, json_text)):
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
    mname = "manifest/entry-hashes-v2-%s.csv" % uid
    mtext = he.manifest_text(os.path.join(stage, csv_name), rows, uid, "chr-entry-v2")
    open(os.path.join(stage, mname), "w", encoding="utf-8", newline="\n").write(mtext)
    open(os.path.join(stage, mname + ".sha256"), "w").write("%s  %s\n" % (sha(mtext.encode()), mname))
    errs = printed_checks(stage)
    e3, _ = manifest_problems(os.path.join(stage, mname), rows)
    errs += e3
    if errs:
        raise rc.Fail("post-build check failed:\n" + "\n".join(errs))
    os.makedirs(os.path.join(out_dir, "manifest"), exist_ok=True)
    written = []
    for rel in ("README.md", "index.html", csv_name, csv_name + ".sha256", json_name, mname, mname + ".sha256"):
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
        rows, csv_sha, prevs, new_ids, written = build(a.date, os.path.abspath(a.out_dir), a.source)
        print("BUILD OK %s: %d entries, CSV sha256 %s" % (a.date, len(rows), csv_sha))
        for prev in prevs:
            print("checked against previous manifest %s (%s): 0 changed, 0 vanished" % (os.path.relpath(prev, ROOT), he.manifest_version(prev)))
        print("%d new since the latest manifest %s" % (len(new_ids), new_ids if new_ids else ""))
        for s, rel in written:
            print("  %-9s %s" % (s, rel))
        return 0
    except rc.Fail as e:
        print("BUILD FAILED\n" + str(e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
