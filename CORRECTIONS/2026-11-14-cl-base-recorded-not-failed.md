Dated note, 14 November 2026: CL-BASE is a recorded baseline, not a FAILED result (Barry go t3498s16986, 14 Nov 2026 12:34 CST)

This note restates, for the data side, the correction of 25 October 2026 (CORRECTIONS/2026-10-25-cl-base-counted-as-recorded.md and CORRECTIONS/2026-10-25-cl-base-status-word.md). The scoring entry CL-BASE-SCORED-20261024 reads "SCORED 24 Oct 2026: FAILED (blocking layer: political choice)". That word is the scoring tool's two-value output. CL-BASE's own test begins "RECORDED, not scored", so it is a recorded baseline of the four closers, not a pass/fail test. Read it as "RECORDED 24 Oct 2026: baseline of the four closers; grid in the entry".

What follows from this note:
- Counts. CL-BASE is counted as recorded as fact, not FAILED, on the page headline and in every desk count built from data/entries.csv (scripts/regcore.py is_baseline; the desk shipping and nightly tools use the same test). FAILED is 33 on 14 November 2026, not 34.
- Failure log. No data/failure-log.csv write-up is owed for CL-BASE, because it is not a FAILED result.
- Sources gate. The five-field FAILED entry record sources/failed/CL-BASE-SCORED-20261024.md stays, because the sources gate reads the status word; its "failed entries" figure in data/sources-check-counts.csv counts records, not FAILED results.

The entry itself is not edited (append only). Follows: CL-BASE-SCORED-20261024. Staged 14 November 2026; it goes live only with the next upload Barry approves.
