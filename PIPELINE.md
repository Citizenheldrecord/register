How the register is built and checked

One source. Every entry lives in data/entries.csv, one row per entry. That file only ever grows. No row in it is edited or removed. Corrections, new dates and scoring results are new rows.

Housekeeping (rule entry R-2026-10-24-A, 24 October 2026). The one exception: internal working notes (approval notes, timestamps, internal file references) may be removed from the date source, measure, money, funding or essay field of a row, by deleting the text or replacing it with OPEN. Each removal is first listed in data/housekeeping-log.csv (date, update, id, field, action, fingerprint layout, fingerprint before and after; one line per layout the row appears in). The build accepts such a changed fingerprint only if the log lists it and the published file named by the previous manifest shows the change is only that; it prints each accepted edit, and the new manifest names the log and its checksum.

Housekeeping in the test field (rule entry R-2026-10-25-A, 25 October 2026). The same rule applies to the test field for internal approval notes only. A test may only lose one stretch of text; it is never replaced with OPEN. Logged and checked the same way.

Adding to it. Use scripts/add_entry.py, never a text editor.
- commit: a new test, with outcome (PASS and FAILED), scoring date, owner and date source. Cost to date starts as OPEN until the scoring date.
- redate: a new date for an existing test. The new row gets its own id and cites the old row's id and fingerprint. The old row stays.
- score: the result on the scoring date, as a new row citing the scored row's id and fingerprint. It needs the result, an evidence URL, a cost to date (a sourced figure, or FAILED naming whoever holds the figure, never OPEN) and the hype, means and cost sub-scores. A FAILED result names the blocking layer. Every entry carries hype, means and cost sub-scores; they read OPEN until the entry is scored.
The script refuses anything that breaks a rule and writes nothing.

Building. scripts/build_register.py --date YYYY-MM-DD (add a letter, as in 2026-10-18b, for a second update the same day, so no published file is overwritten) reads data/entries.csv and writes the dated CSV, JSON and checksum file, puts the CSV inside index.html, prints the matching checksum on the page and in README.md, rebuilds the tables in README.md, and writes a new manifest of entry fingerprints in layout chr-entry-v2 (manifest/entry-hashes-v2-<update>.csv). It checks the data against the latest v2 manifest and the kept v1 manifest of 18 October 2026. A scored entry is shown on the page and in README.md as CLOSED, linked to its scoring entry; its row in the data is never changed. README.md tables include cost to date. It stops, writes nothing and lists every problem if:
- an entry in the previous manifest has changed or disappeared;
- a row lacks its outcome, scoring date, owner, date source, status or cost to date;
- a scoring row after 18 October 2026 lacks a real cost to date, the three sub-scores, or the citation of the entry it scores;
- any public text has a long dash or a curly quote;
- a printed checksum does not match the CSV it names.
scripts/build_register.py --verify checks the published files alone.

Before a push. scripts/preflight.sh YYYY-MM-DD runs the build, the checks and every test, then prints GO or NO-GO and the exact files to add or replace, compared with local/LIVE_FILES.sha256 (the files last recorded as live). After a push, take Wayback Machine snapshots of the page, the CSV and the manifest, and record them in the update log. Then refresh the Codeberg copy (https://codeberg.org/citizen-held-record/register, rule entry J of 19 October 2026): the desk uploads the same files with the same commit message through its Codeberg session (the Codeberg web uploader takes at most 5 files per commit, so an update goes in as several commits with the same message; commit ids then differ from GitHub, so the check compares content: the git tree hash of the head, or a file-by-file comparison of fresh clones), then checks that the head tree hash is the same on both hosts and that the newest dated CSV on Codeberg has the printed checksum, and records both in the update log. If they still differ after 24 hours, a correction note names the update the copy last matched. Then run scripts/check_wayback.py and scripts/preflight.sh --mark-pushed.

Tests. tests/test_hash_entries.sh checks the fingerprints. tests/test_pipeline.sh rebuilds the published files byte for byte and proves each failure case is caught: an edited entry, a vanished entry, a missing owner, a dash or curly quote, a wrong printed checksum, a scoring entry without cost or sub-scores, a second scoring of the same entry. Tests run on scratch copies and never touch the real files.

What is not in the repository. The local folder holds the live baseline, upload lists, audits and the Substack page text. It is never uploaded.

The old prototype build (build_v4.py) is retired. Nothing else writes the register.
