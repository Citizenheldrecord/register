#!/usr/bin/env python3
"""Status derived from source blocks (Barry go t2909u). Typed Status must match computed level.
New script; does not edit check_sources.py."""
from __future__ import annotations
import argparse, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prevention.common import load_entries, parse_sources_record, sources_path

def computed_level(rec) -> str:
    blocks = rec["blocks"]
    full_primary = False
    full_secondary = False
    any_partial = False
    for b in blocks:
        sup = (b.get("supports") or "").lower()
        if not sup:
            continue
        if "secondary" in sup and sup.startswith("full"):
            full_secondary = True
        elif sup.startswith("full"):
            full_primary = True
        elif "partial" in sup:
            any_partial = True
    if full_primary:
        return "SOURCED"
    if full_secondary:
        return "SECONDARY"  # must not claim PROMISE SOURCED / SOURCED without RULE A path
    if any_partial:
        return "PARTLY SOURCED"
    return "UNSOURCED"


def claimed_bucket(status: str) -> str:
    s = (status or "").upper()
    if "PROMISE SOURCED" in s:
        return "PROMISE"
    if s.startswith("SOURCED") or s == "SOURCED":
        return "SOURCED"
    if "PARTLY" in s:
        return "PARTLY SOURCED"
    if "UNSOURCED" in s:
        return "UNSOURCED"
    return s[:40]


def mismatch(rid, rec) -> str | None:
    claimed = claimed_bucket(rec["status"])
    level = computed_level(rec)
    # PROMISE SOURCED on secondary-only is the CAN-UKL-500 class bug
    if claimed in ("PROMISE", "SOURCED") and level == "SECONDARY":
        return "%s: Status claims %s but only full (secondary) support (computed %s)" % (rid, rec["status"], level)
    if claimed == "SOURCED" and level in ("PARTLY SOURCED", "UNSOURCED"):
        return "%s: Status claims SOURCED but computed %s" % (rid, level)
    return None


def selftest() -> int:
    bad = parse_sources_record((Path(__file__).parent / "fixtures/bad_secondary_only.md").read_text())
    good = parse_sources_record((Path(__file__).parent / "fixtures/good_record.md").read_text())
    assert computed_level(bad) == "SECONDARY"
    assert mismatch("FIXTURE-BAD", bad)
    assert computed_level(good) == "SOURCED"
    assert mismatch("FIXTURE-GOOD", good) is None
    print("SELFTEST status_derived: PASS")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--mode", choices=("warn", "block"), default="warn")
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
        m = mismatch(rid, parse_sources_record(p.read_text(encoding="utf-8")))
        if m:
            fails.append(m)
    for f in fails:
        print("STATUS FAIL:", f)
    print("STATUS SUMMARY: %d fail of %d ids" % (len(fails), len(ids)))
    if args.mode == "block" and fails:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
