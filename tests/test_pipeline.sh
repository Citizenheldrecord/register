#!/usr/bin/env bash
# Pipeline tests. Each runs on a scratch copy of the repository; the real files are never touched.
set -uo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd); D=$(ls "$ROOT"/public-live-rows-*.csv | sed -E "s/.*public-live-rows-(.+)\.csv/\1/" | sort | tail -1); fails=0
fresh(){ W=$(mktemp -d); cp -r "$ROOT"/. "$W"/; rm -rf "$W/local"; cd "$W"; }
ok(){ echo "  PASS $1"; }; bad(){ echo "  FAIL $1"; fails=$((fails+1)); }
expect_fail(){ local name=$1; shift; if "$@" >/tmp/pl.out 2>&1; then bad "$name (build should have failed)"; else grep -q "$PATTERN" /tmp/pl.out && ok "$name: $(grep -m1 "$PATTERN" /tmp/pl.out | cut -c1-110)" || { bad "$name (wrong reason)"; cat /tmp/pl.out; }; fi; }
build(){ python3 scripts/build_register.py --date ${1:-$D}; }
# Scratch update id for builds in tests: must sort after every real update, so the latest real manifest is the one checked.
SCRATCH=2099-12-31

echo "1. full build reproduces the current update ($D) byte for byte; first 18 Oct files untouched"
fresh; T=$(mktemp -d); python3 scripts/build_register.py --date $D --out-dir $T >/dev/null || bad "build"
[ "$(sha256sum "$ROOT/public-live-rows-2026-10-18.csv" | cut -c1-64)" = a640b60b737d8e2688588fb8e6230b9af2fa7f7291ad305104c209ed0a357624 ] && ok "18 Oct CSV still a640b60b..." || bad "18 Oct CSV changed"
for f in README.md index.html public-live-rows-$D.csv public-live-rows-$D.csv.sha256 public-live-rows-$D.json manifest/entry-hashes-v2-$D.csv manifest/entry-hashes-v2-$D.csv.sha256; do
  cmp -s "$ROOT/$f" "$T/$f" && ok "identical $f" || bad "differs $f"; done

echo "2. an edited prior entry fails"
fresh; python3 - <<'PY'
p='data/entries.csv'; s=open(p,encoding='utf-8',newline='').read(); s=s.replace('records filed by 20 Oct','records filed by 21 Oct',1); open(p,'w',encoding='utf-8',newline='').write(s)
PY
PATTERN="CHANGED GX1b" expect_fail "edit caught" build $SCRATCH

echo "3. a vanished entry fails"
fresh; python3 - <<'PY'
p='data/entries.csv'; L=open(p,encoding='utf-8',newline='').read().split('\r\n'); open(p,'w',encoding='utf-8',newline='').write('\r\n'.join(L[:1]+L[2:]))
PY
PATTERN="VANISHED GX1b" expect_fail "deletion caught" build $SCRATCH

echo "4. missing owner fails"
fresh; python3 - <<'PY'
import csv,io
p='data/entries.csv'; r=list(csv.DictReader(open(p,encoding='utf-8',newline=''))); h=list(r[0]); r.append(dict(r[0],id='NEW1',owner='',supersedes_id='',supersedes_hash=''))
b=io.StringIO(); w=csv.DictWriter(b,fieldnames=h); w.writeheader(); w.writerows(r); open(p,'w',encoding='utf-8',newline='').write(b.getvalue())
PY
PATTERN="owner is empty" expect_fail "missing owner caught" build $SCRATCH

echo "5. curly quote and em dash fail house grammar"
fresh; python3 scripts/add_entry.py --dry-run commit --id GRAM1 --section DESK --scoring-date "30 Nov 2026" --test "PASS: it works. FAILED: it does not" --owner "Barry Sharp (desk)" --date-source "DESK-SET: test" >/dev/null || bad "valid dry run"
PATTERN="house grammar" expect_fail "em dash caught" python3 scripts/add_entry.py commit --id GRAM1 --section DESK --scoring-date "30 Nov 2026" --test "PASS: it works — FAILED: it does not" --owner "Barry" --date-source "DESK-SET: test"
PATTERN="house grammar" expect_fail "curly quote in page caught" bash -c "sed -i 's/The page is dull on purpose/The page’s dull on purpose/' README.md && python3 scripts/build_register.py --date 2026-10-19"

