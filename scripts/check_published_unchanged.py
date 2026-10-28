#!/usr/bin/env python3
"""Guardrail 3 (Barry go 27 Oct 2026): pre-upload fingerprint check.

Every local file whose name already exists in the published repository
(GitHub Citizenheldrecord/register) must be byte-identical to the published file.
README.md and index.html are expected to change and are exempt. Exits 1 on any
mismatch, 2 if the published listing cannot be read.

  python3 scripts/check_published_unchanged.py            listing from GitHub (falls back to the cache)
  python3 scripts/check_published_unchanged.py --offline  use the cache only
  python3 scripts/check_published_unchanged.py --refresh  rewrite the cache from GitHub, then check
  python3 scripts/check_published_unchanged.py --dir X    check folder X instead of the repository root

The cache is local/published-files.txt: one line per published file, "<git blob sha1>  <size>  <path>".
Append-only sources (data/entries.csv and friends) pass if the published bytes are an exact prefix.
The git blob sha1 is what GitHub reports for each file, so the published bytes are compared
exactly without downloading them. The upload step refreshes it (preflight.sh --mark-pushed).
"""
import argparse, hashlib, json, os, re, sys, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "local", "published-files.txt")
REPO = "Citizenheldrecord/register"
BRANCH = "main"
EXEMPT = {"README.md", "index.html"}
# Non-dated published files (scripts, docs) that an approved update is meant to change are listed, one path per line,
# in local/expected-changes.txt. They are printed as EXPECTED CHANGE, never silently passed. Dated outputs can never be listed.
EXPECTED = os.path.join(ROOT, "local", "expected-changes.txt")
DATED = re.compile(r"^(public-live-rows-.+|manifest/entry-hashes.+)$")
# Append-only sources: the published bytes must be an exact prefix of the local file (rows may only be added).
APPEND_ONLY = {"data/entries.csv", "data/display-groups.csv", "data/housekeeping-log.csv", "data/failure-log.csv"}


def blob_sha(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def fetch_listing():
    url = "https://api.github.com/repos/%s/git/trees/%s?recursive=1" % (REPO, BRANCH)
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "register-preflight"})
    d = json.load(urllib.request.urlopen(req, timeout=30))
    if d.get("truncated"):
        raise RuntimeError("GitHub tree listing truncated")
    return {e["path"]: (e["sha"], e["size"]) for e in d["tree"] if e["type"] == "blob"}


def read_cache(path=CACHE):
    out = {}
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#"):
            h, n, p = line.split(None, 2)
            out[p] = (h, int(n))
    return out


def write_cache(listing, path=CACHE):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("# published files in github.com/%s (%s), git blob sha1, size and path; refreshed by check_published_unchanged.py --refresh\n" % (REPO, BRANCH))
        for p in sorted(listing):
            fh.write("%s  %d  %s\n" % (listing[p][0], listing[p][1], p))


def load_published(offline=False, refresh=False):
    if not offline:
        try:
            listing = fetch_listing()
            if refresh:
                write_cache(listing)
            return listing, "GitHub %s@%s" % (REPO, BRANCH)
        except Exception as e:
            if refresh:
                raise
            print("note: GitHub listing unavailable (%s); using %s" % (e, os.path.relpath(CACHE, ROOT)), file=sys.stderr)
    return read_cache(), os.path.relpath(CACHE, ROOT)


def expected_changes():
    if not os.path.exists(EXPECTED):
        return set()
    return {l.strip() for l in open(EXPECTED, encoding="utf-8") if l.strip() and not l.startswith("#")}


def mismatches(folder, published, expected=frozenset()):
    bad, checked, exp = [], 0, []
    for p, (h, size) in sorted(published.items()):
        if os.path.basename(p) in EXEMPT and os.path.dirname(p) == "":
            continue
        f = os.path.join(folder, p)
        if not os.path.exists(f):
            continue   # a missing file is reported by preflight's MISSING check
        checked += 1
        data = open(f, "rb").read()
        if p in APPEND_ONLY:
            data = data[:size]
        if blob_sha(data) != h:
            if p in expected and not DATED.match(p):
                exp.append(p)
            else:
                bad.append(p)
    return bad, checked, exp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=ROOT)
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    try:
        published, src = load_published(a.offline, a.refresh)
    except Exception as e:
        print("PUBLISHED-UNCHANGED: cannot read the published listing: %s" % e)
        return 2
    expected = expected_changes()
    bad, checked, exp = mismatches(a.dir, published, expected)
    for p in exp:
        print("EXPECTED CHANGE (listed in local/expected-changes.txt): " + p)
    if bad:
        print("PUBLISHED-UNCHANGED FAILED: %d local file(s) differ from the published bytes (%s). Restore them from the published repository; never upload over them:" % (len(bad), src))
        for p in bad:
            print("  " + p)
        return 1
    print("PUBLISHED-UNCHANGED OK: %d published files checked against %s, byte-identical apart from %d listed expected change(s) (README.md and index.html exempt; append-only data files checked as prefixes)" % (checked, src, len(exp)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
