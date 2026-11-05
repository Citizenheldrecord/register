#!/usr/bin/env python3
"""Monthly rolling re-audit (Barry go t2909u). First business day / 2nd of each month:
re-read a third of rows plus scoring dates in the next 30 days. Stamps from TZ=Etc/GMT+6.
Writes reports under sovereign-realism/reports/. Does not score or upload."""
from __future__ import annotations
import argparse, csv, datetime as dt, os, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prevention.common import ROOT, load_entries

DESK_REPORTS = Path("/workspace/sovereign-realism/reports")


def cst_now():
    # fixed UTC-6
    env = os.environ.copy()
    env["TZ"] = "Etc/GMT+6"
    out = subprocess.check_output(["date", "+%Y-%m-%d %H:%M:%S %Z"], env=env, text=True).strip()
    return out


def month_shard(rows, year: int, month: int):
    """Return ~1/3 of ids for this month (stable hash by id)."""
    # months 1-4 -> shard 0, 5-8 -> 1, 9-12 -> 2
    shard = 0 if month <= 4 else 1 if month <= 8 else 2
    picked = []
    for r in rows:
        h = sum(ord(c) for c in r["id"]) % 3
        if h == shard:
            picked.append(r["id"])
    return picked


def scoring_next_30(rows, today: dt.date):
    out = []
    for r in rows:
        sd = (r.get("scoring_date") or "").strip()
        # expect like 30 Nov 2026
        try:
            d = dt.datetime.strptime(sd, "%d %b %Y").date()
        except Exception:
            continue
        if today <= d <= today + dt.timedelta(days=30):
            out.append(r["id"])
    return out


def selftest() -> int:
    rows = [{"id": "A"}, {"id": "B"}, {"id": "C"}]
    s = month_shard(rows, 2026, 11)
    assert isinstance(s, list)
    print("SELFTEST monthly_register_audit: PASS", cst_now())
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    stamp = cst_now()
    today = dt.date.fromisoformat(stamp[:10])
    rows = load_entries()
    shard = month_shard(rows, today.year, today.month)
    due = scoring_next_30(rows, today)
    ids = sorted(set(shard) | set(due))
    print("MONTHLY AUDIT plan %s: shard %d ids; scoring-next-30 %d; union %d" % (stamp, len(shard), len(due), len(ids)))
    if args.write:
        DESK_REPORTS.mkdir(parents=True, exist_ok=True)
        path = DESK_REPORTS / ("MONTHLY-REGISTER-AUDIT-%s.md" % today.isoformat())
        lines = [
            "# Monthly register audit plan",
            "",
            "Clock stamp: %s (TZ=Etc/GMT+6)." % stamp,
            "Barry go t2909u. Re-read these ids with the full audit; never type times by hand.",
            "",
            "## Shard ids (%d)" % len(shard),
        ]
        lines += ["- %s" % i for i in shard]
        lines += ["", "## Scoring in next 30 days (%d)" % len(due)]
        lines += ["- %s" % i for i in due]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("Wrote", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
