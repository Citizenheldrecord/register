#!/usr/bin/env python3
"""Blocking prevention gate (Barry go t2909u, follow-up 4 Nov 2026; rules t2867u, t2885u).

Runs the prevention checks (date provenance, source type, status derived, archive copies,
owner/test numbers, allow-list renewals) as a gate. New script: it only calls the existing
prevention modules; it never edits check_sources.py, the allow-list or the locked seed.

  gate.py --ids ID [ID ...]   block (exit 1) if any listed id fails a prevention check
  gate.py --preflight         block on every id NEW or CHANGED since the last upload baseline
                              (last commit of local/LIVE_FILES.sha256); every other existing failure
                              is printed as KNOWN and counted by tools/integrity_check.py section 15
                              until its data is fixed (never silently exempted)
  gate.py --sweep             print every failure, all ids (used by integrity_check)

Blocking is the default. PREVENTION_BLOCK=0 turns blocking off and is printed loudly.
"""
from __future__ import annotations
import argparse, csv, io, os, re, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prevention.common import ROOT, load_display_groups, load_entries, parse_sources_record, sources_path
from prevention import check_date_provenance as cdp, check_source_type as cst
from prevention import check_status_derived as csd, check_archive_sources as cas
from prevention import check_quote_on_page as cqp

ARCHIVE_MARKERS = ("2026-11-04", "t2871u", "t2909u")


def failures_for(ids=None, extra_rows=None):
    """Return list of (section, id, message) for the given ids (None = all).
    extra_rows: rows not yet written (add_entry.py / stage_recorded.py gate before append)."""
    rows = {r["id"]: r for r in load_entries()}
    for r in (extra_rows or []):
        rows[r["id"]] = r
    groups = load_display_groups()
    want = set(ids) if ids is not None else set(rows)
    out = []
    fails, _ = cdp.check()
    seen = set()
    for f in fails:
        rid = f.split(":", 1)[0]
        seen.add(rid)
        if rid in want:
            out.append(("DATE", rid, f))
    for r in (extra_rows or []):
        if r["id"] in want and r["id"] not in seen and cdp.provenance(r.get("date_source") or "") == "DESK-SET" and groups.get(r["id"], "") == "government_promise":
            out.append(("DATE", r["id"], "%s: date_source is DESK-SET/OUTSIDE but display_group is government_promise (want also_watched unless Barry override)" % r["id"]))
    for rid in sorted(want):
        r = rows.get(rid) or {"owner": ""}
        for f in cst.check_id(rid, r.get("owner") or "", groups.get(rid, "")):
            out.append(("TYPE", rid, f))
        p = sources_path(rid)
        if p.exists():
            text = p.read_text(encoding="utf-8")
            m = csd.mismatch(rid, parse_sources_record(text))
            if m:
                out.append(("STATUS", rid, m))
            if any(k in text for k in ARCHIVE_MARKERS) or ids is not None:
                for f in cas.missing_archives(rid):
                    out.append(("ARCHIVE", rid, f))
    for sec, script in (("OWNER/NUM", "check_owner_numbers.py"), ("ALLOWLIST", "check_allowlist_rundown.py")):
        if ids is not None and sec == "ALLOWLIST":
            continue
        args = [sys.executable, str(Path(__file__).parent / script)]
        if sec == "OWNER/NUM" and ids is not None:
            args += ["--ids", *sorted(want)]
        p = subprocess.run(args, cwd=str(ROOT), capture_output=True, text=True)
        for line in p.stdout.splitlines():
            if line.startswith("OWNER/NUM WARN:"):
                msg = line.split(":", 1)[1].strip()
                out.append((sec, msg.split(":", 1)[0], msg))
            if line.startswith("ALLOWLIST RENEWAL FAIL"):
                out.append((sec, "-", line))
    return out


def quote_failures(ids):
    """QUOTE ON PAGE (Barry go t2909u; wired as blocking t2947u, RULEBOOK.md R1.6 and R2.3).
    Added 5 Nov 2026. Runs only for ids that are new or changed (--ids, --preflight touched ids,
    gate_new_row); --sweep and every existing check are unchanged. A fetch error with no match
    counts as a failure (never a pass)."""
    out = []
    for rid in sorted(set(ids or [])):
        p = sources_path(rid)
        if p.exists():
            for f in cqp.check_record(p):
                out.append(("QUOTE", rid, f))
    return out


