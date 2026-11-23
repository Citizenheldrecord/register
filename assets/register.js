/* Main register page for the live register. */
"use strict";
const C = window.CHR;
let DATA = null;
let COUNTS = null;
let CLOSED = null;
let REPLACED = null;
let ISO = null;
let FILTER = { q: "", status: "", owner: "", section: "", setby: "", from: "", to: "", sort: "date-asc", card: "" };
let themeMode = "auto";

const $ = (id) => document.getElementById(id);

function ownerOf(r) { return r.owner || ""; }

function sectionLabel(r) {
  const g = DATA.groups[r.id];
  const sec = C.SECTION_NAMES[r.section] || r.section;
  if (g && C.GROUP_NAMES[g.display_group]) return C.GROUP_NAMES[g.display_group] + " (" + sec + ")";
  return sec;
}

function essayHTML(r) {
  const list = DATA.essays[r.id];
  if (list && list.length) {
    return list.map(x => '<a href="' + C.esc(x.u) + '" target="_blank" rel="noopener">' + C.esc(x.t) + "</a> (" + C.esc(x.d) + ")").join("; ");
  }
  const m = /^\[publishes (.+)\]$/.exec(r.argument || "");
  if (m) return "Essay not yet published (the entry reads: publishes " + C.esc(m[1]) + "). Link added when it is.";
  return C.linkify(r.argument || "");
}

function matches(r) {
  if (FILTER.card === "promises" && COUNTS.state[r.id] == null) return false;
  if (FILTER.card === "open" && COUNTS.state[r.id] !== "Open") return false;
  if (FILTER.card === "pass" && COUNTS.state[r.id] !== "PASS") return false;
  if (FILTER.card === "fail" && COUNTS.state[r.id] !== "FAILED") return false;
  if (FILTER.card === "recorded" && COUNTS.state[r.id] !== "Recorded") return false;
  if (FILTER.card === "due30") {
    const soon = dueSoonSet();
    if (!soon.has(r.id)) return false;
  }
  if (FILTER.status) {
    if (FILTER.status === "scoring" && COUNTS.state[r.id] != null) return false;
    if (FILTER.status !== "scoring" && COUNTS.state[r.id] !== FILTER.status) return false;
  }
  if (FILTER.owner && ownerOf(r) !== FILTER.owner) return false;
  if (FILTER.section) {
    const g = DATA.groups[r.id];
    const key = (g && g.display_group) || r.section;
    if (key !== FILTER.section && r.section !== FILTER.section) return false;
  }
  if (FILTER.setby) {
    const a = DATA.annotations[r.id];
    if (!a || a.test_set_by !== FILTER.setby) return false;
  }
  if (FILTER.from || FILTER.to) {
    const d = C.rowDateISO(r);
    if (!d) return false;
    if (FILTER.from && d < FILTER.from) return false;
    if (FILTER.to && d > FILTER.to) return false;
  }
  if (FILTER.q) {
    const q = FILTER.q;
    const ann = DATA.annotations[r.id];
    const hay = C.COLUMNS.map(h => r[h] || "").join("\n").toLowerCase()
      + " " + sectionLabel(r).toLowerCase()
      + (ann ? " " + (ann.summary || "") + " " + (ann.primary_source_url || "") : "")
      + " " + (DATA.essays[r.id] || []).map(e => e.t + " " + e.u).join(" ").toLowerCase();
    if (!hay.includes(q)) return false;
  }
  return true;
}

function dueSoonSet() {
  return new Set(C.dueSoonIds(DATA.rows, COUNTS, ISO, 30).map(r => r.id));
}

