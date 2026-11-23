#!/usr/bin/env python3
"""Build data/essays-index.json for the register search box (Barry go t4044u, GO-0745, AS-279).

The live Search every column box also matches published Sovereign Realism essays
(barryesharp.substack.com) by word and lists title, date and the Substack link.

This script writes only when the first argument is exactly "write". Any other
invocation prints this docstring and exits 2 without writing. It does not take
a date flag. Do not pass --help as a data value.

Usage:
  python3 scripts/build_essays_index.py write --out data/essays-index.json
      Fetch the public archive and post bodies (audience=everyone only), redact
      never-name phrases, write a compact word index.

  python3 scripts/build_essays_index.py write --out PATH --bodies-dir DIR --no-fetch
      Rebuild from a cached bodies directory only (tests, and a no-network rebuild).

  python3 scripts/build_essays_index.py write --out PATH --bodies-dir DIR --no-fetch \\
      --add-title TITLE --add-date DATE --add-url URL --add-text FILE
      Merge one newly published public essay into the bodies dir and rebuild.
      Use this after a Substack post is live, as part of the essay-links attach
      upload, so the new essay is searchable in the same (or next) register ship.

Publish hook: the attach step is a booked tools/ship.py upload of data/essay-links.csv,
not a single wrapper this script can safely take over mid-publish. After the essay
is live, run the write command above, add data/essays-index.json to the attach
manifest (or the next upload if that manifest is already sealed), and do not take
the ship lock while COS-50 or COS-51 holds it.

Public posts only. Private, subscriber-only and draft text are skipped. Never-name
phrases (CORE-MUST-KEEP.csv reasons starting with "never-name") are removed from
the index text and are never printed by this script.
"""
from __future__ import annotations

import csv
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESK = Path(os.environ.get("DESK", "/workspace/sovereign-realism")).resolve()
CST = timezone(timedelta(hours=-6))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
ARCHIVE = "https://barryesharp.substack.com/api/v1/archive"
POST = "https://barryesharp.substack.com/api/v1/posts/"
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
TOKEN = re.compile(r"[a-z0-9]+")


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip += 1
        elif tag in ("p", "br", "div", "li", "h1", "h2", "h3", "h4", "tr", "blockquote"):
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self.skip:
            self.skip -= 1
        elif tag in ("p", "div", "li", "h1", "h2", "h3", "h4", "tr", "blockquote"):
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(raw):
    if not raw:
        return ""
    p = _Text()
    try:
        p.feed(raw)
        p.close()
    except Exception:
        return re.sub(r"<[^>]+>", " ", raw)
    return html.unescape(" ".join(p.parts))


def now_cst():
    helper = DESK / "tools" / "now.sh"
    if helper.is_file():
        import subprocess
        try:
            return subprocess.check_output([str(helper)], text=True).strip()
        except Exception:
            pass
    return datetime.now(CST).strftime("%Y-%m-%d %H:%M CST")


def parse_args(argv):
    out = {
        "out": None,
        "bodies_dir": None,
        "fetch": True,
        "add_title": None,
        "add_date": None,
        "add_url": None,
        "add_text": None,
        "never_name_csv": str(DESK / "tools" / "CORE-MUST-KEEP.csv"),
        "sleep": 0.12,
    }
    args = list(argv)
    while args:
        a = args.pop(0)
        if a == "--out" and args:
            out["out"] = args.pop(0)
        elif a == "--bodies-dir" and args:
            out["bodies_dir"] = args.pop(0)
        elif a == "--no-fetch":
            out["fetch"] = False
        elif a == "--add-title" and args:
            out["add_title"] = args.pop(0)
        elif a == "--add-date" and args:
            out["add_date"] = args.pop(0)
        elif a == "--add-url" and args:
            out["add_url"] = args.pop(0)
        elif a == "--add-text" and args:
            out["add_text"] = args.pop(0)
        elif a == "--never-name-csv" and args:
            out["never_name_csv"] = args.pop(0)
        elif a == "--sleep" and args:
            out["sleep"] = float(args.pop(0))
        else:
            raise SystemExit("unknown argument: %s (see the docstring; this script writes only on 'write')" % a)
    if not out["out"]:
        raise SystemExit("write requires --out PATH")
    if out["bodies_dir"] is None:
        out["bodies_dir"] = str(ROOT / "local" / "essays-bodies")
    return out


