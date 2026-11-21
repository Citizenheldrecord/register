/* Satellite pages: what, coming-up, scored, register doorway. */
"use strict";
const C = window.CHR;

function headerTheme(btn) {
  let mode = C.initTheme();
  if (btn) {
    btn.textContent = C.themeLabel(mode);
    btn.onclick = () => {
      mode = C.cycleTheme(mode);
      btn.textContent = C.themeLabel(mode);
    };
  }
}

function sourceLink(r, annotations) {
  const a = annotations[r.id];
  if (a && a.primary_source_url) {
    return ' <a href="' + C.esc(a.primary_source_url) + '" target="_blank" rel="noopener">Source</a>.';
  }
  const m = (r.measure || "").match(/https?:\/\/[^\s]+/);
  if (m) {
    const u = m[0].replace(/[).,;]+$/, "");
    return ' <a href="' + C.esc(u) + '" target="_blank" rel="noopener">Source</a>.';
  }
  return "";
}

function layerOf(status) {
  const m = /blocking layer:\s*(.+)\)\s*$/i.exec(status || "");
  return m ? m[1] : "";
}

function testLine(r) {
  return r.test || "";
}

async function boot() {
  headerTheme(document.getElementById("theme-toggle"));
  const page = document.body.dataset.page;
  if (!page || page === "static") return;
  let data;
  try {
    data = await C.loadRegisterData();
  } catch (e) {
    const err = document.getElementById("load-error");
    if (err) { err.hidden = false; err.textContent = "The register data could not be loaded. " + e.message; }
    return;
  }
  const iso = C.todayISO();
  const counts = C.countStates(data.rows, iso);
  const byId = Object.fromEntries(data.rows.map(r => [r.id, r]));

  if (page === "what") {
    const n = (s) => Object.values(counts.state).filter(v => v === s).length;
    const waiting = n("Open") + n("Due");
    const el = document.getElementById("facts");
    if (el) {
      el.innerHTML = "As at " + C.longDate(iso) + " the register holds " + counts.promises +
        " promises. " + n("PASS") + " passed, " + n("FAILED") + " failed and " + waiting +
        " are waiting for their date. The full counts, with their definitions, are on " +
        '<a href="index.html">the register page</a>.';
    }
    const built = document.getElementById("built-line");
    if (built) {
      built.innerHTML = "Counted " + C.longDate(iso) + " from this copy of data/entries.csv (" +
        counts.total + " rows, sha256 <code>" + C.esc(data.hash) + "</code>). Display only: it changes no entry.";
    }
  }

  if (page === "register-door") {
    const built = document.getElementById("built-line");
    const files = document.getElementById("data-files");
    if (files) {
      files.innerHTML = '<ul class="list"><li><a href="data/entries.csv">data/entries.csv</a>: every entry, one row each. It only grows; nothing is deleted. This copy: ' +
        counts.total + ' rows, sha256 <code style="word-break:break-all">' + C.esc(data.hash) +
        '</code>.</li><li><a href="data/failure-log.csv">data/failure-log.csv</a>: each failure, with where it got stuck and what was chosen instead.</li></ul>';
    }
    if (built) {
      built.innerHTML = "Counted " + C.longDate(iso) + " from this copy of data/entries.csv (" +
        counts.total + " rows, sha256 <code>" + C.esc(data.hash) + "</code>). Display only: it changes no entry.";
    }
  }

  if (page === "coming-up") {
    const end = C.addDaysISO(iso, 30);
    const lead = document.getElementById("coming-lead");
    if (lead) {
      lead.innerHTML = "These are the promises due to be scored in the next 30 days, to " + C.longDate(end) +
        ", in date order. Each is checked on its date against the official source. This list shows promises by governments and the outside files the register watches; " +
        '<a href="index.html">the full table</a> lists every entry.';
    }
    const overdue = data.rows.filter(r => counts.state[r.id] === "Due")
      .sort((a,b) => (C.rowDateISO(a)||"").localeCompare(C.rowDateISO(b)||"") || a.id.localeCompare(b.id));
    const soon = C.dueSoonIds(data.rows, counts, iso, 30);
    const past = document.getElementById("past-due");
    if (past) {
      past.innerHTML = overdue.length ? listByDate(overdue, data, counts, false) : "<p>None.</p>";
    }
    const box = document.getElementById("next-30");
    if (box) {
      const h = document.getElementById("next-30-heading");
      if (h) h.textContent = "Next 30 days (" + soon.length + ")";
      box.innerHTML = soon.length ? listByDate(soon, data, counts, true) : "<p>None.</p>";
    }
    const built = document.getElementById("built-line");
    if (built) {
      built.innerHTML = "Counted " + C.longDate(iso) + " from this copy of data/entries.csv (" +
        counts.total + " rows, sha256 <code>" + C.esc(data.hash) + "</code>). Display only: it changes no entry.";
    }
  }

  if (page === "scored") {
    const passed = [], failed = [], recorded = [];
    const { closed } = C.closersOf(data.rows);
    // Prefer the scoring entry itself when present; else the promise if it carries a SCORED status.
    const scoredRows = data.rows.filter(r => /^SCORED/i.test(r.status || ""));
    const recent = scoredRows.slice().sort((a,b) => {
      const da = C.plainDateISO((a.status.match(/SCORED (\d{1,2} [A-Z][a-z]{2} \d{4})/)||[])[1] || "") || C.rowDateISO(a) || "";
      const db = C.plainDateISO((b.status.match(/SCORED (\d{1,2} [A-Z][a-z]{2} \d{4})/)||[])[1] || "") || C.rowDateISO(b) || "";
      return db.localeCompare(da) || b.id.localeCompare(a.id);
    });
    // Classify by the promise state if this row supersedes one, else by its own status.
    function kindOf(r) {
      const st = (r.status || "").toUpperCase();
      if (st.includes("FAIL")) return "fail";
      if (st.includes("PASS")) return "pass";
      return "recorded";
    }
    const top = recent.slice(0, 20);
    const nPass = top.filter(r => kindOf(r) === "pass").length;
    const nFail = top.filter(r => kindOf(r) === "fail").length;
    const lead = document.getElementById("scored-lead");
    if (lead) {
      lead.innerHTML = "The 20 most recent results, newest first: " + nPass + " passed and " + nFail +
        " failed. Each line is the test in the register's words, the result and the official source it was scored from.";
    }
    const box = document.getElementById("scored-list");
    if (box) {
      box.innerHTML = "<ul class=\"list\">" + top.map(r => {
        const k = kindOf(r);
        const tag = k === "pass" ? '<span class="pill pass"><i aria-hidden="true">OK</i> Passed</span>' :
                    k === "fail" ? '<span class="pill fail"><i aria-hidden="true">X</i> Failed</span>' :
                    '<span class="pill recorded"><i aria-hidden="true">-</i> Recorded</span>';
        const dateM = (r.status.match(/SCORED (\d{1,2} [A-Z][a-z]{2} \d{4})/)||[])[1] || r.scoring_date;
        const layer = layerOf(r.status);
        const promiseId = (r.supersedes_id || r.id);
        const watch = r.section === "WATCH" ? ", an outside file we watch" : "";
        const layerBit = layer ? " Where it stuck: " + C.esc(layer) + "." : "";
        return "<li>" + tag + " " + C.esc(dateM) + ": " + C.esc(testLine(byId[promiseId] || r)) +
          '<span class="meta"><a href="index.html#row-' + C.esc(encodeURIComponent(promiseId)) + '">' + C.esc(promiseId) +
          "</a>" + watch + "." + layerBit + sourceLink(r, data.annotations) + "</span></li>";
      }).join("") + "</ul>";
    }
    const foot = document.getElementById("scored-foot");
    if (foot) {
      const n = (s) => Object.values(counts.state).filter(v => v === s).length;
      foot.innerHTML = "Every result since the register began, " + n("PASS") + " passed and " + n("FAILED") +
        " failed in all, is on <a href=\"index.html\">the register page</a>. Failures are listed with where they got stuck in " +
        '<a href="data/failure-log.csv">the failure log</a>.';
    }
    const built = document.getElementById("built-line");
    if (built) {
      built.innerHTML = "Counted " + C.longDate(iso) + " from this copy of data/entries.csv (" +
        counts.total + " rows, sha256 <code>" + C.esc(data.hash) + "</code>). Display only: it changes no entry.";
    }
  }
}

function listByDate(rows, data, counts, includeSection) {
  const groups = new Map();
  for (const r of rows) {
    const d = C.rowDateISO(r) || "";
    if (!groups.has(d)) groups.set(d, []);
    groups.get(d).push(r);
  }
  const dates = [...groups.keys()].sort();
  let html = "";
  for (const d of dates) {
    html += '<p class="date">' + C.esc(C.longDate(d)) + '</p><ul class="list">';
    for (const r of groups.get(d)) {
      const watch = r.section === "WATCH" ? ", an outside file we watch" : "";
      html += "<li>" + C.esc(r.test) + '<span class="meta"><a href="index.html#row-' +
        C.esc(encodeURIComponent(r.id)) + '">' + C.esc(r.id) + "</a>" + watch +
        ". Owner: " + C.esc(r.owner) + ".</span></li>";
    }
    html += "</ul>";
  }
  return html;
}

boot().catch(e => {
  const err = document.getElementById("load-error");
  if (err) { err.hidden = false; err.textContent = String(e && e.message ? e.message : e); }
});