function shownRows() {
  const out = DATA.rows.filter(matches);
  const key = FILTER.sort;
  out.sort((a, b) => {
    if (key === "date-asc") return (C.rowDateISO(a) || "9999") .localeCompare(C.rowDateISO(b) || "9999") || a.id.localeCompare(b.id);
    if (key === "date-desc") return (C.rowDateISO(b) || "").localeCompare(C.rowDateISO(a) || "") || a.id.localeCompare(b.id);
    if (key === "id") return a.id.localeCompare(b.id);
    if (key === "owner") return ownerOf(a).localeCompare(ownerOf(b)) || a.id.localeCompare(b.id);
    if (key === "status") {
      const sa = (COUNTS.state[a.id] || displayLabel(a));
      const sb = (COUNTS.state[b.id] || displayLabel(b));
      return sa.localeCompare(sb) || a.id.localeCompare(b.id);
    }
    if (key === "section") return sectionLabel(a).localeCompare(sectionLabel(b)) || a.id.localeCompare(b.id);
    return 0;
  });
  return out;
}

function displayLabel(r) { return C.displayStatus(r, CLOSED, REPLACED); }

function testPreview(t, n) {
  t = t || "";
  if (t.length <= n) return t;
  return t.slice(0, n).replace(/\s+\S*$/, "") + "...";
}

function renderCards() {
  const n = (s) => Object.values(COUNTS.state).filter(v => v === s).length;
  const due30 = C.dueSoonIds(DATA.rows, COUNTS, ISO, 30).length;
  const map = [
    ["promises", "total", COUNTS.promises, "Total promises", COUNTS.total + " entries in all"],
    ["open", "open", n("Open"), "Open", "Waiting for their date"],
    ["pass", "pass", n("PASS"), "Passed", "Test met on the date"],
    ["fail", "fail", n("FAILED"), "Failed", "Test not met on the date"],
    ["recorded", "recorded", n("Recorded"), "Recorded", "Fact, no pass or fail line"],
    ["due30", "due", due30, "Due in the next 30 days", "Through " + C.longDate(C.addDaysISO(ISO, 30))]
  ];
  const box = $("summary-cards");
  box.innerHTML = map.map(([id, kind, val, label, hint]) =>
    '<button type="button" class="stat ' + kind + '" data-card="' + id + '" aria-pressed="' + (FILTER.card === id) + '">' +
    '<span class="lbl">' + C.esc(label) + "</span>" +
    '<span class="n">' + val + "</span>" +
    '<span class="hint">' + C.esc(hint) + "</span></button>"
  ).join("");
  box.querySelectorAll(".stat").forEach(btn => {
    btn.addEventListener("click", () => {
      FILTER.card = FILTER.card === btn.dataset.card ? "" : btn.dataset.card;
      renderAll();
      if (FILTER.card) {
        const el = document.getElementById("tools") || document.getElementById("entries");
        if (el) el.scrollIntoView({ block: "start", behavior: "instant" });
      }
    });
  });
}