def never_name_phrases(path):
    p = Path(path)
    if not p.is_file():
        return []
    phrases = []
    with p.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if (row.get("reason") or "").startswith("never-name"):
                ph = (row.get("phrase") or "").strip()
                if ph:
                    phrases.append(ph)
    phrases.sort(key=len, reverse=True)
    return phrases


def redact(text, phrases):
    if not text:
        return text, 0
    n = 0
    out = text
    for ph in phrases:
        if not ph:
            continue
        pat = re.compile(re.escape(ph), re.I)
        out, c = pat.subn(" ", out)
        n += c
    return out, n


def words_of(*parts):
    blob = " ".join(p or "" for p in parts).lower()
    return " ".join(sorted(set(TOKEN.findall(blob))))


def format_date(post_date):
    if not post_date:
        return "", ""
    s = post_date.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s).astimezone(CST)
    except ValueError:
        return post_date, ""
    return "%d %s %d" % (dt.day, MONTHS[dt.month - 1], dt.year), dt.date().isoformat()


def http_json(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_archive(sleep):
    posts, cursor, seen = [], None, set()
    for _ in range(80):
        url = ARCHIVE + "?sort=new&limit=20"
        if cursor:
            url += "&cursor=" + urllib.parse.quote(cursor, safe="")
        data = http_json(url)
        batch = data.get("posts") or []
        for p in batch:
            slug = p.get("slug")
            if slug and slug not in seen:
                seen.add(slug)
                posts.append(p)
        cursor = data.get("nextCursor")
        if not batch or not cursor:
            break
        time.sleep(sleep)
    return posts


def is_public(post):
    if not post:
        return False
    if post.get("audience") and post.get("audience") != "everyone":
        return False
    if post.get("is_published") is False:
        return False
    typ = post.get("type")
    if typ and typ != "newsletter":
        return False
    return True


def slug_of_url(url):
    m = re.search(r"/p/([A-Za-z0-9._~%-]+)", url or "")
    return urllib.parse.unquote(m.group(1)) if m else ""


def save_body(bodies, rec):
    slug = rec.get("slug") or slug_of_url(rec.get("url") or "")
    if not slug:
        raise SystemExit("body record needs a slug or url")
    rec = dict(rec)
    rec["slug"] = slug
    path = Path(bodies) / (slug + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def load_bodies(bodies):
    d = Path(bodies)
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob("*.json")):
        if p.name.endswith(".tmp"):
            continue
        out.append(json.loads(p.read_text(encoding="utf-8")))
    return out


def fetch_bodies(posts, bodies, sleep):
    ok, skipped = 0, 0
    for i, p in enumerate(posts):
        if not is_public(p):
            skipped += 1
            continue
        slug = p.get("slug")
        if not slug:
            skipped += 1
            continue
        cached = Path(bodies) / (slug + ".json")
        if cached.is_file():
            # Refresh metadata from archive; keep body if already fetched.
            rec = json.loads(cached.read_text(encoding="utf-8"))
            rec.update({
                "title": p.get("title") or rec.get("title"),
                "subtitle": p.get("subtitle") or rec.get("subtitle") or "",
                "post_date": p.get("post_date") or rec.get("post_date"),
                "url": p.get("canonical_url") or rec.get("url") or ("https://barryesharp.substack.com/p/" + slug),
                "audience": p.get("audience") or rec.get("audience"),
                "slug": slug,
            })
            if rec.get("body_html") or rec.get("text"):
                save_body(bodies, rec)
                ok += 1
                continue
        post = http_json(POST + urllib.parse.quote(slug, safe=""))
        if not is_public(post):
            skipped += 1
            time.sleep(sleep)
            continue
        rec = {
            "slug": slug,
            "title": post.get("title") or p.get("title") or "",
            "subtitle": post.get("subtitle") or p.get("subtitle") or "",
            "post_date": post.get("post_date") or p.get("post_date") or "",
            "url": post.get("canonical_url") or p.get("canonical_url") or ("https://barryesharp.substack.com/p/" + slug),
            "audience": post.get("audience") or "everyone",
            "body_html": post.get("body_html") or "",
            "wordcount": post.get("wordcount"),
        }
        save_body(bodies, rec)
        ok += 1
        time.sleep(sleep)
    return ok, skipped


def add_one(opt, phrases):
    if not (opt["add_title"] and opt["add_date"] and opt["add_url"] and opt["add_text"]):
        raise SystemExit("adding one essay needs --add-title, --add-date, --add-url and --add-text")
    path = Path(opt["add_text"])
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".html", ".htm") or "<p" in raw[:1000].lower():
        text = html_to_text(raw)
    else:
        text = raw
    text, _ = redact(text, phrases)
    rec = {
        "slug": slug_of_url(opt["add_url"]),
        "title": opt["add_title"],
        "subtitle": "",
        "post_date": opt["add_date"],
        "url": opt["add_url"],
        "audience": "everyone",
        "text": text,
        "body_html": "",
        "added": now_cst(),
    }
    if not rec["slug"]:
        raise SystemExit("could not read a /p/slug from --add-url")
    save_body(opt["bodies_dir"], rec)


