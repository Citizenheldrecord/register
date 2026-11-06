#!/usr/bin/env bash
# METHOD-ROWFILE: data/row-method.csv covers every entries.csv id; date_basis values are allow-listed.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
python3 scripts/build_row_method.py 2099-01-01 >/tmp/row-method-rebuild.out
# rebuild should be deterministic on classification; restore note_date via re-run with real date after check
python3 - <<'PY'
import csv
from pathlib import Path
entries = {r["id"] for r in csv.DictReader(open("data/entries.csv", encoding="utf-8")) if r.get("id")}
rows = list(csv.DictReader(open("data/row-method.csv", encoding="utf-8")))
ids = {r["id"] for r in rows}
assert ids == entries, f"id mismatch missing={sorted(entries-ids)[:10]} extra={sorted(ids-entries)[:10]}"
allowed = {"government", "statutory", "desk-default", "desk-exception", "not recorded"}
bad = sorted({r["date_basis"] for r in rows} - allowed)
assert not bad, f"bad date_basis values: {bad}"
assert all(r.get("note_date") for r in rows)
assert all(r.get("source") for r in rows)
print("OK test_row_method: %d rows, bases=%s" % (len(rows), sorted({r["date_basis"] for r in rows})))
PY
# restore real note_date
python3 scripts/build_row_method.py 2026-11-06 >/dev/null
