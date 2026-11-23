/* Citizen Held Record - live register. Vanilla JS, no tracking, no external deps. */
"use strict";

const MONTHS3 = {Jan:1,Feb:2,Mar:3,Apr:4,May:5,Jun:6,Jul:7,Aug:8,Sep:9,Oct:10,Nov:11,Dec:12};
const MONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"];
const SECTION_NAMES = {
  CANADA: "Canadian files",
  DESK: "This desk's own commitments",
  WATCH: "Outside files we watch",
  RECORDED: "Recorded facts and checkpoints"
};
const GROUP_NAMES = {government_promise:"Government promises", also_watched:"Also watched", recorded:"Recorded"};
const SETBY_NAMES = {GOVERNMENT:"Set by government", DESK:"Set by desk", MIXED:"Set: mixed", UNCLEAR:"Set by: unclear"};
const STATE_ORDER = ["PASS","FAILED","Recorded","Open","Due","Replaced","Proposed","Repeating"];
const COLUMNS = ["section","sort_date","scoring_date","id","test","owner","date_source","status","measure","money","funding","argument","cost_to_date","supersedes_id","supersedes_hash","hype_score","means_score","cost_score","follows_id"];
const COL_LABELS = {
  section:"Section", sort_date:"Sort date", scoring_date:"Scoring date", id:"ID", test:"Test",
  owner:"Owner", date_source:"Date source", status:"Status", measure:"Measure", money:"Money",
  funding:"Funding", argument:"Essay / argument", cost_to_date:"Cost to date",
  supersedes_id:"Supersedes", supersedes_hash:"Supersedes hash", hype_score:"Hype",
  means_score:"Means", cost_score:"Cost", follows_id:"Follows"
};
const LATE_STATUS = /^SCORED \d{1,2} [A-Z][a-z]{2} \d{4}: DELIVERED LATE \(\d+ days? late\)$/;
const PLAIN_DATE = /^(\d{1,2}) ([A-Z][a-z]{2}) (\d{4})$/;
const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

function parseCSV(text) {
  const out = [];
  let row = [], field = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"') {
        if (text[i + 1] === '"') { field += '"'; i++; }
        else quoted = false;
      } else field += c;
    } else if (c === '"') quoted = true;
    else if (c === ",") { row.push(field); field = ""; }
    else if (c === "\n") { row.push(field); out.push(row); row = []; field = ""; }
    else if (c !== "\r") field += c;
  }
  if (field !== "" || row.length) { row.push(field); out.push(row); }
  if (out.length && out[out.length - 1].length === 1 && out[out.length - 1][0] === "") out.pop();
  return out;
}

function rowsFromCSV(text) {
  const grid = parseCSV(text);
  if (!grid.length) return [];
  const head = grid[0];
  return grid.slice(1).filter(r => r.length === head.length || r.some(c => c !== "")).map(r => {
    const o = {};
    head.forEach((h, i) => { o[h] = r[i] == null ? "" : r[i]; });
    return o;
  });
}

async function fetchText(path) {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error("Could not load " + path + " (" + res.status + ")");
  return res.text();
}

async function sha256Hex(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, "0")).join("");
}

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"
  }[c]));
}

function linkify(s) {
  const t = String(s == null ? "" : s);
  return esc(t).replace(/https?:\/\/[^\s<]+/g, u => {
    const trimmed = u.replace(/[).,;]+$/, "");
    return '<a href="' + trimmed + '" target="_blank" rel="noopener">' + trimmed + "</a>" + u.slice(trimmed.length);
  });
}

function todayISO() {
  try {
    return new Intl.DateTimeFormat("en-CA", { timeZone: "America/Winnipeg", year:"numeric", month:"2-digit", day:"2-digit" }).format(new Date());
  } catch (e) {
    const d = new Date();
    const z = (n) => String(n).padStart(2, "0");
    return d.getFullYear() + "-" + z(d.getMonth() + 1) + "-" + z(d.getDate());
  }
}

function addDaysISO(iso, days) {
  const m = ISO_DATE.exec(iso);
  if (!m) return iso;
  const dt = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3] + days));
  const z = (n) => String(n).padStart(2, "0");
  return dt.getUTCFullYear() + "-" + z(dt.getUTCMonth() + 1) + "-" + z(dt.getUTCDate());
}

function longDate(iso) {
  const m = ISO_DATE.exec(iso);
  if (!m) return iso;
  return parseInt(m[3], 10) + " " + MONTHS[+m[2] - 1] + " " + m[1];
}

