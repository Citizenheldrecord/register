#!/usr/bin/env bash
# Preflight before any push. Usage: scripts/preflight.sh YYYY-MM-DD
# Builds from data/entries.csv, runs every test, verifies printed checksums,
# then prints GO or NO-GO and the exact files to upload or replace.
# After a successful push: scripts/preflight.sh --mark-pushed
set -uo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd); cd "$ROOT"
BASE=local/LIVE_FILES.sha256
# Upload exclude list (Barry go 28 Oct 2026 11:43 AM CST, AS-022): desk-only files never go live.
# From simple-view/ only index.html and simple-rows.csv; no __pycache__, no *.bak*, no source templates.
UPLOAD_EXCLUDE='(^|/)__pycache__/|\.bak|^sources/_(FAILED_)?TEMPLATE\.md$|^simple-view/'
UPLOAD_KEEP='^simple-view/(index\.html|simple-rows\.csv)$'
repo_files(){ find . -type f -not -path './local/*' -not -path '*/__pycache__/*' -not -path './.git/*' | sed 's|^\./||' | awk -v ex="$UPLOAD_EXCLUDE" -v keep="$UPLOAD_KEEP" '$0 ~ keep || $0 !~ ex' | sort; }
if [ "${1:-}" = "--mark-pushed" ]; then repo_files | xargs sha256sum > $BASE; echo "baseline updated: $(wc -l < $BASE) files recorded as live"
  python3 scripts/check_published_unchanged.py --refresh >/dev/null && echo "published-files list refreshed from GitHub: local/published-files.txt" || echo "WARNING: could not refresh local/published-files.txt from GitHub"; exit 0; fi
# 27 Oct 2026 (Barry go 04:19): --draft builds into local/draft-build-<date>/ and leaves the upload root untouched.
# Scoring and staging jobs always run: scripts/preflight.sh --draft YYYY-MM-DD. Only the upload step, on Barry's go, runs without --draft.
DRAFT=""; if [ "${1:-}" = "--draft" ]; then DRAFT="--draft"; shift; fi
D=${1:?usage: scripts/preflight.sh [--draft] YYYY-MM-DD}
nogo=0; step(){ echo; echo "== $1"; }
step "build $D${DRAFT:+ (draft: local/draft-build-$D/, upload root untouched)}"; python3 scripts/build_register.py --date "$D" $DRAFT || nogo=1
step "overdue guard (every promise past its date is scored or has a dated scoring-pending reason)"
python3 scripts/check_overdue.py "${D:0:10}" ${REGISTER_CALENDAR:+--calendar "$REGISTER_CALENDAR"} || nogo=1
step "ten to watch (each listed id is in the register, not scored, not replaced, not past its date)"
python3 scripts/check_ten_to_watch.py "${D:0:10}" || nogo=1
step "verify printed checksums and grammar"; python3 scripts/build_register.py --verify || nogo=1
step "fingerprint tests"; bash tests/test_hash_entries.sh > /tmp/pf-hash.out 2>&1 && tail -1 /tmp/pf-hash.out || { cat /tmp/pf-hash.out; nogo=1; }
step "pipeline tests"; bash tests/test_pipeline.sh > /tmp/pf-pipe.out 2>&1 && tail -1 /tmp/pf-pipe.out || { grep -E "FAIL|PIPELINE" /tmp/pf-pipe.out; nogo=1; }
step "published files unchanged (guardrail 3: every local file already on GitHub is byte-identical; README.md and index.html exempt)"
python3 scripts/check_published_unchanged.py || nogo=1
step "sources gate (Barry approval 27 Oct 2026 15:17 CST: no unsourced row off the allow-list, no expired allow-list entry, no row without a record, no over-claim, no secondary fail, no incomplete FAILED entry)"
python3 scripts/check_sources.py --staging "$ROOT" --allowlist data/sources-gate-allowlist.csv --audit-date "${D:0:10}" | grep -E "^(rows|gate|GATE|OVER|FAIL|FAILED)" || nogo=1
# 28 Oct 2026 (Barry go 11:16 AM CST): simple view rebuilt at build time and rides the upload; loop check and approved-not-shipped check block the push.
IDX=index.html; [ -n "$DRAFT" ] && IDX=local/draft-build-$D/index.html
step "simple view (rebuild simple-view/, link and Suggest a row box on $IDX)"
python3 simple-view/build_simple.py || nogo=1
python3 simple-view/inject_index.py "$IDX" || nogo=1
# draft mode: root index.html is left alone (the byte-identical rebuild test compares it); the approved-items check reads an overlay of the root with the draft page
ACSDIR="$ROOT"; if [ -n "$DRAFT" ]; then ACSDIR=$(mktemp -d); for f in "$ROOT"/*; do ln -s "$f" "$ACSDIR/"; done; rm "$ACSDIR/index.html"; cp "$IDX" "$ACSDIR/index.html"; fi
step "loop check (stops on 404, broken chain link, hash or fingerprint mismatch, scored row with no dated log entry; 403, timeouts, missing dates and OPEN costs are report only)"
python3 simple-view/check_loop.py ${LOOP_NO_HTTP:+--no-http} > /tmp/pf-loop.out 2>&1; lrc=$?; grep -E "^\| |^LOOP GATE" /tmp/pf-loop.out; [ $lrc -eq 0 ] || { echo "LOOP CHECK FAILED: see simple-view/LOOP-REPORT.md"; nogo=1; }
step "approved items shipped (/workspace/sovereign-realism/tools/check_approved_shipped.py)"
ACS=${APPROVED_CHECK:-/workspace/sovereign-realism/tools/check_approved_shipped.py}
if [ -f "$ACS" ]; then python3 "$ACS" --build-dir "$ACSDIR" || { echo "APPROVED-NOT-SHIPPED CHECK FAILED: an approved register item is still OPEN"; nogo=1; }
else echo "APPROVED-NOT-SHIPPED CHECK MISSING: $ACS not found; push blocked until it exists"; nogo=1; fi
step "upload list (compared with $BASE, the files last recorded as live)"
declare -A live; while read -r h f; do live[$f]=$h; done < $BASE
add=(); rep=(); while read -r f; do h=$(sha256sum "$f" | cut -d' ' -f1)
  if [ -z "${live[$f]:-}" ]; then add+=("$f"); elif [ "${live[$f]}" != "$h" ]; then rep+=("$f"); fi; done < <(repo_files)
gone=(); for f in "${!live[@]}"; do [ -e "$f" ] || gone+=("$f"); done
echo "ADD (new):"; printf '  %s\n' "${add[@]:-(none)}"
echo "REPLACE (changed):"; printf '  %s\n' "${rep[@]:-(none)}"
if [ ${#gone[@]} -gt 0 ]; then echo "MISSING locally but live (append only, never delete):"; printf '  %s\n' "${gone[@]}"; nogo=1; fi
echo; if [ -n "$DRAFT" ]; then echo "(draft mode: the upload list above is the root as it stands; the draft build is in local/draft-build-$D/ and is not uploaded)"; fi
if [ $nogo -eq 0 ]; then echo "GO: all checks passed. Upload the files above, then Wayback snapshots of the page, CSV and manifest, then scripts/preflight.sh --mark-pushed"; else echo "NO-GO: fix the failures above. Nothing should be pushed."; fi
exit $nogo