function renderTally() {
  const st = COUNTS.state;
  const bySet = {GOVERNMENT:{}, DESK:{}, MIXED:{}, UNCLEAR:{}};
  const blank = () => Object.fromEntries(C.STATE_ORDER.map(s => [s, 0]).concat([["promises", 0]]));
  for (const k of Object.keys(bySet)) bySet[k] = blank();
  let primary = 0, flagged = 0;
  for (const r of DATA.rows) {
    const a = DATA.annotations[r.id];
    if (a && a.source_flag === "primary" && a.primary_source_url) primary++;
    else flagged++;
    const s = st[r.id];
    if (!s) continue;
    const by = (a && a.test_set_by) || "UNCLEAR";
    const bucket = bySet[by] || bySet.UNCLEAR;
    bucket.promises++;
    bucket[s]++;
  }
  const head = ["Who set the test date", "Promises"].concat(C.STATE_ORDER);
  const rows = ["GOVERNMENT","DESK","MIXED","UNCLEAR"].map(k => {
    const label = {GOVERNMENT:"Government-set", DESK:"Desk-set", MIXED:"Mixed", UNCLEAR:"Unclear"}[k];
    const b = bySet[k];
    return [label, b.promises].concat(C.STATE_ORDER.map(s => b[s]));
  });
  const all = [COUNTS.promises].concat(C.STATE_ORDER.map(s => Object.values(st).filter(v => v === s).length));
  const tbl = "<thead><tr>" + head.map(h => "<th>" + C.esc(h) + "</th>").join("") + "</tr></thead><tbody>" +
    rows.map(r => "<tr>" + r.map(c => "<td>" + c + "</td>").join("") + "</tr>").join("") +
    "<tr>" + ["<td><b>All promises</b></td>"].concat(all.map(c => "<td><b>" + c + "</b></td>")).join("") + "</tr></tbody>";
  $("tally-table").innerHTML = tbl;
  const n = (s) => Object.values(st).filter(v => v === s).length;
  $("tally-lead").innerHTML = COUNTS.total + " entries = " + COUNTS.promises + " promises + " + COUNTS.scoring_entries +
    " scoring entries. Of the " + COUNTS.promises + " promises: PASS " + n("PASS") + ", FAILED " + n("FAILED") +
    ", Recorded " + n("Recorded") + ", Open " + n("Open") + ", Due " + n("Due") + ", Replaced " + n("Replaced") +
    ", Proposed " + n("Proposed") + ", Repeating " + n("Repeating") + ".";
  const setCounts = {GOVERNMENT:0,DESK:0,MIXED:0,UNCLEAR:0};
  for (const r of DATA.rows) {
    const a = DATA.annotations[r.id];
    setCounts[(a && a.test_set_by) || "UNCLEAR"]++;
  }
  $("tally-foot").innerHTML = "All " + COUNTS.total + " rows by who set the test: government " + setCounts.GOVERNMENT +
    ", desk " + setCounts.DESK + ", mixed " + setCounts.MIXED + ", unclear " + setCounts.UNCLEAR +
    ". Rows with a primary source link: " + primary + "; flagged with no primary link: " + flagged +
    '. Per-row detail is in <a href="data/row-annotations.csv">data/row-annotations.csv</a>, a display layer; the fingerprinted entries are not changed.';
  $("tally-heading").textContent = "The tally, counted from data/entries.csv on " + C.longDate(ISO);
}

function renderTimeline() {
  const overdue = DATA.rows.filter(r => COUNTS.state[r.id] === "Due")
    .sort((a,b) => (C.rowDateISO(a)||"").localeCompare(C.rowDateISO(b)||"") || a.id.localeCompare(b.id));
  const soon = C.dueSoonIds(DATA.rows, COUNTS, ISO, 30);
  const items = overdue.concat(soon).slice(0, 6);
  const html = items.length ? "<ol>" + items.map(r => {
    const d = C.rowDateISO(r);
    const overdueFlag = COUNTS.state[r.id] === "Due";
    const days = overdueFlag ? COUNTS.due_days[r.id] : C.daysBetween(d, ISO);
    const when = overdueFlag ? (C.longDate(d) + " (" + days + " day" + (days===1?"":"s") + " past)") : C.longDate(d);
    return '<li class="' + (overdueFlag ? "overdue" : "") + '"><div class="when">' + C.esc(when) +
      '</div><div><a href="#row-' + C.esc(encodeURIComponent(r.id)) + '">' + C.esc(r.id) + "</a> · " +
      C.esc(ownerOf(r)) + "<div class=\"small\">" + C.esc(testPreview(r.test, 180)) + "</div></div></li>";
  }).join("") + "</ol>" : '<p class="empty">No open tests fall in the next 30 days, and none is past its date.</p>';
  $("timeline-list").innerHTML = html;
  $("timeline-lead").textContent = "Open tests due to be scored in the next 30 days, through " + C.longDate(C.addDaysISO(ISO, 30)) +
    (overdue.length ? ", and " + overdue.length + " past their date." : ". None is past its date.");
}

function renderFilters() {
  const owners = [...new Set(DATA.rows.map(ownerOf))].sort((a,b) => a.localeCompare(b));
  const ownerSel = $("f-owner");
  const cur = FILTER.owner;
  ownerSel.innerHTML = '<option value="">All owners</option>' + owners.map(o => '<option value="' + C.esc(o) + '">' + C.esc(o) + "</option>").join("");
  ownerSel.value = cur;
}