function plainDateISO(s) {
  const m = PLAIN_DATE.exec((s || "").trim());
  if (!m) return null;
  const mon = MONTHS3[m[2]];
  if (!mon) return null;
  const z = (n) => String(n).padStart(2, "0");
  return m[3] + "-" + z(mon) + "-" + z(+m[1]);
}

function rowDateISO(r) {
  return plainDateISO(r.scoring_date) || (ISO_DATE.test((r.sort_date || "").trim()) ? r.sort_date.trim() : null);
}

function daysBetween(a, b) {
  const ma = ISO_DATE.exec(a), mb = ISO_DATE.exec(b);
  if (!ma || !mb) return 0;
  const da = Date.UTC(+ma[1], +ma[2] - 1, +ma[3]);
  const db = Date.UTC(+mb[1], +mb[2] - 1, +mb[3]);
  return Math.round((da - db) / 86400000);
}

function isLateRow(r) {
  return LATE_STATUS.test((r.status || "").trim());
}

function isBaseline(r) {
  const t = (r.test || "").replace(/^\s+/, "");
  return t.startsWith("RECORDED, not scored") || t.startsWith("RECORDED, not PASS/FAILED");
}

function countStates(rows, iso) {
  const scorers = {}, redated = {};
  for (const r of rows) {
    const sup = (r.supersedes_id || "").trim();
    if (sup) {
      if ((r.status || "").toUpperCase().startsWith("SCORED")) scorers[sup] = r;
      else redated[sup] = r;
    }
  }
  const scoringIds = new Set(Object.values(scorers).map(r => r.id));
  for (const r of rows) {
    if (isLateRow(r) && !(r.supersedes_id || "").trim()) scoringIds.add(r.id);
  }
  const state = {}, dueDays = {};
  for (const r of rows) {
    const rid = r.id, st = (r.status || "").trim().toUpperCase();
    if (scoringIds.has(rid)) continue;
    if (redated[rid]) { state[rid] = "Replaced"; continue; }
    const res = scorers[rid] ? scorers[rid].status.toUpperCase() : (st.startsWith("SCORED") ? st : null);
    if (res != null) {
      state[rid] = isBaseline(r) ? "Recorded" : (res.includes("PASS") ? "PASS" : (res.includes("FAIL") ? "FAILED" : "Recorded"));
      continue;
    }
    if (st === "PROPOSED") { state[rid] = "Proposed"; continue; }
    let d = plainDateISO(r.scoring_date);
    if (!d) {
      const sd = (r.sort_date || "").trim();
      if (!ISO_DATE.test(sd) || sd.startsWith("9999")) { state[rid] = "Repeating"; continue; }
      d = sd;
    }
    if (d < iso) { state[rid] = "Due"; dueDays[rid] = daysBetween(iso, d); }
    else state[rid] = "Open";
  }
  return { total: rows.length, promises: Object.keys(state).length, scoring_entries: scoringIds.size, state, due_days: dueDays, scoringIds, scorers, redated };
}

function closersOf(rows) {
  const closed = {}, replaced = {};
  for (const r of rows) {
    const sup = (r.supersedes_id || "").trim();
    if (!sup) continue;
    const s = (r.status || "").toUpperCase();
    if (/^(SCORED|PASS|FAILED)/.test(s)) closed[sup] = r.id;
    else replaced[sup] = r.id;
  }
  return { closed, replaced };
}

function displayStatus(r, closed, replaced) {
  if (closed[r.id]) return "CLOSED: scored in " + closed[r.id];
  if (replaced[r.id]) return "REPLACED by " + replaced[r.id] + "; this entry is kept";
  return r.status || "";
}

function pillInfo(r, counts, closed, replaced) {
  const st = counts.state[r.id];
  if (st === "PASS") return { kind: "pass", label: "PASS" };
  if (st === "FAILED") return { kind: "fail", label: "FAILED" };
  if (st === "Open") return { kind: "open", label: "Open" };
  if (st === "Due") return { kind: "due", label: "Due" };
  if (st === "Recorded") return { kind: "recorded", label: "Recorded" };
  if (st === "Proposed") return { kind: "proposed", label: "Proposed" };
  if (st === "Replaced") return { kind: "replaced", label: "Replaced" };
  if (st === "Repeating") return { kind: "repeating", label: "Repeating" };
  if (closed[r.id]) return { kind: "closed", label: "CLOSED" };
  const raw = (r.status || "").toUpperCase();
  if (raw.includes("FAIL")) return { kind: "fail", label: "FAILED" };
  if (raw.includes("PASS")) return { kind: "pass", label: "PASS" };
  if (raw.includes("RECORDED")) return { kind: "recorded", label: "Recorded" };
  if (raw.startsWith("SCORED")) return { kind: "scoring", label: "Scored" };
  if (raw === "LIVE") return { kind: "open", label: "LIVE" };
  if (raw === "PROPOSED") return { kind: "proposed", label: "Proposed" };
  return { kind: "recorded", label: r.status || "Status" };
}

