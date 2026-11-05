#!/usr/bin/env python3
"""Archive copy required on source blocks (Barry go t2909u / t2871u).
Blocks when a full-support Source has no http Wayback URL.
Default: only rows whose sources file mtime/content mentions 2026-11-04+ cutover
or --all. New script; does not edit check_wayback.py (upload page snapshots) or check_sources.py."""
from __future__ import annotations
import argparse, sys
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
        if not wb.startswith("http"):
            bad.append("%s source %d: missing Wayback http URL (got %r)" % (rid, i, wb[:60]))
    return bad


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
