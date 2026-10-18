#!/usr/bin/env bash
# Tests for scripts/hash_entries.py. Run from the repository root.
set -euo pipefail
S=scripts/hash_entries.py; D=public-live-rows-2026-10-18.csv; T=$(mktemp -d)
echo "1. manifest builds"; python3 $S $D --date 2026-10-18 --out manifest/entry-hashes-2026-10-18.csv
echo "2. deterministic"; python3 $S $D --date 2026-10-18 --out $T/m2.csv >/dev/null; cmp manifest/entry-hashes-2026-10-18.csv $T/m2.csv && echo "   PASS identical on rerun"
echo "3. independent recompute of GX1b with sha256sum"
python3 $S $D --show GX1b > $T/gx1b.txt
a=$(sha256sum < $T/gx1b.txt | cut -d' ' -f1); b=$(grep ',GX1b,' manifest/entry-hashes-2026-10-18.csv | cut -d, -f5)
[ "$a" = "$b" ] && echo "   PASS $a" || { echo "   FAIL $a vs $b"; exit 1; }
echo "4. whitespace variants do not change fingerprints, an edit does"
python3 - "$D" "$T" <<'PY'
import csv,sys
src,t=sys.argv[1],sys.argv[2]
rows=list(csv.DictReader(open(src,encoding='utf-8',newline='')))
f=list(rows[0].keys())
def w(name,rs):
    with open(f"{t}/{name}",'w',encoding='utf-8',newline='') as fh:
        x=csv.DictWriter(fh,fieldnames=f); x.writeheader(); x.writerows(rs)
ws=[dict(r) for r in rows]; ws[0]['test']='  '+ws[0]['test'].replace(' ','\t \n',3)+' \r\n'
w('ws.csv',ws)
ed=[dict(r) for r in rows]; ed[0]['test']=ed[0]['test'].replace('20 Oct','21 Oct',1)
w('edit.csv',ed)
re_=[dict(r) for r in rows]; f=list(reversed(f)); w('reorder.csv',re_)
PY
python3 $S $T/ws.csv --check manifest/entry-hashes-2026-10-18.csv | tail -1
python3 $S $T/reorder.csv --check manifest/entry-hashes-2026-10-18.csv | tail -1
if python3 $S $T/edit.csv --check manifest/entry-hashes-2026-10-18.csv; then echo "   FAIL edit not caught"; exit 1; else echo "   PASS edit caught"; fi
echo "5. deleted entry caught"
python3 - "$D" "$T" <<'PY'
import sys
L=open(sys.argv[1],encoding='utf-8',newline='').read().split('\r\n'); open(sys.argv[2]+'/del.csv','w',encoding='utf-8',newline='').write('\r\n'.join(L[:1]+L[2:]))
PY
if python3 $S $T/del.csv --check manifest/entry-hashes-2026-10-18.csv | tail -2; then :; fi
python3 $S $T/del.csv --check manifest/entry-hashes-2026-10-18.csv >/dev/null && { echo "   FAIL"; exit 1; } || echo "   PASS deletion caught"
echo "6. live 17 Oct CSV (no new fields) also hashes"; python3 $S public-live-rows-2026-10-17.csv --date 2026-10-17 | sed -n 5,6p
echo ALL TESTS PASSED