echo "6. a mismatched printed checksum fails verify"
fresh; sed -i -E 's/<span id="printed">[0-9a-f]{64}/<span id="printed">0000000000000000000000000000000000000000000000000000000000000000/' index.html
PATTERN="index.html printed" expect_fail "printed mismatch caught" python3 scripts/build_register.py --verify

echo "7. scoring is a new entry; rules enforced; prior untouched; page shows the original as closed"
fresh
PATTERN="never OPEN" expect_fail "OPEN cost on scoring day refused" python3 scripts/add_entry.py score --supersedes AI1 --result PASS --scored-on 2026-10-31 --evidence https://example.org/x --cost-to-date "OPEN" --hype OPEN --means OPEN --cost FAILED
PATTERN="blocking layer" expect_fail "FAILED without layer refused" python3 scripts/add_entry.py score --supersedes AI1 --result FAILED --scored-on 2026-10-31 --evidence https://example.org/x --cost-to-date "FAILED: no public figure; held by Anthropic" --hype OPEN --means OPEN --cost FAILED
PATTERN="MATCHED, MIXED, FAILED or OPEN" expect_fail "bad sub-score refused" python3 scripts/add_entry.py score --supersedes AI1 --result PASS --scored-on 2026-10-31 --evidence https://example.org/x --cost-to-date "FAILED: held by Anthropic" --hype GOOD --means OPEN --cost FAILED
before=$(python3 scripts/hash_entries.py data/entries.csv --show AI1 | sha256sum)
python3 scripts/add_entry.py score --supersedes AI1 --result PASS --scored-on 2026-10-31 --evidence https://example.org/x --cost-to-date "FAILED: no public figure; held by Anthropic" --hype OPEN --means OPEN --cost FAILED >/tmp/pl.out && ok "scoring entry appended: $(cut -c1-80 /tmp/pl.out)" || { bad "score"; cat /tmp/pl.out; }
[ "$before" = "$(python3 scripts/hash_entries.py data/entries.csv --show AI1 | sha256sum)" ] && ok "AI1 row unchanged in the data" || bad "AI1 changed"
build 2026-10-31 >/tmp/pl.out 2>&1 && ok "build after scoring: $(grep -m1 'new since' /tmp/pl.out)" || { bad "build after scoring"; cat /tmp/pl.out; }
grep -q "^AI1 | .* | CLOSED: scored in AI1-SCORED-20261031 | " README.md && ok "README shows AI1 as CLOSED: scored in AI1-SCORED-20261031" || bad "README closed display"
grep -q 'CLOSED\[r.id\]' index.html && ok "page links closed rows to the scoring entry" || bad "page closed display"
python3 scripts/hash_entries.py public-live-rows-2026-10-31.csv --check manifest/entry-hashes-v2-2026-10-18b.csv | tail -1 | grep -q ", 0 problems" && ok "all 118 prior v2 fingerprints unchanged" || bad "prior changed"
PATTERN="already has a scoring entry" expect_fail "double scoring refused" python3 scripts/add_entry.py score --supersedes AI1 --result FAILED --layer courts --scored-on 2026-11-01 --evidence https://example.org/y --cost-to-date "FAILED: held by Anthropic" --hype OPEN --means OPEN --cost FAILED

