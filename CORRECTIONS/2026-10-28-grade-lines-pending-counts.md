Dated notes, 28 October 2026: cost grade lines, scoring-pending lines closed, failed-entry count

No entry in data/entries.csv was edited. Grades are corrected by new dated grade lines (rule 7, RULES-2026-10-25b.md: the cost grade follows the cost cell), as in CORRECTIONS/2026-10-25-grade-lines.md.

COST grade lines under rule 7:
- DLV-C15-SCORED-20261026: COST FAILED (was OPEN). Reason: cost cell "FAILED: no public cost-to-date figure for the measure; held by Finance Canada". The result stays PASS.
- DLV-CTR-SCORED-20261026: COST FAILED (was OPEN). Reason: cost cell "FAILED: no public cost-to-date figure; held by the Montreal Port Authority". The result stays PASS.
- DLV-DEN-SCORED-20261026: COST FAILED (was OPEN). Reason: cost cell "FAILED: no public cost-to-date figure; held by Denison Mines Corp.". The result stays PASS.
- DLV-ONLTC-SCORED-20261026: COST FAILED (was OPEN). Reason: the cost cell opens "FAILED: no public cost-to-date figure"; the $4.9 billion it cites is an allocation, not a cost.

Scoring-pending lines closed. The eight lines in data/scoring-pending.csv (GX1b, BC-PARCELS, TR1, TR-CANDU, TR-OFFTAKE, DSRB-CAP, TR-UA-PAGE, TR-DEF) are closed by their scored entries. The lines stay in the file as written. The second read planned for 26 Oct 2026 was brought forward: each row was read again live on the evening of 25 Oct 2026 and scored then, so each scored entry is dated 25 Oct.
- GX1b: read again 25 Oct 2026; FAILED entry GX1b-SCORED-20261025 stands.
- BC-PARCELS: read again 25 Oct 2026; FAILED entry BC-PARCELS-SCORED-20261025 stands.
- TR1: read again 25 Oct 2026; FAILED entry TR1-SCORED-20261025 stands.
- TR-CANDU: read again 25 Oct 2026; FAILED entry TR-CANDU-SCORED-20261025 stands.
- TR-OFFTAKE: read again 25 Oct 2026; FAILED entry TR-OFFTAKE-SCORED-20261025 stands.
- DSRB-CAP: read again 25 Oct 2026; FAILED entry DSRB-CAP-SCORED-20261025 stands.
- TR-UA-PAGE: read again 25 Oct 2026; FAILED entry TR-UA-PAGE-SCORED-20261025 stands.
- TR-DEF: read again 25 Oct 2026; FAILED entry TR-DEF-SCORED-20261025 stands.
The same eight are now in data/failure-log.csv (appended 28 Oct 2026 after the three earlier lines, which are unchanged).

Failed-entry count. data/last-checked.txt counts "failed entries" as every entry whose status reads FAILED. That count includes CL-BASE-SCORED-20261024, which is a recorded baseline counted as recorded (CORRECTIONS/2026-10-25-cl-base-counted-as-recorded.md). On 28 Oct 2026 before this update it read 14; FAILED results were 13. Read the last-checked figure as FAILED results plus that one recorded baseline.
