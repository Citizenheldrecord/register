#!/usr/bin/env python3
"""Build data/row-method.csv mechanically from data/entries.csv date_source labels.

METHOD-ROWFILE (Barry go t2731u / FIREAT retimed t2886u). Append-only side file.
Never edits entries.csv. Never guesses a date_basis: if the label does not show it,
write "not recorded". entry_reason for pre-existing rows is "not recorded" unless a
later dated line supplies one. Written by this script only, never by hand.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRIES = ROOT / "data" / "entries.csv"
OUT = ROOT / "data" / "row-method.csv"

FIELDS = [
    "id",
    "note_date",
    "entry_reason",
    "date_basis",
    "date_basis_reason",
    "source",
]


def classify_date_basis(date_source: str) -> tuple[str, str]:
    """Return (date_basis, date_basis_reason). reason only for desk-exception."""
    ds = (date_source or "").strip()
    up = ds.upper()
    # statutory / legal deadline
    if up.startswith(("STATUTE", "STATUTORY", "LEGAL DEADLINE", "IRPA")) or "STATUTE:" in up:
        return "statutory", ""
    if "S.94" in up or "SITTING DAY" in up:
        return "statutory", ""
    # government promise / commitment / timetable
    if up.startswith(
        (
            "GOVERNMENT PROMISE",
            "GOVERNMENT COMMITMENT",
            "GOVERNMENT:",
            "COMPANY TIMETABLE",
            "SCHEDULED RELEASE",
            "DOCKET",
            "COURT",
            "LEGISLATURE",
        )
    ):
        return "government", ""
    # desk-set / desk date
    if up.startswith(("DESK-SET", "DESK DATE", "DESK-FIXED", "DESK-PROPOSED", "PROPOSED")):
        # desk-exception would need a written justification line; without it = desk-default
        return "desk-default", ""
    if "DESK-SET" in up:
        # outside date with register window — still desk-default under proposal's four values?
        # Proposal values: government|statutory|desk-default|desk-exception.
        # Mixed outside+desk window is not a listed value; do not invent — not recorded.
        return "not recorded", ""
    if not ds:
        return "not recorded", ""
    # Unclassed label forms
    return "not recorded", ""


def main() -> int:
    note_date = None
    if len(sys.argv) > 1:
        note_date = sys.argv[1]
    else:
        import subprocess

        note_date = subprocess.check_output(
            ["bash", "-lc", "TZ=Etc/GMT+6 date +%Y-%m-%d"], text=True
        ).strip()

    rows = list(csv.DictReader(ENTRIES.open(encoding="utf-8")))
    out_rows = []
    for r in rows:
        rid = r.get("id") or ""
        if not rid:
            continue
        basis, reason = classify_date_basis(r.get("date_source") or "")
        out_rows.append(
            {
                "id": rid,
                "note_date": note_date,
                "entry_reason": "not recorded (existing row; method side-file bootstrapped mechanically)",
                "date_basis": basis,
                "date_basis_reason": reason,
                "source": "scripts/build_row_method.py from data/entries.csv date_source",
            }
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(out_rows)
    print(f"wrote {OUT} rows={len(out_rows)} note_date={note_date}")
    from collections import Counter

    print("date_basis", dict(Counter(r["date_basis"] for r in out_rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
