Correction entry, 20 October 2026: Codeberg commit labels of update 2026-10-19e

Entered 20 October 2026.

On 20 October 2026 the commit messages of the five Codeberg commits of update 2026-10-19e (https://codeberg.org/citizen-held-record/register) were cut short by the web uploader. Each message stops after "correction entry of 19". The history is left unrewritten on purpose: the record is append only, so the fix is this dated entry.

Truncated text, as stored on Codeberg:
"Update 2026-10-19e (1 of 2): six Turkiye visit tests scoring 24 October 2026, correction entry of 19" (commits 1 and 2 below)
"Update 2026-10-19e (2 of 2): six Turkiye visit tests scoring 24 October 2026, correction entry of 19" (commits 3, 4 and 5 below)

Commit, content and intended message:

4e0c0876c0: added public-live-rows-2026-10-19e.csv, public-live-rows-2026-10-19e.csv.sha256, public-live-rows-2026-10-19e.json; replaced index.html. Intended: "Update 2026-10-19e (1 of 2): six Turkiye visit tests scoring 24 October 2026, correction entry of 19 October 2026 (Schedule 1 listing)"
ec2f09421e: replaced data/entries.csv. Intended: "Update 2026-10-19e (1 of 2): six Turkiye visit tests scoring 24 October 2026, correction entry of 19 October 2026 (Schedule 1 listing)"
77ac00f056: replaced README.md. Intended: "Update 2026-10-19e (2 of 2): six Turkiye visit tests scoring 24 October 2026, correction entry of 19 October 2026 (Schedule 1 listing)"
fea37a1a08: added manifest/entry-hashes-v2-2026-10-19e.csv, manifest/entry-hashes-v2-2026-10-19e.csv.sha256. Intended: "Update 2026-10-19e (2 of 2): six Turkiye visit tests scoring 24 October 2026, correction entry of 19 October 2026 (Schedule 1 listing)"
90410517dc: added CORRECTIONS/2026-10-19-schedule1-listing.md. Intended: "Update 2026-10-19e (2 of 2): six Turkiye visit tests scoring 24 October 2026, correction entry of 19 October 2026 (Schedule 1 listing)"

The file contents are byte identical on both hosts: all 9 files of update 2026-10-19e have the same sha256 on GitHub and Codeberg, checked on 20 October 2026. The GitHub messages are exact (commits b3b2732a, dd44dff9, 22ad9623, cecc6eaf, 046b39e0). Each host stored the update as five commits, not the two planned, because files in subfolders went in as separate uploads.

Process fix: Codeberg uploads now use a short summary line of 60 characters or fewer, with the full message in the commit description, and each message is checked against the host's API right after the commit.
