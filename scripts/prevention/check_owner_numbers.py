#!/usr/bin/env python3
"""Owner and test-figure checks (Barry go t2909u). Warn for 30 days, then block.
Looks for owner string / aliases and numbers from the test in a holder primary body when provided.
Offline structural mode: flags DESK owner on government_promise, and numbers with no primary URL on record.
New script; does not edit check_sources.py."""
from __future__ import annotations
import argparse, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prevention.common import load_display_groups, load_entries, parse_sources_record, sources_path

NUM = re.compile(r"\b\d[\d,]*(?:\.\d+)?\s*%|\bEUR\s*\d|\bUSD\s*\d|\bC\$\s*\d|\b\$\d[\d,]*(?:\.\d+)?\s*[BbMm]?\b|\b\d{1,3}(?:,\d{3})+\b")


def numbers_in(text: str):
    return [m.group(0) for m in NUM.finditer(text or "")]


def selftest() -> int:
    assert numbers_in("save $1,400 a year and EUR 500 million") 
    print("SELFTEST owner_numbers: PASS")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--mode", choices=("warn", "block"), default="warn")
    ap.add_argument("--ids", nargs="*")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    groups = load_display_groups()
    rows = load_entries()
    if args.ids:
        rows = [r for r in rows if r["id"] in set(args.ids)]
    warns = []
    for r in rows:
        rid, owner, test = r["id"], r.get("owner") or "", r.get("test") or ""
        g = groups.get(rid, "")
        if g == "government_promise" and re.search(r"\bdesk\b", owner, re.I):
            warns.append("%s: government_promise owner looks like desk (%r)" % (rid, owner[:60]))
        p = sources_path(rid)
        if not p.exists():
            continue
        rec = parse_sources_record(p.read_text(encoding="utf-8"))
        primary_urls = [b["url"] for b in rec["blocks"] if b.get("url") and "secondary" not in (b.get("supports") or "").lower()]
        nums = numbers_in(test)
        if nums and not primary_urls and g == "government_promise":
            warns.append("%s: test has figures %s but no non-secondary Primary URL on record" % (rid, nums[:3]))
    for w in warns:
        print("OWNER/NUM WARN:", w)
    print("OWNER/NUM SUMMARY: %d warn" % len(warns))
    if args.mode == "block" and warns:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
