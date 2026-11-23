#!/usr/bin/env python3
"""Tests for scripts/build_essays_index.py (Barry go t4044u, GO-0745, AS-279)."""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_essays_index.py"
fails = 0


def check(name, cond, detail=""):
    global fails
    if cond:
        print("ok  -", name)
    else:
        fails += 1
        print("FAIL -", name, detail)


def run(args, cwd=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + args,
        cwd=cwd or ROOT,
        text=True,
        capture_output=True,
    )


def write_never_name(dirpath, phrase):
    path = Path(dirpath) / "never-name.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["core_id", "phrase", "reason"])
        w.writeheader()
        w.writerow({"core_id": "C1", "phrase": phrase, "reason": "never-name entry 1 (test fixture)"})
    return path


def write_body(bodies, slug, title, date, url, text, audience="everyone"):
    rec = {
        "slug": slug,
        "title": title,
        "subtitle": "",
        "post_date": date,
        "url": url,
        "audience": audience,
        "text": text,
        "body_html": "",
    }
    Path(bodies).mkdir(parents=True, exist_ok=True)
    (Path(bodies) / (slug + ".json")).write_text(json.dumps(rec), encoding="utf-8")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def matches(index, word):
    q = word.lower()
    hits = []
    for e in index["essays"]:
        hay = " ".join([e.get("title") or "", e.get("date") or "", e.get("url") or "", e.get("words") or ""]).lower()
        if q in hay:
            hits.append(e["title"])
    return hits


def main():
    # No write unless first arg is write.
    r = run([])
    check("no-args exits 2 and writes nothing", r.returncode == 2 and "writes only when" in (r.stdout + r.stderr).lower() or "write" in (r.stdout + r.stderr).lower())
    r = run(["--out", "/tmp/should-not-exist.json"])
    check("missing write verb does not write", r.returncode == 2 and not Path("/tmp/should-not-exist.json").exists())

    with tempfile.TemporaryDirectory() as td:
        bodies = Path(td) / "bodies"
        out = Path(td) / "essays-index.json"
        secret = "ZqTestNeverNamePhrase"
        nn = write_never_name(td, secret)
        write_body(
            bodies,
            "channel-crossing-note",
            "A Channel Crossing Note",
            "2026-11-01T15:00:00Z",
            "https://barryesharp.substack.com/p/channel-crossing-note",
            "Small boats and migrants crossed the Channel. Returns must exceed arrivals. %s should vanish." % secret,
        )
        write_body(
            bodies,
            "nuclear-capacity",
            "Nuclear Capacity Is the Test",
            "2026-10-15T18:00:00Z",
            "https://barryesharp.substack.com/p/nuclear-capacity",
            "Reactors, not rooms. The nuclear file stays open until a plant is finished.",
        )
        write_body(
            bodies,
            "private-draft",
            "Secret Draft",
            "2026-11-02T12:00:00Z",
            "https://barryesharp.substack.com/p/secret-draft",
            "migrants boats channel nuclear should not appear from a private post",
            audience="only_paid",
        )
        r = run([
            "write", "--out", str(out), "--bodies-dir", str(bodies),
            "--no-fetch", "--never-name-csv", str(nn),
        ])
        check("write from fixtures exits 0", r.returncode == 0, r.stdout + r.stderr)
        data = load(out)
        check("indexes two public essays, skips private", data["count"] == 2, data.get("count"))
        titles = {e["title"] for e in data["essays"]}
        check("private title absent", "Secret Draft" not in titles)
        check("Channel search hits the channel essay", matches(data, "Channel") == ["A Channel Crossing Note"])
        check("migrants search hits the channel essay", matches(data, "migrants") == ["A Channel Crossing Note"])
        check("boats search hits the channel essay", matches(data, "boats") == ["A Channel Crossing Note"])
        check("nuclear search hits the nuclear essay", matches(data, "nuclear") == ["Nuclear Capacity Is the Test"])
        check("date uses CST calendar form", data["essays"][0]["date"] and "2026" in data["essays"][0]["date"])
        blob = json.dumps(data)
        check("never-name phrase not in the index file", secret.lower() not in blob.lower())
        check("redactions counted", data.get("redactions", 0) >= 1)
        # words are unique and lowercase
        for e in data["essays"]:
            toks = (e.get("words") or "").split()
            check("words unique lowercase for " + e["title"], toks == sorted(set(toks)) and all(t == t.lower() for t in toks))

        # Merge a newly published essay, as the publish hook will.
        added = Path(td) / "new-essay.txt"
        added.write_text("The ledger is the test of housing and boats policy.", encoding="utf-8")
        r = run([
            "write", "--out", str(out), "--bodies-dir", str(bodies), "--no-fetch",
            "--never-name-csv", str(nn),
            "--add-title", "The Ledger Is the Test",
            "--add-date", "2026-11-23T12:00:00Z",
            "--add-url", "https://barryesharp.substack.com/p/the-ledger-is-the-test",
            "--add-text", str(added),
        ])
        check("add-text write exits 0", r.returncode == 0, r.stdout + r.stderr)
        data = load(out)
        check("new essay is in the index", data["count"] == 3, data.get("count"))
        check("boats now hits two essays", len(matches(data, "boats")) == 2, matches(data, "boats"))
        check("ledger search hits the new essay", matches(data, "ledger") == ["The Ledger Is the Test"])

    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
