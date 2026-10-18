Correction entry, 18 October 2026: commit labels

Entered 18 October 2026.

On 18 October 2026 the commit messages of the commits listed below were overwritten by the editor's auto-suggest. The messages do not describe what the commits contain. The history is left unrewritten on purpose: the record is append only, so the fix is this dated entry, not a rewrite.

The intended message for every commit below was the message of update 2026-10-18b: "Update 2026-10-18b: rule entry C (fingerprint layout v2), three new entries, sub-scores, cost column".

Commit and actual content:

ef927ee4474283cda1c9edb89e29e14806e6c257: added manifest/entry-hashes-v2-2026-10-18b.csv
869d11ec37adf40ec06628b982e7698aecf7f72c: added manifest/entry-hashes-v2-2026-10-18b.csv.sha256
df91cd5bb1172284afbb36b514470b53f2e35260: added scripts/add_entry.py
61cecbc8b260894da98732e13953f59fe9b63033: added scripts/build_register.py
a270da7dfc31e53622fc805119a3f83bba0091b7: added scripts/preflight.sh
6e864550a081305c0443a0d9100a9ccd4724975a: added scripts/regcore.py
2847c3896ae9d312fc9e7e9dda5717d885a17170: added tests/test_pipeline.sh
51ee1b202d85bac8b8d07326f871987cfb3b1107: replaced scripts/hash_entries.py
cb09f9e8db66d214def000fc39fb18b170b03097: replaced tests/test_hash_entries.sh
07a1268d39fce354f8b7a868e1346c28788951a5: replaced README.md
ec48fe6d67f14c4d3fae93248e47b897aa0ecc05: replaced index.html

Also: commit fead496 added data/entries.csv with LF line endings instead of the CRLF line endings the build uses. Commit 9d14720 replaced it with the correct file. Both commits stay in the history.

Process fix: commit messages are now typed with auto-suggest turned off, and each message is checked against its content right after the commit.
