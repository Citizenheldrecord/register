#!/usr/bin/env python3
"""Wayback snapshot verifier. Reads local/UPDATE-LOG.md and local/UPLOAD-LIST-*.md for
recorded snapshot URLs, groups them by update (from the dated public-live-rows files),
and checks each resolves: HTTP 200 and the archived timestamp matching the URL.
Read-only. Exit 0 all resolved and complete; 1 missing or unresolved; 2 archive unreachable."""
import glob, os, re, sys, urllib.request
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = re.compile(r"https?://web\.archive\.org/web/(\d{14})/(\S+?)(?=[\s)|;,]|$)")
KINDS = ("page", "csv", "manifest")
updates = sorted(re.sub(r".*public-live-rows-(.+)\.csv$", r"\1", p) for p in glob.glob(os.path.join(ROOT, "public-live-rows-*.csv")))
rec = {u: {} for u in updates}
cur = None
for f in [os.path.join(ROOT, "local/UPDATE-LOG.md")] + sorted(glob.glob(os.path.join(ROOT, "local/UPLOAD-LIST-*.md"))):
    if not os.path.exists(f): continue
    for line in open(f, encoding="utf-8"):
        m = re.match(r"\s*(20\d\d-\d\d-\d\d[a-z]?)\b", line)
        if m and m.group(1) in rec: cur = m.group(1)
        for ts, tgt in URL.findall(line):
            fm = re.search(r"(20\d\d-\d\d-\d\d[a-z]?)\.csv", tgt)
            u = fm.group(1) if fm else cur
            if u not in rec: continue
            k = "manifest" if "manifest/" in tgt else "csv" if tgt.endswith(".csv") else "page"
            rec[u][k] = (ts, "https://web.archive.org/web/%s/%s" % (ts, tgt))
def head(url):
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "register-check_wayback"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.status, r.headers.get("Memento-Datetime", ""), r.geturl()
bad = unreachable = 0
for u in updates:
    for k in KINDS:
        if k not in rec[u]:
            print("%-12s %-9s MISSING (no snapshot URL recorded)" % (u, k)); bad += 1; continue
        ts, url = rec[u][k]
        try:
            st, md, final = head(url)
            got = re.search(r"/web/(\d{14})", final)
            ok = st == 200 and got and got.group(1)[:8] == ts[:8]
            print("%-12s %-9s %s %s archived %s (%s)" % (u, k, "OK" if ok else "UNRESOLVED", st, got.group(1) if got else "?", md))
            bad += not ok
        except Exception as e:
            print("%-12s %-9s UNREACHABLE %s: %s" % (u, k, url, str(e)[:80])); unreachable += 1
print("SUMMARY: %d updates, %d missing or unresolved, %d unreachable" % (len(updates), bad, unreachable))
sys.exit(2 if unreachable else 1 if bad else 0)
