#!/usr/bin/env python3
"""Restamp the six doorway pages from data/entries.csv and data/row-method.csv
(Barry go t3972s19490, GO-0704). Display only: never writes entries.csv.

Called from scripts/build_register.py after a non-draft build, and from
scripts/preflight.sh before check_public_page_counts, so the pages ride every
upload and stay aligned with the live row count and sha.
"""
from __future__ import annotations

import argparse, datetime as dt, hashlib, os, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESK = Path("/workspace/sovereign-realism")
sys.path.insert(0, str(DESK / "tools"))
import check_public_page_counts as counts

DOORWAY_PAGES = (
    "what.html",
    "how.html",
    "coming-up.html",
    "scored.html",
    "register.html",
    "method.html",
)

CST = dt.timezone(dt.timedelta(hours=-6), "CST")


def now_cst():
    return dt.datetime.now(CST)


def stamp_text(when=None):
    when = when or now_cst()
    return when.strftime("%Y-%m-%d %H:%M CST")


def load_live(root: Path, today: str):
    ent = root / "data" / "entries.csv"
    raw = ent.read_bytes()
    rows = counts.read_csv(ent)
    method = counts.read_csv(root / "data" / "row-method.csv") if (root / "data" / "row-method.csv").is_file() else None
    live = counts.live_counts(rows, today, method)
    live["file_sha"] = hashlib.sha256(raw).hexdigest()
    return live


def _sub(text, pat, repl, flags=0, required=True, name=""):
    new, n = re.subn(pat, repl, text, count=1, flags=flags)
    if required and n != 1:
        raise SystemExit("stamp_doorway_pages: failed to replace %s (matches=%d)" % (name or pat, n))
    return new, n


def stamp_page(name: str, text: str, live: dict, built: str, update_id: str = '') -> str:
    sha = live["file_sha"]
    n = live["total"]
    letter = " (update %s)" % update_id if update_id else ""
    built_line = (
        "Built %s%s from the register's data file, "
        "https://citizenheldrecord.github.io/register/data/entries.csv "
        "(%d rows, sha256 %s), as at %s. Display only: it changes no entry."
        % (built, letter, n, sha, live["long"])
    )
    built_pat = (
        r"Built \d{4}-\d{2}-\d{2}(?:\s+\d{1,2}:\d{2}\s*CST)?(?:\s+\(update \d{4}-\d{2}-\d{2}[a-z]?\))? "
        r"from the register's data file,\s*"
        r"https://citizenheldrecord\.github\.io/register/data/entries\.csv\s*"
        r"\(\d+ rows, sha256 [0-9a-fA-F]{64}\), as at [^.]+\. Display only: it changes no entry\."
    )
    text, k = _sub(text, built_pat, built_line, required=False, name="Built line in " + name)
    if k != 1:
        if name == "method.html":
            snippet = '<p class="small">' + built_line + '</p>\n'
            if "</main>" in text:
                text = text.replace("</main>", snippet + "</main>", 1)
            else:
                text = text + "\n" + snippet
        else:
            raise SystemExit("stamp_doorway_pages: no Built line on %s" % name)

    if name == "what.html":
        text, _ = _sub(
            text,
            r"As at \d{1,2} (?:January|February|March|April|May|June|July|August|September|October|November|December) \d{4} "
            r"the register holds \d+ promises\. \d+ passed, \d+ failed and \d+ are waiting for their date\.",
            "As at %s the register holds %d promises. %d passed, %d failed and %d are waiting for their date."
            % (live["long"], live["promises"], live["state"]["PASS"], live["state"]["FAILED"], live["state"]["Open"]),
            name="promises sentence in what.html",
        )

    if name == "scored.html":
        text, _ = _sub(
            text,
            r"Every result since the register began, \d+ passed and \d+ failed in all,",
            "Every result since the register began, %d passed and %d failed in all,"
            % (live["state"]["PASS"], live["state"]["FAILED"]),
            name="passed/failed in all on scored.html",
        )

    if name == "register.html":
        def repl_copy(m):
            open_tag = m.group(1) or ""
            close_tag = m.group(2) or ""
            return "This copy: %d rows, sha256 %s%s%s" % (n, open_tag, sha, close_tag)
        new, k = re.subn(
            r"This copy: \d+ rows, sha256 (<code[^>]*>)?[0-9a-fA-F]{64}(</code>)?",
            repl_copy,
            text,
            count=1,
        )
        if k != 1:
            raise SystemExit("stamp_doorway_pages: failed to replace This copy line on register.html")
        text = new

    if name == "coming-up.html":
        text, _ = _sub(
            text,
            r"These are the promises due to be scored in the next 30 days, to [^,]+, in date order\.",
            "These are the promises due to be scored in the next 30 days, to %s, in date order." % live["end_long"],
            name="next-30 window on coming-up.html",
        )
        text, _ = _sub(
            text,
            r"Next 30 days \(\d+\)",
            "Next 30 days (%d)" % live["soon"],
            name="Next 30 days count on coming-up.html",
        )

    if name == "method.html":
        if "method" not in live:
            raise SystemExit("stamp_doorway_pages: row-method.csv is required to restamp method.html")
        m = live["method"]
        p = live["method_pct"]
        text, _ = _sub(
            text,
            r"Of the \d+ rows in the method side-file on \d{1,2} [A-Z][a-z]{2} \d{4}, "
            r"\d+ \(\d+\.\d+ per cent\) carry a desk-default date, "
            r"\d+ \(\d+\.\d+ per cent\) a government date, "
            r"\d+ \(\d+\.\d+ per cent\) a statutory date, and "
            r"\d+ \(\d+\.\d+ per cent\) a date basis that is not recorded\.",
            "Of the %d rows in the method side-file on %s, "
            "%d (%s per cent) carry a desk-default date, "
            "%d (%s per cent) a government date, "
            "%d (%s per cent) a statutory date, and "
            "%d (%s per cent) a date basis that is not recorded."
            % (live["method_total"], live["short"],
               m["desk-default"], p["desk-default"],
               m["government"], p["government"],
               m["statutory"], p["statutory"],
               m["not recorded"], p["not recorded"]),
            name="method date-basis counts",
        )
        text, _ = _sub(
            text,
            r"Counts on this page were computed on \d{1,2} [A-Z][a-z]{2} \d{4} from data/row-method\.csv \(\d+ rows\)\.",
            "Counts on this page were computed on %s from data/row-method.csv (%d rows)."
            % (live["short"], live["method_total"]),
            name="method counts-on-this-page line",
        )
    return text