function rowTR(r) {
  const info = C.pillInfo(r, COUNTS, CLOSED, REPLACED);
  return '<tr tabindex="0" data-id="' + C.esc(r.id) + '" id="row-' + C.esc(r.id) + '">' +
    '<td class="col-id">' + C.esc(r.id) + "</td>" +
    '<td class="col-test">' + C.esc(testPreview(r.test, 200)) + "</td>" +
    "<td>" + C.pillHTML(info) + "</td>" +
    '<td class="col-owner">' + C.esc(ownerOf(r)) + "</td>" +
    '<td class="col-date">' + C.esc(r.scoring_date) + "</td>" +
    "<td>" + C.esc(sectionLabel(r)) + "</td></tr>";
}

function rowCard(r) {
  const info = C.pillInfo(r, COUNTS, CLOSED, REPLACED);
  return '<article class="row-card" tabindex="0" data-id="' + C.esc(r.id) + '" id="card-' + C.esc(r.id) + '">' +
    "<header><span class=\"rid\">" + C.esc(r.id) + "</span>" + C.pillHTML(info) + "</header>" +
    '<p class="test">' + C.esc(testPreview(r.test, 240)) + "</p>" +
    '<div class="foot">' + C.esc(ownerOf(r)) + " · " + C.esc(r.scoring_date) + "</div></article>";
}

function essayHay(e) {
  return ((e.title || "") + " " + (e.date || "") + " " + (e.url || "") + " " + (e.words || e.text || "")).toLowerCase();
}

function matchingEssays() {
  const q = FILTER.q;
  const list = DATA.essaysIndex || [];
  if (!q) return [];
  const hits = list.filter(e => essayHay(e).includes(q));
  hits.sort((a, b) => (b.iso || "").localeCompare(a.iso || "") || (a.title || "").localeCompare(b.title || ""));
  return hits;
}

function renderEssayResults() {
  const box = $("essay-results");
  if (!box) return;
  const q = FILTER.q;
  if (!q) {
    box.hidden = true;
    return;
  }
  const hits = matchingEssays();
  box.hidden = false;
  const count = $("essay-results-count");
  const list = $("essay-results-list");
  if (count) {
    count.textContent = hits.length
      ? (hits.length === 1 ? "1 published essay matches." : hits.length + " published essays match.")
      : "No published essays match.";
  }
  if (list) {
    list.innerHTML = hits.map(e => {
      const title = C.esc(e.title || e.url || "Untitled");
      const href = C.esc(e.url || "");
      const date = e.date ? ' <span class="essay-date">(' + C.esc(e.date) + ")</span>" : "";
      return '<li><a href="' + href + '" target="_blank" rel="noopener">' + title + "</a>" + date + "</li>";
    }).join("");
  }
}

function renderList() {
  const shown = shownRows();
  renderEssayResults();
  $("count").textContent = "Showing " + shown.length + " of " + DATA.rows.length;
  $("rows").innerHTML = shown.length ? shown.map(rowTR).join("") : '<tr><td colspan="6" class="empty">No entries match.</td></tr>';
  $("cards-list").innerHTML = shown.length ? shown.map(rowCard).join("") : '<p class="empty">No entries match.</p>';
  const open = (ev) => {
    const el = ev.target.closest("[data-id]");
    if (!el) return;
    if (ev.target.closest("a")) return;
    openDetail(el.dataset.id, true);
  };
  $("rows").onclick = open;
  $("rows").onkeydown = (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); open(ev); } };
  $("cards-list").onclick = open;
  $("cards-list").onkeydown = (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); open(ev); } };
}

function field(name, html) {
  return "<div><div class=\"field-name\">" + C.esc(name) + "</div><div>" + (html || '<span class="muted">none</span>') + "</div></div>";
}

