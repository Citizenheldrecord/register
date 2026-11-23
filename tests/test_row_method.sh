#!/usr/bin/env bash
# METHOD-ROWFILE: data/row-method.csv covers every entries.csv id; date_basis values are allow-listed.
# Argv guards (Barry go t4033u): --help and a bogus flag leave the output file byte-identical.
# This test never writes the live data/row-method.csv; it runs in a temporary copy.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/scripts" "$TMP/data"
cp "$ROOT/scripts/build_row_method.py" "$TMP/scripts/"
cp "$ROOT/data/entries.csv" "$TMP/data/entries.csv"

# Pre-existing output that must not change on a refused or help run.
printf '%s\n' 'id,note_date,entry_reason,date_basis,date_basis_reason,source' 'TEST-KEEP,2026-01-01,keep me,government,,orig' > "$TMP/data/row-method.csv"
cp "$TMP/data/row-method.csv" "$TMP/data/row-method.csv.before"

run_argv() {
  local label="$1" expect_zero="$2"; shift 2
  set +e
  python3 "$TMP/scripts/build_row_method.py" "$@" >"$TMP/$label.out" 2>"$TMP/$label.err"
  local rc=$?
  set -e
  if ! cmp -s "$TMP/data/row-method.csv" "$TMP/data/row-method.csv.before"; then
    echo "FAIL $label: data/row-method.csv was written" >&2
    exit 1
  fi
  if [ "$expect_zero" = "zero" ]; then
    if [ "$rc" -ne 0 ]; then
      echo "FAIL $label: expected exit 0, got $rc" >&2
      cat "$TMP/$label.out" "$TMP/$label.err" >&2
      exit 1
    fi
  else
    if [ "$rc" -eq 0 ]; then
      echo "FAIL $label: expected nonzero exit, got 0" >&2
      cat "$TMP/$label.out" "$TMP/$label.err" >&2
      exit 1
    fi
  fi
}

run_argv help zero --help
if ! grep -q -i "usage" "$TMP/help.out" "$TMP/help.err"; then
  echo "FAIL help: usage text not printed" >&2
  cat "$TMP/help.out" "$TMP/help.err" >&2
  exit 1
fi
run_argv bogus nonzero --not-a-real-flag
run_argv baddate nonzero not-a-date
echo "OK test_row_method argv: --help, a bogus flag and a bad date left the file byte-identical"

# Classification check also runs in the temp tree, not against the live file.
python3 "$TMP/scripts/build_row_method.py" 2099-01-01 >"$TMP/rebuild.out"
python3 - "$TMP" <<'PY'
import csv, sys
from pathlib import Path
root = Path(sys.argv[1])
entries = {r["id"] for r in csv.DictReader((root / "data" / "entries.csv").open(encoding="utf-8")) if r.get("id")}
rows = list(csv.DictReader((root / "data" / "row-method.csv").open(encoding="utf-8")))
ids = {r["id"] for r in rows}
assert ids == entries, f"id mismatch missing={sorted(entries-ids)[:10]} extra={sorted(ids-entries)[:10]}"
allowed = {"government", "statutory", "desk-default", "desk-exception", "not recorded"}
bad = sorted({r["date_basis"] for r in rows} - allowed)
assert not bad, f"bad date_basis values: {bad}"
assert all(r.get("note_date") == "2099-01-01" for r in rows)
assert all(r.get("source") for r in rows)
print("OK test_row_method: %d rows, bases=%s" % (len(rows), sorted({r["date_basis"] for r in rows})))
PY
