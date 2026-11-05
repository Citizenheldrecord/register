#!/usr/bin/env python3
"""date_source vs display group (Barry go t2909u). DESK-SET / OUTSIDE in government_promise -> fail.
New script; does not edit check_sources.py or build_register.py."""
from __future__ import annotations
import argparse, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prevention.common import load_display_groups, load_entries

DESKISH = re.compile(r"\b(DESK-SET|OUTSIDE-CLAIM|OUTSIDE)\b", re.I)
PRINTED = re.compile(r"\b(GOVERNMENT PROMISE|HOLDER|COMPANY TIMETABLE|STATUTE|COURT)\b", re.I)


def provenance(date_source: str) -> str:
    ds = date_source or ""
    if DESKISH.search(ds):
        return "DESK-SET"
    if PRINTED.search(ds):
        return "PRINTED"
    return "UNKNOWN"


def check(mode="warn"):
    groups = load_display_groups()
    fails, warns = [], []
    for r in load_entries():
        rid = r["id"]
        g = groups.get(rid, "")
        prov = provenance(r.get("date_source") or "")
        if prov == "DESK-SET" and g == "government_promise":
            fails.append("%s: date_source is DESK-SET/OUTSIDE but display_group is government_promise (want also_watched unless Barry override)" % rid)
        if prov == "UNKNOWN" and g == "government_promise":
            warns.append("%s: date_source provenance UNKNOWN while government_promise" % rid)
    return fails, warns


def selftest() -> int:
    # synthetic
    assert provenance("DESK-SET: scoring date set by the register") == "DESK-SET"
    assert provenance("GOVERNMENT PROMISE: PMO release 6 Oct 2026") == "PRINTED"
    print("SELFTEST date_provenance: PASS")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--mode", choices=("warn", "block"), default="warn")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    fails, warns = check()
    for w in warns:
        print("DATE WARN:", w)
    for f in fails:
        print("DATE FAIL:", f)
    print("DATE SUMMARY: %d fail, %d warn" % (len(fails), len(warns)))
    if args.mode == "block" and fails:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