echo "7b. a changed sub-score on an existing entry fails (v2)"
fresh; python3 - <<'PY2'
import csv,io
p='data/entries.csv'; r=list(csv.DictReader(open(p,encoding='utf-8',newline=''))); h=list(r[0]); r[0]['hype_score']='MATCHED'
b=io.StringIO(); w=csv.DictWriter(b,fieldnames=h); w.writeheader(); w.writerows(r); open(p,'w',encoding='utf-8',newline='').write(b.getvalue())
PY2
PATTERN="CHANGED GX1b" expect_fail "sub-score edit caught" build $SCRATCH

echo "8. a resolved entry without cost to date or sub-scores fails the build"
fresh; python3 - <<'PY'
import csv,io
p='data/entries.csv'; r=list(csv.DictReader(open(p,encoding='utf-8',newline=''))); h=list(r[0])
r.append(dict(r[0],id='BAD-SCORE',sort_date='2026-10-25',status='SCORED 25 Oct 2026: PASS',cost_to_date='OPEN until scoring date 20 Oct 2026'))
b=io.StringIO(); w=csv.DictWriter(b,fieldnames=h); w.writeheader(); w.writerows(r); open(p,'w',encoding='utf-8',newline='').write(b.getvalue())
PY
PATTERN="needs cost to date" expect_fail "resolved without cost caught" build $SCRATCH

echo "9. redate appends a new entry citing the old fingerprint"
fresh; python3 scripts/add_entry.py redate --supersedes FIR1 --id FIR1-R1 --scoring-date "15 Jan 2027" --date-source "DESK-SET: test redate" >/tmp/pl.out && build $SCRATCH >/tmp/pl2.out 2>&1 && grep -q "1 new since the latest manifest \['FIR1-R1'\]" /tmp/pl2.out && ok "redate built; old FIR1 kept" || { bad "redate"; cat /tmp/pl.out /tmp/pl2.out; }


echo "10. page logic: a synthetic scored row marks its original CLOSED with a link (node, temp copy)"
fresh; node -e '
const fs=require("fs");const h=fs.readFileSync("index.html","utf8");
const line=h.split("\n").find(l=>l.startsWith("const CLOSED="));
const tpl=h.match(/<td>\$\{CLOSED\[r\.id\][^\n]*?esc\(r\.status\)\}<\/td>/)[0];
const esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c]));
const ROWS=[{id:"AI1",status:"LIVE"},{id:"AI1-SCORED-20261031",status:"SCORED 31 Oct 2026: PASS",supersedes_id:"AI1"},{id:"AI2",status:"LIVE"}];
eval(line.replace("const CLOSED","var CLOSED"));
const cell=r=>eval("`"+tpl+"`");
const a=cell(ROWS[0]),b=cell(ROWS[1]),c=cell(ROWS[2]);
if(!a.includes("CLOSED: scored in AI1-SCORED-20261031")||!a.includes("href=\"#row-AI1-SCORED-20261031\""))throw "original not closed: "+a;
if(!b.includes("SCORED 31 Oct 2026: PASS")||c.includes("CLOSED"))throw "wrong rows closed";
console.log(a);' >/tmp/pl.out 2>&1 && ok "original shows $(sed 's/<[^>]*>//g' /tmp/pl.out); scoring row and unscored row unchanged" || { bad "page closed logic"; cat /tmp/pl.out; }
grep -q "<th>Hype</th><th>Means</th><th>Cost</th>" index.html && grep -q "r.hype_score" index.html && ok "page table shows hype, means and cost" || bad "sub-score columns on page"
grep -q "| Cost to date | Hype | Means | Cost$" README.md && ok "README tables show hype, means and cost" || bad "README sub-score columns"