function openDetail(id, push) {
  const r = DATA.rows.find(x => x.id === id);
  if (!r) return;
  if (push) {
    history.replaceState(null, "", "#row-" + encodeURIComponent(id));
  }
  document.querySelectorAll(".results tbody tr.active, .row-card.active").forEach(el => el.classList.remove("active"));
  const tr = document.getElementById("row-" + id);
  const card = document.getElementById("card-" + id);
  if (tr) tr.classList.add("active");
  if (card) card.classList.add("active");
  const info = C.pillInfo(r, COUNTS, CLOSED, REPLACED);
  const a = DATA.annotations[r.id];
  const g = DATA.groups[r.id];
  const meth = DATA.methods[r.id];
  const parts = [];
  parts.push(field("Status", C.pillHTML(info) + " <span class=\"small\">" + C.esc(displayLabel(r)) + "</span>"));
  parts.push(field("Test", C.linkify(r.test)));
  if (a && a.summary) parts.push(field("In plain words", C.esc(a.summary)));
  parts.push(field("Owner", C.esc(r.owner)));
  parts.push(field("Scoring date", C.esc(r.scoring_date) + (r.sort_date ? ' <span class="small">(' + C.esc(r.sort_date) + ")</span>" : "")));
  parts.push(field("Date source", C.linkify(r.date_source)));
  if (a) {
    parts.push(field("Test set by", C.esc(C.SETBY_NAMES[a.test_set_by] || a.test_set_by) + (a.test_set_date && a.test_set_date !== "UNCLEAR" ? " · " + C.esc(a.test_set_date) : "") + (a.test_set_basis ? " · " + C.esc(a.test_set_basis) : "")));
    if (a.primary_source_url) parts.push(field("Primary source", '<a href="' + C.esc(a.primary_source_url) + '" target="_blank" rel="noopener">' + C.esc(a.primary_source_url) + "</a>"));
    if (a.source_flag) parts.push(field("Source flag", C.esc(a.source_flag)));
  }
  parts.push(field("Section", C.esc(sectionLabel(r))));
  if (g && g.reason) parts.push(field("Display group reason", C.esc(g.reason)));
  parts.push(field("Measure", C.linkify(r.measure || "")));
  parts.push(field("Money", C.linkify(r.money || "")));
  parts.push(field("Funding", C.esc(r.funding || "")));
  parts.push(field("Essay / argument", essayHTML(r)));
  parts.push(field("Cost to date", C.linkify(r.cost_to_date || "OPEN")));
  parts.push(field("Hype", C.esc(r.hype_score || "OPEN")));
  parts.push(field("Means", C.esc(r.means_score || "OPEN")));
  parts.push(field("Cost score", C.esc(r.cost_score || "OPEN")));
  if (r.supersedes_id) parts.push(field("Supersedes", '<a href="#row-' + C.esc(encodeURIComponent(r.supersedes_id)) + '">' + C.esc(r.supersedes_id) + "</a>"));
  if (r.supersedes_hash) parts.push(field("Supersedes hash", '<span class="mono">' + C.esc(r.supersedes_hash) + "</span>"));
  if (r.follows_id) parts.push(field("Follows", '<a href="#row-' + C.esc(encodeURIComponent(r.follows_id)) + '">' + C.esc(r.follows_id) + "</a>"));
  if (CLOSED[r.id]) parts.push(field("Scored in", '<a href="#row-' + C.esc(encodeURIComponent(CLOSED[r.id])) + '">' + C.esc(CLOSED[r.id]) + "</a>"));
  if (REPLACED[r.id]) parts.push(field("Replaced by", '<a href="#row-' + C.esc(encodeURIComponent(REPLACED[r.id])) + '">' + C.esc(REPLACED[r.id]) + "</a>"));
  if (meth) {
    if (meth.entry_reason) parts.push(field("Entry reason", C.esc(meth.entry_reason)));
    if (meth.date_basis) parts.push(field("Date basis", C.esc(meth.date_basis) + (meth.date_basis_reason ? " · " + C.esc(meth.date_basis_reason) : "")));
    if (meth.source) parts.push(field("Method source", C.linkify(meth.source)));
    if (meth.note_date) parts.push(field("Method note date", C.esc(meth.note_date)));
  }
  parts.push(field("Permalink", '<a class="permalink" href="#row-' + C.esc(encodeURIComponent(r.id)) + '">#row-' + C.esc(r.id) + "</a>"));

  $("drawer-title").textContent = r.id;
  $("drawer-body").innerHTML = '<div class="field-list">' + parts.join("") + "</div>";
  const root = $("drawer-root");
  root.hidden = false;
  document.body.classList.add("drawer-open");
  $("drawer-close").focus();
  document.body.style.overflow = "hidden";
}