def current_doorway_findings(root: Path, today: str):
    """Return FINDING lines that name one of the six doorway pages."""
    data = {"data/entries.csv": (root / "data" / "entries.csv").read_bytes()}
    rm = root / "data" / "row-method.csv"
    if rm.is_file():
        data["data/row-method.csv"] = rm.read_bytes()
    pages = {}
    for name in DOORWAY_PAGES:
        path = root / name
        if path.is_file():
            pages[name] = path.read_text(encoding="utf-8")
    findings, live, sha = counts.run(pages, data, today)
    door = [f for f in findings if any((" " + name + ":") in f or f.startswith("FINDING " + name + ":") for name in DOORWAY_PAGES)]
    return door, live, sha


def stamp_tree(root: Path, today: str, built: str, dry=False, force=False, update_id: str = ''):
    live = load_live(root, today)
    if not force:
        existing, _, _ = current_doorway_findings(root, today)
        letter_missing = False
        if update_id:
            needle = "update %s" % update_id
            letter_missing = any(
                needle not in (root / name).read_text(encoding="utf-8")
                for name in DOORWAY_PAGES if (root / name).is_file()
            )
        if not existing and not letter_missing:
            return live, []
    written = []
    for name in DOORWAY_PAGES:
        path = root / name
        if not path.is_file():
            raise SystemExit("stamp_doorway_pages: missing %s" % path)
        old = path.read_text(encoding="utf-8")
        new = stamp_page(name, old, live, built, update_id=update_id)
        if new != old:
            if not dry:
                path.write_text(new, encoding="utf-8")
            written.append(name)
    return live, written


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=str(ROOT), help="register tree (HTML at the root, data/entries.csv under it)")
    ap.add_argument("--today", help="count date YYYY-MM-DD (default: desk CST today)")
    ap.add_argument("--built", help="Built stamp, e.g. '2026-11-21 20:35 CST' (default: now CST)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="rewrite even when check_public_page_counts already PASSes")
    ap.add_argument("--update-id", default="", help="update letter, e.g. 2026-11-21l, written on every doorway page")
    a = ap.parse_args(argv)
    today = a.today or counts.desk_today()
    built = a.built or stamp_text()
    live, written = stamp_tree(Path(a.root), today, built, dry=a.dry_run, force=a.force, update_id=a.update_id)
    print("DOORWAY STAMP %s: %d rows, sha256 %s, built %s, as at %s%s"
          % ("DRY" if a.dry_run else "OK", live["total"], live["file_sha"], built, live["long"],
             "; rewrote " + ", ".join(written) if written else "; already current"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