def _git_show(rev, path):
    p = subprocess.run(["git", "show", "%s:%s" % (rev, path)], cwd=str(ROOT), capture_output=True)
    return p.stdout.decode("utf-8", "replace") if p.returncode == 0 else None


def touched_ids():
    base = subprocess.run(["git", "log", "-1", "--format=%H", "--", "local/LIVE_FILES.sha256"],
                          cwd=str(ROOT), capture_output=True, text=True).stdout.strip()
    if not base:
        return None, "no upload baseline commit found"
    ids = set()
    old = _git_show(base, "data/entries.csv") or ""
    old_ids = {r["id"] for r in csv.DictReader(io.StringIO(old))} if old else set()
    for r in load_entries():
        if r["id"] not in old_ids:
            ids.add(r["id"])
    oldg = _git_show(base, "data/display-groups.csv") or ""
    oldlines = set(oldg.splitlines())
    for line in (ROOT / "data/display-groups.csv").read_text(encoding="utf-8").splitlines():
        if line not in oldlines and line and not line.startswith("id,"):
            ids.add(line.split(",", 1)[0])
    diff = subprocess.run(["git", "diff", "--name-only", base, "--", "sources/"], cwd=str(ROOT), capture_output=True, text=True).stdout.split()
    untracked = subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "sources/"], cwd=str(ROOT), capture_output=True, text=True).stdout.split()
    for f in diff + untracked:
        m = re.match(r"sources/([^/]+)\.md$", f)
        if m:
            ids.add(m.group(1))
    return ids, base[:7]


def main(argv=None):
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--ids", nargs="+")
    g.add_argument("--preflight", action="store_true")
    g.add_argument("--sweep", action="store_true")
    a = ap.parse_args(argv)
    block = os.environ.get("PREVENTION_BLOCK", "1") != "0"
    if not block:
        print("PREVENTION GATE: BLOCKING TURNED OFF BY PREVENTION_BLOCK=0 (report this to Barry)")
    if a.sweep:
        allf = failures_for(None)
        for sec, rid, msg in allf:
            print("PREVENTION FAIL [%s] %s" % (sec, msg))
        print("PREVENTION SWEEP: %d failures" % len(allf))
        return 0
    if a.ids:
        f = failures_for(a.ids) + quote_failures(a.ids)
        for sec, rid, msg in f:
            print("PREVENTION BLOCK [%s] %s" % (sec, msg))
        print("PREVENTION GATE (ids %s): %d failures" % (" ".join(a.ids), len(f)))
        return 1 if (f and block) else 0
    ids, base = touched_ids()
    if ids is None:
        print("PREVENTION GATE: cannot compute changed ids (%s); blocking" % base)
        return 1 if block else 0
    allf = failures_for(None)
    hit = [x for x in allf if x[1] in ids or x[1] == "-"]
    hit += quote_failures(ids)
    known = [x for x in allf if x not in hit]
    print("PREVENTION GATE: %d ids new/changed since upload baseline %s" % (len(ids), base))
    for sec, rid, msg in hit:
        print("PREVENTION BLOCK [%s] %s" % (sec, msg))
    for sec, rid, msg in known:
        print("PREVENTION KNOWN (existing row, counted in nightly ERROR COUNT until fixed) [%s] %s" % (sec, msg))
    print("PREVENTION GATE: %d blocking, %d known existing" % (len(hit), len(known)))
    return 1 if (hit and block) else 0


def gate_new_row(row):
    """Called by scripts/add_entry.py append() before any write. Returns list of messages; caller dies on any."""
    if os.environ.get("PREVENTION_BLOCK", "1") == "0":
        print("PREVENTION GATE: BLOCKING TURNED OFF BY PREVENTION_BLOCK=0 (report this to Barry)", file=sys.stderr)
        return []
    fl = failures_for([row["id"]], extra_rows=[row]) + quote_failures([row["id"]])
    return ["[%s] %s" % (s, m) for s, _, m in fl]


if __name__ == "__main__":
    sys.exit(main())
