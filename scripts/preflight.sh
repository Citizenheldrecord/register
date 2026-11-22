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
UPLOAD_EXCLUDE='(^|/)__pycache__/|\.bak|^sources/_(FAILED_)?TEMPLATE\.md$|^simple-view/|(^|/)\.guard/'
UPLOAD_KEEP='^simple-view/(index\.html|simple-rows\.csv)$'
repo_files(){ find . -type f -not -path './local/*' -not -path '*/__pycache__/*' -not -path './.git/*' -not -path './.guard/*' | sed 's|^\./||' | awk -v ex="$UPLOAD_EXCLUDE" -v keep="$UPLOAD_KEEP" '$0 ~ keep || $0 !~ ex' | sort; }
if [ "${1:-}" = "--mark-pushed" ]; then
  GATE=${DESK_SHIPPING_GATE:-/workspace/sovereign-realism/tools/integrity_check.py}
  if [ ! -f "$GATE" ]; then echo "STOP CHECK MISSING: $GATE"; exit 1; fi
  python3 "$GATE" --shipping-gate --stop-only || { echo "STOP: not recording a live baseline"; exit 1; }
  # Record what is live, not the staging working tree (fault found 20 Nov 2026: hashing staging recorded the unshipped
  # R3.11 regcore.py and test_pipeline.sh as live from 13 Nov, so no upload listed them; Barry go t3824u, t3827u).
  # The baseline is read from the GitHub push clone, only if its HEAD is GitHub main (ls-remote) and its tracked files
  # are unmodified; tracked files only, same exclude rules as repo_files. Otherwise the baseline is left unchanged.
  LIVE_TREE=${LIVE_TREE:-/workspace/tmp-register-push}
  lhead=$(git -C "$LIVE_TREE" rev-parse HEAD 2>/dev/null); rmain=$(git -C "$LIVE_TREE" ls-remote origin refs/heads/main 2>/dev/null | cut -f1)
  if [ -z "$lhead" ] || [ "$lhead" != "$rmain" ]; then echo "NOT RECORDING A LIVE BASELINE: $LIVE_TREE HEAD ${lhead:-none} is not GitHub main ${rmain:-unreadable}"; exit 1; fi
  if ! git -C "$LIVE_TREE" diff --quiet HEAD --; then echo "NOT RECORDING A LIVE BASELINE: $LIVE_TREE has modified tracked files"; exit 1; fi
  ( cd "$LIVE_TREE" && git ls-files | grep -v -E '^(local/|\.git/|\.guard/)|(^|/)__pycache__/' | awk -v ex="$UPLOAD_EXCLUDE" -v keep="$UPLOAD_KEEP" '$0 ~ keep || $0 !~ ex' | sort | xargs -d '\n' sha256sum ) > "$BASE.tmp" && [ -s "$BASE.tmp" ] || { rm -f "$BASE.tmp"; echo "NOT RECORDING A LIVE BASELINE: could not hash $LIVE_TREE"; exit 1; }
  mv "$BASE.tmp" "$BASE"; echo "baseline updated: $(wc -l < $BASE) files recorded as live (GitHub main $lhead, read from $LIVE_TREE)"
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
# 28 Oct 2026 (Barry go 11:16 AM CST): simple view rebuilt at build time and rides the upload; loop check and approved-not-shipped check block the push.
# 14 Nov 2026 (Barry go t3516u): runs before the pipeline tests. inject_index.py writes the FRONT-DOOR tally into index.html and the build
# keeps the old block, so test 15 read last upload's tally whenever the row count changed (15:12 CST NO-GO, 429 vs 430).
IDX=index.html; [ -n "$DRAFT" ] && IDX=local/draft-build-$D/index.html
step "simple view (rebuild simple-view/, link and Suggest a row box on $IDX)"
python3 simple-view/build_simple.py || nogo=1
python3 simple-view/inject_index.py "$IDX" || nogo=1
step "doorway page stamps (Barry go t3972s19490: the six doorway pages ride every upload; restamp if check_public_page_counts finds a gap)"
python3 scripts/stamp_doorway_pages.py --today "${D:0:10}" --update-id "$D" || nogo=1
step "public page counts (Barry go t3972s19490 / GO-0704: the ship fails when check_public_page_counts finds a gap)"
python3 /workspace/sovereign-realism/tools/check_public_page_counts.py --root "$ROOT" --today "${D:0:10}" || { echo "PUBLIC PAGE COUNTS FAILED"; nogo=1; }
step "pipeline tests"; bash tests/test_pipeline.sh > /tmp/pf-pipe.out 2>&1 && tail -1 /tmp/pf-pipe.out || { grep -E "FAIL|PIPELINE" /tmp/pf-pipe.out; nogo=1; }
step "published files unchanged (guardrail 3: every local file already on GitHub is byte-identical; README.md and index.html exempt)"
python3 scripts/check_published_unchanged.py || nogo=1
step "sources gate (Barry approval 27 Oct 2026 15:17 CST: no unsourced row off the allow-list, no expired allow-list entry, no row without a record, no over-claim, no secondary fail, no incomplete FAILED entry)"
python3 scripts/check_sources.py --staging "$ROOT" --allowlist data/sources-gate-allowlist.csv --audit-date "${D:0:10}" | grep -E "^(rows|gate|GATE|OVER|FAIL|FAILED)" || nogo=1
# draft mode: root index.html is left alone (the byte-identical rebuild test compares it); the approved-items check reads an overlay of the root with the draft page
ACSDIR="$ROOT"; if [ -n "$DRAFT" ]; then ACSDIR=$(mktemp -d); for f in "$ROOT"/*; do ln -s "$f" "$ACSDIR/"; done; rm "$ACSDIR/index.html"; cp "$IDX" "$ACSDIR/index.html"; fi
step "loop check (stops on 404, broken chain link, hash or fingerprint mismatch, scored row with no dated log entry; 403, timeouts, missing dates and OPEN costs are report only)"
python3 simple-view/check_loop.py ${LOOP_NO_HTTP:+--no-http} > /tmp/pf-loop.out 2>&1; lrc=$?; grep -E "^\| |^LOOP GATE" /tmp/pf-loop.out; [ $lrc -eq 0 ] || { echo "LOOP CHECK FAILED: see simple-view/LOOP-REPORT.md"; nogo=1; }
step "approved items shipped (/workspace/sovereign-realism/tools/check_approved_shipped.py)"
ACS=${APPROVED_CHECK:-/workspace/sovereign-realism/tools/check_approved_shipped.py}
if [ -f "$ACS" ]; then python3 "$ACS" --build-dir "$ACSDIR" || { echo "APPROVED-NOT-SHIPPED CHECK FAILED: an approved register item is still OPEN"; nogo=1; }
else echo "APPROVED-NOT-SHIPPED CHECK MISSING: $ACS not found; push blocked until it exists"; nogo=1; fi
step "prevention gate BLOCKING (Barry go t2909u, 4 Nov 2026; default PREVENTION_BLOCK=1; new/changed ids block, existing failures listed KNOWN and counted nightly by tools/integrity_check.py s15)"
export PREVENTION_BLOCK=${PREVENTION_BLOCK:-1}
python3 scripts/prevention/run_all.py > /tmp/pf-prevention.out 2>&1 || { echo "PREVENTION SELFTEST FAILED: see /tmp/pf-prevention.out"; nogo=1; }
grep -E "SELFTEST FAIL" /tmp/pf-prevention.out && nogo=1
python3 scripts/prevention/gate.py --preflight || { echo "PREVENTION GATE FAILED: fix the data (never the check)"; nogo=1; }
step "recommendation check (Barry go t3556u, t3557u: a CORRECTIONS note or any added or changed entries.csv id cannot ship without RULE, PRIOR and LIVE)"
# RECOMMENDATION_CHECK may point at a test double only when RECOMMENDATION_CHECK_TEST=1.
# A real preflight always uses the desk tool (Barry go t3557u).
REC=/workspace/sovereign-realism/tools/check_recommendation.py
if [ -n "${RECOMMENDATION_CHECK:-}" ]; then
  if [ "${RECOMMENDATION_CHECK_TEST:-}" = "1" ]; then
    REC="$RECOMMENDATION_CHECK"
  elif [ "$RECOMMENDATION_CHECK" != "$REC" ]; then
    echo "RECOMMENDATION CHECK OVERRIDE REFUSED: RECOMMENDATION_CHECK is test-only (set RECOMMENDATION_CHECK_TEST=1)"
    nogo=1
  fi
fi
rec_files=()
if [ -f "$BASE" ]; then
  while IFS= read -r f; do
    [ -f "$f" ] || continue
    case "$f" in CORRECTIONS/*.md) ;; *) continue ;; esac
    old=$(awk -v fn="$f" '$2==fn {print $1}' "$BASE")
    new=$(sha256sum "$f" | cut -d' ' -f1)
    if [ -z "$old" ] || [ "$old" != "$new" ]; then rec_files+=("$f"); fi
  done < <(find CORRECTIONS -name '*.md' -type f 2>/dev/null | sed 's|^\./||' | sort)
fi
if [ ! -f "$REC" ]; then echo "RECOMMENDATION CHECK MISSING: $REC"; nogo=1
else
  if [ ${#rec_files[@]} -gt 0 ]; then
    for f in "${rec_files[@]}"; do
      python3 "$REC" "$ROOT/$f" --staging "$ROOT" || { echo "RECOMMENDATION CHECK FAILED: $f"; nogo=1; }
    done
  fi
  python3 "$REC" --check-entries --staging "$ROOT" || { echo "RECOMMENDATION CHECK FAILED: data/entries.csv"; nogo=1; }
fi
step "upload list (compared with $BASE, the files last recorded as live)"
declare -A live; while read -r h f; do live[$f]=$h; done < $BASE
add=(); rep=(); while read -r f; do h=$(sha256sum "$f" | cut -d' ' -f1)
  if [ -z "${live[$f]:-}" ]; then add+=("$f"); elif [ "${live[$f]}" != "$h" ]; then rep+=("$f"); fi; done < <(repo_files)
gone=(); for f in "${!live[@]}"; do [ -e "$f" ] || gone+=("$f"); done
echo "ADD (new):"; printf '  %s\n' "${add[@]:-(none)}"
echo "REPLACE (changed):"; printf '  %s\n' "${rep[@]:-(none)}"
if [ ${#gone[@]} -gt 0 ]; then echo "MISSING locally but live (append only, never delete):"; printf '  %s\n' "${gone[@]}"; nogo=1; fi
echo; if [ -n "$DRAFT" ]; then echo "(draft mode: the upload list above is the root as it stands; the draft build is in local/draft-build-$D/ and is not uploaded)"; fi
# Real upload only. Draft stays a check. This step writes neither PAUSE.md nor an approval. Desk script, other repo.
if [ -z "$DRAFT" ]; then
  step "shipping gate (STOP/RUNNING and change approval)"
  MAN=$(mktemp)
  : > "$MAN"
  CHANGED=()
  for f in "${add[@]:-}" "${rep[@]:-}"; do
    [ -n "$f" ] || continue
    CHANGED+=("$f")
  done
  AM=${APPROVAL_MANIFEST:-/workspace/sovereign-realism/tools/approval_manifest.py}
  if [ ! -f "$AM" ]; then echo "APPROVAL MANIFEST TOOL MISSING: $AM"; nogo=1
  elif ! python3 "$AM" --staging "$ROOT" --output "$MAN" -- "${CHANGED[@]}"; then
    echo "APPROVAL MANIFEST FAILED: stamp files ship.py requires must be present"; nogo=1
  fi
  GATE=${DESK_SHIPPING_GATE:-/workspace/sovereign-realism/tools/integrity_check.py}
  APPR=${UPLOAD_APPROVAL:-local/upload-approval.txt}
  if [ ! -f "$GATE" ]; then echo "SHIPPING GATE MISSING: $GATE"; nogo=1
  else python3 "$GATE" --shipping-gate --manifest-file "$MAN" --approval-file "$APPR" || { echo "SHIPPING GATE NO-GO: nothing should be pushed"; nogo=1; }
  fi
  rm -f "$MAN"
fi
if [ $nogo -eq 0 ]; then echo "GO: all checks passed. Upload the files above, then Wayback snapshots of the page, CSV and manifest, then scripts/preflight.sh --mark-pushed"; else echo "NO-GO: fix the failures above. Nothing should be pushed."; fi
exit $nogo
