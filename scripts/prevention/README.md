# Prevention checks (Barry go t2909u / pt2909u)

New scripts only. Never edit `scripts/check_sources.py`, `data/sources-gate-allowlist.csv`, or the 27 Oct seed.

| Script | Purpose |
|---|---|
| check_quote_on_page.py | Exact supporting line must appear on a cited URL (tries every URL / Wayback). |
| check_date_provenance.py | DESK-SET / OUTSIDE date_source cannot remain government_promise without override. |
| check_source_type.py | Sole full support from a lead host blocks a promise or score. Host match, not substring. |
| check_status_derived.py | Typed Status must match the level computed from Supports. |
| check_owner_numbers.py | Owner / test-figure warnings (warn 30 days, then block). |
| check_allowlist_rundown.py | No renewals. 26 Nov 2026: remaining allow-listed rows -> also_watched draft. |
| check_archive_sources.py | Full-support Source blocks need an http Wayback URL (t2871u). |
| monthly_register_audit.py | Monthly shard (1/3) plus scoring dates in the next 30 days. |

Run: `python3 scripts/prevention/run_all.py`

Preflight: warn-only step. Set `PREVENTION_BLOCK=1` to enforce.