function closeDetail(clearHash) {
  $("drawer-root").hidden = true;
  document.body.classList.remove("drawer-open");
  document.body.style.overflow = "";
  if (clearHash && location.hash) history.replaceState(null, "", location.pathname + location.search);
}

function renderStand() {
  const ids = (s) => Object.entries(COUNTS.state).filter(([,v]) => v === s).map(([i]) => i).sort();
  const n = (s) => ids(s).length;
  const dueParts = Object.entries(COUNTS.due_days).sort((a,b) => b[1]-a[1] || a[0].localeCompare(b[0]))
    .map(([id, k]) => id + ", " + k + " day" + (k===1?"":"s") + " past its date");
  const over = Object.entries(COUNTS.due_days).filter(([,k]) => k > 14);
  const line = (label, s, extra) => {
    const list = ids(s);
    return "<li><strong>" + label + "</strong> " + list.length + (list.length ? " (" + list.map(id => '<a href="#row-' + C.esc(encodeURIComponent(id)) + '">' + C.esc(id) + "</a>").join(", ") + ")" : "") + (extra || ".") + "</li>";
  };
  let html = "<p>Counted on " + C.longDate(ISO) + " from data/entries.csv, which holds " + COUNTS.total + " entries.</p>";
  html += "<p>Definitions used for every count on this page. A promise is an entry that sets a test. A scoring entry records a result against an earlier promise. Open: live, not scored, scoring date on or after the count date. Due: live, not scored, scoring date before the count date.</p><ul>";
  html += "<li><strong>Entries:</strong> " + COUNTS.total + " = " + COUNTS.promises + " promises + " + COUNTS.scoring_entries + " scoring entries.</li>";
  html += line("Scored PASS:", "PASS");
  html += line("Scored FAILED:", "FAILED");
  html += line("Recorded as fact, with no pass or fail line:", "Recorded");
  html += "<li><strong>Open:</strong> " + n("Open") + ".</li>";
  html += "<li><strong>Due:</strong> " + n("Due") + (dueParts.length ? " (" + dueParts.join("; ") + ")." : ".") + "</li>";
  html += "<li><strong>More than 14 days past due:</strong> " + over.length + ". " + (over.length ? "No new promises are added until these are scored." : "New promises can be added.") + "</li>";
  html += line("Replaced by a later entry (a new date or a correction):", "Replaced", " The old entry stays in the record; its newer entry is counted above.");
  html += line("Proposed, not yet live:", "Proposed");
  html += line("Repeating, with no single scoring day:", "Repeating");
  html += "</ul>";
  const check = C.STATE_ORDER.map(s => n(s) + " " + (s === "PASS" || s === "FAILED" ? s : s.toLowerCase())).join(" + ");
  html += "<p>Check: " + COUNTS.promises + " promises = " + check + ".</p>";
  html += "<p>By section of the data file (every entry counted once; the four sections add up to all " + COUNTS.total + " entries):</p>";
  html += '<div class="tally-wrap"><table class="tally"><thead><tr><th>Section</th><th>Entries</th><th>Scoring entries</th><th>Promises</th>' +
    C.STATE_ORDER.map(s => "<th>" + s + "</th>").join("") + "</tr></thead><tbody>";
  const secs = ["CANADA","DESK","WATCH","RECORDED"];
  const tot = Array(C.STATE_ORDER.length + 3).fill(0);
  for (const s of secs) {
    const rs = DATA.rows.filter(r => r.section === s);
    const pr = rs.filter(r => COUNTS.state[r.id] != null);
    const vals = [rs.length, rs.length - pr.length, pr.length].concat(C.STATE_ORDER.map(k => pr.filter(r => COUNTS.state[r.id] === k).length));
    vals.forEach((v,i) => tot[i]+=v);
    html += "<tr><td>" + C.esc(C.SECTION_NAMES[s]) + "</td>" + vals.map(v => "<td>" + v + "</td>").join("") + "</tr>";
  }
  html += "<tr>" + ["<td><b>Total</b></td>"].concat(tot.map(v => "<td><b>" + v + "</b></td>")).join("") + "</tr></tbody></table></div>";
  $("stand-body").innerHTML = html;
}

