#!/usr/bin/env python3
"""Quote-on-page check (Barry go t2909u). Tries every cited URL / local fixture / Wayback.
New script; does not edit check_sources.py. Exit 0 OK or warn-mode; 1 on block failures."""
from __future__ import annotations
import argparse, sys, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prevention.common import ROOT, norm_quote, parse_sources_record, sources_path

UA = {"User-Agent": "register-check_quote_on_page/1.0"}


_BODY_CACHE: dict[str, str] = {}


# t3062u: page text saved at read time (local/quote-page-cache/<sha256(url)>.txt) is used first; no per-record 40 s live waits.
_DISK = ROOT / "local/quote-page-cache"


def fetch(url: str, timeout=15) -> str:
    import hashlib
    if url in _BODY_CACHE:
        return _BODY_CACHE[url]
    cf = _DISK / (hashlib.sha256(url.encode()).hexdigest() + ".txt")
    if cf.exists():
        _BODY_CACHE[url] = cf.read_text(encoding="utf-8", errors="replace")
        return _BODY_CACHE[url]
    # t3071u: never fetch during the gate. Map file local/quote-page-map.tsv (url<TAB>saved file) or fail now.
    mp = ROOT / "local/quote-page-map.tsv"
    if mp.exists():
        for line in mp.read_text(encoding="utf-8").splitlines():
            parts = line.split("\t")
            if len(parts) == 2 and parts[0] == url and Path(parts[1]).exists():
                _BODY_CACHE[url] = Path(parts[1]).read_text(encoding="utf-8", errors="replace")
                return _BODY_CACHE[url]
    raise RuntimeError("no saved page text (no live fetch, t3071u)")


def quote_in_text(quote: str, body: str) -> bool:
    nq, nb = norm_quote(quote), norm_quote(body)
    if not nq or len(nq) < 12:
        return False
    return nq in nb


def check_record(path: Path, body_by_url: dict[str, str] | None = None) -> list[str]:
    text = path.read_text(encoding="utf-8")
    rec = parse_sources_record(text)
    fails = []
    for i, b in enumerate(rec["blocks"], 1):
        q = b["exact_line"]
        if not q or not b["url"]:
            continue
        if "full" not in (b["supports"] or "").lower():
            continue
        urls = [b["url"]]
        wb = b.get("wayback") or ""
        # t3058u/t3062u: do not fetch Wayback during the gate. Tests may still supply a Wayback body.
        if wb.startswith("http") and body_by_url and wb in body_by_url:
            urls.append(wb)
        found = False
        errors = []
        for u in urls:
            try:
                if body_by_url and u in body_by_url:
                    body = body_by_url[u]
                elif u.startswith("file:"):
                    body = Path(u[5:]).read_text(encoding="utf-8")
                else:
                    body = fetch(u)
                if quote_in_text(q, body):
                    found = True
                    break
            except Exception as e:
                errors.append("%s: %s" % (u[:80], str(e)[:60]))
        if not found:
            fails.append("%s source %d quote not found on any cited URL (%s)" % (path.name, i, "; ".join(errors) or "fetched, no match"))
    return fails


def selftest() -> int:
    good = (ROOT / "scripts/prevention/fixtures/good_page.html").read_text(encoding="utf-8")
    bad = (ROOT / "scripts/prevention/fixtures/bad_page.html").read_text(encoding="utf-8")
    q = "Canada and the EU have signed a treaty framework to allow the EIB to operate in Canada."
    ok = quote_in_text(q, good) and not quote_in_text(q, bad)
    # multi-URL: first misses, second hits
    bodies = {
        "https://example.invalid/miss": bad,
        "https://example.invalid/hit": good,
    }
    # synthesize mini record
    tmp = ROOT / "scripts/prevention/fixtures/_tmp_multi.md"
    tmp.write_text(
        "# SOURCES RECORD: TMP\nStatus: SOURCED\n## Source 1\n- Primary URL: https://example.invalid/miss\n"
        "- Supports: full\n- Exact supporting line (verbatim, straight quotes): \"%s\"\n"
        "- Wayback snapshot URL: https://example.invalid/hit\n" % q,
        encoding="utf-8",
    )
    fails = check_record(tmp, body_by_url=bodies)
    tmp.unlink(missing_ok=True)
    multi_ok = not fails
    print("SELFTEST quote_on_page: known-good %s; known-bad %s; multi-URL %s" % (
        "PASS" if quote_in_text(q, good) else "FAIL",
        "PASS" if not quote_in_text(q, bad) else "FAIL",
        "PASS" if multi_ok else "FAIL",
    ))
    return 0 if ok and multi_ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--mode", choices=("warn", "block"), default="warn")
    ap.add_argument("--ids", nargs="*", help="row ids to check (default: none; use --selftest or pass ids)")
    ap.add_argument("--fixture-record", help="check one local sources markdown against --fixture-page")
    ap.add_argument("--fixture-page", help="local HTML body for fixture-record")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    fails = []
    if args.fixture_record and args.fixture_page:
        body = Path(args.fixture_page).read_text(encoding="utf-8")
        rec = parse_sources_record(Path(args.fixture_record).read_text(encoding="utf-8"))
        url = rec["blocks"][0]["url"] if rec["blocks"] else "file:x"
        fails = check_record(Path(args.fixture_record), body_by_url={url: body})
    for rid in args.ids or []:
        p = sources_path(rid)
        if not p.exists():
            fails.append("%s: no sources record" % rid); continue
        fails.extend(check_record(p))
    for f in fails:
        print("QUOTE FAIL:", f)
    if not fails:
        print("QUOTE OK: %d id(s)" % len(args.ids or ([] if not args.fixture_record else [1])))
    if args.mode == "block" and fails:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
