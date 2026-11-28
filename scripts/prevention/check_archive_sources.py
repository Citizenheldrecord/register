#!/usr/bin/env python3
"""Archive copy required on source blocks (Barry go t2909u / t2871u).
Blocks when a full-support Source has no http Wayback URL.
Default: only rows whose sources file mtime/content mentions 2026-11-04+ cutover
or --all. New script; does not edit check_wayback.py (upload page snapshots) or check_sources.py."""
from __future__ import annotations
import argparse, os, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prevention.common import load_entries, parse_sources_record, sources_path

CUT = "2026-11-04"  # t2871u


def missing_archives(rid: str):
    p = sources_path(rid)
    if not p.exists():
        return []
    rec = parse_sources_record(p.read_text(encoding="utf-8"))
    bad = []
    for i, b in enumerate(rec["blocks"], 1):
        sup = (b.get("supports") or "").lower()
        if not sup.startswith("full"):
            continue
        wb = (b.get("wayback") or "").strip()
        if not wb.startswith("http") and not r18_fallback(blocks_raw(p.read_text(encoding="utf-8"), i)):
            bad.append("%s source %d: missing Wayback http URL (got %r)" % (rid, i, wb[:60]))
    return bad


# Barry go t4424u (28 Nov 2026): the R1.8 (t3300u) / R5.22 fallback for a source that blocks archive.org. A Source block
# with no Wayback URL passes only when it carries all three: (1) "- Screenshot:" and "- Saved page text:" paths that exist
# and are not empty, (2) the dated note "archive link not opened at entry (VERDICT, read HH:MM CST YYYY-MM-DD); record
# rests on screenshot + saved page text", and (3) "- Archive block:" recording the refusal (an HTTP 403 or a Save Page
# Now / archive save failure). Nothing else changes.
R18_NOTE = re.compile(r"archive link not opened at entry \([A-Z]+, read \d{1,2}:\d{2} CST \d{4}-\d{2}-\d{2}\); record rests on screenshot \+ saved page text")
R18_BLOCK = re.compile(r"403|Save Page Now|Job failed|blocks access|save failed", re.I)


def blocks_raw(text, n):
    parts = re.split(r"^## Source (\d+)\b.*$", text, flags=re.M)
    for k in range(1, len(parts) - 1, 2):
        if parts[k] == str(n):
            return re.split(r"^## ", parts[k + 1], maxsplit=1, flags=re.M)[0]
    return ""


def r18_fallback(block):
    def field(name):
        m = re.search(r"^- %s:[ \t]*(.*)$" % re.escape(name), block, re.M)
        return m.group(1).strip() if m else ""
    for name in ("Screenshot", "Saved page text"):
        path = field(name).split(" ")[0]
        if not path or not os.path.isfile(path) or os.path.getsize(path) == 0:
            return False
    return bool(R18_NOTE.search(block)) and bool(R18_BLOCK.search(field("Archive block")))


def selftest() -> int:
    good = parse_sources_record((Path(__file__).parent / "fixtures/good_record.md").read_text())
    bad = parse_sources_record((Path(__file__).parent / "fixtures/bad_secondary_only.md").read_text())
    assert good["blocks"][0]["wayback"].startswith("http")
    assert not bad["blocks"][0]["wayback"].startswith("http")
    print("SELFTEST archive_sources: PASS")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--mode", choices=("warn", "block"), default="warn")
    ap.add_argument("--all", action="store_true", help="check every row with a sources file")
    ap.add_argument("--ids", nargs="*")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    ids = args.ids or [r["id"] for r in load_entries()]
    fails = []
    for rid in ids:
        p = sources_path(rid)
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        if not args.all and CUT not in text and "t2871u" not in text and "t2909u" not in text:
            # legacy quiet unless --all
            continue
        fails.extend(missing_archives(rid))
    for f in fails:
        print("ARCHIVE FAIL:", f)
    print("ARCHIVE SUMMARY: %d fail" % len(fails))
    if args.mode == "block" and fails:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
