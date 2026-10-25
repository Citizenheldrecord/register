#!/usr/bin/env python3
"""Wayback snapshot verifier. Reads local/UPDATE-LOG.md and local/UPLOAD-LIST-*.md for
recorded snapshot URLs, groups them by update (from the dated public-live-rows files),
and checks each resolves: HTTP 200 and the archived timestamp matching the URL.
Read-only. Exit 0 all resolved and complete; 1 missing or unresolved; 2 archive unreachable."""
import glob, os, re, sys, urllib.request
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = re.compile(r"https?://web\.archive\.org/web/(\d{14})/(\S+?)(?=[\s)|;,]|$)")
KINDS = ("page", "csv", "manifest")
# Snapshots must target the register site itself: page = /register/[index.html]?v=X, csv = public-live-rows-<update>.csv,
# manifest = manifest/entry-hashes*-<update>.csv. Never plain-english.html, raw.githubusercontent.com or codeberg raw URLs.
PAGE = re.compile(r"^https?://citizenheldrecord\.github\.io/register/(?:index\.html)?\?v=[^/\s]+$")
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
            url = "https://web.archive.org/web/%s/%s" % (ts, tgt)
            if PAGE.match(tgt): k = "page"
            elif re.match(r"^https?://citizenheldrecord\.github\.io/register/public-live-rows-%s\.csv$" % re.escape(u), tgt): k = "csv"
            elif re.match(r"^https?://citizenheldrecord\.github\.io/register/manifest/entry-hashes[^/]*-%s\.csv$" % re.escape(u), tgt): k = "manifest"
            else: continue
            lst = rec[u].setdefault(k, [])
            if (ts, url) not in lst: lst.append((ts, url))
def head(url):
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "register-check_wayback"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.status, r.headers.get("Memento-Datetime", ""), r.geturl()
bad = unreachable = 0
for u in updates:
    for k in KINDS:
        if k not in rec[u]:
            print("%-12s %-9s MISSING (no snapshot URL recorded)" % (u, k)); bad += 1; continue
        cands = rec[u][k]
        results, errs = [], []
        for ts, url in reversed(cands):  # latest recorded first
            try:
                st, md, final = head(url)
                got = re.search(r"/web/(\d{14})", final)
                ok = bool(st == 200 and got and got.group(1)[:8] == ts[:8])
                results.append((ok, st, got.group(1) if got else "?", md, url))
                if ok: break
            except Exception as e:
                errs.append("%s: %s" % (url, str(e)[:80]))
        good = [r for r in results if r[0]]
        if good or results:
            ok, st, g, md, url = (good or results)[0]
            extra = " via %s" % url
            if errs: extra += " [%d other %s snapshot(s) failed: %s]" % (len(errs), k, "; ".join(errs))
            print("%-12s %-9s %s %s archived %s (%s)%s" % (u, k, "OK" if ok else "UNRESOLVED", st, g, md, extra))
            bad += not ok
        else:
            print("%-12s %-9s UNREACHABLE %s" % (u, k, "; ".join(errs))); unreachable += 1
print("SUMMARY: %d updates, %d missing or unresolved, %d unreachable" % (len(updates), bad, unreachable))
sys.exit(2 if unreachable else 1 if bad else 0)
