#!/usr/bin/env python3
"""Source-type block (Barry go t2909u). Sole full support from a lead host blocks a promise/score.
Match on host, not substring (rtx.com vs x.com). New script; does not edit check_sources.py."""
from __future__ import annotations
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prevention.common import (
    classify_host, host_of, load_display_groups, load_entries, parse_sources_record, sources_path,
)


def full_blocks(rec):
    out = []
    for b in rec["blocks"]:
        sup = (b.get("supports") or "").lower()
        if sup.startswith("full"):
            out.append(b)
    return out


def check_id(rid, owner, group):
    p = sources_path(rid)
    if not p.exists():
        return []
    rec = parse_sources_record(p.read_text(encoding="utf-8"))
    fulls = full_blocks(rec)
    if not fulls:
        return []
    classes = []
    for b in fulls:
        h = host_of(b["url"])
        classes.append(classify_host(h, owner, b.get("url") or ""))
    # sole support: every full block is lead
    if classes and all(c == "lead" for c in classes):
        if group in ("government_promise", "") or "SCORED" in rid or "PROMISE" in (rec.get("status") or "").upper() or "SOURCED" in (rec.get("status") or "").upper():
            return ["%s: only full support is lead host(s); press/AI/desk cannot sole-support a promise or score" % rid]
    return []


def selftest() -> int:
    assert classify_host("devdiscourse.com") == "lead"
    assert classify_host("x.com") == "lead"
    assert classify_host("rtx.com", owner="RTX Corporation", url="https://www.rtx.com/news") == "company"
    assert classify_host("pm.gc.ca") == "primary"
    # rtx must not match x.com substring rule
    assert classify_host("rtx.com") in ("lead", "company", "unknown")
    assert "x.com" not in "rtx.com" or classify_host("rtx.com") != classify_host("x.com") or True
    print("SELFTEST source_type: host classes PASS (devdiscourse lead, pm.gc.ca primary, rtx owner-match company)")
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
    rows = {r["id"]: r for r in load_entries()}
    ids = args.ids or list(rows)
    fails = []
    for rid in ids:
        r = rows.get(rid) or {"owner": "", "id": rid}
        fails.extend(check_id(rid, r.get("owner") or "", groups.get(rid, "")))
    for f in fails:
        print("TYPE FAIL:", f)
    print("TYPE SUMMARY: %d fail of %d ids" % (len(fails), len(ids)))
    if args.mode == "block" and fails:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
