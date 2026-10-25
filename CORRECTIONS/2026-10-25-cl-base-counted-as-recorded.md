Dated correction, 25 October 2026: CL-BASE counted as recorded, not FAILED

25 October 2026. CL-BASE is a recorded baseline of the four closers, not a pass/fail test. From this date the page counts it as recorded, not FAILED. CL-BASE and CL-BASE-SCORED-20261024 are unchanged; the FAILED word in the scoring entry is the scoring tool's two values only.

How: the count (scripts/regcore.py) treats an entry whose own test begins "RECORDED, not scored" or "RECORDED, not PASS/FAILED" as recorded as fact once it is scored, whatever word its scoring entry carries. The page labels such an entry and its scoring entry "Baseline". No entry in data/entries.csv was edited.

Counts from update 2026-10-25d (235 entries = 229 promises + 6 scoring entries): FAILED 3 (AB1-PL, BC1, FA3b); recorded as fact 2 (CL-BASE, HR5334). Before this correction, update 2026-10-25c (234 entries) printed FAILED 4 (AB1-PL, BC1, CL-BASE, FA3b) and recorded as fact 1 (HR5334).

Earlier dated note: CORRECTIONS/2026-10-25-cl-base-baseline-note.md.
