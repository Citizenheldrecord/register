"""Shared helpers for prevention checks (Barry go t2909u)."""
from __future__ import annotations
import csv, os, re, urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Host classes: match on hostname, never substring (fixes rtx.com / x.com).
PRIMARY_SUFFIXES = (
    ".gc.ca", ".canada.ca", ".gov", ".gov.uk", ".gov.au", ".europa.eu",
    ".parl.ca", ".ourcommons.ca", ".justice.gc.ca", ".laws-lois.justice.gc.ca",
    ".federalregister.gov", ".whitehouse.gov", ".defense.gov", ".war.gov",
    ".un.org", ".who.int", ".oecd.org", ".imf.org", ".worldbank.org",
    ".statcan.gc.ca", ".bankofcanada.ca", ".gazette.gc.ca",
)
COURT_SUFFIXES = (".fct-cf.ca", ".scc-csc.ca", ".courts.", ".tribunal.")
PRESS_HOSTS = {
    "devdiscourse.com", "reuters.com", "bloomberg.com", "ft.com", "wsj.com",
    "theglobeandmail.com", "nationalpost.com", "cbc.ca", "globalnews.ca",
    "politico.com", "axios.com", "apnews.com", "northernbeat.ca",
    "fraservalleytoday.ca", "morningstar.com", "nationalobserver.com",
    "dailyhive.com", "theguardian.com", "nytimes.com", "washingtonpost.com",
}
LEAD_HOSTS = PRESS_HOSTS | {
    "x.com", "twitter.com", "substack.com", "barryesharp.substack.com",
    "threads.net", "threads.com", "facebook.com", "linkedin.com",
    "chatgpt.com", "chat.openai.com", "claude.ai", "gemini.google.com",
    "perplexity.ai", "copilot.microsoft.com",
}
COMPANY_HINTS = (".com", ".io", ".ai")  # narrowed by not-primary


def host_of(url: str) -> str:
    try:
        h = urllib.parse.urlparse(url).hostname or ""
    except Exception:
        return ""
    return h.lower().removeprefix("www.")


def classify_host(host: str, owner: str = "", url: str = "") -> str:
    """Return primary | court | company | lead | unknown. Match on host, not substring."""
    if not host:
        return "unknown"
    own_l = (owner or "").lower()
    url_l = (url or "").lower()
    # Desk / register holder primary: owner's own github/codeberg/desk path
    if ("desk" in own_l or "barry sharp" in own_l) and (
        "github.com/citizenheldrecord" in url_l
        or "codeberg.org/citizen-held-record" in url_l
        or host in ("github.com", "codeberg.org")
    ):
        return "company"
    if host in LEAD_HOSTS or host.endswith(".substack.com"):
        # Substack is lead unless it is the row owner's own publication and owner is desk
        if host.endswith("substack.com") and ("desk" in own_l or "barry sharp" in own_l) and "barryesharp" in host:
            return "company"
        return "lead"
    if any(host.endswith(s) or (s.strip(".") and s.strip(".") in host) for s in COURT_SUFFIXES):
        return "court"
    if any(host.endswith(s) for s in PRIMARY_SUFFIXES) or host.endswith(".gc.ca") or host.endswith(".canada.ca"):
        return "primary"
    # company: holder primary only when host relates to owner (token match, not x-in-rtx)
    own = re.sub(r"[^a-z0-9]", "", own_l)
    hflat = re.sub(r"[^a-z0-9]", "", host)
    tokens = [t for t in re.findall(r"[a-z0-9]{3,}", own_l) if t not in ("the", "and", "for", "minister", "ministry", "department")]
    if any(tok in hflat for tok in tokens):
        return "company"
    # bare company domains without owner match stay lead for sole-support purposes
    if any(host.endswith(s) for s in (".com", ".io", ".ai", ".net", ".org")):
        return "lead"
    return "unknown"


def norm_quote(s: str) -> str:
    s = s or ""
    s = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", s)
    s = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&quot;", '"'), ("&#39;", "'"),
                 ("&rsquo;", "'"), ("&lsquo;", "'"), ("&rdquo;", '"'), ("&ldquo;", '"')):
        s = s.replace(a, b)
    s = re.sub(r"&\w+;", " ", s)
    s = re.sub(r"[\u200b\u200c\u200d\u2060\ufeff\u00ad]", "", s)
    s = s.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    s = s.replace("–", "-").replace("—", "-").replace(" ", " ")
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def parse_sources_record(text: str) -> dict:
    status_m = re.search(r"^Status:\s*(.+)$", text, re.M)
    status = status_m.group(1).strip() if status_m else ""
    blocks = []
    parts = re.split(r"\n## Source \d+", text)
    for part in parts[1:]:
        url_m = re.search(r"Primary URL:\s*(\S+)", part)
        sup_m = re.search(r"Supports:\s*(.+)$", part, re.M)
        line_m = re.search(r"Exact supporting line[^:]*:\s*[\"']?(.*?)[\"']?\s*$", part, re.M)
        wb_m = re.search(r"Wayback snapshot URL:\s*(.+)$", part, re.M)
        blocks.append({
            "url": (url_m.group(1).strip() if url_m else ""),
            "supports": (sup_m.group(1).strip() if sup_m else ""),
            "exact_line": (line_m.group(1).strip().strip('"').strip("'") if line_m else ""),
            "wayback": (wb_m.group(1).strip() if wb_m else ""),
        })
    return {"status": status, "blocks": blocks, "text": text}


def load_entries(path: Path | None = None):
    path = path or (ROOT / "data/entries.csv")
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_display_groups(path: Path | None = None) -> dict[str, str]:
    """Last line wins (matches build_register)."""
    path = path or (ROOT / "data/display-groups.csv")
    out = {}
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[r["id"]] = r["display_group"]
    return out


def sources_path(row_id: str) -> Path:
    return ROOT / "sources" / f"{row_id}.md"
