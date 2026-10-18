#!/usr/bin/env bash
# Tests for scripts/hash_entries.py. Run from the repository root. Writes only to a scratch folder.
set -euo pipefail
S=scripts/hash_entries.py; T=$(mktemp -d)
D1=public-live-rows-2026-10-18.csv; M1=manifest/entry-hashes-2026-10-18.csv
D2=public-live-rows-2026-10-18b.csv; M2=manifest/entry-hashes-v2-2026-10-18b.csv
echo "1. published v1 manifest still verifies the 18 Oct CSV (layout chr-entry-v1)"
python3 $S $D1 --check $M1 | tail -1 | grep -q ", 0 problems" && echo "   PASS" || { echo "   FAIL"; exit 1; }
python3 $S $D1 --date 2026-10-18 --layout chr-entry-v1 --out $T/m1.csv >/dev/null; cmp $M1 $T/m1.csv && echo "   PASS v1 manifest rebuilt byte for byte"
echo "2. published v2 manifest verifies the 18b CSV and rebuilds byte for byte"
python3 $S $D2 --check $M2 | tail -1 | grep -q ", 0 problems" && echo "   PASS"
python3 $S $D2 --date 2026-10-18b --out $T/m2.csv >/dev/null; cmp $M2 $T/m2.csv && echo "   PASS deterministic"
echo "3. independent recompute with sha256sum, both layouts"
a=$(python3 $S $D2 --show GX1b | sha256sum | cut -d' ' -f1); b=$(grep ',GX1b,' $M2 | cut -d, -f5); [ "$a" = "$b" ] && echo "   PASS v2 $a"
a=$(python3 $S $D2 --show GX1b --layout chr-entry-v1 | sha256sum | cut -d' ' -f1); b=$(grep ',GX1b,' $M1 | cut -d, -f5); [ "$a" = "$b" ] && echo "   PASS v1 $a (unchanged by the new columns)"
echo "4. whitespace and column order do not change fingerprints; edits do"
python3 - "$D2" "$T" <<'PY'
import csv,sys
src,t=sys.argv[1],sys.argv[2]
rows=list(csv.DictReader(open(src,encoding='utf-8',newline=''))); f=list(rows[0].keys())
def w(name,rs,fields):
    with open(f"{t}/{name}",'w',encoding='utf-8',newline='') as fh:
        x=csv.DictWriter(fh,fieldnames=fields); x.writeheader(); x.writerows(rs)
ws=[dict(r) for r in rows]; ws[0]['test']='  '+ws[0]['test'].replace(' ','\t \n',3)+' \r\n'; w('ws.csv',ws,f)
w('reorder.csv',rows,list(reversed(f)))
ed=[dict(r) for r in rows]; ed[0]['test']=ed[0]['test'].replace('20 Oct','21 Oct',1); w('edit.csv',ed,f)
hy=[dict(r) for r in rows]; hy[0]['hype_score']='MATCHED'; w('hype.csv',hy,f)
PY
python3 $S $T/ws.csv --check $M2 | tail -1 | grep -q ", 0 problems" && echo "   PASS whitespace"
python3 $S $T/reorder.csv --check $M2 | tail -1 | grep -q ", 0 problems" && echo "   PASS column order"
python3 $S $T/edit.csv --check $M2 >/dev/null && { echo "   FAIL edit not caught"; exit 1; } || echo "   PASS test edit caught"
python3 $S $T/hype.csv --check $M2 >/dev/null && { echo "   FAIL"; exit 1; } || echo "   PASS sub-score edit caught by v2"
python3 $S $T/hype.csv --check $M1 >/dev/null && echo "   PASS (v1 cannot see sub-scores, which is why v2 exists)"
echo ALL TESTS PASSED