function renderEssays() {
  const by = new Map();
  for (const r of DATA.rows) {
    for (const e of (DATA.essays[r.id] || [])) {
      const key = e.u + "\t" + e.t + "\t" + e.d;
      if (!by.has(key)) by.set(key, { t: e.t, u: e.u, d: e.d, ids: [] });
      by.get(key).ids.push(r.id);
    }
  }
  const items = [...by.values()].sort((a,b) => {
    const da = C.plainDateISO(a.d) || "";
    const db = C.plainDateISO(b.d) || "";
    return db.localeCompare(da) || a.t.localeCompare(b.t);
  });
  $("essays-body").innerHTML = "<p>Each published essay and the rows it set. Rows whose essay is not yet published read OPEN or show the planned date in the essay column.</p><ul>" +
    items.map(e => "<li><a href=\"" + C.esc(e.u) + "\" target=\"_blank\" rel=\"noopener\">" + C.esc(e.t) + "</a> (" + C.esc(e.d) + "): " +
      e.ids.map(id => '<a href="#row-' + C.esc(encodeURIComponent(id)) + '">' + C.esc(id) + "</a>").join(", ") + "</li>").join("") + "</ul>";
}

function renderNotes() {
  const overlaps = DATA.notes.filter(n => n.kind === "possible_overlap");
  const related = DATA.notes.filter(n => n.kind !== "possible_overlap");
  const block = (arr) => arr.length ? "<ul>" + arr.map(n => {
    const ids = (n.ids || "").split(";").map(s => s.trim()).filter(Boolean);
    return "<li><strong>" + ids.map(id => '<a href="#row-' + C.esc(encodeURIComponent(id)) + '">' + C.esc(id) + "</a>").join(" and ") +
      "</strong> (noted " + C.esc(n.noted) + (n.status ? "; " + C.esc(n.status) : "") + "): " + C.esc(n.text) + "</li>";
  }).join("") + "</ul>" : '<p class="empty">None recorded in data/display-notes.csv.</p>';
  const ovb = $("overlaps-body");
  if (ovb) ovb.innerHTML = block(overlaps);
  const relb = $("related-body");
  if (relb) relb.innerHTML = block(related);
}

function renderFailLog() {
  const flb = $("faillog-body");
  if (!flb) return;
  if (!DATA.failures.length) { flb.innerHTML = '<p class="empty">No rows in data/failure-log.csv.</p>'; return; }
  const cols = Object.keys(DATA.failures[0]);
  const labels = {id:"ID", original_deadline:"Original deadline", date_failed:"Date failed", test:"Test", layer:"Layer", cost:"Cost", chosen_instead:"Chosen instead"};
  let html = '<div class="audit-table"><table class="plain"><thead><tr>' + cols.map(c => "<th>" + C.esc(labels[c] || c) + "</th>").join("") + "</tr></thead><tbody>";
  html += DATA.failures.map(r => "<tr>" + cols.map(c => {
    const v = r[c] || "";
    if (c === "id") return '<td><a href="#row-' + C.esc(encodeURIComponent(v)) + '">' + C.esc(v) + "</a></td>";
    return "<td>" + C.linkify(v) + "</td>";
  }).join("") + "</tr>").join("");
  html += "</tbody></table></div>";
  flb.innerHTML = html;
}