def build_index(bodies, phrases, generated):
    essays = []
    redactions = 0
    for rec in load_bodies(bodies):
        if not is_public(rec):
            continue
        title = rec.get("title") or ""
        subtitle = rec.get("subtitle") or ""
        url = rec.get("url") or ""
        if rec.get("text"):
            plain = rec["text"]
        else:
            plain = html_to_text(rec.get("body_html") or "")
        title, n1 = redact(title, phrases)
        subtitle, n2 = redact(subtitle, phrases)
        plain, n3 = redact(plain, phrases)
        redactions += n1 + n2 + n3
        date, iso = format_date(rec.get("post_date") or rec.get("date") or "")
        if not date and rec.get("date"):
            date = rec["date"]
        if not iso and re.match(r"\d{4}-\d{2}-\d{2}", rec.get("post_date") or ""):
            iso = (rec.get("post_date") or "")[:10]
        essays.append({
            "title": title.strip(),
            "date": date,
            "iso": iso,
            "url": url,
            "words": words_of(title, subtitle, plain, date),
        })
    essays.sort(key=lambda e: (e.get("iso") or "", e.get("title") or ""), reverse=True)
    return {
        "generated": generated,
        "source": "barryesharp.substack.com public archive",
        "count": len(essays),
        "essays": essays,
        "redactions": redactions,
    }, redactions


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def write(opt):
    phrases = never_name_phrases(opt["never_name_csv"])
    Path(opt["bodies_dir"]).mkdir(parents=True, exist_ok=True)
    if opt["add_title"] or opt["add_date"] or opt["add_url"] or opt["add_text"]:
        add_one(opt, phrases)
    if opt["fetch"]:
        posts = fetch_archive(opt["sleep"])
        public = [p for p in posts if is_public(p)]
        ok, skipped = fetch_bodies(public, opt["bodies_dir"], opt["sleep"])
        print("archive %d public posts, bodies stored %d, skipped %d" % (len(public), ok, skipped))
    data, redactions = build_index(opt["bodies_dir"], phrases, now_cst())
    atomic_write(opt["out"], json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print("wrote %s (%d essays, %d redactions)" % (opt["out"], data["count"], redactions))
    return 0


def main(argv):
    if not argv or argv[0] != "write":
        print(__doc__)
        return 2
    return write(parse_args(argv[1:]))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
