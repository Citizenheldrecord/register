#!/usr/bin/env bash
# Preflight before any push. Usage: scripts/preflight.sh YYYY-MM-DD
# Builds from data/entries.csv, runs every test, verifies printed checksums,
# then prints GO or NO-GO and the exact files to upload or replace.
# After a successful push: scripts/preflight.sh --mark-pushed
set -uo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd); cd "$ROOT"
BASE=local/LIVE_FILES.sha256
repo_files(){ find . -type f -not -path './local/*' -not -path '*/__pycache__/*' -not -path './.git/*' | sed 's|^\./||' | sort; }
if [ "${1:-}" = "--mark-pushed" ]; then repo_files | xargs sha256sum > $BASE; echo "baseline updated: $(wc -l < $BASE) files recorded as live"; exit 0; fi
D=${1:?usage: scripts/preflight.sh YYYY-MM-DD}
nogo=0; step(){ echo; echo "== $1"; }
step "build $D"; python3 scripts/build_register.py --date "$D" || nogo=1
step "overdue guard (every promise past its date is scored or has a dated scoring-pending reason)"
python3 scripts/check_overdue.py "${D:0:10}" ${REGISTER_CALENDAR:+--calendar "$REGISTER_CALENDAR"} || nogo=1
step "ten to watch (each listed id is in the register, not scored, not replaced, not past its date)"
python3 scripts/check_ten_to_watch.py "${D:0:10}" || nogo=1
step "verify printed checksums and grammar"; python3 scripts/build_register.py --verify || nogo=1
step "fingerprint tests"; bash tests/test_hash_entries.sh > /tmp/pf-hash.out 2>&1 && tail -1 /tmp/pf-hash.out || { cat /tmp/pf-hash.out; nogo=1; }
step "pipeline tests"; bash tests/test_pipeline.sh > /tmp/pf-pipe.out 2>&1 && tail -1 /tmp/pf-pipe.out || { grep -E "FAIL|PIPELINE" /tmp/pf-pipe.out; nogo=1; }
step "upload list (compared with $BASE, the files last recorded as live)"
declare -A live; while read -r h f; do live[$f]=$h; done < $BASE
add=(); rep=(); while read -r f; do h=$(sha256sum "$f" | cut -d' ' -f1)
  if [ -z "${live[$f]:-}" ]; then add+=("$f"); elif [ "${live[$f]}" != "$h" ]; then rep+=("$f"); fi; done < <(repo_files)
gone=(); for f in "${!live[@]}"; do [ -e "$f" ] || gone+=("$f"); done
echo "ADD (new):"; printf '  %s\n' "${add[@]:-(none)}"
echo "REPLACE (changed):"; printf '  %s\n' "${rep[@]:-(none)}"
if [ ${#gone[@]} -gt 0 ]; then echo "MISSING locally but live (append only, never delete):"; printf '  %s\n' "${gone[@]}"; nogo=1; fi
echo; if [ $nogo -eq 0 ]; then echo "GO: all checks passed. Upload the files above, then Wayback snapshots of the page, CSV and manifest, then scripts/preflight.sh --mark-pushed"; else echo "NO-GO: fix the failures above. Nothing should be pushed."; fi
exit $nogo
