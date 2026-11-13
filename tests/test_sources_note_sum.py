#!/usr/bin/env python3
"""Sourcing note sum check (Barry go t3446u, 13 Nov 2026): every category on the page note must add up to the
sources check row count and the data/entries.csv row count, or the build stops. Run: python3 tests/test_sources_note_sum.py"""
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import build_register as br, regcore as rc
HEAD = "date,sourced,secondary_sourced,partly_sourced,unsourced,missing_record,rows,failed_entries,failed_entry_incomplete,promise_outcome_pending,promise_outcome_scored\n"
def note(line, n):
    f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False); f.write(HEAD + line + "\n"); f.close()
    keep, br.SOURCES_COUNTS = br.SOURCES_COUNTS, f.name; br.STAMP["n"] = n
    try: return br.sources_note("2026-11-13")
    finally: br.SOURCES_COUNTS = keep; os.unlink(f.name)
t = note("2026-11-13,178,0,90,87,0,426,34,0,67,4", 426)
assert "178 rows are sourced, 0 secondary-sourced, 67 have their promise sourced with the outcome pending, 4 have their promise sourced with the outcome scored, 90 partly sourced and 87 unsourced, and 0 do not yet have a record." in t, t
for line, n in (("2026-11-13,178,0,90,87,0,426,34,0,67,4", 427), ("2026-11-13,178,0,90,87,0,426,34,0,67,0", 426)):
    try:
        note(line, n)
    except rc.Fail as e:
        assert "SUM MISMATCH" in str(e); continue
    sys.exit("FAIL: sum mismatch not caught (%s, entries %d)" % (line, n))
print("PASS test_sources_note_sum (3 cases)")