function renderMeta() {
  $("row-total").textContent = DATA.rows.length;
  $("printed").textContent = DATA.hash;
  $("last-checked-line").textContent = DATA.lastChecked || "Last checked: not found in data/last-checked.txt.";
  $("verify").textContent = "Checked in this browser: the SHA-256 of the loaded data/entries.csv is shown above.";
  const copies = $("copies-line");
  if (copies) copies.innerHTML = 'Copies of this record: the live site on <a href="https://github.com/Citizenheldrecord/register">GitHub</a> and the Codeberg mirror, <a href="https://codeberg.org/citizen-held-record/register">https://codeberg.org/citizen-held-record/register</a> (manual copy; the desk refreshes it after each push and checks the checksum). This page is a live register and is not those sites.';
  const hist = document.getElementById("checked-history");
  if (hist) hist.textContent = (DATA.lastCheckedAll || "").trim();
}

function renderAll() {
  renderCards();
  renderTally();
  renderTimeline();
  renderList();
  renderStand();
}

function readFilters() {
  FILTER.q = ($("q").value || "").trim().toLowerCase();
  FILTER.status = $("f-status").value;
  FILTER.owner = $("f-owner").value;
  FILTER.section = $("f-section").value;
  FILTER.setby = $("f-setby").value;
  FILTER.from = $("f-from").value;
  FILTER.to = $("f-to").value;
  FILTER.sort = $("f-sort").value;
}

function bind() {
  ["q","f-status","f-owner","f-section","f-setby","f-from","f-to","f-sort"].forEach(id => {
    $(id).addEventListener(id === "q" ? "input" : "change", () => { readFilters(); renderList(); });
  });
  $("reset").onclick = () => {
    ["q","f-status","f-owner","f-section","f-setby","f-from","f-to"].forEach(id => $(id).value = "");
    $("f-sort").value = "date-asc";
    FILTER = { q:"", status:"", owner:"", section:"", setby:"", from:"", to:"", sort:"date-asc", card:"" };
    renderAll();
  };
  $("dlcsv").onclick = () => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([DATA.entriesText], {type:"text/csv;charset=utf-8"}));
    a.download = "entries.csv";
    document.body.appendChild(a); a.click(); a.remove();
  };
  $("dljson").onclick = () => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([JSON.stringify(DATA.rows, null, 1)], {type:"application/json"}));
    a.download = "entries.json";
    document.body.appendChild(a); a.click(); a.remove();
  };
  $("drawer-close").onclick = () => closeDetail(true);
  $("drawer-backdrop").onclick = () => closeDetail(true);
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && !$("drawer-root").hidden) closeDetail(true);
  });
  window.addEventListener("hashchange", () => openFromHash());
  $("theme-toggle").onclick = () => {
    themeMode = C.cycleTheme(themeMode);
    $("theme-toggle").textContent = C.themeLabel(themeMode);
  };
}

function openFromHash() {
  const raw = decodeURIComponent((location.hash || "").replace(/^#/, ""));
  if (!raw) { if (!$("drawer-root").hidden) closeDetail(false); return; }
  const id = raw.startsWith("row-") ? raw.slice(4) : raw;
  if (DATA.rows.some(r => r.id === id)) openDetail(id, false);
}

async function main() {
  themeMode = C.initTheme();
  $("theme-toggle").textContent = C.themeLabel(themeMode);
  try {
    DATA = await C.loadRegisterData();
  } catch (e) {
    $("load-error").hidden = false;
    $("load-error").textContent = "The register data could not be loaded. " + e.message + " Serve this folder over HTTP (for example python3 -m http.server) so the browser can read data/entries.csv.";
    return;
  }
  ISO = C.todayISO();
  COUNTS = C.countStates(DATA.rows, ISO);
  const maps = C.closersOf(DATA.rows);
  CLOSED = maps.closed;
  REPLACED = maps.replaced;
  $("page-count").textContent = String(DATA.rows.length);
  renderFilters();
  bind();
  renderAll();
  renderEssays();
  renderNotes();
  renderFailLog();
  renderMeta();
  $("loaded-ok").hidden = false;
  openFromHash();
}

main().catch(err => {
  const el = $("load-error");
  if (el) { el.hidden = false; el.textContent = String(err && err.message ? err.message : err); }
});