echo "12. transfer cap: a sixth open transfer entry is refused (R-2026-10-19-H)"
fresh; n=$(python3 -c "import csv;print(sum(1 for r in csv.DictReader(open('data/entries.csv',encoding='utf-8',newline='')) if r['id'].startswith('XFER-') and r['status']=='LIVE'))")
for i in $(seq $((n+1)) 5); do python3 scripts/add_entry.py commit --id XFER-TEST-$i --section CANADA --scoring-date "30 Nov 2027" --test "PASS: test. FAILED: test." --owner "Test owner" --date-source "DESK-SET: test" >/dev/null || bad "cap setup $i"; done
PATTERN="transfer cap" expect_fail "sixth open transfer entry refused" python3 scripts/add_entry.py commit --id XFER-TEST-6 --section CANADA --scoring-date "30 Nov 2027" --test "PASS: test. FAILED: test." --owner "Test owner" --date-source "DESK-SET: test"
python3 scripts/add_entry.py commit --id NOTXFER-TEST --section CANADA --scoring-date "30 Nov 2027" --test "PASS: test. FAILED: test." --owner "Test owner" --date-source "DESK-SET: test" >/dev/null && ok "non-transfer entry still allowed at the cap" || bad "non-transfer entry refused"

echo "13. next on the clock lists no CLOSED entry and carries the past-due line"
fresh; build $SCRATCH >/dev/null 2>&1; python3 - <<'PY' && ok "strip clean" || bad "strip"
import re,csv
t=open('index.html',encoding='utf-8').read(); m=re.search(r'<!-- NEXT-ON-CLOCK -->(.*?)<!-- /NEXT-ON-CLOCK -->',t,re.S); assert m
ids=re.findall(r'<tr><td>[^<]*</td><td>([^<]*)</td>',m.group(1)); assert len(ids)<=5
rows=list(csv.DictReader(open('data/entries.csv',encoding='utf-8',newline='')))
closed={r['supersedes_id'] for r in rows if r['supersedes_id']}
assert not set(ids)&closed and 'Past their scoring date' in m.group(1)
PY

echo "14. housekeeping (R-2026-10-24-A): unlogged removal fails; logged removal passes; logged edit to a protected field fails"
hk(){ python3 - "$@" <<'PY'
import csv,sys,glob
sys.path.insert(0,'scripts'); import hash_entries as he
field,new,log=sys.argv[1],sys.argv[2],sys.argv[3]=='log'
p='data/entries.csv'; rd=csv.DictReader(open(p,encoding='utf-8',newline='')); h=rd.fieldnames; rows=list(rd)
r=next(x for x in rows if x['id']=='EA-REFORM'); before=he.fingerprint(r,'chr-entry-v2'); r[field]=new
w=csv.DictWriter(open(p,'w',encoding='utf-8',newline=''),fieldnames=h,lineterminator='\r\n'); w.writeheader(); w.writerows(rows)
if log:
    open('data/housekeeping-log.csv','a',encoding='utf-8',newline='').write('2099-12-31,2099-12-31,EA-REFORM,%s,test,chr-entry-v2,%s,%s\n'%(field,before,he.fingerprint(r,'chr-entry-v2')))
PY
}
fresh; hk date_source "scoring date set by the register; first check 23 Oct 2026, Supreme Court leave decision" nolog
PATTERN="CHANGED EA-REFORM\|HOUSEKEEPING EA-REFORM: log lists it but not fingerprint" expect_fail "unlogged removal caught" build $SCRATCH
fresh; hk date_source "DESK-SET: scoring date set by the register" log
build $SCRATCH >/tmp/pl.out 2>&1 && grep -q "housekeeping edits as logged" /tmp/pl.out && grep -q "^# housekeeping_log: data/housekeeping-log.csv" manifest/entry-hashes-v2-$SCRATCH.csv && ok "logged removal accepted, printed and named in the manifest" || { bad "logged removal"; cat /tmp/pl.out; }
fresh; hk owner "Someone else" log
PATTERN="not a housekeeping removal in owner" expect_fail "logged owner edit refused" build $SCRATCH
fresh; hk date_source "DESK-SET: scoring date set by the register, now with added words" log
PATTERN="not a housekeeping removal in date_source" expect_fail "logged addition refused" build $SCRATCH

echo; [ $fails -eq 0 ] && echo "PIPELINE TESTS: ALL PASSED" || echo "PIPELINE TESTS: $fails FAILED"; exit $fails
