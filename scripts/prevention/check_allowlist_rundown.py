#!/usr/bin/env python3
"""Allow-list run-down (Barry go t2909u). No renewals. On 26 Nov remaining unsourced
allow-listed rows go to also_watched by default. This script REPORTS only; it never
edits data/sources-gate-allowlist.csv or the seed (locked)."""
from __future__ import annotations
import argparse, csv, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prevention.common import ROOT, load_display_groups

ALLOW = ROOT / "data/sources-gate-allowlist.csv"
CUTOVER = "2026-11-26"


def selftest() -> int:
    assert ALLOW.exists()
    print("SELFTEST allowlist_rundown: allowlist present PASS")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--as-of", default=None, help="YYYY-MM-DD (default today CST via caller)")
    ap.add_argument("--write-draft", action="store_true", help="write drafts list under local/")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    rows = list(csv.DictReader(ALLOW.open(encoding="utf-8")))
    renewals = [r for r in rows if int(r.get("renewals") or "0") > 0]
    groups = load_display_groups()
    print("ALLOWLIST rows: %d; expire field sample %s; cutover %s" % (len(rows), rows[0].get("expires") if rows else "-", CUTOVER))
    if renewals:
        print("ALLOWLIST RENEWAL FAIL: %d rows have renewals>0 (no renewals under t2909u)" % len(renewals))
        for r in renewals[:20]:
            print("  ", r["id"], "renewals", r["renewals"])
    still = []
    for r in rows:
        rid = r["id"]
        g = groups.get(rid, "")
        still.append((rid, r.get("level"), r.get("expires"), g))
    print("ALLOWLIST RUNDOWN PLAN: on %s, move still-unsourced/partly allow-listed ids to also_watched (display-groups append), do not renew." % CUTOVER)
    print("ALLOWLIST PENDING COUNT: %d" % len(still))
    if args.write_draft:
        out = ROOT / "local/ALLOWLIST-RUNDOWN-DRAFT.md"
        lines = ["# Allow-list rundown draft (t2909u)", "", "Cutover: %s. No renewals." % CUTOVER, ""]
        for rid, level, exp, g in still:
            lines.append("- %s | %s | expires %s | current group %s -> also_watched" % (rid, level, exp, g or "?"))
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("Wrote", out)
    # renewals are a hard fail even in report mode when present
    return 1 if renewals else 0


if __name__ == "__main__":
    sys.exit(main())