function pillMark(kind) {
  if (kind === "pass") return "OK";
  if (kind === "fail") return "X";
  if (kind === "open") return "O";
  if (kind === "due") return "!";
  return "-";
}

function pillHTML(info) {
  return '<span class="pill ' + esc(info.kind) + '"><i aria-hidden="true">' + pillMark(info.kind) + "</i> " + esc(info.label) + "</span>";
}

function dueSoonIds(rows, counts, iso, days) {
  const end = addDaysISO(iso, days);
  const out = [];
  for (const r of rows) {
    if (counts.state[r.id] !== "Open") continue;
    const d = rowDateISO(r);
    if (!d) continue;
    if (d >= iso && d <= end) out.push(r);
  }
  out.sort((a, b) => (rowDateISO(a) || "").localeCompare(rowDateISO(b) || "") || a.id.localeCompare(b.id));
  return out;
}

function latestChecked(text) {
  const lines = (text || "").split(/\r?\n/).map(s => s.trim()).filter(Boolean);
  return lines.length ? lines[lines.length - 1] : "";
}

function applyTheme(mode) {
  const root = document.documentElement;
  if (mode === "dark") root.setAttribute("data-theme", "dark");
  else if (mode === "light") root.setAttribute("data-theme", "light");
  else {
    const prefers = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    root.setAttribute("data-theme", prefers ? "dark" : "light");
  }
  try { localStorage.setItem("chr-theme", mode); } catch (e) {}
}

function initTheme() {
  let mode = "auto";
  try { mode = localStorage.getItem("chr-theme") || "auto"; } catch (e) {}
  applyTheme(mode);
  return mode;
}

function themeLabel(mode) {
  if (mode === "dark") return "Theme: dark";
  if (mode === "light") return "Theme: light";
  return "Theme: auto";
}

function cycleTheme(current) {
  const next = current === "light" ? "dark" : current === "dark" ? "auto" : "light";
  applyTheme(next);
  return next;
}

async function loadRegisterData() {
  const [entriesText, essaysText, annText, groupsText, notesText, failText, checkedText, methodText, essaysIndexText] = await Promise.all([
    fetchText("data/entries.csv"),
    fetchText("data/essay-links.csv"),
    fetchText("data/row-annotations.csv"),
    fetchText("data/display-groups.csv"),
    fetchText("data/display-notes.csv"),
    fetchText("data/failure-log.csv"),
    fetchText("data/last-checked.txt"),
    fetchText("data/row-method.csv").catch(() => ""),
    fetchText("data/essays-index.json").catch(() => "")
  ]);
  const rows = rowsFromCSV(entriesText);
  const essays = {};
  for (const e of rowsFromCSV(essaysText)) {
    if (!e.id) continue;
    (essays[e.id] || (essays[e.id] = [])).push({ t: e.essay_title, u: e.essay_url, d: e.essay_live_date });
  }
  const annotations = {};
  for (const a of rowsFromCSV(annText)) annotations[a.id] = a;
  const groups = {};
  for (const g of rowsFromCSV(groupsText)) groups[g.id] = g;
  const methods = {};
  if (methodText) {
    for (const m of rowsFromCSV(methodText)) methods[m.id] = m;
  }
  let essaysIndex = [];
  if (essaysIndexText) {
    try {
      const parsed = JSON.parse(essaysIndexText);
      essaysIndex = parsed.essays || [];
    } catch (e) {
      essaysIndex = [];
    }
  }
  return {
    entriesText, rows, essays, annotations, groups,
    notes: rowsFromCSV(notesText),
    failures: rowsFromCSV(failText),
    lastChecked: latestChecked(checkedText),
    lastCheckedAll: checkedText,
    methods,
    essaysIndex,
    hash: await sha256Hex(entriesText)
  };
}

window.CHR = {
  parseCSV, rowsFromCSV, fetchText, sha256Hex, esc, linkify, todayISO, addDaysISO, longDate,
  plainDateISO, rowDateISO, daysBetween, countStates, closersOf, displayStatus, pillInfo, pillHTML,
  dueSoonIds, applyTheme, initTheme, themeLabel, cycleTheme, loadRegisterData,
  SECTION_NAMES, GROUP_NAMES, SETBY_NAMES, STATE_ORDER, COLUMNS, COL_LABELS
};
