/* Kosmokrator local browser with a bounded monster editor. All untrusted text is inserted with textContent / DOM nodes only. */
"use strict";

(() => {
  const $ = (sel, root = document) => root.querySelector(sel);
  const main = $("#main");
  const state = { meta: null, projects: null, models: new Map(), scale: 3, sheetZoom: 1, unitQuery: "", unitRole: "all",
    godQuery: "", godStatus: "all", godSource: "all", nation: null, editors: new Map(), exports: new Map(), creates: new Map(), arts: new Map(),
    nationEditors: new Map(), catalogUnits: new Map(), compare: { query: "", results: null, searching: false },
    authData: new Map(), authoring: new Map(), refs: new Map(), importDraft: null, toolDrafts: new Map(), depDrafts: new Map(),
    maps: new Map(), mapImports: new Map(), inspector: new Map() };

  // ---------- DOM helpers (never innerHTML) ----------
  function el(tag, attrs, ...kids) {
    const n = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v === null || v === undefined || v === false) continue;
        if (k === "text") n.textContent = String(v);
        else if (k === "class") n.className = v;
        else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
        else n.setAttribute(k, v === true ? "" : String(v));
      }
    }
    for (const kid of kids.flat(Infinity)) {
      if (kid === null || kid === undefined || kid === false) continue;
      n.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
    }
    return n;
  }
  const txt = (v) => (v === null || v === undefined ? "" : String(v));
  const badge = (t, kind) => el("span", { class: `badge ${kind || ""}`, text: t });
  const unresolved = (t) => el("span", { class: "unresolved", text: t || "unresolved" });
  const encPath = (p) => String(p).split("/").map(encodeURIComponent).join("/");
  // Project links carry the selected nation (?n=) so every view, back link and bookmark keeps it.
  const hashPath = (...parts) => "#/" + parts.map((p) => encodeURIComponent(String(p))).join("/");
  const routeNation = (key, ...parts) => `${hashPath(...parts)}?n=${encodeURIComponent(key)}`;
  const route = (...parts) => parts[0] === "p" && state.nation && state.nation.slug === String(parts[1])
    ? routeNation(state.nation.key, ...parts) : hashPath(...parts);

  // ---------- nation selection (shared by Overview, Nation, Units, Sites and Pretenders) ----------
  // Keys: a nation id (or its uid tail for unnumbered blocks), "all", or "none" (definitions tied to no nation).
  const N_ALL = "all", N_NONE = "none";
  const nationKey = (n) => String(n.id ?? n.uid.split(":")[1]);
  const nationLabel = (n) => `${txt(n.name || n.uid)}${n.id !== null && n.id !== undefined ? ` (#${n.id})` : ""}`;
  const storedNation = (slug) => { try { return localStorage.getItem(`kosmo.nation.${slug}`); } catch (_) { return null; } };
  const rememberNation = (slug, key) => { try { localStorage.setItem(`kosmo.nation.${slug}`, key); } catch (_) { /* private mode */ } };
  // URL first, then this project's remembered choice, then the first nation.
  function resolveNation(m, wanted) {
    const keys = m.nations.map(nationKey);
    for (const k of [wanted, storedNation(m.project.slug)]) if (k && (k === N_ALL || k === N_NONE || keys.includes(k))) return k;
    return keys[0] || N_ALL;
  }
  const selectedNation = (m) => m.nations.find((n) => nationKey(n) === state.nation.key) || null;
  const unitNationUids = (u) => [...new Set((u.nations || []).map((x) => x.nation))];
  // Shared definitions appear under every nation they are tied to; "none" lists those tied to no nation.
  function inSelectedNation(m, uids) {
    if (state.nation.key === N_ALL) return true;
    if (state.nation.key === N_NONE) return !uids.length;
    const n = selectedNation(m);
    return !!n && uids.includes(n.uid);
  }
  const nationScopeText = (m) => state.nation.key === N_ALL ? "all nations" : state.nation.key === N_NONE ? "no nation" : nationLabel(selectedNation(m));
  const nationNames = (m, uids) => uids.map((uid) => { const n = m.nations.find((x) => x.uid === uid); return n ? txt(n.name || uid) : uid; });

  function table(headers, rows, opts = {}) {
    const t = el("table", null,
      opts.caption ? el("caption", { text: opts.caption }) : null,
      el("thead", null, el("tr", null, headers.map((h) => (h instanceof Node ? el("th", { scope: "col" }, h) : el("th", { scope: "col", text: h }))))),
      el("tbody", null, rows.map((r) => {
        const cells = Array.isArray(r) ? r : r.cells;
        const tr = el("tr", { class: (!Array.isArray(r) && r.class) || null },
          cells.map((c) => (c instanceof Node && c.tagName === "TD" ? c : el("td", null, c))));
        return tr;
      })));
    return el("div", { class: "table-wrap" }, t);
  }
  const panel = (title, ...kids) => el("section", { class: "panel" }, title ? el("h3", { text: title }) : null, kids);

  function stateBox(kind, title, detail) {
    const box = el("div", { class: `state state-${kind}`, role: kind === "error" ? "alert" : "status" });
    if (kind === "loading") box.append(el("span", { class: "spinner", "aria-hidden": "true" }));
    box.append(el("span", null, el("strong", { text: title }), detail ? el("div", null, detail) : null));
    return box;
  }
  function errorBox(err, what) {
    const e = (err && err.error) || { code: "network_error", message: String(err && err.message || err) };
    return stateBox("error", `Could not load ${what}.`,
      el("span", null, el("span", { class: "code", text: `[${e.code}] ` }), txt(e.message),
        e.details ? el("div", { class: "faint mono", text: JSON.stringify(e.details) }) : null));
  }
  function toast(msg) {
    const t = el("div", { class: "toast", role: "status", text: msg });
    document.body.append(t);
    setTimeout(() => t.remove(), 1800);
  }

  // ---------- save receipts ----------
  // Every successful save, create or art upload leaves a receipt under the project header (file, new revision, backup)
  // that survives route changes until dismissed; the toast only echoes it. Receipts are kept per project slug, so they
  // never appear in another project, and are dropped when the project leaves the workspace list.
  const receipts = new Map();
  const RECEIPT_MAX = 5;
  function recordReceipt(slug, title, r, extra) {
    const res = r || {};
    if (res.written === false) return;
    const files = Array.isArray(res.files) ? res.files.map((f) => (typeof f === "string" ? f : txt(f && (f.path || f.file)))).filter(Boolean) : [];
    const list = receipts.get(slug) || [];
    list.unshift({ title, at: new Date(), file: res.file || res.dm || null, sha: res.after_sha256 || null,
      revision: typeof res.revision === "string" ? res.revision : null, backup: res.backup || null, files, ...(extra || {}) });
    receipts.set(slug, list.slice(0, RECEIPT_MAX));
    // Writes that only redraw their own panel (no route render) still show the receipt at once.
    const head = main.querySelector(".proj-head"), ds = main.querySelector("#draft-status");
    if (head && ds && ds.dataset.slug === slug) {
      const panelNode = receiptPanel(slug), old = main.querySelector(".receipt");
      if (old) old.replaceWith(panelNode); else head.after(panelNode);
    }
  }
  function receiptPanel(slug) {
    const list = receipts.get(slug);
    if (!list || !list.length) return null;
    const [last, ...older] = list;
    const time = (d) => d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    const facts = (x) => el("dl", { class: "kv receipt-facts" },
      x.file ? [el("dt", { text: "File" }), el("dd", { class: "mono", text: x.file })] : null,
      x.folder ? [el("dt", { text: "Folder" }), el("dd", null, el("span", { class: "mono", text: x.folder }), x.folderNote ? el("span", { class: "faint", text: ` (${x.folderNote})` }) : null)] : null,
      x.files.length ? [el("dt", { text: x.files.length === 1 ? "New file" : "New files" }), el("dd", { class: "mono", text: x.files.join(", ") })] : null,
      x.sha ? [el("dt", { text: "New revision" }), el("dd", { class: "mono", title: x.sha }, `SHA-256 ${shortSha(x.sha)}`)] : null,
      x.revision ? [el("dt", { text: "Revision" }), el("dd", { class: "mono", title: x.revision }, shortRev(x.revision))] : null,
      el("dt", { text: "Backup" }), el("dd", { class: x.backup ? "mono" : "faint", text: x.backup || x.backupNote || "None reported for this write" }));
    const box = el("section", { class: "receipt", "aria-labelledby": "receipt-h" },
      el("div", { class: "receipt-head" },
        el("h2", { id: "receipt-h", class: "receipt-title" }, badge("saved", "ok"), " ", last.title),
        el("span", { class: "faint", text: `at ${time(last.at)}` }),
        el("button", { type: "button", class: "btn btn-small btn-ghost receipt-dismiss", "aria-label": "Dismiss save receipts for this project",
          onclick: () => { receipts.delete(slug); box.remove(); const t = $("#page-title"); if (t) t.focus({ preventScroll: true }); } }, "Dismiss")),
      facts(last),
      older.length ? el("details", { class: "raw tech receipt-older" }, el("summary", null, `Earlier saves this session (${older.length})`),
        el("div", { class: "inner" }, el("ol", { class: "plain-list" }, older.map((x) => el("li", null,
          el("strong", { text: x.title }), el("span", { class: "faint", text: ` at ${time(x.at)}` }), facts(x)))))) : null);
    return box;
  }

  // ---------- data ----------
  async function getJSON(url, opts) {
    const signal = opts && opts.signal;
    const aborted = () => ({ error: { code: "aborted", message: "Superseded by a newer request." } });
    let res;
    try { res = await fetch(url, { headers: { Accept: "application/json" }, cache: "no-store", signal }); }
    catch (e) {
      if (signal && signal.aborted) throw aborted();
      throw { error: { code: "network_error", message: "The local server is not reachable. Is `kosmokrator serve` still running?" } };
    }
    let body;
    try { body = await res.json(); } catch (e) {
      if (signal && signal.aborted) throw aborted();
      throw { error: { code: "bad_response", message: `HTTP ${res.status}` } };
    }
    if (!res.ok || body.ok === false) throw body.error ? body : { error: { code: `http_${res.status}`, message: res.statusText } };
    return body;
  }
  async function getText(url) {
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) {
      let e = { error: { code: `http_${res.status}`, message: res.statusText } };
      try { e = await res.json(); } catch (_) { /* keep generic */ }
      throw e;
    }
    return res.text();
  }
  // Optional trait icon manifest (GET /api/trait-icons): command -> { url, width, height }. A command without an
  // entry has no confirmed icon and stays text-only; a failed or missing manifest just means no icons.
  const traitIcons = new Map();
  // Native catalog icons by fixed key, following the catalog's own formatter: Gem_<P> for gem amounts (costs,
  // income), Path_<P> for magic path skill and requirements, Path_U for random picks, abilityicons/holy for sacred.
  // A key that does not load stays text-only; letters and names are always shown beside the art.
  const PATH_KEYS = ["F", "A", "W", "E", "S", "D", "N", "G", "B", "H"];
  const gemIcons = new Map(), skillIcons = new Map(), abilityIcons = new Map();
  // Icon source: the server-wide catalog ("/api"), or a project's own reference snapshot through its project-scoped
  // routes while that project is open. Projects without a snapshot keep the server-wide icons.
  const iconScope = { base: "/api", key: "global" };
  async function useIconScope(m) {
    const ref = m && m.reference, snap = ref && ref.active ? ref.snapshot : null;
    const key = snap ? `${m.project.slug}:${snap}` : "global";
    if (iconScope.key === key) return;
    iconScope.key = key;
    iconScope.base = snap ? `/api/projects/${encodeURIComponent(m.project.slug)}` : "/api";
    for (const map of [traitIcons, gemIcons, skillIcons, abilityIcons]) map.clear();
    await Promise.all([loadTraitIcons(), loadGemIcons()]);
  }
  // The catalog a project reads (its snapshot or the live catalog); without a project, the server-wide one.
  const catalogOf = (m) => (m ? (m.provenance && m.provenance.catalog) || null : (state.meta && state.meta.catalog) || null);
  function probeIcon(map, key, url, cls) {
    return new Promise((done) => {
      const img = new Image(), timer = setTimeout(() => { img.src = ""; done(); }, 3000);
      img.onload = () => { clearTimeout(timer); if (img.naturalWidth > 0 && img.naturalWidth <= 64 && img.naturalHeight <= 64) map.set(key, { url, cls, width: img.naturalWidth, height: img.naturalHeight }); done(); };
      img.onerror = () => { clearTimeout(timer); done(); };
      img.src = url;
    });
  }
  function loadGemIcons() {
    const b = iconScope.base;
    return Promise.all([...PATH_KEYS.map((p) => probeIcon(gemIcons, p, `${b}/gem-icons/${p}.png`, "gem-ic")),
      ...[...PATH_KEYS, "U"].map((p) => probeIcon(skillIcons, p, `${b}/path-icons/${p}.png`, "path-img")),
      probeIcon(abilityIcons, "holy", `${b}/ability-icons/holy.png`, "trait-icon")]);
  }
  async function loadTraitIcons() {
    const ctl = new AbortController(), timer = setTimeout(() => ctl.abort(), 3000);
    try {
      const b = iconScope.base;
      const res = await fetch(`${b}/trait-icons`, { headers: { Accept: "application/json" }, cache: "no-store", credentials: "same-origin", signal: ctl.signal });
      if (!res.ok) return;
      const body = await res.json();
      if (!body || body.ok !== true || !body.icons || typeof body.icons !== "object") return;
      for (const [raw, ic] of Object.entries(body.icons)) {
        const cmd = String(raw).replace(/^#/, "").toLowerCase();
        // Only accept this exact same-origin API path for the command; anything else is ignored.
        if (!/^[a-z0-9_]+$/.test(cmd) || !ic || typeof ic.url !== "string" || ic.url.toLowerCase() !== `${b}/trait-icons/${cmd}.png`.toLowerCase()) continue;
        const dim = (v) => (Number.isInteger(v) && v > 0 && v <= 64 ? v : 32);
        traitIcons.set(cmd, { url: ic.url, width: dim(ic.width), height: dim(ic.height) });
      }
    } catch (_) { /* optional: keep text-only traits */ }
    finally { clearTimeout(timer); }
  }
  // Decorative pixel icon shown beside a trait's text; removed if it fails to load, so the text remains alone.
  function traitIcon(cmd, value) {
    const key = String(cmd).replace(/^#/, "").toLowerCase();
    const negative = typeof value === "number" ? value < 0 : typeof value === "string" && /^-\d+$/.test(value);
    // Without the extracted trait cache, sacred falls back to the catalog's own sacred badge.
    const ic = (negative && traitIcons.get(`${key}_negative`)) || traitIcons.get(key) || (key === "holy" ? abilityIcons.get("holy") : null);
    if (!ic) return null;
    const img = el("img", { class: "trait-icon", src: ic.url, alt: "", width: ic.width, height: ic.height, decoding: "async", draggable: "false" });
    img.addEventListener("error", () => img.remove(), { once: true });
    return img;
  }
  // Stat icons, decorative and always beside the visible label. Only verified game art is used: gold, resources and
  // recruitment/commander points take the misc.trs frames the game itself draws beside those labels (optional local
  // cache, /api/trait-icons/stat_*). The game draws base stats as text only, so they get no icon. Fixed allowlist.
  const STAT_NATIVE = { gold: "stat_gold", resources: "stat_resources", recruitment_points: "stat_recpoints", commander_points: "stat_compoints" };
  // Display labels used across sheets, cards and tables, matched exactly (an "(base)" fallback suffix is ignored).
  const STAT_KEY_OF_LABEL = new Map([
    ["hit points", "hp"], ["hp", "hp"], ["size", "size"], ["protection", "prot"], ["natural protection", "prot"],
    ["magic res", "mr"], ["magic resistance", "mr"], ["morale", "mor"], ["leadership", "leader"], ["strength", "str"],
    ["attack skill", "att"], ["attack", "att"], ["base attack", "att"], ["defence skill", "def"], ["defence", "def"], ["base defence", "def"],
    ["precision", "prec"], ["base precision", "prec"], ["combat speed", "ap"], ["comb. speed", "ap"], ["combat speed (ap)", "ap"],
    ["encumbrance", "enc"], ["base encumbrance", "enc"], ["map move", "mapmove"], ["gold", "gold"], ["resources", "resources"],
    ["rec points", "recruitment_points"], ["recruitment points", "recruitment_points"]]);
  const statKeyOf = (label) => STAT_KEY_OF_LABEL.get(String(label).toLowerCase().replace(/ \(base\)$/, "")) || null;
  // Native cost art or null; a missing cache entry or a failed load leaves the text label alone, with no substitute.
  function statIcon(key) {
    const ic = key && Object.hasOwn(STAT_NATIVE, key) ? traitIcons.get(STAT_NATIVE[key]) : null;
    if (!ic) return null;
    const img = el("img", { class: "stat-ic stat-ic-native", src: ic.url, alt: "", width: ic.width, height: ic.height, decoding: "async", draggable: "false", "aria-hidden": "true" });
    img.addEventListener("error", () => img.remove(), { once: true });
    return img;
  }
  // Icon and visible text together; unknown keys return the text alone.
  const statLabel = (key, text) => { const ic = statIcon(key); return ic ? el("span", { class: "stat-label" }, ic, text) : text; };
  async function model(slug, force) {
    if (force || !state.models.has(slug)) state.models.set(slug, getJSON(`/api/projects/${encodeURIComponent(slug)}`));
    try { return await state.models.get(slug); }
    catch (e) { state.models.delete(slug); throw e; }
  }
  // Resolves true only when the text reached the clipboard: the async API succeeded, or the legacy command reported
  // success. Callers that move a workflow forward must check the result.
  async function copy(text, label) {
    let ok = false;
    if (navigator.clipboard && window.isSecureContext) {
      try { await navigator.clipboard.writeText(text); ok = true; } catch (_) { ok = false; }
    }
    if (!ok) {
      const back = document.activeElement;
      const ta = el("textarea", { class: "sr-only", readonly: true, tabindex: "-1", "aria-hidden": "true" });
      ta.value = text; document.body.append(ta); ta.select();
      try { ok = document.execCommand("copy") === true; } catch (_e) { ok = false; }
      ta.remove();
      if (back && back.isConnected && typeof back.focus === "function") back.focus({ preventScroll: true });
    }
    toast(ok ? `${label} copied` : `${label} not copied: the browser blocked the clipboard`);
    return ok;
  }

  function jsonActions(url, getObj, label) {
    return el("div", { class: "btn-row" },
      el("button", { type: "button", class: "btn btn-small", onclick: () => copy(JSON.stringify(getObj(), null, 2), label) }, "Copy JSON"),
      el("a", { class: "btn btn-small", href: `${url}${url.includes("?") ? "&" : "?"}download=1`, download: "" }, "Download JSON"),
      el("a", { class: "btn btn-small btn-ghost", href: url, target: "_blank", rel: "noopener" }, "Open JSON URL"));
  }

  // ---------- shared renderers ----------
  // Compact "L12" link to the source view; the full file:line is in the title and accessible name.
  function srcRef(slug, file, line, full) {
    if (!line) return el("span", { class: "src-ref", text: file || "" });
    return el("a", { class: "src-ref", href: route("p", slug, "source", line), title: `${file}:${line} - show in source`,
      "aria-label": `${file} line ${line}` }, full ? `${file}:${line}` : `L${line}`);
  }
  function monsterLink(slug, ref) {
    if (!ref) return unresolved("none");
    if (ref.origin === "project" && ref.id !== null) return el("a", { href: route("p", slug, "units", ref.id) }, `${txt(ref.name)} (#${ref.id})`);
    if (ref.origin === "catalog") return el("span", null, `${txt(ref.name)} (#${ref.id}) `, badge("vanilla", "info"));
    return el("span", null, `${txt(ref.name || ref.ref)} `, badge(ref.unresolved || "unresolved", "warn"));
  }
  function siteLink(slug, ref) {
    if (!ref) return unresolved("none");
    if (ref.origin === "project") return el("a", { href: route("p", slug, "sites", ref.id) }, `${txt(ref.name)} (#${ref.id})`);
    if (ref.origin === "catalog") return el("span", null, `${txt(ref.name)} (#${ref.id}) `, badge("vanilla", "info"));
    return el("span", null, `${txt(ref.name || ref.ref)} `, badge(ref.unresolved || "unresolved", "warn"));
  }
  function statusBadge(s) {
    if (s === "curated") return badge("curated", "ok");
    if (s === "documented_uncurated") return badge("documented", "info");
    return badge("unverified", "warn");
  }
  function effectBadge(e) {
    if (!e) return badge("-", "");
    if (e.startsWith("unsupported")) return badge("not modelled", "warn");
    if (e.startsWith("applied")) return el("span", { title: e }, badge("applied", "ok"), e.includes(":") ? el("span", { class: "faint", text: ` ${e.split(": ")[1]}` }) : null);
    if (e === "unresolved donor") return badge("unresolved donor", "err");
    return badge(e.split(":")[0], "");
  }
  function authoredTable(slug, obj) {
    return table(["Line", "Command", "Arguments", "Manual status", "Browser effect"], obj.authored.map((c) => [
      srcRef(slug, obj.source.file, c.line), el("code", { text: c.command }),
      el("code", { text: c.args.join(" ") }), statusBadge(c.status), effectBadge(c.effect)]));
  }
  function codeBlock(text, firstLine, highlight) {
    const pre = el("pre", { class: "code", tabindex: "0", "aria-label": "Source code" });
    const lines = text.split(/\r?\n/);
    lines.forEach((ln, i) => {
      const n = firstLine + i;
      const span = el("span", { class: "ln" + (n === highlight ? " hl" : ""), "data-n": n, id: `L${n}` });
      highlightDm(span, ln);
      pre.append(span);
    });
    return pre;
  }
  // Lightweight colouring of one .dm line: comments, #commands, "strings", numbers.
  function highlightDm(target, line) {
    const re = /(--.*$)|(#[A-Za-z0-9_]+)|("[^"]*"?)|(-?\b\d+(?:\.\d+)?\b)/g;
    let last = 0, m;
    while ((m = re.exec(line))) {
      if (m.index > last) target.append(line.slice(last, m.index));
      const cls = m[1] ? "c-comment" : m[2] ? "c-cmd" : m[3] ? "c-str" : "c-num";
      target.append(el("span", { class: cls, text: m[0] }));
      last = m.index + m[0].length;
    }
    if (last < line.length) target.append(line.slice(last));
    if (!line.length) target.append("​");
  }
  function sourcePanel(slug, obj, kindLabel) {
    const s = obj.source;
    return panel("Source block",
      el("p", { class: "panel-note" }, `${kindLabel} defined at `, srcRef(slug, s.file, s.line, true), ` - lines ${s.line}-${s.end_line}.`),
      el("div", { class: "btn-row" },
        el("button", { type: "button", class: "btn btn-small", onclick: () => copy(s.text, "Source block") }, "Copy block"),
        el("a", { class: "btn btn-small", href: `/api/projects/${encodeURIComponent(slug)}/source?download=1`, download: "" }, "Download .dm")),
      el("div", { style: null }, codeBlock(s.text, s.line)));
  }
  function diagnosticsList(slug, items, file) {
    if (!items || !items.length) return el("p", { class: "muted", text: "No validation items for this block." });
    return el("ul", { class: "diag" }, items.map((d) => el("li", null,
      badge(d.severity, d.severity === "error" ? "err" : d.severity === "warning" ? "warn" : "info"),
      el("code", { text: d.code }), el("span", { text: d.message }), srcRef(slug, d.file || file, d.line))));
  }
  function spriteImg(src, alt, scale, onFail) {
    const img = el("img", { src, alt, decoding: "async" });
    img.addEventListener("load", () => {
      if (!scale) return; // 0 = size comes from CSS
      img.width = img.naturalWidth * scale; img.height = img.naturalHeight * scale;
      img.title = `${img.naturalWidth}x${img.naturalHeight} px shown at ${scale}x`;
    });
    img.addEventListener("error", () => img.replaceWith(onFail || el("div", { class: "preview-missing", text: "Preview unavailable" })));
    return img;
  }

  // The mod's #icon banner (4:1), never a nation flag. Missing or unreadable -> neutral placeholder.
  function bannerImg(banner, alt) {
    const hole = (why) => el("div", { class: "mod-banner placeholder", title: why, text: "no banner" });
    if (!banner) return hole("No #icon in the .dm");
    if (!banner.preview) return hole(`#icon ${banner.path}: ${banner.status === "missing" ? "file missing" : "no browser preview"}`);
    const img = spriteImg(banner.preview, alt, 0, hole(`#icon ${banner.path}: preview unavailable`));
    img.className = "mod-banner";
    return img;
  }

  // ---------- sidebar ----------
  async function loadProjects(force) {
    const list = $("#project-list");
    if (force || !state.projects) {
      list.replaceChildren(stateBox("loading", "Reading workspace..."));
      try {
        state.projects = await getJSON("/api/projects");
        const listed = new Set((state.projects.projects || []).map((p) => p.slug));
        for (const s of [...receipts.keys()]) if (!listed.has(s)) receipts.delete(s);
      } catch (e) {
        state.projects = null;
        list.replaceChildren(errorBox(e, "projects"));
        return;
      }
    }
    renderSidebar();
    renderCatalogStatus();
  }
  // Only a problem is shown; ready vanilla data needs no header badge.
  function renderCatalogStatus(m) {
    const box = $("#catalog-status");
    const meta = state.meta || {};
    const cat = meta.catalog, ref = m && m.reference;
    if (ref && ref.active) {
      box.replaceChildren(...(ref.state === "stale" ? [badge("Vanilla data update available", "warn")] : []));
    } else if (ref && ref.state === "invalid") {
      box.replaceChildren(badge("Vanilla data needs repair", "err"));
    } else if (cat) {
      box.replaceChildren();
    } else {
      const n = (meta.project_references && meta.project_references.projects_with_snapshot) || 0;
      box.replaceChildren(...(n ? [] : [badge("Vanilla data unavailable", "warn")]));
    }
  }
  // Compact rows: a small banner, name, era/version/validation and slug. A filter appears once the list is long,
  // so test or fixture projects never push the one being worked on off screen.
  const projectFilter = el("input", { type: "search", class: "input project-filter", id: "project-filter", placeholder: "Filter projects",
    "aria-label": "Filter projects", autocomplete: "off", spellcheck: "false", hidden: true });
  projectFilter.addEventListener("input", () => { state.projectQuery = projectFilter.value; renderSidebar(); });
  const projectMatches = (p) => {
    const q = txt(state.projectQuery).trim().toLowerCase();
    return !q || [p.slug, p.name, p.mod_name, p.nation, p.era_name].some((x) => x && String(x).toLowerCase().includes(q));
  };
  // Problems only: a clean project shows no badge.
  const validationBadge = (v) => !v ? badge("not validated", "warn") : v.ok
    ? (v.counts.warnings ? badge(`${v.counts.warnings} warning${v.counts.warnings === 1 ? "" : "s"}`, "warn") : null)
    : badge(`${v.counts.errors} error${v.counts.errors === 1 ? "" : "s"}`, "err");
  // The vanilla catalog sits under the project list: it opens the inspector of one project, which reads that project's own
  // reference snapshot (or the live catalog). Without a selected project it names the last selected or first readable one.
  const storedLastProject = () => { try { return localStorage.getItem("kosmo.lastProject"); } catch (_) { return null; } };
  function renderCatalogNav(cur) {
    const box = $("#catalog-nav");
    const readable = state.projects ? state.projects.projects.filter((p) => p.ok) : [];
    const find = (s) => s && readable.find((p) => p.slug === s);
    let target = find(cur), why = null;
    if (target) { try { localStorage.setItem("kosmo.lastProject", target.slug); } catch (_) { /* private mode */ } }
    else if ((target = find(storedLastProject()))) why = "Last selected project";
    else if ((target = readable[0])) why = "First project";
    if (!target) {
      box.replaceChildren(el("p", { class: "faint sidebar-empty", text: "Open a project to browse the catalog." }));
      return;
    }
    const name = target.nation || target.name || target.slug;
    const here = !why && (location.hash.match(/^#\/p\/([^/?]+)\/inspector(?:[/?]|$)/) || [])[1] === target.slug;
    box.replaceChildren(el("a", { class: "catalog-link", href: route("p", target.slug, "inspector"), "aria-current": here ? "page" : null,
      "aria-label": `Vanilla catalog for ${name} (${target.slug})${why ? `, ${why.toLowerCase()}` : ""}` },
      el("span", { class: "title", text: "Vanilla catalog" }),
      why ? el("span", { class: "faint", text: `${why}: ${name}` }) : null));
  }
  function renderSidebar(current) {
    const list = $("#project-list");
    const data = state.projects;
    const cur = current !== undefined ? current : (location.hash.match(/^#\/p\/([^/?]+)/) || [])[1];
    renderCatalogNav(cur);
    if (!data) return;
    if (!projectFilter.isConnected) list.before(projectFilter);
    projectFilter.hidden = data.projects.length <= 5;
    if (!data.projects.length) {
      list.replaceChildren(el("p", { class: "faint sidebar-empty" }, "No projects yet. ", el("a", { href: "#/start" }, "Start a nation or map")));
      return;
    }
    const shown = projectFilter.hidden ? data.projects : data.projects.filter((p) => projectMatches(p) || p.slug === cur);
    // The slug is shown only where two projects would otherwise look the same.
    const shownName = (p) => txt(p.nation || p.name || p.slug);
    const dupName = (p) => data.projects.filter((x) => x.ok && shownName(x) === shownName(p)).length > 1;
    if (!shown.length) { list.replaceChildren(el("p", { class: "faint sidebar-empty", role: "status", text: "No project matches the filter." })); return; }
    list.replaceChildren(...shown.map((p) => {
      if (!p.ok) {
        return el("div", { class: "project-card is-broken", role: "group", "aria-label": `${p.slug} (unreadable)` },
          el("div", { class: "pc-text" }, el("div", { class: "title", text: p.slug }),
            el("div", { class: "meta" }, badge("unreadable", "err"), el("span", { class: "mono", text: p.error.code })),
            el("div", { class: "faint", text: p.error.message })));
      }
      return el("a", { class: "project-card", href: route("p", p.slug), "aria-current": p.slug === cur ? "page" : null, title: `${txt(p.mod_name || p.name || p.slug)} (${p.slug})` },
        bannerImg(p.banner, ""),
        el("div", { class: "pc-text" },
          el("div", { class: "title", text: p.nation || p.name || p.slug }),
          el("div", { class: "meta" },
            p.era_name ? el("span", { text: p.era_name }) : null,
            p.version ? el("span", { text: `v${p.version}` }) : null, validationBadge(p.validation)),
          dupName(p) ? el("div", { class: "faint mono slug", text: p.slug }) : null));
    }));
  }

  // ---------- project shell ----------
  // Section groups shown in the tab bar; keys and routes are unchanged. Browse and Build are always visible;
  // the secondary Files group sits behind the More disclosure so the page content starts sooner on narrow screens.
  const TAB_GROUPS = [
    ["browse", "Browse", [["overview", "Overview"], ["nation", "Nation"], ["units", "Units"], ["pretenders", "Pretenders"], ["sites", "Sites"], ["spells", "Spells"], ["items", "Items"], ["mercs", "Mercenaries"], ["maps", "Maps"], ["balance", "Balance"]]],
    ["edit", "Build", [["author", "Advanced tools"], ["health", "Health"], ["validation", "Validation"], ["export", "Export"]]],
    ["files", "More", [["source", "Source"], ["assets", "Assets"], ["other", "Other definitions"], ["docs", "Docs"]]],
  ];
  // The vanilla inspector is reached from the sidebar's Catalog section, not the tab bar.
  const TABS = [...TAB_GROUPS.flatMap((g) => g[2]), ["inspector", "Vanilla catalog"]];
  // Sections that follow the nation selector; the rest are always project-wide.
  const NATION_TABS = new Set(["overview", "nation", "units", "pretenders", "balance", "sites"]);
  const nationUnits = (m) => m.monsters.filter((u) => inSelectedNation(m, unitNationUids(u)));
  const nationSites = (m) => m.sites.filter((s) => inSelectedNation(m, s.start_site_of));
  // Pretender list counts: the selected nation's listed candidates, every god for "all", unlisted custom gods for "none".
  function nationPretenderCount(m) {
    const P = m.pretenders;
    if (!P) return null;
    if (state.nation.key === N_ALL) return P.counts.gods;
    if (state.nation.key === N_NONE) return P.gods.filter((g) => g.source === "project" && !(g.availability || []).length).length;
    const n = selectedNation(m), nv = n && P.nations.find((x) => x.nation === n.uid);
    return nv ? nv.counts.listed : 0;
  }
  function tabCount(m, key) {
    const c = m.counts;
    // Units counts every entry its list shows for the selected nation (recruits, heroes, summons, pretender forms ...).
    return { nation: c.nations, units: nationUnits(m).length, pretenders: nationPretenderCount(m),
      sites: nationSites(m).length, spells: otherOfKind(m, "spell").length, items: otherOfKind(m, "item").length, mercs: otherOfKind(m, "merc").length, other: c.other_definitions, assets: c.asset_files,
      validation: m.validation ? m.validation.counts.errors + m.validation.counts.warnings + m.validation.counts.unverified : null,
      docs: m.project.docs.length + ((state.meta && state.meta.docs.length) || 0) }[key];
  }
  // The shared nation picker. Changing it keeps the current section and any open unit, site or god detail.
  function nationBar(m, active, arg) {
    const slug = m.project.slug;
    if (!m.nations.length) return null;
    const sel = el("select", { class: "input", id: "nation-select" },
      m.nations.map((n) => el("option", { value: nationKey(n), text: nationLabel(n) })),
      el("option", { value: N_NONE, text: "Not tied to a nation" }),
      el("option", { value: N_ALL, text: "All nations" }));
    sel.value = state.nation.key;
    sel.addEventListener("change", () => {
      state.nation = { slug, key: sel.value };
      rememberNation(slug, sel.value);
      // The Nation tab's argument is the nation itself, so it is dropped; other details stay open.
      // An open section editor ("<section>/edit/<key>") keeps its entry.
      location.hash = active === "nation" || !arg ? route("p", slug, active)
        : SECTION_EDITORS[active] && arg === "edit" ? route("p", slug, ...parseHash().slice(2)) : route("p", slug, active, arg);
    });
    // Tab tooltips say which sections follow the selector; no standing explanation here.
    return el("div", { class: "nation-bar", role: "group", "aria-label": "Nation selection" },
      el("label", { for: "nation-select", text: "Nation" }), sel);
  }
  // The nation selector appears only where it filters something: the nation sections, and Heroes (set per nation).
  const showsNation = (active, arg) => NATION_TABS.has(active) || (active === "author" && arg === "heroes");
  // Remembered per project so the Vanilla catalog can offer an exact way back.
  const lastProjectHash = new Map();
  function tabLink(m, key, label, active) {
    const slug = m.project.slug, cnt = tabCount(m, key), wide = !NATION_TABS.has(key);
    const xs = key === "export" ? exportStatus(m) : null;
    return el("a", { href: route("p", slug, key), "aria-current": key === active ? "page" : null, class: wide ? "wide" : null,
      title: xs ? `Export: ${xs[0]}` : wide ? "Project-wide" : `Filtered to ${nationScopeText(m)}` },
      label, cnt !== undefined && cnt !== null ? el("span", { class: "count", text: cnt }) : null,
      xs ? el("span", { class: `tab-flag ${xs[1]}`, text: xs[0] }) : null);
  }
  // "More" disclosure for the secondary sections (Source, Assets, Other definitions, Docs). A button controls a list of
  // ordinary links: Escape or a click elsewhere closes it, arrow keys move through it, and the current section shows on the button.
  function moreMenu(m, items, active) {
    const cur = items.find(([k]) => k === active);
    const id = "tab-more-list";
    const list = el("ul", { class: "tab-more-list", id, hidden: true }, items.map(([k, l]) => el("li", null, tabLink(m, k, l, active))));
    const btn = el("button", { type: "button", class: "tab-more-btn" + (cur ? " is-current" : ""), "aria-expanded": "false", "aria-controls": id },
      cur ? `More: ${cur[1]}` : "More", el("span", { class: "caret", "aria-hidden": "true", text: "▾" }));
    const wrap = el("div", { class: "tab-more" }, btn, list);
    const links = () => [...list.querySelectorAll("a")];
    const outside = (e) => { if (!wrap.contains(e.target)) setOpen(false); };
    function setOpen(open, focus) {
      list.hidden = !open;
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      if (open) document.addEventListener("pointerdown", outside, true); else document.removeEventListener("pointerdown", outside, true);
      if (open && focus) (links().find((a) => a.getAttribute("aria-current") === "page") || links()[0]).focus();
      if (!open && focus) btn.focus();
    }
    btn.addEventListener("click", () => setOpen(list.hidden, false));
    btn.addEventListener("keydown", (e) => { if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true, true); } });
    wrap.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !list.hidden) { e.preventDefault(); e.stopPropagation(); setOpen(false, true); return; }
      const ls = links(), i = ls.indexOf(document.activeElement);
      if (i < 0 || (e.key !== "ArrowDown" && e.key !== "ArrowUp")) return;
      e.preventDefault(); e.stopPropagation();
      if (e.key === "ArrowUp" && i === 0) { btn.focus(); return; }
      ls[Math.min(ls.length - 1, i + (e.key === "ArrowDown" ? 1 : -1))].focus();
    });
    wrap.addEventListener("focusout", (e) => { if (!list.hidden && e.relatedTarget && !wrap.contains(e.relatedTarget)) setOpen(false); });
    list.addEventListener("click", (e) => { if (e.target.closest("a")) setOpen(false); });
    return wrap;
  }
  function projectShell(m, active, arg) {
    const slug = m.project.slug;
    if (active === "inspector") return catalogShell(m);
    const n = selectedNation(m) || m.nations[0];
    const banner = bannerImg(m.project.banner, `${m.project.mod_name || m.project.name || slug} banner`);
    const [primary, secondary] = [TAB_GROUPS.filter((g) => g[0] !== "files"), TAB_GROUPS.find((g) => g[0] === "files")];
    const groups = el("div", { class: "tabs-scroll", id: "tabs-scroll" }, primary.map(([gk, glabel, items]) =>
      el("div", { class: `tab-group tab-group-${gk}`, role: "group", "aria-label": glabel }, items.map(([key, label]) => tabLink(m, key, label, active)))));
    // Narrow screens put the tabs in one sideways-scrolling row; these buttons (with a fade) show there is more on that
    // side and scroll by about a screen width. They are hidden whenever that side has nothing more.
    const nudge = (dir, label, glyph) => el("button", { type: "button", class: `tabs-nudge tabs-${dir < 0 ? "prev" : "next"}`, "aria-label": label,
      "aria-controls": "tabs-scroll", hidden: true, onclick: () => groups.scrollBy({ left: dir * Math.max(120, groups.clientWidth * 0.7), behavior: reducedMotion() ? "auto" : "smooth" }) },
      el("span", { "aria-hidden": "true", text: glyph }));
    const prev = nudge(-1, "Scroll section tabs left", "‹"), next = nudge(1, "Scroll section tabs right", "›");
    const rail = el("div", { class: "tabs-rail" }, prev, groups, next);
    tabOverflow(rail, groups, prev, next);
    const tabs = el("nav", { class: "tabs", "aria-label": "Project sections" }, rail, moreMenu(m, secondary[2], active));
    // Left/Right move along the visible tabs and the More button.
    tabs.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      const stops = [...groups.querySelectorAll("a"), tabs.querySelector(".tab-more-btn")];
      const i = stops.indexOf(document.activeElement);
      if (i < 0) return;
      e.preventDefault();
      stops[(i + (e.key === "ArrowRight" ? 1 : stops.length - 1)) % stops.length].focus();
    });
    const nDrafts = unsavedDrafts(slug).length;
    const head = el("div", { class: "proj-head" }, banner,
      el("div", { class: "proj-title" },
        el("h1", { tabindex: "-1", id: "page-title", text: m.project.mod_name || m.project.name || slug }),
        el("div", { class: "sub" },
          [n && n.epithet, m.project.era_name, m.project.version && `v${m.project.version}`]
            .filter(Boolean).join(" · "))),
      el("div", { class: "proj-actions" },
        showsNation(active, arg) ? nationBar(m, active, arg) : null,
        el("span", { id: "draft-status", "data-slug": slug, hidden: !nDrafts || null },
          el("a", { class: "badge warn", href: route("p", slug, "export"), title: "Drafts are kept in this browser tab only; Export lists them" },
            `${nDrafts} unsaved draft${nDrafts === 1 ? "" : "s"}`))));
    const banners = [];
    if (m.catalog_error) banners.push(stateBox("empty", "No game-data catalog.",
      `${m.catalog_error.message} Donor stats and vanilla references are shown as unresolved.`));
    for (const d of m.diagnostics || []) banners.push(stateBox(d.severity === "error" ? "error" : "empty", d.code, d.message));
    return [head, receiptPanel(slug), ...banners, tabs].filter(Boolean);
  }
  const reducedMotion = () => !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  // Shows a scroll button only on a side with hidden tabs. A focused button that disappears hands focus to the nearest tab.
  function tabOverflow(rail, sc, prev, next) {
    let ro = null;
    const sync = () => {
      if (!sc.isConnected) { if (ro && rail.dataset.mounted) ro.disconnect(); return; }
      rail.dataset.mounted = "1";
      const max = sc.scrollWidth - sc.clientWidth, left = max > 1 && sc.scrollLeft > 1, right = max > 1 && sc.scrollLeft < max - 1;
      for (const [b, on] of [[prev, left], [next, right]]) {
        if (!on && !b.hidden && document.activeElement === b) {
          const ls = [...sc.querySelectorAll("a")];
          const t = b === prev ? ls[0] : ls[ls.length - 1];
          if (t) t.focus({ preventScroll: true });
        }
        b.hidden = !on;
      }
      rail.classList.toggle("can-left", left);
      rail.classList.toggle("can-right", right);
    };
    sc.addEventListener("scroll", sync, { passive: true });
    if (typeof ResizeObserver === "function") { ro = new ResizeObserver(sync); ro.observe(sc); }
    return sync;
  }
  // After a route renders, centre the current tab inside the scrolling strip. Only the strip scrolls, never the page;
  // a current section in the More menu leaves the strip where it is.
  function revealActiveTab() {
    const sc = main.querySelector(".tabs-scroll");
    if (!sc || sc.scrollWidth <= sc.clientWidth + 1) return;
    const a = sc.querySelector('a[aria-current="page"]');
    if (!a) return;
    const sr = sc.getBoundingClientRect(), ar = a.getBoundingClientRect();
    sc.scrollLeft += (ar.left + ar.width / 2) - (sr.left + sr.width / 2);
  }
  // The Vanilla catalog is a separate, read-only reference context: no project tabs or nation selector, its own heading,
  // where the data comes from, and an explicit way back. Routes (#/p/<slug>/inspector/...) and the APIs are unchanged;
  // the project in the address only decides which snapshot or live catalog is read.
  function catalogShell(m) {
    const slug = m.project.slug, name = txt(m.project.mod_name || m.project.name || slug);
    const cat = catalogOf(m), snap = cat && cat.reference_snapshot;
    const back = lastProjectHash.get(slug) || route("p", slug, "overview");
    return [el("header", { class: "catalog-head" },
      el("div", { class: "catalog-head-text" },
        el("p", { class: "catalog-kicker" }, badge("read-only reference", "info"), " Vanilla game data"),
        el("h1", { tabindex: "-1", id: "page-title", text: "Vanilla catalog" }),
        el("p", { class: "sub" }, !cat ? "No catalog is available for this project."
          : snap ? ["Reading ", el("strong", { text: `${name}'s reference snapshot` }), ` (${txt(snap.snapshot)}). Nothing here changes the project.`]
            : ["Reading ", el("strong", { text: "the live catalog" }), ` the server was started with, opened from ${name}. Nothing here changes the project.`])),
      el("a", { class: "btn catalog-back", href: back }, `← Back to ${name}`))];
  }

  // ---------- project readiness (top of Overview) ----------
  // Everything comes from the server's readiness block (parsed .dm + current mod folder) and the export list read
  // fresh with the project. Shared and vanilla sprites are informational; only missing files and errors need work.
  function exportTime(s) {
    const t = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$/.exec(txt(s));
    const d = t ? new Date(Date.UTC(+t[1], t[2] - 1, +t[3], +t[4], +t[5], +t[6])) : new Date(txt(s));
    return Number.isNaN(d.getTime()) ? null : d;
  }
  function agoText(d) {
    const s = Math.round((Date.now() - d.getTime()) / 1000);
    if (s < 90) return "just now";
    const units = [[86400, "day"], [3600, "hour"], [60, "minute"]];
    for (const [n, l] of units) if (s >= n) { const v = Math.round(s / n); return `${v} ${l}${v === 1 ? "" : "s"} ago`; }
    return "just now";
  }
  function readinessPanel(m) {
    const slug = m.project.slug, R = m.readiness, p = m.provenance;
    const holder = el("section", { class: "panel readiness", "aria-labelledby": "ready-h" });
    if (!R) {
      holder.append(el("h3", { id: "ready-h", text: "Readiness" }),
        stateBox("empty", "Readiness is not available from this server.", "Restart `kosmokrator serve` to load the current version, then reload."));
      return holder;
    }
    const S = R.sprites, V = R.validation, sc = S.counts;
    const unitHref = (u) => route("p", slug, "units", u.id ?? u.uid);
    const unitA = (u) => el("a", { href: unitHref(u) }, `${txt(u.name || "(unnamed)")}${u.id !== null && u.id !== undefined ? ` (#${u.id})` : ""}`);
    const goExport = () => { location.hash = route("p", slug, "export"); };
    function exportRow() {
      const L = m.latest_export, x = L && L.export;
      if (!L) return ["info", "Not reported by this server.", null];
      if (!L.available) return ["warn", `Export list unreadable (${txt(L.error)}).`, null];
      if (!x) return ["info", "No exports yet.", "Export when validation is clean."];
      const d = exportTime(x.created_utc), when = d ? agoText(d) : "time unknown";
      const cur = x.sha256 && x.sha256 === p.sha256;
      return [x.error ? "warn" : cur ? "ok" : "warn",
        x.error ? `${when}; manifest unreadable (${txt(x.error)}).` : cur ? `${when}; matches the saved .dm.` : `${when}; built from an older .dm revision.`,
        el("span", { class: "mono faint", title: d ? d.toLocaleString() : null, text: `${txt(x.export_id)} · ${txt(x.format)}` })];
    }
    function draw() {
      const vOk = V.available && V.ok, vc = V.counts || {};
      const nMissingSpr = sc.missing, nMissingFiles = R.missing_assets_count;
      const [xKind, xText, xDetail] = exportRow();
      const rows = [
        { key: "validation", kind: !V.available ? "err" : vOk ? (vc.warnings ? "warn" : "ok") : "err", label: "Validation",
          text: !V.available ? "Could not run; see diagnostics above." : vOk ? `No errors · ${vc.warnings} warning${vc.warnings === 1 ? "" : "s"} · ${vc.unverified} unverified`
            : `${vc.errors} error${vc.errors === 1 ? "" : "s"} must be fixed before export.`,
          action: el("a", { href: route("p", slug, "validation") }, "Validation report") },
        { key: "files", kind: nMissingFiles ? "err" : "ok", label: "Referenced files",
          text: nMissingFiles ? `${nMissingFiles} file${nMissingFiles === 1 ? " is" : "s are"} named in the .dm but not in the mod folder.` : "Every file the .dm names is in the mod folder.",
          action: el("a", { href: route("p", slug, "assets") }, "Assets") },
        { key: "sprites", kind: nMissingSpr ? "err" : "ok", label: "Unit sprites",
          text: [`${sc.custom} custom`, sc.vanilla ? `${sc.vanilla} vanilla` : null, sc.inherited ? `${sc.inherited} copied from project units` : null,
            nMissingSpr ? `${nMissingSpr} missing` : "none missing"].filter(Boolean).join(" · "),
          action: el("a", { href: route("p", slug, "units") }, "Units") },
        { key: "export", kind: xKind, label: "Latest export", text: xText, detail: xDetail,
          action: el("button", { type: "button", class: "btn btn-small btn-ghost", onclick: goExport }, "Open export") },
      ];
      const attention = R.status !== "ready";
      // Rows that pass are left out; the latest export always stays as the route to Export.
      const kindWord = { warn: "Check", err: "Fix" };
      const list = el("ul", { class: "ready-list" }, rows.filter((r) => r.kind === "warn" || r.kind === "err" || r.key === "export").map((r) => el("li", { class: `ready-row is-${r.kind}`, "data-ready": r.key },
        kindWord[r.kind] ? el("span", { class: `badge ${r.kind}`, text: kindWord[r.kind] }) : el("span", { "aria-hidden": "true" }),
        el("span", { class: "ready-label", text: r.label }),
        el("span", { class: "ready-text" }, r.text, r.detail ? el("span", { class: "ready-detail" }, r.detail) : null),
        r.action ? el("span", { class: "ready-action" }, r.action) : null)));

      const lists = [];
      if (V.errors.length) lists.push(el("details", { class: "raw", open: true }, el("summary", null, `Validation errors (${vc.errors})`),
        el("div", { class: "inner" }, diagnosticsList(slug, V.errors, p.file),
          vc.errors > V.errors.length ? el("p", { class: "faint" }, `Showing ${V.errors.length}. `, el("a", { href: route("p", slug, "validation") }, "See all in the validation report")) : null)));
      if (R.missing_assets.length) lists.push(el("details", { class: "raw", open: true }, el("summary", null, `Missing files (${nMissingFiles})`),
        el("div", { class: "inner" }, el("ul", { class: "plain-list ready-items" }, R.missing_assets.map((a) => el("li", null, el("code", { text: a.path }), " ",
          el("span", { class: "faint" }, "named by "), a.used_by.map((u, i) => [i ? ", " : "",
            /^monster:\d+$/.test(u.uid) ? el("a", { href: route("p", slug, "units", u.uid.split(":")[1]) }, txt(u.name || u.uid)) : el("span", { text: txt(u.name || u.uid) }),
            " ", srcRef(slug, p.file, u.line)])))))));
      if (S.missing.length) lists.push(el("details", { class: "raw", open: true }, el("summary", null, `Units without a sprite (${nMissingSpr})`),
        el("div", { class: "inner" }, el("ul", { class: "plain-list ready-items" }, S.missing.map((s) => el("li", null, unitA(s), " ",
          s.missing.length ? [el("span", { class: "faint", text: "missing " }), s.missing.map((f, i) => [i ? ", " : "", el("code", { text: f })])]
            : el("span", { class: "faint", text: "no #spr1, #copyspr or #copystats donor" }), " ", srcRef(slug, p.file, s.line)))),
          el("p", { class: "panel-note", text: "Open a unit and use its editor to add or replace art." }))));
      if (S.vanilla.length || S.inherited.length) {
        const srcText = (s) => s.source ? `${s.source.via} ${txt(s.source.ref)}${s.source.name ? ` ${s.source.name}` : ""}` : "";
        lists.push(el("details", { class: "raw" }, el("summary", null, `Vanilla and copied sprites (${sc.vanilla + sc.inherited})`),
          el("div", { class: "inner" },
            el("p", { class: "panel-note", text: "These units borrow an existing sprite instead of custom art." }),
            el("ul", { class: "plain-list ready-items" }, [...S.vanilla, ...S.inherited].map((s) => el("li", null, unitA(s), " ",
              badge(s.status === "vanilla" ? "vanilla sprite" : "copied sprite", "info"), " ",
              el("span", { class: "faint", text: `from ${srcText(s)}` }), " ", s.source ? srcRef(slug, p.file, s.source.line) : null,
              s.status === "vanilla" && s.source && s.source.verified === false ? [" ", badge("not in catalog", "warn")] : null,
              s.overwritten.length ? el("div", { class: "ready-note" }, badge("note", "warn"), " ",
                `Custom ${s.overwritten.map((o) => `${o.command} (L${o.line})`).join(", ")} ${s.overwritten.length === 1 ? "is" : "are"} replaced by the later #copystats on L${s.source && s.source.line}. Move #spr1/#spr2 after it to use custom art.`) : null))))));
      }
      if (S.shared.length) lists.push(el("details", { class: "raw" }, el("summary", null, `Shared sprites (${S.shared_count})`),
        el("div", { class: "inner" },
          el("p", { class: "panel-note", text: "Allowed. Give a unit its own art only if it should look different." }),
          el("ul", { class: "plain-list ready-items" }, S.shared.map((g) => el("li", null,
            g.files.map((f, i) => [i ? " = " : "", el("code", { text: f })]), g.kind === "same_content" ? [" ", badge("identical files", "info")] : null,
            el("div", { class: "ready-units" }, g.monsters.map((u, i) => [i ? ", " : "", unitA(u)]))))),
          S.shared_count > S.shared.length ? el("p", { class: "faint", text: `Showing ${S.shared.length} of ${S.shared_count}.` }) : null)));

      fillKids(holder,
        el("div", { class: "ready-head" },
          el("h3", { id: "ready-h", text: "Readiness" }),
          attention ? badge("needs attention", "err") : null),
        list, lists);
    }
    draw();
    exportUi(slug).redrawReadiness = draw;
    return holder;
  }

  // ---------- reference snapshot (Overview) ----------
  // Copies the catalog tables and local reference art this project needs into <project>/.kosmokrator/reference so it
  // can be browsed and edited without the external catalog. The server checks the saved .dm hash and the current
  // snapshot id under the project lock; nothing here is ever packaged into exports or Workshop folders.
  const mb = (n) => `${(Number(n || 0) / 1048576).toFixed(n >= 10485760 ? 0 : 1)} MB`;
  function referenceUi(slug) {
    if (!state.reference) state.reference = new Map();
    if (!state.reference.has(slug)) state.reference.set(slug, { sprites: "referenced", busy: null, preview: null, result: null, error: null });
    return state.reference.get(slug);
  }
  function referencePanel(m) {
    const slug = m.project.slug, ref = m.reference, ui = referenceUi(slug), p = m.provenance;
    if (!ref) return techSection("Reference snapshot", false,
      stateBox("empty", "Not reported by this server.", "Restart `kosmokrator serve` to load the current version, then reload."));
    const holder = el("div", { class: "inner stack" });
    const base = `/api/projects/${encodeURIComponent(slug)}`;
    const live = ref.live || {};
    const body = () => ({ expected_sha256: p.sha256, expected_snapshot: ref.snapshot || null, sprites: ui.sprites });
    async function run(preview) {
      ui.busy = preview ? "preview" : "write"; ui.error = null; if (!preview) ui.result = null; draw();
      try {
        const r = await postJSON(`${base}/reference-snapshot`, { ...body(), preview });
        if (preview) ui.preview = r;
        else { ui.result = r; ui.preview = null; }
      } catch (e) { ui.error = e; }
      ui.busy = null;
      if (!preview && ui.result) {
        // The write never touches the .dm, so there is no .dm backup; replaced snapshots are deleted, not backed up.
        const r = ui.result, t = r.totals || {}, gone = r.removed || [];
        recordReceipt(slug, `Wrote reference snapshot ${txt(r.snapshot)}`, { written: true }, {
          folder: `${slug}/${txt(r.path)}/`, folderNote: `${txt(t.files)} files · ${mb(t.bytes)}`,
          backupNote: gone.length ? `None: the .dm was not changed. Replaced snapshot${gone.length === 1 ? "" : "s"} ${gone.join(", ")} deleted, not backed up.`
            : "Not needed: the .dm was not changed and no earlier snapshot was replaced." });
        state.models.delete(slug); state.catalogUnits && state.catalogUnits.clear();
        await loadProjects(true);
        try { state.meta = await getJSON("/api/meta"); } catch (_) { /* keep the old status */ }
        await render();
        toast("Reference snapshot written");
        return;
      }
      draw();
      const h = holder.querySelector("#ref-outcome"); if (h) h.focus();
    }
    const stateRow = {
      none: ["info", "No snapshot", live.available ? "This project reads the live catalog the server was started with." : "No live catalog either: vanilla references are unresolved."],
      offline: ["ok", "Self-contained", "Reading this project's snapshot. No live catalog is configured, so it cannot be compared or refreshed."],
      current: ["ok", "Self-contained", "Reading this project's snapshot; it matches the live catalog."],
      stale: ["warn", "Snapshot differs from live catalog", "Still reading this project's snapshot (versions are never mixed). Refresh to adopt the live catalog."],
      invalid: ["err", "Snapshot failed verification", "The snapshot is not used and no live catalog data is substituted. Recreate it from a live catalog."],
    }[ref.state] || ["info", txt(ref.state), ref.summary];
    const needs = stateRow[0] === "warn" || stateRow[0] === "err";
    const box = el("details", { class: "raw tech reference-panel", open: needs || ui.open || ui.busy || ui.error || ui.preview || ui.result ? true : null },
      el("summary", null, "Reference snapshot", needs ? [" ", badge(stateRow[1], stateRow[0])] : null), holder);
    box.addEventListener("toggle", () => { ui.open = box.open; });
    const ver = (v) => v ? `${v.dataset_version ? `data ${v.dataset_version}` : "version unknown"}${v.revision ? ` · rev ${String(v.revision).slice(0, 10)}` : ""}` : "—";
    const groupRows = (g) => Object.entries(g || {}).map(([k, x]) => [txt(k).replace(/_/g, " "), txt(x.files), mb(x.bytes)]);
    function missingList(list, count) {
      if (!list || !list.length) return el("p", { class: "muted", text: "Nothing referenced is missing from the source catalog." });
      const label = (x) => x.kind === "sprite" ? `Unit ${x.id} ${x.frame} sprite` : x.kind === "unit" ? `Unit ${x.id}` : x.kind === "item_icon" ? `Item ${x.id} icon`
        : x.kind === "trait_icons" ? "Native UI icons" : `${txt(x.kind).replace(/_/g, " ")} ${txt(x.name || x.id || "")}`;
      return el("div", null, el("ul", { class: "plain-list ready-items" }, list.slice(0, 40).map((x) => el("li", null, el("strong", { text: label(x) }), " ", el("span", { class: "faint", text: txt(x.reason) })))),
        (count || list.length) > 40 ? el("p", { class: "faint", text: `Showing 40 of ${count || list.length}.` }) : null);
    }
    function planView(r, written) {
      const sc = r.scope || {};
      return el("div", { class: "stack" },
        el("p", null, el("strong", { id: "ref-outcome", tabindex: "-1", text: written ? `Snapshot ${txt(r.snapshot)} written.` : "Snapshot preview (nothing written yet)." }), " ",
          badge(`${txt(r.totals && r.totals.files)} files · ${mb(r.totals && r.totals.bytes)}`, "info")),
        el("dl", { class: "kv" },
          el("dt", { text: "Catalog tables" }), el("dd", { text: `Complete: all ${txt(sc.table_count)} gamedata tables, byte for byte.` }),
          el("dt", { text: "Unit sprites" }), el("dd", { text: sc.sprites === "all" ? `All ${txt(sc.sprite_units_count)} catalog units.` : `Partial: ${txt(sc.sprite_units_count)} catalog units this project references.` }),
          el("dt", { text: "Item, gem and path icons" }), el("dd", { text: `Items ${txt(sc.item_icons)}; gem and path icons and the sacred badge (fixed set).` }),
          el("dt", { text: "Native UI icons" }), el("dd", { text: sc.trait_icons ? "Copied from the verified workspace cache." : "Not available in this workspace; trait labels stay text-only." }),
          el("dt", { text: "Source" }), el("dd", { text: `${txt((r.source || {}).name)} · ${ver(r.source)} · ${txt((r.source || {}).license)}` })),
        table(["Group", "Files", "Size"], groupRows(r.groups), { caption: "What the snapshot holds" }),
        el("details", { class: "raw", open: (r.missing_count || 0) > 0 && (r.missing_count || 0) <= 12 || null },
          el("summary", null, `Missing from the source catalog (${txt(r.missing_count || 0)})`),
          el("div", { class: "inner" }, missingList(r.missing, r.missing_count))),
        written && (r.removed || []).length ? el("p", { class: "faint", text: `Replaced ${r.removed.join(", ")}.` }) : null);
    }
    function errorView(e) {
      const err = e.error || {};
      const title = { sha_mismatch: "Not written: the saved .dm changed since this page loaded.",
        reference_changed: "Not written: the snapshot changed since this page loaded.",
        catalog_missing: "A live catalog is needed to create or refresh the snapshot.",
        project_locked: "Not written: another save or export holds the project lock.",
        reference_too_large: "Not written: the snapshot would exceed the size limits.",
        bad_csrf: "Not written: the page token is out of date.", bad_origin: "Not written: request was not from this page." }[err.code] || "Snapshot failed.";
      const reload = ["sha_mismatch", "reference_changed", "bad_csrf"].includes(err.code);
      return el("div", { class: "state state-error", role: "alert" },
        el("strong", { id: "ref-outcome", tabindex: "-1", text: title }),
        el("div", null, el("span", { class: "code", text: `[${txt(err.code)}] ` }), txt(err.message)),
        el("div", { class: "btn-row" },
          reload ? el("button", { type: "button", class: "btn btn-small", onclick: async () => { state.models.delete(slug); await loadProjects(true); await render(); } }, "Reload project") : null,
          err.code === "project_locked" ? el("button", { type: "button", class: "btn btn-small", onclick: () => run(false) }, "Try again") : null),
        el("p", { class: "panel-note", text: "Nothing was changed by this request; the previous snapshot, if any, is still in use." }));
    }
    function draw() {
      const blocked = !CSRF ? "No editor token from this server; restart `kosmokrator serve` and reload."
        : !live.available ? (ref.active ? "Refreshing needs the live catalog: start the server with --catalog. The current snapshot stays in use." : "Creating a snapshot needs the live catalog: start the server with --catalog.")
        : null;
      const scopeSel = el("select", { class: "input", id: "ref-sprites", disabled: ui.busy || blocked ? true : null },
        el("option", { value: "referenced", text: "Sprites this project references (small)" }),
        el("option", { value: "all", text: "Every catalog unit sprite (about 20 MB, 9,000 files)" }));
      scopeSel.value = ui.sprites;
      scopeSel.addEventListener("change", () => { ui.sprites = scopeSel.value; ui.preview = null; draw(); });
      const sc = ref.scope || {}, t = ref.totals || {};
      const nowMissing = ref.sprites_missing_now_count || 0;
      fillKids(holder,
        el("p", { class: "panel-note", text: "Copies the catalog data and art this project uses into its folder, so it works without the external catalog." }),
        el("p", { class: "export-drafts", role: "note" }, badge("local only", "warn"),
          " Contains imagery from your own copy of Dominions 6. Exports and Workshop folders never include it. Do not share it."),
        el("ul", { class: "ready-list" },
          el("li", { class: `ready-row is-${stateRow[0]}` }, el("span", { class: `badge ${stateRow[0]}`, text: { ok: "OK", warn: "Check", err: "Fix", info: "Info" }[stateRow[0]] }),
            el("span", { class: "ready-label", text: "Status" }), el("span", { class: "ready-text", text: stateRow[2] })),
          ref.active ? el("li", { class: "ready-row is-info" }, el("span", { class: "badge info", text: "Info" }), el("span", { class: "ready-label", text: "Snapshot" }),
            el("span", { class: "ready-text" }, `${ver(ref.version)} · ${txt(t.files)} files · ${mb(t.bytes)}`,
              el("span", { class: "ready-detail mono faint", text: `${txt(ref.snapshot)} · created ${txt(ref.created_utc)}` }))) : null,
          ref.active ? el("li", { class: `ready-row is-${sc.sprites === "all" || !nowMissing ? "ok" : "warn"}` },
            el("span", { class: `badge ${sc.sprites === "all" || !nowMissing ? "ok" : "warn"}`, text: sc.sprites === "all" || !nowMissing ? "OK" : "Check" }),
            el("span", { class: "ready-label", text: "Coverage" }),
            el("span", { class: "ready-text", text: `Tables complete (${txt(sc.table_count)}). ${sc.sprites === "all" ? "All unit sprites." : `Sprites for ${txt(sc.sprite_units_count)} referenced units (partial).`}`
              + (nowMissing ? ` ${nowMissing} unit${nowMissing === 1 ? " referenced now has" : "s referenced now have"} no sprite in the snapshot; refresh to add.` : "")
              + (ref.project_changed ? " The .dm changed since the snapshot was made." : "") })) : null,
          live.available ? el("li", { class: "ready-row is-info" }, el("span", { class: "badge info", text: "Info" }), el("span", { class: "ready-label", text: "Live catalog" }),
            el("span", { class: "ready-text", text: ver(live) })) : null),
        ref.state === "invalid" && ref.error ? stateBox("error", txt(ref.error.message), (ref.error.problems || []).join(", ") || null) : null,
        el("div", { class: "btn-row export-controls" },
          el("label", { for: "ref-sprites", class: "faint", text: "Sprites" }), scopeSel,
          el("button", { type: "button", class: "btn btn-small btn-ghost", disabled: ui.busy || blocked ? true : null, "aria-describedby": blocked ? "ref-blocked" : null, onclick: () => run(true) },
            ui.busy === "preview" ? "Checking…" : "Preview size and coverage"),
          el("button", { type: "button", class: "btn", disabled: ui.busy || blocked ? true : null, "aria-describedby": blocked ? "ref-blocked" : null, onclick: () => run(false) },
            ui.busy === "write" ? "Writing snapshot…" : ref.active ? "Refresh snapshot" : "Make project self-contained")),
        blocked ? el("p", { class: "panel-note", id: "ref-blocked", text: blocked }) : null,
        el("div", { role: "status", "aria-live": "polite" }, ui.busy ? stateBox("loading", ui.busy === "preview" ? "Measuring what the snapshot would hold..." : "Copying and verifying the snapshot...") : null),
        ui.error ? errorView(ui.error) : ui.result ? planView(ui.result, true) : ui.preview ? planView(ui.preview, false) : null,
        ref.active && !ui.preview && !ui.result ? el("details", { class: "raw" }, el("summary", null, `Missing from the source catalog when made (${(ref.missing || []).length})`),
          el("div", { class: "inner" }, missingList(ref.missing))) : null,
        el("p", { class: "panel-note", text: `Stored in ${slug}/.kosmokrator/reference/ with a manifest of sources, versions, licences and hashes. Catalog data: dom6inspector (GPL-3.0), licence copied alongside.` }));
    }
    draw();
    return box;
  }

  // ---------- views ----------
  function viewOverview(m) {
    const slug = m.project.slug, c = m.counts, v = m.validation, p = m.provenance;
    const tile = (n, l, href) => el(href ? "a" : "div", { class: "tile", href, style: null },
      el("div", { class: "n", text: n }), el("div", { class: "l", text: l }));
    const base = `/api/projects/${encodeURIComponent(slug)}`;
    const rc = rosterCounts(m);
    const pretenders = nationPretenderCount(m);
    // Roster tiles open Units with the matching role filter, so each number leads to the same list.
    const rosterTile = (key, label) => { const a = tile(rc[key], label, route("p", slug, "units")); a.addEventListener("click", () => { state.unitRole = key; }); return a; };
    return el("div", { class: "stack" },
      (m.mod_info.description || {}).value ? el("p", { class: "prose muted", text: m.mod_info.description.value }) : null,
      readinessPanel(m),
      referencePanel(m),
      el("section", { "aria-labelledby": "ov-nation" },
        el("h4", { id: "ov-nation", text: `Nation: ${nationScopeText(m)}` }),
        el("div", { class: "tiles" },
          rosterTile("troop", "recruitable troops"), rosterTile("commander", "recruitable commanders"),
          rc.hero ? rosterTile("hero", rc.hero === 1 ? "hero" : "heroes") : null,
          rc.summon ? rosterTile("summon", rc.summon === 1 ? "summon" : "summons") : null,
          rc.other ? rosterTile("other", "start army / defence only") : null,
          pretenders !== null ? tile(pretenders, state.nation.key === N_NONE ? "unlisted custom gods" : pretenders === 1 ? "pretender listed" : "pretenders listed", route("p", slug, "pretenders")) : null,
          rc.pretender ? tile(rc.pretender, rc.pretender === 1 ? "custom pretender form" : "custom pretender forms", route("p", slug, "pretenders")) : null,
          tile(nationSites(m).length, state.nation.key === N_ALL || state.nation.key === N_NONE ? "sites" : "start sites", route("p", slug, "sites")),
          rc.unassigned ? rosterTile("unassigned", "units tied to no nation") : null)),
      el("section", { "aria-labelledby": "ov-project" },
        el("h4", { id: "ov-project", text: "Project-wide" }),
        el("div", { class: "tiles" },
          tile(c.nations, "nations", route("p", slug, "nation")), tile(c.monsters, "monster definitions", route("p", slug, "units")),
          tile(c.sites, "site definitions", route("p", slug, "sites")))),
      // Validation counts live in the readiness panel above; this panel keeps only what readiness does not show.
      panel("Dependencies",
        !v ? stateBox("error", "Validation unavailable", "See diagnostics above.")
          : !m.readiness ? el("p", null, v.ok ? badge("no errors", "ok") : badge("has errors", "err"), " ",
            `${v.counts.errors} errors · ${v.counts.warnings} warnings · ${v.counts.unverified} unverified `,
            el("a", { href: route("p", slug, "validation") }, "Open validation report")) : null,
        m.compatibility && (m.compatibility.overlaps || []).length ? el("p", null, badge(`${m.compatibility.overlaps.length} overlap(s) with dependencies or vanilla`, "warn"),
          el("span", { class: "faint" }, " Listed in the ", el("a", { href: route("p", slug, "validation") }, "validation report"), ".")) : null,
        CSRF ? depEditor(m) : el("p", { class: "faint", text: m.project.dependencies.length ? `Dependencies: ${m.project.dependencies.join(", ")}` : "No dependencies listed." })),
      techSection("Details", false,
        el("div", { class: "grid-2" },
          panel("Mod info", el("dl", { class: "kv" },
            el("dt", { text: "#modname" }), el("dd", { text: (m.mod_info.modname || {}).value || "—" }),
            el("dt", { text: "#version" }), el("dd", { text: (m.mod_info.version || {}).raw || "—" }),
            el("dt", { text: "Project slug" }), el("dd", { class: "mono", text: slug }),
            el("dt", { text: "Source file" }), el("dd", null, srcRef(slug, p.file, null)),
            el("dt", { text: "SHA-256" }), el("dd", { class: "hash", text: p.sha256 }),
            el("dt", { text: "Encoding" }), el("dd", { text: p.encoding }),
            el("dt", { text: "Target game" }), el("dd", { text: txt(m.project.target_game_version) }),
            el("dt", { text: "Manual" }), el("dd", { text: txt(m.project.manual_version) }),
            el("dt", { text: "Dependencies" }), el("dd", { text: m.project.dependencies.length ? m.project.dependencies.join(", ") : "none" }),
            el("dt", { text: "Sprite frames" }), el("dd", null, el("a", { href: route("p", slug, "assets") }, txt(c.sprite_frames))),
            el("dt", { text: "Flags" }), el("dd", null, el("a", { href: route("p", slug, "assets") }, txt(c.flags))),
            el("dt", { text: "Other definitions" }), el("dd", null, el("a", { href: route("p", slug, "other") }, txt(c.other_definitions))))),
          panel("Catalog provenance",
            p.catalog ? el("dl", { class: "kv" },
              el("dt", { text: "Read from" }), el("dd", { text: p.catalog.reference_snapshot ? `this project's reference snapshot (${p.catalog.reference_snapshot.snapshot})` : "live catalog" }),
              el("dt", { text: "Dataset" }), el("dd", { text: p.catalog.dataset_version || "unknown" }),
              el("dt", { text: "Revision" }), el("dd", { class: "hash", text: p.catalog.revision || "unknown" }),
              el("dt", { text: "Source" }), el("dd", { class: "faint", text: p.catalog.source })) :
              el("p", { class: "muted", text: "No catalog supplied." }))),
        panel("JSON",
          table(["Resource", "URL", ""], [
            ["Whole project", base], ["Nations", `${base}/nations`], ["Monsters", `${base}/monsters`], ["Sites", `${base}/sites`],
            ["Pretenders", `${base}/pretenders`], ["Other definitions", `${base}/other_definitions`], ["Assets", `${base}/assets`], ["Validation", `${base}/validation`],
            ["Raw .dm source", `${base}/source`],
          ].map(([label, url]) => [label, el("a", { class: "mono", href: url, target: "_blank", rel: "noopener", text: url }),
            el("a", { class: "btn btn-small", href: `${url}?download=1`, download: "" }, "Download")])),
          el("div", { class: "btn-row" }, el("button", { type: "button", class: "btn btn-small", onclick: () => copy(JSON.stringify(m, null, 2), "Project JSON") }, "Copy project JSON"))),
        panel("Limitations", el("ul", null, m.limitations.map((l) => el("li", { text: l }))))));
  }

  function viewNation(m, arg) {
    const slug = m.project.slug;
    if (arg === "~new") return nationCreator(m);
    const newBtn = CSRF ? el("div", { class: "btn-row create-bar" }, el("a", { class: "btn btn-small", href: route("p", slug, "nation", "~new") }, "New nation")) : null;
    if (!m.nations.length) return el("div", { class: "stack" }, newBtn, stateBox("empty", "No nation blocks.", "This project defines or selects no nation. Create one with New nation."));
    const n = selectedNation(m);
    if (!n) {
      return el("div", { class: "stack" }, newBtn,
        stateBox("empty", "Choose a nation."),
        table(["Nation", "Era"], m.nations.map((x) => [el("a", { href: route("p", slug, "nation", nationKey(x)) }, nationLabel(x)),
          txt(x.era_name || "unknown")])));
    }
    // Roster lines and per-unit Compare stay reachable through Advanced (authored commands) and the unit sheet.
    // The recruiting command is in the tooltip; the authored commands under Details list every line.
    const rows = (list) => list.length ? el("ul", { class: "plain-list" }, list.map((r) =>
      el("li", { title: txt(r.command) }, monsterLink(slug, r.monster)))) : el("p", { class: "muted", text: "None." });
    const sa = n.start_army;
    const swatch = (rgb) => {
      const s = el("span", { class: "swatch", "aria-hidden": "true" });
      if (Array.isArray(rgb) && rgb.length >= 3 && rgb.every((x) => typeof x === "number")) {
        s.style.backgroundColor = `rgb(${rgb.slice(0, 3).map((x) => Math.round(Math.max(0, Math.min(1, x)) * 255)).join(",")})`;
      }
      return s;
    };
    const same = (x, y) => txt(x).trim() === txt(y).trim();
    return el("div", { class: "stack" }, newBtn, nationEditorSection(m, n),
      panel(`${txt(n.name)}${n.epithet ? ", " + n.epithet : ""}`,
        el("div", { class: "nation-ident" },
          n.flag ? el("div", { class: "sprite-box nation-flag" }, spriteImg(`${n.flag.url}?format=png`, `${txt(n.name)} flag`, 1)) : null,
          el("dl", { class: "kv" },
            el("dt", { text: "Era" }), el("dd", { text: n.era_name ? `${n.era_name} (#era ${n.era})` : "unknown" }),
            el("dt", { text: "Colours" }), el("dd", null, Object.entries(n.colors).map(([k, c]) => el("span", { title: `#${k} ${c.rgb.join(" ")}` }, swatch(c.rgb), `${k === "color" ? "primary" : "secondary"} `))),
            n.flag ? null : [el("dt", { text: "Flag" }), el("dd", { text: "none" })])),
        n.brief ? el("p", { class: "prose", style: null }, el("em", { text: n.brief })) : null,
        Number.isInteger(n.id) ? el("p", { class: "cross-link" }, el("a", { class: "btn btn-small", href: route("p", slug, "author", "heroes") }, "Edit heroes")) : null),
      n.description ? panel("Description", el("p", { class: "prose", text: n.description })) : null,
      n.summary && !same(n.summary, n.description) ? panel("Summary", el("p", { class: "prose", text: n.summary })) : null,
      el("div", { class: "grid-2" },
        panel("Fort troops (#addrecunit)", rows(n.recruitment.troops)),
        panel("Fort commanders (#addreccom)", rows(n.recruitment.commanders))),
      (() => {
        // Capital-site, terrain and coastal recruits come from the units' own recruitment entries (same source as Units and Balance).
        const other = m.monsters.flatMap((u) => recruitsFor(m, u, n).filter((r) => !/^#addrec(unit|com)$/.test(txt(r.via))).map((r) => ({ u, r })));
        return other.length ? panel(`Other recruitment (${other.length})`, el("ul", { class: "plain-list" }, other.map(({ u, r }) =>
          el("li", null, el("a", { href: route("p", slug, "units", u.id ?? u.uid) }, `${txt(u.name || "(unnamed)")}${u.id !== null && u.id !== undefined ? ` (#${u.id})` : ""}`), " ", el("code", { text: txt(r.via) }), " ",
            el("span", { class: "faint", text: r.site_name ? `${r.where} (${r.site_name})` : txt(r.where) }))))) : null;
      })(),
      el("div", { class: "grid-2" },
        panel("Start army",
          el("dl", { class: "kv" },
            el("dt", { text: "Commander" }), el("dd", null, sa.commander ? [monsterLink(slug, sa.commander.monster), " ", srcRef(slug, n.source.file, sa.commander.line)] : unresolved("none set")),
            el("dt", { text: "Scout" }), el("dd", null, sa.scout ? [monsterLink(slug, sa.scout.monster), " ", srcRef(slug, n.source.file, sa.scout.line)] : unresolved("none set")),
            ...sa.units.flatMap((u) => [el("dt", { text: `Unit slot ${u.slot}` }),
              el("dd", null, u.count !== null ? `${u.count} × ` : unresolved("count unset "), monsterLink(slug, u.monster), " ", srcRef(slug, n.source.file, u.lines[0]))]))),
        panel("Start sites and gems",
          n.start_sites.length ? table(["Site", "Gems"], n.start_sites.map((s) => {
            const g = n.gem_sites.find((x) => x.site === s.site.uid);
            return [siteLink(slug, s.site), g ? gemList(g.gems) : unresolved("no modelled gems")];
          })) : el("p", { class: "muted", text: "No start sites." }),
          el("p", { class: "panel-note" }, "Start-site gems per turn: ", gemList(n.gem_sites.flatMap((g) => g.gems), "none")))),
      n.defence.length ? panel("Province defence, walls and guards", table(["Command", "Value", "Line"], n.defence.map((d) =>
        [el("code", { text: d.command }), d.monster ? monsterLink(slug, d.monster) : txt(d.count), srcRef(slug, n.source.file, d.line)]))) : null,
      n.diagnostics.length ? panel(`Diagnostics (${n.diagnostics.length})`, diagnosticsList(slug, n.diagnostics, n.source.file)) : null,
      techSection("Details: commands, source and JSON", false,
        panel("Flag and clears",
          el("dl", { class: "kv" },
            el("dt", { text: "Nation" }), el("dd", null, el("code", { text: `#selectnation ${txt(n.id)}` }), " ", srcRef(slug, n.source.file, n.source.line)),
            el("dt", { text: "Flag" }), el("dd", null, n.flag ? [el("code", { text: n.flag.path }), " ", srcRef(slug, n.source.file, n.flag.line), " ",
              el("a", { href: `${n.flag.url}?format=png`, target: "_blank", rel: "noopener" }, "Open PNG preview")] : "none"),
            el("dt", { text: "Clears" }), el("dd", null, n.clears.length ? n.clears.map((x) => [el("code", { text: x.command }), " ", srcRef(slug, n.source.file, x.line), " "]) : "none"))),
        n.other_commands.length ? panel("Other nation commands (listed, not interpreted)", table(["Command", "Arguments", "Status", "Line"], n.other_commands.map((o) =>
          [el("code", { text: o.command }), el("code", { text: o.args.join(" ") }), statusBadge(o.status), srcRef(slug, n.source.file, o.line)]))) : null,
        panel(`Authored commands (${n.authored.length})`, authoredTable(slug, n)),
        sourcePanel(slug, n, "Nation"),
        panel("JSON", jsonActions(`/api/projects/${encodeURIComponent(slug)}/nations/${encodeURIComponent(n.id)}`, () => n, "Nation JSON"))));
  }

  // Summons come from a nonempty u.summoning; the backend role stays troop/commander. Summon-only units (no direct recruitment) are
  // grouped under Summons; directly recruited units that can also be summoned keep their role group and still match the Summons filter.
  // Heroes come only from live national #heroN/#multiheroN ties in u.nations (the backend drops slots overwritten later or
  // cleared by #clearnation), scoped to the selected nation; never from the unit name or #unique. The backend role stays
  // commander. Hero-only units (no direct recruitment) are grouped under Heroes, ahead of Summons when both apply.
  const HERO_VIA = /^#(multi)?hero\d+$/;
  // `n` (a nation object) overrides the selected nation; Balance classifies each project nation this way.
  function heroTies(m, u, n) {
    const ties = (u.nations || []).filter((x) => HERO_VIA.test(txt(x.via)));
    if (n === undefined) {
      if (state.nation.key === N_ALL) return ties;
      n = state.nation.key === N_NONE ? null : selectedNation(m);
    }
    return n ? ties.filter((x) => x.nation === n.uid) : [];
  }
  const isHero = (m, u, n) => heroTies(m, u, n).length > 0;
  const isSummon = (u) => Array.isArray(u.summoning) && u.summoning.length > 0;
  // Shared roster classification for Units, Overview, the tab count and Balance. A recruit has a recruitment entry for the
  // selected nation (fort, capital or other start site, terrain or coastal command); everything else is a hero, summon,
  // pretender form, a unit tied only by start army or province defence ("other"), or tied to no nation.
  function recruitsFor(m, u, n) {
    const rec = u.recruitment || [];
    if (n === undefined) {
      if (state.nation.key === N_ALL || state.nation.key === N_NONE) return rec;
      n = selectedNation(m);
    }
    if (!n) return [];
    return rec.filter((r) => r.nation === n.uid || (r.site && (u.nations || []).some((x) => x.nation === n.uid && x.site === r.site)));
  }
  function unitGroup(m, u, n) {
    if (u.role === "pretender") return "pretender";
    if (recruitsFor(m, u, n).length) return u.role === "commander" ? "commander" : "troop";
    if (isHero(m, u, n)) return "hero";
    if (isSummon(u)) return "summon";
    return u.role === "troop" || u.role === "commander" ? "other" : "unassigned";
  }
  const ROSTER_GROUPS = [["troop", "Recruitable troops", "recruitable troop", "recruitable troops"], ["commander", "Recruitable commanders", "recruitable commander", "recruitable commanders"],
    ["hero", "Heroes", "hero", "heroes"], ["summon", "Summons (not recruited)", "summon", "summons"],
    ["other", "Start army or defence only (not recruitable)", "start army / defence unit", "start army / defence units"],
    ["unassigned", "Not tied to a nation", "unit tied to no nation", "units tied to no nation"], ["pretender", "Pretender forms (not recruitable)", "pretender form", "pretender forms"]];
  function rosterCounts(m, n) {
    const c = Object.fromEntries(ROSTER_GROUPS.map((g) => [g[0], 0]));
    const pool = n === undefined ? nationUnits(m) : m.monsters.filter((u) => unitNationUids(u).includes(n.uid));
    for (const u of pool) c[unitGroup(m, u, n)]++;
    return c;
  }
  const rosterWord = (key, n) => { const g = ROSTER_GROUPS.find((x) => x[0] === key); return `${n} ${n === 1 ? g[2] : g[3]}`; };
  // "11 recruitable troops · 7 recruitable commanders · 1 hero ..." (empty groups left out).
  const rosterSummary = (c, keys) => (keys || ROSTER_GROUPS.map((g) => g[0])).filter((k) => c[k]).map((k) => rosterWord(k, c[k])).join(" · ");
  function unitMatches(m, u, q, role) {
    if (role !== "all" && (role === "summon" ? !isSummon(u) : role === "hero" ? !isHero(m, u) : unitGroup(m, u) !== role)) return false;
    if (!q) return true;
    const heroVia = heroTies(m, u).map((x) => x.via.slice(1));
    const hay = [u.name, u.id, u.role, heroVia.length ? "hero" : "", ...heroVia, isSummon(u) ? "summon" : "", u.uid, u.donor && u.donor.name, u.donor && u.donor.id].map(txt).join(" ").toLowerCase();
    return q.toLowerCase().split(/\s+/).every((t) => hay.includes(t));
  }
  function viewUnits(m, sel, sub) {
    const slug = m.project.slug;
    const ca = creatorArg(sel);
    if (ca) return creatorView(m, "unit", ca.dup);
    if (!m.monsters.length) return el("div", { class: "stack" }, createButtons(m, "unit"), stateBox("empty", "No monster blocks.", "This project defines or selects no monsters. Create one with New unit."));
    const selected = m.monsters.find((u) => String(u.id) === String(sel) || u.uid === sel) || null;
    const listEl = el("ul", { class: "unit-list", "aria-label": "Units" });
    const search = el("input", { class: "input", type: "search", placeholder: "Search units  ( / )", "aria-label": "Search units by name, id, role or donor", value: state.unitQuery });
    const roleSel = el("select", { class: "input", "aria-label": "Filter by role" },
      [["all", "All roles"], ["troop", "Recruitable troops"], ["commander", "Recruitable commanders"], ["hero", "Heroes"], ["summon", "Summons"],
        ["other", "Start army or defence only"], ["unassigned", "Not tied to a nation"], ["pretender", "Pretender forms"]].map(([v, l]) => {
        const o = el("option", { value: v, text: l }); if (v === state.unitRole) o.selected = true; return o;
      }));
    // One visible count line doubles as the live status for search and filter changes.
    const status = el("p", { class: "faint", role: "status", "aria-live": "polite" });
    const pool = nationUnits(m), counts = rosterCounts(m);
    function fill() {
      const shown = pool.filter((u) => unitMatches(m, u, state.unitQuery, state.unitRole));
      listEl.replaceChildren();
      // Under the Heroes or Summons filter every match is listed in that group; otherwise each unit appears once, in its own group.
      const groupOf = (u) => state.unitRole === "summon" || state.unitRole === "hero" ? state.unitRole : unitGroup(m, u);
      for (const [role, groupLabel] of ROSTER_GROUPS) {
        const group = shown.filter((u) => groupOf(u) === role);
        if (!group.length) continue;
        listEl.append(el("li", { class: "group-label", "aria-hidden": "true", text: `${groupLabel} (${group.length})` }));
        for (const u of group) {
          const thumb = el("span", { class: "thumb" });
          if (u.sprites.idle) thumb.append(spriteImg(u.sprites.idle.url, "", 1, el("span", { class: "faint", text: "?" })));
          listEl.append(el("li", null, el("a", { class: "unit-item", href: route("p", slug, "units", u.id ?? u.uid), "aria-current": u === selected ? "true" : null },
            thumb, el("span", null, el("div", { class: "nm", text: u.name || "(unnamed)" }),
              el("div", { class: "sub", text: [`#${txt(u.id ?? u.selector)}`, role !== "hero" && isHero(m, u) ? "hero" : null, role !== "summon" && isSummon(u) ? "summon" : null].filter(Boolean).join(" · ") })))));
        }
      }
      if (!shown.length) listEl.append(el("li", null, stateBox("empty", pool.length ? "No units match." : `No units for ${nationScopeText(m)}.`,
        pool.length ? "Clear the search or role filter." : "Choose another nation, \"Not tied to a nation\" or \"All nations\" above.")));
      status.textContent = shown.length === pool.length ? `${pool.length} unit${pool.length === 1 ? "" : "s"}${pool.length ? `: ${rosterSummary(counts)}` : ""}` : `${shown.length} of ${pool.length} units`;
    }
    search.addEventListener("input", () => { state.unitQuery = search.value; fill(); });
    search.addEventListener("keydown", (e) => { if (e.key === "Escape") { search.value = ""; state.unitQuery = ""; fill(); } if (e.key === "ArrowDown") { e.preventDefault(); const a = listEl.querySelector("a"); if (a) a.focus(); } });
    roleSel.addEventListener("change", () => { state.unitRole = roleSel.value; fill(); });
    // Picking a unit collapses the stacked roster again (re-picking the open unit does not re-render, so collapse here too).
    listEl.addEventListener("click", (e) => { if (e.target.closest("a")) setRoster(false); });
    listEl.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      const links = [...listEl.querySelectorAll("a")];
      const i = links.indexOf(document.activeElement);
      if (i < 0) return;
      e.preventDefault();
      if (e.key === "ArrowUp" && i === 0) { search.focus(); return; }
      links[Math.max(0, Math.min(links.length - 1, i + (e.key === "ArrowDown" ? 1 : -1)))].focus();
    });
    fill();
    const outside = selected && !pool.includes(selected)
      ? el("p", { class: "panel-note", role: "note" }, badge("outside filter", "warn"), ` This unit is not tied to ${nationScopeText(m)}. `,
        el("a", { href: routeNation(N_ALL, "p", slug, "units", selected.id ?? selected.uid) }, "Show all nations"))
      : null;
    // Below 1100px the roster stacks above the sheet; with a unit selected it starts collapsed so the sheet comes first.
    const rosterOpen = !selected || state.rosterOpen;
    const roster = el("div", { class: "roster-body", id: "unit-roster" },
      createButtons(m, "unit", selected && selected.new && Number.isInteger(selected.id) ? selected.id : null),
      el("div", { class: "unit-filter" }, search, roleSel), status, listEl);
    const rosterBtn = selected ? el("button", { type: "button", class: "btn btn-small roster-toggle", "aria-controls": "unit-roster",
      "aria-expanded": rosterOpen ? "true" : "false", onclick: () => setRoster(!state.rosterOpen) }, rosterOpen ? "Hide unit list" : `Show unit list (${pool.length})`) : null;
    function setRoster(open) {
      state.rosterOpen = open;
      if (!rosterBtn) return;
      rosterBtn.setAttribute("aria-expanded", open ? "true" : "false");
      left.classList.toggle("roster-collapsed", !open);
      rosterBtn.textContent = open ? "Hide unit list" : `Show unit list (${pool.length})`;
    }
    const left = el("div", { class: "unit-pane" + (rosterOpen ? "" : " roster-collapsed") }, rosterBtn, outside, roster);
    const right = selected && sub === "compare" ? compareView(m, selected) : selected ? unitDetail(m, selected) : stateBox("empty", "Select a unit.");
    return el("div", { class: "split" }, left, el("div", { id: "unit-detail" }, right));
  }

  function fieldCell(slug, file, f, donorRaw) {
    if (!f) return [unresolved(), ""];
    const val = f.value === null || f.value === undefined ? unresolved(f.note || "unresolved") : el("strong", { text: f.value });
    let src;
    if (f.source === "authored") src = el("span", null, badge("authored", "authored"), " ", srcRef(slug, file, f.line));
    else if (f.source === "donor") src = el("span", null, badge("donor", "copper"), " ", srcRef(slug, file, f.line));
    else src = badge(f.source.replace(/_/g, " "), "warn");
    const inherited = f.source === "authored" && donorRaw !== undefined && donorRaw !== null ? el("span", { class: "faint", text: ` (donor ${donorRaw})` }) : null;
    return [el("span", null, val, inherited), src];
  }
  const STAT_LABELS = { hp: "Hit points", prot: "Natural protection", mr: "Magic resistance", mor: "Morale", str: "Strength", att: "Base attack", def: "Base defence", prec: "Base precision", enc: "Base encumbrance", mapmove: "Map move", ap: "Combat speed (AP)", size: "Size" };

  // ---------- game-style unit sheet ----------
  // Compact labels in the order of the in-game unit information sheet; stats are base (unequipped) values.
  const SHEET_COLS = [
    [["hp", "Hit points"], ["size", "Size"], ["prot", "Protection"], ["mr", "Magic res"], ["mor", "Morale"], ["leader", "Leadership"]],
    [["str", "Strength"], ["att", "Attack skill"], ["def", "Defence skill"], ["prec", "Precision"], ["ap", "Combat speed"], ["enc", "Encumbrance"]],
  ];
  const ABILITY_LABELS = { holy: "sacred", stealthy: "stealth", float: "floating", pooramphibian: "poor amphibian", animalawe: "animal awe",
    iceprot: "ice protection", neednoteat: "does not eat", formationfighter: "formation fighter", fixforgebonus: "fixed forge bonus",
    mastersmith: "master smith", castledef: "castle defence", taskmaster: "task master", invulnerable: "invulnerability",
    snowmove: "snow move", fireshield: "fire shield", magicbeing: "magic being", stonebeing: "stone being", coldblood: "cold-blooded",
    mind: "mindless", spiritsight: "spirit sight", moremagic: "magic scale", alchemy: "alchemist" };
  const FLAG_ABILITIES = new Set(["holy", "flying", "float", "amphibian", "pooramphibian", "ethereal", "trample", "inquisitor", "undisciplined",
    "teleport", "spy", "assassin", "neednoteat", "darkvision", "bodyguard", "skirmisher", "snowmove", "standard", "heal", "spiritsight",
    "undead", "demon", "inanimate", "magicbeing", "stonebeing", "animal", "coldblood", "female", "mind", "aquatic", "immobile", "slave"]);
  function abilityLabel(k, v) {
    const name = ABILITY_LABELS[k] || k.replace(/(res|survival|power|bonus|cloud|awe)$/, " $1").replace(/ res$/, " resistance").trim();
    return FLAG_ABILITIES.has(k) && (String(v) === "1" || v === true) ? name : `${name} ${txt(v)}`;
  }
  const PATH_NAMES = { F: "Fire", A: "Air", W: "Water", E: "Earth", S: "Astral", D: "Death", N: "Nature", G: "Glamour", B: "Blood", H: "Holy" };
  const PATH_OF_NUMBER = (n) => (Number.isInteger(Number(n)) && Number(n) >= 0 && Number(n) <= 9 ? PATH_KEYS[Number(n)] : null);
  // Decorative path marker. kind "gem" (amounts) uses the native gem icon; skill and requirements use the native
  // path icon, then the gem icon; otherwise the CSS-drawn letter disc. onLetter runs if the art falls back later.
  function pathIcon(p, kind, onLetter) {
    const letter = () => (p === "U" ? null : el("span", { class: `path-ic path-${p}`, "aria-hidden": "true", text: p }));
    const ic = kind === "gem" ? gemIcons.get(p) : skillIcons.get(p) || gemIcons.get(p);
    if (!ic) return letter();
    const img = el("img", { class: ic.cls, src: ic.url, alt: "", width: ic.width, height: ic.height, decoding: "async", draggable: "false", "aria-hidden": "true" });
    img.addEventListener("error", () => { const l = letter(); if (l) img.replaceWith(l); else img.remove(); if (onLetter) onLetter(); }, { once: true });
    return img;
  }
  // Path marker and level; the full name is announced and shown in the tooltip. Letters are a missing-art fallback.
  function pathChip(p, level, mod, title) {
    return el("span", { class: "mpath" + (mod ? " mod" : ""), title: title || `${PATH_NAMES[p] || p} ${level}` },
      pathIcon(p, "path"), el("span", { class: "sr-only", text: `${PATH_NAMES[p] || p} ` }), txt(level));
  }
  // Path icon beside its full visible name, with an optional suffix such as a level ("Fire 2").
  const pathNamed = (p, suffix) => el("span", { class: "mpath mpath-named" }, pathIcon(p), el("span", { text: `${PATH_NAMES[p] || p}${suffix ?? ""}` }));
  // Gem amount: number, native gem icon and visible path name ("3 [gem] Fire"); unit words stay with the caller.
  const gemChip = (p, amount, suffix) => el("span", { class: "mpath mpath-named gem-amt", title: `${txt(amount)} ${PATH_NAMES[p] || p} gem${Number(amount) === 1 ? "" : "s"}` },
    el("span", { text: txt(amount) }), pathIcon(p, "gem"), el("span", { text: `${PATH_NAMES[p] || p}${suffix ?? ""}` }));
  const gemList = (gems, none) => (gems || []).length ? gems.map((g, i) => [i ? ", " : "", gemChip(g.path, g.amount)]) : (none ?? "none");
  const joinParts = (xs, sep = " · ") => xs.map((x, i) => [i ? sep : "", x]);
  // Random magic marker: the catalog's random-path icon before the written text, which stays the label.
  const randomMark = () => pathIcon("U");
  // One "label: value" stat. Values set by this .dm are marked; the line is in the tooltip.
  function sheetStat(label, f, opts = {}) {
    const has = f && f.value !== null && f.value !== undefined;
    const mod = f && f.source === "authored";
    const where = !f ? "not available" : mod ? `set in this .dm${f.line ? ` (line ${f.line})` : ""}` : f.source === "donor" ? `from donor${f.line ? ` (#copystats line ${f.line})` : ""}` : txt(f.source).replace(/_/g, " ");
    const shown = opts.text !== undefined ? opts.text : has ? (Array.isArray(f.value) ? f.value.join(", ") || "none" : txt(f.value)) : "?";
    return [el("dt", null, statIcon(opts.stat || statKeyOf(label)), label + (opts.mark || "")),
      el("dd", { class: [mod ? "mod" : "", has || opts.text !== undefined ? "" : "unknown"].join(" ").trim() || null, title: [where, f && f.note, opts.note].filter(Boolean).join(". ") },
        shown, mod ? el("span", { class: "sr-only", text: " (set in this mod)" }) : null)];
  }
  // Sprite at native size on a neutral backdrop; the attack frame and a crisp zoom are optional.
  function sheetFigure(name, frames) {
    const fig = el("figure", { class: "sheet-figure" });
    const idle = frames.idle, atk = frames.attack;
    if (!idle && !atk) { fig.append(el("div", { class: "sheet-stage" }, el("div", { class: "preview-missing", text: "no sprite" }))); return fig; }
    const imgs = [];
    const mk = (fr, label) => {
      if (!fr) return null;
      const img = spriteImg(fr.url, `${name} ${label} sprite`, state.sheetZoom, el("div", { class: "preview-missing", text: fr.missing || "sprite unavailable" }));
      imgs.push(img); return img;
    };
    const idleImg = mk(idle, "idle"), atkImg = mk(atk, "attack");
    const stage = el("div", { class: "sheet-stage" }, idleImg, atkImg);
    let attack = !idle;
    const cap = el("figcaption", { class: "sheet-cap" });
    const sync = () => {
      if (idleImg) idleImg.hidden = attack;
      if (atkImg) atkImg.hidden = !attack;
      atkBtn.setAttribute("aria-pressed", attack ? "true" : "false");
      cap.textContent = `${attack ? "Attack" : "Idle"} frame · ${state.sheetZoom === 1 ? "native size" : `${state.sheetZoom}x zoom`}`;
    };
    const atkBtn = el("button", { type: "button", class: "btn btn-small", disabled: !idle || !atk, title: !atk ? "No attack sprite" : null,
      onclick: () => { attack = !attack; sync(); } }, "Attack frame");
    const zoom = el("div", { class: "btn-row seg", role: "group", "aria-label": "Sprite zoom" }, [1, 2, 3].map((s) =>
      el("button", { type: "button", class: "btn btn-small", "aria-pressed": state.sheetZoom === s ? "true" : "false", onclick: (e) => {
        state.sheetZoom = s;
        for (const b of zoom.children) b.setAttribute("aria-pressed", b === e.currentTarget ? "true" : "false");
        for (const img of imgs) if (img.naturalWidth) { img.width = img.naturalWidth * s; img.height = img.naturalHeight * s; }
        sync();
      } }, `${s}x`)));
    stage.addEventListener("click", () => { if (idle && atk) { attack = !attack; sync(); } });
    stage.title = idle && atk ? "Click to toggle the attack frame" : "";
    sync();
    fig.append(stage, cap, el("div", { class: "btn-row sheet-tools" }, atkBtn, zoom));
    return fig;
  }
  function sheetGear(list, kind, status) {
    if (status && status.status === "unresolved") return el("p", { class: "sheet-line" }, badge(`${kind} list unresolved`, "warn"), " ", el("span", { class: "muted", text: status.note }));
    if (!list || !list.length) return null;
    return el("table", { class: "sheet-gear" },
      el("thead", null, el("tr", null, el("th", { scope: "col", text: kind }), el("th", { scope: "col", class: "num", text: "Id" }))),
      el("tbody", null, list.map((x) => el("tr", null,
        el("td", { class: x.source === "authored" ? "mod" : null, title: x.source === "authored" ? `set in this .dm${x.line ? ` (line ${x.line})` : ""}` : "from donor" },
          x.name ? txt(x.name) : unresolved(x.unresolved || "unknown")),
        el("td", { class: "num", text: txt(x.id ?? x.ref) })))));
  }
  function sheetAbilities(entries) {
    if (!entries.length) return null;
    return el("p", { class: "sheet-abilities" }, "(", entries.map(([k, f], i) => [i ? ", " : "",
      el("span", { class: f.source === "authored" ? "mod" : null, title: `#${k}${f.source === "authored" && f.line ? ` set on line ${f.line}` : ""}` }, traitIcon(k, f.value), abilityLabel(k, f.value))]), ")");
  }
  function sheetMagic(paths, random) {
    const keys = Object.keys(paths || {});
    if (!keys.length && !(random || []).length) return null;
    return el("p", { class: "sheet-line" }, el("span", { class: "sheet-k", text: "Magic paths:" }), " ",
      keys.map((p) => [pathChip(p, paths[p].value ?? paths[p].level, paths[p].source === "authored"), " "]),
      (random || []).map((x) => el("span", { class: "path-rand" + (x.source === "authored" ? " mod" : ""), title: `Random pick, mask ${x.mask}; probabilities not expanded` },
        randomMark(), `+${txt(x.levels ?? "?")} random ${x.paths.join("/")}${x.chance !== 100 ? ` (${x.chance}%)` : ""} `)));
  }
  function costText(f) {
    if (!f || f.authored_value === null || f.authored_value === undefined) return "—";
    if (f.interpretation === "autocalc_encoded") return `auto${f.base >= 0 ? "+" : ""}${f.base}`;
    if ((f.command === "#rpcost" || f.column === "rpcost") && f.authored_value >= 1000) return "auto";
    return String(f.authored_value);
  }
  // The whole parchment sheet. `cols` is a list of columns of [label, field, opts] stats.
  function unitSheet(o) {
    return el("section", { class: "unit-sheet", "aria-labelledby": "unit-title" },
      el("header", { class: "sheet-head" },
        el("div", { class: "sheet-title" }, el("h2", { id: "unit-title", tabindex: "-1", text: o.name }), el("span", { class: "sheet-type", text: o.type })),
        el("div", { class: "sheet-sub" }, o.sub)),
      el("div", { class: "sheet-body" },
        el("div", { class: "sheet-main" },
          el("div", { class: "sheet-stats" }, o.cols.map((col) => el("dl", null, col.map(([label, f, opts]) => sheetStat(label, f, opts))))),
          o.gear, o.abilities, o.magic, o.lines),
        o.figure),
      el("p", { class: "sheet-note", text: o.note }),
      o.description ? el("div", { class: "sheet-descr" }, el("p", { text: o.description })) : null,
      o.foot ? el("footer", { class: "sheet-foot" }, o.foot) : null);
  }
  // A closed-by-default technical section below the sheet.
  const techSection = (title, open, ...kids) => el("details", { class: "raw tech", open: open || null }, el("summary", null, title), el("div", { class: "inner stack" }, kids));
  // The old large transparency-grid frames, kept as optional artwork inspection.
  function artworkSection(frames) {
    const imgs = [];
    const scaleBtns = el("div", { class: "btn-row seg", role: "group", "aria-label": "Artwork scale" }, [1, 2, 3, 4].map((s) =>
      el("button", { type: "button", class: "btn btn-small", "aria-pressed": state.scale === s ? "true" : "false", onclick: (e) => {
        state.scale = s;
        for (const b of scaleBtns.children) b.setAttribute("aria-pressed", b === e.currentTarget ? "true" : "false");
        for (const img of imgs) if (img.naturalWidth) { img.width = img.naturalWidth * s; img.height = img.naturalHeight * s; img.title = `${img.naturalWidth}x${img.naturalHeight} px shown at ${s}x`; }
      } }, `${s}x`)));
    const frame = (fr) => {
      const img = fr.url ? spriteImg(fr.url, fr.alt, state.scale, el("div", { class: "preview-missing", text: "Preview unavailable" })) : null;
      if (img) imgs.push(img);
      return el("div", { class: "sprite-frame" },
        el("div", { class: "sprite-box" }, img || el("div", { class: "preview-missing", text: fr.missing || "no sprite command" })),
        el("div", { class: "cap" }, fr.label, fr.path ? [el("br"), el("code", { text: fr.path })] : null, fr.origin ? el("div", { class: "faint", text: fr.origin }) : null));
    };
    return techSection("Enlarged sprites", false,
      el("div", { class: "sprites" }, frames.map(frame)),
      el("div", { class: "btn-row" }, el("span", { class: "muted", text: "Enlarged view:" }), scaleBtns,
        el("span", { class: "faint", text: "Pixelated scaling on a transparency grid, for checking edges and alpha." })));
  }

  // ---------- relationships, identity and compatibility (all optional in the model) ----------
  // Only definitions from this project's .dm link anywhere; dependency and vanilla entries are plain text with their origin.
  const isLocal = (origin) => origin === null || origin === undefined || ["project", "local"].includes(String(origin).toLowerCase());
  const asText = (w) => (w !== null && typeof w === "object" ? txt(w.message || w.reason || w.label || JSON.stringify(w)) : txt(w));
  // Catalog targets ("catalog:<context>:<id>") are not graph objects; their names come from entries the model already
  // carries (enriched uses/used_by of definitions, or this object's catalog template).
  const relCatalogNames = new WeakMap();
  function relCatalogEntry(m, key) {
    if (!relCatalogNames.has(m)) {
      const names = new Map();
      for (const o of [...(m.monsters || []), ...(m.sites || []), ...(m.nations || []), ...(m.other_definitions || [])])
        for (const e of [...(o.uses || []), ...(o.used_by || [])]) if (e && e.key && e.name && !names.has(e.key)) names.set(e.key, e);
      relCatalogNames.set(m, names);
    }
    return relCatalogNames.get(m).get(key);
  }
  // used_by / uses for one definition: from the object itself, else derived from m.relationships by context and id (or line).
  // Derived entries keep src_origin, the file their source line belongs to (the referring definition), apart from origin.
  function relOf(m, obj, ctx) {
    if (!obj) return null;
    const enriched = Array.isArray(obj.used_by) || Array.isArray(obj.uses);
    const R = m.relationships;
    if (!R || !Array.isArray(R.objects)) return enriched ? { used_by: obj.used_by || [], uses: obj.uses || [], ctx } : null;
    const line = obj.source ? obj.source.line : obj.line, has = (v) => v !== null && v !== undefined;
    const me = R.objects.find((o) => o.context === ctx && ((has(o.id) && has(obj.id) && String(o.id) === String(obj.id)) || (line && o.line === line && isLocal(o.origin))));
    if (!me) return { used_by: obj.used_by || [], uses: obj.uses || [], ctx };
    const byKey = new Map(R.objects.map((o) => [o.key, o]));
    const tp = obj.template || {};
    const target = (k, e) => {
      if (byKey.has(k)) return byKey.get(k);
      const cat = k && /^catalog:([^:]+):(.+)$/.exec(k);
      if (cat) {
        const id = /^-?\d+$/.test(cat[2]) ? Number(cat[2]) : cat[2], known = relCatalogEntry(m, k);
        const name = (known && known.name) || (tp.source === "catalog" && cat[1] === ctx && String(tp.id) === String(id) ? tp.name : null);
        return { key: k, context: cat[1], id, name: name || null, origin: "catalog" };
      }
      // Unresolved (to: null): keep the written argument and the expected kind.
      if (!k) return { key: null, context: e.target_context || null, id: Number.isInteger(e.argument) ? e.argument : null,
        name: has(e.argument) && !Number.isInteger(e.argument) ? String(e.argument) : null, origin: null };
      return { key: k };
    };
    const ent = (k, e, srcOrigin) => { const t = target(k, e);
      return { ...t, command: e.command, relation: e.relation, line: e.line ?? t.line, status: e.status, target_context: e.target_context, src_origin: srcOrigin }; };
    const derived = { ctx, used_by: (R.edges || []).filter((e) => e.to === me.key).map((e) => ent(e.from, e, (byKey.get(e.from) || {}).origin)),
      uses: (R.edges || []).filter((e) => e.from === me.key).map((e) => ent(e.to, e, me.origin)) };
    if (!enriched) return derived;
    // Preserve enriched names and inherited equipment, but take reference lines and source files from graph edges.
    for (const direction of ["used_by", "uses"]) {
      const supplied = obj[direction] || [], edges = derived[direction];
      derived[direction] = supplied.map((entry) => {
        const edge = edges.find((e) => e.key === entry.key && e.command === entry.command);
        return edge ? { ...entry, line: edge.line, src_origin: edge.src_origin, target_context: edge.target_context, status: edge.status }
          : { ...entry, source_is_definition: true };
      });
      for (const edge of edges) if (!supplied.some((e) => e.key === edge.key && e.command === edge.command)) derived[direction].push(edge);
    }
    return derived;
  }
  const relNoun = (ctx) => REL_NOUN[ctx] || txt(ctx) || "definition";
  const relOriginText = (o) => o === "catalog" ? "the vanilla catalog" : txt(o);
  function relLink(m, e) {
    const slug = m.project.slug, hasId = e.id !== null && e.id !== undefined, noun = relNoun(e.context);
    const label = e.name ? `${txt(e.name)}${hasId ? ` (#${e.id})` : ""}`
      : hasId ? `${noun.charAt(0).toUpperCase()}${noun.slice(1)} #${e.id}` : txt(e.key || "unknown");
    if (!isLocal(e.origin) || !e.key) return el("span", { text: label });
    if (e.context === "monster" && m.monsters.some((u) => u.id !== null && String(u.id) === String(e.id))) return el("a", { href: route("p", slug, "units", e.id) }, label);
    if (e.context === "site" && m.sites.some((s) => s.id !== null && String(s.id) === String(e.id))) return el("a", { href: route("p", slug, "sites", e.id) }, label);
    if (e.context === "nation" && e.id !== null && e.id !== undefined) return el("a", { href: route("p", slug, "nation", e.id) }, label);
    if (e.key && CMD_CONTEXTS.some((c) => c[0] === e.context)) return el("a", { href: cmdRoute(slug, e.context, e.key) }, label);
    return el("span", { text: label });
  }
  // What a reference means, as [phrase when the other entry uses this one, phrase when this one uses the other].
  const REL_NOUN = { monster: "unit", armor: "armour", merc: "mercenary company" };
  // tctx is the context of the referenced side; #damage only summons when that side is a unit (summon spells).
  function relPhrase(e, tctx = e.target_context || e.context) {
    const c = String(e.command || "").replace(/^#/, "").toLowerCase(), rel = String(e.relation || "");
    if (rel === "effective inherited equipment reference") return ["has this as inherited equipment", "has as inherited equipment"];
    if (rel === "event code requirement") return ["is linked to this by an event code", "is linked by an event code to"];
    if (c === "copystats") return ["copies stats from this", "copies stats from"];
    if (c === "copyspr") return ["copies the sprite of this", "copies the sprite of"];
    if (c.startsWith("copy")) return ["copies this", "copies"];
    if (/rec(unit|com)|^addrec|^forcerec/.test(c)) return ["recruits this", "recruits"];
    if (/summon|makemonster/.test(c) || (c === "damage" && tctx === "monster")) return ["summons this", "summons"];
    if (/^start(com|unit|scout)/.test(c)) return ["starts with this", "starts with"];
    if (c.includes("hero")) return ["has this as a hero", "has as a hero"];
    if (c === "addgod") return ["offers this as a pretender", "offers as a pretender"];
    if (c === "startsite" || c === "newsite") return ["has this as a start site", "has as a start site"];
    if (c === "weapon") return ["is armed with this", "is armed with"];
    if (c === "armor") return ["wears this", "wears"];
    return ["refers to this", "refers to"];
  }
  // Related content: plain sentences about what refers to this entry and what it refers to. Collapsed by default; the raw
  // commands, relations and source lines are in the nested Details table. Unresolved references and read-only dependency
  // entries stay flagged in the sentences and in the summary line.
  function usedBySection(m, rel) {
    if (!rel) return null;
    const ub = rel.used_by || [], us = rel.uses || [], n = ub.length + us.length;
    if (!n) return null;
    const all = [...ub, ...us];
    const flagged = (e) => e.status && e.status !== "resolved";
    const nFlag = all.filter(flagged).length, nDep = all.filter((e) => !isLocal(e.origin)).length;
    const who = (e) => [relLink(m, e), el("span", { class: "faint", text: ` (${relNoun(e.context)}${isLocal(e.origin) ? "" : `, from ${relOriginText(e.origin)}, read-only`})` })];
    const flag = (e) => flagged(e) ? [" ", badge(String(e.status).replace(/_/g, " "), "warn")] : null;
    // An incoming entry is the referring side; the referenced side is this page's own definition.
    const usedItem = (e) => el("li", null, who(e), ` ${relPhrase(e, e.target_context || rel.ctx)[0]}.`, flag(e));
    const usesItem = (e) => el("li", null, `This ${relPhrase(e)[1]} `, who(e), ".", flag(e));
    const list = (title, xs, item) => xs.length ? [el("h4", { text: `${title} (${xs.length})` }), el("ul", { class: "plain-list rel-list" }, xs.map(item))] : null;
    // A derived entry's line belongs to the referring definition (src_origin), not necessarily to the entry shown.
    const source = (e) => { const o = "src_origin" in e ? e.src_origin : e.origin;
      return isLocal(o) ? (e.line ? srcRef(m.project.slug, m.provenance.file, e.line, true) : el("span", { class: "faint", text: "—" }))
        : el("span", { class: "faint", text: `${relOriginText(o)}${e.line ? ` line ${e.line}` : ""} (read-only)${e.source_is_definition ? " · definition" : ""}` }); };
    const row = (dir) => (e) => [dir, relLink(m, e), e.command ? el("code", { text: e.command }) : el("span", { class: "faint", text: "—" }),
      el("span", { text: e.relation ? String(e.relation).replace(/_/g, " ") : "—" }), flagged(e) ? badge(String(e.status).replace(/_/g, " "), "warn") : el("span", { class: "faint", text: "resolved" }), source(e)];
    return el("details", { class: "raw tech used-by" },
      el("summary", null, "Related content", el("span", { class: "faint", text: ` · used by ${ub.length} · uses ${us.length}${nDep ? ` · ${nDep} read-only reference${nDep === 1 ? "" : "s"}` : ""}` }),
        nFlag ? [" ", badge(`${nFlag} unresolved`, "warn")] : null),
      el("div", { class: "inner stack" }, list("Used by", ub, usedItem), list("Uses", us, usesItem),
        techSection("Details: commands and source lines", false,
          table(["Direction", "Entry", "Command", "Relation", "Status", "Source"], [...ub.map(row("used by")), ...us.map(row("uses"))]))));
  }
  const IDENTITY_TEXT = { new: "new definition", vanilla_override: "overrides vanilla", dependency_override: "overrides a dependency", extension: "extends an existing definition" };
  // A plain new definition needs no note; overrides and extensions do.
  function identityNote(idn) {
    if (!idn || !idn.kind || idn.kind === "new") return null;
    return el("p", { class: "identity-note faint" }, "Definition: ", el("strong", { text: IDENTITY_TEXT[idn.kind] || String(idn.kind).replace(/_/g, " ") }),
      idn.origin ? ` · ${txt(idn.origin)}` : null, idn.note ? ` · ${txt(idn.note)}` : null);
  }
  // Overlap classes from resolution.py. Advice is shown, never applied: Kosmokrator does not remap ids or reorder by itself.
  const OVERLAP_CLASS = { hard_id_collision: ["Hard ID collision", "err"], intentional_selector_override: ["Intentional override", "info"],
    ambiguous_named_definition: ["Ambiguous named definition", "warn"] };
  const ACTION_TEXT = { remap_ids: "Reserve a new id (manual)", declare_dependency: "Declare the dependency", review_override: "Review the override",
    change_order: "Preview a different order", verify_reference: "Verify the reference" };
  const contribText = (x) => x ? `${txt(x.origin)}${x.line ? ` line ${x.line}` : ""}` : "?";
  const overlapKey = (o) => `${txt(o.context)}:${o.id !== null && o.id !== undefined ? o.id : txt(o.name).toLowerCase()}`;
  const overlapLabel = (o) => `${txt(o.name || "?")} (${txt(o.context)}${o.id !== null && o.id !== undefined ? ` #${o.id}` : ""})`;
  function actionList(actions) {
    return (actions || []).length ? el("ul", { class: "plain-list compat-actions" }, actions.map((a) => el("li", null,
      el("strong", { text: ACTION_TEXT[a.action] || String(a.action).replace(/_/g, " ") }), " ", badge(a.automatic ? "automatic" : "manual step", a.automatic ? "warn" : "info"),
      a.reason ? el("div", { class: "faint", text: txt(a.reason) }) : null))) : null;
  }
  function summaryBadges(sum) {
    if (!sum) return null;
    const kind = (k, v) => !v ? "ok" : /collision/.test(k) ? "err" : /intentional/.test(k) ? "info" : "warn";
    return el("ul", { class: "plain-list chips compat-summary", "aria-label": "Compatibility summary" },
      Object.entries(sum).map(([k, v]) => el("li", null, badge(`${txt(v)} ${k.replace(/_/g, " ")}`, kind(k, v)))));
  }
  function overlapCard(m, o) {
    const [label, kind] = OVERLAP_CLASS[o.classification] || [o.severity === "error" ? "Error" : txt(o.classification || o.severity || "overlap").replace(/_/g, " "), o.severity === "error" ? "err" : "warn"];
    const contribs = o.contributors || [];
    const winner = o.classification === "hard_id_collision" || o.blocked_by_collision
      ? el("span", null, badge("no safe winner", "err"), " ", el("span", { class: "faint", text: "Duplicate new ids: the result is not decided by order." }))
      : o.winner ? el("span", null, "Last selector: ", el("strong", { text: contribText(o.winner) }), el("span", { class: "faint", text: " (last authored contributor, not proof of the in-game result)" }))
      : o.last_contributor ? el("span", null, "Last contributor: ", el("strong", { text: contribText(o.last_contributor) })) : null;
    const effects = o.effects || [];
    return el("li", { class: "compat-overlap" },
      el("div", { class: "compat-head" }, el("strong", { text: overlapLabel(o) }), " ", badge(label, kind)),
      contribs.length ? el("p", { class: "compat-chain" }, "Contributors in order: ",
        contribs.map((x, i) => [i ? " → " : "", isLocal(x.origin) && x.line ? srcRef(m.project.slug, m.provenance.file, x.line) : el("span", { text: contribText(x) })]))
        : (o.origins || []).length ? el("p", { class: "compat-chain", text: `Origins: ${o.origins.map(asText).join(" → ")}` }) : null,
      winner ? el("p", null, winner) : null,
      o.reason ? el("p", { class: "faint", text: txt(o.reason) }) : null,
      effects.length ? el("details", { class: "compat-effects" }, el("summary", null, `Commands by contributor (${effects.length})`),
        table(["Command", "Contributors", "Last authored"], effects.map((e) => [el("code", { text: `#${txt(e.command).replace(/^#/, "")}` }),
          (e.contributors || []).map(contribText).join(", "), contribText(e.last_authored)])),
        effects[0] && effects[0].interpretation ? el("p", { class: "panel-note", text: txt(effects[0].interpretation) }) : null) : null,
      actionList(o.actions));
  }
  function compatibilitySection(m) {
    const c = m.compatibility, R = m.relationships;
    const order = (c && c.activation_order) || [], ov = (c && c.overlaps) || [], warns = (c && c.warnings) || [], lim = (c && c.limitations) || [];
    const unres = (R && R.unresolved) || [], guide = (c && c.guidance) || [];
    const edit = depEditor(m);
    if (!c && !(R && (R.unresolved || []).length)) return edit ? techSection("Dependencies and compatibility", false, edit) : null;
    const hard = ov.filter((o) => o.classification === "hard_id_collision").length;
    // Collisions first, then ambiguous names, then intentional overrides.
    const rank = (o) => o.classification === "hard_id_collision" ? 0 : o.classification === "intentional_selector_override" ? 2 : 1;
    return techSection(`Dependencies and compatibility (${order.length} in order · ${ov.length} overlap(s)${hard ? ` · ${hard} hard collision(s)` : ""} · ${warns.length + unres.length} uncertain)`, hard > 0,
      edit,
      c && c.summary ? summaryBadges(c.summary) : null,
      panel("Activation order",
        order.length ? el("ol", { class: "compat-order" }, order.map((o) => el("li", null, txt(o.label), " ",
          el("span", { class: "hash", title: o.sha256 ? `SHA-256 ${o.sha256}` : null, text: o.sha256 ? shortSha(o.sha256) : "no hash" }))))
          : el("p", { class: "muted", text: "No dependency order reported." }),
        el("p", { class: "panel-note", text: txt(c && c.order_basis) || "The order Kosmokrator assumes. The game's real mod order is chosen in Dominions." })),
      panel("Overlapping definitions",
        ov.length ? el("ul", { class: "plain-list compat-overlaps" }, [...ov].sort((a, b) => rank(a) - rank(b)).map((o) => overlapCard(m, o)))
          : el("p", { class: "muted", text: "No overlaps found." }),
        ov.length ? el("p", { class: "panel-note", text: "Advice only; nothing is remapped or reordered automatically." }) : null),
      guide.length ? panel(`References to check (${guide.length})`, el("ul", { class: "plain-list compat-overlaps" }, guide.map((g) => el("li", { class: "compat-overlap" },
        el("div", { class: "compat-head" }, el("code", { text: `#${txt(g.command).replace(/^#/, "")} ${txt(g.argument)}` }), " ",
          badge(txt(g.classification).replace(/_/g, " "), "warn"), " ",
          g.source && isLocal(g.source.origin) && g.line ? srcRef(m.project.slug, m.provenance.file, g.line) : el("span", { class: "faint", text: contribText(g.source || { line: g.line }) })),
        actionList(g.actions))))) : null,
      warns.length ? panel("Warnings", el("ul", null, warns.map((w) => el("li", { text: asText(w) })))) : null,
      unres.length && !guide.length ? panel(`Unresolved references (${unres.length})`, el("ul", null, unres.map((w) => el("li", { text: asText(w) })))) : null,
      lim.length ? panel("Limitations", el("ul", null, lim.map((w) => el("li", { text: asText(w) })))) : null);
  }
  // Predicted effect of a dependency reorder: the saved model's report beside the preview's candidate report.
  function reorderPrediction(before, after) {
    if (!after) return null;
    const sb = (before && before.summary) || {}, sa = after.summary || {};
    // The saved view has the catalog and the preview does not, so unresolved counts are not comparable.
    const keys = [...new Set([...Object.keys(sb), ...Object.keys(sa)])].filter((k) => k !== "unresolved_references");
    const rows = keys.map((k) => [k.replace(/_/g, " "), txt(sb[k] ?? "—"), txt(sa[k] ?? "—"),
      sb[k] === sa[k] ? el("span", { class: "faint", text: "same" })
        : badge((sa[k] || 0) > (sb[k] || 0) ? "more" : "fewer", /intentional/.test(k) ? "info" : (sa[k] || 0) > (sb[k] || 0) ? "warn" : "ok")]);
    const ob = new Map(((before && before.overlaps) || []).map((o) => [overlapKey(o), o])), oa = new Map((after.overlaps || []).map((o) => [overlapKey(o), o]));
    const changes = [];
    for (const [k, o] of oa) {
      const p = ob.get(k), last = o.last_contributor || o.winner, plast = p && (p.last_contributor || p.winner);
      if (o.classification === "hard_id_collision") changes.push([overlapLabel(o), badge("hard collision remains", "err"), "Reordering does not repair it; reserve a new id manually."]);
      else if (!p) changes.push([overlapLabel(o), badge("new overlap", "warn"), contribText(last)]);
      else if (plast && last && (plast.origin !== last.origin || plast.line !== last.line)) changes.push([overlapLabel(o), badge("last contributor changes", "info"), `${contribText(plast)} → ${contribText(last)}`]);
    }
    for (const [k, o] of ob) if (!oa.has(k) && o.classification !== "hard_id_collision") changes.push([overlapLabel(o), badge("no longer listed", "ok"), contribText(o.last_contributor || o.winner)]);
    return el("div", { class: "stack compat-predict" },
      el("h4", { text: "Predicted compatibility changes" }),
      keys.length ? table(["Count", "Saved", "After this order", ""], rows) : null,
      changes.length ? table(["Definition", "Change", "Detail"], changes) : el("p", { class: "muted", text: "No overlap would change its last contributor." }),
      sa.unresolved_references !== undefined ? el("p", { class: "faint", text: `${sa.unresolved_references} unresolved reference(s) in the preview (checked without the catalog).` }) : null,
      after.catalog_available === false ? el("p", { class: "panel-note", text: "The preview runs without the game catalog: collisions with vanilla ids and vanilla references are re-checked in the project view after saving." }) : null,
      el("p", { class: "panel-note", text: "Last contributor is the last authored block, not the in-game result." }));
  }

  // ---------- dependency settings (kosmokrator.json "dependencies", SHA-guarded) ----------
  // Collapsed until opened; nothing is fetched or written before that. The draft (dr.list) survives errors and stale-SHA reloads.
  function depDraft(slug) {
    if (!state.depDrafts.has(slug)) state.depDrafts.set(slug, { open: false, st: null, list: null, manual: "", addErr: "", phase: "edit", preview: null, msg: null });
    return state.depDrafts.get(slug);
  }
  function depEditor(m) {
    if (!CSRF) return null;
    const slug = m.project.slug, dr = depDraft(slug), url = `/api/projects/${encodeURIComponent(slug)}/dependencies`;
    const inner = el("div", { class: "inner stack", id: `dep-editor-${slug}` });
    const box = el("details", { class: "raw tech dep-editor", open: dr.open || null },
      el("summary", { "data-dep-summary": "" }, `Edit dependency settings (${(m.project.dependencies || []).length} listed)`), inner);
    const same = () => !!dr.st && JSON.stringify(dr.list) === JSON.stringify(dr.st.dependencies || []);
    const nameOf = (path) => { const o = ((dr.st && dr.st.options) || []).find((x) => x.path === path); return o ? txt(o.name) : null; };
    const load = async () => {
      inner.replaceChildren(stateBox("loading", "Reading project settings..."));
      try {
        dr.st = (await getJSON(url)).result;
        if (!dr.list) dr.list = [...(dr.st.dependencies || [])];
        draw();
      } catch (e) {
        inner.replaceChildren(errorBox(e, "dependency settings"), el("div", { class: "btn-row" }, el("button", { type: "button", class: "btn btn-small", onclick: load }, "Retry")));
      }
    };
    // Re-read the settings SHA but keep the draft list.
    const reload = () => { dr.st = null; dr.msg = null; dr.preview = null; dr.phase = "edit"; load(); };
    const edited = (focus) => { dr.msg = null; dr.preview = null; dr.phase = "edit"; draw(focus); };
    function add(path, focus) {
      const p = String(path || "").trim();
      dr.addErr = !p ? "Choose or enter a .dm path."
        : !/\.dm$/i.test(p) ? "The path must end in .dm."
        : /^([a-zA-Z]:|[\\/])/.test(p) || p.includes("\\") || p.split("/").includes("..") ? "Use a workspace-relative path with forward slashes, e.g. othermod/othermod.dm."
        : dr.list.includes(p) ? "Already in the list." : dr.list.length >= 32 ? "At most 32 dependencies." : "";
      if (dr.addErr) { draw(focus); return false; }
      dr.list.push(p);
      return true;
    }
    function move(i, d) {
      const j = i + d;
      [dr.list[i], dr.list[j]] = [dr.list[j], dr.list[i]];
      const dir = d < 0 ? "up" : "down", other = d < 0 ? "down" : "up";
      const edge = j === 0 || j === dr.list.length - 1;
      edited(`[data-dep="${edge ? other : dir}-${j}"]`);
    }
    async function send(preview) {
      dr.msg = { kind: "busy", text: preview ? "Checking..." : "Saving..." }; draw();
      try {
        const r = await postJSON(url, { expected_sha256: dr.st.sha256, preview, dependencies: [...dr.list] });
        if (preview) { dr.preview = r; dr.phase = "review"; dr.msg = null; draw("[data-focus=review]"); return; }
        state.depDrafts.delete(slug);
        const fresh = depDraft(slug);
        fresh.open = true;
        fresh.msg = { kind: "ok", text: r.written ? `Saved kosmokrator.json.${r.backup ? ` Backup: ${r.backup}` : ""}` : "Nothing changed." };
        state.models.delete(slug);
        recordReceipt(slug, "Saved dependency settings", r, { file: r.file || "kosmokrator.json" });
        toast(r.written ? "Dependency settings saved" : "Nothing to save");
        await loadProjects(true);
        render().then(() => { const sm = $("[data-dep-summary]"); if (sm) sm.focus(); });
      } catch (e) { dr.phase = "edit"; dr.msg = { kind: "err", err: e }; draw("[data-focus=err]"); }
    }
    function listView() {
      const n = dr.list.length;
      const items = dr.list.map((path, i) => {
        const nm = nameOf(path), label = nm || path;
        return el("li", { class: "dep-item" },
          el("span", { class: "dep-name" }, nm ? el("strong", { text: nm }) : null, nm ? " " : null, el("code", { text: path }),
            nm ? null : [" ", badge("manual path", "info")]),
          el("span", { class: "dep-actions" },
            el("button", { type: "button", class: "btn btn-small btn-ghost", "data-dep": `up-${i}`, disabled: i === 0 || null, "aria-label": `Move ${label} up`, onclick: () => move(i, -1) }, "Up"),
            el("button", { type: "button", class: "btn btn-small btn-ghost", "data-dep": `down-${i}`, disabled: i === n - 1 || null, "aria-label": `Move ${label} down`, onclick: () => move(i, 1) }, "Down"),
            el("button", { type: "button", class: "btn btn-small btn-ghost", "data-dep": `rm-${i}`, "aria-label": `Remove ${label}`,
              onclick: () => { dr.list.splice(i, 1); edited(n > 1 ? `[data-dep="rm-${Math.min(i, n - 2)}"]` : "#dep-pick"); } }, "Remove")));
      });
      items.push(el("li", { class: "dep-item dep-self" },
        el("span", { class: "dep-name" }, el("strong", { text: txt(m.project.name || slug) }), " ", badge("this project · activates last", "copper"))));
      return el("ol", { class: "compat-order dep-list", "aria-label": "Activation order (first activates first)" }, items);
    }
    function addRow() {
      const free = (dr.st.options || []).filter((o) => !dr.list.includes(o.path));
      const pick = el("select", { class: "input", id: "dep-pick", disabled: !free.length || null },
        el("option", { value: "", text: free.length ? "Choose an imported project…" : "No other imported projects" }),
        free.map((o) => el("option", { value: o.path, text: `${txt(o.name)} (${o.path})` })));
      const manual = el("input", { class: "input", id: "dep-manual", type: "text", autocomplete: "off", spellcheck: "false", placeholder: "folder/mod.dm",
        value: dr.manual, "aria-describedby": "dep-add-err", "aria-invalid": dr.addErr ? "true" : null });
      manual.addEventListener("input", () => { dr.manual = manual.value; });
      const addManual = () => { if (add(manual.value, "#dep-manual")) { dr.manual = ""; dr.addErr = ""; edited("#dep-manual"); } };
      manual.addEventListener("keydown", (ev) => { if (ev.key === "Enter") { ev.preventDefault(); addManual(); } });
      return el("div", { class: "dep-add" },
        el("div", { class: "edit-field" }, el("label", { for: "dep-pick", text: "Add an imported project" }),
          el("div", { class: "edit-control" }, pick,
            el("button", { type: "button", class: "btn btn-small", disabled: !free.length || null,
              onclick: () => { if (add(pick.value, "#dep-pick")) { dr.addErr = ""; edited("#dep-pick"); } } }, "Add"))),
        el("div", { class: "edit-field" }, el("label", { for: "dep-manual", text: "Or a workspace .dm path" }),
          el("div", { class: "edit-control" }, manual, el("button", { type: "button", class: "btn btn-small", onclick: addManual }, "Add path"))),
        el("div", { class: "field-err", id: "dep-add-err", role: "alert", text: dr.addErr }));
    }
    function draw(focus) {
      if (!dr.st) { load(); return; }
      const ch = !same(), busy = dr.msg && dr.msg.kind === "busy";
      const msg = !dr.msg ? null : dr.msg.kind === "err" ? writeError(dr.msg.err, reload)
        : el("p", { class: dr.msg.kind === "ok" ? "edit-ok" : "faint", role: "status", text: dr.msg.text });
      let body;
      if (dr.phase === "review" && dr.preview) {
        const r = dr.preview, none = !(r.changes || []).length;
        body = el("div", { class: "stack" },
          el("h4", { tabindex: "-1", "data-focus": "review", text: "Review before saving" }),
          (r.warnings || []).length ? el("ul", { class: "diag" }, r.warnings.map((w) => el("li", null, badge("check", "warn"), " ", asText(w)))) : null,
          none ? el("p", { class: "muted", text: "The saved settings already match this list; nothing would change." }) : diffView(r.diff || "", "Exact change to kosmokrator.json (diff)"),
          none ? null : reorderPrediction(m.compatibility, r.compatibility),
          el("p", { class: "panel-note", text: "Writes the project settings only, with a backup. No .dm is changed." }),
          el("div", { class: "btn-row" },
            none ? null : el("button", { type: "button", class: "btn", disabled: busy || null, onclick: () => send(false) }, "Save dependency settings"),
            el("button", { type: "button", class: none ? "btn" : "btn btn-ghost", disabled: busy || null, onclick: () => edited("[data-dep-preview]") }, "Back to the list")));
      } else {
        body = el("div", { class: "stack" }, listView(), addRow(),
          el("div", { class: "btn-row" },
            el("button", { type: "button", class: "btn", "data-dep-preview": "", disabled: !ch || busy || null, onclick: () => send(true) }, "Preview change"),
            ch ? el("button", { type: "button", class: "btn btn-ghost", disabled: busy || null,
              onclick: () => { dr.list = [...(dr.st.dependencies || [])]; dr.addErr = ""; edited("[data-dep-preview]"); } }, "Discard draft") : null,
            el("span", { class: "edit-count", role: "status", text: ch ? "Unsaved changes" : "Matches the saved settings" })));
      }
      inner.replaceChildren(...[
        el("p", { class: "panel-note", text: txt(dr.st.note) }),
        msg, body,
      ].filter(Boolean));
      if (focus) { const f = inner.querySelector(focus); if (f) f.focus(); }
    }
    escapeReview(inner, () => dr.phase === "review" && !(dr.msg && dr.msg.kind === "busy"), () => edited("[data-dep-preview]"));
    box.addEventListener("toggle", () => { dr.open = box.open; if (box.open && !inner.childNodes.length) draw(); });
    if (dr.open) draw();
    return box;
  }

  // ---------- equipped values (r.equipped, optional) ----------
  // Resolved values replace the base stat; estimates are marked "≈"; anything else keeps the base, labelled "(base)".
  // null / unresolved never becomes 0.
  const eqVal = (e) => !!e && (e.status === "resolved" || e.status === "estimated") && e.value !== null && e.value !== undefined;
  function eqCell(label, e, base, baseOpts) {
    if (eqVal(e)) {
      const est = e.status === "estimated";
      return [label, { value: e.value, source: est ? "estimated" : "with equipment" },
        { text: `${est ? "≈" : ""}${e.value}`, note: [est ? "Estimated, not exact" : "With equipment", e.note].filter(Boolean).join(". ") }];
    }
    return [`${label} (base)`, base, { ...(baseOpts || {}), note: [e ? `Equipped value ${txt(e.status || "unresolved").replace(/_/g, " ")}` : "No equipped value", e && e.note, baseOpts && baseOpts.note].filter(Boolean).join(". ") }];
  }
  function equippedStat(k, label, base, eq) {
    if (k === "prot") { const p = eq.protection || {}; return eqCell(label, { status: p.status, value: p.average ?? p.body, note: p.note }, base); }
    if (k === "def") return eqCell(label, eq.defence, base);
    if (k === "enc") return eqCell(label, eq.encumbrance, base);
    if (k === "att") {
      const atk = eq.attack || [];
      if (atk.length === 1) return eqCell(label, atk[0], base);
      return [`${label} (base)`, base, { note: atk.length ? "Varies by weapon; see Attack by weapon" : "No per-weapon attack reported" }];
    }
    return [label, base];
  }
  const eqShow = (e) => !e || e.value === null || e.value === undefined ? "?" : e.status === "estimated" ? `≈${e.value}` : e.status === "resolved" ? txt(e.value) : "?";
  function equippedLines(eq) {
    const v = (x) => (x === null || x === undefined ? "?" : txt(x));
    const p = eq.protection, atk = eq.attack || [], out = [];
    const flag = (s) => s && s !== "resolved" ? ` (${String(s).replace(/_/g, " ")})` : "";
    if (p && [p.body, p.head, p.average].some((x) => x !== null && x !== undefined))
      out.push(el("p", { class: "sheet-line", title: txt(p.note) || null }, el("span", { class: "sheet-k" }, statIcon("prot"), "Protection:"),
        ` body ${v(p.body)} · head ${v(p.head)}${p.average !== null && p.average !== undefined ? ` · average ${p.average}` : ""}${flag(p.status)}`));
    if (atk.length > 1 || (atk.length === 1 && !eqVal(atk[0])))
      out.push(el("p", { class: "sheet-line" }, el("span", { class: "sheet-k" }, statIcon("att"), "Attack by weapon:"), " ",
        atk.map((a, i) => [i ? " · " : "", el("span", { title: [a.status, a.note].filter(Boolean).join(": ") || null, text: `${txt(a.name || "?")} ${eqShow(a)}` })])));
    if ((eq.mounts || []).length) out.push(el("p", { class: "sheet-line" }, el("span", { class: "sheet-k", text: "Mount:" }), " ",
      eq.mounts.map((x, i) => [i ? ", " : "", el("span", { title: [x.origin, x.note].filter(Boolean).join(". ") || null, text: `${txt(x.name || "?")}${x.id !== null && x.id !== undefined ? ` (#${x.id})` : ""}${flag(x.status)}` })])));
    if ((eq.shapes || []).length) out.push(el("p", { class: "sheet-line" }, el("span", { class: "sheet-k", text: "Shapes:" }), " ",
      eq.shapes.map((x, i) => [i ? ", " : "", el("span", { title: [x.origin, x.note].filter(Boolean).join(". ") || null,
        text: `${txt(x.name || "?")}${x.id !== null && x.id !== undefined ? ` (#${x.id}${x.command ? `, ${x.command}` : ""})` : x.command ? ` (${x.command})` : ""}${flag(x.status)}` })])));
    return out;
  }
  function equippedPanel(eq) {
    const row = (label, e, key) => [statLabel(key || statKeyOf(label), label), el("strong", { text: eqShow(e) }), e ? badge(txt(e.status || "unresolved").replace(/_/g, " "), e.status === "resolved" ? "ok" : e.status === "estimated" ? "info" : "warn") : badge("not reported", "warn"), txt(e && e.note)];
    const p = eq.protection || {}, c = eq.costs || {};
    const rows = [
      row("Protection, body", { value: p.body, status: p.status, note: p.note }, "prot"), row("Protection, head", { value: p.head, status: p.status }, "prot"),
      row("Protection, average", { value: p.average, status: p.status }, "prot"),
      ...(eq.attack || []).map((a) => row(`Attack with ${txt(a.name || "?")}`, a, "att")),
      row("Defence", eq.defence), row("Encumbrance", eq.encumbrance),
      row("Gold", c.gold), row("Resources", c.resources), row("Recruitment points", c.recruitment_points)];
    return panel("With equipment",
      table(["Value", "Shown", "Status", "Note"], rows),
      (eq.notes || []).length ? el("ul", { class: "panel-note" }, eq.notes.map((n) => el("li", { text: asText(n) }))) : null,
      el("p", { class: "panel-note", text: "≈ marks an estimate; \"?\" is not calculated." }));
  }

  function unitDetail(m, u) {
    const slug = m.project.slug, file = u.source.file, r = u.resolved;
    const row = (u.donor && u.donor.catalog_row) || {};
    const wrap = el("div", { class: "stack" });
    const d = u.donor;
    const tiedTo = nationNames(m, unitNationUids(u));
    const stat = (k) => k === "leader" ? r.leadership : r.stats[k];
    // With r.equipped, resolved equipment values replace base stats and costs; the rest stay base values, labelled.
    const eq = r.equipped || null, ec = (eq && eq.costs) || {};
    const cols = SHEET_COLS.map((col) => col.map(([k, label]) => eq ? equippedStat(k, label, stat(k), eq) : [label, stat(k)]));
    const costCell = (label, k) => {
      const comp = [label, r.costs[k], { mark: "†", text: costText(r.costs[k]), note: r.costs[k] && r.costs[k].note }];
      const out = eq && eqVal(ec[k]) ? eqCell(label, ec[k], null) : comp;
      return k === "recruitment_points" && u.role === "commander" ? [out[0], out[1], { ...(out[2] || {}), stat: "commander_points" }] : out;
    };
    cols.push([["Map move", r.stats.mapmove], costCell("Gold", "gold"), costCell("Resources", "resources"), costCell("Rec points", "recruitment_points")]);
    const roleType = { troop: "Troop", commander: "Commander", pretender: "Pretender form", unassigned: "Not recruited" }[u.role] || txt(u.role);
    const spr = (k, label) => u.sprites[k] ? { url: u.sprites[k].url, path: u.sprites[k].path, label, alt: `${txt(u.name)} ${label} sprite` } : { label, missing: "no sprite command" };
    wrap.append(editorSection(slug, u.id, u.name));
    const recruit = u.role === "pretender"
      ? el("p", { class: "sheet-line" }, el("span", { class: "sheet-k", text: "Recruitment:" }), " not recruitable; pretender form. ",
        el("a", { href: route("p", slug, "pretenders", `project-${u.id}`) }, "Open pretender sheet"))
      : el("p", { class: "sheet-line" }, el("span", { class: "sheet-k", text: "Recruitment:" }), " ",
        u.recruitment.length ? u.recruitment.map((x, i) => [i ? "; " : "", x.site_name ? `${x.where} (${x.site_name})` : x.where]) : "not recruitable in this project");
    wrap.append(unitSheet({
      name: u.name || "(unnamed monster)", type: roleType,
      sub: [el("span", { text: tiedTo.length ? tiedTo.join(", ") : "not tied to a nation" }), el("span", { title: `${u.new ? "#newmonster" : "#selectmonster"} ${txt(u.id ?? u.selector)}`, text: `#${txt(u.id ?? u.selector)}` })]
        .filter(Boolean).map((x, i) => [i ? " · " : "", x]),
      cols,
      gear: el("div", { class: "sheet-gear-wrap" }, sheetGear(r.equipment.weapons, "Weapon", r.equipment.weapons_status), sheetGear(r.equipment.armor, "Armour", r.equipment.armor_status)),
      abilities: sheetAbilities([...Object.entries(r.specials), ...Object.entries(r.creature_traits)]),
      magic: sheetMagic(r.magic.paths, r.magic.random),
      lines: [eq ? equippedLines(eq) : null, recruit],
      figure: sheetFigure(txt(u.name), { idle: u.sprites.idle, attack: u.sprites.attack }),
      note: eq ? "Includes equipment where resolved; (base) = without equipment, ≈ = estimate. † Cost component, not the final cost. Underlined = set in this mod."
        : "Base values, before equipment. † Cost component, not the final cost. Underlined = set in this mod.",
      description: u.description,
      foot: [srcRef(slug, file, u.source.line, true), " ",
        u.diagnostics.length ? [badge(`${u.diagnostics.length} validation item(s)`, "warn"), " "] : null,
        el("a", { class: "btn btn-small btn-ghost", href: compareHref(slug, u.id ?? u.uid, donorRef(u)), title: "Side by side with one or two vanilla units" }, "Compare")],
    }));
    const idn = identityNote(u.identity), rel = usedBySection(m, relOf(m, u, "monster"));
    if (idn || rel) wrap.append(el("div", { class: "detail-meta" }, idn, rel));
    wrap.append(inheritanceDisclosure(m, u));
    wrap.append(artworkSection([spr("idle", "Idle (#spr1)"), spr("attack", "Attack (#spr2)")]));
    if (u.new && Number.isInteger(u.id) && CSRF) wrap.append(artManager(m, u, { idle: u.sprites.idle, attack: u.sprites.attack }));
    if (Number.isInteger(u.id) && CSRF) wrap.append(equipmentEditor(m, u));

    // Technical details: inheritance, per-field sources and raw data.
    const tech = [];
    tech.push(panel("Inheritance",
      d ? el("p", null, el("code", { text: `${d.command} ${txt(d.ref)}` }), " ", srcRef(slug, file, d.line), " → ",
        d.resolved ? el("span", null, el("strong", { text: txt(d.name) }), ` (catalog #${d.id}) `, badge("donor resolved", "ok"))
          : el("span", null, badge("donor unresolved", "err"), " ", txt(d.reason)))
        : el("p", { class: "muted", text: u.new ? "No #copystats: unset fields fall back to game defaults, which are not modelled." : "No donor." }),
      el("p", { class: "panel-note", text: "Values apply this block over its donor. Bracketed values are the donor's." }),
      u.unsupported.length ? el("div", null, el("h4", { text: "Commands not modelled" }), table(["Line", "Command", "Why"], u.unsupported.map((x) => [srcRef(slug, file, x.line), el("code", { text: x.raw }), x.reason]))) : null,
      u.unresolved.length ? el("div", null, el("h4", { text: "Unresolved dependencies" }), el("ul", null, u.unresolved.map((x) => el("li", null, srcRef(slug, file, x.line), " ", x.reason)))) : null));
    if (eq) tech.push(equippedPanel(eq));

    // Stats
    const statRows = Object.entries(r.stats).map(([k, f]) => ({ class: f.source === "authored" ? "override" : null,
      cells: [statLabel(k, STAT_LABELS[k] || k), el("code", { text: `#${k}` }), ...fieldCell(slug, file, f, row[k])] }));
    const ld = r.leadership;
    statRows.push({ class: ld.source === "authored" ? "override" : null, cells: [statLabel("leader", "Leadership"), el("code", { text: "leader" }), ...fieldCell(slug, file, ld, row.leader)] });
    tech.push(el("div", { class: "grid-2" },
      panel("Base stats (unequipped)", table(["Field", "Key", "Value", "Source"], statRows),
        el("p", { class: "panel-note", text: "Base values before equipment. Natural protection excludes armour; attack, defence, precision and encumbrance exclude weapon and armour modifiers. Equipment-derived combat totals are not calculated." })),
      el("div", { class: "stack" },
        panel("Magic",
          Object.keys(r.magic.paths).length ? table(["Path", "Level", "Source"], Object.entries(r.magic.paths).map(([p, f]) => ({ class: f.source === "authored" ? "override" : null, cells: [pathNamed(p, ` (${p})`), ...fieldCell(slug, file, f, row[p])] })))
            : el("p", { class: "muted", text: "No fixed magic paths." }),
          r.magic.random.length ? table(["Random pick", "Chance", "Levels", "Source"], r.magic.random.map((x) => [el("span", { class: "path-rand" }, randomMark(), x.paths.join("/") + ` (mask ${x.mask})`), `${x.chance}%`, txt(x.levels ?? "?"),
            el("span", null, badge(x.source, x.source === "authored" ? "authored" : "copper"), " ", srcRef(slug, file, x.line))]), { caption: "Random magic (listed as written; probabilities not expanded)" }) : null),
        panel("Costs",
          table(["Cost", "Component", "Final cost", "Source"], Object.entries(r.costs).map(([k, f]) => [statLabel(k, k.replace(/_/g, " ")),
            f.authored_value === null ? el("span", { class: "muted", text: "none" })
              : el("span", null, el("code", { text: `${f.source === "donor" ? f.column : f.command} ${f.authored_value}` }), " ", badge(f.interpretation.replace(/_/g, " "), "info")),
            unresolved("not computed"),
            el("span", null, badge(f.source.replace(/_/g, " "), f.source === "authored" ? "authored" : f.source === "donor" ? "copper" : "warn"), f.line ? [" ", srcRef(slug, file, f.line)] : null,
              f.note ? el("div", { class: "faint", text: f.note }) : null)])),
          el("p", { class: "panel-note", text: "Components only: the game computes the final costs, and Kosmokrator does not. #rcost leaves out the resource cost of weapons and armour. #gcost is either a fixed value or autocalc-encoded (10000 + base), which the game then adjusts for leadership, magic, spy/assassin and sacred status. How #rpcost values are interpreted depends on the value." })))));

    // Equipment and specials
    const eqRows = (list, cat) => list.length ? table(["Item", "Id", "Source"], list.map((x) => [
      x.name ? txt(x.name) : unresolved(x.unresolved || "unknown"), txt(x.id ?? x.ref),
      el("span", null, badge(x.source, x.source === "authored" ? "authored" : "copper"), " ", srcRef(slug, file, x.line))])) : el("p", { class: "muted", text: `No ${cat}.` });
    const eqStatus = (s) => s && s.status === "unresolved" ? el("p", null, badge("effective list unresolved", "warn"), " ", el("span", { class: "muted", text: s.note })) : null;
    const specRows = (obj, empty) => Object.keys(obj).length ? table(["Ability", "Value", "Source"], Object.entries(obj).map(([k, f]) => ({ class: f.source === "authored" ? "override" : null,
      cells: [el("code", { text: `#${k}` }), f.status === "unresolved" ? unresolved(f.note) : el("strong", { text: txt(f.value) }), fieldCell(slug, file, f, null)[1]] }))) : el("p", { class: "muted", text: empty });
    tech.push(el("div", { class: "grid-2" },
      panel("Equipment",
        el("h4", { text: "Weapons" }), eqStatus(r.equipment.weapons_status), eqRows(r.equipment.weapons, "weapons"),
        el("h4", { text: "Armour" }), eqStatus(r.equipment.armor_status), eqRows(r.equipment.armor, "armour"),
        el("p", { class: "panel-note", text: r.equipment.note })),
      panel("Special abilities", specRows(r.specials, "No modelled special abilities."),
        Object.keys(r.creature_traits).length ? [el("h4", { text: "Creature traits" }), specRows(r.creature_traits, "")] : null,
        (r.authored_traits || []).length ? [el("h4", { text: "Authored trait lines" }),
          table(["Command", "Line", "Status"], r.authored_traits.map((a) => ({ class: a.status === "authored" ? "override" : null,
            cells: [el("span", null, el("code", { text: a.raw }), el("div", { class: "faint", text: `${a.group}, p.${a.page}` })), srcRef(slug, file, a.line),
              a.status === "authored" ? badge("authored", "authored") : badge(a.status, "warn")] }))),
          el("p", { class: "panel-note", text: r.authored_traits_note })] : null,
        el("p", { class: "panel-note", text: "Only common abilities are shown; inherited ones may still apply." }))));

    // Recruitment
    tech.push(panel("Recruitment and restrictions",
      u.role === "pretender" ? el("p", null, badge("not recruitable", "info"), " Pretender form, named only by nation god commands: ",
        (u.god_commands || []).map((x, i) => [i ? ", " : "", el("code", { text: x.via }), " ", srcRef(slug, file, x.line)]), ". ",
        el("a", { href: route("p", slug, "pretenders", `project-${u.id}`) }, "Open in Pretenders")) : null,
      u.recruitment.length ? table(["Via", "Where", "Line"], u.recruitment.map((x) => [el("code", { text: x.via }), x.site_name ? `${x.where} (${x.site_name})` : x.where, srcRef(slug, file, x.line)]))
        : el("p", { class: "muted", text: "Not recruitable through any nation or site in this project." }),
      el("p", { class: "panel-note", text: "Donor recruitment limits are raw catalog values; confirm in game." })));

    const gf = r.god, extra = r.unmodelled_donor_columns || {};
    if (gf && (gf.startdom.value !== null || gf.pathcost.value !== null || (gf.homerealm.value || []).length || gf.startdom.source === "cleared" || Object.keys(extra).length)) {
      tech.push(panel("God fields and unmodelled donor columns",
        table(["Field", "Value", "Source"], [["Starting dominion", "startdom", gf.startdom], ["New path cost", "pathcost", gf.pathcost], ["Home realm", "homerealm", gf.homerealm]].map(([label, key, f]) => [
          `${label} (#${key})`, f.value === null || f.value === undefined ? unresolved(f.note || "unknown") : el("strong", { text: Array.isArray(f.value) ? (f.value.join(", ") || "none") : f.value }),
          godSource(slug, file, f)])),
        Object.keys(extra).length ? table(["Donor column", "Raw value", "Status"], Object.entries(extra).map(([k, x]) => [el("code", { text: k }), el("code", { text: x.value }), x.status]),
          { caption: "Donor columns that can change shape, economy or god behaviour. Not modelled; the status is an assumption." }) : null,
        el("p", { class: "panel-note", text: gf.note })));
    }
    const nTech = u.unsupported.length + u.unresolved.length;
    wrap.append(techSection(`Details: stat sources and costs${nTech ? ` (${nTech} not modelled or unresolved)` : ""}`, false, tech));
    wrap.append(techSection(`Authored commands (${u.authored.length})`, false, authoredTable(slug, u)));
    if (d && d.catalog_row) {
      const costKeys = new Set(["basecost", "rcost", "rpcost"]);
      wrap.append(el("details", { class: "raw tech" }, el("summary", null, `Donor raw catalog row: ${txt(d.name)} (#${d.id}) - ${Object.keys(d.catalog_row).length} non-empty columns`),
        el("div", { class: "inner" },
          el("p", { class: "panel-note", text: "Raw dom6inspector columns as stored, before this block's commands. Not effective values." }),
          table(["Column", "Raw value", ""], Object.entries(d.catalog_row).map(([k, v]) => [el("code", { text: k }), el("code", { text: v }),
            costKeys.has(k) ? badge("raw cost component, not a final cost", "warn") : ""])))));
    }
    wrap.append(techSection(`Diagnostics (${u.diagnostics.length})`, u.diagnostics.length > 0, diagnosticsList(slug, u.diagnostics, file)));
    wrap.append(techSection("Source", false, sourcePanel(slug, u, "Monster")));
    wrap.append(techSection("JSON", false, jsonActions(`/api/projects/${encodeURIComponent(slug)}/monsters/${encodeURIComponent(u.id ?? u.uid)}`, () => u, "Unit JSON")));
    return wrap;
  }

  // ---------- copy/reset history (kosmokrator.inheritance/1, read-only) ----------
  // From m.inheritance when the model carries it, else GET .../inheritance when opened. Evidence only: states come from the
  // existing resolver and are never upgraded here; anything the report calls unresolved stays labelled unresolved.
  const INH_STATES = [["retained", "Retained from donor", "copper"], ["authored", "Set in this .dm", "authored"], ["cleared", "Cleared by a reset", "info"], ["recorded", "Recorded status evidence", "info"], ["unresolved", "Unresolved", "warn"]];
  const HIST_BADGE = { overwritten: ["overwritten later", "warn"], cleared: ["ended by a reset", "info"], unresolved: ["not modelled / unresolved", "warn"], recorded: ["recorded", ""] };
  const inhUrl = (slug) => `/api/projects/${encodeURIComponent(slug)}/inheritance`;
  function inhValue(f) {
    if (f.name) return `${txt(f.name)}${f.id !== null && f.id !== undefined ? ` (#${f.id})` : ""}`;
    if (f.authored_value !== undefined && (f.value === null || f.value === undefined)) return f.authored_value === null ? "none" : `${txt(f.command || f.column || "")} ${txt(f.authored_value)}`.trim();
    if (Array.isArray(f.value)) return f.value.join(", ") || "none";
    if (f.value === null || f.value === undefined) return f.mask !== undefined ? `mask ${f.mask}` : "unknown";
    return txt(f.value);
  }
  function inheritanceBody(m, u, rep) {
    const slug = m.project.slug, file = u.source.file;
    const r = rep && (rep.monsters || []).find((x) => x.uid === u.uid || (x.id !== null && x.id !== undefined && String(x.id) === String(u.id)));
    if (!r) return [stateBox("empty", "No inheritance entry for this unit.", "The report lists every project monster block; reload the project if the .dm changed.")];
    const line = (n) => (n ? srcRef(slug, file, n) : null);
    const donors = (r.donors || []).length ? el("ul", { class: "plain-list inh-donors" }, r.donors.map((d) => el("li", null,
      el("code", { text: `${txt(d.command || "#copystats")} ${txt(d.ref)}` }), " ", line(d.line), " → ",
      d.name ? el("strong", { text: txt(d.name) }) : el("span", { class: "muted", text: "unnamed" }), " ",
      badge(d.origin === "catalog" ? "catalog donor" : d.origin === "project" ? "project donor" : "unknown donor", d.status === "unresolved" ? "warn" : "copper"),
      d.status === "unresolved" ? [" ", badge("unresolved", "warn"), " ", el("span", { class: "faint", text: txt(d.reason) })] : null,
      d.ordering_uncertainty ? el("div", { class: "faint", text: `Order: ${d.ordering_uncertainty}` }) : null,
      d.catalog && d.catalog.dataset_version ? el("div", { class: "faint", text: `Catalog ${txt(d.catalog.dataset_version)}${d.catalog.revision ? ` @ ${String(d.catalog.revision).slice(0, 10)}` : ""}; community data, may differ from your game.` }) : null)))
      : el("p", { class: "muted", text: u.new ? "No #copystats: unset fields fall back to game defaults, which are not modelled." : "No copy command in this block." });
    // History: only copies, resets and lines whose state is not plainly "recorded" (names and sprites stay in Authored commands).
    const hist = (r.history || []).filter((h) => h.donor || h.reset || h.state !== "recorded");
    const histTable = hist.length ? table(["Line", "Command", "State", "Effect"], hist.map((h) => {
      const [label, kind] = HIST_BADGE[h.state] || [txt(h.state), "info"];
      return { class: h.reset || h.donor ? "inh-step" : null, cells: [line(h.line), el("code", { text: txt(h.raw || h.command) }),
        el("span", null, h.reset ? [badge("reset", "info"), " "] : h.donor ? [badge("copy", "copper"), " "] : null, h.state === "recorded" && (h.reset || h.donor) ? null : badge(label, kind)),
        el("span", null, txt(h.effect), h.scope ? el("div", { class: "faint", text: `Scope: ${h.scope}` }) : null, h.trait_status ? el("div", { class: "faint", text: txt(h.trait_status) }) : null)] };
    }), { caption: "Copies, resets and lines that were overwritten, cleared or not modelled, in source order" })
      : el("p", { class: "muted", text: "No copies, resets, overwritten or unmodelled lines." });
    const fields = r.fields || [];
    const groups = INH_STATES.map(([key, label, kind]) => {
      const xs = fields.filter((f) => f.state === key);
      if (!xs.length) return null;
      return el("details", { class: "inh-group", open: (key === "unresolved" || key === "cleared") || null },
        el("summary", null, badge(`${xs.length}`, kind), " ", label),
        el("ul", { class: "plain-list chips inh-fields" }, xs.map((f) => el("li", { class: "inh-field", title: f.note || null },
          el("code", { text: txt(f.field) }), " ", el("span", { text: inhValue(f) }), f.line ? [" ", line(f.line)] : null,
          key === "unresolved" && f.note ? el("span", { class: "faint", text: ` ${txt(f.note)}` }) : null))));
    }).filter(Boolean);
    const cols = Object.entries(r.unmodelled_donor_columns || {});
    const shapes = cols.filter(([k]) => /shape/.test(k)), other = cols.filter(([k]) => !/shape/.test(k));
    const colList = (xs) => el("ul", { class: "plain-list chips" }, xs.map(([k, x]) => el("li", null, el("code", { text: `${k} ${txt(x && typeof x === "object" ? x.value : x)}` }),
      x && x.status ? el("span", { class: "faint", text: ` ${txt(x.status)}` }) : null)));
    return [
      el("h4", { text: "Donors" }), donors,
      el("h4", { text: "Copy and reset history" }), histTable,
      el("h4", { text: "Modelled fields by origin" }),
      groups.length ? el("div", { class: "inh-groups" }, groups) : el("p", { class: "muted", text: "No modelled fields reported." }),
      shapes.length ? [el("h4", { text: "Transformations (donor shape columns, not modelled)" }), colList(shapes),
        el("p", { class: "panel-note", text: "Whether a later #clearspec or #copystats keeps these is not documented; treat them as uncertain and confirm in game." })] : null,
      other.length ? [el("h4", { text: "Other donor abilities not modelled" }), colList(other)] : null,
      (r.unsupported || []).length ? [el("h4", { text: `Authored commands not modelled (${r.unsupported.length})` }),
        el("ul", { class: "plain-list" }, r.unsupported.map((x) => el("li", null, line(x.line), " ", el("code", { text: txt(x.raw || x.command) }), x.reason ? el("span", { class: "faint", text: ` ${txt(x.reason)}` }) : null)))] : null,
      (r.issues || []).length ? [el("h4", { text: "Issues" }), el("ul", { class: "diag" }, r.issues.map((x) => el("li", null, badge("unresolved", "warn"), " ", line(x.line),
        el("span", { text: txt(x.reason) }), (x.chains || []).length ? el("span", { class: "faint", text: ` Chains: ${x.chains.map((c) => c.join(" → ")).join("; ")}` }) : null)))] : null,
      (rep.limits || []).length ? el("details", { class: "inh-limits" }, el("summary", null, "What this does not prove"), el("ul", null, rep.limits.map((t) => el("li", { text: txt(t) })))) : null,
      rep.catalog_issue ? stateBox("empty", "Catalog could not be read for this report.", txt(rep.catalog_issue)) : null,
    ];
  }
  function inheritanceDisclosure(m, u) {
    const slug = m.project.slug, rep0 = m.inheritance || null;
    const entry = rep0 && (rep0.monsters || []).find((x) => x.uid === u.uid);
    const c = entry && entry.counts, unres = c ? (c.unresolved || 0) + (entry.issues || []).length : 0;
    const resets = entry ? (entry.history || []).filter((h) => h.reset).length : 0;
    const nd = entry ? (entry.donors || []).length : 0;
    const title = entry ? `Inheritance: ${nd} cop${nd === 1 ? "y" : "ies"}${resets ? ` · ${resets} reset${resets === 1 ? "" : "s"}` : ""}${unres ? ` · ${unres} unresolved` : ""}`
      : "Inheritance";
    const inner = el("div", { class: "inner stack" });
    const box = el("details", { class: "raw tech inh" }, el("summary", null, title, entry && unres ? [" ", badge("uncertain", "warn")] : null), inner);
    const fill = (rep) => fillKids(inner, el("p", { class: "panel-note", text: "Static reading of this block over its donor. It does not run the game; unresolved items stay unresolved." }), inheritanceBody(m, u, rep));
    box.addEventListener("toggle", () => {
      if (!box.open || inner.childNodes.length) return;
      if (rep0) { fill(rep0); return; }
      inner.replaceChildren(stateBox("loading", "Reading inheritance report..."));
      // Cached per loaded model, so a reloaded project (after any save) fetches a fresh report.
      modelLoad(m, inhUrl(slug), (b) => b.inheritance || b.result).then(fill, (e) => { fillKids(inner, errorBox(e, "the inheritance report"),
        el("div", { class: "btn-row" }, el("button", { type: "button", class: "btn btn-small", onclick: () => { inner.replaceChildren(); box.open = false; box.open = true; } }, "Retry"))); });
    });
    return box;
  }

  // ---------- bounded monster editor ----------
  // Edits curated commands inside one project #newmonster/#selectmonster block through the server's editor route.
  // Drafts live in state.editors (keyed by slug:id) so re-renders, failed saves and conflicts never lose input.
  const CSRF = ($('meta[name="kosmo-csrf"]') || {}).content || "";
  const EDIT_GROUPS = [["stats", "Base stats (unequipped)"], ["leadership", "Leadership"], ["magic", "Magic paths"], ["god", "Pretender design"]];
  const LEADER_LABELS = { noleader: "No leader (0)", poorleader: "Poor (10)", okleader: "Ok (50)", goodleader: "Good (100)", expertleader: "Expert (150)", superiorleader: "Superior (200)" };
  async function postJSON(url, body) {
    let res;
    try {
      res = await fetch(url, { method: "POST", cache: "no-store", credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json", "X-Kosmo-CSRF": CSRF }, body: JSON.stringify(body) });
    } catch (e) { throw { status: 0, error: { code: "network_error", message: "The local server is not reachable. Is `kosmokrator serve` still running?" } }; }
    let data;
    try { data = await res.json(); } catch (e) { throw { status: res.status, error: { code: "bad_response", message: `HTTP ${res.status}` } }; }
    if (!res.ok || data.ok === false) throw { status: res.status, ...(data.error ? data : { error: { code: `http_${res.status}`, message: res.statusText } }) };
    return data.result;
  }
  const editorKey = (slug, id) => `${slug}:${id}`;
  function editorDraft(slug, id) {
    const k = editorKey(slug, id);
    if (!state.editors.has(k)) state.editors.set(k, { open: false, raw: {}, ops: {}, tops: [], q: "", pick: "", st: null, phase: "edit", preview: null, msg: null });
    return state.editors.get(k);
  }
  // Current written value of a field: the authored line if any, else the effective (inherited) value.
  const curValue = (f) => (f.authored ? f.authored.value : f.effective.value);
  function sourceTag(f) {
    if (f.authored) return el("span", { class: "field-src" }, badge("authored", "authored"), ` line ${f.authored.line}`);
    const e = f.effective;
    if (e.value === null || e.value === undefined) return el("span", { class: "field-src faint", text: e.source === "not_modelled" ? "not modelled" : "not set" });
    return el("span", { class: "field-src" }, badge(e.source === "donor" ? "inherited" : txt(e.source).replace(/_/g, " "), e.source === "donor" ? "copper" : "warn"));
  }
  // Turn the draft into server changes plus per-field input errors (checked again on the server).
  function draftChanges(ed) {
    const st = ed.st, changes = [], errors = {};
    for (const [key, rawText] of Object.entries(ed.raw)) {
      const s = st.schema[key], f = st.fields[key], t = String(rawText).trim(), cur = curValue(f);
      if (t === "") {
        if (f.authored) changes.push({ key, op: "remove" });
        else if (s.group === "stats" && cur !== null && cur !== undefined) errors[key] = "Enter a value.";
        else if (cur !== null && cur !== undefined) changes.push({ key, op: "remove" });
        else if (s.group === "traits") errors[key] = "Enter a value, or cancel the add.";
        continue;
      }
      if (!/^-?\d+$/.test(t)) { errors[key] = "Whole numbers only."; continue; }
      const n = Number(t);
      if (n < s.min || n > s.max) { errors[key] = `Allowed ${s.min} to ${s.max}.`; continue; }
      if (n === 0 && !s.zero) { errors[key] = "0 is not valid here; remove the command instead."; continue; }
      if (n !== cur) changes.push({ key, op: "set", value: n });
    }
    for (const [key, op] of Object.entries(ed.ops)) if (!(key in ed.raw)) changes.push({ key, ...op });
    // Full trait catalogue drafts: { key, op, line?, raw: [strings] } -> typed values (the server checks again).
    (ed.tops || []).forEach((t, i) => {
      const spec = st.traits.traits[t.key], ek = `trait:${i}`;
      if (t.op === "remove") { changes.push(t.line ? { key: t.key, op: "remove", line: t.line } : { key: t.key, op: "remove" }); return; }
      if (!spec.args.length) { changes.push({ key: t.key, op: t.op, value: true }); return; }
      const vals = [];
      spec.args.forEach((a, j) => {
        const r = String(t.raw[j] ?? "").trim();
        if (r === "") { errors[ek] = errors[ek] || `Enter ${a.name}.`; return; }
        if (a.type === "int" || a.type === "pathmask") {
          if (!/^-?\d+$/.test(r)) { errors[ek] = `${a.name}: whole numbers only.`; return; }
          const n = Number(r);
          if (a.allowed && !a.allowed.includes(n)) errors[ek] = `${a.name}: allowed ${a.allowed.length > 12 ? `${a.allowed[0]}…${a.allowed[a.allowed.length - 1]}` : a.allowed.join(", ")}.`;
          else if (a.range && ((a.range[0] !== null && n < a.range[0]) || (a.range[1] !== null && n > a.range[1]))) errors[ek] = `${a.name}: allowed ${a.range[0] ?? "…"} to ${a.range[1] ?? "…"}.`;
          vals.push(n);
        } else {
          if (/["#\r\n]|--/.test(r)) { errors[ek] = `${a.name}: no quotes, #, -- or line breaks.`; return; }
          vals.push(/^-?\d+$/.test(r) ? Number(r) : r);
        }
      });
      if (errors[ek] || vals.length !== spec.args.length) return;
      const value = vals.length === 1 ? vals[0] : vals;
      changes.push(t.line ? { key: t.key, op: t.op, line: t.line, value } : { key: t.key, op: t.op, value });
    });
    return { changes, errors };
  }
  // `toggle` redraws only the editor section, so opening or closing keeps the page's scroll position and focus.
  function editorButton(slug, id, name, toggle) {
    const ed = editorDraft(slug, id);
    const n = ed.st ? draftChanges(ed).changes.length : 0;
    return el("div", { class: "btn-row edit-bar" },
      el("button", { type: "button", class: "btn", "aria-expanded": ed.open ? "true" : "false", "aria-controls": `editor-${id}`,
        disabled: !CSRF || null, title: CSRF ? null : "This server did not provide an editor token; restart `kosmokrator serve` and reload.",
        "aria-label": ed.open ? "Close editor" : `Edit ${txt(name) || "this monster"}`,
        onclick: () => { ed.open = !ed.open; ed.msg = null; toggle(); } }, ed.open ? "Close editor" : "Edit"),
      n ? badge(`${n} unsaved change(s)`, "warn") : null,
      ed.msg && ed.msg.kind === "ok" ? el("span", { class: "edit-ok", role: "status", text: ed.msg.text }) : null,
      !CSRF ? el("span", { class: "faint", text: "Editing unavailable: no editor token." }) : null);
  }
  // The editor panel. `holder` is replaced in place; the draft survives re-renders and errors.
  function monsterEditor(slug, id, onClose) {
    const ed = editorDraft(slug, id);
    const holder = el("section", { class: "panel editor", id: `editor-${id}`, "aria-labelledby": `editor-h-${id}` });
    const url = `/api/projects/${encodeURIComponent(slug)}/monsters/${encodeURIComponent(id)}/edit`;
    const load = async () => {
      holder.replaceChildren(el("h3", { id: `editor-h-${id}`, text: "Edit" }), stateBox("loading", "Reading the current .dm..."));
      try { ed.st = await getJSON(url).then((r) => r.result); ed.phase = "edit"; draw(); }
      catch (e) { holder.replaceChildren(el("h3", { id: `editor-h-${id}`, text: "Edit" }), errorBox(e, "the editor"),
        el("div", { class: "btn-row" }, el("button", { type: "button", class: "btn", onclick: load }, "Retry"))); }
    };
    const focusKey = (sel) => focusIn(holder, sel);
    function numInput(key, opts = {}) {
      const s = ed.st.schema[key], f = ed.st.fields[key];
      const cur = curValue(f), val = key in ed.raw ? ed.raw[key] : (cur === null || cur === undefined ? "" : String(cur));
      const { errors } = draftChanges(ed);
      const errId = `err-${id}-${key.replace(/\W/g, "_")}`, hintId = `hint-${id}-${key.replace(/\W/g, "_")}`;
      const changed = key in ed.raw && String(ed.raw[key]).trim() !== (cur === null || cur === undefined ? "" : String(cur));
      const input = el("input", { class: "input num-input" + (changed ? " changed" : ""), type: "text", inputmode: "numeric", autocomplete: "off",
        id: `f-${id}-${key.replace(/\W/g, "_")}`, "data-key": key, value: val, "aria-invalid": errors[key] ? "true" : null,
        "aria-describedby": [errors[key] ? errId : null, hintId].filter(Boolean).join(" ") });
      input.addEventListener("input", () => {
        ed.raw[key] = input.value; ed.msg = null;
        const err = draftChanges(ed).errors[key];
        input.setAttribute("aria-invalid", err ? "true" : "false");
        input.classList.toggle("changed", input.value.trim() !== (cur === null || cur === undefined ? "" : String(cur)));
        const box = holder.querySelector(`#${errId}`); if (box) box.textContent = err || "";
        input.setAttribute("aria-describedby", [err ? errId : null, hintId].join(" ").trim());
        updateCount();
      });
      const range = `${s.min}–${s.max}${s.zero ? "" : ", not 0"}${s.range_source && s.range_source !== "manual" ? " (sanity bound)" : ""}`;
      return el("div", { class: "edit-field" + (opts.wide ? " wide" : "") },
        el("label", { for: input.id }, s.group === "stats" ? statIcon(key) : null, opts.label || s.label),
        el("div", { class: "edit-control" }, input,
          f.authored && !opts.noRevert ? el("button", { type: "button", class: "btn btn-small btn-ghost", title: `Delete the authored line ${f.authored.line}; the review shows what the value falls back to`,
            onclick: () => { ed.raw[key] = ""; draw(`[data-key="${key}"]`); } }, "Remove override") : null),
        el("div", { class: "field-meta", id: hintId }, sourceTag(f), f.donor !== null && f.donor !== undefined ? el("span", { class: "faint", text: ` donor ${f.donor}` }) : null,
          el("span", { class: "faint", text: ` · ${range}` }), f.duplicates.length ? el("span", { class: "field-err", text: ` · duplicate lines ${f.duplicates.join(", ")}` }) : null),
        el("div", { class: "field-err", id: errId, "aria-live": "polite", text: errors[key] || "" }));
    }
    function leaderControl() {
      const f = ed.st.fields.leader, op = ed.ops.leader;
      const sel = el("select", { class: "input", id: `f-${id}-leader`, "data-key": "leader" },
        el("option", { value: "", text: f.authored ? `${LEADER_LABELS[f.authored.value]} (authored)` : `Inherited: ${txt(f.effective.value ?? "unknown")} (no change)` }),
        Object.entries(LEADER_LABELS).filter(([k]) => !f.authored || k !== f.authored.value).map(([k, l]) => el("option", { value: k, text: l })),
        f.authored ? el("option", { value: "__remove", text: `Use inherited${f.donor ? ` (donor ${f.donor})` : ""}` }) : null);
      sel.value = op ? (op.op === "remove" ? "__remove" : op.value) : "";
      sel.addEventListener("change", () => {
        if (!sel.value) delete ed.ops.leader; else ed.ops.leader = sel.value === "__remove" ? { op: "remove" } : { op: "set", value: sel.value };
        sel.classList.toggle("changed", !!sel.value); ed.msg = null; updateCount();
      });
      if (op) sel.classList.add("changed");
      return el("div", { class: "edit-field wide" }, el("label", { for: sel.id }, statIcon("leader"), "Leadership"), el("div", { class: "edit-control" }, sel),
        el("div", { class: "field-meta" }, sourceTag(f), el("span", { class: "faint", text: " · #poorleader … #superiorleader" })));
    }
    // Full trait catalogue (traits.py, Modding Manual 6.36). Only traits present on this monster are listed; the
    // searchable picker adds any other documented trait with typed, reference or tuple controls.
    const argHint = (a) => a.type === "mon" ? "monster name or number" : a.type === "monneg" ? "monster name/number, -2…-26 or -montag"
      : a.type === "spell" ? "spell name or number" : a.type === "site" ? "site name or number" : a.type === "item" ? "item name or number"
      : a.type === "pathmask" ? "sum of path masks (128 Fire … 65536 Priest)"
      : a.allowed ? (a.allowed.length > 12 ? `${a.allowed[0]}…${a.allowed[a.allowed.length - 1]}` : a.allowed.join(" / "))
      : a.range ? `${a.range[0] ?? "…"} to ${a.range[1] ?? "…"} (manual)` : "whole number (no range in manual)";
    function argInputs(t, i) {
      const spec = ed.st.traits.traits[t.key], ek = `trait:${i}`;
      const err = draftChanges(ed).errors[ek];
      return el("div", { class: "trait-args" }, spec.args.map((a, j) => {
        const inp = el("input", { class: "input trait-arg", type: "text", autocomplete: "off", id: `ta-${id}-${i}-${j}`, "data-trait-arg": `${i}:${j}`,
          inputmode: ["int", "pathmask"].includes(a.type) ? "numeric" : null, value: t.raw[j] ?? "", "aria-invalid": err ? "true" : null,
          "aria-describedby": `ta-err-${id}-${i}` });
        inp.addEventListener("input", () => { t.raw[j] = inp.value; ed.msg = null; const e2 = draftChanges(ed).errors[ek];
          const box = holder.querySelector(`#ta-err-${id}-${i}`); if (box) box.textContent = e2 || ""; inp.setAttribute("aria-invalid", e2 ? "true" : "false"); updateCount(); });
        return el("label", { class: "trait-arg-wrap", for: inp.id }, el("span", { class: "faint", text: `${a.name} · ${argHint(a)}` }), inp);
      }), el("div", { class: "field-err", id: `ta-err-${id}-${i}`, "aria-live": "polite", text: err || "" }));
    }
    function traitRows() {
      const cat = ed.st.traits.traits, tf = ed.st.trait_fields || {};
      const drop = (i) => { ed.tops.splice(i, 1); draw(`#trait-search-${id}`); };
      const pending = (key, line) => ed.tops.findIndex((t) => t.key === key && (t.line || null) === (line || null) && t.op !== "add");
      const rows = [];
      for (const [k, f] of Object.entries(tf)) {
        const spec = cat[k];
        const name = el("span", null, traitIcon(k, f.effective && f.effective.value), el("code", { text: `#${k}` }), el("div", { class: "faint", text: `${spec.group}, p.${spec.page}` }));
        const meta = el("span", { class: "faint", text: spec.summary });
        if (f.duplicates) rows.push({ class: "row-removing", cells: [name, el("span", { class: "field-err", text: `Duplicate live lines ${f.duplicates.join(", ")}: fix in the source first.` }), meta, ""] });
        for (const ln of f.lines) {
          const i = pending(k, spec.repeatable ? ln.line : null), t = ed.tops[i];
          let value, action;
          if (t && t.op === "remove") { value = el("span", { class: "faint", text: `— (delete line ${ln.line})` }); action = el("button", { type: "button", class: "btn btn-small", onclick: () => drop(i) }, "Undo"); }
          else if (t) { value = argInputs(t, i); action = el("button", { type: "button", class: "btn btn-small", onclick: () => drop(i) }, "Undo"); }
          else {
            value = el("span", null, el("code", { text: ln.raw }), " ", badge("authored", "authored"), ` line ${ln.line}`, ln.malformed ? el("div", { class: "field-err", text: "Not the documented arguments: kept as written, not editable." }) : null);
            action = el("span", { class: "btn-row" },
              spec.args.length && !ln.malformed && !f.duplicates ? el("button", { type: "button", class: "btn btn-small btn-ghost", "aria-label": `Change #${k} on line ${ln.line}`, onclick: () => {
                ed.tops.push({ key: k, op: spec.repeatable ? "replace" : "set", line: spec.repeatable ? ln.line : undefined, raw: (ln.args || []).map((x) => String(x)) }); draw(`[data-trait-arg="${ed.tops.length - 1}:0"]`); } }, "Change") : null,
              !f.duplicates ? el("button", { type: "button", class: "btn btn-small", "aria-label": `Remove #${k} line ${ln.line}`, onclick: () => {
                ed.tops.push({ key: k, op: "remove", line: spec.repeatable ? ln.line : undefined, raw: [] }); draw(`#trait-search-${id}`); } }, "Remove") : null);
          }
          rows.push({ class: t ? (t.op === "remove" ? "row-removing" : "row-adding") : null, cells: [name, value, meta, action] });
        }
        if (!f.lines.length) {
          const e = f.effective, inh = e.value !== null && e.value !== undefined;
          rows.push({ cells: [name, inh ? el("span", null, el("strong", { text: e.value === true ? "yes" : txt(e.value) }), " ", badge("inherited", "copper")) : el("span", { class: "faint", text: "no live line" }),
            el("span", null, meta, f.dead_lines.length ? el("div", { class: "faint", text: `Line(s) ${f.dead_lines.join(", ")} ended by ${f.reset ? `${f.reset.command} line ${f.reset.line}` : "a reset"}.` }) : null,
              inh ? el("div", { class: "faint", text: "Inherited from the donor. Removing it needs #clearspec/#clearmagic, which also removes other abilities, so it is not offered." }) : null),
            spec.repeatable ? "" : el("span", { class: "faint", text: inh ? "inherited" : "" })] });
        }
      }
      ed.tops.forEach((t, i) => {
        if (t.op !== "add" && !(t.op === "set" && !(tf[t.key] && tf[t.key].lines.length))) return;
        const spec = cat[t.key];
        rows.push({ class: "row-adding", cells: [el("span", null, traitIcon(t.key, t.raw && t.raw[0]), el("code", { text: `#${t.key}` }), el("div", { class: "faint", text: `${spec.group}, p.${spec.page}` })),
          spec.args.length ? argInputs(t, i) : el("span", { text: "yes (flag)" }),
          el("span", { class: "faint", text: `New line before #end. ${spec.note || ""}` }), el("button", { type: "button", class: "btn btn-small", onclick: () => drop(i) }, "Cancel add")] });
      });
      // Searchable, grouped picker: single-value traits already present are hidden; repeatable ones stay addable.
      const q = ed.q.trim().toLowerCase().replace(/^#/, "");
      const taken = (k) => !cat[k].repeatable && ((tf[k] && (tf[k].lines.length || (tf[k].effective.value !== null && tf[k].effective.value !== undefined))) || ed.tops.some((t) => t.key === k));
      const avail = Object.keys(cat).filter((k) => !taken(k) && (!q || k.includes(q) || cat[k].summary.toLowerCase().includes(q) || cat[k].group.toLowerCase().includes(q)));
      const search = el("input", { class: "input", type: "search", id: `trait-search-${id}`, placeholder: "Search traits (e.g. fire, summon, shape)…", value: ed.q, autocomplete: "off", "aria-controls": `add-trait-${id}` });
      const count = el("span", { class: "faint", role: "status", "aria-live": "polite", text: `${avail.length} of ${Object.keys(cat).length} documented traits match` });
      const pick = el("select", { class: "input", id: `add-trait-${id}`, "aria-label": "Trait to add" },
        el("option", { value: "", text: avail.length ? "Choose a trait…" : "No matching trait" }),
        ed.st.traits.groups.map((g) => { const ks = avail.filter((k) => cat[k].group === g); return ks.length ? el("optgroup", { label: g }, ks.map((k) => el("option", { value: k, title: cat[k].summary, text: `#${k}${cat[k].args.length ? " " + cat[k].args.map((a) => `<${a.name}>`).join(" ") : ""}${cat[k].repeatable ? " (repeatable)" : ""} — ${cat[k].summary.slice(0, 70)}` }))) : null; }));
      if (avail.includes(ed.pick)) pick.value = ed.pick;
      const sel = cat[pick.value];
      const desc = el("p", { class: "panel-note", id: `trait-desc-${id}`, "aria-live": "polite" }, sel ? [traitIcon(pick.value), el("code", { text: `#${pick.value}` }), ` (${sel.group}, manual p.${sel.page}): ${sel.summary}`, sel.note ? ` ${sel.note}` : "", sel.range_note ? ` ${sel.range_note}` : ""] : "Pick a trait to see its manual summary.");
      search.addEventListener("input", () => { ed.q = search.value; const pos = search.selectionStart; draw(`#trait-search-${id}`); const s2 = holder.querySelector(`#trait-search-${id}`); if (s2) s2.setSelectionRange(pos, pos); });
      pick.addEventListener("change", () => { ed.pick = pick.value; draw(`#add-trait-${id}`); });
      const add = el("button", { type: "button", class: "btn btn-small", onclick: () => {
        const k = pick.value; if (!k) { pick.focus(); return; }
        ed.tops.push({ key: k, op: cat[k].repeatable ? "add" : "set", raw: cat[k].args.map(() => "") }); ed.pick = "";
        draw(cat[k].args.length ? `[data-trait-arg="${ed.tops.length - 1}:0"]` : `#add-trait-${id}`);
      } }, "Add trait");
      return el("fieldset", { class: "edit-group" }, el("legend", { text: "Special abilities and traits" }),
        rows.length ? table(["Trait", "Value", "About", ""], rows) : el("p", { class: "muted", text: "No documented traits are authored or modelled as inherited on this monster." }),
        el("div", { class: "trait-picker" }, el("label", { for: search.id, text: "Find a trait to add" }), search, count,
          el("div", { class: "btn-row add-trait" }, el("label", { for: pick.id, class: "sr-only", text: "Trait to add" }), pick, add), desc),
        el("p", { class: "panel-note", text: `All ${Object.keys(cat).length} documented monster traits (${ed.st.traits.manual}) can be added. Authored lines can be changed or removed; traits inherited from the donor cannot, because Kosmokrator never adds #clearspec or #clearmagic for you. Inherited abilities outside the modelled donor columns are not shown.` }));
    }
    const countBox = el("span", { role: "status", "aria-live": "polite", class: "edit-count" });
    let reviewBtn;
    function updateCount() {
      const { changes, errors } = draftChanges(ed), nErr = Object.keys(errors).length;
      countBox.textContent = nErr ? `${nErr} field(s) need fixing` : changes.length ? `${changes.length} change(s) ready to review` : "No changes yet";
      if (reviewBtn) reviewBtn.disabled = !changes.length || nErr > 0;
    }
    async function send(preview) {
      const { changes } = draftChanges(ed);
      ed.msg = { kind: "busy", text: preview ? "Checking the changes..." : "Saving..." }; draw();
      try {
        const r = await postJSON(url, { expected_sha256: ed.st.sha256, changes, preview });
        if (preview) { ed.preview = r; ed.phase = "review"; ed.msg = null; draw(r.changed ? "#confirm-save-" + id : "[data-focus=review]"); return; }
        recordReceipt(slug, `Saved ${txt(ed.st.name) || "monster"} (#${id})`, r);
        const key = editorKey(slug, id);
        state.editors.delete(key);
        const fresh = editorDraft(slug, id);
        fresh.msg = { kind: "ok", text: r.written ? `Saved to the .dm. Backup: ${r.backup}` : "Nothing changed." };
        state.models.delete(slug);
        toast(r.written ? "Saved to the .dm" : "Nothing to save");
        render().then(() => { const b = $(`[aria-controls="editor-${id}"]`); if (b) b.focus(); });
      } catch (e) {
        ed.phase = "edit";
        ed.msg = { kind: "err", err: e };
        draw("#edit-error-" + id);
      }
    }
    function errorPanel() {
      const e = ed.msg.err, er = e.error || {};
      const conflict = e.status === 409;
      const blocked = (er.details && er.details.blocked) || [];
      return el("div", { class: "state state-error", role: "alert", id: `edit-error-${id}`, tabindex: "-1" },
        el("strong", { text: conflict ? "The file changed on disk, or another save is running. Nothing was written." : e.status === 403 ? "The server refused the save. Nothing was written." : "Not saved. Nothing was written." }),
        el("div", null, el("span", { class: "code", text: `[${txt(er.code)}] ` }), txt(er.message)),
        blocked.length ? el("ul", null, blocked.map((b) => el("li", null, el("strong", { text: `${b.label}: ` }), b.reason))) : null,
        er.details && er.details.problems ? el("ul", null, er.details.problems.map((p) => el("li", { text: p }))) : null,
        conflict ? el("p", null, "Your edits are still in the form. Reload the latest file; your values are kept and compared with it again.") : el("p", null, "Your edits are still in the form."),
        el("div", { class: "btn-row" }, conflict || e.status === 403 ? el("button", { type: "button", class: "btn", onclick: load }, "Reload latest file (keep my edits)") : null));
    }
    function reviewPanel() {
      const p = ed.preview;
      const effText = (x) => !x ? "?" : x.value === null || x.value === undefined ? "none" : `${x.value === true ? "yes" : x.value} (${txt(x.source).replace(/_/g, " ")})`;
      return el("div", { class: "stack" },
        el("h4", { tabindex: "-1", "data-focus": "review", text: "Review before saving" }),
        table(["Field", "Change", "Effective value", "What happens"], p.plan.map((x) => [
          el("strong", { text: x.label }),
          el("span", null, badge(x.action, x.action === "remove" ? "warn" : x.action === "unchanged" ? "" : "authored"), " ", x.before ? el("code", { text: x.before }) : null, x.before && x.after ? " → " : null, x.after ? el("code", { text: x.after }) : null),
          `${effText(x.effective_before)} → ${effText(x.effective_after)}`, el("span", { class: "muted", text: x.explanation })])),
        el("details", { class: "raw" }, el("summary", null, "Exact text change (diff)"), el("div", { class: "inner" }, el("pre", { class: "code diff" }, p.diff.split("\n").map((l) => el("span", { class: "ln" + (l.startsWith("+") && !l.startsWith("+++") ? " add" : l.startsWith("-") && !l.startsWith("---") ? " del" : ""), text: l }))))),
        el("p", { class: "panel-note", text: "Only the lines shown change. A backup is kept." }),
        el("div", { class: "btn-row" },
          p.changed ? el("button", { type: "button", class: "btn", id: `confirm-save-${id}`, onclick: () => send(false) }, "Save to .dm")
            : el("span", { class: "muted", text: "Nothing to save: the file already says this." }),
          el("button", { type: "button", class: p.changed ? "btn btn-ghost" : "btn", onclick: () => { ed.phase = "edit"; ed.preview = null; draw(REVIEW_TRIGGER); } }, "Back to editing")));
    }
    function draw(focusSel) {
      const st = ed.st;
      const head = el("h3", { id: `editor-h-${id}`, text: `Edit ${txt(st.name) || `monster ${id}`}` });
      const intro = el("p", { class: "panel-note" }, "Writes into ", el("code", { text: `${st.opener} ${id}` }), ` (lines ${st.line}–${st.end_line} of ${st.file}). `,
        st.donor ? ["Donor: ", el("code", { text: `${txt(st.donor.command)} ${txt(st.donor.ref)}` }), st.donor.name ? ` (${st.donor.name}). ` : ". "] : "No donor. ",
        "Values set here are added as overrides or change the existing line; nothing else in the file is rewritten.");
      const busy = ed.msg && ed.msg.kind === "busy" ? stateBox("loading", ed.msg.text) : null;
      const err = ed.msg && ed.msg.kind === "err" ? errorPanel() : null;
      if (ed.phase === "review" && ed.preview) { holder.replaceChildren(head, intro, busy || reviewPanel()); if (focusSel) focusKey(focusSel); return; }
      const groups = EDIT_GROUPS.map(([g, title]) => {
        const keys = Object.keys(st.schema).filter((k) => st.schema[k].group === g);
        return el("fieldset", { class: "edit-group" }, el("legend", { text: title }),
          el("div", { class: "edit-grid" }, g === "leadership" ? leaderControl() : keys.map((k) => numInput(k))),
          g === "magic" ? el("p", { class: "panel-note", text: "Blank means no fixed level. Clearing an authored path deletes its #magicskill line; inherited paths cannot be removed here (that needs #clearmagic)." }) : null,
          g === "god" ? el("p", { class: "panel-note", text: "#startdom and #pathcost make the monster selectable as a pretender. #gcost 10000+base means autocalc; the game computes the final cost." }) : null);
      });
      reviewBtn = el("button", { type: "button", class: "btn", onclick: () => send(true), ...RT }, "Review changes");
      const actions = el("div", { class: "btn-row edit-actions" }, reviewBtn,
        el("button", { type: "button", class: "btn btn-ghost", onclick: () => { state.editors.delete(editorKey(slug, id)); if (onClose) onClose(); else render(); } }, "Cancel"), countBox);
      holder.replaceChildren(...[head, intro, err, busy].filter(Boolean), el("form", { class: "edit-form", novalidate: true, onsubmit: (e) => { e.preventDefault(); if (!reviewBtn.disabled) send(true); } },
        groups, traitRows(), actions));
      updateCount();
      if (focusSel) focusKey(focusSel);
    }
    escapeReview(holder, () => ed.phase === "review", () => { ed.phase = "edit"; draw(REVIEW_TRIGGER); });
    if (ed.st) draw(); else load();
    return holder;
  }
  // Edit button plus (when open) the editor, for project monsters only. Catalog monsters never get one.
  function editorSection(slug, id, name) {
    if (!Number.isInteger(id)) return null;
    const box = el("div", { class: "stack" });
    const draw = (focus) => {
      const ed = editorDraft(slug, id);
      fillKids(box, editorButton(slug, id, name, () => draw(true)), ed.open ? monsterEditor(slug, id, () => draw(true)) : null);
      if (focus) { const b = box.querySelector(`[aria-controls="editor-${id}"]`); if (b) b.focus({ preventScroll: true }); }
    };
    draw(false);
    return box;
  }

  // ---------- authoring: create/duplicate units and gods, create nations, attach art ----------
  // Each form keeps its draft in state.creates / state.arts (keyed by slug and form), so failed checks, conflicts and
  // re-renders never lose input. Every write is reviewed first (preview: true), then sent with the page's SHA-256.
  // Form drafts remember their starting values, so unsavedDrafts() counts them only once something was changed.
  const draftOf = (map, key, init) => {
    if (!map.has(key)) { const d = init(); if (d && d.form && d.formBase === undefined) d.formBase = JSON.stringify(d.form); map.set(key, d); }
    return map.get(key);
  };
  const projectMonsters = (m) => m.monsters.filter((u) => u.new && Number.isInteger(u.id));
  const isGod = (u) => u.resolved && u.resolved.god && u.resolved.god.startdom.value !== null && u.resolved.god.startdom.value !== undefined
    && u.resolved.god.pathcost.value !== null && u.resolved.god.pathcost.value !== undefined;
  const numberedNations = (m) => m.nations.filter((n) => Number.isInteger(n.id));
  const startSitesOf = (m, n) => m.sites.filter((s) => Number.isInteger(s.id) && n && s.start_site_of.includes(n.uid));
  function labelled(id, label, control, hint, err) {
    return el("div", { class: "edit-field" }, el("label", { for: id, text: label }), control,
      hint ? el("div", { class: "field-meta faint", id: `${id}-hint`, text: hint }) : null,
      err ? el("div", { class: "field-err", role: "alert", text: err }) : null);
  }
  function bindInput(node, dr, key, after) {
    node.addEventListener(node.tagName === "SELECT" || node.type === "checkbox" || node.type === "radio" ? "change" : "input", () => {
      dr.form[key] = node.type === "checkbox" ? node.checked : node.value; dr.msg = null; if (after) after();
    });
    return node;
  }
  function writeError(e, retry) {
    const er = e.error || {}, d = er.details || {};
    const conflict = e.status === 409;
    return el("div", { class: "state state-error", role: "alert", tabindex: "-1", "data-focus": "err" },
      el("strong", { text: conflict ? "The project changed on disk, or another write is running. Nothing was written."
        : e.status === 403 ? "The server refused the request. Nothing was written." : "Not written." }),
      el("div", null, el("span", { class: "code", text: `[${txt(er.code)}] ` }), txt(er.message), d.field ? el("span", { class: "faint", text: ` (field: ${d.field})` }) : null),
      Array.isArray(d.problems) ? el("ul", null, d.problems.map((p) => el("li", { text: p }))) : null,
      Array.isArray(d.blocked) ? el("ul", null, d.blocked.map((b) => el("li", { text: b.reason || JSON.stringify(b) }))) : null,
      el("p", null, "Your form values are kept."),
      conflict || e.status === 403 ? el("div", { class: "btn-row" }, el("button", { type: "button", class: "btn btn-small", onclick: retry }, "Reload latest file (keep my form)")) : null);
  }
  function diffView(diff, title) {
    return el("details", { class: "raw", open: true }, el("summary", null, title || "Exact text added to the .dm (diff)"), el("div", { class: "inner" },
      el("pre", { class: "code diff", tabindex: "0" }, diff.split("\n").map((l) => el("span", { class: "ln" + (l.startsWith("+") && !l.startsWith("+++") ? " add" : l.startsWith("-") && !l.startsWith("---") ? " del" : ""), text: l })))));
  }
  // Shared review panel: what will be written, then the explicit write button.
  function reviewBlock(r, commitLabel, onCommit, onBack) {
    const ids = Object.entries(r.ids || {}).map(([k, v]) => `${k} ${v.join(", ")}`).join(" · ");
    return el("div", { class: "stack" },
      el("h4", { tabindex: "-1", "data-focus": "review", text: "Review before writing" }),
      ids ? el("p", null, "Id: ", el("strong", { text: ids }), el("span", { class: "faint", text: " (re-checked and reserved when you confirm)" })) : null,
      (r.assignments || []).length ? el("p", null, "Assignment: ", r.assignments.join("; ")) : null,
      (r.explanation || []).map((t) => el("p", { class: "panel-note", text: t })),
      (r.warnings || []).length ? el("ul", { class: "diag" }, r.warnings.map((w) => el("li", null, badge("check", "warn"), " ", w))) : null,
      diffView(r.diff),
      el("p", { class: "panel-note", text: "Saved with a backup of the previous .dm. Static checks only: test in game." }),
      el("div", { class: "btn-row" }, el("button", { type: "button", class: "btn", onclick: onCommit }, commitLabel),
        el("button", { type: "button", class: "btn btn-ghost", onclick: onBack }, "Back to the form")));
  }
  // Runs preview or write for a draft and re-draws; success hands the result to done().
  async function runWrite(dr, url, body, preview, redraw, done) {
    dr.msg = { kind: "busy", text: preview ? "Checking..." : "Writing..." }; redraw();
    try {
      const r = await postJSON(url, { ...body, preview });
      dr.msg = null;
      if (preview) { dr.preview = r; dr.phase = "review"; redraw("[data-focus=review]"); return; }
      done(r);
    } catch (e) { dr.msg = { kind: "err", err: e }; dr.phase = "edit"; redraw("[data-focus=err]"); }
  }
  // r and title record a save receipt (see recordReceipt); a write that changed nothing leaves none.
  async function afterWrite(slug, href, message, r, title) {
    state.models.delete(slug);
    if (r) recordReceipt(slug, title || message, r);
    toast(message);
    await loadProjects(true);
    if (location.hash === href) render(); else location.hash = href;
  }

  // Create a unit/god from a donor, or duplicate a project monster. kind: "unit" or "god".
  function creatorView(m, kind, dupId) {
    const slug = m.project.slug, key = `${slug}:${kind}:${dupId || "new"}`;
    const nations = numberedNations(m), mons = projectMonsters(m);
    const sn = selectedNation(m);
    const dr = draftOf(state.creates, key, () => ({ phase: "edit", preview: null, msg: null, results: null, searching: false,
      form: { mode: dupId ? "duplicate" : "new", source_id: dupId ? String(dupId) : "", donorSource: "catalog", donorQuery: "", donorId: "", donorName: "",
        projectDonor: "", name: "", descr: "", role: kind === "god" ? "god" : "troop", nation: String(sn && Number.isInteger(sn.id) ? sn.id : (nations[0] || {}).id ?? ""),
        recruit: "fort", site: "", startdom: "", pathcost: "", gcost: "", magic: {} } }));
    const f = dr.form;
    const holder = el("section", { class: "panel editor creator", "aria-labelledby": `create-h-${kind}` });
    escapeReview(holder, () => dr.phase === "review", () => { dr.phase = "edit"; redraw(REVIEW_TRIGGER); });
    const url = `/api/projects/${encodeURIComponent(slug)}/create/monster`;
    const back = kind === "god" ? route("p", slug, "pretenders") : route("p", slug, "units");
    const reload = () => { state.models.delete(slug); dr.msg = null; render(); };
    function body() {
      const b = { expected_sha256: m.provenance.sha256, mode: f.mode, role: f.role, name: f.name, descr: f.descr || null };
      if (f.mode === "new") b.donor = f.donorSource === "catalog" ? { source: "catalog", id: Number(f.donorId) } : { source: "project", id: Number(f.projectDonor) };
      else b.source_id = Number(f.source_id);
      if (f.role !== "none") b.nation = Number(f.nation);
      if (f.role === "troop" || f.role === "commander") { b.recruit = f.recruit; if (f.recruit === "site") b.site = Number(f.site); }
      if (f.role === "god" && f.mode === "new") {
        const g = { startdom: Number(f.startdom), pathcost: Number(f.pathcost), magic: {} };
        if (String(f.gcost).trim() !== "") g.gcost = Number(f.gcost);
        for (const [p, v] of Object.entries(f.magic)) if (String(v).trim() !== "") g.magic[p] = Number(v);
        b.god = g;
      }
      return b;
    }
    // Client-side draft checks (the server checks everything again).
    function problems() {
      const out = {};
      const intIn = (v, lo, hi) => /^\d+$/.test(String(v).trim()) && Number(v) >= lo && Number(v) <= hi;
      if (!f.name.trim()) out.name = "Enter a name.";
      else if (/["#\r\n\t]/.test(f.name) || f.name.length > 60) out.name = "Up to 60 characters, no double quotes or #.";
      if (/["#\r\n\t]/.test(f.descr) || f.descr.length > 1999) out.descr = "Up to 1999 characters, no double quotes, # or line breaks.";
      if (f.mode === "new" && f.donorSource === "catalog" && !f.donorId) out.donor = "Search the catalog and choose a donor.";
      if (f.mode === "new" && f.donorSource === "project" && !f.projectDonor) out.donor = "Choose a project unit as donor.";
      if (f.mode === "duplicate" && !f.source_id) out.source_id = "Choose the project unit to copy.";
      if (f.role !== "none" && !f.nation) out.nation = "Choose a nation.";
      if ((f.role === "troop" || f.role === "commander") && f.recruit === "site" && !f.site) out.site = "Choose a start site of this nation.";
      if (f.role === "god" && f.mode === "new") {
        if (!intIn(f.startdom, 1, 10)) out.startdom = "Required: 1-10.";
        if (!intIn(f.pathcost, 1, 200)) out.pathcost = "Required: 1-200.";
        if (String(f.gcost).trim() !== "" && !intIn(f.gcost, 0, 19999)) out.gcost = "0-19999, or leave blank.";
        for (const [p, v] of Object.entries(f.magic)) if (String(v).trim() !== "" && !intIn(v, 1, 10)) out[`magic-${p}`] = "1-10";
      }
      if (f.mode === "duplicate" && f.role === "god") { const s = mons.find((u) => String(u.id) === f.source_id); if (s && !isGod(s)) out.role = "This unit has no #startdom/#pathcost; duplicate it as a unit, then set them with Edit."; }
      return out;
    }
    let showErrors = false;
    async function searchDonors(q) {
      dr.searching = true; dr.results = null; redrawResults();
      try { dr.results = (await getJSON(`/api/projects/${encodeURIComponent(slug)}/donors?q=${encodeURIComponent(q)}`)).result; }
      catch (e) { dr.results = { error: e }; }
      dr.searching = false; redrawResults();
    }
    const resultsBox = el("div", { class: "donor-results", "aria-live": "polite" });
    function redrawResults() {
      if (dr.searching) { resultsBox.replaceChildren(stateBox("loading", "Searching the catalog...")); return; }
      const r = dr.results;
      if (!r) { resultsBox.replaceChildren(); return; }
      if (r.error) { resultsBox.replaceChildren(errorBox(r.error, "catalog units")); return; }
      if (!r.results.length) { resultsBox.replaceChildren(el("p", { class: "muted", text: "No catalog units match." })); return; }
      resultsBox.replaceChildren(el("ul", { class: "donor-list", "aria-label": "Catalog units" }, r.results.map((x) => el("li", null,
        el("button", { type: "button", class: "btn btn-small" + (String(x.id) === f.donorId ? " is-picked" : ""), "aria-pressed": String(x.id) === f.donorId ? "true" : "false",
          onclick: () => { f.donorId = String(x.id); f.donorName = x.name; dr.msg = null; redraw("#donor-picked"); } }, `${x.name} (#${x.id})`)))),
        r.truncated ? el("p", { class: "faint", text: `Showing ${r.results.length} of ${r.total_matches}; refine the search.` }) : null);
    }
    function redraw(focusSel) {
      const errs = showErrors ? problems() : {};
      const head = el("h3", { id: `create-h-${kind}`, tabindex: "-1" }, f.mode === "duplicate" ? `Duplicate ${kind === "god" ? "pretender" : "unit"}` : kind === "god" ? "New pretender god" : "New unit");
      const busy = dr.msg && dr.msg.kind === "busy" ? stateBox("loading", dr.msg.text) : null;
      const err = dr.msg && dr.msg.kind === "err" ? writeError(dr.msg.err, reload) : null;
      if (dr.phase === "review" && dr.preview) {
        holder.replaceChildren(head, busy || reviewBlock(dr.preview, kind === "god" ? "Create god" : "Create unit",
          () => runWrite(dr, url, body(), false, redraw, (r) => {
            state.creates.delete(key);
            const href = r.role === "god" ? routeNation(String(f.nation), "p", slug, "pretenders", `project-${r.id}`)
              : r.role === "none" ? routeNation(N_NONE, "p", slug, "units", r.id) : routeNation(String(f.nation), "p", slug, "units", r.id);
            afterWrite(slug, href, `Created #${r.id}. Backup: ${r.backup}`, r, `Created ${kind === "god" ? "pretender" : "unit"} #${r.id}`);
          }), () => { dr.phase = "edit"; redraw(REVIEW_TRIGGER); }));
        if (focusSel) { const t = holder.querySelector(focusSel); if (t) t.focus(); }
        return;
      }
      const g = [];
      // Source
      const modeSel = bindInput(el("select", { class: "input", id: `cr-mode-${kind}` },
        el("option", { value: "new", text: "From a donor (copies its stats)" }), el("option", { value: "duplicate", text: "Duplicate a project unit (exact copy)" })), dr, "mode", () => { if (f.mode === "duplicate" && f.role !== "god") f.role = "troop"; redraw(`#cr-mode-${kind}`); });
      modeSel.value = f.mode;
      const src = [labelled(`cr-mode-${kind}`, "Start from", modeSel)];
      if (f.mode === "new") {
        const dsrc = bindInput(el("select", { class: "input", id: `cr-dsrc-${kind}` }, el("option", { value: "catalog", text: "Vanilla catalog unit" }),
          el("option", { value: "project", text: "Unit defined in this project" }, )), dr, "donorSource", () => redraw(`#cr-dsrc-${kind}`));
        dsrc.value = f.donorSource;
        src.push(labelled(`cr-dsrc-${kind}`, "Donor source", dsrc));
        if (f.donorSource === "catalog") {
          const q = el("input", { class: "input", type: "search", id: `cr-q-${kind}`, value: f.donorQuery, placeholder: "Name or id, e.g. Hoplite or 199", autocomplete: "off" });
          q.addEventListener("input", () => { f.donorQuery = q.value; });
          q.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); if (q.value.trim()) searchDonors(q.value.trim()); } });
          const btn = el("button", { type: "button", class: "btn btn-small", disabled: !catalogOf(m) || null, onclick: () => { if (q.value.trim()) searchDonors(q.value.trim()); else q.focus(); } }, "Search");
          src.push(el("div", { class: "edit-field wide" }, el("label", { for: q.id, text: "Search catalog units" }), el("div", { class: "edit-control" }, q, btn), resultsBox,
            el("div", { id: "donor-picked", tabindex: "-1", class: f.donorId ? "picked" : "faint" }, f.donorId ? ["Donor: ", el("strong", { text: `${f.donorName} (#${f.donorId})` })] : "No donor chosen yet."),
            errs.donor ? el("div", { class: "field-err", text: errs.donor }) : null));
          redrawResults();
        } else {
          const pd = bindInput(el("select", { class: "input", id: `cr-pd-${kind}` }, el("option", { value: "", text: "Choose…" }),
            mons.map((u) => el("option", { value: String(u.id), text: `${txt(u.name)} (#${u.id})` }))), dr, "projectDonor");
          pd.value = f.projectDonor;
          src.push(labelled(pd.id, "Project donor", pd, "#copystats/#copyspr of a unit defined earlier in this .dm.", errs.donor));
        }
      } else {
        const pool = kind === "god" ? mons.filter(isGod) : mons;
        const sd = bindInput(el("select", { class: "input", id: `cr-src-${kind}` }, el("option", { value: "", text: "Choose…" }),
          pool.map((u) => el("option", { value: String(u.id), text: `${txt(u.name)} (#${u.id})` }))), dr, "source_id");
        sd.value = f.source_id;
        src.push(labelled(sd.id, kind === "god" ? "Project god to copy" : "Project unit to copy", sd, "The whole block is copied as written (unknown commands, comments, sprite paths); only the id, name and description change.", errs.source_id));
      }
      g.push(el("fieldset", { class: "edit-group" }, el("legend", { text: "Source" }), el("div", { class: "edit-grid creator-grid" }, src),
        f.mode === "new" ? el("p", { class: "panel-note", text: "#copystats copies the donor's stats, equipment, magic and abilities; #copyspr borrows its sprite until you upload art. Refine values afterwards with Edit." }) : null));
      // Identity
      const nm = bindInput(el("input", { class: "input", id: `cr-name-${kind}`, value: f.name, maxlength: "60", autocomplete: "off", "aria-invalid": errs.name ? "true" : null }), dr, "name");
      const ds = bindInput(el("textarea", { class: "input", id: `cr-descr-${kind}`, rows: "3", maxlength: "1999", "aria-invalid": errs.descr ? "true" : null }), dr, "descr");
      ds.value = f.descr;
      g.push(el("fieldset", { class: "edit-group" }, el("legend", { text: "Name and description" }), el("div", { class: "edit-grid creator-grid" },
        labelled(nm.id, "Name", nm, null, errs.name), el("div", { class: "edit-field wide" }, el("label", { for: ds.id, text: "Description (optional)" }), ds,
          el("div", { class: "field-meta faint", text: f.mode === "duplicate" ? "Blank keeps the copied description." : "One paragraph; no line breaks or double quotes." }), errs.descr ? el("div", { class: "field-err", text: errs.descr }) : null))));
      // Assignment
      const asg = [];
      if (kind !== "god") {
        const roleSel = bindInput(el("select", { class: "input", id: `cr-role-${kind}` }, el("option", { value: "troop", text: "Troop" }), el("option", { value: "commander", text: "Commander" }),
          el("option", { value: "none", text: "Hero / summon (not recruited)" })), dr, "role", () => redraw(`#cr-role-${kind}`));
        roleSel.value = f.role;
        asg.push(labelled(roleSel.id, "Role", roleSel, null, errs.role));
      } else if (errs.role) asg.push(el("div", { class: "field-err", text: errs.role }));
      if (f.role !== "none") {
        const ns = bindInput(el("select", { class: "input", id: `cr-nation-${kind}` }, el("option", { value: "", text: "Choose…" }),
          nations.map((n) => el("option", { value: String(n.id), text: nationLabel(n) }))), dr, "nation", () => { f.site = ""; redraw(`#cr-nation-${kind}`); });
        ns.value = f.nation;
        asg.push(labelled(ns.id, "Nation", ns, nations.length ? null : "This project has no numbered #selectnation block; create a nation first.", errs.nation));
      }
      if (f.role === "troop" || f.role === "commander") {
        const n = nations.find((x) => String(x.id) === f.nation), sites = startSitesOf(m, n);
        const rs = bindInput(el("select", { class: "input", id: `cr-rec-${kind}` }, el("option", { value: "fort", text: `Forts (${f.role === "troop" ? "#addrecunit" : "#addreccom"})` }),
          el("option", { value: "site", text: `Capital start site (${f.role === "troop" ? "#homemon" : "#homecom"})`, disabled: !sites.length || null })), dr, "recruit", () => redraw(`#cr-rec-${kind}`));
        rs.value = f.recruit;
        asg.push(labelled(rs.id, "Recruited at", rs, sites.length ? null : "No project start site for this nation."));
        if (f.recruit === "site") {
          const ss = bindInput(el("select", { class: "input", id: `cr-site-${kind}` }, el("option", { value: "", text: "Choose…" }), sites.map((s) => el("option", { value: String(s.id), text: `${txt(s.name)} (#${s.id})` }))), dr, "site");
          ss.value = f.site;
          asg.push(labelled(ss.id, "Start site", ss, null, errs.site));
        }
      }
      g.push(el("fieldset", { class: "edit-group" }, el("legend", { text: kind === "god" ? "Nation (pretender list)" : "Recruitment" }), el("div", { class: "edit-grid creator-grid" }, asg),
        el("p", { class: "panel-note", text: kind === "god" ? "Adds #addgod to the chosen nation only. New gods get #homerealm 0, so no realm makes them available implicitly; they are never recruitable."
          : "Exactly one line is added to the chosen nation or start site; nothing is assigned automatically." })));
      // God design (new gods)
      if (f.role === "god" && f.mode === "new") {
        const num = (k, label, hint) => { const i = bindInput(el("input", { class: "input num-input", id: `cr-${k}`, inputmode: "numeric", value: f[k], autocomplete: "off", "aria-invalid": errs[k] ? "true" : null }), dr, k); return labelled(i.id, label, i, hint, errs[k]); };
        const magic = Object.entries(PATH_NAMES).map(([p, name]) => {
          const i = el("input", { class: "input num-input", id: `cr-mag-${p}`, inputmode: "numeric", value: f.magic[p] || "", autocomplete: "off", "aria-invalid": errs[`magic-${p}`] ? "true" : null });
          i.addEventListener("input", () => { f.magic[p] = i.value; dr.msg = null; });
          return labelled(i.id, `${name} (${p})`, i, null, errs[`magic-${p}`]);
        });
        g.push(el("fieldset", { class: "edit-group" }, el("legend", { text: "Pretender design" }),
          el("div", { class: "edit-grid creator-grid" }, num("startdom", "Starting dominion", "Required, 1-10 (#startdom)."), num("pathcost", "New path cost", "Required, 1-200 (#pathcost)."),
            num("gcost", "Design cost (optional)", "#gcost; 10000+base = autocalc.")),
          el("h4", { text: "Starting magic (optional, 1-10 each)" }), el("div", { class: "edit-grid creator-grid magic-grid" }, magic),
          el("p", { class: "panel-note", text: "#startdom and #pathcost make the monster a selectable god. Final design-point costs are computed by the game. Holy (H) magic also needs #holy." })));
      }
      const nErr = Object.keys(problems()).length;
      const actions = el("div", { class: "btn-row edit-actions" },
        el("button", { type: "submit", class: "btn", ...RT }, "Review"),
        el("a", { class: "btn btn-ghost", href: back, onclick: () => { state.creates.delete(key); } }, "Cancel"),
        el("span", { class: "edit-count", role: "status", text: showErrors && nErr ? `${nErr} field(s) need attention` : "Nothing is written until you confirm the review." }));
      holder.replaceChildren(...[head, err, busy].filter(Boolean), el("form", { class: "edit-form", novalidate: true, onsubmit: (e) => {
        e.preventDefault(); showErrors = true;
        if (Object.keys(problems()).length) { redraw("[aria-invalid=true], .field-err"); return; }
        runWrite(dr, url, body(), true, redraw);
      } }, g, actions));
      if (focusSel) { const t = holder.querySelector(focusSel); if (t) { if (!t.hasAttribute("tabindex") && t.classList.contains("field-err")) t.setAttribute("tabindex", "-1"); t.focus(); } }
    }
    redraw();
    return el("div", { class: "stack" }, el("p", null, el("a", { href: back, text: kind === "god" ? "← Pretenders" : "← Units" })), holder);
  }
  function createButtons(m, kind, dupId) {
    const slug = m.project.slug, tab = kind === "god" ? "pretenders" : "units";
    if (!CSRF) return el("p", { class: "faint", text: "Creating is unavailable: no editor token from this server." });
    return el("div", { class: "btn-row create-bar" },
      el("a", { class: "btn btn-small", href: route("p", slug, tab, "~new") }, kind === "god" ? "New god" : "New unit"),
      dupId ? el("a", { class: "btn btn-small btn-ghost", href: route("p", slug, tab, `~dup-${dupId}`) }, "Duplicate") : null);
  }
  const creatorArg = (sel) => typeof sel === "string" && /^~(new|dup-\d+)$/.test(sel) ? (sel === "~new" ? { dup: null } : { dup: Number(sel.slice(5)) }) : null;

  // New nation: ids from core, explicit roster, start army, sites, realms and custom gods only.
  function nationCreator(m) {
    const slug = m.project.slug, key = `${slug}:nation`;
    const mons = projectMonsters(m), gods = mons.filter(isGod), units = mons.filter((u) => !isGod(u) || u.role !== "pretender");
    const sites = m.sites.filter((s) => s.new && Number.isInteger(s.id) && s.name);
    const dr = draftOf(state.creates, key, () => ({ phase: "edit", preview: null, msg: null,
      form: { name: "", epithet: "", era: "1", descr: "", sites: [], realms: [], gods: [], troops: [], commanders: [], startcom: "", startscout: "", su1: "", su1n: "20", su2: "", su2n: "20" } }));
    const f = dr.form;
    const url = `/api/projects/${encodeURIComponent(slug)}/create/nation`;
    const holder = el("section", { class: "panel editor creator", "aria-labelledby": "nation-create-h" });
    escapeReview(holder, () => dr.phase === "review", () => { dr.phase = "edit"; redraw(REVIEW_TRIGGER); });
    const reload = () => { state.models.delete(slug); dr.msg = null; render(); };
    let showErrors = false;
    function problems() {
      const o = {};
      for (const [k, lim] of [["name", 60], ["epithet", 60]]) if (!f[k].trim()) o[k] = "Required."; else if (/["#\r\n\t]/.test(f[k]) || f[k].length > lim) o[k] = `Up to ${lim} characters, no double quotes or #.`;
      if (/["#\r\n\t]/.test(f.descr) || f.descr.length > 1999) o.descr = "Up to 1999 characters, no double quotes, # or line breaks.";
      if (f.sites.length > 4) o.sites = "At most 4 start sites.";
      for (const k of ["su1", "su2"]) if (f[k] && !(/^\d+$/.test(f[`${k}n`]) && +f[`${k}n`] >= 1 && +f[`${k}n`] <= 60)) o[k] = "Squad size 1-60.";
      if (f.su1 && f.su2 && f.su1 === f.su2) o.su2 = "Choose a different unit or leave blank.";
      return o;
    }
    function body() {
      const b = { expected_sha256: m.provenance.sha256, name: f.name, epithet: f.epithet, era: Number(f.era), descr: f.descr || null,
        sites: f.sites.map(Number), realms: f.realms.map(Number), gods: f.gods.map(Number), troops: f.troops.map(Number), commanders: f.commanders.map(Number),
        startcom: f.startcom ? [Number(f.startcom)] : [], startscout: f.startscout ? [Number(f.startscout)] : [], startunits: [] };
      for (const k of ["su1", "su2"]) if (f[k]) b.startunits.push({ id: Number(f[k]), count: Number(f[`${k}n`]) });
      return b;
    }
    function checks(name, legend, items, note) {
      const list = f[name];
      return el("fieldset", { class: "edit-group" }, el("legend", { text: legend }),
        items.length ? el("div", { class: "check-grid" }, items.map(([v, label]) => {
          const id = `nc-${name}-${v}`;
          const cb = el("input", { type: "checkbox", id, checked: list.includes(String(v)) || null });
          cb.addEventListener("change", () => { const i = list.indexOf(String(v)); if (cb.checked && i < 0) list.push(String(v)); if (!cb.checked && i >= 0) list.splice(i, 1); dr.msg = null; });
          return el("label", { class: "check", for: id }, cb, " ", label);
        })) : el("p", { class: "muted", text: "None available in this project." }),
        note ? el("p", { class: "panel-note", text: note }) : null);
    }
    const monSel = (k, label, pool) => { const s = bindInput(el("select", { class: "input", id: `nc-${k}` }, el("option", { value: "", text: "None" }), pool.map((u) => el("option", { value: String(u.id), text: `${txt(u.name)} (#${u.id})` }))), dr, k); s.value = f[k]; return labelled(s.id, label, s); };
    function redraw(focusSel) {
      const errs = showErrors ? problems() : {};
      const head = el("h3", { id: "nation-create-h", tabindex: "-1", text: "New nation" });
      const busy = dr.msg && dr.msg.kind === "busy" ? stateBox("loading", dr.msg.text) : null;
      const err = dr.msg && dr.msg.kind === "err" ? writeError(dr.msg.err, reload) : null;
      if (dr.phase === "review" && dr.preview) {
        holder.replaceChildren(head, busy || reviewBlock(dr.preview, "Create nation", () => runWrite(dr, url, body(), false, redraw, (r) => {
          state.creates.delete(key); rememberNation(slug, String(r.id));
          afterWrite(slug, routeNation(String(r.id), "p", slug, "nation", r.id), `Created nation #${r.id}. Backup: ${r.backup}`, r, `Created nation #${r.id}`);
        }), () => { dr.phase = "edit"; redraw(REVIEW_TRIGGER); }));
        if (focusSel) { const t = holder.querySelector(focusSel); if (t) t.focus(); }
        return;
      }
      const inp = (k, label, max) => { const i = bindInput(el("input", { class: "input", id: `nc-${k}`, value: f[k], maxlength: String(max), autocomplete: "off", "aria-invalid": errs[k] ? "true" : null }), dr, k); return labelled(i.id, label, i, null, errs[k]); };
      const era = bindInput(el("select", { class: "input", id: "nc-era" }, [["1", "Early Age"], ["2", "Middle Age"], ["3", "Late Age"]].map(([v, l]) => el("option", { value: v, text: l }))), dr, "era");
      era.value = f.era;
      const ds = bindInput(el("textarea", { class: "input", id: "nc-descr", rows: "3", maxlength: "1999", "aria-invalid": errs.descr ? "true" : null }), dr, "descr");
      ds.value = f.descr;
      const squad = (k, label) => {
        const s = bindInput(el("select", { class: "input", id: `nc-${k}` }, el("option", { value: "", text: "None" }), units.map((u) => el("option", { value: String(u.id), text: `${txt(u.name)} (#${u.id})` }))), dr, k);
        s.value = f[k];
        const n = bindInput(el("input", { class: "input num-input", id: `nc-${k}n`, inputmode: "numeric", value: f[`${k}n`], "aria-label": `${label} size` }), dr, `${k}n`);
        return el("div", { class: "edit-field" }, el("label", { for: s.id, text: label }), el("div", { class: "edit-control" }, s, n), errs[k] ? el("div", { class: "field-err", text: errs[k] }) : null);
      };
      holder.replaceChildren(...[head, err, busy].filter(Boolean),
        el("p", { class: "panel-note", text: "Allocates a free nation id (150+) from the core, then appends #selectnation with #name, #epithet and #era first and #clearnation after them. Only what you tick is added. Write the design brief first (docs/NATION-DESIGN.md); flags, colours and further commands can be added later. Units shared with another nation stay shared." }),
        el("form", { class: "edit-form", novalidate: true, onsubmit: (e) => {
          e.preventDefault(); showErrors = true;
          if (Object.keys(problems()).length) { redraw("[aria-invalid=true]"); return; }
          runWrite(dr, url, body(), true, redraw);
        } },
          el("fieldset", { class: "edit-group" }, el("legend", { text: "Identity" }), el("div", { class: "edit-grid creator-grid" }, inp("name", "Name", 60), inp("epithet", "Epithet", 60), labelled("nc-era", "Era", era)),
            el("div", { class: "edit-field wide" }, el("label", { for: "nc-descr", text: "Lore / description (optional)" }), ds, errs.descr ? el("div", { class: "field-err", text: errs.descr }) : null)),
          checks("troops", "Recruitable troops (#addrecunit)", units.map((u) => [u.id, `${txt(u.name)} (#${u.id})`])),
          checks("commanders", "Recruitable commanders (#addreccom)", units.map((u) => [u.id, `${txt(u.name)} (#${u.id})`])),
          el("fieldset", { class: "edit-group" }, el("legend", { text: "Start army (optional)" }), el("div", { class: "edit-grid creator-grid" },
            monSel("startcom", "Starting commander (#startcom)", units), monSel("startscout", "Scout (#startscout)", units), squad("su1", "Squad 1"), squad("su2", "Squad 2")),
            el("p", { class: "panel-note", text: "Nothing is guessed: leave blank to set the start army later. The review warns when no starting commander is chosen." })),
          checks("sites", "Start sites (#startsite, max 4)", sites.map((s) => [s.id, `${txt(s.name)} (#${s.id})${s.start_site_of.length ? " · shared" : ""}`]), errs.sites || "Project #newsite blocks with a name; #startsite refers to them by name."),
          checks("gods", "Custom pretender gods (#addgod)", gods.map((u) => [u.id, `${txt(u.name)} (#${u.id})`]), "Only project monsters with #startdom and #pathcost."),
          checks("realms", "Home realms (#homerealm, optional)", Object.entries({ 1: "North", 2: "Celtic", 3: "Mediterranean", 4: "Far East", 5: "Middle East", 6: "Middle America", 7: "Africa", 8: "India", 9: "Deeps", 10: "Default" }).map(([k, v]) => [k, `${k} ${v}`]),
            "Adds vanilla gods of these realms. Realm 10 (Default) is added only when ticked."),
          el("div", { class: "btn-row edit-actions" }, el("button", { type: "submit", class: "btn", ...RT }, "Review"),
            el("a", { class: "btn btn-ghost", href: route("p", slug, "nation"), onclick: () => { state.creates.delete(key); } }, "Cancel"),
            el("span", { class: "edit-count", text: "Nothing is written until you confirm the review." }))));
      if (focusSel) { const t = holder.querySelector(focusSel); if (t) t.focus(); }
    }
    redraw();
    return el("div", { class: "stack" }, el("p", null, el("a", { href: route("p", slug, "nation"), text: "← Nation" })), holder);
  }

  // ---------- existing-nation editor ----------
  // Edits one #selectnation block through GET/POST .../nations/<id>/edit. The draft keeps only what the user asked for
  // (identity text, list adds/removes, start-army choices) and is compared again with the latest file after a reload,
  // so conflicts and failed checks never lose input.
  const NATION_IDENT = ["name", "epithet", "era", "descr", "summary", "brief"];
  const NATION_LISTS = [["troops", "Fort troops (#addrecunit)"], ["commanders", "Fort commanders (#addreccom)"]];
  function nationDraft(slug, id) {
    return draftOf(state.nationEditors, `${slug}:${id}`, () => ({ open: false, st: null, phase: "edit", preview: null, msg: null,
      ident: {}, add: {}, remove: {}, start: {} }));
  }
  const listHas = (o, f, v) => (o[f] || []).includes(v);
  const listToggle = (o, f, v, on) => { const a = o[f] || (o[f] = []); const i = a.indexOf(v); if (on && i < 0) a.push(v); if (!on && i >= 0) a.splice(i, 1); };
  // Draft -> server changes, plus per-field input errors (the server checks everything again).
  function nationChanges(nd) {
    const st = nd.st, changes = [], errors = {};
    for (const k of NATION_IDENT) {
      if (!(k in nd.ident)) continue;
      const e = st.identity[k], raw = String(nd.ident[k]);
      if (k === "era") { if (Number(raw) !== e.value) changes.push({ field: k, op: "set", value: Number(raw) }); continue; }
      const t = raw.trim();
      if (t === (e.value === null ? "" : String(e.value).trim())) continue;
      if (!t) { errors[k] = e.value === null ? null : "Cannot be blank here; removing identity lines is not supported."; if (!errors[k]) delete errors[k]; continue; }
      if (/["#\t\r\n]/.test(t) || t.length > e.max) { errors[k] = `Up to ${e.max} characters, no double quotes, #, tabs or line breaks.`; continue; }
      changes.push({ field: k, op: "set", value: t });
    }
    for (const [f, ls] of Object.entries(st.lists)) {
      const liveKeys = ls.live.map((x) => x.key);
      for (const key of nd.remove[f] || []) if (liveKeys.includes(key)) changes.push({ field: f, op: "remove", value: key });
      for (const v of nd.add[f] || []) if (!ls.live.some((x) => x.value === v || x.id === v)) changes.push({ field: f, op: "add", value: v });
    }
    for (const f of ["startcom", "startscout", "squad1", "squad2"]) {
      const c = nd.start[f]; if (!c) continue;
      if (c.op === "remove") { changes.push({ field: f, op: "remove" }); continue; }
      if (f === "startcom" || f === "startscout") { if (String(c.value) !== String(st.start[f].key)) changes.push({ field: f, op: "set", value: Number(c.value) }); continue; }
      const cur = st.start[f], unit = c.unit === "" ? cur.type.key : Number(c.unit), cnt = String(c.count).trim();
      if (unit === null || unit === undefined) { errors[f] = "Choose a unit for this squad."; continue; }
      if (!/^\d+$/.test(cnt) || +cnt < 1 || +cnt > st.max_count) { errors[f] = `Squad size 1-${st.max_count}.`; continue; }
      if (String(unit) !== String(cur.type.key) || +cnt !== cur.count.value) changes.push({ field: f, op: "set", value: { unit, count: +cnt } });
    }
    return { changes, errors };
  }
  function nationEditorSection(m, n) {
    if (!Number.isInteger(n.id) || !CSRF) return null;
    const slug = m.project.slug, box = el("div", { class: "stack" });
    // Opening and closing redraws only this section, keeping scroll position and focus.
    const draw = (focus) => {
      const nd = nationDraft(slug, n.id), cnt = nd.st ? nationChanges(nd).changes.length : 0;
      const btn = el("button", { type: "button", class: "btn", "aria-expanded": nd.open ? "true" : "false", "aria-controls": `nation-editor-${n.id}`,
        onclick: () => { nd.open = !nd.open; nd.msg = null; draw(true); } }, nd.open ? "Close editor" : "Edit nation");
      fillKids(box, el("div", { class: "btn-row edit-bar" }, btn,
        cnt ? badge(`${cnt} unsaved change(s)`, "warn") : null,
        nd.msg && nd.msg.kind === "ok" ? el("span", { class: "edit-ok", role: "status", text: nd.msg.text }) : null),
        nd.open ? nationEditor(m, n, () => draw(true)) : null);
      if (focus) btn.focus({ preventScroll: true });
    };
    draw(false);
    return box;
  }
  function nationEditor(m, n, onClose) {
    const slug = m.project.slug, id = n.id, nd = nationDraft(slug, id);
    const url = `/api/projects/${encodeURIComponent(slug)}/nations/${encodeURIComponent(id)}/edit`;
    const holder = el("section", { class: "panel editor nation-editor", id: `nation-editor-${id}`, "aria-labelledby": `nation-editor-h-${id}` });
    const head = () => el("h3", { id: `nation-editor-h-${id}`, tabindex: "-1", text: `Edit nation: ${txt((nd.st && nd.st.identity.name.value) || n.name || id)}` });
    const load = async () => {
      holder.replaceChildren(head(), stateBox("loading", "Reading the current .dm..."));
      try { nd.st = (await getJSON(url)).result; nd.phase = "edit"; nd.preview = null; draw(); }
      catch (e) { holder.replaceChildren(head(), errorBox(e, "the nation editor"), el("div", { class: "btn-row" }, el("button", { type: "button", class: "btn", onclick: load }, "Retry"))); }
    };
    const countBox = el("span", { class: "edit-count", role: "status", "aria-live": "polite" });
    let reviewBtn;
    function updateCount() {
      const { changes, errors } = nationChanges(nd), nErr = Object.keys(errors).length;
      countBox.textContent = nErr ? `${nErr} field(s) need fixing` : changes.length ? `${changes.length} change(s) ready to review` : "No changes yet";
      if (reviewBtn) reviewBtn.disabled = !changes.length || nErr > 0;
    }
    async function send(preview) {
      const { changes } = nationChanges(nd);
      nd.msg = { kind: "busy", text: preview ? "Checking the changes..." : "Saving..." }; draw();
      try {
        const r = await postJSON(url, { expected_sha256: nd.st.sha256, changes, preview });
        if (preview) { nd.preview = r; nd.phase = "review"; nd.msg = null; draw("[data-focus=review]"); return; }
        state.nationEditors.delete(`${slug}:${id}`);
        const fresh = nationDraft(slug, id);
        fresh.msg = { kind: "ok", text: r.written ? `Saved to the .dm. Backup: ${r.backup}` : "Nothing changed." };
        state.models.delete(slug);
        recordReceipt(slug, `Saved nation #${id}`, r);
        toast(r.written ? "Nation saved to the .dm" : "Nothing to save");
        await loadProjects(true);
        render().then(() => { const b = $(`[aria-controls="nation-editor-${id}"]`); if (b) b.focus(); });
      } catch (e) { nd.phase = "edit"; nd.msg = { kind: "err", err: e }; draw("[data-focus=err]"); }
    }
    const reload = () => { nd.st = null; nd.msg = null; nd.preview = null; state.models.delete(slug); load(); };
    const lineNote = (e, where) => e.blocked ? el("div", { class: "field-err", text: e.blocked })
      : el("div", { class: "field-meta faint", text: e.line ? `line ${e.line}` : where });
    function identityGroup(st) {
      const fields = NATION_IDENT.map((k) => {
        const e = st.identity[k], fid = `ne-${id}-${k}`;
        const val = k in nd.ident ? nd.ident[k] : e.value === null ? "" : String(e.value);
        const where = st.catalog && st.catalog[k] ? `not authored; catalog: ${st.catalog[k]}. A new line goes right after #selectnation.` : "not authored; a new line goes right after #selectnation, before any reset";
        let ctl;
        if (k === "era") {
          ctl = el("select", { class: "input", id: fid, disabled: e.blocked || null }, Object.entries(st.era_names).map(([v, l]) => el("option", { value: v, text: `${l} (#era ${v})` })),
            e.value === null ? el("option", { value: "", text: "not authored" }) : null);
          ctl.value = e.value === null && !(k in nd.ident) ? "" : val;
          ctl.addEventListener("change", () => { if (ctl.value === "") delete nd.ident[k]; else nd.ident[k] = ctl.value; nd.msg = null; updateCount(); });
        } else if (k === "name" || k === "epithet") {
          ctl = el("input", { class: "input", id: fid, value: val, maxlength: String(e.max), autocomplete: "off", disabled: e.blocked || null });
        } else {
          ctl = el("textarea", { class: "input", id: fid, rows: k === "descr" ? "5" : "2", maxlength: String(e.max), disabled: e.blocked || null });
          ctl.value = val;
        }
        if (k !== "era") ctl.addEventListener("input", () => { nd.ident[k] = ctl.value; nd.msg = null; const err = nationChanges(nd).errors[k]; ctl.setAttribute("aria-invalid", err ? "true" : "false"); errBox.textContent = err || ""; updateCount(); });
        const errBox = el("div", { class: "field-err", "aria-live": "polite", id: `${fid}-err`, text: nationChanges(nd).errors[k] || "" });
        ctl.setAttribute("aria-describedby", `${fid}-err ${fid}-hint`);
        const hint = lineNote(e, where); hint.id = `${fid}-hint`;
        return el("div", { class: "edit-field" + (k === "descr" || k === "summary" || k === "brief" ? " wide" : "") },
          el("label", { for: fid, text: `${e.label} (#${k})` }), ctl, hint,
          e.multiline ? el("div", { class: "faint", text: "The current text spans several lines; it stays as written unless you change it (line breaks cannot be entered here)." }) : null, errBox);
      });
      return el("fieldset", { class: "edit-group" }, el("legend", { text: "Identity" }), el("div", { class: "edit-grid creator-grid" }, fields),
        el("p", { class: "panel-note", text: "Existing lines are rewritten in place, so their position before or after #clearnation is kept. Text: no double quotes, # or line breaks." }));
    }
    // One checkbox list: live authored entries (kept or removed) plus project options (added or not).
    function checkList(st, f, legend, options, note) {
      const ls = st.lists[f];
      const liveIds = new Set(ls.live.map((x) => x.id ?? x.value));
      const rows = [];
      for (const it of ls.live) {
        const cid = `ne-${id}-${f}-l${it.line}`;
        const cb = el("input", { type: "checkbox", id: cid, checked: !listHas(nd.remove, f, it.key) || null, disabled: !it.removable || null,
          "aria-describedby": it.removable ? null : `${cid}-why` });
        cb.addEventListener("change", () => { listToggle(nd.remove, f, it.key, !cb.checked); nd.msg = null; lab.classList.toggle("row-removing", !cb.checked); updateCount(); });
        const origin = it.origin === "catalog" ? badge("vanilla", "info") : f === "realms" ? null : it.origin === "project" ? null : badge(it.unresolved || "unresolved", "warn");
        const lab = el("label", { class: "check" + (listHas(nd.remove, f, it.key) ? " row-removing" : ""), for: cid }, cb, " ", txt(it.label || it.key), " ", origin,
          el("span", { class: "faint", text: ` line ${it.line}` }));
        rows.push(el("div", null, lab, it.removable ? null : el("div", { class: "faint", id: `${cid}-why`, text: it.reason })));
      }
      for (const [v, label] of options) {
        if (liveIds.has(v)) continue;
        const cid = `ne-${id}-${f}-o${v}`;
        const cb = el("input", { type: "checkbox", id: cid, checked: listHas(nd.add, f, v) || null });
        cb.addEventListener("change", () => { listToggle(nd.add, f, v, cb.checked); nd.msg = null; updateCount(); });
        rows.push(el("label", { class: "check", for: cid }, cb, " ", label));
      }
      return el("fieldset", { class: "edit-group" }, el("legend", { text: legend }),
        rows.length ? el("div", { class: "check-grid" }, rows) : el("p", { class: "muted", text: "Nothing listed and no project options." }),
        ls.dead.length ? el("details", { class: "raw" }, el("summary", null, `${ls.dead.length} earlier line(s) already cleared (read-only)`),
          el("ul", { class: "inner" }, ls.dead.map((d) => el("li", null, el("code", { text: d.raw }), ` line ${d.line}: ${d.note}`)))) : null,
        el("p", { class: "panel-note" }, ls.last_reset ? `Entries after ${ls.last_reset.command} (line ${ls.last_reset.line}) are shown. ` : "",
          ls.inherited ? `This vanilla nation has no ${ls.resets.join("/")} here, so it may also inherit entries that are not listed; only project units can be removed losslessly. ` : "",
          note || ""));
    }
    function capitalPanel(st) {
      const cr = st.capital_roster;
      return el("fieldset", { class: "edit-group" }, el("legend", { text: "Capital-only recruitment (read-only, derived)" }),
        cr.length ? table(["Start site", "Recruits", "Command"], cr.flatMap((s) => (s.units.length ? s.units : [null]).map((u) => [
          el("a", { href: route("p", slug, "sites", s.site.id) }, `${txt(s.site.name)} (#${s.site.id})`),
          u ? monsterLink(slug, u.monster) : el("span", { class: "muted", text: "none" }),
          u ? el("span", null, el("code", { text: u.command }), " ", srcRef(slug, st.file, u.line), s.shared_with.length ? [" ", badge("shared site", "warn")] : null) : ""])))
          : el("p", { class: "muted", text: "No project start site of this nation recruits anything." }),
        el("p", { class: "panel-note", text: "#homecom/#homemon on start sites are recruitable only where the site is (the capital). They are edited on the site block and never change when you tick or untick fort entries here." }));
    }
    function startGroup(st) {
      const s = st.start, units = st.options.units.filter((u) => !u.god || u.role !== "pretender");
      const unitOpts = () => units.map((u) => el("option", { value: String(u.id), text: `${txt(u.name)} (#${u.id})` }));
      const cur = (e) => e.blocked ? `blocked: ${e.blocked}` : e.value === null ? "none authored" : `${txt(e.ref ? e.ref.label : e.key)} · line ${e.line}`;
      function single(f, label) {
        const e = s[f], c = nd.start[f], sid = `ne-${id}-${f}`;
        const sel = el("select", { class: "input", id: sid, disabled: e.blocked || null },
          el("option", { value: "", text: e.value === null ? "Keep: none" : `Keep: ${txt(e.ref ? e.ref.label : e.key)}` }), unitOpts(),
          e.value !== null ? el("option", { value: "__remove", text: "Remove the authored line" }) : null);
        sel.value = !c ? "" : c.op === "remove" ? "__remove" : String(c.value);
        sel.addEventListener("change", () => { if (!sel.value) delete nd.start[f]; else nd.start[f] = sel.value === "__remove" ? { op: "remove" } : { op: "set", value: sel.value }; nd.msg = null; updateCount(); });
        return el("div", { class: "edit-field" }, el("label", { for: sid, text: label }), sel, el("div", { class: "field-meta faint", text: cur(e) }));
      }
      function squad(f, label) {
        const e = s[f], c = nd.start[f] || { op: "set", unit: "", count: e.count.value ?? "" }, sid = `ne-${id}-${f}`;
        const blocked = e.type.blocked || e.count.blocked;
        const sel = el("select", { class: "input", id: sid, disabled: blocked || null },
          el("option", { value: "", text: e.type.value === null ? "Keep: none" : `Keep: ${txt(e.type.ref ? e.type.ref.label : e.type.key)}` }), unitOpts(),
          e.type.value !== null || e.count.value !== null ? el("option", { value: "__remove", text: "Remove the squad lines" }) : null);
        sel.value = c.op === "remove" ? "__remove" : String(c.unit);
        const num = el("input", { class: "input num-input", id: `${sid}-n`, inputmode: "numeric", value: String(c.count ?? ""), "aria-label": `${label} size`, disabled: blocked || c.op === "remove" || null });
        const errBox = el("div", { class: "field-err", "aria-live": "polite", text: nationChanges(nd).errors[f] || "" });
        const sync = () => {
          if (sel.value === "__remove") nd.start[f] = { op: "remove" };
          else if (sel.value === "" && String(num.value).trim() === String(e.count.value ?? "")) delete nd.start[f];
          else nd.start[f] = { op: "set", unit: sel.value, count: num.value };
          num.disabled = sel.value === "__remove";
          errBox.textContent = nationChanges(nd).errors[f] || ""; nd.msg = null; updateCount();
        };
        sel.addEventListener("change", sync); num.addEventListener("input", sync);
        return el("div", { class: "edit-field" }, el("label", { for: sid, text: label }), el("div", { class: "edit-control" }, sel, num),
          el("div", { class: "field-meta faint", text: blocked ? `blocked: ${blocked}` : e.type.value === null ? "none authored" : `${cur(e.type)}${e.count.value !== null ? ` × ${e.count.value}` : " (count unset: game default)"}` }), errBox);
      }
      return el("fieldset", { class: "edit-group" }, el("legend", { text: "Start army" }),
        el("div", { class: "edit-grid creator-grid" }, single("startcom", "Starting commander (#startcom)"), single("startscout", "Scout (#startscout)"),
          squad("squad1", "Squad 1 (#startunittype1/#startunitnbrs1)"), squad("squad2", "Squad 2 (#startunittype2/#startunitnbrs2)")),
        s.dead.length ? el("p", { class: "panel-note" }, `Lines before #startcom are already cleared by it: ${s.dead.map((d) => `${d.raw} (line ${d.line})`).join("; ")}.`) : null,
        el("p", { class: "panel-note", text: (s.inherited ? "This vanilla nation has no authored #startcom, so it may inherit its start army; removals are refused. " : "")
          + "Choices are limited to project units; the current entry (even a vanilla or unresolved one) is kept unless you change it. A new #startcom goes before the other start-army lines so it does not clear them." }));
    }
    function reviewPanel() {
      const p = nd.preview;
      return el("div", { class: "stack" },
        el("h4", { tabindex: "-1", "data-focus": "review", text: "Review before saving" }),
        table(["Field", "Change", "What happens"], p.plan.map((x) => [
          el("span", null, el("strong", { text: x.label }), x.label_value ? el("div", { class: "faint", text: x.label_value }) : null),
          el("span", null, badge(x.action, x.action === "remove" ? "warn" : x.action === "unchanged" ? "" : "authored"), " ",
            x.before ? el("code", { text: x.before }) : null, x.before && x.after ? " → " : null, x.after ? el("code", { text: x.after }) : null),
          el("span", { class: "muted", text: x.explanation })])),
        diffView(p.diff || "(no text change)"),
        el("p", { class: "panel-note", text: "Only the lines in the diff change. Defence, walls, flags, colours, AI and unknown commands, comments, order, newlines and encoding stay as written; start-site #homecom/#homemon lines are not touched. A backup of the previous .dm is kept." }),
        el("div", { class: "btn-row" },
          p.changed ? el("button", { type: "button", class: "btn", onclick: () => send(false) }, "Save to .dm")
            : el("span", { class: "muted", text: "Nothing to save: the file already says this." }),
          el("button", { type: "button", class: p.changed ? "btn btn-ghost" : "btn", onclick: () => { nd.phase = "edit"; nd.preview = null; draw(REVIEW_TRIGGER); } }, "Back to editing")));
    }
    function draw(focusSel) {
      const st = nd.st;
      const busy = nd.msg && nd.msg.kind === "busy" ? stateBox("loading", nd.msg.text) : null;
      const err = nd.msg && nd.msg.kind === "err" ? writeError(nd.msg.err, reload) : null;
      const intro = el("p", { class: "panel-note" }, "Writes into ", el("code", { text: `#selectnation ${id}` }), ` (lines ${st.line}–${st.end_line} of ${st.file}). ${st.basis}. `,
        st.resets.length ? ["Resets in the block: ", st.resets.map((r, i) => [i ? ", " : "", el("code", { text: r.command }), ` line ${r.line}`]), ". "] : "No resets in the block. ",
        "Kosmokrator never adds a reset; nothing is changed that you did not ask for.");
      if (nd.phase === "review" && nd.preview) { holder.replaceChildren(head(), intro, busy || reviewPanel()); focusIn(holder, focusSel); return; }
      const projUnits = st.options.units.filter((u) => u.role !== "pretender");
      reviewBtn = el("button", { type: "submit", class: "btn", ...RT }, "Review changes");
      const actions = el("div", { class: "btn-row edit-actions" }, reviewBtn,
        el("button", { type: "button", class: "btn btn-ghost", onclick: () => { state.nationEditors.delete(`${slug}:${id}`); if (onClose) onClose(); else render(); } }, "Cancel"), countBox);
      holder.replaceChildren(...[head(), intro, err, busy].filter(Boolean), el("form", { class: "edit-form", novalidate: true,
        onsubmit: (e) => { e.preventDefault(); if (!reviewBtn.disabled) send(true); } },
        identityGroup(st),
        el("div", { class: "grid-2" }, NATION_LISTS.map(([f, legend]) => checkList(st, f, legend, projUnits.map((u) => [u.id, `${txt(u.name)} (#${u.id})`]),
          "Unticking deletes only that authored line; ticking adds one line after the last live entry."))),
        capitalPanel(st),
        startGroup(st),
        checkList(st, "sites", `Start sites (#startsite, max ${st.max_start_sites})`, st.options.sites.map((s) => [s.id, `${txt(s.name)} (#${s.id})${s.start_site_of.filter((x) => x !== `nation:${id}`).length ? " · shared" : ""}`]),
          "Project #newsite blocks with a name; #startsite refers to them by name."),
        el("div", { class: "grid-2" },
          checkList(st, "gods", "Custom pretender gods (#addgod)", st.options.units.filter((u) => u.god).map((u) => [u.id, `${txt(u.name)} (#${u.id})`]), "Only project monsters with #startdom and #pathcost can be added."),
          checkList(st, "realms", "Home realms (#homerealm)", Object.entries(st.options.realms).map(([k, v]) => [Number(k), `${k} ${v}`]), "Realm 10 (Default) is added only when ticked.")),
        actions));
      updateCount();
      focusIn(holder, focusSel);
    }
    escapeReview(holder, () => nd.phase === "review", () => { nd.phase = "edit"; draw(REVIEW_TRIGGER); });
    if (nd.st) draw(); else load();
    return holder;
  }

  // Art manager: upload PNG frames for a project #newmonster. Native preview from a Blob URL (CSP allows blob:),
  // optional crisp zoom; the server decodes and checks every frame again before anything is written.
  const MAX_FRAME_BYTES = 2 * 1024 * 1024;
  function toBase64(buf) {
    const bytes = new Uint8Array(buf); let s = "";
    for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    return btoa(s);
  }
  function artManager(m, u, existing) {
    const slug = m.project.slug, key = `${slug}:${u.id}`;
    const dr = draftOf(state.arts, key, () => ({ open: false, frames: {}, zoom: 1, phase: "edit", preview: null, msg: null }));
    const url = `/api/projects/${encodeURIComponent(slug)}/monsters/${encodeURIComponent(u.id)}/art`;
    const holder = el("div", { class: "stack art-manager", id: `art-${u.id}` });
    escapeReview(holder, () => dr.phase === "review", () => { dr.phase = "edit"; redraw(REVIEW_TRIGGER); });
    const reload = () => { state.models.delete(slug); dr.msg = null; render(); };
    const body = () => ({ expected_sha256: m.provenance.sha256, frames: Object.fromEntries(Object.entries(dr.frames).map(([k, v]) => [k, v.b64])) });
    async function pick(frame, file) {
      dr.msg = null; dr.phase = "edit"; dr.preview = null;
      if (dr.frames[frame]) { URL.revokeObjectURL(dr.frames[frame].url); delete dr.frames[frame]; }
      if (!file) { redraw(); return; }
      if (file.type !== "image/png" && !/\.png$/i.test(file.name)) { dr.msg = { kind: "local", text: `${file.name}: only PNG files are accepted.` }; redraw(); return; }
      if (file.size > MAX_FRAME_BYTES) { dr.msg = { kind: "local", text: `${file.name}: larger than 2 MB.` }; redraw(); return; }
      const buf = await file.arrayBuffer();
      const head = new Uint8Array(buf.slice(0, 8));
      if (![137, 80, 78, 71, 13, 10, 26, 10].every((b, i) => head[i] === b)) { dr.msg = { kind: "local", text: `${file.name}: not a PNG file.` }; redraw(); return; }
      dr.frames[frame] = { name: file.name, size: file.size, b64: toBase64(buf), url: URL.createObjectURL(new Blob([buf], { type: "image/png" })) };
      redraw(`#art-${u.id}-${frame}`);
    }
    function frameCol(frame, label) {
      const cur = existing[frame], d = dr.frames[frame];
      const input = el("input", { type: "file", accept: "image/png,.png", id: `art-${u.id}-${frame}`, class: "input" });
      input.addEventListener("change", () => pick(frame, input.files && input.files[0]));
      const img = d ? spriteImg(d.url, `${label} upload preview`, dr.zoom) : null;
      const facts = dr.preview && dr.preview.frames && dr.preview.frames[frame];
      return el("div", { class: "art-col" },
        el("label", { for: input.id, text: `${label} (${frame === "idle" ? "#spr1" : "#spr2"})` }), input,
        el("div", { class: "art-pair" },
          el("figure", { class: "sprite-frame" }, el("div", { class: "sprite-box" }, cur && cur.url ? spriteImg(cur.url, `${label} current`, dr.zoom) : el("div", { class: "preview-missing", text: "none" })),
            el("figcaption", { class: "cap" }, "Current", cur && cur.path ? [el("br"), el("code", { text: cur.path })] : null)),
          el("figure", { class: "sprite-frame" }, el("div", { class: "sprite-box" }, img || el("div", { class: "preview-missing", text: "no new file" })),
            el("figcaption", { class: "cap" }, d ? [`New: ${d.name}`, el("br"), `${d.size} bytes`] : "New", facts ? [el("br"), `${facts.width}×${facts.height} px`] : null))),
        facts && facts.warnings.length ? el("ul", { class: "diag" }, facts.warnings.map((w) => el("li", null, badge("check", "warn"), " ", w))) : null,
        d ? el("button", { type: "button", class: "btn btn-small btn-ghost", onclick: () => pick(frame, null) }, "Clear") : null);
    }
    function redraw(focusSel) {
      const n = Object.keys(dr.frames).length;
      const busy = dr.msg && dr.msg.kind === "busy" ? stateBox("loading", dr.msg.text) : null;
      const err = dr.msg && dr.msg.kind === "err" ? writeError(dr.msg.err, reload) : dr.msg && dr.msg.kind === "local" ? stateBox("error", "File not accepted.", dr.msg.text) : null;
      const zoom = el("div", { class: "btn-row seg", role: "group", "aria-label": "Preview zoom" }, [1, 2, 3, 4].map((s) =>
        el("button", { type: "button", class: "btn btn-small", "aria-pressed": dr.zoom === s ? "true" : "false", onclick: () => { dr.zoom = s; redraw(`[aria-label="Preview zoom"] [aria-pressed=true]`); } }, `${s}x`)));
      holder.replaceChildren(...[
        el("p", { class: "panel-note", text: "PNG, 8-bit RGBA, up to 256 px per side (64×64 recommended), 2 MB max, alpha 0 or 255. Saved as new files under art/" + (isGod(u) ? "pretenders" : "units") + "/; existing files are never overwritten. Removes #copyspr, so a borrowed sprite needs both frames." }),
        err, busy,
        el("div", { class: "art-grid" }, frameCol("idle", "Idle"), frameCol("attack", "Attack")),
        el("div", { class: "btn-row" }, el("span", { class: "muted", text: "Preview:" }), zoom),
        dr.phase === "review" && dr.preview ? reviewBlock({ ...dr.preview, explanation: (dr.preview.plan || []).map((p) => `${p.action} ${p.frame}: ${p.before ? p.before + " → " : ""}${p.after || ""}${p.explanation ? " (" + p.explanation + ")" : ""}`) },
          "Save frames", () => runWrite(dr, url, body(), false, redraw, (r) => {
            for (const f of Object.values(dr.frames)) URL.revokeObjectURL(f.url);
            state.arts.delete(key);
            afterWrite(slug, location.hash, `Saved ${r.files.length} frame(s). Backup: ${r.backup}`, r, `Saved ${r.files.length} art frame(s) for ${txt(u.name) || "unit"} (#${u.id})`);
          }), () => { dr.phase = "edit"; redraw(REVIEW_TRIGGER); })
          : el("div", { class: "btn-row" }, el("button", { type: "button", class: "btn", disabled: !n || !CSRF || null, onclick: () => runWrite(dr, url, body(), true, redraw), ...RT }, "Check frames"),
            el("span", { class: "faint", text: n ? `${n} frame(s) chosen` : "Choose one or two PNG files." }))].filter(Boolean));
      if (focusSel) { const t = holder.querySelector(focusSel); if (t) t.focus(); }
    }
    redraw();
    return techSection(`Upload art${Object.keys(dr.frames).length ? ` (${Object.keys(dr.frames).length} chosen)` : ""}`, Object.keys(dr.frames).length > 0 || dr.phase === "review", holder);
  }

  // ---------- build and export (project-wide) ----------
  // Packages exactly the saved revision this page shows. The server re-checks the hash under the project lock,
  // validates, refuses errors and writes a new uniquely named export under <project>/exports (never overwrites).
  // UI state lives in state.exports (keyed by slug) so results and errors survive re-renders.
  function exportUi(slug) {
    if (!state.exports.has(slug)) state.exports.set(slug, { format: "zip", busy: false, result: null, error: null, list: null, listError: null, listOpen: false });
    return state.exports.get(slug);
  }
  // ---------- unsaved drafts (every editor) ----------
  // Drafts live in this tab's memory only. One registry lists every editor holding input the saved files do not contain
  // yet: Export, the project header and the browser's leave-page warning all read it. A draft that matches the file again
  // (typed back, discarded, saved or cancelled) is not listed. slug: one project; omitted: every project plus .dm import.
  const formDirty = (dr) => !!dr && !!dr.form && dr.formBase !== undefined && JSON.stringify(dr.form) !== dr.formBase;
  function unsavedDrafts(slug) {
    const out = [];
    const add = (s, label, href) => { if (slug === undefined || s === slug) out.push({ slug: s, label, href }); };
    const head = (k) => { const i = k.indexOf(":"); return [k.slice(0, i), k.slice(i + 1)]; };
    const hasErrOrChange = (r) => r.changes.length > 0 || Object.keys(r.errors).length > 0;
    for (const [k, ed] of state.editors) {
      const [s, id] = head(k);
      if (ed.st && hasErrOrChange(draftChanges(ed))) add(s, `Unit #${id}: field edits`, hashPath("p", s, "units", id));
    }
    for (const [k, nd] of state.nationEditors) {
      const [s, id] = head(k);
      if (nd.st && hasErrOrChange(nationChanges(nd))) add(s, `Nation #${id}: edits`, routeNation(id, "p", s, "nation", id));
    }
    for (const [k, dr] of state.creates) {
      if (!formDirty(dr)) continue;
      const [s, rest] = head(k), [kind, which] = rest.split(":");
      if (kind === "nation") add(s, "New nation", hashPath("p", s, "nation", "~new"));
      else add(s, `${which === "new" ? "New" : `Duplicate of #${which}`} ${kind === "god" ? "pretender god" : "unit"}`,
        hashPath("p", s, kind === "god" ? "pretenders" : "units", which === "new" ? "~new" : `~dup-${which}`));
    }
    for (const [k, dr] of state.arts) { const [s, id] = head(k); if (Object.keys(dr.frames).length) add(s, `Unit #${id}: artwork upload`, hashPath("p", s, "units", id)); }
    for (const [k, dr] of state.authoring) {
      if (k.startsWith("equipment:")) {
        const [s, id] = head(k.slice(10));
        if (Object.values(dr.replace || {}).some(Boolean)) add(s, `Unit #${id}: equipment`, hashPath("p", s, "units", id));
        continue;
      }
      const [s, rest] = head(k), parts = rest.split(":"), kind = parts[0], key = parts.slice(1).join(":");
      if (CONTENT_KINDS[kind]) {
        if (key === "~new" ? draftDirty(dr) : Object.keys(dr.touched || {}).length) add(s, `${key === "~new" ? "New" : "Edited"} ${CONTENT_KINDS[kind].one}${/^\d+$/.test(key) ? ` #${key}` : ""}`, authRoute(s, kind, key));
      } else if (kind === "heroes") {
        if (Object.keys(dr.touched.heroes || {}).length + Object.keys(dr.touched.multiheroes || {}).length) add(s, `Heroes of nation #${key}`, routeNation(key, "p", s, "author", "heroes"));
      } else if (kind === "playtest") {
        if (Object.keys(dr.touched || {}).length || (dr.evidence || []).length) add(s, "Playtest record", hashPath("p", s, "author", "playtests"));
      } else if (kind === "cmd") {
        const ctx = parts[1], bkey = parts.slice(2).join(":"), label = (CMD_CONTEXTS.find((c) => c[0] === ctx) || [ctx, ctx])[1];
        const opener = bkey === "~new" && (dr.opener.raw || []).some((x) => String(x ?? "").trim());
        if (dr.ops.length || opener) add(s, `${bkey === "~new" ? "New" : "Edited"} ${label.toLowerCase()} block (advanced)`, cmdRoute(s, ctx, bkey));
      } else if (kind === "merc" && formDirty(dr)) add(s, "New mercenary company", hashPath("p", s, "mercs", "~new"));
    }
    for (const [s, dr] of state.depDrafts) {
      if (dr.st && dr.list && JSON.stringify(dr.list) !== JSON.stringify(dr.st.dependencies || [])) add(s, "Dependency settings", hashPath("p", s));
    }
    for (const [k, dr] of state.maps) { const [s, id] = head(k); if (draftSize(dr)) add(s, `Map ${id}: edits`, mapRoute(s, id)); }
    for (const [s, dr] of state.mapImports) if (!dr.done && (dr.files.length || dr.id.trim())) add(s, "Map import", mapRoute(s, "~import"));
    for (const [s, dr] of state.mapBuilds || []) if (dr.brief && dr.briefBase !== undefined && JSON.stringify(dr.brief) !== dr.briefBase) add(s, "Map job brief", mapRoute(s));
    const imp = state.importDraft;
    if (slug === undefined && imp && !imp.done && (imp.dm || imp.assets.length || imp.form.slug.trim() || imp.form.name.trim())) out.push({ slug: null, label: "Import a .dm", href: "#/import" });
    return out;
  }
  // Header badge for the current project, refreshed after input without re-rendering the page.
  let draftTimer = 0;
  function syncDraftStatus() {
    const box = $("#draft-status");
    if (!box) return;
    const n = unsavedDrafts(box.dataset.slug).length;
    box.hidden = !n;
    const a = box.querySelector("a");
    if (a) a.textContent = `${n} unsaved draft${n === 1 ? "" : "s"}`;
  }
  for (const ev of ["input", "change", "click"]) document.addEventListener(ev, () => { clearTimeout(draftTimer); draftTimer = setTimeout(syncDraftStatus, 200); }, true);
  // Drafts are in memory only: closing or reloading the tab would lose them, so the browser asks first.
  window.addEventListener("beforeunload", (e) => { if (unsavedDrafts().length) { e.preventDefault(); e.returnValue = ""; } });
  const shortSha = (s) => (s ? `${s.slice(0, 12)}…` : "—");
  function exportPanel(m) {
    const slug = m.project.slug, p = m.provenance, v = m.validation, ui = exportUi(slug);
    const base = `/api/projects/${encodeURIComponent(slug)}`;
    const holder = el("section", { class: "panel export-panel", "aria-labelledby": "export-h" });
    const fresh = !!v && v.sha256 === p.sha256;
    const revalidate = async () => {
      state.models.delete(slug);
      await loadProjects(true);
      await render();
      toast("Saved .dm re-read and re-validated");
    };
    async function run() {
      ui.busy = true; ui.error = null; ui.result = null; draw();
      try { ui.result = await postJSON(`${base}/export`, { expected_sha256: p.sha256, format: ui.format }); ui.list = null; }
      catch (e) { ui.error = e; }
      ui.busy = false; draw();
      if (ui.result) {
        // Keep the readiness summary's "latest export" in step without re-reading the whole project.
        const r = ui.result, man = r.manifest || {};
        m.latest_export = { available: true, export: { export_id: r.export_id, format: r.format, sha256: r.sha256,
          created_utc: man.created_utc, files: (man.files || []).length } };
        if (ui.redrawReadiness) ui.redrawReadiness();
        if (ui.redrawWorkshop) ui.redrawWorkshop();
      }
      const h = holder.querySelector("#export-outcome"); if (h) h.focus();
    }
    function errorView(e) {
      const err = e.error || {}, d = err.details || {};
      const title = { sha_mismatch: "Not exported: the saved .dm changed since this page loaded.",
        validation_failed: "Not exported: validation reported errors.",
        project_locked: "Not exported: another save or export holds the project lock.",
        changed_during_export: "Not exported: mod files changed while packaging.",
        bad_csrf: "Not exported: the page token is out of date.", bad_origin: "Not exported: request was not from this page." }[err.code] || "Export failed.";
      return el("div", { class: "state state-error", role: "alert" },
        el("strong", { id: "export-outcome", tabindex: "-1", text: title }),
        el("div", null, el("span", { class: "code", text: `[${txt(err.code)}] ` }), txt(err.message)),
        err.code === "sha_mismatch" ? el("p", { class: "mono faint", text: `shown ${shortSha(d.expected)} · on disk ${shortSha(d.actual)}` }) : null,
        err.code === "validation_failed" && Array.isArray(d.errors) ? diagnosticsList(slug, d.errors.slice(0, 20), p.file) : null,
        el("div", { class: "btn-row" },
          err.code === "sha_mismatch" || err.code === "changed_during_export" ? el("button", { type: "button", class: "btn btn-small", onclick: revalidate }, "Reload saved revision") : null,
          err.code === "validation_failed" ? el("a", { class: "btn btn-small", href: route("p", slug, "validation") }, "Open validation report") : null,
          err.code === "project_locked" ? el("button", { type: "button", class: "btn btn-small", onclick: run }, "Try again") : null),
        el("p", { class: "panel-note", text: "Nothing was written. Unsaved drafts are untouched." }));
    }
    function resultView(r) {
      const man = r.manifest, val = r.validation || {}, c = val.counts || {}, zip = r.format === "zip";
      const xbase = `${base}/exports/${encodeURIComponent(r.export_id)}`;
      return el("div", { class: "export-result stack" },
        el("p", null, el("strong", { id: "export-outcome", tabindex: "-1", text: zip ? "ZIP export written." : "Folder export written." }),
          r.sha256 === p.sha256 ? null : [" ", badge("older revision than this page", "warn")]),
        c.unverified || c.warnings ? el("p", null, `${txt(c.warnings)} warnings · ${txt(c.unverified)} unverified `,
          el("a", { href: route("p", slug, "validation") }, "review")) : null,
        techSection("Technical details", false, el("dl", { class: "kv" },
          el("dt", { text: "Export id" }), el("dd", { class: "mono", text: r.export_id }),
          el("dt", { text: ".dm SHA-256" }), el("dd", { class: "hash", text: r.sha256 }),
          zip ? el("dt", { text: "Archive SHA-256" }) : null, zip ? el("dd", { class: "hash", text: txt(man.archive_sha256) }) : null,
          el("dt", { text: "Location" }), el("dd", { class: "mono", text: `${slug}/${r.path}` }),
          el("dt", { text: "Manifest" }), el("dd", { class: "mono", text: `${slug}/${r.manifest_path}` }),
          el("dt", { text: "Created (UTC)" }), el("dd", { text: txt(man.created_utc) }),
          el("dt", { text: "Target game" }), el("dd", { text: `Dominions ${txt(man.target_game_version)} · manual ${txt(man.manual_version)}` })),
        table(["Packaged file", "Bytes", "SHA-256"], man.files.map((f) => [el("code", { text: f.path }), txt(f.bytes), el("span", { class: "hash", text: f.sha256 })]),
          { caption: "Bytes hashed from the validated snapshot; the manifest records the same hashes." }),
          el("p", { class: "panel-note", text: `${txt(man.disclaimer)} Not installed or published: ${txt(man.install_hint)}` })),
        (val.warnings || []).length ? el("details", { class: "raw" }, el("summary", null, `Warnings (${val.warnings.length})`),
          el("div", { class: "inner" }, diagnosticsList(slug, val.warnings, p.file))) : null,
        el("div", { class: "btn-row" },
          zip ? el("a", { class: "btn", href: `${xbase}/archive`, download: "" }, "Download ZIP") : null,
          el("a", { class: "btn btn-small", href: `${xbase}/manifest`, target: "_blank", rel: "noopener" }, "Manifest JSON"),
          zip ? el("button", { type: "button", class: "btn btn-small btn-ghost", onclick: () => copy(txt(man.archive_sha256), "Archive hash") }, "Copy archive hash") : null),
        el("p", { class: "panel-note", text: "Not installed or published. Test it in Dominions 6." }));
    }
    function listView() {
      const box = el("div", { class: "inner" });
      if (ui.listError) box.append(errorBox(ui.listError, "earlier exports"));
      else if (!ui.list) box.append(stateBox("loading", "Reading exports..."));
      else if (!ui.list.length) box.append(el("p", { class: "muted", text: "No exports yet." }));
      else box.append(table(["Export (UTC stamp in id)", ".dm revision", ""], ui.list.map((x) => {
        const xbase = `${base}/exports/${encodeURIComponent(x.export_id)}`;
        return [el("span", null, el("code", { text: x.export_id }), " ", badge(x.format, "info"), x.error ? [" ", badge(x.error, "warn")] : null),
          el("span", null, el("span", { class: "mono", text: shortSha(x.sha256) }), x.sha256 === p.sha256 ? [" ", badge("current", "ok")] : null),
          el("span", { class: "btn-row" }, x.format === "zip" ? el("a", { class: "btn btn-small", href: `${xbase}/archive`, download: "" }, "ZIP") : null,
            el("a", { class: "btn btn-small btn-ghost", href: `${xbase}/manifest`, target: "_blank", rel: "noopener" }, "Manifest"))];
      })));
      return box;
    }
    function draw() {
      const drafts = unsavedDrafts(slug);
      const blocked = !CSRF ? "No export token from this server; restart `kosmokrator serve` and reload."
        : !v ? "Validation could not run for this revision."
        : !fresh ? "Validation describes a different revision; re-validate first."
        : !v.ok ? `${v.counts.errors} validation error(s) must be fixed first.` : null;
      const fmt = el("select", { class: "input", id: "export-format", disabled: ui.busy || null },
        el("option", { value: "zip", text: "ZIP archive (download)" }), el("option", { value: "folder", text: "Folder in project exports" }));
      fmt.value = ui.format;
      fmt.addEventListener("change", () => { ui.format = fmt.value; });
      const list = el("details", { class: "raw", open: ui.listOpen || null }, el("summary", null, `Earlier exports in ${slug}/exports`), ui.listOpen ? listView() : null);
      list.addEventListener("toggle", async () => {
        ui.listOpen = list.open;
        if (!list.open) return;
        if (!ui.list) {
          try { ui.list = (await getJSON(`${base}/exports`)).exports; ui.listError = null; } catch (e) { ui.listError = e; }
        }
        const old = list.querySelector(".inner"); if (old) old.remove();
        list.append(listView());
      });
      holder.replaceChildren(...[
        el("h3", { id: "export-h" }, "Export"),
        el("dl", { class: "kv" },
          el("dt", { text: "Validation" }), el("dd", null, !v ? badge("unavailable", "err") : !fresh ? badge("stale", "warn") : v.ok ? "No errors" : badge(`${v.counts.errors} error(s)`, "err"),
            v ? ` · ${v.counts.warnings} warnings · ${v.counts.unverified} unverified` : ""),
          p.catalog ? null : [el("dt", { text: "Catalog" }), el("dd", { text: "none (vanilla references unverified)" })]),
        drafts.length ? el("div", { class: "export-drafts", role: "note" },
          el("p", null, badge(`${drafts.length} unsaved draft${drafts.length === 1 ? "" : "s"}`, "warn"),
            " Not included: only the saved files are exported. Save or cancel these first if they belong in this export."),
          el("ul", { class: "plain-list" }, drafts.map((d) => el("li", null, el("a", { href: d.href }, d.label))))) : null,
        el("div", { class: "btn-row export-controls" },
          el("button", { type: "button", class: "btn btn-small btn-ghost", disabled: ui.busy || null, onclick: revalidate }, "Re-validate"),
          el("label", { for: "export-format", class: "faint", text: "Format" }), fmt,
          el("button", { type: "button", class: "btn", disabled: ui.busy || blocked ? true : null, "aria-describedby": blocked ? "export-blocked" : null, onclick: run },
            ui.busy ? "Exporting…" : "Export")),
        blocked ? el("p", { class: "panel-note", id: "export-blocked", text: blocked }) : null,
        el("div", { role: "status", "aria-live": "polite" },
          ui.busy ? stateBox("loading", "Validating and packaging the saved revision...") : null),
        ui.error ? errorView(ui.error) : ui.result ? resultView(ui.result) : null,
        el("p", { class: "panel-note", text: "Packages the saved .dm and its art. Nothing is installed or published." }),
        techSection("Saved revision", false, el("dl", { class: "kv" },
          el("dt", { text: "File" }), el("dd", { class: "mono", text: p.file }),
          el("dt", { text: ".dm SHA-256" }), el("dd", { class: "hash", text: p.sha256 }),
          v ? [el("dt", { text: "Validated" }), el("dd", { class: "hash", text: v.sha256 })] : null,
          el("dt", { text: "Catalog" }), el("dd", { text: p.catalog ? `dataset ${txt(p.catalog.dataset_version || "unknown")}${p.catalog.reference_snapshot ? " (project reference snapshot; never packaged)" : ""}` : "none" }))),
        list].filter(Boolean));
    }
    draw();
    ui.redrawPanel = draw;
    return holder;
  }

  // ---------- export status (shown on the Export tab) ----------
  // [text, kind] only when something blocks the export; null when it can run.
  function exportStatus(m) {
    const v = m.validation, fresh = !!v && v.sha256 === m.provenance.sha256;
    return !v ? ["validation unavailable", "err"] : !fresh ? ["re-validate", "warn"]
      : !v.ok ? [`${v.counts.errors} error${v.counts.errors === 1 ? "" : "s"}`, "err"] : null;
  }
  function viewExport(m) {
    return el("div", { class: "stack" }, exportPanel(m), workshopPanel(m));
  }

  // ---------- Steam Workshop preparation ----------
  // Builds <project>/exports/workshop/<id>/<slug>/ from an export of the revision this page shows (the server re-hashes
  // it under the project lock), adds dom6ws.txt and a 256x256 banner.png, and can copy it into the mods folder the
  // server was started with. The game's own Mods menu does the upload; this page only links to Steam.
  function workshopUi(slug) {
    if (!state.workshop) state.workshop = new Map();
    if (!state.workshop.has(slug)) state.workshop.set(slug, { data: null, loadError: null, visibility: "", busy: null,
      result: null, error: null, install: null, installError: null, focus: null });
    return state.workshop.get(slug);
  }
  function workshopPanel(m) {
    const slug = m.project.slug, p = m.provenance, v = m.validation, ui = workshopUi(slug), xui = exportUi(slug);
    const base = `/api/projects/${encodeURIComponent(slug)}`;
    const holder = el("section", { class: "panel workshop-panel", "aria-labelledby": "ws-h" });
    const fresh = !!v && v.sha256 === p.sha256;
    // An export of exactly this revision, if the page knows one (the last export here, or the newest on disk).
    const currentExport = () => {
      const r = xui.result, L = m.latest_export && m.latest_export.export;
      if (r && r.sha256 === p.sha256) return { export_id: r.export_id, format: r.format };
      if (L && L.sha256 === p.sha256 && !L.error) return { export_id: L.export_id, format: L.format };
      return null;
    };
    async function load() {
      try { ui.data = (await getJSON(`${base}/workshop`)).result; ui.loadError = null; } catch (e) { ui.loadError = e; }
      draw();
    }
    async function prepare() {
      ui.busy = "prepare"; ui.error = null; ui.result = null; ui.install = null; ui.installError = null; draw();
      try {
        let src = currentExport();
        if (!src) {
          // No export of this revision yet: make the regular one first (same route, same checks as the panel above).
          const r = await postJSON(`${base}/export`, { expected_sha256: p.sha256, format: "zip" });
          xui.result = r; xui.list = null;
          const man = r.manifest || {};
          m.latest_export = { available: true, export: { export_id: r.export_id, format: r.format, sha256: r.sha256,
            created_utc: man.created_utc, files: (man.files || []).length } };
          src = { export_id: r.export_id, format: r.format };
          if (xui.redrawPanel) xui.redrawPanel();
        }
        ui.result = await postJSON(`${base}/workshop/prepare`, { expected_sha256: p.sha256, export_id: src.export_id, visibility: ui.visibility });
        ui.data = null;
      } catch (e) { ui.error = e; }
      ui.busy = null; ui.focus = "#ws-outcome";
      if (!ui.data) await load(); else draw();
    }
    async function install(wid) {
      ui.busy = "install"; ui.install = null; ui.installError = null; draw();
      try { ui.install = await postJSON(`${base}/workshop/${encodeURIComponent(wid)}/install`, { expected_sha256: p.sha256 }); }
      catch (e) { ui.installError = e; }
      ui.busy = null; ui.focus = "#ws-install-outcome";
      await load();
    }
    const errTitle = (code, fallback) => ({
      sha_mismatch: "The saved .dm changed since this page loaded.", stale_export: "That export is from an older .dm revision.",
      validation_failed: "Validation reported errors.", project_locked: "Another save or export holds the project lock.",
      export_changed: "The export no longer matches its manifest.", workshop_changed: "The prepared folder was changed after it was made.",
      banner_missing: "No banner image to reuse.", banner_unsupported: "The banner image cannot be read.", banner_conflict: "The mod's own banner.png cannot be used.",
      export_conflict: "The export already holds Workshop control files.", bad_visibility: "Choose a visibility first.",
      install_conflict: "a different mod folder is already there.", install_unavailable: "local install is not available.",
      symlink_rejected: "Refused: a link or junction is in the way.", bad_csrf: "The page token is out of date.", bad_origin: "Request was not from this page.",
    }[code] || fallback);
    function failure(e, id, what) {
      const err = e.error || {}, d = err.details || {};
      const reload = ["sha_mismatch", "stale_export", "changed_during_export", "bad_csrf"].includes(err.code);
      return el("div", { class: "state state-error", role: "alert" },
        el("strong", { id, tabindex: "-1", text: `${what}: ${errTitle(err.code, "the request failed.").replace(/^[A-Z](?=[a-z ])/, (c) => c.toLowerCase())}` }),
        el("div", null, el("span", { class: "code", text: `[${txt(err.code)}] ` }), txt(err.message)),
        Array.isArray(d.problems) && d.problems.filter(Boolean).length ? el("ul", { class: "plain-list ws-problems" },
          d.problems.filter(Boolean).map((x) => el("li", null, el("code", { text: x })))) : null,
        err.code === "validation_failed" && Array.isArray(d.errors) ? diagnosticsList(slug, d.errors.slice(0, 20), p.file) : null,
        el("div", { class: "btn-row" },
          reload ? el("button", { type: "button", class: "btn btn-small", onclick: async () => { state.models.delete(slug); await loadProjects(true); await render(); } }, "Reload saved revision") : null,
          err.code === "validation_failed" ? el("a", { class: "btn btn-small", href: route("p", slug, "validation") }, "Open validation report") : null),
        el("p", { class: "panel-note", text: err.code === "install_conflict" ? "Nothing in the mods folder was changed. Kosmokrator only replaces a folder it installed itself and never renames one, because a renamed copy would upload as a second Workshop item."
          : "Nothing was changed by this request." }));
    }
    const folderText = (r) => r.folder_abs || `${slug}/${r.path}`;
    function preparedView(r, open) {
      const wbase = `${base}/workshop/${encodeURIComponent(r.workshop_id)}`;
      const cur = r.sha256 === p.sha256, b = r.banner || {};
      return el("div", { class: "ws-result stack" },
        el("div", { class: "ws-result-head" },
          el("img", { class: "ws-banner", src: `${wbase}/banner.png`, width: 96, height: 96, alt: `banner.png for ${slug} (256 by 256)` }),
          el("div", null,
            el("p", null, el("strong", { id: open ? "ws-outcome" : null, tabindex: open ? "-1" : null, text: open ? "Workshop folder ready." : r.workshop_id }), " ",
              cur ? null : [badge("older revision", "warn"), " "], el("span", { class: "faint", text: `Visibility: ${txt(r.visibility)}` })),
            el("p", { class: "panel-note", text: `banner.png from ${txt(b.source)}: ${txt(b.method)}.` }))),
        techSection("Technical details", false, el("dl", { class: "kv" },
          el("dt", { text: "Content folder" }), el("dd", null, el("span", { class: "mono", text: folderText(r) }), " ",
            el("button", { type: "button", class: "btn btn-small btn-ghost", onclick: () => copy(folderText(r), "Folder path") }, "Copy path")),
          el("dt", { text: "From export" }), el("dd", { class: "mono", text: `${txt((r.source_export || {}).export_id)}` }),
          el("dt", { text: ".dm SHA-256" }), el("dd", { class: "hash", text: txt(r.sha256) }),
          el("dt", { text: "ZIP SHA-256" }), el("dd", { class: "hash", text: txt(r.archive_sha256) })),
        open ? el("details", { class: "raw" }, el("summary", null, `Files in the Workshop folder (${(r.files || []).length}): all of them are uploaded`),
          el("div", { class: "inner" }, table(["File", "Bytes", "SHA-256"], (r.files || []).map((f) => [el("code", { text: f.path }), txt(f.bytes), el("span", { class: "hash", text: f.sha256 })]),
            { caption: "The manifest and ZIP sit beside this folder, not inside it." }))) : null),
        el("div", { class: "btn-row" },
          el("a", { class: open ? "btn" : "btn btn-small", href: `${wbase}/archive`, download: "" }, "Download Workshop ZIP"),
          el("a", { class: "btn btn-small btn-ghost", href: `${wbase}/manifest`, target: "_blank", rel: "noopener" }, "Manifest JSON")));
    }
    function installView(latest) {
      const I = ui.data && ui.data.install;
      if (!I) return null;
      const words = { absent: ["not installed yet", "info"], managed: ["installed by Kosmokrator", "ok"], identical: ["identical", "ok"],
        conflict: ["another folder is there", "err"], unavailable: ["unavailable", "warn"] }[I.state] || [I.state, "info"];
      const can = I.available && latest && latest.sha256 === p.sha256 && I.state !== "conflict" && CSRF;
      const why = !I.available ? I.reason : !latest ? "Prepare a Workshop folder first." : latest.sha256 !== p.sha256 ? "Prepare the current revision first."
        : I.state === "conflict" ? "A mod folder with this name already exists and was not installed from this project. It is left untouched." : null;
      const R = ui.install;
      return el("div", { class: "ws-step stack" },
        el("h4", { id: "ws-install-h", text: "Install locally (optional)" }),
        el("dl", { class: "kv" },
          el("dt", { text: "Mods folder" }), el("dd", null, I.mods_dir ? el("span", { class: "mono", text: I.mods_dir }) : el("span", { class: "muted", text: "none" }),
            " ", el("span", { class: "faint", text: I.source === "environment" ? `(server setting ${I.env})` : I.source === "appdata" ? "(%APPDATA%\\Dominions6\\mods)" : "" })),
          el("dt", { text: "Destination" }), el("dd", null, I.destination ? el("span", { class: "mono", text: I.destination }) : "—", " ", badge(words[0], words[1]),
            I.pfid_present ? [" ", badge("dom6ws_pfid kept", "info")] : null)),
        I.state === "conflict" && (I.unmanaged || []).length ? el("details", { class: "raw" }, el("summary", null, `Files not from this project (${I.unmanaged_count})`),
          el("div", { class: "inner" }, el("ul", { class: "plain-list ws-problems" }, I.unmanaged.map((f) => el("li", null, el("code", { text: f })))))) : null,
        el("div", { class: "btn-row" },
          el("button", { type: "button", class: "btn", disabled: !can || ui.busy ? true : null, "aria-describedby": why ? "ws-install-why" : null,
            onclick: () => install(latest.workshop_id) }, ui.busy === "install" ? "Installing…" : I.state === "managed" ? "Update installed copy" : "Install into mods folder")),
        why ? el("p", { class: "panel-note", id: "ws-install-why", text: why }) : null,
        el("div", { role: "status", "aria-live": "polite" }, ui.busy === "install" ? stateBox("loading", "Checking hashes and copying...") : null),
        ui.installError ? failure(ui.installError, "ws-install-outcome", "Not installed") : R ? el("div", { class: "state state-ok" },
          el("strong", { id: "ws-install-outcome", tabindex: "-1", text: { installed: "Installed.", unchanged: "Already installed; nothing to copy.", updated: "Installed copy updated." }[R.result] || "Done." }),
          el("div", { class: "mono", text: R.destination }),
          el("div", { class: "faint", text: [R.written.length ? `${R.written.length} file(s) written` : "no files written", R.removed.length ? `${R.removed.length} old file(s) removed` : null,
            R.pfid_preserved ? "dom6ws_pfid kept unchanged" : null].filter(Boolean).join(" · ") })) : null,
        el("p", { class: "panel-note", text: `Copies the prepared files into <mods>/${slug}. Only an unchanged folder this project installed is replaced.` }));
    }
    function draw() {
      const D = ui.data, latest = ui.result || (D && D.prepared.find((x) => !x.error)) || null;
      const src = currentExport();
      const blocked = !CSRF ? "No editor token from this server; restart `kosmokrator serve` and reload."
        : !v ? "Validation could not run for this revision."
        : !fresh ? "Validation describes a different revision; re-validate first."
        : !v.ok ? `${v.counts.errors} validation error(s) must be fixed first.`
        : !ui.visibility ? "Choose the dom6ws.txt visibility first." : null;
      const banner = m.project.banner;
      const vis = el("select", { class: "input", id: "ws-visibility", disabled: ui.busy ? true : null, "aria-describedby": "ws-vis-note" },
        el("option", { value: "", text: "Choose…" }),
        ((D && D.visibility_values) || ["Public"]).map((x) => el("option", { value: x, text: x })));
      vis.value = ui.visibility;
      vis.addEventListener("change", () => { ui.visibility = vis.value; draw(); const s = holder.querySelector("#ws-visibility"); if (s) s.focus(); });
      const earlier = D ? D.prepared.filter((x) => !latest || x.workshop_id !== latest.workshop_id) : [];
      const steps = (D && D.upload_steps) || [];
      holder.replaceChildren(...[
        el("div", { class: "ws-head" },
          el("h3", { id: "ws-h" }, "Steam Workshop"),
          el("span", { class: "faint", text: "Upload happens inside Dominions 6." })),
        ui.loadError ? errorBox(ui.loadError, "Workshop status") : !D ? stateBox("loading", "Reading Workshop status...") : null,
        el("div", { class: "ws-step stack" },
          el("h4", { text: "Choose what goes in" }),
          el("dl", { class: "kv" },
            el("dt", { text: "Package" }), el("dd", null, src ? [el("span", { class: "mono", text: src.export_id }),
              el("p", { class: "panel-note", text: "Uses the artwork saved in this export. If you changed artwork, export again first." })]
              : el("span", { class: "muted", text: `No export of revision ${p.sha256.slice(0, 8)} yet; a ZIP export is made first.` })),
            el("dt", { text: "Banner" }), el("dd", null, banner && banner.status === "ok"
              ? [el("code", { text: banner.path }), el("span", { class: "faint", text: " → banner.png 256×256, centred on transparency, pixels unchanged" })]
              : el("span", { class: "muted", text: "No #icon image found; add one (or a 256×256 banner.png) before preparing." })),
            el("dt", null, el("label", { for: "ws-visibility", text: "dom6ws.txt" })), el("dd", null, vis,
              el("p", { class: "panel-note", id: "ws-vis-note", text: "The creator guide documents only Visibility = \"Public\" for this file. To keep the item private, friends-only or unlisted, change it on its Workshop page after the upload." }))),
          el("div", { class: "btn-row" },
            el("button", { type: "button", class: "btn btn-export", disabled: blocked || ui.busy ? true : null, "aria-describedby": blocked ? "ws-blocked" : null, onclick: prepare },
              ui.busy === "prepare" ? "Preparing…" : "Prepare Workshop folder")),
          blocked ? el("p", { class: "panel-note", id: "ws-blocked", text: blocked }) : null,
          el("div", { role: "status", "aria-live": "polite" }, ui.busy === "prepare" ? stateBox("loading", "Checking the export and writing the Workshop folder...") : null)),
        ui.error ? failure(ui.error, "ws-outcome", "Not prepared") : null,
        latest ? el("div", { class: "ws-step stack" }, el("h4", { text: "Prepared folder" }), preparedView(latest, !!ui.result)) : null,
        D ? installView(latest) : null,
        el("div", { class: "ws-step stack" },
          el("h4", { text: "Upload from the game" }),
          el("ol", { class: "ws-steps" }, (steps.length ? steps : ["Start Dominions 6, open Mods, right-click the local entry and choose \"Upload to Steam Workshop\"."]).map((t) => el("li", { text: t }))),
          el("div", { class: "btn-row" },
            el("a", { class: "btn", href: (D && D.steam_run_url) || "steam://run/2511500" }, "Launch Dominions 6 in Steam"),
            D ? el("a", { class: "btn btn-small btn-ghost", href: D.guide, target: "_blank", rel: "noopener noreferrer" }, "Creator guide (Steam)") : null),
          el("p", { class: "panel-note", text: "Upload from the game's mods folder (install or copy it there first). Kosmokrator sends nothing to Steam." })),
        earlier.length ? el("details", { class: "raw" }, el("summary", null, `Earlier Workshop folders (${earlier.length})`),
          el("div", { class: "inner stack" }, earlier.map((x) => x.error ? el("p", null, el("code", { text: x.workshop_id }), " ", badge(x.error, "warn")) : preparedView(x, false)))) : null,
      ].filter(Boolean));
      if (ui.focus) { const t = holder.querySelector(ui.focus); ui.focus = null; if (t) t.focus(); }
    }
    draw();
    xui.redrawWorkshop = draw;
    if (!ui.data) load();
    return holder;
  }

  // ---------- unit comparison (read-only) ----------
  // A project unit beside one or two vanilla catalog units chosen with the donor search. The reference ids live in the
  // address (#/p/<slug>/units/<id>/compare?c=199,311), so the view is bookmarkable and switching is one click.
  const MAX_REFS = 2;
  const compareRefs = () => (hashQuery().get("c") || "").split(",").filter((x) => /^\d{1,6}$/.test(x)).slice(0, MAX_REFS).map(Number);
  function compareHref(slug, uid, refs) {
    const base = route("p", slug, "units", uid, "compare");
    return refs.length ? `${base}${base.includes("?") ? "&" : "?"}c=${refs.join(",")}` : base;
  }
  // The unit's own catalog donor makes a natural first reference.
  const donorRef = (u) => u.donor && u.donor.resolved && Number.isInteger(u.donor.id) ? [u.donor.id] : [];
  function catalogUnit(slug, id) {
    const k = `${slug}:${id}`;
    if (!state.catalogUnits.has(k)) state.catalogUnits.set(k, getJSON(`/api/projects/${encodeURIComponent(slug)}/catalog-units/${id}`).then((r) => r.result));
    return state.catalogUnits.get(k).catch((e) => { state.catalogUnits.delete(k); throw e; });
  }
  const CMP_STATS = [["hp", "Hit points"], ["str", "Strength"], ["att", "Attack"], ["def", "Defence"], ["prec", "Precision"], ["prot", "Natural protection"],
    ["size", "Size"], ["mr", "Magic resistance"], ["mor", "Morale"], ["enc", "Encumbrance"], ["ap", "Combat speed (AP)"], ["mapmove", "Map move"], ["leader", "Leadership"]];
  function compareView(m, u) {
    const slug = m.project.slug, refs = compareRefs(), uid = u.id ?? u.uid;
    const cs = state.compare;
    const holder = el("div", { class: "stack compare-view" });
    const back = el("p", null, el("a", { href: route("p", slug, "units", uid) }, `← ${txt(u.name || "unit")} sheet`));
    const hasDoc = ((state.meta && state.meta.docs) || []).some((d) => d.name === "NATION-DESIGN.md");
    const criteria = techSection("Design criteria", false,
      el("p", { class: "panel-note" }, "Compare with the criteria in ",
        hasDoc ? el("a", { href: route("docs", "NATION-DESIGN.md") }, "docs/NATION-DESIGN.md") : el("code", { text: "docs/NATION-DESIGN.md" }),
        ": useful roster (a purpose for each unit; compare gold, resources, recruitment capacity and upkeep), whole economy (capital-only availability, Holy limits) and the copied-unit audit (inspect the donor and the result). "
        + "No balance score is computed: base values are raw, final costs are the game's, and equal headcount is not equal investment. Test in Dominions 6."));
    if (!catalogOf(m)) {
      holder.append(back, stateBox("empty", "No game-data catalog.", "Comparison needs the local dom6inspector catalog (start the server with --catalog) or this project's reference snapshot."), criteria);
      return holder;
    }
    const setRefs = (list) => { location.hash = compareHref(slug, uid, [...new Set(list)].slice(0, MAX_REFS)); };
    // Reference picker: the existing donor search endpoint.
    const q = el("input", { class: "input", type: "search", id: "cmp-q", value: cs.query, placeholder: "Vanilla unit name or id, e.g. Myrmidon or 20", autocomplete: "off" });
    const results = el("div", { class: "donor-results", "aria-live": "polite" });
    function drawResults() {
      if (cs.searching) { results.replaceChildren(stateBox("loading", "Searching the catalog...")); return; }
      const r = cs.results;
      if (!r) { results.replaceChildren(); return; }
      if (r.error) { results.replaceChildren(errorBox(r.error, "catalog units")); return; }
      if (!r.results.length) { results.replaceChildren(el("p", { class: "muted", text: "No catalog units match." })); return; }
      results.replaceChildren(el("ul", { class: "donor-list cmp-results", "aria-label": "Catalog units" }, r.results.map((x) => el("li", null,
        el("span", { class: "nm", text: `${x.name} (#${x.id})` }),
        el("button", { type: "button", class: "btn btn-small", "aria-pressed": refs[0] === x.id ? "true" : "false", onclick: () => setRefs([x.id, ...refs.slice(1).filter((y) => y !== x.id)]) }, "Reference 1"),
        el("button", { type: "button", class: "btn btn-small btn-ghost", "aria-pressed": refs[1] === x.id ? "true" : "false", disabled: (!refs.length || refs[0] === x.id) || null,
          onclick: () => setRefs([refs[0], x.id]) }, "Reference 2")))),
        ...(r.truncated ? [el("p", { class: "faint", text: `Showing ${r.results.length} of ${r.total_matches}; refine the search.` })] : []));
    }
    async function search() {
      const v = q.value.trim(); cs.query = q.value;
      if (!v) { q.focus(); return; }
      cs.searching = true; cs.results = null; drawResults();
      try { cs.results = (await getJSON(`/api/projects/${encodeURIComponent(slug)}/donors?q=${encodeURIComponent(v)}`)).result; }
      catch (e) { cs.results = { error: e }; }
      cs.searching = false; drawResults();
    }
    q.addEventListener("input", () => { cs.query = q.value; });
    q.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); search(); } });
    drawResults();
    const dr = donorRef(u);
    const picker = panel("Vanilla references",
      el("div", { class: "btn-row cmp-chips" }, refs.length ? refs.map((id, i) => el("span", { class: "cmp-chip" }, `Reference ${i + 1}: #${id} `,
        el("button", { type: "button", class: "btn btn-small btn-ghost", "aria-label": `Remove reference ${i + 1} (#${id})`, onclick: () => setRefs(refs.filter((x) => x !== id)) }, "Remove")))
        : el("span", { class: "muted", text: "No reference chosen yet." }),
        dr.length && !refs.includes(dr[0]) ? el("button", { type: "button", class: "btn btn-small", onclick: () => setRefs([dr[0], ...refs].slice(0, MAX_REFS)) }, `Use donor ${txt(u.donor.name)} (#${dr[0]})`) : null),
      el("div", { class: "edit-field wide" }, el("label", { for: "cmp-q", text: "Search catalog units" }),
        el("div", { class: "edit-control" }, q, el("button", { type: "button", class: "btn btn-small", onclick: search }, "Search")), results));
    const tableBox = el("div", { "aria-live": "polite" });
    holder.append(back, el("h3", { tabindex: "-1", id: "compare-title", text: `Compare: ${txt(u.name || "(unnamed)")}` }), picker, tableBox, criteria);
    if (!refs.length) {
      tableBox.append(stateBox("empty", "Choose a vanilla reference.", dr.length ? "Use the donor, or search for any catalog unit." : "Search for a catalog unit above."));
      return holder;
    }
    tableBox.append(stateBox("loading", "Reading catalog units..."));
    Promise.all(refs.map((id) => catalogUnit(slug, id).then((r) => ({ ok: true, r }), (e) => ({ ok: false, e, id })))).then((loaded) => {
      if (location.hash.split("?")[0] !== compareHref(slug, uid, refs).split("?")[0] || compareRefs().join() !== refs.join()) return;
      tableBox.replaceChildren(compareTable(m, u, loaded));
    });
    return holder;
  }
  function compareTable(m, u, loaded) {
    const slug = m.project.slug, file = u.source.file;
    const cols = [{ kind: "project", name: u.name, r: u.resolved, sprites: u.sprites, unit: u },
      ...loaded.map((x) => x.ok ? { kind: "catalog", name: x.r.name, id: x.r.id, r: x.r.resolved, sprites: x.r.sprites, unit: x.r } : { kind: "error", e: x.e, id: x.id })];
    const unknown = (t) => unresolved(t || "unknown");
    const statOf = (c, k) => k === "leader" ? c.r.leadership : c.r.stats[k];
    const val = (f) => f && f.value !== null && f.value !== undefined ? f.value : null;
    const head = cols.map((c, i) => el("th", { scope: "col" }, i === 0 ? [txt(c.name || "(unnamed)"), " ", badge("project", "copper")]
      : c.kind === "error" ? `#${c.id}` : [`${txt(c.name)} (#${c.id})`, " ", badge("vanilla", "info")]));
    const rows = [];
    const group = (t) => rows.push(el("tr", { class: "cmp-group" }, el("th", { scope: "colgroup", colspan: String(cols.length + 1), text: t })));
    const row = (label, cell, note) => rows.push(el("tr", null, el("th", { scope: "row" }, label, note ? el("div", { class: "faint", text: note }) : null),
      cols.map((c, i) => el("td", null, c.kind === "error" ? (rows.length <= 1 ? errorBox(c.e, `unit #${c.id}`) : "—") : cell(c, i)))));
    group("Sprites (native size)");
    // The APIs give no image dimensions, so every stage in this row grows to the largest loaded canvas (at least
    // 64x64). Images stay 1x, bottom-centred, never scaled or cropped; only this row's stages are touched.
    const stages = [], sprImgs = [];
    const fitStages = () => {
      let w = 64, h = 64;
      for (const im of sprImgs) if (im.isConnected && im.naturalWidth) { w = Math.max(w, im.naturalWidth); h = Math.max(h, im.naturalHeight); }
      for (const s of stages) { s.style.minWidth = `${w}px`; s.style.minHeight = `${h}px`; }
    };
    row("Idle / attack", (c) => el("div", { class: "cmp-sprites" }, ["idle", "attack"].map((k) => {
      if (!(c.sprites && c.sprites[k])) return el("div", { class: "preview-missing", text: `no ${k}` });
      const lbl = k === "idle" ? "Idle" : "Attack", cap = el("figcaption", { class: "cap", text: lbl });
      const img = spriteImg(c.sprites[k].url, `${txt(c.name)} ${k} sprite`, 1);
      img.addEventListener("load", () => { cap.textContent = `${lbl} ${img.naturalWidth}×${img.naturalHeight} px, 1x`; fitStages(); });
      img.addEventListener("error", () => { cap.textContent = `${lbl}: not loaded`; fitStages(); });
      const stage = el("div", { class: "cmp-stage" }, img);
      stages.push(stage); sprImgs.push(img);
      return el("figure", { class: "cmp-sprite" }, el("div", { class: "sprite-box" }, stage), cap);
    })), "Equal stages include transparent padding; figures stay at native 1x.");
    group("Base values (unequipped)");
    for (const [k, label] of CMP_STATS) {
      row(statLabel(k, label), (c, i) => {
        const f = statOf(c, k), v = val(f);
        if (v === null) return unknown(f && f.note);
        const base = val(statOf(cols[0], k));
        const mod = c.kind === "project" && f.source === "authored";
        return el("span", { title: c.kind === "project" ? (mod ? `set in this .dm (line ${f.line})` : txt(f.source).replace(/_/g, " ")) : "catalog row" },
          el("strong", { class: mod ? "mod" : null, text: v }), mod ? el("span", { class: "sr-only", text: " (set in this mod)" }) : null,
          i > 0 && typeof v === "number" && typeof base === "number" && base !== v ? el("span", { class: "faint", text: ` unit ${base - v > 0 ? "+" : "−"}${Math.abs(base - v)}` }) : null);
      });
    }
    group("Equipment");
    const gear = (list, status) => status && status.status === "unresolved" ? el("span", null, badge("unresolved", "warn"), " ", el("span", { class: "faint", text: status.note }))
      : list.length ? el("ul", { class: "cmp-list" }, list.map((x) => el("li", null, x.name ? txt(x.name) : unknown(x.unresolved), el("span", { class: "faint", text: ` #${txt(x.id ?? x.ref)}` })))) : el("span", { class: "muted", text: "none" });
    row("Weapons", (c) => gear(c.r.equipment.weapons, c.r.equipment.weapons_status));
    row("Armour", (c) => gear(c.r.equipment.armor, c.r.equipment.armor_status), "Armour protection is not added to natural protection.");
    group("Magic");
    row("Fixed paths", (c) => { const p = c.r.magic.paths; return Object.keys(p).length ? el("span", null, Object.entries(p).map(([k, f]) => [pathChip(k, f.value, c.kind === "project" && f.source === "authored"), " "])) : el("span", { class: "muted", text: "none" }); });
    row("Random picks", (c) => c.r.magic.random.length ? el("ul", { class: "cmp-list" }, c.r.magic.random.map((x) => el("li", { text: `${x.chance}% +${txt(x.levels ?? "?")} ${x.paths.join("/")}${x.count && x.count > 1 ? ` ×${x.count}` : ""}` })))
      : el("span", { class: "muted", text: "none" }), "As written; probabilities are not expanded.");
    group("Abilities");
    row("Modelled abilities and traits", (c) => { const e = [...Object.entries(c.r.specials), ...Object.entries(c.r.creature_traits)];
      return e.length ? el("span", null, e.map(([k, f], i) => [i ? ", " : "", el("span", { class: c.kind === "project" && f.source === "authored" ? "mod" : null, title: `#${k}`, text: abilityLabel(k, f.value) })])) : el("span", { class: "muted", text: "none modelled" }); },
      "Only a subset of catalog abilities is modelled.");
    row("Unmodelled donor/catalog columns", (c) => { const x = Object.keys(c.r.unmodelled_donor_columns || {}); return x.length ? el("code", { text: x.join(", ") }) : el("span", { class: "muted", text: "none" }); });
    group("Recruitment");
    row("Where", (c) => {
      if (c.kind === "project") {
        const un = c.unit, nat = unitNationUids(un);
        if (un.role === "pretender") return el("span", null, "not recruitable (pretender form)");
        return el("div", null, un.recruitment.length ? el("ul", { class: "cmp-list" }, un.recruitment.map((x) => el("li", null, el("code", { text: x.via }), " ",
          x.via === "#homecom" || x.via === "#homemon" ? [badge("capital only", "warn"), ` ${txt(x.site_name)}`] : x.via.startsWith("#addrec") ? badge("fort", "ok") : null,
          x.nation ? el("span", { class: "faint", text: ` ${nationNames(m, [x.nation])[0]}` }) : null))) : el("span", { class: "muted", text: "not recruitable in this project" }),
          nat.length > 1 ? el("div", null, badge(`shared by ${nat.length} nations`, "info")) : null);
      }
      const rec = c.unit.recruitment;
      return rec.length ? el("ul", { class: "cmp-list" }, rec.slice(0, 8).map((x) => el("li", null, `${x.kind}: ${txt(x.nation || `nation ${x.nation_id}`)}`, x.era_name ? el("span", { class: "faint", text: ` (${x.era_name})` }) : null)),
        rec.length > 8 ? el("li", { class: "faint", text: `+${rec.length - 8} more` }) : null) : el("span", { class: "muted", text: "not in the inspector's fort/non-fort nation tables" });
    }, "Vanilla: raw inspector nation tables; capital-only vanilla recruitment is not shown.");
    group("Cost components (not final costs)");
    for (const [k, label] of [["gold", "Gold component (#gcost / basecost)"], ["resources", "Resource component (#rcost)"], ["recruitment_points", "Recruitment points (#rpcost)"]]) {
      row(statLabel(k, label), (c) => { const f = c.r.costs[k];
        if (!f || f.authored_value === null || f.authored_value === undefined) return unknown(f && f.interpretation === "unknown" ? "unknown (donor unresolved)" : "unset");
        return el("span", { title: f.note || "" }, el("code", { text: String(f.authored_value) }), " ", badge(txt(f.interpretation).replace(/_/g, " "), "info"),
          f.interpretation === "autocalc_encoded" ? el("span", { class: "faint", text: ` base ${f.base}` }) : null); });
    }
    row("Final gold / resources / recruitment cost", () => unknown("not computed: the game adds equipment, leadership, magic and other costs"));
    group("Provenance and limits");
    row("Unmodelled or unresolved", (c) => c.kind === "project"
      ? el("span", null, `${u.unsupported.length} command(s) not modelled · ${u.unresolved.length} unresolved`, " ", srcRef(slug, file, u.source.line))
      : el("span", null, `${c.unit.unresolved.length} unresolved · catalog ${txt(c.unit.provenance.dataset_version || "version unknown")}`));
    return panel("Side by side",
      el("div", { class: "table-wrap cmp-wrap" }, el("table", { class: "cmp-table" },
        el("caption", { text: "Base values and cost components. A difference shows the project unit minus that reference; it is not a balance verdict." }),
        el("thead", null, el("tr", null, el("th", { scope: "col", text: "Field" }), head)), el("tbody", null, rows))),
      el("p", { class: "panel-note", text: "Base values exclude equipment. Underlined values are set in this .dm." }));
  }

  // ---------- pretenders ----------
  function godSource(slug, file, f) {
    if (!f) return unresolved();
    const ln = f.line ? [" ", srcRef(slug, file, f.line)] : null;
    if (f.source === "authored") return el("span", null, badge("authored", "authored"), ln);
    if (f.source === "donor") return el("span", null, badge("donor", "copper"), ln);
    if (f.source === "catalog") return badge("catalog", "info");
    if (f.source === "cleared") return el("span", null, badge("cleared", "warn"), ln, f.note ? el("div", { class: "faint", text: f.note }) : null);
    return el("span", null, badge(String(f.source).replace(/_/g, " "), "warn"), f.note ? el("div", { class: "faint", text: f.note }) : null);
  }
  const GOD_STATUS = { eligible: ["statically eligible", "ok"], provisional: ["provisional", "warn"], excluded: ["excluded", "err"] };
  const godTail = (g) => `${g.source}-${g.id}`;
  const godStatusBadge = (s) => badge(...(GOD_STATUS[s] || [s || "not listed", "warn"]));
  const magicText = (g) => Object.entries(g.starting_magic.paths).map(([p, v]) => `${p}${v.level}`).join(" ") || "no fixed magic";
  function godArt(g, frame, scale, alt) {
    const a = g.art[frame];
    if (a && a.status === "available" && a.url) return spriteImg(a.url, alt, scale, el("div", { class: "preview-missing", text: "Preview unavailable" }));
    return el("div", { class: "preview-missing", title: (a && a.note) || "", text: a && a.status === "missing" ? "sprite file missing" : "no thumbnail" });
  }
  function godMatches(g, cand, nv) {
    if (state.godStatus !== "all" && cand.status !== state.godStatus) return false;
    if (state.godSource === "custom" && g.source !== "project") return false;
    if (state.godSource === "vanilla" && !(g.source === "catalog" && cand.via.some((v) => v.kind === "homerealm"))) return false;
    if (state.godSource === "explicit" && !cand.via.some((v) => v.kind !== "homerealm")) return false;
    const q = state.godQuery.trim().toLowerCase();
    if (!q) return true;
    const hay = [g.name, g.id, g.source, magicText(g), cand.status, nv.name].map(txt).join(" ").toLowerCase();
    return q.split(/\s+/).every((t) => hay.includes(t));
  }
  function godCard(slug, g, cand) {
    return el("a", { class: "god-card", href: route("p", slug, "pretenders", godTail(g)), "aria-label": `${txt(g.name)}, ${g.source === "project" ? "custom" : "vanilla"} god, ${(GOD_STATUS[cand.status] || [cand.status || "not listed for this selection"])[0]}` },
      el("div", { class: "sprite-box" }, godArt(g, "idle", 1, "")),
      el("div", { class: "god-body" },
        el("div", { class: "nm", text: g.name || "(unnamed)" }),
        cand.status === "eligible" ? null : el("div", { class: "btn-row" }, godStatusBadge(cand.status)),
        el("div", { class: "facts", text: `Dominion ${txt(g.startdom.value ?? "?")} · path cost ${txt(g.pathcost.value ?? "?")} · ${magicText(g)}` }),
        cand.cheapgod ? el("div", { class: "facts", text: `cheapgod: ${cand.cheapgod.discount} points less` }) : null,
        cand.reasons.length ? el("div", { class: "faint", text: cand.reasons.join("; ") }) : null));
  }
  function viewPretenders(m, sel) {
    const slug = m.project.slug, P = m.pretenders;
    if (!P) return stateBox("error", "No pretender data.", "This server's model has no pretender section; reload or restart the server.");
    const gods = new Map(P.gods.map((g) => [g.uid, g]));
    const ca = creatorArg(sel);
    if (ca) return creatorView(m, "god", ca.dup);
    if (sel) return pretenderDetail(m, P, gods, sel);
    if (!P.nations.length) return el("div", { class: "stack" }, createButtons(m, "god"), stateBox("empty", "No nation blocks.", "Pretender lists are read from nation blocks; this project has none."));
    const sn = selectedNation(m);
    const nv = sn && P.nations.find((x) => x.nation === sn.uid);
    if (!nv) return el("div", { class: "stack" }, createButtons(m, "god"), pretenderScopes(m, P));
    const file = m.provenance.file;
    const status = el("p", { class: "sr-only", role: "status", "aria-live": "polite" });
    const customBox = el("div", { class: "gallery" }), vanillaBox = el("div", { class: "gallery" });
    const customHead = el("h3"), vanillaHead = el("span");
    function fill() {
      const shown = nv.candidates.filter((cnd) => godMatches(gods.get(cnd.god), cnd, nv));
      const custom = shown.filter((cnd) => gods.get(cnd.god).source === "project");
      const vanilla = shown.filter((cnd) => gods.get(cnd.god).source !== "project");
      customHead.textContent = `Custom national gods (${custom.length})`;
      vanillaHead.textContent = `Vanilla candidates (${vanilla.length})`;
      customBox.replaceChildren(...(custom.length ? custom.map((cnd) => godCard(slug, gods.get(cnd.god), cnd)) : [el("p", { class: "muted", text: "None match." })]));
      vanillaBox.replaceChildren(...(vanilla.length ? vanilla.map((cnd) => godCard(slug, gods.get(cnd.god), cnd)) : [el("p", { class: "muted", text: "None match." })]));
      status.textContent = `${shown.length} of ${nv.candidates.length} pretenders shown`;
    }
    const search = el("input", { class: "input", type: "search", placeholder: "Search name, id, paths  ( / )", "aria-label": "Search pretenders", value: state.godQuery });
    const mkSel = (label, key, opts) => {
      const s = el("select", { class: "input", "aria-label": label }, opts.map(([v, l]) => { const o = el("option", { value: v, text: l }); if (v === state[key]) o.selected = true; return o; }));
      s.addEventListener("change", () => { state[key] = s.value; fill(); });
      return s;
    };
    search.addEventListener("input", () => { state.godQuery = search.value; fill(); });
    search.addEventListener("keydown", (e) => { if (e.key === "Escape") { search.value = ""; state.godQuery = ""; fill(); } });
    const c = nv.counts;
    const realmText = nv.realms.length ? nv.realms.map((r, i) => [i ? ", " : "", el("span", { text: `${r.realm} ${txt(r.name)}` })]) : "none declared";
    fill();
    return el("div", { class: "stack pretender-view" }, createButtons(m, "god"),
      panel(`Pretenders for ${txt(nv.name || nv.nation)}`,
          el("dl", { class: "kv" },
            el("dt", { text: "Home realms" }), el("dd", null, realmText),
            el("dt", { text: "Listed" }), el("dd", null, `${c.eligible} eligible`,
              c.provisional ? [" ", badge(`${c.provisional} provisional`, "warn")] : null, c.excluded ? [" ", badge(`${c.excluded} excluded`, "err")] : null)),
          el("p", { class: "panel-note", text: "Static check only; confirm gods in game." })),
      el("div", { class: "unit-filter", role: "search" }, search,
        mkSel("Filter by status", "godStatus", [["all", "All statuses"], ["eligible", "Statically eligible"], ["provisional", "Provisional"], ["excluded", "Excluded"]]),
        mkSel("Filter by source", "godSource", [["all", "All sources"], ["custom", "Custom (project)"], ["vanilla", "Vanilla realm"], ["explicit", "Explicit (#addgod)"]])),
      status,
      el("section", { class: "stack", "aria-label": "Custom national gods" }, customHead, customBox),
      el("details", { class: "raw tech", open: state.godSource === "vanilla" || null }, el("summary", null, vanillaHead),
        el("div", { class: "inner stack" }, vanillaBox)),
      nv.unresolved.length ? panel("Unresolved constraints and dependencies", el("ul", null, nv.unresolved.map((u) => el("li", null, badge(u.kind.replace(/_/g, " "), "warn"), " ", u.line ? [srcRef(slug, file, u.line), " "] : null, u.message)))) : null,
      techSection("Details: realms, god commands and JSON", false,
        panel("Availability basis", el("dl", { class: "kv" },
          el("dt", { text: "Basis" }), el("dd", { text: nv.basis }),
          el("dt", { text: "Home realms" }), el("dd", null, nv.realms.length ? nv.realms.map((r) => [el("span", { text: `${r.realm} ${txt(r.name)}` }), " ", r.line ? srcRef(slug, file, r.line) : badge("catalog baseline", "info"), " "]) : "none declared"),
          el("dt", { text: "Default realm 10" }), el("dd", { text: nv.default_realm_10.included ? "declared" : "not declared" }),
          el("dt", { text: "Restrictions" }), el("dd", null, nv.noundeadgods ? [el("code", { text: "#noundeadgods" }), " ", srcRef(slug, file, nv.noundeadgods)] : "none interpreted"),
          el("dt", { text: "Sources" }), el("dd", { text: `${c.custom} custom · ${c.vanilla_realm} vanilla realm · ${c.explicit} explicit` }))),
        panel(`Explicit god commands (${nv.commands.length})`,
          nv.commands.length ? table(["Line", "Command", "Target", "Effect"], nv.commands.map((x) => [srcRef(slug, file, x.line), el("code", { text: `${x.command} ${x.args.join(" ")}` }),
            x.target ? (x.target.source === "project" ? el("a", { href: route("p", slug, "pretenders", `project-${x.target.id}`) }, `${txt(x.target.name)} (#${x.target.id})`) : el("span", null, `${txt(x.target.name)} `, badge(x.target.source || "unresolved", x.target.source ? "info" : "warn"))) : "—",
            el("span", { class: "muted", text: x.effect })]))
            : el("p", { class: "muted", text: "No god commands in this nation block." })),
        panel("Assumptions and limitations", el("ul", null, [...P.assumptions, ...P.limitations].map((t) => el("li", { text: t })))),
        panel("JSON", jsonActions(`/api/projects/${encodeURIComponent(slug)}/pretenders`, () => P, "Pretenders JSON"))));
  }
  // "All nations" / "Not tied to a nation": pretender lists exist per nation, so show the per-nation totals and the
  // project's own gods (all of them, or those no nation lists) instead of hiding them.
  function pretenderScopes(m, P) {
    const slug = m.project.slug, none = state.nation.key === N_NONE;
    const custom = P.gods.filter((g) => g.source === "project" && (!none || !(g.availability || []).length));
    return el("div", { class: "stack pretender-view" },
      stateBox("empty", "Pretender lists are per nation.", "Choose a nation to see its eligible, provisional and excluded gods."),
      none ? null : table(["Nation", "Listed", "Custom", "Vanilla realm", "Explicit"], P.nations.map((x) => {
        const n = m.nations.find((y) => y.uid === x.nation);
        return [n ? el("a", { href: routeNation(nationKey(n), "p", slug, "pretenders") }, nationLabel(n)) : txt(x.name || x.nation),
          txt(x.counts.listed), txt(x.counts.custom), txt(x.counts.vanilla_realm), txt(x.counts.explicit)];
      })),
      el("section", { class: "stack", "aria-label": "Custom pretender gods" },
        el("h3", { text: none ? `Custom gods listed by no nation (${custom.length})` : `All custom gods in this project (${custom.length})` }),
        el("div", { class: "gallery" }, custom.length ? custom.map((g) => godCard(slug, g, { status: null, via: [], reasons: [] }))
          : [el("p", { class: "muted", text: "None." })])));
  }
  function pretenderDetail(m, P, gods, sel) {
    const slug = m.project.slug, file = m.provenance.file;
    const g = [...gods.values()].find((x) => godTail(x) === sel || x.uid === sel);
    const back = el("p", null, el("a", { href: route("p", slug, "pretenders") }, "← All pretenders"));
    if (!g) return el("div", { class: "stack" }, back, stateBox("error", `Pretender ${sel} not found.`, "It is not listed for any nation in this project."));
    const art = (key, label) => {
      const a = g.art[key];
      const ok = a && a.status === "available" && a.url;
      return { url: ok ? a.url : null, path: a && a.path, label, alt: `${txt(g.name)} ${label} sprite`,
        missing: a && a.status === "missing" ? "sprite file missing" : "no thumbnail",
        origin: a ? (a.origin === "catalog" ? "catalog sprite (read-only)" : a.status === "available" ? "project asset" : (a.note || a.status)) : null };
    };
    const statRows = Object.entries(g.physical).map(([k, f]) => [statLabel(k, STAT_LABELS[k] || (k === "leader" ? "Leadership" : k)), el("code", { text: k }),
      f.value === null || f.value === undefined ? unresolved(f.note || "unknown") : el("strong", { text: f.value }), godSource(slug, file, f)]);
    const dp = g.design_points;
    const ab = g.abilities;
    const specTable = (obj, empty) => Object.keys(obj || {}).length ? table(["Ability", "Value", "Source"], Object.entries(obj).map(([k, f]) => [el("code", { text: `#${k}` }),
      f.status === "unresolved" ? unresolved(f.note) : el("strong", { text: txt(f.value) }), godSource(slug, file, f)])) : el("p", { class: "muted", text: empty });
    const cols = SHEET_COLS.map((col) => col.map(([k, label]) => [label, g.physical[k]]));
    cols.push([["Map move", g.physical.mapmove], ["Design pts", dp, { mark: "†", text: costText(dp), note: dp.note }],
      ["Dominion", g.startdom], ["Path cost", g.pathcost]]);
    const abilityEntries = ab.raw ? Object.entries(ab.raw).map(([k, v]) => [k, { value: v, source: "catalog" }])
      : [...Object.entries(ab.specials || {}), ...Object.entries(ab.traits || {})];
    const unmodelled = Object.keys(ab.unmodelled_donor_columns || {}).length;
    const homerealm = Array.isArray(g.homerealm.value) ? (g.homerealm.value.join(", ") || "none") : "unknown";
    const sheetPaths = Object.fromEntries(Object.entries(g.starting_magic.paths).map(([p, v]) => [p, { value: v.level, source: v.source }]));
    const idle = art("idle", "Idle (#spr1)"), attack = art("attack", "Attack (#spr2)");
    const availability = el("p", { class: "sheet-line" }, el("span", { class: "sheet-k", text: "Availability:" }), " ",
      g.availability.length ? g.availability.map((a, i) => [i ? " " : "", el("span", null, `${txt(a.nation_name || a.nation)} `, godStatusBadge(a.status))]) : "not listed for any nation in this project");
    const nTech = (g.unsupported || []).length + (g.unresolved || []).length;
    const gm = g.source === "project" ? m.monsters.find((x) => x.id === g.id && x.new) : null;
    return el("div", { class: "stack pretender-view sheet-view" }, back,
      gm ? createButtons(m, "god", g.id) : null,
      g.source === "project" ? editorSection(slug, g.id, g.name) : el("p", { class: "faint", text: "Vanilla pretender (read-only)." }),
      unitSheet({
        name: g.name || "(unnamed)", type: "Pretender",
        sub: [g.source === "project" ? "Custom pretender" : "Vanilla pretender", `#${g.id}`,
          g.pretender_only ? "not recruitable" : null].filter(Boolean).map((x, i) => [i ? " · " : "", x]),
        cols,
        gear: g.equipment ? el("div", { class: "sheet-gear-wrap" }, sheetGear(g.equipment.weapons, "Weapon", g.equipment.weapons_status), sheetGear(g.equipment.armor, "Armour", g.equipment.armor_status)) : null,
        abilities: sheetAbilities(abilityEntries),
        magic: sheetMagic(sheetPaths, g.starting_magic.random),
        lines: [
          el("p", { class: "sheet-line" }, `+${txt(g.pathcost.value ?? "?")} pts per magic path · Dominion ${txt(g.startdom.value ?? "?")} · Home realm ${homerealm}`),
          unmodelled ? el("p", { class: "sheet-line muted" }, `${unmodelled} donor ${unmodelled === 1 ? "ability" : "abilities"} not modelled (see Details).`) : null,
          availability],
        figure: sheetFigure(txt(g.name), { idle: idle.url ? { url: idle.url } : null, attack: attack.url ? { url: attack.url } : null }),
        note: "Base values before equipment. † Design points as written; the game computes the final cost. Underlined values are set in this mod.",
        foot: [g.source === "project" && g.provenance.line ? srcRef(slug, file, g.provenance.line, true) : el("span", { class: "faint", text: "catalog data, read-only" }), " ",
          g.source === "project" ? el("a", { href: route("p", slug, "units", g.id) }, "Open monster detail") : null],
      }),
      artworkSection([idle, attack]),
      gm && CSRF ? artManager(m, gm, { idle: idle.url ? { url: idle.url, path: idle.path } : null, attack: attack.url ? { url: attack.url, path: attack.path } : null }) : null,
      panel("Availability and restrictions",
        g.availability.length ? table(["Nation", "Status", "Via", "Notes"], g.availability.map((a) => [txt(a.nation_name || a.nation), godStatusBadge(a.status),
          el("span", null, a.via.map((v, i) => [i ? "; " : "", v.kind === "homerealm" ? `home realm ${v.realm}` : v.kind === "addgod" ? "#addgod" : "catalog nation list", v.line ? [" ", srcRef(slug, file, v.line)] : (v.lines || []).filter(Boolean).map((l) => [" ", srcRef(slug, file, l)])])),
          el("span", null, a.reasons.length ? a.reasons.join("; ") : "—", a.cheapgod ? el("div", { class: "faint", text: `cheapgod ${a.cheapgod.discount}` }) : null)]))
          : el("p", { class: "muted", text: "Not listed for any nation in this project." }),
        el("p", { class: "panel-note", text: "Statically eligible means the documented rules found no obstacle. It is not verified in game." })),
      techSection(`Details: god design and sources${nTech ? ` (${nTech} not modelled or unresolved)` : ""}`, false,
        el("div", { class: "grid-2" },
          panel("God design",
            el("dl", { class: "kv" },
              el("dt", { text: "Starting dominion" }), el("dd", null, g.startdom.value ?? unresolved(g.startdom.note || "unknown"), " ", godSource(slug, file, g.startdom)),
              el("dt", { text: "New path cost" }), el("dd", null, g.pathcost.value ?? unresolved(g.pathcost.note || "unknown"), " ", godSource(slug, file, g.pathcost)),
              el("dt", { text: "Design points" }), el("dd", null, el("code", { text: `${dp.command} ${txt(dp.authored_value ?? "unset")}` }), " ", badge(dp.interpretation.replace(/_/g, " "), "info"), " ", unresolved("final not computed"),
                dp.line ? [" ", srcRef(slug, file, dp.line)] : null, el("div", { class: "faint", text: dp.note })),
              el("dt", { text: "Home realm" }), el("dd", null, Array.isArray(g.homerealm.value) ? homerealm : unresolved("unknown"), " ", godSource(slug, file, g.homerealm)))),
          panel("Starting magic",
            Object.keys(g.starting_magic.paths).length ? table(["Path", "Level", "Source"], Object.entries(g.starting_magic.paths).map(([p, v]) => [pathNamed(p, ` (${p})`), el("strong", { text: v.level }), godSource(slug, file, v)]))
              : el("p", { class: "muted", text: "No fixed starting magic." }),
            el("p", { class: "panel-note", text: "Magic the god starts with before the player buys more paths at the new path cost." }))),
        el("div", { class: "grid-2" },
          panel("Physical (base, unequipped)", table(["Field", "Key", "Value", "Source"], statRows)),
          panel("Abilities",
            ab.raw ? (Object.keys(ab.raw).length ? table(["Catalog column", "Raw value"], Object.entries(ab.raw).map(([k, v]) => [el("code", { text: k }), el("code", { text: v })])) : el("p", { class: "muted", text: "No selected ability columns set." }))
              : [el("h4", { text: "Special abilities" }), specTable(ab.specials, "None modelled."), el("h4", { text: "Creature traits" }), specTable(ab.traits, "None."),
                unmodelled ? table(["Donor column", "Raw", "Status"], Object.entries(ab.unmodelled_donor_columns).map(([k, x]) => [el("code", { text: k }), el("code", { text: x.value }), x.status]), { caption: "Unmodelled donor columns (shape, economy, dominion traits)" }) : null],
            el("p", { class: "panel-note", text: ab.note || "Only a subset of abilities is modelled." }))),
        g.equipment ? panel("Equipment", table(["Item", "Kind", "Source"], [...g.equipment.weapons.map((x) => [txt(x.name || x.ref), "weapon", godSource(slug, file, x)]), ...g.equipment.armor.map((x) => [txt(x.name || x.ref), "armour", godSource(slug, file, x)])]),
          el("p", { class: "panel-note", text: "As listed by the donor and authored commands; equipment-derived totals are not calculated." })) : null),
      techSection("Provenance", false, el("dl", { class: "kv" }, Object.entries(g.provenance).map(([k, v]) => [el("dt", { text: k }), el("dd", { class: "mono", text: v && typeof v === "object" ? JSON.stringify(v) : txt(v) })])),
        g.source === "project" ? el("p", null, el("a", { href: route("p", slug, "units", g.id) }, "Open monster detail (inheritance, authored commands, source)")) : null),
      techSection("JSON", false, jsonActions(`/api/projects/${encodeURIComponent(slug)}/pretenders/${encodeURIComponent(godTail(g))}`, () => g, "Pretender JSON")));
  }

  function viewSites(m, sel) {
    const slug = m.project.slug;
    if (!m.sites.length) return stateBox("empty", "No site blocks.", "This project defines or selects no magic sites.");
    // A site detail always opens, even outside the nation filter; the list follows the selected nation.
    const list = sel ? m.sites.filter((s) => String(s.id) === String(sel)) : nationSites(m);
    if (sel && !list.length) return stateBox("error", `Site ${sel} not found.`, "");
    const head = sel ? el("p", null, el("a", { href: route("p", slug, "sites") }, `← Sites for ${nationScopeText(m)}`),
      inSelectedNation(m, list[0].start_site_of) ? null : [" ", badge("outside filter", "warn"), el("span", { class: "faint", text: ` not a start site of ${nationScopeText(m)}` })])
      : el("p", { class: "faint", text: list.length === m.sites.length ? `${list.length} site${list.length === 1 ? "" : "s"}` : `${list.length} of ${m.sites.length} sites` });
    if (!list.length) return el("div", { class: "stack" }, head, stateBox("empty", `No sites for ${nationScopeText(m)}.`, "Choose another nation, \"Not tied to a nation\" or \"All nations\" above."));
    const body = (s) => [
      panel(`${txt(s.name || "(unnamed site)")}`,
        el("div", { class: "btn-row" }, el("code", { text: `${s.new ? "#newsite" : "#selectsite"} ${txt(s.id ?? s.selector)}` }), srcRef(slug, s.source.file, s.source.line),
          s.start_site_of.length ? badge("start site", "copper") : null),
        el("dl", { class: "kv" },
          el("dt", { text: "Path" }), el("dd", null, s.path ? pathNamed(s.path, ` (${s.path})`) : "—"),
          el("dt", { text: "Level" }), el("dd", { text: txt(s.level ?? "—") }),
          el("dt", { text: "Rarity" }), el("dd", { text: txt(s.rarity ?? "—") }),
          el("dt", { text: "Gems" }), el("dd", null, gemList(s.gems)),
          el("dt", { text: "Start site of" }), el("dd", null, s.start_site_of.length ? s.start_site_of.map((n, i) => [i ? ", " : "", el("a", { href: route("p", slug, "nation", n.split(":")[1]), text: nationNames(m, [n])[0] })]) : "not a start site (tied to no nation)")),
        s.units.length ? table(["Recruits", "Command", "Role", "Line"], s.units.map((x) => [monsterLink(slug, x.monster), el("code", { text: x.command }), x.role, srcRef(slug, s.source.file, x.line)])) : null,
        s.unsupported.length ? el("p", { class: "panel-note" }, `${s.unsupported.length} command(s) not modelled: `, s.unsupported.map((x) => el("code", { text: x.command + " " }))) : null,
        s.base ? el("p", { class: "panel-note" }, `Modifies catalog site ${txt(s.base.name || s.base.id)}.`) : null,
        sel ? identityNote(s.identity) : null),
      sel ? usedBySection(m, relOf(m, s, "site")) : null,
      sel ? siteEditLink(m, s, "Edit site") : null,
      sel ? techSection("Details: commands, source and JSON", false, panel(`Authored commands (${s.authored.length})`, authoredTable(slug, s)), sourcePanel(slug, s, "Site"),
        panel("JSON", jsonActions(`/api/projects/${encodeURIComponent(slug)}/sites/${encodeURIComponent(s.id)}`, () => s, "Site JSON")))
        : [panel("Authored commands", authoredTable(slug, s)), el("p", null, el("a", { href: route("p", slug, "sites", s.id) }, "Open site"))]];
    if (sel) return el("div", { class: "stack" }, head, list.map((s) => el("div", { class: "stack", id: `site-${s.id}` }, body(s))));
    // The list is a card grid; each card keeps the complete site panels in its disclosure.
    const card = (s) => {
      const name = txt(s.name || "(unnamed site)");
      const facts = [s.path ? pathNamed(s.path, ` ${s.level ?? "?"}`) : (s.level != null ? `Level ${s.level}` : null),
        s.rarity != null ? `Rarity ${s.rarity}` : null].filter(Boolean);
      return el("article", { class: "item-card", id: `site-${s.id}` },
        el("div", { class: "item-card-head" },
          el("div", null, el("h2", null, el("a", { href: route("p", slug, "sites", s.id) }, name)),
            el("p", { class: "faint" }, facts.length ? joinParts(facts) : "No path or level set"),
            el("p", { class: "muted" }, s.gems.length ? ["Income: ", gemList(s.gems)] : "No gem income"),
            s.start_site_of.length ? el("p", null, badge("start site", "copper")) : null)),
        siteEditLink(m, s),
        el("details", { class: "raw" },
          el("summary", { "aria-label": `Details for ${name}` }, "Details"),
          el("div", { class: "inner stack" }, body(s))));
    };
    return el("div", { class: "stack" }, head, el("div", { class: "item-grid" }, list.map(card)));
  }

  // "Edit" appears only once the editor's list confirms an editable block for this entry (sites by id, spells by opener line).
  function contentEditLink(m, kind, match, name, label) {
    const slug = m.project.slug, box = el("p", { class: "cross-link", hidden: true });
    authLoad(`${apiBase(slug)}/content/${kind}`).then((st) => {
      const it = (st.items || []).find(match);
      if (!it || !it.editable || !box.isConnected) return;
      // The link opens the structured form directly (even if it was closed earlier).
      box.append(el("a", { class: "btn btn-small", href: authRoute(slug, kind, it.key), "aria-label": `Edit ${name}`,
        onclick: () => { authDraft(`${slug}:${kind}:${it.key}`).open = true; } }, label || "Edit"));
      box.hidden = false;
    }, () => {});
    return box;
  }
  function siteEditLink(m, s, label) {
    if (!Number.isInteger(s.id)) return null;
    return contentEditLink(m, "sites", (x) => String(x.key) === String(s.id), txt(s.name || "this site"), label);
  }

  // One parsed-only block from other_definitions: summary, source line, authored commands, verbatim source and JSON.
  // `card` gives the disclosure a plain "Details" summary for use under a card's name and art.
  function otherDefDetails(m, d, extra, card) {
    const slug = m.project.slug;
    return el("details", { class: "raw" },
      card ? el("summary", { "aria-label": `Details for ${txt(d.name || d.opener)}` }, "Details")
        : el("summary", null, `${d.opener} ${txt(d.id ?? d.selector ?? "")} ${d.name ? "- " + d.name : ""}  `, badge(d.kind, "info")),
      el("div", { class: "inner stack" }, el("p", { class: "panel-note" }, d.status, " · ", srcRef(slug, d.source.file, d.source.line)),
        extra || null, authoredTable(slug, d), codeBlock(d.source.text, d.source.line),
        jsonActions(`/api/projects/${encodeURIComponent(slug)}/other_definitions/${encodeURIComponent(d.uid.split(":")[1])}`, () => d, "Definition JSON")));
  }
  function viewOther(m) {
    if (!m.other_definitions.length) return stateBox("empty", "No other definitions.");
    return el("div", { class: "stack" },
      el("p", { class: "faint", text: `${m.other_definitions.length} block${m.other_definitions.length === 1 ? "" : "s"}` }),
      m.other_definitions.map((d) => otherDefDetails(m, d)));
  }

  // ---------- spells and items (read-only, parsed only) ----------
  // A block belongs to a kind by its parsed kind, or by its #new<kind>/#select<kind> opener.
  const otherOfKind = (m, kind) => (m.other_definitions || []).filter((d) =>
    String(d.kind).toLowerCase() === kind || new RegExp(`^#(new|select)${kind}$`, "i").test(txt(d.opener)));
  // Project asset files whose server-reported used_by points at a #spr command inside this item's block.
  function itemSpriteAssets(m, d) {
    const first = d.source.line, last = first + d.source.text.split(/\r?\n/).length - 1;
    return (m.assets || []).filter((a) => (a.used_by || []).some((x) => x.uid === d.uid
      || (/^#?spr$/i.test(txt(x.command)) && Number(x.line) >= first && Number(x.line) <= last)));
  }
  function itemArtwork(m, d) {
    const assets = itemSpriteAssets(m, d);
    if (!assets.length) return null;
    return el("div", { class: "btn-row" }, el("span", { class: "muted", text: "Sprite asset:" }), assets.map((a) => [
      a.status !== "missing" && a.browser_preview ? spriteImg(a.browser_preview, a.path, 1, el("span", { class: "faint", text: "preview unavailable" })) : null,
      el("code", { text: a.path }), a.status === "missing" ? badge("referenced but missing", "err") : null]),
      el("a", { class: "btn btn-small btn-ghost", href: route("p", m.project.slug, "assets") }, "Open Assets"));
  }
  // Last authored value of one item command (quotes stripped), or null.
  const itemArg = (d, cmd) => {
    const c = (d.authored || []).filter((x) => txt(x.command).toLowerCase() === `#${cmd}`).pop();
    return c && c.args.length ? String(c.args[0]).replace(/^"|"$/g, "") : null;
  };
  const ITEM_TYPES = { 1: "One-handed weapon", 2: "Two-handed weapon", 3: "Missile weapon", 4: "Helmet", 5: "Body armour", 6: "Shield", 7: "Boots", 8: "Miscellaneous" };
  const itemType = (d) => itemArg(d, "type") === null ? null : ITEM_TYPES[itemArg(d, "type")] || `Slot type #${itemArg(d, "type")}`;
  // Item cards show authored metadata, leaving full parsed source in the existing disclosure.
  function itemCard(m, d) {
    const arg = (cmd) => itemArg(d, cmd);
    const { assets, a, cat } = itemIcon(m, d);
    const preview = a ? spriteImg(a.browser_preview, d.name || a.path, 2, el("span", { text: "Preview unavailable" }))
      : cat ? (() => {
        const img = spriteImg(cat.url, `${d.name || "item"} vanilla icon`, 2, el("span", { class: "muted", text: "No custom icon" }));
        img.title = `Vanilla icon #${cat.id}`;
        return img;
      })()
      : el("span", { class: "muted", text: assets.length ? "Missing icon" : "No custom icon" });
    const facts = [...itemForging(d), itemType(d)].filter(Boolean);
    return el("article", { class: "item-card" },
      el("div", { class: "item-card-head" }, el("div", { class: "item-card-icon" }, preview),
        el("div", null, el("h2", { text: d.name || `${d.opener} ${d.id ?? d.selector ?? ""}` }),
          el("p", { class: "faint" }, facts.length ? joinParts(facts) : "No forging data"))),
      arg("descr") ? el("p", { class: "item-card-description", text: arg("descr") }) : null,
      el("p", { class: "cross-link" }, el("a", { class: "btn btn-small", href: cmdRoute(m.project.slug, "item", `item:line:${d.source.line}`),
        "aria-label": `Advanced edit of ${txt(d.name || "this item")}: raw command lines` }, "Advanced edit")),
      otherDefDetails(m, d, itemArtwork(m, d), true));
  }
  // Spell cards share the item-card layout and show only what the block itself authors.
  const SPELL_SCHOOLS = { "-1": "Unresearchable", 0: "Conjuration", 1: "Alteration", 2: "Evocation", 3: "Construction", 4: "Enchantment", 5: "Thaumaturgy", 6: "Blood", 7: "Divine" };
  const spellPathName = (p) => Number(p) === 9 ? "Holy" : Number(p) === -1 ? "No path" : gemName([], p);
  function spellCard(m, d) {
    const cmds = (cmd) => (d.authored || []).filter((x) => x.command === `#${cmd}`);
    const arg = (cmd) => {
      const c = cmds(cmd).pop();
      return c && c.args.length ? String(c.args[0]).replace(/^"|"$/g, "") : null;
    };
    // #path <slot> <path> and #pathlevel <slot> <level>; slot 0 is primary, 1 secondary.
    const slots = {};
    cmds("path").forEach((c) => { if (c.args.length >= 2) (slots[c.args[0]] ||= {}).path = c.args[1]; });
    cmds("pathlevel").forEach((c) => { if (c.args.length >= 2) (slots[c.args[0]] ||= {}).level = c.args[1]; });
    const paths = Object.keys(slots).sort().map((k) => slots[k])
      .filter((s) => s.path !== undefined && Number(s.path) !== -1)
      .map((s) => (PATH_OF_NUMBER(s.path) ? pathNamed(PATH_OF_NUMBER(s.path), ` ${s.level ?? "?"}`) : `${spellPathName(s.path)} ${s.level ?? "?"}`));
    const school = arg("school"), research = arg("researchlevel"), fatigue = arg("fatiguecost");
    const fat = fatigue !== null && Number.isFinite(Number(fatigue)) ? Number(fatigue) : null;
    const gemPath = Object.keys(slots).sort().map((k) => slots[k]).find((s) => s.path !== undefined && Number(s.path) >= 0);
    const gems = Math.floor(fat / 100), gemWord = `gem${gems === 1 ? "" : "s"}`, gemLetter = gemPath ? PATH_OF_NUMBER(gemPath.path) : null;
    const cost = fat === null ? (fatigue !== null ? `Fatigue ${fatigue}` : null)
      : fat >= 100 ? (gemLetter ? gemChip(gemLetter, gems, ` ${gemWord}`) : `${gems} ${gemPath ? spellPathName(gemPath.path) + " " : ""}${gemWord}`)
      : `${fat} fatigue`;
    const facts = [school !== null ? (SPELL_SCHOOLS[school] || `School #${school}`) : null,
      research !== null && school !== "-1" ? `Research ${research}` : null].filter(Boolean);
    const reqs = [paths.length ? joinParts(paths, " + ") : null, cost].filter(Boolean);
    return el("article", { class: "item-card" },
      el("div", { class: "item-card-head" },
        el("div", null, el("h2", { text: d.name || `${d.opener} ${d.id ?? d.selector ?? ""}` }),
          el("p", { class: "faint", text: facts.join(" · ") || "No school set" }),
          reqs.length ? el("p", { class: "muted" }, joinParts(reqs)) : null)),
      arg("descr") ? el("p", { class: "item-card-description", text: arg("descr") }) : null,
      contentEditLink(m, "spells", (x) => x.line === d.source.line, txt(d.name || "this spell")),
      otherDefDetails(m, d, null, true));
  }
  const BROWSE_KINDS = {
    spell: { label: "Spells", one: "spell", plural: "spells", openers: "#newspell / #selectspell" },
    item: { label: "Items", one: "item", plural: "items", openers: "#newitem / #selectitem" },
  };
  const browseQuery = {};
  function viewKindBrowse(m, kind) {
    const K = BROWSE_KINDS[kind], all = otherOfKind(m, kind), slug = m.project.slug;
    if (!all.length) return stateBox("empty", `No ${K.plural} in this project.`, CSRF ? `Use New ${K.one} to add one.` : "");
    const key = `${slug}:${kind}`;
    const search = el("input", { class: "input", type: "search", id: `browse-q-${kind}`, placeholder: `Search ${K.plural}`,
      "aria-label": `Search ${K.plural} by name, id or command`, value: browseQuery[key] || "", autocomplete: "off" });
    const status = el("p", { class: "faint", role: "status", "aria-live": "polite" });
    const listEl = el("div", { class: kind === "spell" ? "item-grid spell-grid" : "item-grid" });
    const hay = (d) => [d.name, d.id, d.selector, d.opener, ...(d.authored || []).map((c) => c.command)].map((v) => txt(v).toLowerCase()).join(" ");
    const fill = () => {
      const q = search.value.trim().toLowerCase();
      const shown = q ? all.filter((d) => hay(d).includes(q)) : all;
      status.textContent = q ? `${shown.length} of ${all.length} ${K.plural} match.` : `${all.length} ${all.length === 1 ? K.one : K.plural}.`;
      fillKids(listEl, shown.length ? shown.map((d) => kind === "item" ? itemCard(m, d) : spellCard(m, d))
        : stateBox("empty", `No ${K.plural} match "${search.value.trim()}".`, "Clear the search to see them all."));
    };
    search.addEventListener("input", () => { browseQuery[key] = search.value; fill(); });
    search.addEventListener("keydown", (e) => { if (e.key === "Escape" && search.value) { search.value = ""; browseQuery[key] = ""; fill(); } });
    fill();
    return el("div", { class: "stack" }, el("div", { class: "unit-filter" }, search), status, listEl);
  }

  function viewAssets(m) {
    const slug = m.project.slug;
    if (!m.assets.length) return stateBox("empty", "No asset files.", "The mod folder holds no files besides the .dm.");
    const card = (a) => {
      const missing = a.status === "missing";
      const preview = missing ? el("div", { class: "preview-missing", text: "file missing" })
        : a.browser_preview ? spriteImg(a.browser_preview, `${a.path}`, a.width && a.width <= 64 ? 2 : 1,
          el("div", { class: "preview-missing", text: a.format === "tga" ? "TGA preview unavailable (unsupported variant)" : "Preview unavailable" }))
          : el("div", { class: "preview-missing", text: "not an image" });
      return el("article", { class: `asset-card ${missing ? "missing" : ""}`, "aria-label": a.path },
        el("div", { class: "sprite-box" }, preview),
        el("div", { class: "path", text: a.path }),
        missing ? badge("referenced but missing", "err") : el("div", { class: "facts" },
          [a.format && a.format.toUpperCase(), a.width && `${a.width}×${a.height}`, a.depth && `${a.depth}-bit`, `${a.bytes} bytes`].filter(Boolean).join(" · "),
          null),
        (a.problems || []).map((p) => badge(p, "err")),
        el("div", { class: "facts" }, a.used_by.length ? ["Used by: ", a.used_by.map((x, i) => [i ? ", " : "",
          x.uid.startsWith("monster:") ? el("a", { href: route("p", slug, "units", x.uid.split(":")[1]) }, txt(x.name || x.uid))
            : x.uid.startsWith("nation:") ? el("a", { href: route("p", slug, "nation", x.uid.split(":")[1]) }, txt(x.name || x.uid)) : txt(x.name || x.uid),
          ` ${x.command} `, srcRef(slug, m.provenance.file, x.line)])] : badge("unreferenced", "warn")),
        missing ? null : el("div", { class: "btn-row" }, el("a", { class: "btn btn-small", href: `${a.url}?download=1`, download: "" }, "Download"),
          el("button", { type: "button", class: "btn btn-small btn-ghost", onclick: () => copy(a.sha256, "Hash") }, "Copy hash")));
    };
    return el("div", { class: "stack" },
      el("div", { class: "btn-row" }, el("span", { class: "muted", text: `${m.counts.asset_files} files · ${m.counts.sprite_frames} sprite frames · ${m.counts.flags} flag(s)` }),
        jsonActions(`/api/projects/${encodeURIComponent(slug)}/assets`, () => m.assets, "Assets JSON")),
      m.assets_skipped.length ? stateBox("error", "Some paths were skipped", m.assets_skipped.map((s) => `${s.path}: ${s.reason}`).join("; ")) : null,
      el("div", { class: "gallery" }, m.assets.map(card)));
  }

  async function viewSource(m, line, target) {
    const slug = m.project.slug;
    const url = `/api/projects/${encodeURIComponent(slug)}/source`;
    target.replaceChildren(stateBox("loading", "Loading source..."));
    let text;
    try { text = await getText(url); } catch (e) { target.replaceChildren(errorBox(e, "the .dm source")); return; }
    const hl = Number(line) || null;
    const pre = codeBlock(text.replace(/\r?\n$/, ""), 1, hl);
    target.replaceChildren(el("div", { class: "stack" },
      el("div", { class: "btn-row" }, el("span", { class: "muted mono", text: m.provenance.file }), el("span", { class: "hash", text: m.provenance.sha256 }),
        el("button", { type: "button", class: "btn btn-small", onclick: () => copy(text, "Source") }, "Copy source"),
        el("a", { class: "btn btn-small", href: `${url}?download=1`, download: "" }, "Download .dm"),
        el("a", { class: "btn btn-small btn-ghost", href: url, target: "_blank", rel: "noopener" }, "Open raw")),
      pre));
    if (hl) {
      // Scroll only the code box so the page header stays in place.
      const ln = pre.querySelector(`#L${hl}`);
      if (ln) { pre.scrollTop = ln.offsetTop - pre.clientHeight / 2; ln.setAttribute("tabindex", "-1"); ln.focus({ preventScroll: true }); }
    }
  }

  function viewValidation(m) {
    const slug = m.project.slug, v = m.validation;
    if (!v) return stateBox("error", "Validation could not run.", (m.diagnostics || []).map((d) => d.message).join(" "));
    const sec = (title, items) => panel(`${title} (${items.length})`, items.length ? diagnosticsList(slug, items, v.file) : el("p", { class: "muted", text: "None." }));
    const ins = m.inspection;
    return el("div", { class: "stack" },
      el("p", null, v.ok ? "No errors." : badge(`${v.errors.length} error${v.errors.length === 1 ? "" : "s"}`, "err")),
      sec("Errors", v.errors), v.warnings.length ? sec("Warnings", v.warnings) : null, v.unverified.length ? sec("Unverified", v.unverified) : null,
      compatibilitySection(m),
      techSection("Details", false,
        el("dl", { class: "kv" },
          el("dt", { text: "File" }), el("dd", { class: "mono", text: v.file }),
          el("dt", { text: "SHA-256" }), el("dd", { class: "hash", text: v.sha256 }),
          el("dt", { text: "Manual" }), el("dd", { text: txt(v.manual_version) }),
          el("dt", { text: "Target game" }), el("dd", { text: txt(v.target_game_version) }),
          ins ? [el("dt", { text: "Inspection" }), el("dd", { text: `${ins.statement_count} statements · ${ins.syntax_issues.length} syntax issues · ${ins.stray_text.length} stray text lines · ${ins.unverified_commands.length} unverified commands` })] : null),
        panel("Limitations", el("ul", null, v.limitations.map((l) => el("li", { text: l })))),
        panel("JSON", jsonActions(`/api/projects/${encodeURIComponent(slug)}/validation`, () => v, "Validation JSON"))));
  }

  // ---------- project health ----------
  // One prioritized, deduplicated list from the server's health report (GET /api/projects/<slug>/health). Errors are
  // always listed in full; longer warning, unverified and info lists show the first rows and expand on request.
  const HEALTH_SEV = { error: ["Blocker", "err"], warning: ["Warning", "warn"], unverified: ["Unverified", "info"], info: ["Info", ""] };
  const HEALTH_STATUS = { blocked: ["Blocked", "err", "Errors must be fixed before export."], attention: ["Needs review", "warn", "No errors; review the warnings."],
    unverified: ["Unverified", "info", "No errors or warnings; some items could not be checked."], clear: ["Clear", "ok", "No findings in the checked scope."] };
  const HEALTH_PLURAL = { error: "Blockers", warning: "Warnings", unverified: "Unverified", info: "Info" };
  const HEALTH_COUNT = { error: ["blocker", "blockers"], warning: ["warning", "warnings"], unverified: ["unverified", "unverified"], info: ["info", "info"] };
  const HEALTH_PAGE = 25;
  const healthRuns = new Map(); // slug -> revision last shown, so a recheck can say the project changed
  function healthObjectLink(m, obj, loc) {
    const slug = m.project.slug;
    if (!obj || obj.kind === "mod") return loc.line ? srcRef(slug, loc.file, loc.line) : null;
    const label = `${txt(obj.name || obj.kind)}${obj.id !== null && obj.id !== undefined ? ` (#${obj.id})` : ""}`;
    const tab = obj.origin === "project" && obj.id !== null && obj.id !== undefined ? { monster: "units", site: "sites", nation: "nation" }[obj.kind] : null;
    if (tab) return el("a", { href: route("p", slug, tab, obj.id) }, label);
    return el("span", null, label, obj.origin && obj.origin !== "project" ? el("span", { class: "faint", text: ` in ${obj.origin}` }) : null);
  }
  function healthRow(m, f) {
    const slug = m.project.slug, loc = f.location, [sevLabel, sevKind] = HEALTH_SEV[f.severity] || [f.severity, ""];
    const places = f.occurrences.filter((o) => o.line);
    return el("li", { class: `health-row is-${sevKind || "plain"}`, "data-finding": f.id },
      el("span", { class: `badge ${sevKind}`, text: sevLabel }),
      el("div", { class: "health-main" },
        el("div", { class: "health-title" }, el("strong", { text: f.title }), " ", el("code", { class: "faint", text: f.code }),
          f.count > 1 ? el("span", { class: "faint", text: ` · ${f.count} places` }) : null),
        el("div", { class: "health-msg", text: f.message }),
        el("div", { class: "health-where" }, healthObjectLink(m, loc.object, loc), loc.asset ? [" ", el("code", { text: loc.asset })] : null,
          loc.line && loc.object && loc.object.kind !== "mod" ? [" ", srcRef(slug, loc.file, loc.line)] : null),
        el("div", { class: "health-next" }, el("span", { class: "faint", text: "Next: " }), f.next_action),
        places.length > 1 ? el("details", { class: "health-places" }, el("summary", null, `All ${places.length} locations`),
          el("ul", { class: "plain-list" }, places.map((o) => el("li", null, srcRef(slug, o.file, o.line, true), " ",
            o.command ? el("code", { text: o.command }) : null, " ", el("span", { class: "faint", text: `${txt(o.source)}${o.message ? `: ${o.message}` : ""}` }))))) : null));
  }
  // Three or more findings with one code (e.g. several unreserved IDs) share a row listing their objects; the JSON keeps each.
  function healthCodeRow(m, fs) {
    const slug = m.project.slug, f = fs[0], [sevLabel, sevKind] = HEALTH_SEV[f.severity] || [f.severity, ""];
    return el("li", { class: `health-row is-${sevKind || "plain"}`, "data-code": f.code },
      el("span", { class: `badge ${sevKind}`, text: sevLabel }),
      el("div", { class: "health-main" },
        el("div", { class: "health-title" }, el("strong", { text: f.title }), " ", el("code", { class: "faint", text: f.code }),
          el("span", { class: "faint", text: ` · ${fs.length} findings` })),
        el("div", { class: "health-where" }, fs.map((x, i) => [i ? ", " : "", healthObjectLink(m, x.location.object, x.location) || el("code", { text: txt(x.location.asset) }),
          x.location.asset && x.location.object && x.location.object.kind !== "mod" ? [" ", el("code", { text: x.location.asset })] : null])),
        el("div", { class: "health-next" }, el("span", { class: "faint", text: "Next: " }), f.next_action),
        el("details", { class: "health-places" }, el("summary", null, "Messages"),
          el("ul", { class: "plain-list" }, fs.map((x) => el("li", null, x.location.line ? [srcRef(slug, x.location.file, x.location.line), " "] : null, x.message))))));
  }
  function healthGroup(m, sev, items) {
    if (!items.length) return null;
    const rows = [];
    for (const f of items) {
      const prev = rows[rows.length - 1];
      if (prev && prev[0].code === f.code) prev.push(f); else rows.push([f]);
    }
    const list = el("ul", { class: "health-list" });
    const more = el("button", { type: "button", class: "btn btn-small btn-ghost" });
    let shown = 0;
    const fill = () => {
      const next = sev === "error" ? rows.length : Math.min(rows.length, shown + HEALTH_PAGE);
      list.append(...rows.slice(shown, next).map((fs) => fs.length >= 3 ? healthCodeRow(m, fs) : fs.map((f) => healthRow(m, f))).flat());
      shown = next;
      if (shown >= rows.length) more.remove();
      else more.textContent = `Show ${Math.min(HEALTH_PAGE, rows.length - shown)} more of ${rows.length - shown}`;
    };
    more.addEventListener("click", fill);
    fill();
    return el("details", { class: "raw health-group", open: sev !== "info" || null, "data-severity": sev },
      el("summary", null, `${HEALTH_PLURAL[sev]} (${items.length})`), el("div", { class: "inner" }, list, shown < rows.length ? more : null));
  }
  function viewHealth(m) {
    const slug = m.project.slug, url = `/api/projects/${encodeURIComponent(slug)}/health`;
    const holder = el("div", { class: "stack health" }, stateBox("loading", "Checking project health..."));
    const recheck = el("button", { type: "button", class: "btn btn-small", onclick: () => load() }, "Recheck");
    let last = null;
    async function load() {
      recheck.disabled = true;
      const prev = healthRuns.get(slug) || null;
      try {
        const r = (await getJSON(prev ? `${url}?expected_revision=${encodeURIComponent(prev)}` : url)).result;
        last = r;
        healthRuns.set(slug, r.revision);
        draw(r, prev);
      } catch (e) {
        fillKids(holder, errorBox(e, "project health"), el("p", null, recheck));
      } finally { recheck.disabled = false; }
    }
    function draw(r, prev) {
      const [stLabel, stKind, stText] = HEALTH_STATUS[r.status] || [r.status, "", ""], c = r.counts;
      const pageOld = r.identity.source_sha256 && r.identity.source_sha256 !== m.provenance.sha256;
      const rc = r.recruitment.counts, RC = { normal: "recruitable", cap_only: "capital-only", site: "site-only", start_army: "start army", defence: "defence",
        hero: "hero", summon: "summon", pretender: "pretender", form: "alternate form", merc: "mercenary", event: "event", referenced: "other reference", unassigned: "unassigned" };
      const recruitText = Object.entries(rc).filter(([, n]) => n).map(([k, n]) => `${n} ${RC[k] || k}`).join(" · ");
      const noCatalog = ["none", "error", "snapshot_invalid"].includes(r.catalog.state);
      fillKids(holder,
        el("div", { class: "health-head" }, badge(stLabel, stKind),
          el("span", { class: "health-counts faint", text: ["error", "warning", "unverified", "info"].map((s) => `${c[s]} ${HEALTH_COUNT[s][c[s] === 1 ? 0 : 1]}`).join(" · ") }),
          recheck),
        el("p", { class: "panel-note" }, stText, " ", noCatalog ? "Vanilla references are unverified without a catalog."
          : `Catalog: ${r.catalog.state}${r.catalog.dataset_version ? ` (${r.catalog.dataset_version})` : ""}.`, " Static checks only; not a game-load or balance result."),
        el("div", { role: "status", "aria-live": "polite" },
          prev && r.stale ? stateBox("empty", "The project changed since the last check.", "These findings describe the current files.") : null),
        pageOld ? stateBox("empty", "Other tabs show an older revision.", el("button", { type: "button", class: "btn btn-small", onclick: () => { state.models.delete(slug); render(); } }, "Reload project")) : null,
        r.identity.consistent ? null : stateBox("error", "Files changed while health was read.", "Recheck when edits have finished."),
        r.findings.length ? ["error", "warning", "unverified", "info"].map((s) => healthGroup(m, s, r.findings.filter((f) => f.severity === s)))
          : stateBox("empty", "No findings.", "Nothing to fix in the checked scope."),
        techSection("Scope, recruitment and revision", false,
          el("dl", { class: "kv" },
            el("dt", { text: "Revision" }), el("dd", { class: "mono", title: r.revision, text: shortSha(r.revision) }),
            el("dt", { text: "Source" }), el("dd", { class: "mono", title: txt(r.identity.source_sha256), text: shortSha(r.identity.source_sha256) }),
            el("dt", { text: "Dependencies" }), el("dd", { text: r.scope.dependencies.length ? r.scope.dependencies.join(", ") : "none declared" }),
            el("dt", { text: "Recruitment" }), el("dd", { text: recruitText || "no new units" }),
            el("dt", { text: "Checked" }), el("dd", { text: r.scope.checked.join(", ") }),
            el("dt", { text: "Not checked" }), el("dd", null, el("ul", { class: "plain-list" }, r.scope.not_checked.map((x) => el("li", null, el("code", { text: x.check }), " ", x.reason))))),
          panel("Limitations", el("ul", null, r.limitations.map((l) => el("li", { text: l })))),
          panel("JSON", jsonActions(url, () => last, "Health JSON"))));
    }
    load();
    return holder;
  }

  // ---------- docs ----------
  function renderMarkdown(src) {
    const root = el("div", { class: "md prose" });
    const lines = src.replace(/\r\n?/g, "\n").split("\n");
    const inline = (s) => {
      const out = [];
      const re = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*\s][^*]*\*)|(\[([^\]]+)\]\(([^)\s]+)\))/g;
      let last = 0, mm;
      while ((mm = re.exec(s))) {
        if (mm.index > last) out.push(s.slice(last, mm.index));
        if (mm[1]) out.push(el("code", { text: mm[1].slice(1, -1) }));
        else if (mm[2]) out.push(el("strong", { text: mm[2].slice(2, -2) }));
        else if (mm[3]) out.push(el("em", { text: mm[3].slice(1, -1) }));
        else {
          const href = mm[6];
          if (/^https?:\/\//i.test(href)) out.push(el("a", { href, rel: "noopener noreferrer", target: "_blank" }, mm[5]));
          else if (/^[A-Za-z0-9_.\-]+\.md(#.*)?$/.test(href)) out.push(el("a", { href: route("docs", href.split("#")[0]) }, mm[5]));
          else out.push(el("span", { title: href }, mm[5]));
        }
        last = mm.index + mm[0].length;
      }
      if (last < s.length) out.push(s.slice(last));
      return out;
    };
    let i = 0;
    while (i < lines.length) {
      const l = lines[i];
      if (/^```/.test(l)) {
        const buf = []; i++;
        while (i < lines.length && !/^```/.test(lines[i])) buf.push(lines[i++]);
        i++; root.append(el("pre", null, el("code", { text: buf.join("\n") }))); continue;
      }
      const h = l.match(/^(#{1,4})\s+(.*)$/);
      if (h) { root.append(el(`h${Math.min(4, h[1].length)}`, null, inline(h[2]))); i++; continue; }
      if (/^\s*\|.*\|\s*$/.test(l) && i + 1 < lines.length && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1])) {
        const cells = (s) => s.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
        const head = cells(l); i += 2; const body = [];
        while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) body.push(cells(lines[i++]));
        root.append(el("div", { class: "table-wrap" }, el("table", null, el("thead", null, el("tr", null, head.map((c) => el("th", null, inline(c))))),
          el("tbody", null, body.map((r) => el("tr", null, r.map((c) => el("td", null, inline(c))))))))); continue;
      }
      if (/^\s*([-*]|\d+\.)\s+/.test(l)) {
        const ordered = /^\s*\d+\./.test(l);
        const list = el(ordered ? "ol" : "ul");
        while (i < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[i])) {
          let item = lines[i++].replace(/^\s*([-*]|\d+\.)\s+/, "");
          while (i < lines.length && /^\s{2,}\S/.test(lines[i]) && !/^\s*([-*]|\d+\.)\s+/.test(lines[i])) item += " " + lines[i++].trim();
          list.append(el("li", null, inline(item)));
        }
        root.append(list); continue;
      }
      if (/^>\s?/.test(l)) {
        const buf = [];
        while (i < lines.length && /^>\s?/.test(lines[i])) buf.push(lines[i++].replace(/^>\s?/, ""));
        root.append(el("blockquote", null, inline(buf.join(" ")))); continue;
      }
      if (!l.trim()) { i++; continue; }
      const buf = [];
      while (i < lines.length && lines[i].trim() && !/^(#{1,4}\s|```|>|\s*([-*]|\d+\.)\s|\s*\|)/.test(lines[i])) buf.push(lines[i++].trim());
      if (!buf.length) buf.push(lines[i++]);
      root.append(el("p", null, inline(buf.join(" "))));
    }
    return root;
  }
  async function viewDocs(target, slug, name) {
    const projectDocs = slug ? (await model(slug)).project.docs : [];
    const globalDocs = (state.meta && state.meta.docs) || [];
    const all = [...projectDocs.map((d) => ({ ...d, scope: "project" })), ...globalDocs.map((d) => ({ ...d, scope: "global" }))];
    const href = (d) => d.scope === "project" ? route("p", slug, "docs", d.name) : route("docs", d.name);
    const nav = all.length ? el("nav", { "aria-label": "Documents", class: "btn-row" }, all.map((d) =>
      el("a", { class: "btn btn-small", href: href(d), "aria-pressed": d.name === name ? "true" : "false" }, d.name, d.scope === "project" ? badge("project", "copper") : null)))
      : stateBox("empty", "No documents.", "Start the server with --docs <folder> to show review/design Markdown, or add *.md files to the project folder.");
    const body = el("div");
    target.replaceChildren(el("div", { class: "stack" }, nav, body));
    const doc = all.find((d) => d.name === name);
    if (!name) { if (all.length) body.append(el("p", { class: "muted", text: "Choose a document." })); return; }
    if (!doc) { body.append(stateBox("error", "Document not found.", name)); return; }
    body.append(stateBox("loading", "Loading document..."));
    const url = doc.scope === "project" ? `/api/projects/${encodeURIComponent(slug)}/docs/${encPath(doc.name)}` : `/api/docs/${encodeURIComponent(doc.name)}`;
    try {
      const text = await getText(url);
      body.replaceChildren(panel(null, el("div", { class: "btn-row" }, el("span", { class: "muted mono", text: doc.name }),
        el("a", { class: "btn btn-small", href: `${url}?download=1`, download: "" }, "Download"),
        el("a", { class: "btn btn-small btn-ghost", href: url, target: "_blank", rel: "noopener" }, "Raw")), renderMarkdown(text)));
    } catch (e) { body.replaceChildren(errorBox(e, "the document")); }
  }

  // ---------- authoring hub (the Edit tab): weapons, armour, events, heroes, advanced commands, reference, playtests ----------
  // Spells, sites, items and mercenaries are edited inside their own sections (see SECTION_EDITORS); the forms are shared.
  // Every form keeps its draft in state.authoring (per project and kind/item), reviews with preview:true, then saves with
  // preview:false against the SHA-256 the page loaded. A 409 reloads the file and keeps the draft.
  const apiBase = (slug) => `/api/projects/${encodeURIComponent(slug)}`;
  // Sections grouped for the section picker; keys (and so routes) are unchanged.
  // [key, label, description, advanced]; the landing page lists the same entries with their descriptions.
  const AUTH_GROUPS = [
    ["Structured forms", [["weapons", "Weapons", "Field form for #newweapon / #selectweapon blocks, with a vanilla or project template."],
      ["armors", "Armour", "Field form for #newarmor / #selectarmor blocks, with a vanilla or project template."],
      ["heroes", "Heroes", "Hero and multihero slots of the nation chosen in the Nation selector."]]],
    ["Advanced line editors", [["events", "Events", "Raw #newevent lines from the event modding manual; no structured form exists.", true],
      ["commands", "All manual commands", "Any block type, any documented command. Use it when a structured form does not cover a field.", true]]],
    ["Reference and records", [["reference", "Reference lookup", "Quick vanilla spell, site, weapon and armour lookup with Use as template."],
      ["playtests", "Playtests", "Observations from real games, tied to the .dm revision played."]]],
  ];
  // Browse and edit share one section for these: "#/p/<slug>/<section>" browses, "<section>/edit/<key>" opens the editor.
  // Old "#/p/<slug>/author/<section>/<key>" links are redirected there by the router.
  const SECTION_EDITORS = { spells: ["New spell", "edit", "~new"], sites: ["New site", "edit", "~new"], items: ["New item", "edit", "~new"], mercs: ["New company", "~new"] };
  const authRoute = (slug, sub, ...rest) => SECTION_EDITORS[sub] ? route("p", slug, sub, "edit", ...rest) : route("p", slug, "author", sub, ...rest);
  // Items and existing mercenary companies have no structured form: their Edit mode is the advanced line editor.
  const ADVANCED_SECTIONS = new Set(["items", "mercs"]);
  const advancedTag = () => badge("Advanced", "warn");
  // Browse/Edit switch at the top of those sections; Browse also offers the New action.
  function sectionModes(m, tab, editing, arg) {
    const slug = m.project.slug, [newLabel, ...newPath] = SECTION_EDITORS[tab], creating = !editing && arg === "~new";
    const mode = (on, href, text) => el("a", { class: "btn btn-small", href, "aria-current": on ? "page" : null }, text);
    return el("div", { class: "btn-row section-modes" },
      el("nav", { class: "btn-row seg mode-switch", "aria-label": `${TABS.find((t) => t[0] === tab)[1]} view` },
        mode(!editing && !creating, route("p", slug, tab), "Browse"), mode(editing, route("p", slug, tab, "edit"), ADVANCED_SECTIONS.has(tab) ? "Advanced edit" : "Edit")),
      editing ? null : CSRF ? el("a", { class: "btn btn-small", href: route("p", slug, tab, ...newPath), "aria-current": creating ? "page" : null }, newLabel)
        : creating ? null : noToken());
  }
  // The guarded editor of one section: the field form for spells and sites, the line editor for items and mercenaries.
  const sectionEditor = (m, tab, key) => CONTENT_KINDS[tab] ? contentView(m, tab, key) : commandsHub(m, tab, [key]);
  const CONTENT_KINDS = {
    sites: { one: "site", label: "Sites", projectTemplates: true, templateRequired: false },
    spells: { one: "spell", label: "Spells", projectTemplates: false, templateRequired: true },
    weapons: { one: "weapon", label: "Weapons", projectTemplates: true, templateRequired: false },
    armors: { one: "armour", label: "Armour", projectTemplates: true, templateRequired: false },
  };
  const REF_CATS = [["spells", "Spells"], ["sites", "Sites"], ["weapons", "Weapons"], ["armors", "Armour"]];
  const GEM_PATHS = [[0, "Fire"], [1, "Air"], [2, "Water"], [3, "Earth"], [4, "Astral"], [5, "Death"], [6, "Nature"], [7, "Glamour"], [8, "Blood"]];
  const MAX_IMPORT_BYTES = 6 * 1024 * 1024;
  const WIDE_TEXT = new Set(["descr", "details", "observations", "result_summary", "opponents"]);
  const safeId = (s) => String(s).replace(/[^A-Za-z0-9_-]/g, "_");
  const sameVal = (a, b) => JSON.stringify(a === undefined ? null : a) === JSON.stringify(b === undefined ? null : b);
  const fmtBytes = (n) => n >= 1048576 ? `${(n / 1048576).toFixed(2)} MB` : n >= 1024 ? `${(n / 1024).toFixed(1)} KB` : `${n} bytes`;
  // replaceChildren() would print null/false as text; drop them first.
  const fillKids = (node, ...kids) => node.replaceChildren(...kids.flat(Infinity).filter((k) => k !== null && k !== undefined && k !== false));
  // Leaving a review (Back or Escape) returns focus to the control that opened it (marked with RT); when that control
  // is gone or disabled, focusIn falls back to the editor heading.
  const REVIEW_TRIGGER = "[data-review-trigger]";
  const RT = { "data-review-trigger": "" };
  const escapeReview = (holder, inReview, back) => holder.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !e.defaultPrevented && inReview()) { e.preventDefault(); back(); }
  });
  const focusIn = (root, sel) => {
    if (!sel) return;
    let t = root.querySelector(sel);
    if (t && t.disabled) t = root.querySelector("h3[tabindex], h4[tabindex], h3");
    if (!t) return;
    if (!t.hasAttribute("tabindex") && !/^(INPUT|SELECT|TEXTAREA|BUTTON|A)$/.test(t.tagName)) t.setAttribute("tabindex", "-1");
    t.focus();
  };

  // GET cache for authoring data, keyed by URL; cleared for a project after any write. Bounded: the least recently
  // used entries are dropped (a dropped entry is simply fetched again).
  const AUTH_CACHE_MAX = 200;
  function authLoad(url, force) {
    if (force || !state.authData.has(url)) state.authData.set(url, getJSON(url).then((r) => r.result));
    const p = state.authData.get(url);
    state.authData.delete(url);
    state.authData.set(url, p);
    while (state.authData.size > AUTH_CACHE_MAX) state.authData.delete(state.authData.keys().next().value);
    p.catch(() => { if (state.authData.get(url) === p) state.authData.delete(url); });
    return p;
  }
  function invalidateAuth(slug) {
    for (const k of [...state.authData.keys()]) if (!slug || k.startsWith(apiBase(slug) + "/")) state.authData.delete(k);
    for (const k of [...inspCache.keys()]) if (!slug || k.startsWith(apiBase(slug) + "/")) inspCache.delete(k);
  }
  // Loads url, then fills the box with draw(result). A missing route (backend not updated) shows the server message.
  function asyncView(url, what, draw) {
    const box = el("div", { class: "stack", "aria-busy": "true" }, stateBox("loading", `Loading ${what}...`));
    authLoad(url).then((r) => {
      box.removeAttribute("aria-busy");
      try { box.replaceChildren(...[draw(r)].flat().filter(Boolean)); }
      catch (e) { box.replaceChildren(stateBox("error", "This view failed to render.", String((e && e.message) || e))); }
    }, (e) => {
      box.removeAttribute("aria-busy");
      const code = (e && e.error && e.error.code) || "";
      fillKids(box, errorBox(e, what),
        /^(http_404|not_found|bad_response|unknown_route)$/.test(code) ? el("p", { class: "faint", text: "This server may be a build without this part of the authoring API. Restart `kosmokrator serve` from an updated checkout." }) : null,
        el("div", { class: "btn-row" }, el("button", { type: "button", class: "btn", onclick: () => { state.authData.delete(url); render(); } }, "Retry")));
    });
    return box;
  }
  const noToken = () => el("p", { class: "faint", text: "Writing is unavailable: this server did not provide an editor token. Restart `kosmokrator serve` and reload." });
  const statusLine = (text) => el("span", { class: "edit-count", role: "status", "aria-live": "polite", text });

  // ----- generic field model (from the server's `fields` spec) -----
  // "textarea" is a multi-line text field; everything else keeps its type.
  const specOf = (fields) => (fields || []).map((f) => (f.type === "textarea" ? { ...f, type: "text", multi: true } : f));
  // Draft ("raw") shapes: int/text/choice/monster/nation -> string, flag -> bool, gems -> [{path, amount}] strings, monsters -> [int].
  function rawOf(f, v) {
    switch (f.type) {
      case "flag": return !!v;
      case "gems": return (Array.isArray(v) ? v : []).map((g) => ({ path: String(g.path), amount: String(g.amount) }));
      case "monsters": return (Array.isArray(v) ? v : []).map(Number);
      default: return v === null || v === undefined ? "" : String(v);
    }
  }
  function normOf(f, raw) {
    switch (f.type) {
      case "flag": return { value: !!raw };
      case "text": return { value: raw === "" ? null : raw };
      case "gems": {
        const rows = raw || [];
        for (const g of rows) {
          if (!/^\d+$/.test(String(g.path).trim()) || Number(g.path) > 8) return { error: "Choose a magic path for every gem row." };
          if (!/^\d+$/.test(String(g.amount).trim()) || Number(g.amount) < 1) return { error: "Each gem row needs a whole amount of at least 1." };
        }
        return { value: rows.length ? rows.map((g) => ({ path: Number(g.path), amount: Number(g.amount) })) : null };
      }
      case "monsters": return { value: raw && raw.length ? raw.map(Number) : null };
      default: {
        const t = String(raw).trim();
        if (t === "") return { value: null };
        if (!/^-?\d+$/.test(t)) return { error: f.type === "int" ? "Whole numbers only." : "Choose a value from the list, or enter an id." };
        const n = Number(t);
        if (f.type === "int" && f.min !== undefined && f.min !== null && n < f.min) return { error: `Allowed ${f.min} to ${f.max ?? "…"}.` };
        if (f.type === "int" && f.max !== undefined && f.max !== null && n > f.max) return { error: `Allowed ${f.min ?? "…"} to ${f.max}.` };
        return { value: n };
      }
    }
  }
  const gemName = (choices, p) => { const c = (choices || []).find((x) => Number(x.value) === Number(p)); return c ? c.label : (GEM_PATHS.find((x) => x[0] === Number(p)) || [0, `path ${p}`])[1]; };
  const optName = (list, id) => { const o = (list || []).find((x) => Number(x.id) === Number(id)); return o ? `${txt(o.name)} (#${id})` : `#${id}`; };
  function fmtValue(f, v, opts, fields) {
    if (v === null || v === undefined) return "—";
    if (!f) return typeof v === "object" ? JSON.stringify(v) : String(v);
    const pathChoices = ((fields || []).find((x) => x.key === "path") || {}).choices;
    switch (f.type) {
      case "flag": return v ? "yes" : "no";
      case "choice": { const c = (f.choices || []).find((x) => String(x.value) === String(v)); return c ? `${c.label} (${v})` : String(v); }
      case "monster": return optName(opts && opts.monsters, v);
      case "nation": return optName(opts && opts.nations, v);
      case "gems": return Array.isArray(v) && v.length ? v.map((g) => `${g.amount} × ${gemName(pathChoices, g.path)}`).join(", ") : "none";
      case "monsters": return Array.isArray(v) && v.length ? v.map((id) => optName(opts && opts.monsters, id)).join(", ") : "none";
      default: return typeof v === "object" ? JSON.stringify(v) : String(v);
    }
  }
  // Values to send: only fields the user changed; null removes the authored line. Also per-field input errors.
  function fieldChanges(fields, touched, current) {
    const values = {}, errors = {};
    for (const [key, raw] of Object.entries(touched)) {
      const f = fields.find((x) => x.key === key);
      if (!f) continue;
      const n = normOf(f, raw);
      if (n.error) { errors[key] = n.error; continue; }
      const cur = normOf(f, rawOf(f, current ? current[key] : undefined)).value;
      if (!sameVal(n.value, cur)) values[key] = n.value;
    }
    return { values, errors };
  }
  // One labelled control. c: { dr, idp, cur, err, opts, fields, line, slug, file, changed, redraw, edit }
  function authField(f, c) {
    const id = `${c.idp}-${safeId(f.key)}`, hintId = `${id}-hint`, errId = `${id}-err`;
    const t = c.dr.touched, curRaw = rawOf(f, c.cur);
    const val = f.key in t ? t[f.key] : curRaw;
    const set = (v, focusSel) => {
      if (sameVal(v, curRaw)) delete t[f.key]; else t[f.key] = v;
      c.dr.msg = null; c.dr.preview = null; c.dr.serverErr = null;
      if (focusSel) c.redraw(focusSel); else c.changed(f.key);
    };
    const aria = { "aria-invalid": c.err ? "true" : null, "aria-describedby": `${errId} ${hintId}` };
    const isChanged = f.key in t;
    let control, group = false;
    if (f.type === "flag") {
      const cb = el("input", { type: "checkbox", id, "data-key": f.key, ...aria });
      cb.checked = !!val;
      cb.addEventListener("change", () => set(cb.checked));
      control = el("div", { class: "edit-control" }, cb, el("span", { class: "faint", text: c.edit && c.cur ? "set in this block" : "" }));
    } else if (f.type === "choice" || ((f.type === "monster" || f.type === "nation") && ((c.opts && c.opts[f.type === "monster" ? "monsters" : "nations"]) || []).length)) {
      const list = f.type === "choice" ? (f.choices || []).map((x) => [String(x.value), `${x.label} (${x.value})`])
        : (c.opts[f.type === "monster" ? "monsters" : "nations"] || []).map((x) => [String(x.id), `${txt(x.name)} (#${x.id}${x.role ? `, ${x.role}` : ""})`]);
      if (val !== "" && !list.some((x) => x[0] === val)) list.unshift([val, `${val} (not in the list)`]);
      const sel = el("select", { class: "input" + (isChanged ? " changed" : ""), id, "data-key": f.key, ...aria },
        el("option", { value: "", text: c.edit && curRaw !== "" ? "Not set (remove the line)" : "Not set" }),
        list.map(([v, l]) => el("option", { value: v, text: l })));
      sel.value = val;
      sel.addEventListener("change", () => { sel.classList.toggle("changed", sel.value !== curRaw); set(sel.value); });
      control = el("div", { class: "edit-control" }, sel);
    } else if (f.type === "gems") {
      group = true;
      const pathChoices = ((c.fields.find((x) => x.key === "path") || {}).choices || []).map((x) => [String(x.value), x.label]);
      const paths = pathChoices.length ? pathChoices : GEM_PATHS.map(([v, l]) => [String(v), l]);
      const rows = val.map((g, i) => {
        const ps = el("select", { class: "input", id: `${id}-p${i}`, "aria-label": `${f.label}: path, row ${i + 1}` },
          el("option", { value: "", text: "Path…" }), paths.map(([v, l]) => el("option", { value: v, text: `${l} (${v})` })));
        ps.value = g.path;
        const am = el("input", { class: "input num-input", id: `${id}-a${i}`, inputmode: "numeric", autocomplete: "off", value: g.amount, "aria-label": `${f.label}: amount, row ${i + 1}` });
        const upd = () => set(val.map((x, j) => (j === i ? { path: ps.value, amount: am.value } : x)));
        ps.addEventListener("change", upd); am.addEventListener("input", upd);
        return el("li", { class: "edit-control" }, ps, am,
          el("button", { type: "button", class: "btn btn-small btn-ghost", "aria-label": `Remove gem row ${i + 1}`, onclick: () => set(val.filter((_, j) => j !== i), `#${id}-add`) }, "Remove"));
      });
      control = el("div", { class: "multi-control", role: "group", "aria-labelledby": `${id}-lbl`, "aria-describedby": `${errId} ${hintId}` },
        rows.length ? el("ul", { class: "plain-list" }, rows) : el("p", { class: "faint", text: "No gems." }),
        el("button", { type: "button", class: "btn btn-small", id: `${id}-add`, onclick: () => set([...val, { path: "", amount: "1" }], `#${id}-p${val.length}`) }, "Add gem"));
    } else if (f.type === "monsters") {
      group = true;
      const mons = (c.opts && c.opts.monsters) || [];
      const add = el("select", { class: "input", id: `${id}-pick`, "aria-label": `${f.label}: monster to add` },
        el("option", { value: "", text: "Choose a monster…" }), mons.map((x) => el("option", { value: String(x.id), text: `${txt(x.name)} (#${x.id}${x.role ? `, ${x.role}` : ""})` })));
      control = el("div", { class: "multi-control", role: "group", "aria-labelledby": `${id}-lbl`, "aria-describedby": `${errId} ${hintId}` },
        val.length ? el("ul", { class: "plain-list chips" }, val.map((mid, i) => el("li", { class: "cmp-chip" }, el("span", { text: optName(mons, mid) }),
          el("button", { type: "button", class: "btn btn-small btn-ghost", "aria-label": `Remove ${optName(mons, mid)} from ${f.label}`, onclick: () => set(val.filter((_, j) => j !== i), `#${id}-pick`) }, "Remove"))))
          : el("p", { class: "faint", text: "None." }),
        el("div", { class: "edit-control" }, add, el("button", { type: "button", class: "btn btn-small", onclick: () => {
          if (!add.value) { add.focus(); return; }
          set([...val, Number(add.value)], `#${id}-pick`);
        } }, "Add")),
        mons.length ? null : el("p", { class: "faint", text: "This project defines no monsters to choose from." }));
    } else if (f.type === "text" && (WIDE_TEXT.has(f.key) || f.multi)) {
      const ta = el("textarea", { class: "input" + (isChanged ? " changed" : ""), id, rows: "3", "data-key": f.key, maxlength: f.max ? String(f.max) : null, ...aria });
      ta.value = val;
      ta.addEventListener("input", () => { ta.classList.toggle("changed", ta.value !== curRaw); set(ta.value); });
      control = ta;
    } else {
      const num = f.type !== "text";
      const inp = el("input", { class: "input" + (num ? " num-input" : "") + (isChanged ? " changed" : ""), id, type: "text", autocomplete: "off", "data-key": f.key,
        inputmode: num ? "numeric" : null, maxlength: !num && f.max ? String(f.max) : null, value: val, ...aria });
      inp.addEventListener("input", () => { inp.classList.toggle("changed", inp.value !== curRaw); set(inp.value); });
      control = el("div", { class: "edit-control" }, inp);
    }
    const authored = c.edit && c.line;
    const meta = el("div", { class: "field-meta", id: hintId },
      c.edit ? (authored ? el("span", { class: "field-src" }, badge("authored", "authored"), " ", srcRef(c.slug, c.file, c.line, false)) : el("span", { class: "faint", text: "not authored in this block" })) : null,
      f.type === "int" && (f.min != null || f.max != null) ? el("span", { class: "faint", text: ` · ${f.min ?? "…"}–${f.max ?? "…"}` }) : null,
      f.type === "text" && f.max ? el("span", { class: "faint", text: ` · up to ${f.max} characters` }) : null,
      f.help ? el("span", { text: ` · ${f.help}` }) : null,
      f.source ? el("span", { class: "faint cite", text: ` · Manual: ${f.source}` }) : null);
    const removeBtn = authored && !(f.key in t && sameVal(normOf(f, t[f.key]).value, null))
      ? el("button", { type: "button", class: "btn btn-small btn-ghost", title: `Delete the authored line ${c.line}`, onclick: () => set(f.type === "flag" ? false : f.type === "gems" || f.type === "monsters" ? [] : "", `#${id}, #${id}-add, #${id}-pick`) }, "Remove line") : null;
    return el("div", { class: "edit-field" + (group || f.type === "text" ? " wide" : ""), "data-field": f.key },
      group ? el("span", { class: "lbl", id: `${id}-lbl`, text: f.label }) : el("label", { for: id, text: f.label }),
      control, removeBtn ? el("div", null, removeBtn) : null, meta,
      el("div", { class: "field-err", id: errId, "aria-live": "polite", text: c.err || "" }));
  }
  // Server field errors ({details:{field}}) are shown next to that field.
  const serverFieldErr = (dr) => {
    const e = dr.msg && dr.msg.kind === "err" && dr.msg.err && dr.msg.err.error;
    return e && e.details && e.details.field ? { field: String(e.details.field), message: e.message } : null;
  };
  function changesTable(r, fields, opts) {
    const label = (k) => (fields.find((x) => x.key === k) || { label: k }).label;
    const show = (k, v) => v === null || v === undefined ? el("span", { class: "faint", text: "—" }) : el("code", { text: typeof v === "string" ? v : fmtValue(fields.find((x) => x.key === k), v, opts, fields) });
    if (!(r.changes || []).length) return el("p", { class: "muted", text: "No changes: the file already says this." });
    return table(["Field", "Change", "Before", "After", "Line"], r.changes.map((x) => [el("strong", { text: label(x.field) }),
      badge(x.action, x.action === "remove" ? "warn" : x.action === "add" ? "authored" : "copper"), show(x.field, x.before), show(x.field, x.after),
      x.line ? el("span", { class: "mono", text: `L${x.line}` }) : el("span", { class: "faint", text: "new" })]));
  }
  // Review: changes, warnings, explanation and the exact diff, then an explicit save.
  function authReview(r, fields, opts, saveLabel, onSave, onBack, onCancel) {
    return el("div", { class: "stack" },
      el("h4", { tabindex: "-1", "data-focus": "review", text: "Review before saving" }),
      r.name || r.id !== undefined ? el("p", null, `${txt(r.name || "")}${r.id !== null && r.id !== undefined ? ` (#${r.id})` : ""}`, r.key ? el("span", { class: "faint", text: ` · key ${r.key}` }) : null) : null,
      changesTable(r, fields, opts),
      (r.warnings || []).length ? el("ul", { class: "diag" }, r.warnings.map((w) => el("li", null, badge("check", "warn"), " ", el("span", { text: w })))) : null,
      (r.explanation || []).map((t) => el("p", { class: "panel-note", text: t })),
      r.note ? el("p", { class: "panel-note", text: r.note }) : null,
      typeof r.diff === "string" && r.diff ? diffView(r.diff) : el("p", { class: "faint", text: "No text change." }),
      el("p", { class: "panel-note", text: "Saved with a backup of the previous .dm. Static checks only: test in game." }),
      el("div", { class: "btn-row" },
        r.changes && !r.changes.length ? el("span", { class: "muted", text: "Nothing to save." })
          : el("button", { type: "button", class: "btn", onclick: onSave }, saveLabel),
        el("button", { type: "button", class: r.changes && !r.changes.length ? "btn" : "btn btn-ghost", onclick: onBack }, "Back to the form"),
        onCancel ? el("button", { type: "button", class: "btn btn-ghost", onclick: onCancel }, "Cancel (discard)") : null));
  }

  // Landing of Advanced tools: what each tool is for, and where the structured editors of other definitions live.
  function authoringHome(m) {
    const slug = m.project.slug;
    const where = [["Units", "units", "Edit on a unit's page; New unit and Duplicate in the list."], ["Nation", "nation", "Edit nation on the nation's page; New nation there too."],
      ["Sites", "sites", "Edit on a site card or page."], ["Spells", "spells", "Edit on a spell card."],
      ["Items", "items", "Advanced edit (raw lines) on an item card."], ["Mercenaries", "mercs", "New company form; existing companies use Advanced edit."]];
    return el("div", { class: "stack auth-home" },
      el("p", { class: "panel-note", text: "Most editing happens where you browse. These tools cover the definitions without a section of their own, raw manual commands, vanilla lookup and playtest notes." }),
      AUTH_GROUPS.map(([g, items]) => el("section", { class: "panel", "aria-label": g }, el("h3", { text: g }),
        el("ul", { class: "tool-list" }, items.map(([k, l, d, adv]) => el("li", null,
          el("a", { href: route("p", slug, "author", k) }, l), adv ? [" ", advancedTag()] : null, el("span", { class: "faint", text: ` ${d}` })))),
        g === "Reference and records" ? el("p", { class: "panel-note" }, "For filters, units, items, events and mercenaries, browse the ",
          el("a", { href: route("p", slug, "inspector") }, "Vanilla catalog"), ". Only its site, spell, weapon and armour entries offer Use as template; the other categories are for browsing.") : null)),
      el("section", { class: "panel", "aria-label": "Editing in other sections" }, el("h3", { text: "Editing in other sections" }),
        el("ul", { class: "tool-list" }, where.map(([l, tab, d]) => el("li", null, el("a", { href: route("p", slug, tab) }, l), el("span", { class: "faint", text: ` ${d}` }))))));
  }
  function viewAuthoring(m, sub, rest) {
    const slug = m.project.slug;
    // Bare #/p/<slug>/author opens the Advanced tools overview; every section keeps its own route.
    const pick = el("select", { class: "input", id: "auth-section" }, el("option", { value: "", text: "Overview" }), AUTH_GROUPS.map(([g, items]) =>
      el("optgroup", { label: g }, items.map(([k, l, , adv]) => el("option", { value: k, text: adv ? `${l} (advanced)` : l })))));
    pick.value = sub || "";
    pick.addEventListener("change", () => { location.hash = pick.value ? route("p", slug, "author", pick.value) : route("p", slug, "author"); });
    const nav = el("nav", { class: "nation-bar subtabs", "aria-label": "Advanced tools sections" },
      el("label", { for: "auth-section", text: "Tool" }), pick);
    let body;
    if (!sub) body = authoringHome(m);
    else if (CONTENT_KINDS[sub]) body = contentView(m, sub, rest[0]);
    else if (sub === "heroes") body = heroesView(m);
    else if (CMD_SUBS[sub] || sub === "commands") body = commandsHub(m, sub, rest);
    else if (sub === "reference") body = referenceView(m, rest[0], rest[1]);
    else if (sub === "playtests") body = playtestsView(m);
    else body = stateBox("error", "Unknown authoring section.", sub);
    return el("div", { class: "stack authoring" }, nav, body);
  }

  // ----- sites / spells / weapons / armour -----
  function contentView(m, kind, sel) {
    const slug = m.project.slug, K = CONTENT_KINDS[kind], url = `${apiBase(slug)}/content/${kind}`;
    return asyncView(url, K.label.toLowerCase(), (st) => {
      st.fields = specOf(st.fields);
      const items = st.items || [];
      const selected = sel && sel !== "~new" ? items.find((i) => String(i.key) === String(sel)) : null;
      const list = el("ul", { class: "auth-list", "aria-label": K.label }, items.map((it) => el("li", null,
        el("a", { class: "auth-item", href: authRoute(slug, kind, it.key), "aria-current": it === selected ? "true" : null,
          onclick: () => { const d = state.authoring.get(`${slug}:${kind}:${it.key}`); if (d) d.open = true; } },
          el("span", { class: "nm", text: it.name || "(unnamed)" }),
          el("span", { class: "sub" }, it.id !== null && it.id !== undefined ? `#${it.id}` : null,
            it.editable ? null : [" ", badge("read-only", "warn")])))));
      const newDraft = state.authoring.get(`${slug}:${kind}:~new`);
      const left = el("div", { class: "unit-pane auth-pane" },
        CSRF ? el("div", { class: "btn-row" }, el("a", { class: "btn btn-small", href: authRoute(slug, kind, "~new"), "aria-current": sel === "~new" ? "page" : null }, `New ${K.one}`),
          draftBadge(newDraft)) : noToken(),
        el("p", { class: "faint", text: `${items.length} ${items.length === 1 ? K.one : K.label.toLowerCase()}` }),
        items.length ? list : stateBox("empty", `No ${K.label.toLowerCase()} yet.`, `Use New ${K.one} to add one.`));
      let right;
      if (sel === "~new") right = CSRF ? contentForm(m, kind, st, null) : noToken();
      else if (sel && !selected) right = stateBox("error", `${K.one} "${sel}" not found.`, "It may have moved after a save (spells are keyed by their line). Choose it again from the list.");
      else if (selected) right = contentDetail(m, kind, st, selected, url);
      else right = el("div", { class: "stack" }, stateBox("empty", `Choose ${K.one}.`), contentNotes(st));
      return el("div", { class: "split" }, left, el("div", { class: "auth-detail" }, right));
    });
  }
  function contentNotes(st) {
    if (!(st.notes || []).length && !(st.limitations || []).length) return null;
    const all = [...(st.notes || []), ...(st.limitations || [])];
    return techSection(`Notes and limitations (${all.length})`, false, el("ul", null, all.map((n) => el("li", { text: n }))));
  }
  function contentDetail(m, kind, st, it, url) {
    const slug = m.project.slug, K = CONTENT_KINDS[kind], fields = st.fields || [], file = st.dm;
    const authored = fields.filter((f) => it.value_lines && it.value_lines[f.key]);
    const tp = it.template || {};
    const dkey = `${slug}:${kind}:${it.key}`;
    // Arriving here (from a card's Edit or the list) opens the form at once; Close or Cancel keeps it closed until reopened.
    // The bar and form redraw in place, so toggling keeps the scroll position and focus.
    const editBox = el("div", { class: "stack" });
    const drawEdit = (focus) => {
      if (!it.editable) { fillKids(editBox, stateBox("empty", "Not editable here.", it.blocked_reason || "This block uses commands the form cannot safely rewrite.")); return; }
      if (!CSRF) { fillKids(editBox, noToken()); return; }
      const dr = state.authoring.get(dkey), open = dr ? dr.open !== false : true, pending = dr ? Object.keys(dr.touched).length : 0;
      const btn = el("button", { type: "button", class: "btn", "aria-expanded": open ? "true" : "false", "aria-controls": `auth-form-${safeId(dkey)}`, onclick: () => {
        const d = authDraft(dkey); d.open = !open; drawEdit(true);
      } }, open ? "Close editor" : "Edit");
      fillKids(editBox, el("div", { class: "btn-row edit-bar" }, btn, pending ? badge(`${pending} unsaved change(s)`, "warn") : null),
        open ? contentForm(m, kind, st, it) : null);
      if (focus) btn.focus({ preventScroll: true });
    };
    drawEdit(false);
    // The editor sits right under the heading; reference panels and raw data follow.
    return el("div", { class: "stack" },
      panel(`${txt(it.name || "(unnamed)")}${it.id !== null && it.id !== undefined ? ` (#${it.id})` : ""}`,
        el("p", { class: "panel-note" }, srcRef(slug, file, it.line, true), it.editable ? null : [" ", badge("read-only", "warn")]),
        kind === "sites" && m.sites.some((x) => Number.isInteger(x.id) && String(x.id) === String(it.key))
          ? el("p", { class: "cross-link" }, el("a", { href: route("p", slug, "sites", it.key) }, "Open in Sites")) : null,
        identityNote(it.identity)),
      editBox,
      usedBySection(m, relOf(m, it, { sites: "site", spells: "spell", weapons: "weapon", armors: "armor" }[kind])),
      panel("Authored in this .dm",
        authored.length ? table(["Field", "Value", "Line"], authored.map((f) => [el("strong", { text: f.label }),
          el("code", { text: fmtValue(f, it.values[f.key], st.options, fields) }), srcRef(slug, file, it.value_lines[f.key])]))
          : el("p", { class: "muted", text: "No modelled values are written in this block." }),
        el("p", { class: "panel-note", text: "Unlisted values come from the template or game defaults." })),
      panel("Template defaults",
        tp.source ? el("p", null, "Template: ", el("strong", { text: `${txt(tp.name || "?")} (#${txt(tp.id)})` }), " ", badge(tp.source === "catalog" ? "vanilla catalog" : "project", tp.source === "catalog" ? "info" : "copper"),
          tp.source === "catalog" && REF_CATS.some((x) => x[0] === kind) ? [" ", el("a", { href: route("p", slug, "author", "reference", kind, tp.id) }, "Open in Reference")] : null,
          tp.source === "project" ? [" ", el("a", { href: authRoute(slug, kind, String(tp.id)) }, "Open project template")] : null)
          : el("p", { class: "muted", text: "No template: this block starts from nothing (or selects an existing entry by id)." }),
        tp.catalog_row ? techSection(`Raw catalog row (${Object.keys(tp.catalog_row).length} columns) — not effective in game`, false,
          el("p", { class: "panel-note", text: "Raw catalog columns of the template, for reference." }),
          table(["Catalog column", "Raw value"], Object.entries(tp.catalog_row).map(([k, v]) => [el("code", { text: k }), el("code", { text: txt(v) })]))) : null),
      (it.unmanaged || []).length ? panel(`Not modelled (${it.unmanaged.length})`,
        el("ul", { class: "verbatim" }, it.unmanaged.map((u) => el("li", null, srcRef(slug, file, u.line), " ", el("code", { text: u.raw })))),
        el("p", { class: "panel-note", text: "Listed verbatim. The form never changes or removes these lines; they are kept as written." })) : null,
      techSection("Source", false, el("div", { class: "btn-row" }, el("button", { type: "button", class: "btn btn-small", onclick: () => copy(it.source_text || "", "Source block") }, "Copy block")),
        codeBlock(it.source_text || "", it.first_line || it.line)),
      techSection("JSON", false, el("p", { class: "faint", text: `The URL lists every ${K.one} in the project; Copy JSON copies only this one.` }), jsonActions(url, () => it, `${K.one} JSON`)));
  }
  // Dirty state of a new-entry draft, shared by the list badge and Use as template: filled fields and a chosen template.
  const filledRaw = (v) => (Array.isArray(v) ? v.length > 0 : typeof v === "boolean" ? v : v !== null && v !== undefined && String(v).trim() !== "");
  const draftFilled = (dr) => (dr ? Object.keys(dr.touched || {}).filter((k) => filledRaw(dr.touched[k])) : []);
  const draftDirty = (dr) => !!dr && (draftFilled(dr).length > 0 || !!dr.template);
  function draftBadge(dr) {
    if (!draftDirty(dr)) return null;
    const n = draftFilled(dr).length;
    return badge(n ? `unsaved draft · ${n} field${n === 1 ? "" : "s"}` : "unsaved draft · template chosen", "warn");
  }
  function authDraft(dkey, init) {
    return draftOf(state.authoring, dkey, () => ({ open: false, touched: {}, template: null, tsrc: "catalog", search: { q: "", results: null, searching: false },
      phase: "edit", preview: null, msg: null, showErrors: false, ...(init || {}) }));
  }
  function contentForm(m, kind, st, it) {
    const slug = m.project.slug, K = CONTENT_KINDS[kind], fields = st.fields || [], url = `${apiBase(slug)}/content/${kind}`;
    const edit = !!it, dkey = `${slug}:${kind}:${edit ? it.key : "~new"}`, idp = `af-${safeId(kind)}-${safeId(edit ? it.key : "new")}`;
    const dr = authDraft(dkey, { open: true });
    const holder = el("section", { class: "panel editor creator", id: `auth-form-${safeId(dkey)}`, "aria-labelledby": `${idp}-h` });
    const reload = () => { state.authData.delete(url); dr.msg = null; render(); };
    // Cancel discards the draft; an existing entry's form then stays closed until Edit is pressed again.
    const cancel = () => {
      state.authoring.delete(dkey);
      if (edit) authDraft(dkey).open = false;
      location.hash === authRoute(slug, kind, edit ? it.key : "") ? render() : (location.hash = authRoute(slug, kind, ...(edit ? [it.key] : [])));
    };
    function problems() {
      const { values, errors } = fieldChanges(fields, dr.touched, edit ? it.values : null);
      if (!edit && fields.some((f) => f.key === "name") && !(values.name && String(values.name).trim())) errors.name = errors.name || "Enter a name.";
      if (!edit && K.templateRequired && !dr.template) errors.template = `Choose a vanilla ${K.one} as the template.`;
      return { values, errors };
    }
    function body() {
      const b = { expected_sha256: st.sha256, mode: edit ? "edit" : "new", values: problems().values };
      if (edit) b.target = String(it.key);
      else if (dr.template) b.template = { source: dr.template.source, id: Number(dr.template.id) };
      return b;
    }
    const countBox = statusLine("");
    let reviewBtn;
    function updateCount(key) {
      const { values, errors } = problems(), n = Object.keys(values).length, nErr = Object.keys(errors).length;
      countBox.textContent = dr.showErrors && nErr ? `${nErr} field(s) need fixing` : n ? `${n} change(s) ready to review` : "No changes yet. Nothing is written until you confirm the review.";
      if (reviewBtn) reviewBtn.disabled = !n && !(!edit && dr.template);
      if (key && dr.showErrors) {
        const fid = `${idp}-${safeId(key)}`, box = holder.querySelector(`#${fid}-err`), inp = holder.querySelector(`#${fid}`);
        if (box) box.textContent = errors[key] || "";
        if (inp) inp.setAttribute("aria-invalid", errors[key] ? "true" : "false");
      }
    }
    function templatePicker(errs) {
      const tp = dr.template, s = dr.search;
      const resultsBox = el("div", { class: "donor-results", "aria-live": "polite" });
      const drawResults = () => {
        if (s.searching) { resultsBox.replaceChildren(stateBox("loading", "Searching the catalog...")); return; }
        const r = s.results;
        if (!r) { resultsBox.replaceChildren(); return; }
        if (r.error) { resultsBox.replaceChildren(errorBox(r.error, "catalog search")); return; }
        if (!r.results.length) { resultsBox.replaceChildren(el("p", { class: "muted", text: "No catalog entries match." })); return; }
        fillKids(resultsBox, el("ul", { class: "donor-list", "aria-label": `Catalog ${K.label.toLowerCase()}` }, r.results.map((x) => {
          const on = tp && tp.source === "catalog" && String(tp.id) === String(x.id);
          return el("li", null, el("button", { type: "button", class: "btn btn-small" + (on ? " is-picked" : ""), "aria-pressed": on ? "true" : "false",
            onclick: () => { dr.template = { source: "catalog", id: x.id, name: x.name }; dr.msg = null; dr.preview = null; redraw(`#${idp}-tpl`); } }, `${txt(x.name)} (#${x.id})`));
        })), r.truncated ? el("p", { class: "faint", text: `Showing ${r.results.length} of ${r.total_matches}; refine the search.` }) : null);
      };
      const search = async () => {
        const q = s.q.trim();
        if (!q || q.length > 60) { s.results = { error: { error: { code: "bad_query", message: "Enter 1 to 60 characters." } } }; drawResults(); return; }
        s.searching = true; drawResults();
        try { s.results = await authLoad(`${apiBase(slug)}/reference?cat=${encodeURIComponent(kind)}&q=${encodeURIComponent(q)}`); }
        catch (e) { s.results = { error: e }; }
        s.searching = false; drawResults();
      };
      const parts = [];
      if (K.projectTemplates) {
        const srcSel = el("select", { class: "input", id: `${idp}-tsrc` }, el("option", { value: "catalog", text: "Vanilla catalog entry" }), el("option", { value: "project", text: `A ${K.one} in this project` }));
        srcSel.value = dr.tsrc;
        srcSel.addEventListener("change", () => { dr.tsrc = srcSel.value; redraw(`#${idp}-tsrc`); });
        parts.push(labelled(srcSel.id, "Template source", srcSel));
      }
      if (dr.tsrc === "project" && K.projectTemplates) {
        const pool = (st.items || []).filter((x) => Number.isInteger(x.id));
        const ps = el("select", { class: "input", id: `${idp}-tproj` }, el("option", { value: "", text: "Choose…" }), pool.map((x) => el("option", { value: String(x.id), text: `${txt(x.name)} (#${x.id})` })));
        ps.value = tp && tp.source === "project" ? String(tp.id) : "";
        ps.addEventListener("change", () => { const x = pool.find((y) => String(y.id) === ps.value); dr.template = x ? { source: "project", id: x.id, name: x.name } : null; dr.preview = null; redraw(`#${idp}-tproj`); });
        parts.push(labelled(ps.id, `Project ${K.one}`, ps, pool.length ? null : `No numbered ${K.label.toLowerCase()} in this project yet.`));
      } else {
        const q = el("input", { class: "input", type: "search", id: `${idp}-tq`, value: s.q, maxlength: "60", autocomplete: "off", placeholder: "Name or id" });
        q.addEventListener("input", () => { s.q = q.value; });
        q.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); search(); } });
        parts.push(el("div", { class: "edit-field wide" }, el("label", { for: q.id, text: `Search vanilla ${K.label.toLowerCase()}` }),
          el("div", { class: "edit-control" }, q, el("button", { type: "button", class: "btn btn-small", disabled: !catalogOf(m) || null, onclick: search }, "Search")), resultsBox));
        drawResults();
      }
      return el("fieldset", { class: "edit-group" }, el("legend", { text: K.templateRequired ? "Template (required)" : "Template (optional)" }),
        el("div", { class: "edit-grid creator-grid" }, parts),
        el("div", { id: `${idp}-tpl`, tabindex: "-1", class: tp ? "picked" : "faint" },
          tp ? ["Template: ", el("strong", { text: `${txt(tp.name)} (#${tp.id})` }), " ", badge(tp.source, tp.source === "catalog" ? "info" : "copper"), " ",
            el("button", { type: "button", class: "btn btn-small btn-ghost", onclick: () => { dr.template = null; dr.preview = null; redraw(`#${idp}-tpl`); } }, "Clear template"),
            tp.source === "catalog" ? [" ", el("a", { href: route("p", slug, "author", "reference", kind, tp.id) }, "Details in Reference")] : null]
            : K.templateRequired ? `Required: choose a vanilla ${K.one} to start from.` : `Optional. Without a template the new ${K.one} starts empty.`),
        errs.template ? el("div", { class: "field-err", role: "alert", text: errs.template }) : null,
        el("p", { class: "panel-note", text: "The template's values are not copied into this form; the review shows exactly which lines are written." }));
    }
    function redraw(focusSel) {
      const sErr = serverFieldErr(dr);
      const { errors } = problems();
      const errs = dr.showErrors ? { ...errors } : {};
      if (sErr) errs[sErr.field] = sErr.message;
      const head = el("h3", { id: `${idp}-h`, tabindex: "-1", text: edit ? `Edit ${K.one}: ${txt(it.name || it.key)}` : `New ${K.one}` });
      const busy = dr.msg && dr.msg.kind === "busy" ? stateBox("loading", dr.msg.text) : null;
      const err = dr.msg && dr.msg.kind === "err" ? writeError(dr.msg.err, reload) : null;
      if (dr.phase === "review" && dr.preview) {
        fillKids(holder, head, busy || authReview(dr.preview, fields, st.options, edit ? "Save to .dm" : `Create ${K.one}`,
          () => runWrite(dr, url, body(), false, redraw, (r) => {
            state.authoring.delete(dkey); invalidateAuth(slug);
            // The saved entry opens with its form closed, so the updated values are what the page shows first.
            const savedKey = r.key !== undefined && r.key !== null ? r.key : edit ? it.key : null;
            if (savedKey !== null) authDraft(`${slug}:${kind}:${savedKey}`).open = false;
            const nm = txt(r.name || (edit ? it.name : dr.touched.name) || "");
            afterWrite(slug, authRoute(slug, kind, ...(savedKey !== null ? [savedKey] : [])),
              r.written ? `Saved to the .dm.${r.backup ? ` Backup: ${r.backup}` : ""}` : "Nothing changed.", r, `${edit ? "Saved" : "Created"} ${K.one}${nm ? ` ${nm}` : ""}`);
          }), () => { dr.phase = "edit"; redraw(REVIEW_TRIGGER); }, cancel));
        focusIn(holder, focusSel);
        return;
      }
      const ctx = (f) => ({ dr, idp, cur: edit ? it.values[f.key] : undefined, err: errs[f.key], opts: st.options || {}, fields, edit, slug, file: st.dm,
        line: edit && it.value_lines ? it.value_lines[f.key] : null, changed: updateCount, redraw });
      reviewBtn = el("button", { type: "submit", class: "btn", ...RT }, "Review changes");
      const intro = el("p", { class: "panel-note" }, edit
        ? "Changes this block only. Clearing a field removes its line; other lines stay as written."
        : `Adds a new ${K.one} to the end of the .dm. Only filled fields are written.`);
      const unknownField = sErr && !fields.some((f) => f.key === sErr.field) && sErr.field !== "template";
      fillKids(holder, ...[head, intro, err, busy].filter(Boolean),
        unknownField ? el("p", { class: "field-err", text: `${sErr.field}: ${sErr.message}` }) : null,
        el("form", { class: "edit-form", novalidate: true, onsubmit: (e) => {
          e.preventDefault(); dr.showErrors = true;
          if (Object.keys(problems().errors).length) { redraw("[aria-invalid=true], .field-err:not(:empty)"); return; }
          runWrite(dr, url, body(), true, redraw);
        } },
          edit ? null : templatePicker(errs),
          el("fieldset", { class: "edit-group" }, el("legend", { text: "Values" }), el("div", { class: "edit-grid creator-grid" }, fields.map((f) => authField(f, ctx(f))))),
          el("div", { class: "btn-row edit-actions" }, reviewBtn,
            el("button", { type: "button", class: "btn btn-ghost", onclick: cancel }, "Cancel"), countBox)));
      updateCount();
      focusIn(holder, focusSel);
    }
    escapeReview(holder, () => dr.phase === "review", () => { dr.phase = "edit"; redraw(REVIEW_TRIGGER); });
    redraw(dr.msg && dr.msg.kind === "err" ? "[data-focus=err]" : null);
    return holder;
  }

  // ----- manual-backed command editor (items, mercenaries, events and the advanced contexts) -----
  // GET /commands?context= lists the manual's commands for one context plus this .dm's blocks of that context. Changes are
  // typed add/replace/remove operations on block lines, previewed (exact diff) and then saved against the loaded SHA-256.
  // Drafts live in state.authoring, so conflicts, failed checks and re-renders never lose them.
  const CMD_CONTEXTS = [["monster", "Monsters"], ["nation", "Nations"], ["site", "Sites"], ["spell", "Spells"], ["weapon", "Weapons"],
    ["armor", "Armour"], ["item", "Items"], ["merc", "Mercenaries"], ["event", "Events"]];
  const CMD_SUBS = { items: ["item", "Items", "item"], mercs: ["merc", "Mercenaries", "mercenary"], events: ["event", "Events", "event"] };
  const NUM_ARGS = new Set(["int", "monid", "nation", "pathmask", "locmask"]);
  const TEXT_ARGS = new Set(["str", "img", "file", "sitename"]);
  const REF_NOUN = { mon: "monster", monneg: "monster", site: "site", weapon: "weapon", armor: "armour", item: "item", spell: "spell", nation: "nation", nationref: "nation" };
  const cmdSubOf = (ctx) => Object.keys(CMD_SUBS).find((k) => CMD_SUBS[k][0] === ctx);
  const cmdRoute = (slug, ctx, key) => cmdSubOf(ctx) ? authRoute(slug, cmdSubOf(ctx), ...(key ? [key] : []))
    : route("p", slug, "author", "commands", ctx, ...(key ? [key] : []));
  const choiceList = (a) => (a.choices || []).map((c) => (c !== null && typeof c === "object" ? [c.value, txt(c.label ?? c.value)] : [c, txt(c)]));
  // Manual labels are often just "#command"; cmdLabel is null when the label adds nothing to the command name.
  const cmdLabel = (c) => { const l = txt(c.label).trim(); return l && l.replace(/^#/, "").toLowerCase() !== String(c.command).replace(/^#/, "").toLowerCase() ? l : null; };
  const cmdName = (c) => `#${String(c).replace(/^#/, "")}`;
  const argText = (v) => (typeof v === "string" && !/^-?\d+(\.\d+)?$/.test(v) ? `"${v}"` : txt(v));
  function cmdArgHint(a) {
    const range = (a.min !== null && a.min !== undefined) || (a.max !== null && a.max !== undefined) ? ` ${a.min ?? "…"} to ${a.max ?? "…"}` : "";
    if (choiceList(a).length) return "choose a value";
    if (a.type === "int" || a.type === "monid") return `whole number${range}`;
    if (a.type === "float") return `number${range}`;
    if (a.type === "pathmask") return "sum of path masks";
    if (a.type === "locmask") return "sum of location masks";
    if (a.type === "monneg") return `monster number or negative montag${range}`;
    if (a.type === "nation") return `nation number${range}`;
    if (a.type === "img" || a.type === "file") return "file path in the mod folder";
    if (a.type === "sitename") return "site name";
    if (a.type === "str") return "text";
    return REF_NOUN[a.type] ? `${REF_NOUN[a.type]} name or number` : txt(a.type);
  }
  // Description-like text arguments get a textarea and may span lines; every other argument stays on one line.
  const cmdArgMulti = (a, command) => a.type === "str" && /descr|msg|text|message/i.test(`${a.name} ${command || ""}`);
  // Draft text -> { value } typed for the server, { skip } for an empty optional argument, or { err }.
  function cmdArgValue(a, raw, command) {
    const r = String(raw ?? "").trim();
    if (r === "") return a.optional ? { skip: true } : { err: `Enter ${a.name}.` };
    const list = choiceList(a);
    if (list.length) { const c = list.find(([v]) => String(v) === r); return c ? { value: c[0] } : { err: `${a.name}: choose one of the listed values.` }; }
    if (r.includes('"')) return { err: `${a.name}: no double quotes.` };
    if (/[\r\n]/.test(r) && !cmdArgMulti(a, command)) return { err: `${a.name}: no line breaks.` };
    if (NUM_ARGS.has(a.type) || a.type === "float") {
      if (!(a.type === "float" ? /^-?\d+(\.\d+)?$/ : /^-?\d+$/).test(r)) return { err: `${a.name}: ${a.type === "float" ? "a number" : "whole numbers only"}.` };
      const n = Number(r);
      if ((a.min !== null && a.min !== undefined && n < a.min) || (a.max !== null && a.max !== undefined && n > a.max)) return { err: `${a.name}: allowed ${a.min ?? "…"} to ${a.max ?? "…"}.` };
      return { value: n };
    }
    if (TEXT_ARGS.has(a.type)) return { value: r };
    if (/^-?\d+$/.test(r)) return { value: Number(r) };
    if (r.includes("#") || r.includes("--")) return { err: `${a.name}: no # or -- in a name.` };
    return { value: r };
  }
  function cmdArgs(specs, raw, command) {
    const args = [];
    let gap = null;
    for (let j = 0; j < specs.length; j++) {
      const v = cmdArgValue(specs[j], raw[j], command);
      if (v.err) return { err: v.err };
      if (v.skip) { gap = gap || specs[j].name; continue; }
      if (gap) return { err: `${specs[j].name}: fill ${gap} first, or clear this value.` };
      args.push(v.value);
    }
    return { args };
  }
  // Pending ops -> server changes plus per-op errors. Replace/remove ops remember the row text they were made against.
  function cmdDraftChanges(dr, st, block) {
    const byCmd = new Map((st.commands || []).map((c) => [c.command, c]));
    const changes = [], errors = {};
    dr.ops.forEach((o, i) => {
      if (o.op !== "add") {
        const row = block && block.commands.find((r) => r.line === o.line);
        if (!row || row.raw !== o.was) { errors[i] = `Line ${o.line} changed on disk after this change was drafted. Drop it and redo it.`; return; }
      }
      if (o.op === "remove") { changes.push({ op: "remove", line: o.line }); return; }
      const spec = byCmd.get(o.command);
      if (!spec || spec.editable === false) { errors[i] = `${o.command} cannot be written by this editor.`; return; }
      const r = cmdArgs(spec.args || [], o.raw, o.command);
      if (r.err) { errors[i] = r.err; return; }
      changes.push(o.op === "add" ? { op: "add", command: o.command, args: r.args } : { op: "replace", line: o.line, command: o.command, args: r.args });
    });
    return { changes, errors };
  }
  // Typed argument controls. Inputs update the draft in place (no redraw), so focus and typing are never interrupted.
  function cmdArgControls(specs, raw, idp, onInput, command) {
    if (!specs.length) return el("span", { class: "faint", text: "No arguments." });
    return el("div", { class: "trait-args" }, specs.map((a, j) => {
      const id = `${idp}-${j}`, list = choiceList(a);
      let c;
      if (list.length) {
        c = el("select", { class: "input", id }, el("option", { value: "", text: a.optional ? "(none)" : "Choose…" }),
          list.map(([v, l]) => el("option", { value: String(v), text: l === String(v) ? l : `${l} (${v})` })));
      } else if (cmdArgMulti(a, command)) {
        c = el("textarea", { class: "input cmd-text", id, rows: "3" });
      } else {
        const nonneg = NUM_ARGS.has(a.type) && a.min !== null && a.min !== undefined && a.min >= 0;
        c = el("input", { class: "input trait-arg", type: "text", id, autocomplete: "off", inputmode: nonneg ? "numeric" : a.type === "float" ? "decimal" : null });
      }
      c.value = raw[j] ?? "";
      c.addEventListener(list.length ? "change" : "input", () => { raw[j] = c.value; onInput(); });
      return el("label", { class: "trait-arg-wrap", for: id }, el("span", { class: "faint", text: `${a.name}${a.optional ? " (optional)" : ""} · ${cmdArgHint(a)}` }), c);
    }));
  }

  function commandsHub(m, sub, rest) {
    const slug = m.project.slug;
    if (sub === "mercs") return el("div", { class: "stack" },
      el("p", { class: "panel-note" }, "Line editor for ", el("code", { text: "#newmerc" }), " blocks. ",
        el("a", { href: route("p", slug, "mercs") }, "Browse"), " has the readable list and ", el("a", { href: route("p", slug, "mercs", "~new") }, "New company"), "."),
      commandsView(m, "merc", rest[0], "Mercenaries", "mercenary"));
    if (CMD_SUBS[sub]) return commandsView(m, CMD_SUBS[sub][0], rest[0], CMD_SUBS[sub][1], CMD_SUBS[sub][2]);
    const ctx = CMD_CONTEXTS.some((c) => c[0] === rest[0]) ? rest[0] : "item";
    const sel = el("select", { class: "input", id: "cmd-context" }, CMD_CONTEXTS.map(([k, l]) => el("option", { value: k, text: l })));
    sel.value = ctx;
    sel.addEventListener("change", () => { location.hash = cmdRoute(slug, sel.value); });
    const label = CMD_CONTEXTS.find((c) => c[0] === ctx)[1];
    return el("div", { class: "stack" },
      el("div", { class: "nation-bar", role: "group", "aria-label": "Command context" },
        el("label", { for: "cmd-context", text: "Block type" }), sel),
      commandsView(m, ctx, rest[1], label, ctx, true));
  }

  function commandsView(m, ctx, sel, title, one, advanced) {
    const slug = m.project.slug, url = `${apiBase(slug)}/commands?context=${encodeURIComponent(ctx)}`;
    return asyncView(url, `${title.toLowerCase()} commands`, (st) => {
      const blocks = st.blocks || [];
      const selected = sel && sel !== "~new" ? blocks.find((b) => String(b.key) === String(sel)) : null;
      const newDr = state.authoring.get(`${slug}:cmd:${ctx}:~new`);
      const list = el("ul", { class: "auth-list", "aria-label": title }, blocks.map((b) => {
        const dr = state.authoring.get(`${slug}:cmd:${ctx}:${b.key}`);
        return el("li", null, el("a", { class: "auth-item", href: cmdRoute(slug, ctx, b.key), "aria-current": b === selected ? "true" : null },
          el("span", { class: "nm", text: b.name || "(unnamed)" }),
          el("span", { class: "sub" }, `${txt(b.opener)}${b.id !== null && b.id !== undefined ? ` ${b.id}` : ""}`,
            (b.used_by || []).length ? [" ", badge(`used by ${b.used_by.length}`, "info")] : null,
            dr && dr.ops.length ? [" ", badge("unsaved", "warn")] : null)));
      }));
      const left = el("div", { class: "unit-pane auth-pane" },
        CSRF ? el("div", { class: "btn-row" }, el("a", { class: "btn btn-small", href: cmdRoute(slug, ctx, "~new"), "aria-current": sel === "~new" ? "page" : null }, `New ${one}`),
          newDr && newDr.ops.length ? badge("unsaved draft", "warn") : null) : noToken(),
        el("p", { class: "faint", text: `${blocks.length} block${blocks.length === 1 ? "" : "s"}` }),
        blocks.length ? list : stateBox("empty", `No ${title.toLowerCase()} yet.`, CSRF ? `Use New ${one} to add one.` : ""));
      let right;
      if (sel === "~new") right = CSRF ? cmdEditor(m, ctx, st, null, url, one) : noToken();
      else if (sel && !selected) right = stateBox("error", `Block "${sel}" not found.`, "Blocks are keyed by their opener line, which moves when lines above it change. Choose it again from the list.");
      else if (selected) right = cmdBlockDetail(m, ctx, st, selected, url, one);
      else right = stateBox("empty", `Select ${/^[aeiou]/i.test(one) ? "an" : "a"} ${one} block.`);
      // Every view of this editor says what it is: raw manual commands, used where no structured form exists.
      const structured = { monster: "Units", nation: "Nation", site: "Sites", spell: "Spells", weapon: "Weapons", armor: "Armour" }[ctx];
      return el("div", { class: "stack" },
        el("p", { class: "advanced-note" }, advancedTag(), " ", `Line editor for raw ${title.toLowerCase()} commands from the modding manual. `,
          structured ? `For common fields, prefer the structured form in ${structured}. ` : `There is no structured form for existing ${title.toLowerCase()}; `,
          "every change is previewed as an exact diff before it is saved."),
        el("div", { class: "split" }, left, el("div", { class: "auth-detail" }, right)));
    });
  }

  function cmdBlockDetail(m, ctx, st, b, url, one) {
    const slug = m.project.slug;
    return el("div", { class: "stack" },
      panel(`${txt(b.name || "(unnamed)")}${b.id !== null && b.id !== undefined ? ` (#${b.id})` : ""}`,
        el("p", { class: "panel-note" }, el("code", { text: `${txt(b.opener)}${b.id !== null && b.id !== undefined ? ` ${b.id}` : ""}` }), " at ",
          srcRef(slug, st.dm, b.line, true), ` · ${b.commands.length} command line(s)`),
        identityNote(b.identity),
        usedBySection(m, { used_by: b.used_by || [], uses: b.uses || [] }, false)),
      CSRF ? cmdEditor(m, ctx, st, b, url, one) : [noToken(), cmdRowsTable(slug, st, b, null)]);
  }

  // Read-only view of a block's rows; the editor passes `act` to add Change/Remove controls per row.
  function cmdRowsTable(slug, st, b, act) {
    if (!b.commands.length) return el("p", { class: "muted", text: "No command lines after the opener yet." });
    return el("div", { class: "table-wrap" }, el("table", { class: "cmd-rows" },
      el("caption", { text: "Current lines in this block" }),
      el("thead", null, el("tr", null, ["Line", "Command", "Arguments", act ? "Change" : "Status"].map((h) => el("th", { scope: "col", text: h })))),
      el("tbody", null, b.commands.map((r) => {
        const a = act ? act(r) : null;
        return el("tr", { class: a && a.cls || null },
          el("td", null, srcRef(slug, st.dm, r.line)),
          el("td", null, el("code", { text: cmdName(r.command) })),
          el("td", null, a && a.args ? a.args : el("code", { class: "cmd-raw", text: (r.args || []).map(argText).join(" ") })),
          el("td", null, a ? a.ctl : r.editable === false ? badge("read-only", "warn") : null));
      }))));
  }

  function cmdEditor(m, ctx, st, block, url, one) {
    const slug = m.project.slug, dkey = `${slug}:cmd:${ctx}:${block ? block.key : "~new"}`, idp = `cmd-${safeId(dkey)}`;
    const openers = st.openers || [];
    const dr = draftOf(state.authoring, dkey, () => ({ ops: [], opener: { command: (openers[0] || {}).command || "", raw: [] },
      pick: { q: "", command: "", raw: [] }, mode: block ? "edit" : "new", phase: "edit", preview: null, msg: null }));
    const byCmd = new Map((st.commands || []).map((c) => [c.command, c]));
    const usedBy = (block && block.used_by) || [];
    const holder = el("section", { class: "panel editor cmd-editor", "aria-labelledby": `${idp}-h` });
    // A removal preview returns to the remove button; any other review to the review button.
    const backFromReview = () => { const del = dr.mode === "delete"; dr.phase = "edit"; dr.preview = null; dr.mode = block ? "edit" : "new"; redraw(del ? "[data-delete-trigger]" : REVIEW_TRIGGER); };
    escapeReview(holder, () => dr.phase === "review", backFromReview);
    const postUrl = `${apiBase(slug)}/commands`;
    const reload = () => { state.authData.delete(url); dr.msg = null; dr.phase = "edit"; dr.preview = null; render(); };
    const openerSpec = () => openers.find((o) => o.command === dr.opener.command);
    const openerArgs = () => openerSpec() ? cmdArgs(openerSpec().args || [], dr.opener.raw, openerSpec().command) : { err: "Choose how the block opens." };
    const pendingFor = (line) => dr.ops.findIndex((o) => o.op !== "add" && o.line === line);
    function problems() {
      const { changes, errors } = cmdDraftChanges(dr, st, block);
      const list = Object.values(errors);
      if (!block) { const oa = openerArgs(); if (oa.err) list.unshift(`Opener: ${oa.err}`); }
      return { changes, list, errors };
    }
    function body(preview) {
      const b = { expected_sha256: st.sha256, preview, context: ctx, mode: dr.mode, changes: dr.mode === "delete" ? [] : problems().changes };
      if (block) b.target = block.key;
      if (dr.mode === "new") b.opener = { command: dr.opener.command, args: openerArgs().args || [] };
      return b;
    }
    const countBox = statusLine("");
    let reviewBtn = null;
    // Live refresh after typing: error lines, change count and the review button, without rebuilding inputs.
    function refresh() {
      const p = problems();
      dr.ops.forEach((_, i) => { const box = holder.querySelector(`#${idp}-err-${i}`); if (box) box.textContent = p.errors[i] || ""; });
      const ob = holder.querySelector(`#${idp}-opener-err`); if (ob) ob.textContent = block ? "" : (openerArgs().err || "");
      const n = dr.ops.length;
      countBox.textContent = !n && block ? "No changes yet." : p.list.length ? `${p.list.length} problem(s) to fix before review.` : block ? `${n} change(s) ready to review.` : `New ${one} with ${n} command(s) ready to review.`;
      if (reviewBtn) reviewBtn.disabled = !!p.list.length || (block && !n);
    }
    const edited = () => { dr.msg = null; dr.preview = null; refresh(); };
    async function send(preview) {
      const p = problems();
      if (dr.mode !== "delete" && p.list.length) { refresh(); return; }
      await runWrite(dr, postUrl, body(preview), preview, redraw, (r) => {
        const wasDelete = dr.mode === "delete";
        state.authoring.delete(dkey); invalidateAuth(slug);
        afterWrite(slug, wasDelete || !block ? cmdRoute(slug, ctx, r && r.key && !wasDelete ? r.key : null) : cmdRoute(slug, ctx, block.key),
          wasDelete ? "Block removed. Backup kept." : block ? "Saved. Backup kept." : `New ${one} saved. Backup kept.`, r,
          wasDelete ? `Removed ${one} ${txt(block.name || block.key)}` : block ? `Saved ${one} ${txt(block.name || block.key)}` : `Created ${one}`);
      });
    }
    function openerGroup() {
      if (!openers.length) return stateBox("error", "No opener for this context.", "The server listed no block openers, so a new block cannot be started here.");
      const sel = el("select", { class: "input", id: `${idp}-opener` }, openers.map((o) => el("option", { value: o.command, text: cmdName(o.command) })));
      sel.value = dr.opener.command;
      sel.addEventListener("change", () => { dr.opener.command = sel.value; dr.opener.raw = []; redraw(`#${idp}-opener`); });
      const spec = openerSpec();
      return el("fieldset", { class: "edit-group" }, el("legend", { text: "1. How the block opens" }),
        el("div", { class: "edit-field" }, el("label", { for: sel.id, text: "Opener" }), sel),
        spec ? cmdArgControls(spec.args || [], dr.opener.raw, `${idp}-oa`, edited, spec.command) : null,
        el("div", { class: "field-err", id: `${idp}-opener-err`, "aria-live": "polite", text: openerArgs().err || "" }),
        el("p", { class: "panel-note", text: "A new id is usually needed; leave an optional id empty only if the manual allows it (the review shows what is written)." }));
    }
    function rowsGroup() {
      return cmdRowsTable(slug, st, block, (r) => {
        const i = pendingFor(r.line), o = dr.ops[i];
        const spec = byCmd.get(r.command);
        const canChange = r.editable !== false && spec && spec.editable !== false;
        if (o && o.op === "remove") return { cls: "cmd-row-removing", ctl: el("div", { class: "btn-row" }, badge("will be removed", "err"),
          el("button", { type: "button", class: "btn btn-small", id: `${idp}-row-${r.line}`, "aria-label": `Undo removing ${r.command} on line ${r.line}`, onclick: () => { dr.ops.splice(i, 1); redraw(`#${idp}-row-${r.line}`); } }, "Undo")),
          args: [el("code", { class: "cmd-raw", text: (r.args || []).map(argText).join(" ") }), el("div", { class: "field-err", id: `${idp}-err-${i}`, "aria-live": "polite" })] };
        if (o) return { cls: "row-adding", args: [cmdArgControls((spec || {}).args || [], o.raw, `${idp}-r${r.line}`, edited, r.command),
            el("div", { class: "field-err", id: `${idp}-err-${i}`, "aria-live": "polite" })],
          ctl: el("div", { class: "btn-row" }, badge("changing", "warn"), el("button", { type: "button", class: "btn btn-small", id: `${idp}-row-${r.line}`, "aria-label": `Undo changing ${r.command} on line ${r.line}`, onclick: () => { dr.ops.splice(i, 1); redraw(`#${idp}-row-${r.line}`); } }, "Undo")) };
        return { ctl: r.editable === false || !canChange
          ? el("span", { title: "Kept as written: the editor cannot rewrite this line safely." }, badge("read-only", "warn"))
          : el("div", { class: "btn-row" },
            el("button", { type: "button", class: "btn btn-small", id: `${idp}-row-${r.line}`, "aria-label": `Change ${r.command} on line ${r.line}`, onclick: () => {
              dr.ops.push({ op: "replace", line: r.line, was: r.raw, command: r.command, raw: (r.args || []).map((v) => txt(v)) }); redraw(`#${idp}-r${r.line}-0, #${idp}-row-${r.line}`);
            } }, "Change"),
            el("button", { type: "button", class: "btn btn-small btn-ghost", "aria-label": `Remove ${r.command} on line ${r.line}`, onclick: () => {
              dr.ops.push({ op: "remove", line: r.line, was: r.raw }); redraw(`#${idp}-row-${r.line}`);
            } }, "Remove")) };
      });
    }
    function addsGroup() {
      const adds = dr.ops.map((o, i) => [o, i]).filter(([o]) => o.op === "add");
      if (!adds.length) return null;
      return el("div", { class: "table-wrap" }, el("table", { class: "cmd-rows" }, el("caption", { text: block ? "Lines to add at the end of the block" : "Command lines for the new block" }),
        el("thead", null, el("tr", null, ["Command", "Arguments", ""].map((h) => el("th", { scope: "col", text: h })))),
        el("tbody", null, adds.map(([o, i]) => {
          const spec = byCmd.get(o.command) || { args: [] };
          return el("tr", { class: "row-adding" },
            el("td", null, el("code", { text: cmdName(o.command) }), cmdLabel(spec) ? el("div", { class: "faint", text: cmdLabel(spec) }) : null),
            el("td", null, cmdArgControls(spec.args || [], o.raw, `${idp}-a${i}`, edited, o.command), el("div", { class: "field-err", id: `${idp}-err-${i}`, "aria-live": "polite" })),
            el("td", null, el("button", { type: "button", class: "btn btn-small btn-ghost", "aria-label": `Drop ${o.command}`, onclick: () => { dr.ops.splice(i, 1); redraw(`#${idp}-q`); } }, "Drop")));
        }))));
    }
    function picker() {
      const q = el("input", { type: "search", class: "input", id: `${idp}-q`, placeholder: "Command name or manual text", value: dr.pick.q, autocomplete: "off", "aria-controls": `${idp}-res` });
      const res = el("ul", { class: "cmd-results", id: `${idp}-res`, "aria-label": "Matching manual commands" });
      const detail = el("div", { class: "cmd-pick", "aria-live": "polite" });
      const quick = ["name", "msg", "descr"].filter((c) => byCmd.has(c) && byCmd.get(c).editable !== false);
      const choose = (c) => { dr.pick.command = c; dr.pick.raw = []; fill(); const f = detail.querySelector("input, select, textarea, button"); if (f) f.focus(); };
      function drawDetail() {
        const c = byCmd.get(dr.pick.command);
        if (!c) { fillKids(detail, el("p", { class: "faint", text: "Choose a command to see its manual summary and arguments." })); return; }
        const err = el("div", { class: "field-err", "aria-live": "polite" });
        const add = el("button", { type: "button", class: "btn btn-small", disabled: c.editable === false || null, onclick: () => {
          const r = cmdArgs(c.args || [], dr.pick.raw, c.command);
          if (r.err) { err.textContent = r.err; return; }
          dr.ops.push({ op: "add", command: c.command, raw: [...dr.pick.raw] });
          dr.pick = { q: dr.pick.q, command: "", raw: [] }; dr.msg = null; dr.preview = null;
          redraw(`#${idp}-q`);
        } }, `Add ${cmdName(c.command)}`);
        fillKids(detail,
          el("h5", null, el("code", { text: cmdName(c.command) }), cmdLabel(c) ? ` ${cmdLabel(c)}` : null),
          c.summary ? el("p", { class: "cmd-summary", text: c.summary }) : null,
          c.source ? el("p", { class: "faint", text: `Source: ${typeof c.source === "string" ? c.source : [c.source.document, c.source.version, c.source.page ? `p.${c.source.page}` : null].filter(Boolean).join(" · ")}` }) : null,
          c.editable === false ? el("p", null, badge("read-only", "warn"), el("span", { class: "faint", text: " This command's arguments are not supported by the editor; it is listed for reference only." }))
            : cmdArgControls(c.args || [], dr.pick.raw, `${idp}-p`, () => { err.textContent = ""; }, c.command),
          err, el("div", { class: "btn-row" }, add, el("button", { type: "button", class: "btn btn-small btn-ghost", onclick: () => { dr.pick.command = ""; fill(); q.focus(); } }, "Cancel")));
      }
      function fill() {
        const t = dr.pick.q.trim().toLowerCase().replace(/^#/, "");
        const score = (c) => { const k = c.command.toLowerCase().replace(/^#/, ""); return k === t ? 0 : k.startsWith(t) ? 1 : k.includes(t) ? 2 : txt(c.label).toLowerCase().includes(t) ? 3 : 4; };
        const hits = (st.commands || []).filter((c) => !t || score(c) < 4 || txt(c.summary).toLowerCase().includes(t)).sort((a, b) => score(a) - score(b));
        fillKids(res, hits.slice(0, 30).map((c) => el("li", null, el("button", { type: "button", class: "cmd-hit", "aria-pressed": dr.pick.command === c.command ? "true" : "false", onclick: () => choose(c.command) },
            el("code", { text: cmdName(c.command) }), cmdLabel(c) ? el("span", { class: "nm", text: cmdLabel(c) }) : null, c.editable === false ? badge("read-only", "warn") : null))),
          hits.length > 30 ? el("li", { class: "faint", text: `${hits.length - 30} more; refine the search.` }) : null,
          hits.length ? null : el("li", { class: "faint", text: "No matching command for this context." }));
        drawDetail();
      }
      q.addEventListener("input", () => { dr.pick.q = q.value; fill(); });
      fill();
      return el("fieldset", { class: "edit-group cmd-picker" }, el("legend", { text: block ? "Add a command" : "2. Add commands" }),
        quick.length ? el("div", { class: "btn-row" }, el("span", { class: "faint", text: "Common:" }), quick.map((c) => el("button", { type: "button", class: "btn btn-small", onclick: () => choose(c) }, cmdName(c)))) : null,
        el("label", { for: q.id, class: "faint", text: `Search ${(st.commands || []).length} manual commands` }), q,
        el("div", { class: "cmd-pick-grid" }, res, detail));
    }
    function deleteControl() {
      if (!block) return null;
      return el("div", { class: "cmd-delete" },
        el("button", { type: "button", class: "btn btn-small btn-ghost", disabled: usedBy.length || null, "aria-describedby": `${idp}-del-note`, "data-delete-trigger": "",
          onclick: () => { dr.mode = "delete"; send(true); } }, "Remove entire block…"),
        el("span", { class: "faint", id: `${idp}-del-note`, text: usedBy.length ? `Disabled: used by ${usedBy.length} definition(s) listed above. Remove those references first.`
          : "Shows the exact removal for review first; nothing is deleted until you confirm." }));
    }
    function reviewPanel() {
      const r = dr.preview, del = dr.mode === "delete";
      const chg = (c) => typeof c === "string" ? c : `${txt(c.op)} ${txt(c.command)}${(c.args || []).length ? " " + c.args.map(argText).join(" ") : ""}${c.line ? ` (line ${c.line})` : ""}`;
      return el("div", { class: "stack" },
        el("h4", { tabindex: "-1", "data-focus": "review", text: del ? "Review: remove this block" : "Review before writing" }),
        (r.changes || []).length ? el("ul", { class: "plain-list" }, r.changes.map((c) => el("li", null, el("code", { text: chg(c) })))) : null,
        (r.used_by || []).length ? el("div", { class: "state state-error", role: "alert" }, el("strong", { text: `Still used by ${r.used_by.length} definition(s). The server will refuse this removal.` }),
          el("ul", null, r.used_by.map((u) => el("li", { text: `${txt(u.name || u.key)} (${txt(u.context)}${u.command ? `, ${u.command}` : ""})` })))) : null,
        (r.warnings || []).length ? el("ul", { class: "diag" }, r.warnings.map((w) => el("li", null, badge("check", "warn"), " ", txt(w)))) : null,
        diffView(r.diff || "", "Exact change to the .dm (diff)"),
        el("p", { class: "panel-note", title: `Checked against SHA-256 ${txt(r.before_sha256 || st.sha256)}`, text: "Saved with a backup of the previous .dm. Static checks only: test in game." }),
        el("div", { class: "btn-row" },
          el("button", { type: "button", class: "btn", disabled: (del && (r.used_by || []).length) || null, onclick: () => send(false) }, del ? "Remove block" : block ? "Save changes" : `Create ${one}`),
          el("button", { type: "button", class: "btn btn-ghost", onclick: backFromReview }, "Back to the editor")));
    }
    function redraw(focusSel) {
      const head = el("h3", { id: `${idp}-h` }, block ? `Edit ${txt(block.name || one)}` : `New ${one}`, " ", advancedTag());
      const msg = dr.msg && dr.msg.kind === "err" ? writeError(dr.msg.err, reload) : dr.msg && dr.msg.kind === "busy" ? stateBox("loading", dr.msg.text) : null;
      if (dr.phase === "review" && dr.preview) { fillKids(holder, head, msg, reviewPanel()); focusIn(holder, focusSel); return; }
      // A delete preview that failed returns here; keep the mode while the request is still running.
      if (dr.mode === "delete" && !(dr.msg && dr.msg.kind === "busy")) dr.mode = block ? "edit" : "new";
      reviewBtn = el("button", { type: "button", class: "btn", onclick: () => send(true), ...RT }, block ? "Review changes" : `Review new ${one}`);
      fillKids(holder, head,
        msg,
        block ? rowsGroup() : openerGroup(),
        addsGroup(),
        picker(),
        el("div", { class: "btn-row edit-actions" }, reviewBtn, countBox,
          dr.ops.length ? el("button", { type: "button", class: "btn btn-ghost btn-small", onclick: () => { dr.ops = []; dr.msg = null; redraw(`#${idp}-q`); } }, "Discard draft") : null),
        deleteControl());
      refresh();
      if (dr.msg) countBox.textContent = dr.msg.kind === "busy" ? dr.msg.text : countBox.textContent;
      focusIn(holder, focusSel);
    }
    redraw();
    return holder;
  }

  // ----- heroes (per nation, follows the nation filter) -----
  function heroSprite(m, id) {
    const u = id === null || id === undefined ? null : m.monsters.find((x) => x.id === Number(id));
    const box = el("span", { class: "hero-thumb" });
    if (u && u.sprites && u.sprites.idle) box.append(spriteImg(u.sprites.idle.url, `${txt(u.name)} sprite`, 1, el("span", { class: "faint", text: "no preview" })));
    else box.append(el("span", { class: "faint", text: id === null || id === undefined ? "empty" : "no sprite" }));
    return box;
  }
  function heroesView(m) {
    const slug = m.project.slug, n = selectedNation(m);
    if (!n || !Number.isInteger(n.id)) return stateBox("empty", "Choose a nation for heroes.",
      "Heroes are set per nation. Pick a numbered nation in the Nation selector above (not \"All nations\" or \"Not tied to a nation\").");
    const url = `${apiBase(slug)}/nations/${encodeURIComponent(n.id)}/heroes`;
    return asyncView(url, "heroes", (st) => heroesForm(m, n, st, url));
  }
  function heroesForm(m, n, st, url) {
    const slug = m.project.slug, dkey = `${slug}:heroes:${n.id}`;
    const dr = authDraft(dkey, { touched: { heroes: {}, multiheroes: {} } });
    const mons = (st.options && st.options.monsters) || [];
    const holder = el("section", { class: "panel editor creator", "aria-labelledby": "heroes-h" });
    escapeReview(holder, () => dr.phase === "review", () => { dr.phase = "edit"; redraw(REVIEW_TRIGGER); });
    const reload = () => { state.authData.delete(url); dr.msg = null; render(); };
    const cancel = () => { state.authoring.delete(dkey); render(); };
    const groups = [["heroes", "Heroes (#hero1–#hero10)", 10], ["multiheroes", "Multiheroes (#multihero1–#multihero7)", 7]];
    const current = (g, slot) => (st[g] || []).find((x) => Number(x.slot) === slot) || { slot, monster: null, name: null, line: null };
    function changes() {
      const out = { heroes: {}, multiheroes: {} };
      for (const [g] of groups) for (const [slot, v] of Object.entries(dr.touched[g])) {
        const nv = v === "" ? null : Number(v), cur = current(g, Number(slot)).monster;
        if (!sameVal(nv, cur === undefined ? null : cur)) out[g][slot] = nv;
      }
      return out;
    }
    const nChanges = () => { const c = changes(); return Object.keys(c.heroes).length + Object.keys(c.multiheroes).length; };
    const countBox = statusLine("");
    let reviewBtn;
    const updateCount = () => { const k = nChanges(); countBox.textContent = k ? `${k} slot change(s) ready to review` : "No changes yet."; if (reviewBtn) reviewBtn.disabled = !k; };
    const fieldsSpec = [];
    for (const [g, , max] of groups) for (let s = 1; s <= max; s++) for (const k of [`${g === "heroes" ? "hero" : "multihero"}${s}`, `${g}:${s}`]) fieldsSpec.push({ key: k, label: `${g === "heroes" ? "Hero" : "Multihero"} ${s}`, type: "monster" });
    function slotCard(g, slot) {
      const cur = current(g, slot), id = `hero-${g}-${slot}`;
      const val = slot in dr.touched[g] || String(slot) in dr.touched[g] ? dr.touched[g][slot] : (cur.monster === null || cur.monster === undefined ? "" : String(cur.monster));
      const sErr = serverFieldErr(dr), fieldKey = `${g === "heroes" ? "hero" : "multihero"}${slot}`;
      const err = sErr && (sErr.field === fieldKey || sErr.field === `${g}:${slot}` || sErr.field === `${g}.${slot}` || sErr.field === `${g}[${slot}]`) ? sErr.message : null;
      const opts = mons.map((x) => [String(x.id), `${txt(x.name)} (#${x.id}${x.role ? `, ${x.role}` : ""})`]);
      if (val !== "" && !opts.some((x) => x[0] === val)) opts.unshift([val, `${cur.name ? txt(cur.name) : "monster"} (#${val}, not in the list)`]);
      const sel = el("select", { class: "input", id, "aria-invalid": err ? "true" : null, "aria-describedby": `${id}-err ${id}-cur` },
        el("option", { value: "", text: cur.monster !== null && cur.monster !== undefined ? "Empty (remove the line)" : "Empty" }), opts.map(([v, l]) => el("option", { value: v, text: l })));
      sel.value = val;
      const curStr = cur.monster === null || cur.monster === undefined ? "" : String(cur.monster);
      if (val !== curStr) sel.classList.add("changed");
      const preview = el("div", { class: "hero-preview" }, heroSprite(m, val === "" ? null : val));
      sel.addEventListener("change", () => {
        if (sel.value === curStr) delete dr.touched[g][slot]; else dr.touched[g][slot] = sel.value;
        sel.classList.toggle("changed", sel.value !== curStr);
        dr.msg = null; dr.preview = null;
        preview.replaceChildren(heroSprite(m, sel.value === "" ? null : sel.value));
        updateCount();
      });
      return el("div", { class: "hero-slot" + (cur.monster !== null && cur.monster !== undefined ? " is-set" : "") }, preview,
        el("div", { class: "edit-field" }, el("label", { for: id, text: `${g === "heroes" ? "Hero" : "Multihero"} ${slot}` }), sel,
          el("div", { class: "field-meta", id: `${id}-cur` }, cur.monster !== null && cur.monster !== undefined
            ? ["Now: ", el("strong", { text: `${txt(cur.name || "?")} (#${cur.monster})` }), " ", cur.line ? srcRef(slug, m.provenance.file, cur.line) : null]
            : el("span", { class: "faint", text: "Now: empty" })),
          el("div", { class: "field-err", id: `${id}-err`, "aria-live": "polite", text: err || "" })));
    }
    function redraw(focusSel) {
      const head = el("h3", { id: "heroes-h", tabindex: "-1", text: `Heroes of ${txt(st.nation ? st.nation.name : n.name)} (#${n.id})` });
      const busy = dr.msg && dr.msg.kind === "busy" ? stateBox("loading", dr.msg.text) : null;
      const err = dr.msg && dr.msg.kind === "err" ? writeError(dr.msg.err, reload) : null;
      if (dr.phase === "review" && dr.preview) {
        fillKids(holder, head, busy || authReview(dr.preview, fieldsSpec, { monsters: mons }, "Save to .dm",
          () => runWrite(dr, url, { expected_sha256: st.sha256, ...changes() }, false, redraw, (r) => {
            state.authoring.delete(dkey); invalidateAuth(slug);
            afterWrite(slug, route("p", slug, "author", "heroes"), r.written ? `Saved heroes.${r.backup ? ` Backup: ${r.backup}` : ""}` : "Nothing changed.", r,
              `Saved heroes of ${txt(st.nation ? st.nation.name : n.name)} (#${n.id})`);
          }), () => { dr.phase = "edit"; redraw(REVIEW_TRIGGER); }, cancel));
        focusIn(holder, focusSel);
        return;
      }
      reviewBtn = el("button", { type: "submit", class: "btn", ...RT }, "Review changes");
      fillKids(holder, ...[head, err, busy].filter(Boolean),
        st.nation && st.nation.vanilla ? el("p", { class: "panel-note" }, badge("vanilla nation", "info"), " This project modifies a vanilla nation's hero list.") : null,
        (st.notes || []).length ? el("ul", { class: "panel-note" }, st.notes.map((x) => el("li", { text: x }))) : null,
        mons.length ? null : stateBox("empty", "No project monsters to choose.", "Heroes must be monsters defined in this project. Create units first."),
        el("form", { class: "edit-form", novalidate: true, onsubmit: (e) => { e.preventDefault(); if (nChanges()) runWrite(dr, url, { expected_sha256: st.sha256, ...changes() }, true, redraw); } },
          groups.map(([g, legend, max]) => {
            // Assigned (or edited) slots stay visible; empty ones sit in a closed disclosure that remembers its state.
            const slots = Array.from({ length: max }, (_, i) => i + 1);
            const shown = (k) => { const c = current(g, k).monster; return (c !== null && c !== undefined) || k in dr.touched[g] || String(k) in dr.touched[g]; };
            const used = slots.filter(shown), empty = slots.filter((k) => !shown(k));
            dr.emptyOpen = dr.emptyOpen || {};
            const more = empty.length ? el("details", { class: "raw tech", open: dr.emptyOpen[g] || null },
              el("summary", null, `${used.length ? "Empty slots" : "All slots empty"} (${empty.length})`),
              el("div", { class: "inner" }, el("div", { class: "hero-grid" }, empty.map((k) => slotCard(g, k))))) : null;
            if (more) more.addEventListener("toggle", () => { dr.emptyOpen[g] = more.open; });
            return el("fieldset", { class: "edit-group" }, el("legend", { text: `${legend}: ${used.length} assigned` }),
              used.length ? el("div", { class: "hero-grid" }, used.map((k) => slotCard(g, k))) : null, more);
          }),
          el("div", { class: "btn-row edit-actions" }, reviewBtn, el("button", { type: "button", class: "btn btn-ghost", onclick: cancel }, "Cancel"), countBox)));
      updateCount();
      focusIn(holder, focusSel);
    }
    redraw(dr.msg && dr.msg.kind === "err" ? "[data-focus=err]" : null);
    return el("div", { class: "stack" }, holder,
      techSection("JSON", false, jsonActions(url, () => st, "Heroes JSON")));
  }

  // ----- reference (vanilla catalog lookup) -----
  function referenceView(m, cat, id) {
    const slug = m.project.slug;
    const rs = draftOf(state.refs, slug, () => ({ cat: "spells", q: "", results: null, searching: false }));
    if (cat && REF_CATS.some((x) => x[0] === cat)) rs.cat = cat;
    const resultsBox = el("div", { "aria-live": "polite" });
    const drawResults = () => {
      if (rs.searching) { resultsBox.replaceChildren(stateBox("loading", "Searching...")); return; }
      const r = rs.results;
      if (!r) { resultsBox.replaceChildren(el("p", { class: "faint", text: "Search by name or id." })); return; }
      if (r.error) { resultsBox.replaceChildren(errorBox(r.error, "reference results")); return; }
      if (!r.results.length) { resultsBox.replaceChildren(el("p", { class: "muted", text: `No ${r.category || rs.cat} match "${txt(r.query)}".` })); return; }
      resultsBox.replaceChildren(el("p", { class: "faint", text: `${r.results.length}${r.truncated ? ` of ${r.total_matches}` : ""} result(s)${r.truncated ? "; refine the search" : ""}.` }),
        el("ul", { class: "auth-list ref-results", "aria-label": "Reference results" }, r.results.map((x) => el("li", null,
          el("a", { class: "auth-item", href: route("p", slug, "author", "reference", r.category || rs.cat, x.id), "aria-current": String(x.id) === String(id) && (r.category || rs.cat) === cat ? "true" : null },
            el("span", { class: "nm", text: txt(x.name) }), el("span", { class: "sub", text: `#${x.id}` }))))));
    };
    const catSel = el("select", { class: "input", id: "ref-cat" }, REF_CATS.map(([v, l]) => el("option", { value: v, text: l })));
    catSel.value = rs.cat;
    catSel.addEventListener("change", () => { rs.cat = catSel.value; rs.results = null; drawResults(); });
    const q = el("input", { class: "input", type: "search", id: "ref-q", value: rs.q, maxlength: "60", autocomplete: "off", placeholder: "Name or id" });
    q.addEventListener("input", () => { rs.q = q.value; });
    const search = async () => {
      const t = rs.q.trim();
      if (!t || t.length > 60) { rs.results = { error: { error: { code: "bad_query", message: "Enter 1 to 60 characters." } } }; drawResults(); q.focus(); return; }
      rs.searching = true; drawResults();
      try { rs.results = await authLoad(`${apiBase(slug)}/reference?cat=${encodeURIComponent(rs.cat)}&q=${encodeURIComponent(t)}`); }
      catch (e) { rs.results = { error: e }; }
      rs.searching = false; drawResults();
    };
    const form = el("form", { class: "unit-filter ref-form", role: "search", onsubmit: (e) => { e.preventDefault(); search(); } },
      el("label", { for: "ref-cat", class: "sr-only", text: "Category" }), catSel,
      el("label", { for: "ref-q", class: "sr-only", text: "Search the catalog" }), q,
      el("button", { type: "submit", class: "btn btn-small" }, "Search"));
    drawResults();
    const left = el("div", { class: "unit-pane auth-pane" },
      el("p", { class: "faint" }, "Vanilla data, read-only. Quick lookup by name or id; the ",
        el("a", { href: inspHref(slug, rs.cat) }, "Vanilla catalog"), " has filters and every category."), form, resultsBox);
    const right = cat && id ? asyncView(`${apiBase(slug)}/reference/${encodeURIComponent(cat)}/${encodeURIComponent(id)}`, "the reference entry", (d) => referenceDetail(m, cat, d))
      : stateBox("empty", "Choose an entry.", "Search, then open a result.");
    return el("div", { class: "split" }, left, el("div", { class: "auth-detail" }, right));
  }
  // Shared by Reference and the Vanilla catalog: start a new project spell, site, weapon or armour from a catalog entry.
  // An existing new-entry draft with filled fields or another template is never replaced silently: the user chooses to
  // keep it, swap only the template (keeping the filled fields) or start clean.
  function useAsTemplate(m, cat, d, cls) {
    const slug = m.project.slug, K = CONTENT_KINDS[cat];
    if (!K || !CSRF || d.id === null || d.id === undefined) return null;
    const dkey = `${slug}:${cat}:~new`, label = `${txt(d.name)} (#${d.id})`, pid = `tpl-decide-${safeId(cat)}-${safeId(d.id)}`;
    const box = el("div", { class: "tpl-use" });
    const open = () => { location.hash = authRoute(slug, cat, "~new"); };
    // Deliberate replacement: the new template, and no stale errors, review or server message from the old draft.
    const apply = (keepFields) => {
      const old = state.authoring.get(dkey);
      if (!keepFields) state.authoring.delete(dkey);
      const dr = keepFields && old ? old : authDraft(dkey, { open: true });
      Object.assign(dr, { template: { source: "catalog", id: d.id, name: d.name }, tsrc: "catalog", preview: null, phase: "edit", msg: null, showErrors: false, open: true });
      open();
    };
    const btn = el("button", { type: "button", class: cls || "btn", "aria-expanded": "false", "aria-controls": pid, onclick: () => decide() }, `Use as template for a new ${K.one}`);
    const close = () => { fillKids(box, btn); btn.setAttribute("aria-expanded", "false"); btn.focus(); };
    async function decide() {
      const dr = state.authoring.get(dkey), tp = dr && dr.template;
      const same = !!tp && tp.source === "catalog" && String(tp.id) === String(d.id), filled = draftFilled(dr);
      if (!draftDirty(dr)) { apply(false); return; }
      if (same && !filled.length) { open(); return; }
      let names = filled;
      try { const fs = specOf((await authLoad(`${apiBase(slug)}/content/${cat}`)).fields); names = filled.map((k) => (fs.find((f) => f.key === k) || { label: k }).label); }
      catch (_) { /* keys are shown as written */ }
      const cur = tp ? `${txt(tp.name || "?")} (#${txt(tp.id)}${tp.source === "project" ? ", a project entry" : ""})` : "no template";
      const n = filled.length, nf = `${n} filled field${n === 1 ? "" : "s"}`;
      const panelBox = el("div", { class: "state tpl-decide", id: pid, role: "group", "aria-labelledby": `${pid}-h` },
        el("div", null,
          el("p", { id: `${pid}-h`, tabindex: "-1" }, el("strong", { text: `You already have an unsaved new ${K.one} draft. ` }),
            `It uses ${cur}${n ? ` and has ${nf}: ${names.join(", ")}.` : "."}`),
          el("p", { class: "faint", text: same
            ? `It already uses ${label}. Keep draft opens it unchanged; starting clean discards your ${nf}.`
            : n ? `Replace template keeps your ${nf}; they override ${label}'s values, and everything you did not fill comes from ${label}. Start clean discards the draft.`
              : `Replace template swaps ${cur} for ${label}. Keep draft opens it unchanged.` }),
          el("div", { class: "btn-row" },
            el("button", { type: "button", class: "btn btn-small", onclick: open }, "Keep draft"),
            same ? null : el("button", { type: "button", class: "btn btn-small", onclick: () => apply(true) }, n ? `Replace template, keep ${nf}` : "Replace template"),
            n ? el("button", { type: "button", class: "btn btn-small btn-ghost", onclick: () => apply(false) }, `Start clean from ${label}`) : null,
            el("button", { type: "button", class: "btn btn-small btn-ghost", onclick: close }, "Cancel"))));
      panelBox.addEventListener("keydown", (e) => { if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(); } });
      fillKids(box, btn, panelBox);
      btn.setAttribute("aria-expanded", "true");
      panelBox.querySelector(`#${pid}-h`).focus();
    }
    box.append(btn);
    return box;
  }
  function referenceDetail(m, cat, d) {
    const slug = m.project.slug;
    const effects = Array.isArray(d.effects) ? d.effects : [];
    const effCols = [...new Set(effects.flatMap((x) => Object.keys(x || {})))];
    const useBtn = el("div", { class: "btn-row" }, useAsTemplate(m, cat, d),
      el("a", { class: "btn btn-small btn-ghost", href: inspHref(slug, cat, d.id) }, "Open in Vanilla catalog"));
    const url = `${apiBase(slug)}/reference/${encodeURIComponent(cat)}/${encodeURIComponent(d.id)}`;
    return el("div", { class: "stack" },
      panel(`${txt(d.name)} (#${txt(d.id)})`, el("p", { class: "panel-note", text: `Vanilla ${txt(d.category || cat)}` }),
        useBtn,
        (d.labelled || []).length ? table(["Field", "Value", "Note"], d.labelled.map((x) => [el("strong", { text: txt(x.label) }), el("code", { text: txt(x.value) }), el("span", { class: "faint", text: txt(x.note) })]))
          : el("p", { class: "muted", text: "No labelled values." }),
        d.summon ? el("p", null, "Summons: ", el("strong", { text: `${txt(d.summon.monster_name || "?")} (#${txt(d.summon.monster_id)})` })) : null,
        d.note ? el("p", { class: "panel-note", text: d.note }) : null),
      effects.length ? panel("Effect records (raw)", table(effCols, effects.map((x) => effCols.map((k) => el("code", { text: x[k] === undefined ? "" : typeof x[k] === "object" ? JSON.stringify(x[k]) : txt(x[k]) }))))) : null,
      techSection("Catalog row (raw columns)", false, d.catalog_row ? table(["Catalog column", "Raw value"], Object.entries(d.catalog_row).map(([k, v]) => [el("code", { text: k }), el("code", { text: txt(v) })])) : el("p", { class: "muted", text: "No raw row." })),
      d.catalog ? techSection("Catalog provenance", false, el("dl", { class: "kv" }, Object.entries(d.catalog).map(([k, v]) => [el("dt", { text: k }), el("dd", { class: "mono", text: v && typeof v === "object" ? JSON.stringify(v) : txt(v) })]))) : null,
      techSection("JSON", false, jsonActions(url, () => d, "Reference JSON")));
  }

  // ----- playtests (observations tied to a .dm SHA-256; no balance claims) -----
  const PLAYTEST_FIELDS = [
    { key: "game_version", label: "Game version", type: "text" }, { key: "nation", label: "Nation played", type: "text" },
    { key: "opponents", label: "Opponents", type: "text" }, { key: "map", label: "Map", type: "text" }, { key: "turns", label: "Turns played", type: "int", min: 0, max: 1000 },
    { key: "result_summary", label: "Result summary", type: "text" }, { key: "observations", label: "Observations", type: "text" }, { key: "tester", label: "Tester", type: "text" }];
  const EVIDENCE_KINDS = ["screenshot", "save", "log", "note"];
  function playtestsView(m) {
    const slug = m.project.slug, url = `${apiBase(slug)}/playtests`;
    return asyncView(url, "playtest records", (st) => {
      const spec = specOf(st.fields && st.fields.length ? st.fields : PLAYTEST_FIELDS);
      const fields = spec.filter((f) => f.key !== "evidence" && f.type !== "evidence");
      const evSpec = spec.find((f) => f.key === "evidence") || {};
      const recs = st.records || [];
      const kv = (r) => el("dl", { class: "kv" }, fields.map((f) => [el("dt", { text: f.label }), el("dd", { text: r[f.key] === null || r[f.key] === undefined || r[f.key] === "" ? "—" : fmtValue(f, r[f.key]) })]),
        el("dt", { text: "Evidence" }), el("dd", null, (r.evidence || []).length ? el("ul", { class: "plain-list" }, r.evidence.map((x) => el("li", null, badge(x.kind, ""), " ", el("span", { text: txt(x.reference) }), x.sha256 ? el("span", { class: "hash", text: ` sha256 ${x.sha256}` }) : null))) : "none"));
      return [
        panel(null,
          el("p", { class: "panel-note", text: "Observations from real games, tied to the .dm revision played. Not verified; no balance claims." }),
          techSection("Technical details", false, el("p", { class: "panel-note" }, "Current .dm SHA-256: ", el("span", { class: "hash", text: txt(st.current_sha256) })),
            st.note ? el("p", { class: "panel-note", text: st.note }) : null)),
        recs.length ? el("div", { class: "stack" }, recs.map((r) => el("article", { class: "panel playtest", "aria-label": `Playtest ${txt(r.created_utc)}` },
          el("h3", { text: `${txt(r.created_utc || "undated")} — ${txt(r.result_summary || "no summary")}` }),
          el("p", { class: "panel-note" }, r.matches_current ? "Current revision" : badge("older revision", "warn"), " · .dm ", el("span", { class: "hash", text: shortSha(r.dm_sha256), title: txt(r.dm_sha256) }),
            r.matches_current ? null : el("span", { class: "faint", text: " — the .dm has changed since this record; its observations may not apply." })),
          kv(r))))
          : stateBox("empty", "No playtest records yet.", "Add one below after playing this revision in Dominions 6."),
        CSRF ? playtestForm(m, st, fields, url, evSpec) : noToken(),
        techSection("JSON", false, jsonActions(url, () => st, "Playtests JSON"))];
    });
  }
  function playtestForm(m, st, fields, url, evSpec) {
    const evKinds = Array.isArray(evSpec.kinds) && evSpec.kinds.length ? evSpec.kinds : EVIDENCE_KINDS, evMax = evSpec.max_items || 20;
    const slug = m.project.slug, dkey = `${slug}:playtest`;
    const dr = authDraft(dkey, { touched: {}, evidence: [] });
    const holder = el("section", { class: "panel editor creator", "aria-labelledby": "pt-h" });
    escapeReview(holder, () => dr.phase === "review", () => { dr.phase = "edit"; redraw(REVIEW_TRIGGER); });
    const reload = () => { state.authData.delete(url); dr.msg = null; render(); };
    const cancel = () => { state.authoring.delete(dkey); render(); };
    function problems() {
      const { values, errors } = fieldChanges(fields, dr.touched, null);
      if (!values.result_summary && fields.some((f) => f.key === "result_summary")) errors.result_summary = errors.result_summary || "Describe the result in a sentence.";
      dr.evidence.forEach((x, i) => {
        if (!String(x.reference).trim()) errors[`evidence.${i}`] = "Enter a reference (file name, link or note), or remove this row.";
        else if (x.sha256.trim() && !/^[0-9a-fA-F]{64}$/.test(x.sha256.trim())) errors[`evidence.${i}`] = "SHA-256 must be 64 hex characters, or blank.";
      });
      return { values, errors };
    }
    function record() {
      const rec = {};
      for (const f of fields) { const n = normOf(f, f.key in dr.touched ? dr.touched[f.key] : rawOf(f, null)); rec[f.key] = n.error ? null : n.value; }
      rec.evidence = dr.evidence.map((x) => { const e = { kind: x.kind, reference: x.reference.trim() }; if (x.sha256.trim()) e.sha256 = x.sha256.trim().toLowerCase(); return e; });
      return rec;
    }
    function redraw(focusSel) {
      const sErr = serverFieldErr(dr);
      const errs = dr.showErrors ? { ...problems().errors } : {};
      if (sErr) { const k = sErr.field.replace(/^record\./, "").replace(/\[(\d+)\]/, ".$1").replace(/^(evidence\.\d+).*$/, "$1"); errs[k] = sErr.message; }
      const head = el("h3", { id: "pt-h", tabindex: "-1", text: "Add a playtest record" });
      const busy = dr.msg && dr.msg.kind === "busy" ? stateBox("loading", dr.msg.text) : null;
      const err = dr.msg && dr.msg.kind === "err" ? writeError(dr.msg.err, reload) : null;
      if (dr.phase === "review" && dr.preview) {
        const r = dr.preview, rec = r.record || record();
        fillKids(holder, head, busy || el("div", { class: "stack" },
          el("h4", { tabindex: "-1", "data-focus": "review", text: "Review before saving" }),
          el("p", null, "This record will be stored against .dm SHA-256 ", el("span", { class: "hash", text: txt(rec.dm_sha256 || st.current_sha256) }), "."),
          el("dl", { class: "kv" }, fields.map((f) => [el("dt", { text: f.label }), el("dd", { text: rec[f.key] === null || rec[f.key] === undefined || rec[f.key] === "" ? "—" : fmtValue(f, rec[f.key]) })]),
            el("dt", { text: "Evidence" }), el("dd", { text: (rec.evidence || []).length ? rec.evidence.map((x) => `${x.kind}: ${x.reference}`).join("; ") : "none" })),
          r.note ? el("p", { class: "panel-note", text: r.note }) : null,
          el("p", { class: "panel-note", text: "Saving records an observation only. It changes nothing in the .dm and makes no balance claim." }),
          el("div", { class: "btn-row" },
            el("button", { type: "button", class: "btn", onclick: () => runWrite(dr, url, { expected_sha256: st.current_sha256, record: record() }, false, redraw, (res) => {
              state.authoring.delete(dkey); invalidateAuth(slug);
              afterWrite(slug, route("p", slug, "author", "playtests"), res.written ? "Playtest record saved." : "Nothing saved.", res, "Saved playtest record");
            }) }, "Save record"),
            el("button", { type: "button", class: "btn btn-ghost", onclick: () => { dr.phase = "edit"; redraw(REVIEW_TRIGGER); } }, "Back to the form"),
            el("button", { type: "button", class: "btn btn-ghost", onclick: cancel }, "Cancel (discard)"))));
        focusIn(holder, focusSel);
        return;
      }
      const ctx = (f) => ({ dr, idp: "pt", cur: undefined, err: errs[f.key], opts: st.options || {}, fields, edit: false, slug, file: null, line: null,
        changed: () => { dr.preview = null; }, redraw });
      const evRows = dr.evidence.map((x, i) => {
        const kind = el("select", { class: "input", id: `pt-ev-k${i}`, "aria-label": `Evidence ${i + 1}: kind` }, evKinds.map((k) => el("option", { value: k, text: k })));
        kind.value = x.kind;
        kind.addEventListener("change", () => { x.kind = kind.value; dr.preview = null; });
        const ref = el("input", { class: "input", id: `pt-ev-r${i}`, value: x.reference, autocomplete: "off", "aria-label": `Evidence ${i + 1}: reference`, "aria-invalid": errs[`evidence.${i}`] ? "true" : null, "aria-describedby": `pt-ev-e${i}` });
        ref.addEventListener("input", () => { x.reference = ref.value; dr.preview = null; });
        const sha = el("input", { class: "input mono", id: `pt-ev-s${i}`, value: x.sha256, autocomplete: "off", maxlength: "64", placeholder: "SHA-256 (optional)", "aria-label": `Evidence ${i + 1}: SHA-256 (optional)`, "aria-describedby": `pt-ev-e${i}` });
        sha.addEventListener("input", () => { x.sha256 = sha.value; dr.preview = null; });
        return el("li", { class: "evidence-row" }, kind, ref, sha,
          el("button", { type: "button", class: "btn btn-small btn-ghost", "aria-label": `Remove evidence ${i + 1}`, onclick: () => { dr.evidence.splice(i, 1); redraw("#pt-ev-add"); } }, "Remove"),
          el("div", { class: "field-err", id: `pt-ev-e${i}`, "aria-live": "polite", text: errs[`evidence.${i}`] || "" }));
      });
      fillKids(holder, ...[head, err, busy].filter(Boolean),
        el("p", { class: "panel-note", text: "Record what you observed in a real game of this revision." }),
        el("form", { class: "edit-form", novalidate: true, onsubmit: (e) => {
          e.preventDefault(); dr.showErrors = true;
          if (Object.keys(problems().errors).length) { redraw("[aria-invalid=true], .field-err:not(:empty)"); return; }
          runWrite(dr, url, { expected_sha256: st.current_sha256, record: record() }, true, redraw);
        } },
          el("fieldset", { class: "edit-group" }, el("legend", { text: "Record" }), el("div", { class: "edit-grid creator-grid" }, fields.map((f) => authField(f, ctx(f))))),
          el("fieldset", { class: "edit-group" }, el("legend", { text: "Evidence (optional)" }),
            evRows.length ? el("ul", { class: "plain-list" }, evRows) : el("p", { class: "faint", text: "No evidence listed." }),
            el("button", { type: "button", class: "btn btn-small", id: "pt-ev-add", disabled: dr.evidence.length >= evMax || null, onclick: () => { dr.evidence.push({ kind: evKinds[0], reference: "", sha256: "" }); redraw(`#pt-ev-r${dr.evidence.length - 1}`); } }, "Add evidence"),
            errs.evidence ? el("div", { class: "field-err", role: "alert", text: errs.evidence }) : null,
            el("p", { class: "panel-note", text: "References are text only (a file name, path or note); files are not uploaded." })),
          el("div", { class: "btn-row edit-actions" }, el("button", { type: "submit", class: "btn", ...RT }, "Review"),
            el("button", { type: "button", class: "btn btn-ghost", onclick: cancel }, "Cancel"), statusLine("Nothing is saved until you confirm the review."))));
      focusIn(holder, focusSel);
    }
    redraw(dr.msg && dr.msg.kind === "err" ? "[data-focus=err]" : null);
    return holder;
  }

  // ---------- workspace: import a .dm ----------
  const readFile = (file) => new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result); r.onerror = () => reject(r.error || new Error("read failed"));
    r.readAsArrayBuffer(file);
  });
  function importProblems(dr) {
    const f = dr.form, o = {};
    if (!f.slug.trim()) o.slug = "Enter a folder name for the new project.";
    else if (!/^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/.test(f.slug.trim())) o.slug = "Letters, digits, dot, dash or underscore; up to 64 characters.";
    if (!dr.dm) o.dm = "Choose one .dm file.";
    else if (!/\.dm$/i.test(dr.dm.filename)) o.dm = "The mod file must end in .dm.";
    dr.assets.forEach((a, i) => {
      const p = a.path.trim();
      if (!p) o[`asset.${i}`] = "Enter the path relative to the mod folder.";
      else if (/^([A-Za-z]:|[\\/])/.test(p) || p.split(/[\\/]/).includes("..")) o[`asset.${i}`] = "Relative paths only, without .. or a drive.";
      else if (dr.assets.some((b, j) => j < i && b.path.trim() === p)) o[`asset.${i}`] = "Duplicate path.";
    });
    if (importTotal(dr) > MAX_IMPORT_BYTES) o.size = `Selected files total ${fmtBytes(importTotal(dr))}; the limit is ${fmtBytes(MAX_IMPORT_BYTES)}.`;
    return o;
  }
  const importTotal = (dr) => (dr.dm ? dr.dm.size : 0) + dr.assets.reduce((s, a) => s + a.size, 0);
  function viewImport() {
    const dr = state.importDraft || (state.importDraft = { form: { slug: "", name: "" }, dm: null, assets: [], phase: "edit", preview: null, msg: null, showErrors: false, done: null, reading: 0 });
    const holder = el("section", { class: "panel editor creator", "aria-labelledby": "imp-h" });
    escapeReview(holder, () => dr.phase === "review", () => { dr.phase = "edit"; redraw(REVIEW_TRIGGER); });
    const url = "/api/import";
    const body = () => ({ slug: dr.form.slug.trim(), name: dr.form.name.trim() || null, dm: { filename: dr.dm.filename, base64: dr.dm.b64 },
      assets: dr.assets.map((a) => ({ path: a.path.trim().replace(/\\/g, "/"), base64: a.b64 })) });
    const touch = () => { dr.msg = null; dr.preview = null; };
    async function addFiles(files, isDm) {
      dr.reading++; redraw();
      try {
        for (const file of files) {
          const b64 = toBase64(await readFile(file));
          if (isDm) dr.dm = { filename: file.name, size: file.size, b64 };
          else dr.assets.push({ id: `${Date.now()}-${Math.random().toString(36).slice(2)}`, file: file.name, path: (file.webkitRelativePath || file.name).replace(/\\/g, "/"), size: file.size, b64 });
        }
      } catch (e) { dr.msg = { kind: "err", err: { error: { code: "read_failed", message: `Could not read a file: ${String((e && e.message) || e)}` } } }; }
      dr.reading--; touch(); redraw(isDm ? "#imp-dm" : "#imp-assets");
    }
    function redraw(focusSel) {
      const sErr = serverFieldErr(dr);
      const errs = dr.showErrors ? importProblems(dr) : {};
      if (sErr) errs[/^assets?/.test(sErr.field) ? "assets" : sErr.field.replace(/\..*$/, "")] = sErr.message;
      const head = el("h2", { id: "imp-h", tabindex: "-1", text: "New project from a .dm" });
      const busy = dr.reading ? stateBox("loading", "Reading files...") : dr.msg && dr.msg.kind === "busy" ? stateBox("loading", dr.msg.text) : null;
      const er = dr.msg && dr.msg.kind === "err" ? dr.msg.err : null;
      const err = !er ? null : er.error && er.error.code === "project_exists"
        ? el("div", { class: "state state-error", role: "alert", tabindex: "-1", "data-focus": "err" }, el("strong", { text: "A project with that folder name already exists. Nothing was written." }),
          el("div", { text: txt(er.error.message) }), el("p", null, "Choose a different project folder name; imports never overwrite."))
        : writeError(er, () => { dr.msg = null; redraw(); });
      if (dr.done) {
        const r = dr.done, slug = typeof r.project === "string" ? r.project : (r.project && r.project.slug) || dr.form.slug.trim();
        fillKids(holder, head, el("div", { class: "state", role: "status", tabindex: "-1", "data-focus": "done" },
          el("strong", { text: "Imported." }), el("p", null, "Project folder created with ", el("code", { text: txt(r.dm_path) }), "."),
          r.note ? el("p", { class: "panel-note", text: r.note }) : null,
          el("div", { class: "btn-row" }, el("a", { class: "btn", href: hashPath("p", slug) }, "Open the project"),
            el("button", { type: "button", class: "btn btn-ghost", onclick: () => { state.importDraft = null; render(); } }, "Import another"))));
        focusIn(holder, focusSel);
        return;
      }
      if (dr.phase === "review" && dr.preview) {
        const r = dr.preview;
        fillKids(holder, head, busy || el("div", { class: "stack" },
          el("h4", { tabindex: "-1", "data-focus": "review", text: "Review before importing" }),
          el("dl", { class: "kv" }, el("dt", { text: "Project" }), el("dd", { class: "mono", text: typeof r.project === "string" ? r.project : JSON.stringify(r.project) })),
          techSection("Technical details", false, el("dl", { class: "kv" },
            el("dt", { text: ".dm" }), el("dd", { class: "mono", text: txt(r.dm_path) }), el("dt", { text: "SHA-256" }), el("dd", { class: "hash", text: txt(r.sha256) }),
            el("dt", { text: "Encoding" }), el("dd", { text: txt(r.encoding) }), el("dt", { text: "Newlines" }), el("dd", { text: txt(r.newlines) }))),
          (r.assets || []).length ? table(["Asset", "Bytes", "SHA-256", "Referenced by the .dm"], r.assets.map((a) => [el("code", { text: a.path }), txt(a.bytes), el("span", { class: "hash", text: shortSha(a.sha256), title: txt(a.sha256) }),
            a.referenced ? "yes" : badge("not referenced", "warn")])) : el("p", { class: "muted", text: "No asset files." }),
          (r.missing_assets || []).length ? el("div", null, el("h4", { text: "Referenced by the .dm but not provided" }), el("ul", null, r.missing_assets.map((p) => el("li", null, el("code", { text: p }))))) : null,
          (r.warnings || []).length ? el("ul", { class: "diag" }, r.warnings.map((w) => el("li", null, badge("check", "warn"), " ", el("span", { text: w })))) : null,
          r.note ? el("p", { class: "panel-note", text: r.note }) : null,
          el("p", { class: "panel-note", text: "Creates a new project folder; existing projects are never overwritten." }),
          el("div", { class: "btn-row" },
            el("button", { type: "button", class: "btn", onclick: () => runWrite(dr, url, body(), false, redraw, (res) => { dr.done = res; dr.phase = "edit"; loadProjects(true); redraw("[data-focus=done]"); toast("Imported"); }) }, "Import"),
            el("button", { type: "button", class: "btn btn-ghost", onclick: () => { dr.phase = "edit"; redraw(REVIEW_TRIGGER); } }, "Back to the form"))));
        focusIn(holder, focusSel);
        return;
      }
      const inp = (k, label, hint) => {
        const i = el("input", { class: "input", id: `imp-${k}`, value: dr.form[k], autocomplete: "off", "aria-invalid": errs[k] ? "true" : null, "aria-describedby": `imp-${k}-hint imp-${k}-err` });
        i.addEventListener("input", () => { dr.form[k] = i.value; touch(); });
        return el("div", { class: "edit-field" }, el("label", { for: i.id, text: label }), i, el("div", { class: "field-meta faint", id: `imp-${k}-hint`, text: hint }),
          el("div", { class: "field-err", id: `imp-${k}-err`, "aria-live": "polite", text: errs[k] || "" }));
      };
      const dmIn = el("input", { type: "file", id: "imp-dm", accept: ".dm", "aria-invalid": errs.dm ? "true" : null, "aria-describedby": "imp-dm-hint imp-dm-err" });
      dmIn.addEventListener("change", () => { if (dmIn.files.length) addFiles([dmIn.files[0]], true); });
      const asIn = el("input", { type: "file", id: "imp-assets", multiple: true, "aria-describedby": "imp-assets-hint imp-assets-err" });
      asIn.addEventListener("change", () => { if (asIn.files.length) addFiles([...asIn.files], false); });
      const rows = dr.assets.map((a, i) => {
        const p = el("input", { class: "input mono", id: `imp-ap-${a.id}`, value: a.path, autocomplete: "off", "aria-invalid": errs[`asset.${i}`] ? "true" : null, "aria-describedby": `imp-ae-${a.id}` });
        p.addEventListener("input", () => { a.path = p.value; touch(); });
        return el("li", { class: "asset-row" },
          el("label", { for: p.id, text: `Path for ${a.file} (${fmtBytes(a.size)})` }),
          el("div", { class: "edit-control" }, p, el("button", { type: "button", class: "btn btn-small btn-ghost", "aria-label": `Remove ${a.file}`, onclick: () => { dr.assets.splice(i, 1); touch(); redraw("#imp-assets"); } }, "Remove")),
          el("div", { class: "field-err", id: `imp-ae-${a.id}`, "aria-live": "polite", text: errs[`asset.${i}`] || "" }));
      });
      const total = importTotal(dr);
      fillKids(holder, ...[head, err, busy].filter(Boolean),
        el("p", { class: "panel-note", text: "Copies a .dm and its images into a new project. Nothing is written until you confirm." }),
        el("form", { class: "edit-form", novalidate: true, onsubmit: (e) => {
          e.preventDefault(); dr.showErrors = true;
          if (Object.keys(importProblems(dr)).length) { redraw("[aria-invalid=true], .field-err:not(:empty)"); return; }
          runWrite(dr, url, body(), true, redraw);
        } },
          el("fieldset", { class: "edit-group" }, el("legend", { text: "New project" }), el("div", { class: "edit-grid creator-grid" },
            inp("slug", "Project folder (slug)", "A new folder name in the workspace."), inp("name", "Display name (optional)", "Shown in the browser; defaults to the mod name."))),
          el("fieldset", { class: "edit-group" }, el("legend", { text: "Mod file" }),
            el("div", { class: "edit-field wide" }, el("label", { for: "imp-dm", text: "The .dm file" }), dmIn,
              el("div", { class: "field-meta", id: "imp-dm-hint" }, dr.dm ? ["Chosen: ", el("strong", { text: dr.dm.filename }), ` (${fmtBytes(dr.dm.size)})`] : el("span", { class: "faint", text: "No file chosen." })),
              el("div", { class: "field-err", id: "imp-dm-err", "aria-live": "polite", text: errs.dm || "" }))),
          el("fieldset", { class: "edit-group" }, el("legend", { text: "Asset files (optional)" }),
            el("div", { class: "edit-field wide" }, el("label", { for: "imp-assets", text: "Add image files" }), asIn,
              el("div", { class: "field-meta faint", id: "imp-assets-hint", text: "Each file's path is relative to the mod folder, as the .dm refers to it (e.g. mymod/units/hero.tga). Edit a path below if needed." }),
              el("div", { class: "field-err", id: "imp-assets-err", "aria-live": "polite", text: errs.assets || "" })),
            rows.length ? el("ul", { class: "plain-list" }, rows) : el("p", { class: "faint", text: "No assets added." })),
          el("p", { class: total > MAX_IMPORT_BYTES ? "field-err" : "faint", role: "status", "aria-live": "polite",
            text: `Selected: ${fmtBytes(total)} of the ${fmtBytes(MAX_IMPORT_BYTES)} total limit.${errs.size ? ` ${errs.size}` : ""}` }),
          el("div", { class: "btn-row edit-actions" }, el("button", { type: "submit", class: "btn", disabled: !CSRF || dr.reading > 0 || null, ...RT }, "Review import"),
            el("button", { type: "button", class: "btn btn-ghost", onclick: () => { state.importDraft = null; render(); } }, "Cancel"),
            CSRF ? statusLine("Nothing is written until you confirm the review.") : noToken())));
      focusIn(holder, focusSel);
    }
    redraw();
    return holder;
  }

  // Equipment replacement is explicit about clearing the inherited group; drafts survive a stale-source reload.
  function equipmentEditor(model, unit) {
    const key = `equipment:${model.project.slug}:${unit.id}`, slug = model.project.slug;
    if (!state.authoring.has(key)) state.authoring.set(key, { data: null, weapons: [], armor: [],
      replace: {}, preview: null, error: null, busy: false });
    const draft = state.authoring.get(key), body = el("div", { class: "stack" });
    const details = el("details", { class: "panel loadout-editor" }, el("summary", { text: "Edit equipment" }), body);
    const url = `${apiBase(slug)}/monsters/${unit.id}/equipment`;
    async function load(keep) {
      draft.busy = true; draw();
      try {
        draft.data = (await getJSON(url)).result;
        if (!keep) for (const group of ["weapons", "armor"]) draft[group] = draft.data.equipment[group].map((item) => item.id).filter(Number.isInteger);
        draft.error = null; draft.preview = null;
      } catch (error) { draft.error = error; }
      draft.busy = false; draw();
    }
    function draw() {
      if (!draft.data) { body.replaceChildren(draft.error ? errorBox(draft.error, "equipment") : el("p", { text: "Loading equipment…" })); return; }
      const children = [el("p", { class: "panel-note", text: draft.data.note })];
      const invalidate = () => { draft.preview = null; draft.error = null; };
      for (const group of ["weapons", "armor"]) {
        const id = `equipment-${unit.id}-${group}`, check = el("input", { id, type: "checkbox", disabled: draft.busy });
        check.checked = !!draft.replace[group];
        check.addEventListener("change", () => { draft.replace[group] = check.checked; invalidate(); draw(); });
        const rows = draft[group].map((value, index) => {
          const selectId = `${id}-${index}`, select = el("select", { id: selectId, class: "input", disabled: draft.busy },
            el("option", { value: "", text: "Choose equipment" }),
            draft.data.options[group].map((option) => el("option", { value: option.id, text: `${option.name || "Unnamed"} (#${option.id}, ${option.source})` })));
          select.value = value === null ? "" : String(value);
          select.addEventListener("change", () => { draft[group][index] = select.value === "" ? null : Number(select.value); draft.replace[group] = true; invalidate(); draw(); });
          return el("div", { class: "btn-row" }, el("label", { for: selectId, text: `${group === "armor" ? "Armour" : "Weapon"} ${index + 1}` }), select,
            el("button", { type: "button", class: "btn btn-small", disabled: draft.busy, text: "Remove", onclick: () => { draft[group].splice(index, 1); draft.replace[group] = true; invalidate(); draw(); } }));
        });
        children.push(el("fieldset", null, el("legend", { text: group === "armor" ? "Armour" : "Weapons" }),
          el("label", { for: id }, check, " Replace this entire group"), rows,
          el("button", { type: "button", class: "btn btn-small", disabled: draft.busy || draft[group].length >= 8, text: `Add ${group === "armor" ? "armour" : "weapon"}`, onclick: () => { draft[group].push(null); draft.replace[group] = true; invalidate(); draw(); } })));
      }
      const request = () => ({ expected_sha256: draft.data.sha256,
        ...Object.fromEntries(["weapons", "armor"].filter((group) => draft.replace[group]).map((group) => [group, draft[group]])) });
      children.push(el("div", { class: "btn-row" }, el("button", { type: "button", class: "btn", disabled: draft.busy,
        text: "Review equipment changes", onclick: async () => {
          draft.busy = true; draft.error = null; draw();
          try { draft.preview = await postJSON(url, { ...request(), preview: true }); }
          catch (error) { draft.error = error; }
          draft.busy = false; draw();
        } }), el("button", { type: "button", class: "btn btn-ghost", disabled: draft.busy, text: "Cancel", onclick: () => { state.authoring.delete(key); details.open = false; render(); } })));
      if (draft.error) children.push(errorBox(draft.error, "equipment"),
        el("button", { type: "button", class: "btn", text: "Reload equipment (keep draft)", disabled: draft.busy, onclick: () => load(true) }));
      if (draft.preview) children.push(el("pre", { class: "code", text: draft.preview.diff }),
        el("button", { type: "button", class: "btn", disabled: draft.busy, text: "Save equipment to .dm", onclick: async () => {
          draft.busy = true; draw();
          try {
            const saved = await postJSON(url, { ...request(), preview: false }); state.authoring.delete(key);
            recordReceipt(slug, `Saved equipment for ${txt(unit.name) || "unit"} (#${unit.id})`, saved);
            state.models.delete(slug); invalidateAuth(); toast(saved.written ? "Equipment saved with a source backup." : "Equipment already matches; no source change."); render();
          } catch (error) { draft.error = error; draft.preview = null; draft.busy = false; draw(); }
        } }));
      body.replaceChildren(...children);
    }
    details.addEventListener("toggle", () => { if (details.open) { if (!draft.data && !draft.busy) load(false); else draw(); } });
    return details;
  }

  // ---------- vanilla inspector (read-only, per project) ----------
  // GET .../inspector (counts, provenance), .../inspector/<cat>?q=&c=field:op[:value]&sort=&order=&page=&per_page=
  // (one bounded page; c repeats and is AND-ed), .../inspector/<cat>/filters (common filters, columns, sorts) and
  // .../inspector/<cat>/<id> (detail) read the catalog this project reads: its reference snapshot, else the live
  // catalog. Images come only from the existing id-based sprite and icon routes. Nothing here writes.
  // List state lives in the hash query (q, c, sort, order, per, page), so detail links, category links, bookmarks and
  // Back keep it; within one category the list and detail update in place instead of re-rendering the page.
  const INSP_CATS = [["units", "Units"], ["sites", "Sites"], ["events", "Events"], ["mercs", "Mercenaries"], ["items", "Items"],
    ["spells", "Spells"], ["weapons", "Weapons"], ["armors", "Armour"], ["nations", "Nations"]];
  const INSP_PER_PAGE = 40, INSP_PAGE_SIZES = [20, 40, 60, 100], INSP_MAX_CONDS = 8;
  const INSP_OPS = [["gte", "at least", "≥"], ["lte", "at most", "≤"], ["between", "between", "between"], ["eq", "equals", "="], ["ne", "does not equal", "≠"],
    ["gt", "greater than", ">"], ["lt", "less than", "<"], ["has", "has a value", "has a value"], ["none", "is blank or 0", "is blank or 0"], ["contains", "contains", "contains"]];
  const INSP_NUM_OPS = new Set(["gt", "gte", "lt", "lte", "between"]);
  const INSP_VALUE_OPS = new Set(["eq", "ne", "contains", "gt", "gte", "lt", "lte", "between"]);
  const INSP_NUM_RE = /^-?\d+(\.\d+)?$/;
  const INSP_KEYS = ["q", "c", "sort", "order", "per", "page", "age", "nation", "role"];
  const INSP_AGE_ABBR = { 1: "EA", 2: "MA", 3: "LA" };
  const SITE_PATH_LETTER = { Fire: "F", Air: "A", Water: "W", Earth: "E", Astral: "S", Death: "D", Nature: "N", Glamour: "G", Blood: "B", Holy: "H" };
  const inspDefaults = () => ({ q: "", conds: [], sort: "id", order: "asc", per: state.inspPer || INSP_PER_PAGE, page: 1, age: "", nation: "", role: "" });
  const inspDraft = (slug, cat) => draftOf(state.inspector, `${slug}:${cat}`, inspDefaults);
  const inspCondParam = (c) => c.op === "between" ? `${c.field}:between:${c.value}..${c.value2}` : INSP_VALUE_OPS.has(c.op) ? `${c.field}:${c.op}:${c.value}` : `${c.field}:${c.op}`;
  function inspParseCond(s) {
    const m = /^([^:]+):([^:]+)(?::([\s\S]*))?$/.exec(String(s));
    if (!m) return null;
    const c = { field: m[1], op: m[2], value: m[3] || "", value2: "" };
    if (c.op === "between") { const i = c.value.indexOf(".."); c.value2 = i < 0 ? "" : c.value.slice(i + 2); c.value = i < 0 ? c.value : c.value.slice(0, i); }
    return c;
  }
  // List parameters of one state, defaults left out.
  function inspParams(d) {
    const p = new URLSearchParams();
    if (d.q.trim()) p.set("q", d.q.trim());
    for (const k of ["age", "nation", "role"]) if (d[k]) p.set(k, d[k]);
    for (const c of d.conds) p.append("c", inspCondParam(c));
    if (d.sort && d.sort !== "id") p.set("sort", d.sort);
    if (d.order === "desc") p.set("order", "desc");
    if (d.per !== INSP_PER_PAGE) p.set("per", String(d.per));
    if (d.page > 1) p.set("page", String(d.page));
    return p;
  }
  // The list state named by a hash query, or null when it names none (then the remembered state applies).
  function inspFromQuery(qs) {
    if (!INSP_KEYS.some((k) => qs.has(k))) return null;
    const per = parseInt(qs.get("per") || "", 10), page = parseInt(qs.get("page") || "", 10);
    return { q: (qs.get("q") || "").slice(0, 60), conds: qs.getAll("c").map(inspParseCond).filter(Boolean),
      sort: qs.get("sort") || "id", order: qs.get("order") === "desc" ? "desc" : "asc",
      per: per >= 1 ? Math.min(per, 100) : INSP_PER_PAGE, page: page >= 1 ? page : 1,
      age: /^[123]$/.test(qs.get("age") || "") ? qs.get("age") : "", nation: /^(\d{1,4}|national|none)$/.test(qs.get("nation") || "") ? qs.get("nation") : "",
      role: /^(troop|commander|capital|hero)$/.test(qs.get("role") || "") ? qs.get("role") : "" };
  }
  const inspSameState = (a, b) => inspParams(a).toString() === inspParams(b).toString();
  // Hash link to a category (and entry) carrying that category's list state; ?n= stays first.
  function inspHref(slug, cat, id, d) {
    const base = route("p", slug, "inspector", ...(cat ? [cat] : []), ...(id !== undefined && id !== null && id !== "" ? [id] : []));
    const ds = d || (cat && state.inspector.get(`${slug}:${cat}`));
    const extra = ds ? inspParams(ds).toString() : "";
    return extra ? base + (base.includes("?") ? "&" : "?") + extra : base;
  }
  const inspItemIcon = (slug, id) => (Number.isInteger(id) && id > 0 && id < 10000 ? `${apiBase(slug)}/item-icons/${id}.png` : null);
  function inspListUrl(slug, cat, d) {
    const p = inspParams({ ...d, per: INSP_PER_PAGE, page: 1 });
    p.delete("per"); p.delete("page");
    p.set("page", String(d.page || 1)); p.set("per_page", String(d.per || INSP_PER_PAGE));
    return `${apiBase(slug)}/inspector/${encodeURIComponent(cat)}?${p}`;
  }

  // Bounded GET cache for inspector reads: settled results (LRU), one shared request per URL, and requests that
  // nobody waits for any more are aborted. Cleared with invalidateAuth().
  const INSP_CACHE_MAX = 60;
  const inspCache = new Map(), inspInflight = new Map();
  const INSP_ABORTED = { error: { code: "aborted", message: "Superseded by a newer request." } };
  const inspAborted = (e) => !!(e && e.error && e.error.code === "aborted");
  function inspGet(url, signal) {
    if (inspCache.has(url)) { const v = inspCache.get(url); inspCache.delete(url); inspCache.set(url, v); return Promise.resolve(v); }
    let f = inspInflight.get(url);
    if (!f) {
      const ctrl = new AbortController();
      f = { ctrl, users: 0 };
      f.p = getJSON(url, { signal: ctrl.signal }).then((r) => {
        inspCache.set(url, r.result);
        while (inspCache.size > INSP_CACHE_MAX) inspCache.delete(inspCache.keys().next().value);
        return r.result;
      });
      f.p.then(() => {}, () => {}).then(() => { if (inspInflight.get(url) === f) inspInflight.delete(url); });
      inspInflight.set(url, f);
    }
    f.users++;
    return new Promise((resolve, reject) => {
      let done = false;
      const finish = () => { if (done) return false; done = true; f.users--; return true; };
      if (signal) {
        const quit = () => {
          if (!finish()) return;
          if (f.users <= 0 && inspInflight.get(url) === f) { inspInflight.delete(url); f.ctrl.abort(); }
          reject(INSP_ABORTED);
        };
        if (signal.aborted) { quit(); return; }
        signal.addEventListener("abort", quit, { once: true });
      }
      f.p.then((v) => { if (finish()) resolve(v); }, (e) => { if (finish()) reject(e); });
    });
  }

  // Compact provenance: snapshot or live catalog, data version and revision; every field in a disclosure.
  function inspProvenance(pv) {
    if (!pv) return null;
    return el("details", { class: "insp-prov" },
      el("summary", { class: "faint", text: `Vanilla data from dom6inspector · read-only${pv.dataset_version ? ` · game ${pv.dataset_version}` : ""}` }),
      el("p", { class: "faint insp-attr", text: txt(pv.attribution) }),
      el("dl", { class: "kv" }, Object.entries(pv).filter(([k]) => k !== "attribution").map(([k, v]) =>
        [el("dt", { text: k }), el("dd", { class: "mono", text: v && typeof v === "object" ? JSON.stringify(v) : txt(v) })])));
  }
  // Thumbnail for one list row: unit sprites, item icons and merc commander sprites; other categories show none.
  function inspThumb(slug, cat, r) {
    if (cat === "units") return previewThumb(catalogSprite(slug, r.id), "No sprite");
    if (cat === "mercs") return previewThumb(r.commander ? catalogSprite(slug, r.commander.id) : null, "No commander");
    if (cat === "items") return previewThumb(inspItemIcon(slug, r.id), "No icon");
    return null;
  }
  // Readable facts from the server's row summary (no raw cost encodings); units add their nations.
  function inspRowSub(cat, r, label) {
    const f = r.fields || {}, vals = r.values || {};
    const parts = [];
    if (cat === "mercs") parts.push(r.commander ? txt(r.commander.name || "#" + r.commander.id) : null,
      r.troop ? `${txt(f.nrunits)} × ${txt(r.troop.name || "#" + r.troop.id)}` : "no troops");
    else if (r.summary) parts.push(...r.summary);
    else parts.push(...Object.entries(f).filter(([k]) => !(k in vals)).slice(0, 3).map(([k, v]) => `${k} ${txt(v)}`));
    if (cat === "units" && r.nations) {
      const ns = r.nations.map((n) => `${INSP_AGE_ABBR[n.era] || ""} ${n.name}`.trim());
      if (ns.length) parts.push(ns.length > 2 ? `${ns.slice(0, 2).join(", ")} +${ns.length - 2}` : ns.join(", "));
    }
    // Values of the filtered and sorted columns, so the reason a row matched is visible.
    parts.push(...Object.entries(vals).map(([k, v]) => `${label(k)} ${txt(v) || "blank"}`));
    if (r.filter_value !== undefined) parts.push(`= ${txt(r.filter_value) || "(empty)"}`);
    return parts.filter(Boolean).join(" · ");
  }

  let inspMounted = null;  // the inspector currently on screen, for in-place route updates
  function viewInspector(m, cat, id) {
    const slug = m.project.slug;
    inspMounted = null;
    if (!catalogOf(m)) return stateBox("empty", "No game-data catalog for this project.",
      "Create a reference snapshot under Overview, or start the server with --catalog.");
    cat = INSP_CATS.some((c) => c[0] === cat) ? cat : "units";
    // The address wins when it names a list state; otherwise the remembered one is written into it (no new entry).
    const d = inspDraft(slug, cat), fromUrl = inspFromQuery(hashQuery());
    if (fromUrl) Object.assign(d, fromUrl);
    else if (inspParams(d).toString()) history.replaceState(null, "", inspHref(slug, cat, id, d));
    const nav = el("nav", { class: "btn-row insp-cats", "aria-label": "Catalog categories" },
      INSP_CATS.map(([k, l]) => el("a", { class: "btn btn-small", href: inspHref(slug, k), "aria-current": k === cat ? "page" : null, "data-cat": k }, l, el("span", { class: "count", text: "" }))));
    const provBox = el("div");
    inspGet(`${apiBase(slug)}/inspector`).then((s) => {
      for (const c of s.categories || []) {
        const link = nav.querySelector(`[data-cat="${c.key}"]`);
        if (!link) continue;
        link.querySelector(".count").textContent = c.available ? ` ${c.count}` : " –";
        if (!c.available) link.title = `${c.file} is not in this catalog`;
      }
      fillKids(provBox, inspProvenance(s.provenance));
    }, (e) => fillKids(provBox, errorBox(e, "catalog counts")));
    const detail = inspDetail(m, cat);
    const list = inspList(m, cat, d, {
      currentId: () => detail.id,
      onState: () => { const a = nav.querySelector(`[data-cat="${cat}"]`); if (a) a.setAttribute("href", inspHref(slug, cat, null, d)); },
    });
    detail.show(id);
    const root = el("div", { class: "stack inspector" }, nav, list.tools,
      el("div", { class: "split insp-split" }, list.pane, detail.node), provBox);
    inspMounted = {
      root, slug, cat, nkey: state.nation && state.nation.key,
      // True when the route was applied in place (same project, category and nation, inspector still on screen).
      update(slug2, cat2, id2, nkey) {
        if (!root.isConnected || slug2 !== slug || (INSP_CATS.some((c) => c[0] === cat2) ? cat2 : "units") !== cat || nkey !== this.nkey) return false;
        // An address without list parameters (a plain tab link) keeps the remembered state, as a fresh view does.
        const want = inspFromQuery(hashQuery());
        if (want && !inspSameState(want, d)) list.apply(want);
        else if (!want && inspParams(d).toString()) history.replaceState(null, "", inspHref(slug, cat, id2, d));
        const changed = String(id2 ?? "") !== String(detail.id ?? "");
        if (changed) detail.show(id2);
        list.markCurrent(id2);
        return { changed };
      },
    };
    return root;
  }

  function inspList(m, cat, d, hooks) {
    const slug = m.project.slug, label = INSP_CATS.find((c) => c[0] === cat)[1], noun = label.toLowerCase();
    const metaUrl = `${apiBase(slug)}/inspector/${encodeURIComponent(cat)}/filters`;
    let meta = null, last = null, seq = 0, ctrl = null, timer = 0, editIndex = -1, edField = "";
    const fieldInfo = (k) => (meta && meta.columns.find((c) => c.key === k)) || null;
    const commonOf = (k) => (meta && meta.common.find((c) => c.field === k)) || null;
    const fieldLabel = (k) => { const c = commonOf(k) || fieldInfo(k); return (c && c.label) || k; };
    const choiceLabel = (k, v) => { const c = commonOf(k), ch = c && (c.choices || []).find((x) => x.value === v); return ch && ch.label ? ch.label : v; };
    const opSym = (op) => (INSP_OPS.find((o) => o[0] === op) || [op, op, op])[2];
    const opWord = (op) => (INSP_OPS.find((o) => o[0] === op) || [op, op])[1];
    const condText = (c) => c.op === "between" ? `${fieldLabel(c.field)} ${c.value}–${c.value2}`
      : INSP_VALUE_OPS.has(c.op) ? `${fieldLabel(c.field)} ${opSym(c.op)} ${choiceLabel(c.field, c.value)}` : `${fieldLabel(c.field)} ${opSym(c.op)}`;
    const condSpeech = (c) => c.op === "between" ? `${fieldLabel(c.field)} between ${c.value} and ${c.value2}`
      : `${fieldLabel(c.field)} ${opWord(c.op)}${INSP_VALUE_OPS.has(c.op) ? ` ${choiceLabel(c.field, c.value)}` : ""}`;

    // ----- toolbar: search and a few everyday filters; sort, page size and column conditions under Advanced -----
    const q = el("input", { class: "input", type: "search", id: "insp-q", value: d.q, maxlength: "60", autocomplete: "off", placeholder: `Name or id${cat === "events" ? " or description" : ""}  ( / )` });
    const sortSel = el("select", { class: "input", id: "insp-sort" });
    const orderBtn = el("button", { type: "button", class: "btn btn-small insp-order", id: "insp-order" });
    const perSel = el("select", { class: "input", id: "insp-per" }, INSP_PAGE_SIZES.map((n) => el("option", { value: String(n), text: `${n} per page` })));
    const resetBtn = el("button", { type: "button", class: "btn btn-small btn-ghost", onclick: () => reset() }, "Reset all");
    const simpleBox = el("div", { class: "insp-simple", role: "group", "aria-label": `${label} filters` });
    const chips = el("ul", { class: "insp-chips", "aria-label": "Column filters" });
    const chipsRow = el("div", { class: "insp-chips-row" });
    // Condition editor: searchable column chooser (combobox), operator, value(s).
    const colIn = el("input", { class: "input", id: "insp-col", type: "text", role: "combobox", autocomplete: "off", spellcheck: "false", maxlength: "60",
      "aria-autocomplete": "list", "aria-expanded": "false", "aria-controls": "insp-col-list", placeholder: "Search columns, e.g. hp, flying" });
    const colList = el("ul", { class: "insp-col-list", id: "insp-col-list", role: "listbox", "aria-label": "Columns", hidden: true });
    const opSel = el("select", { class: "input", id: "insp-op" });
    const valBox = el("span", { class: "insp-vals" });
    const condErr = el("p", { class: "insp-cond-err", id: "insp-cond-err", role: "alert" });
    const addBtn = el("button", { type: "submit", class: "btn btn-small insp-add" }, "Add filter");
    const cancelBtn = el("button", { type: "button", class: "btn btn-small btn-ghost", hidden: true, onclick: () => closeEditor(true) }, "Cancel");
    const editorHint = el("span", { class: "faint insp-hint" });
    const form = el("form", { class: "insp-cond", "aria-label": "Add a column filter", novalidate: true },
      el("span", { class: "insp-col-wrap" }, el("label", { for: "insp-col", class: "insp-lbl", text: "Column" }), colIn, colList),
      el("span", { class: "insp-field" }, el("label", { for: "insp-op", class: "insp-lbl", text: "Condition" }), opSel),
      valBox, el("span", { class: "insp-actions" }, addBtn, cancelBtn), editorHint, condErr);
    const status = el("p", { class: "insp-status", role: "status", "aria-live": "polite" });
    const sem = el("p", { class: "faint insp-sem" });
    const advSum = el("summary", { text: "Advanced" });
    const adv = el("details", { class: "insp-adv", open: d.sort !== "id" || d.order !== "asc" || null }, advSum,
      el("div", { class: "insp-row" },
        el("span", { class: "insp-field" }, el("label", { for: "insp-sort", class: "insp-lbl", text: "Sort" }), sortSel, orderBtn),
        el("span", { class: "insp-field" }, el("label", { for: "insp-per", class: "insp-lbl", text: "Per page" }), perSel)),
      form, chipsRow, sem);
    const tools = el("section", { class: "insp-tools", "aria-label": `Filter ${noun}` },
      el("div", { class: "insp-row" },
        el("div", { class: "unit-filter insp-search", role: "search" }, el("label", { for: "insp-q", class: "sr-only", text: `Search ${noun}` }), q),
        simpleBox, resetBtn),
      adv, status);

    const listBox = el("div", { class: "insp-results", id: "insp-results", "aria-label": `${label} results` });
    const pager = el("div");
    const pane = el("div", { class: "unit-pane auth-pane insp-pane" }, listBox, pager);

    // ----- state changes -----
    const pushUrl = (push) => {
      const href = inspHref(slug, cat, hooks.currentId(), d);
      if (location.hash !== href) history[push ? "pushState" : "replaceState"](null, "", href);
      hooks.onState();
    };
    // Apply a change: new page 1 unless paging, URL entry (pushed for discrete actions), then load.
    function change(mut, opts) {
      mut(d);
      if (!(opts && opts.keepPage)) d.page = 1;
      pushUrl(!(opts && opts.replace));
      syncTools();
      load();
    }
    function apply(want) {  // from the address (Back/Forward or a link); no new history entry
      Object.assign(d, want);
      q.value = d.q;
      closeEditor(false);
      syncTools();
      hooks.onState();
      load();
    }
    const anyFilter = () => !!(d.conds.length || d.q.trim() || d.age || d.nation || d.role);
    function reset() {
      change((x) => Object.assign(x, inspDefaults(), { per: x.per }));
      q.value = "";
      closeEditor(false);
      q.focus();
    }

    // ----- loading: previous results stay visible (dimmed) until the new page arrives -----
    function load() {
      const mine = ++seq, url = inspListUrl(slug, cat, d);
      if (ctrl) ctrl.abort();
      ctrl = new AbortController();
      listBox.setAttribute("aria-busy", "true");
      pane.classList.toggle("is-updating", !!last);
      if (!last) fillKids(listBox, stateBox("loading", `Reading ${noun}...`));
      else status.dataset.busy = "1";
      drawStatus();
      inspGet(url, ctrl.signal).then((r) => { if (mine === seq) { last = r; done(); draw(r); } }, (e) => {
        if (mine !== seq || inspAborted(e)) return;
        done();
        const conds = anyFilter() || d.sort !== "id";
        fillKids(listBox, errorBox(e, `catalog ${noun}`),
          el("div", { class: "btn-row" },
            el("button", { type: "button", class: "btn btn-small", onclick: () => { inspCache.delete(url); load(); } }, "Retry"),
            conds ? el("button", { type: "button", class: "btn btn-small btn-ghost", onclick: () => reset() }, "Reset filters") : null),
          null);
        last = null;
        fillKids(pager);
        drawStatus(e);
      });
    }
    function done() { listBox.removeAttribute("aria-busy"); pane.classList.remove("is-updating"); delete status.dataset.busy; }
    function drawStatus(err) {
      const r = last;
      const sortTxt = d.sort === "id" && d.order === "asc" ? "" : ` · sorted by ${fieldLabel(d.sort === "id" ? "Id" : d.sort === "name" ? "Name" : d.sort)} ${orderText()}`;
      const busy = status.dataset.busy ? " · updating..." : "";
      if (err) { status.textContent = "Could not load results."; return; }
      if (!r) { status.textContent = `Loading ${noun}...`; return; }
      const filtered = r.matches !== r.total, from = (r.page - 1) * r.per_page;
      const [a, b] = r.range || [from + 1, from + r.results.length];
      status.textContent = r.matches
        ? `${r.matches.toLocaleString()} ${filtered ? `of ${r.total.toLocaleString()} ` : ""}${noun}${r.pages > 1 ? ` · ${a}–${b}` : ""}${sortTxt}${busy}`
        : `No ${noun} match${busy}`;
    }
    function orderText() {
      const kind = d.sort === "name" ? "text" : d.sort === "id" ? "number" : ((fieldInfo(d.sort) || {}).kind || "number");
      return kind === "text" ? (d.order === "desc" ? "Z–A" : "A–Z") : (d.order === "desc" ? "high to low" : "low to high");
    }
    function draw(r) {
      // The server clamps a page past the end (a bookmark after filters changed); the address follows it.
      if (d.page !== r.page) { d.page = r.page; pushUrl(false); }
      drawStatus();
      sem.textContent = r.semantics || "";
      if (!r.results.length) {
        fillKids(listBox, stateBox("empty", `No ${noun} match.`, anyFilter() ? "Try fewer filters." : "This catalog table is empty."),
          anyFilter() ? el("div", { class: "btn-row" }, el("button", { type: "button", class: "btn btn-small", onclick: () => reset() }, "Clear filters")) : null);
        fillKids(pager);
        return;
      }
      const id = hooks.currentId();
      const list = el("ul", { class: "unit-list insp-list", "aria-label": `Catalog ${noun}, page ${r.page} of ${r.pages}` }, r.results.map((x) => el("li", null,
        el("a", { class: "unit-item", href: inspHref(slug, cat, x.id, d), "data-id": String(x.id), "aria-current": String(x.id) === String(id ?? "") ? "true" : null },
          inspThumb(slug, cat, x),
          el("span", null, el("div", { class: "nm", text: x.name || "(unnamed)" }), el("div", { class: "sub", text: inspRowSub(cat, x, fieldLabel) }))))));
      list.addEventListener("keydown", (e) => {
        if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
        const links = [...list.querySelectorAll("a")], i = links.indexOf(document.activeElement);
        if (i < 0) return;
        e.preventDefault();
        if (e.key === "ArrowUp" && i === 0) { q.focus(); return; }
        links[Math.max(0, Math.min(links.length - 1, i + (e.key === "ArrowDown" ? 1 : -1)))].focus();
      });
      const hadFocus = listBox.contains(document.activeElement) || pager.contains(document.activeElement);
      fillKids(listBox, list);
      const go = (p) => change((x) => { x.page = p; }, { keepPage: true });
      fillKids(pager, r.pages > 1 ? el("nav", { class: "btn-row insp-pager", "aria-label": "Pages" },
        el("button", { type: "button", class: "btn btn-small", disabled: r.page <= 1 || null, onclick: () => go(1), "aria-label": "First page" }, "«"),
        el("button", { type: "button", class: "btn btn-small", disabled: r.page <= 1 || null, onclick: () => go(r.page - 1) }, "Previous"),
        el("span", { class: "faint insp-pageno", text: `${r.page} / ${r.pages}` }),
        el("button", { type: "button", class: "btn btn-small", disabled: r.page >= r.pages || null, onclick: () => go(r.page + 1) }, "Next"),
        el("button", { type: "button", class: "btn btn-small", disabled: r.page >= r.pages || null, onclick: () => go(r.pages), "aria-label": "Last page" }, "»")) : null);
      if (hadFocus) { const a = list.querySelector("a"); if (a) a.focus({ preventScroll: true }); }
      list.scrollTop = 0;
      // Keep the open entry visible inside the scrolling list (the page itself does not scroll).
      const cur = list.querySelector('[aria-current="true"]');
      if (cur) list.scrollTop = Math.max(0, cur.parentElement.offsetTop - list.offsetTop - list.clientHeight / 2);
    }
    function markCurrent(id) {
      for (const a of listBox.querySelectorAll("a.unit-item")) {
        if (a.dataset.id === String(id ?? "")) a.setAttribute("aria-current", "true"); else a.removeAttribute("aria-current");
      }
    }

    // ----- toolbar drawing -----
    function syncTools() {
      // A bookmarked size outside the menu (still at most 100) gets its own entry.
      if (![...perSel.options].some((o) => o.value === String(d.per))) perSel.append(el("option", { value: String(d.per), text: `${d.per} per page` }));
      perSel.value = String(d.per);
      const sorts = meta ? [...meta.sorts] : [{ key: "id", label: "Id" }, { key: "name", label: "Name" }];
      for (const c of d.conds) if (!sorts.some((s) => s.key === c.field) && (!meta || (fieldInfo(c.field) || {}).kind !== "text")) sorts.push({ key: c.field, label: fieldLabel(c.field) });
      if (!sorts.some((s) => s.key === d.sort)) sorts.push({ key: d.sort, label: fieldLabel(d.sort) });
      fillKids(sortSel, sorts.map((s) => el("option", { value: s.key, text: s.label + (s.key !== "id" && s.key !== "name" && s.label !== s.key ? ` (${s.key})` : "") })));
      sortSel.value = d.sort;
      const ot = orderText();
      orderBtn.textContent = d.order === "desc" ? `↓ ${ot}` : `↑ ${ot}`;
      orderBtn.setAttribute("aria-label", `Sort order: ${ot}. Activate to reverse.`);
      resetBtn.disabled = !(anyFilter() || d.sort !== "id" || d.order !== "asc") || null;
      // Conditions set by an everyday filter show in its dropdown; only the others are chips.
      const advanced = d.conds.map((c, i) => [c, i]).filter(([c]) => !isOwned(c));
      fillKids(chips, advanced.map(([c, i]) => el("li", { class: `insp-chip${i === editIndex ? " is-editing" : ""}` },
        el("button", { type: "button", class: "insp-chip-t", title: "Edit this filter", "aria-label": `Edit filter: ${condSpeech(c)}`, onclick: () => openEditor(c.field, i) }, condText(c)),
        el("button", { type: "button", class: "insp-chip-x", "aria-label": `Remove filter: ${condSpeech(c)}`, onclick: () => removeCond(i) }, "×"))));
      fillKids(chipsRow, advanced.length ? [el("span", { class: "insp-lbl", text: "Column filters (all must match)" }), chips] : null);
      advSum.textContent = advanced.length ? `Advanced (${advanced.length})` : "Advanced";
      if (meta && advanced.length) adv.open = true;
      addBtn.disabled = editIndex < 0 && d.conds.length >= INSP_MAX_CONDS || null;
      drawSimple();
    }
    function removeCond(i) {
      if (editIndex === i) closeEditor(false);
      else if (editIndex > i) editIndex--;
      change((x) => { x.conds = x.conds.filter((_, j) => j !== i); });
      // Keep keyboard focus in the chip row at the same position (or the search box when it empties).
      const xs = chips.querySelectorAll(".insp-chip-x");
      (xs[Math.min(i, xs.length - 1)] || q).focus();
    }

    // ----- everyday filters: a list parameter (age, nation, role) or one column condition per choice -----
    const ownedBy = (spec, c) => (spec.param ? null : (spec.choices || []).find((ch) => ch.cond && ch.cond === inspCondParam(c))) || null;
    const isOwned = (c) => !!(meta && (meta.simple || []).some((s) => ownedBy(s, c)));
    const nationSpec = () => (meta && (meta.simple || []).find((s) => s.param === "nation")) || null;
    function drawSimple() {
      if (!meta) return;
      const had = simpleBox.contains(document.activeElement) ? document.activeElement.id : "";
      fillKids(simpleBox, (meta.simple || []).map(simpleSelect));
      if (had) { const n = document.getElementById(had); if (n) n.focus(); }
    }
    function simpleSelect(s) {
      const id = `insp-s-${s.key}`, age = Number(d.age) || 0;
      const owned = s.param ? null : d.conds.map((c) => ownedBy(s, c)).find(Boolean);
      const cur = s.param ? d[s.param] || "" : owned ? owned.value : "";
      const sel = el("select", { class: "input", id, disabled: s.param === "role" && d.nation === "none" || null });
      const opt = (v, t) => el("option", { value: v, text: t });
      if (s.param === "nation") {
        // An age narrows the nation list; units without a nation have no age.
        sel.append(opt("", "All"), ...(s.special || []).filter((x) => !(age && x.value === "none")).map((x) => opt(x.value, x.label)),
          ...[1, 2, 3].filter((a) => !age || a === age).map((a) => el("optgroup", { label: `${INSP_AGE_ABBR[a]} nations` },
            s.choices.filter((n) => n.era === a).map((n) => opt(n.value, `${INSP_AGE_ABBR[a]} ${n.label}`)))));
      } else sel.append(opt("", "All"), ...(s.choices || []).map((ch) => opt(ch.value, ch.label)));
      // A bookmarked value that is no longer offered stays visible so it can be cleared.
      if (cur && ![...sel.options].some((o) => o.value === cur)) sel.append(opt(cur, cur));
      sel.value = cur;
      sel.addEventListener("change", () => setSimple(s, sel.value));
      return el("span", { class: "insp-field" }, el("label", { for: id, class: "insp-lbl", text: s.label }), sel);
    }
    function setSimple(s, v) {
      if (!s.param && v && !d.conds.some((c) => ownedBy(s, c)) && d.conds.length >= INSP_MAX_CONDS) {
        status.textContent = `At most ${INSP_MAX_CONDS} filters. Remove a column filter under Advanced first.`;
        return;
      }
      change((x) => {
        if (s.param) {
          x[s.param] = v;
          const ns = nationSpec(), n = ns && ns.choices.find((c) => c.value === x.nation);
          // A nation outside the chosen age, or "No nation" with an age, is cleared rather than kept invalid.
          if (s.param === "age" && v && (x.nation === "none" || (n && String(n.era) !== v) || (/^\d+$/.test(x.nation) && ns && !n))) x.nation = "";
          if (x.nation === "none") x.role = "";
        } else {
          x.conds = x.conds.filter((c) => !ownedBy(s, c));
          const ch = (s.choices || []).find((c) => c.value === v);
          if (ch) x.conds = [...x.conds, inspParseCond(ch.cond)];
        }
      });
    }

    // ----- condition editor -----
    function opsFor(k) {
      const info = fieldInfo(k), kind = info ? info.kind : "number", common = commonOf(k);
      let ops = INSP_OPS.map((o) => o[0]);
      if (kind === "text") ops = ["eq", "ne", "contains", "has", "none"];
      if (common && common.kind === "choice") ops = kind === "text" ? ["eq", "ne", "has", "none"] : ["eq", "ne", "gte", "lte", "between", "has", "none"];
      return ops;
    }
    function openEditor(k, index, keepOp) {
      editIndex = index;
      edField = k;
      const existing = index >= 0 && d.conds[index] && d.conds[index].field === k ? d.conds[index] : null;
      colIn.value = k;
      const ops = opsFor(k), common = commonOf(k);
      fillKids(opSel, ops.map((o) => el("option", { value: o, text: opWord(o) })));
      opSel.value = existing ? existing.op : keepOp && ops.includes(keepOp) ? keepOp : common && common.kind === "choice" ? "eq" : ops[0];
      drawValues(existing);
      addBtn.textContent = index >= 0 ? "Update filter" : "Add filter";
      cancelBtn.hidden = false;
      condErr.textContent = "";
      const info = fieldInfo(k);
      editorHint.textContent = info ? `${info.kind === "empty" ? "blank in every row" : `${info.kind}, ${info.filled} non-blank`}${info.min !== undefined ? ` · range ${info.min} to ${info.max}` : ""}` : "";
      syncTools();
      const first = valBox.querySelector("input, select");
      (first && !first.disabled ? first : opSel).focus();
    }
    function closeEditor(focusBack) {
      editIndex = -1; edField = "";
      colIn.value = ""; fillKids(opSel); fillKids(valBox); editorHint.textContent = ""; condErr.textContent = "";
      addBtn.textContent = "Add filter"; cancelBtn.hidden = true;
      closeCols();
      syncToolsLight();
      if (focusBack) colIn.focus();
    }
    const syncToolsLight = () => { for (const li of chips.children) li.classList.remove("is-editing"); };
    function drawValues(existing) {
      const op = opSel.value, k = edField, common = commonOf(k), info = fieldInfo(k);
      fillKids(valBox);
      if (!INSP_VALUE_OPS.has(op)) return;
      const numeric = INSP_NUM_OPS.has(op) || (info && info.kind !== "text" && op !== "contains");
      const hint = info && info.min !== undefined ? `${info.min} to ${info.max}` : "value";
      const mk = (id, v, lbl) => {
        if (common && common.kind === "choice" && (op === "eq" || op === "ne")) {
          const s = el("select", { class: "input", id }, el("option", { value: "", text: "Choose a value" }),
            common.choices.map((c) => el("option", { value: c.value, text: `${c.label ? `${c.label} (${c.value})` : c.value} · ${c.count}` })));
          s.value = v || "";
          return [el("label", { for: id, class: "insp-lbl", text: lbl }), s];
        }
        return [el("label", { for: id, class: "insp-lbl", text: lbl }),
          el("input", { class: "input insp-num", id, type: "text", inputmode: numeric ? "decimal" : "text", maxlength: "60", autocomplete: "off", value: v || "", placeholder: numeric ? hint : "text", "aria-describedby": "insp-cond-err" })];
      };
      valBox.append(el("span", { class: "insp-field" }, mk("insp-v1", existing && existing.value, op === "between" ? "From" : "Value")));
      if (op === "between") valBox.append(el("span", { class: "insp-field" }, mk("insp-v2", existing && existing.value2, "to")));
    }
    function submitCond() {
      const k = edField || colIn.value.trim(), op = opSel.value;
      const v1 = valBox.querySelector("#insp-v1"), v2 = valBox.querySelector("#insp-v2");
      const value = v1 ? v1.value.trim() : "", value2 = v2 ? v2.value.trim() : "";
      for (const x of [colIn, v1, v2]) if (x) x.removeAttribute("aria-invalid");
      const fail = (msg, node) => { condErr.textContent = msg; if (node) { node.setAttribute("aria-invalid", "true"); node.focus(); } };
      if (!k || (meta && !fieldInfo(k))) return fail(k ? `No column named "${k}" in ${noun}. Pick one from the list.` : "Choose a column first.", colIn);
      if (!edField) { openEditor(k, editIndex); return; }  // a typed column name: choose its condition next
      if (!op) return fail("Choose a condition.", opSel);
      if (INSP_VALUE_OPS.has(op) && !value) return fail("Enter a value.", v1);
      if (INSP_NUM_OPS.has(op) && !INSP_NUM_RE.test(value)) return fail(`"${value}" is not a number. Use digits, an optional minus sign and decimal point.`, v1);
      if (op === "between" && !INSP_NUM_RE.test(value2)) return fail("Enter a number for the upper bound.", v2);
      if (op === "between" && Number(value2) < Number(value)) return fail("The lower bound is above the upper bound.", v1);
      const cond = { field: k, op, value: INSP_VALUE_OPS.has(op) ? value : "", value2: op === "between" ? value2 : "" };
      const at = editIndex;
      if (at < 0 && d.conds.length >= INSP_MAX_CONDS) return fail(`At most ${INSP_MAX_CONDS} filters. Remove one first.`);
      closeEditor(false);
      change((x) => { x.conds = at >= 0 ? x.conds.map((c, j) => (j === at ? cond : c)) : [...x.conds, cond]; });
      colIn.focus();
    }
    form.addEventListener("submit", (e) => { e.preventDefault(); submitCond(); });
    opSel.addEventListener("change", () => {
      const v1 = valBox.querySelector("#insp-v1"), keep = v1 ? v1.value : "";
      drawValues(null);
      const n1 = valBox.querySelector("#insp-v1");
      if (n1 && keep && n1.tagName === "INPUT") n1.value = keep;
      condErr.textContent = "";
    });

    // Column combobox: filters every column by key or label; arrow keys move, Enter picks, Escape closes.
    let colHits = [], colActive = -1;
    function closeCols() { colList.hidden = true; colIn.setAttribute("aria-expanded", "false"); colIn.removeAttribute("aria-activedescendant"); colActive = -1; }
    function drawCols() {
      if (!meta) { fillKids(colList, el("li", { class: "faint", role: "presentation", text: "Loading columns..." })); colList.hidden = false; colIn.setAttribute("aria-expanded", "true"); return; }
      const t = colIn.value.trim().toLowerCase();
      const all = meta.columns;
      const score = (c) => (c.key.toLowerCase() === t ? 0 : c.key.toLowerCase().startsWith(t) ? 1 : (c.label || "").toLowerCase().startsWith(t) ? 2 : 3);
      const hits = all.filter((c) => !t || c.key.toLowerCase().includes(t) || (c.label || "").toLowerCase().includes(t))
        .sort((a, b) => score(a) - score(b) || (a.kind === "empty") - (b.kind === "empty") || (!!b.label - !!a.label) || a.key.localeCompare(b.key));
      colHits = hits.slice(0, 60);
      colActive = colHits.length ? 0 : -1;
      fillKids(colList, colHits.length ? colHits.map((c, i) => el("li", { id: `insp-col-o${i}`, role: "option", class: "insp-col-opt", "aria-selected": i === colActive ? "true" : "false", "data-key": c.key,
        onmousedown: (e) => e.preventDefault(), onclick: () => pickCol(c.key) },
        el("code", { text: c.key }), c.label ? el("span", { text: c.label }) : null,
        el("span", { class: "faint", text: c.kind === "empty" ? "blank in every row" : `${c.kind} · ${c.filled} filled` })))
        : el("li", { class: "faint", role: "presentation", text: `No column matches "${colIn.value.trim()}".` }),
        hits.length > colHits.length ? el("li", { class: "faint", role: "presentation", text: `${hits.length - colHits.length} more; keep typing to narrow.` }) : null);
      colList.hidden = false;
      colIn.setAttribute("aria-expanded", "true");
      setActive(colActive);
    }
    function setActive(i) {
      colActive = i;
      [...colList.querySelectorAll('[role="option"]')].forEach((o, j) => o.setAttribute("aria-selected", j === i ? "true" : "false"));
      const o = colList.querySelector(`#insp-col-o${i}`);
      if (o) { colIn.setAttribute("aria-activedescendant", o.id); o.scrollIntoView({ block: "nearest" }); } else colIn.removeAttribute("aria-activedescendant");
    }
    // Picking a column while editing a chip changes that chip's column; otherwise it starts a new filter.
    function pickCol(k) { closeCols(); openEditor(k, editIndex, opSel.value); }
    colIn.addEventListener("input", () => { edField = ""; drawCols(); });
    colIn.addEventListener("click", () => { if (colList.hidden) drawCols(); });
    colIn.addEventListener("blur", () => setTimeout(closeCols, 120));
    colIn.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        if (colList.hidden) { drawCols(); return; }
        if (colHits.length) setActive((colActive + (e.key === "ArrowDown" ? 1 : -1) + colHits.length) % colHits.length);
      } else if (e.key === "Enter") {
        if (!colList.hidden && colActive >= 0 && colHits[colActive]) { e.preventDefault(); pickCol(colHits[colActive].key); }
      } else if (e.key === "Escape") {
        if (!colList.hidden) { e.preventDefault(); closeCols(); } else if (edField || colIn.value) { e.preventDefault(); closeEditor(true); }
      }
    });

    // ----- inputs -----
    q.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(() => change((x) => { x.q = q.value; }, { replace: true }), 250);
    });
    q.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && q.value) { clearTimeout(timer); q.value = ""; change((x) => { x.q = ""; }); }
      if (e.key === "Enter") { clearTimeout(timer); if (q.value !== d.q) change((x) => { x.q = q.value; }, { replace: true }); }
      if (e.key === "ArrowDown") { const a = listBox.querySelector("a"); if (a) { e.preventDefault(); a.focus(); } }
    });
    sortSel.addEventListener("change", () => {
      const k = sortSel.value, kind = k === "name" ? "text" : ((fieldInfo(k) || {}).kind || "number");
      // Numbers read best high to low on first choice; ids and names keep ascending.
      change((x) => { x.sort = k; x.order = k !== "id" && kind !== "text" ? "desc" : "asc"; });
    });
    orderBtn.addEventListener("click", () => change((x) => { x.order = x.order === "desc" ? "asc" : "desc"; }));
    perSel.addEventListener("change", () => { const n = Math.min(100, Math.max(1, parseInt(perSel.value, 10) || INSP_PER_PAGE)); state.inspPer = n; change((x) => { x.per = n; }); });

    function loadMeta() {
      inspGet(metaUrl).then((r) => { meta = r; syncTools(); if (last) { drawStatus(); draw(last); } }, (e) => {
        fillKids(simpleBox, errorBox(e, "filter choices"), el("button", { type: "button", class: "btn btn-small", onclick: () => { fillKids(simpleBox); loadMeta(); } }, "Retry"));
      });
    }
    syncTools();
    loadMeta();
    load();
    return { tools, pane, apply, markCurrent };
  }

  // Detail pane: the previous entry stays (dimmed) while the next loads; obsolete requests are cancelled.
  function inspDetail(m, cat) {
    const slug = m.project.slug;
    const node = el("div", { class: "auth-detail insp-detail", id: "insp-detail", "aria-live": "off" });
    let seq = 0, ctrl = null;
    const api = { node, id: null, show };
    function show(id) {
      api.id = id === undefined || id === "" ? null : id;
      const mine = ++seq;
      if (ctrl) ctrl.abort();
      ctrl = null;
      node.classList.remove("is-updating");
      node.removeAttribute("aria-busy");
      if (api.id === null) { fillKids(node, stateBox("empty", "Choose an entry from the list.")); return; }
      if (!/^\d{1,6}$/.test(String(id))) { fillKids(node, stateBox("error", "Not a catalog id.", String(id))); return; }
      const url = `${apiBase(slug)}/inspector/${encodeURIComponent(cat)}/${encodeURIComponent(id)}`;
      ctrl = new AbortController();
      node.setAttribute("aria-busy", "true");
      if (node.querySelector(".insp-body")) node.classList.add("is-updating");
      else fillKids(node, stateBox("loading", "Loading..."));
      inspGet(url, ctrl.signal).then((d) => {
        if (mine !== seq) return;
        node.classList.remove("is-updating");
        node.removeAttribute("aria-busy");
        try {
          const body = cat === "units" ? inspUnit(m, d) : cat === "mercs" ? inspMerc(m, d) : cat === "events" ? inspEvent(m, d)
            : cat === "items" ? inspItem(m, d) : inspGeneric(m, cat, d);
          const tpl = CONTENT_KINDS[cat] ? useAsTemplate(m, cat, d, "btn btn-small") : null;
          fillKids(node, el("div", { class: "stack insp-body" }, body,
            tpl ? el("div", { class: "cross-link" }, tpl, el("span", { class: "faint", text: `Starts a new draft in ${txt(m.project.mod_name || m.project.name || slug)}; nothing is written until you review it.` }))
              : CONTENT_KINDS[cat] ? null : el("p", { class: "faint", text: "Browsing only. Use as template is offered for sites, spells, weapons and armour." }),
            techSection("Raw catalog row", false,
            d.catalog_row ? table(["Catalog column", "Raw value"], Object.entries(d.catalog_row).map(([k, v]) => [el("code", { text: k }), el("code", { text: txt(v) })])) : el("p", { class: "muted", text: "No raw row." })),
            techSection("JSON", false, jsonActions(url, () => d, "Catalog entry JSON"))));
        } catch (e) { fillKids(node, stateBox("error", "This entry failed to render.", String((e && e.message) || e))); }
      }, (e) => {
        if (mine !== seq || inspAborted(e)) return;
        node.classList.remove("is-updating");
        node.removeAttribute("aria-busy");
        fillKids(node, errorBox(e, "the catalog entry"),
          el("div", { class: "btn-row" }, el("button", { type: "button", class: "btn btn-small", onclick: () => { inspCache.delete(url); show(id); } }, "Retry")));
      });
    }
    return api;
  }
  // Data notes and limitations of one entry, collapsed.
  const inspNote = (text) => (text ? techSection("About this data", false, el("p", { class: "faint", text })) : null);
  // Link to a catalog unit with the shared hover / focus preview card.
  function inspUnitLink(m, ref) {
    if (!ref) return el("span", { class: "muted", text: "none" });
    if (ref.in_catalog === false) return el("span", null, `#${ref.id} `, badge("not in catalog", "warn"));
    const a = el("a", { href: inspHref(m.project.slug, "units", ref.id) }, `${txt(ref.name || "unknown unit")} (#${ref.id})`);
    return attachPreview(a, txt(ref.name || `unit ${ref.id}`), (isCurrent) => catalogUnitCard(m, ref.id, isCurrent));
  }
  const inspMercLinks = (m, list) => (list || []).length ? el("p", { class: "sheet-line" }, el("span", { class: "sheet-k", text: "Vanilla mercenary companies:" }), " ",
    list.map((x, i) => [i ? ", " : "", el("a", { href: inspHref(m.project.slug, "mercs", x.id) }, txt(x.name)), el("span", { class: "faint", text: ` (${x.roles.join(", ")})` })])) : null;
  // A catalog unit on the project sheet layout (stats, gear, abilities, magic, sprite), labelled read-only.
  function inspUnit(m, cu) {
    const r = cu.resolved || {}, stats = r.stats || {}, costs = r.costs || {}, eq = r.equipment || {}, nat = cu.nations || [];
    const cols = SHEET_COLS.map((col) => col.map(([k, label]) => [label, k === "leader" ? r.leadership : stats[k]]));
    cols.push([["Map move", stats.mapmove], ["Gold", costs.gold, { mark: "†", text: costText(costs.gold) }], ["Resources", costs.resources, { mark: "†", text: costText(costs.resources) }],
      ["Rec points", costs.recruitment_points, { mark: "†", text: costText(costs.recruitment_points) }]]);
    return el("div", { class: "stack" },
      unitSheet({
        name: cu.name || `Unit ${cu.id}`, type: "Vanilla unit",
        sub: [el("span", { text: `#${cu.id}` })],
        cols,
        gear: el("div", { class: "sheet-gear-wrap" }, sheetGear(eq.weapons, "Weapon", eq.weapons_status), sheetGear(eq.armor, "Armour", eq.armor_status)),
        abilities: sheetAbilities([...Object.entries(r.specials || {}), ...Object.entries(r.creature_traits || {})]),
        magic: r.magic ? sheetMagic(r.magic.paths, r.magic.random) : null,
        lines: [el("p", { class: "sheet-line" }, el("span", { class: "sheet-k", text: "Nations:" }), " ",
          nat.length ? nat.map((x, i) => [i ? "; " : "", el("a", { href: inspHref(m.project.slug, "units", null, { ...inspDefaults(), nation: String(x.id) }) }, `${INSP_AGE_ABBR[x.era] || ""} ${txt(x.name)}`.trim()),
            el("span", { class: "faint", text: ` ${x.how.join(", ")}` })]) : "none"), inspMercLinks(m, cu.mercs)],
        figure: sheetFigure(txt(cu.name), { idle: cu.sprites && cu.sprites.idle, attack: cu.sprites && cu.sprites.attack }),
        note: "Base values before equipment. † Cost component, not the final cost.",
      }),
      (cu.limitations || []).length ? techSection(`Limitations (${cu.limitations.length})`, false, el("ul", null, cu.limitations.map((x) => el("li", { text: x })))) : null);
  }
  // Compact hover card for a catalog unit; the asynchronous fill checks isCurrent() first.
  function catalogUnitCard(m, id, isCurrent) {
    const slug = m.project.slug, box = el("div", null, stateBox("loading", "Reading catalog unit..."));
    catalogUnit(slug, id).then((cu) => {
      if (!isCurrent()) return;
      const r = cu.resolved || {}, st = r.stats || {};
      const cols = [[["HP", st.hp], ["Protection", st.prot], ["Magic res", st.mr], ["Morale", st.mor]],
        [["Strength", st.str], ["Attack", st.att], ["Defence", st.def], ["Precision", st.prec]],
        [["Size", st.size], ["Comb. speed", st.ap], ["Map move", st.mapmove], ["Leadership", r.leadership]]];
      const abil = [...Object.entries(r.specials || {}), ...Object.entries(r.creature_traits || {})];
      fillKids(box,
        el("header", { class: "sheet-head" }, el("div", { class: "sheet-title" }, el("h3", { id: `${PREVIEW_ID}-title`, text: txt(cu.name) }), el("span", { class: "sheet-type", text: "Vanilla unit" })),
          el("div", { class: "sheet-sub", text: `#${cu.id}` })),
        el("div", { class: "sheet-body" },
          el("div", { class: "sheet-main" },
            el("div", { class: "sheet-stats preview-stats" }, cols.map((col) => el("dl", null, col.map(([l, f]) => sheetStat(l, f))))),
            r.magic ? sheetMagic(r.magic.paths, r.magic.random) : null,
            abil.length ? sheetAbilities(abil.slice(0, 10)) : null),
          previewSprite(cu.sprites && cu.sprites.idle ? cu.sprites.idle.url : null, `${txt(cu.name)} idle sprite`, "no sprite in this catalog")),
        el("p", { class: "sheet-note", text: "Base values before equipment." }),
        el("footer", { class: "sheet-foot" }, el("a", { class: "btn btn-small", href: inspHref(slug, "units", cu.id) }, "Open in catalog")));
    }, (e) => { if (isCurrent()) fillKids(box, errorBox(e, "the catalog unit")); });
    return box;
  }
  const meaningRow = (x) => [el("strong", { text: txt(x.label) }),
    el("span", null, el("code", { text: txt(x.value) || "—" }), x.meaning ? el("span", { class: "faint", text: ` ${x.meaning}` }) : null),
    el("span", { class: "faint" }, x.command ? el("code", { text: x.command }) : null, x.note ? ` ${x.note}` : "")];
  function inspMerc(m, d) {
    const slug = m.project.slug, boss = (d.labelled.find((x) => x.key === "bossname") || {}).value;
    const fig = (ref, role) => el("figure", { class: "merc-fig" },
      previewSprite(ref ? catalogSprite(slug, ref.id) : null, ref ? `${txt(ref.name)} sprite` : "", ref ? "no sprite in this catalog" : "none"),
      el("figcaption", null, el("span", { class: "faint", text: `${role}: ` }), inspUnitLink(m, ref)));
    return el("div", { class: "stack" },
      el("section", { class: "panel merc-company" },
        el("h3", { tabindex: "-1", text: `${txt(d.name)} (#${d.id})` }),
        el("p", { class: "panel-note" }, "Led by ", el("strong", { text: txt(boss || "?") })),
        el("div", { class: "merc-figs" }, fig(d.commander, "Commander"), fig(d.troop, "Troops")),
        d.items.length ? el("p", { class: "sheet-line" }, el("span", { class: "sheet-k", text: "Commander items:" }), " ",
          d.items.map((it, i) => [i ? ", " : "", it.id ? el("a", { class: "merc-item", href: inspHref(slug, "items", it.id) }, previewThumb(inspItemIcon(slug, it.id), "No icon"), txt(it.name))
            : el("span", null, txt(it.name), " ", badge("name not in catalog items", "warn"))])) : null,
        table(["Field", "Value", "Manual"], d.labelled.map(meaningRow)),
        inspNote(d.note)));
  }
  function eventTokens(m, list, title) {
    if (!list.length) return panel(title, el("p", { class: "muted", text: "None recorded." }));
    return panel(title, table(["Raw token", "Arguments", "Event manual entry"], list.map((t) => [
      el("code", { text: t.token }),
      el("span", null, el("code", { text: t.args.join(" ") || "—" }), t.unit ? [" ", inspUnitLink(m, t.unit)] : null),
      t.manual ? el("span", null, el("code", { text: `${t.manual.command} ${txt(t.manual.signature)}` }), el("span", { class: "faint", text: ` p.${txt(t.manual.page)}` }))
        : el("span", { class: "faint", text: "no manual command with this name" })])));
  }
  function inspEvent(m, d) {
    return el("div", { class: "stack" },
      el("section", { class: "panel" },
        el("h3", { tabindex: "-1", text: `Event #${d.id}` }),
        el("p", { class: "panel-note" }, "Rarity ", el("code", { text: txt(d.rarity) })),
        el("blockquote", { class: "event-descr", text: d.description || "(no description)" })),
      eventTokens(m, d.requirements, `Requirements (${d.requirements.length})`),
      eventTokens(m, d.effects, `Effects (${d.effects.length})`),
      inspNote([d.name_note, d.note].filter(Boolean).join(" ")));
  }
  function inspItem(m, d) {
    const slug = m.project.slug, val = (k) => (d.labelled.find((x) => x.key === k) || {}).value;
    const facts = [];
    if (val("type")) facts.push(txt((d.labelled.find((x) => x.key === "type") || {}).meaning || val("type")));
    if (val("constlevel")) facts.push(`Construction ${val("constlevel")}`);
    for (const [p, l] of [["mainpath", "mainlevel"], ["secondarypath", "secondarylevel"]]) if (val(p)) facts.push(PATH_NAMES[val(p)] ? pathNamed(val(p), ` ${txt(val(l) || "?")}`) : `${val(p)} ${txt(val(l) || "?")}`);
    return el("div", { class: "stack" },
      el("article", { class: "item-card" },
        el("div", { class: "item-card-head" },
          el("div", { class: "item-card-icon" }, d.icon ? spriteImg(inspItemIcon(slug, d.id), `${txt(d.name)} icon`, 2, el("span", { class: "muted", text: "No icon in this catalog" })) : null),
          el("div", null, el("h2", { tabindex: "-1", text: `${txt(d.name)} (#${d.id})` }), el("p", { class: "faint" }, facts.length ? joinParts(facts) : "No forging data"))),
        table(["Field", "Raw value"], d.labelled.map((x) => [el("strong", { text: x.label }), el("code", { text: txt(x.value) })])),
        inspMercLinks(m, d.mercs),
        inspNote(d.note)));
  }
  function inspGeneric(m, cat, d) {
    const effects = Array.isArray(d.effects) ? d.effects : [];
    const effCols = [...new Set(effects.flatMap((x) => Object.keys(x || {})))];
    const row = d.catalog_row || {};
    const pathLetter = cat === "sites" ? SITE_PATH_LETTER[row.path] : cat === "spells" ? PATH_OF_NUMBER(row.path1) : null;
    return el("div", { class: "stack" },
      el("section", { class: "panel" },
        el("h3", { tabindex: "-1" }, pathLetter ? [pathIcon(pathLetter), " "] : null, `${txt(d.name)} (#${txt(d.id)})`),
        (d.labelled || []).length ? table(["Field", "Value", "Note"], d.labelled.map((x) => [el("strong", { text: txt(x.label) }), el("code", { text: txt(x.value) }), el("span", { class: "faint", text: txt(x.note) })]))
          : el("p", { class: "muted", text: "No labelled values." }),
        d.summon ? el("p", null, "Summons: ", inspUnitLink(m, { id: d.summon.monster_id, name: d.summon.monster_name })) : null,
        inspNote(d.note)),
      effects.length ? techSection("Effect records (raw)", false, table(effCols, effects.map((x) => effCols.map((k) => el("code", { text: x[k] === undefined ? "" : typeof x[k] === "object" ? JSON.stringify(x[k]) : txt(x[k]) }))))) : null);
  }

  // ---------- mercenary companies (#newmerc, manual p.63) ----------
  // GET .../mercs lists this project's companies with #com/#unit/#item names resolved against project and catalog
  // definitions; POST .../mercs previews or appends one structured company through the guarded command writer.
  // Existing companies are edited in the advanced command editor (Edit → Mercenaries).
  const mercUrl = (slug) => `${apiBase(slug)}/mercs`;
  const MERC_INTS = [["nrunits", "Number of troops", "#nrunits"], ["minmen", "Minimum men", "#minmen", "Recruitment of new troops starts below this many (manual p.63)."],
    ["minpay", "Minimum pay (gold)", "#minpay"], ["xp", "Experience", "#xp", "Troops start with this; the commander has twice this amount."],
    ["recrate", "Recruitment rate", "#recrate", "100 means one new troop per month."]];
  // Sprite of a resolved monster: a project monster's own #spr, or the catalog sprite.
  function mercSprite(m, cand) {
    if (!cand) return null;
    if (cand.origin === "catalog") return catalogSprite(m.project.slug, cand.id);
    const u = m.monsters.find((x) => (Number.isInteger(cand.id) ? x.id === cand.id : x.source && `monster:line:${x.source.line}` === cand.key));
    return u && u.sprites && u.sprites.idle ? u.sprites.idle.url : null;
  }
  function mercRef(m, res) {
    if (!res) return el("span", { class: "muted", text: "not set" });
    const c = res.candidates && res.candidates[0];
    const written = el("code", { text: typeof res.written === "string" ? `"${res.written}"` : txt(res.written) });
    if (res.status === "resolved" && c) {
      const label = `${txt(c.name)}${Number.isInteger(c.id) ? ` (#${c.id})` : ""}`;
      const link = c.origin === "project" ? (Number.isInteger(c.id) ? el("a", { href: route("p", m.project.slug, "units", c.id) }, label) : el("span", { text: label }))
        : inspUnitLink(m, { id: c.id, name: c.name });
      return el("span", null, link, " ", badge(c.origin === "project" ? "project" : "vanilla", c.origin === "project" ? "copper" : "info"));
    }
    if (res.status === "ambiguous") return el("span", null, written, " ", badge(`${res.candidate_count} share this name`, "warn"));
    if (res.status === "number") return el("span", null, written, " ", badge("number; the manual documents a name", "warn"));
    return el("span", null, written, " ", badge("unresolved", "err"));
  }
  function mercCard(m, st, c) {
    const slug = m.project.slug, f = c.fields || {};
    const lead = c.commander && c.commander.status === "resolved" ? c.commander.candidates[0] : null;
    const troop = c.troop && c.troop.status === "resolved" ? c.troop.candidates[0] : null;
    const facts = [f.level !== undefined ? `Level ${f.level}` : null, f.eramask !== undefined ? `Era mask ${f.eramask}` : null,
      f.minpay !== undefined ? `min pay ${f.minpay} gold` : null].filter(Boolean);
    return el("article", { class: "item-card merc-card", "aria-label": txt(c.name || "mercenary company") },
      el("div", { class: "item-card-head" },
        el("div", { class: "merc-thumbs" }, previewThumb(mercSprite(m, lead), lead ? "No sprite" : "Commander unresolved"), troop ? previewThumb(mercSprite(m, troop), "No sprite") : null),
        el("div", null, el("h2", { text: c.name || "(unnamed company)" }),
          el("p", { class: "faint", text: `${f.bossname ? `Led by ${f.bossname} · ` : ""}${facts.join(" · ")}` }),
          c.closed ? null : el("p", null, badge("no #end", "err")))),
      el("dl", { class: "kv merc-kv" },
        el("dt", { text: "Commander" }), el("dd", null, mercRef(m, c.commander)),
        el("dt", { text: "Troops" }), el("dd", null, c.troop ? [`${txt(f.nrunits ?? "?")} × `, mercRef(m, c.troop)] : el("span", { class: "muted", text: "none (commander only)" })),
        f.minmen !== undefined || f.recrate !== undefined ? [el("dt", { text: "Replenishing" }), el("dd", { text: `below ${txt(f.minmen ?? "?")} men, rate ${txt(f.recrate ?? "?")}` })] : null,
        f.xp !== undefined ? [el("dt", { text: "Experience" }), el("dd", { text: txt(f.xp) })] : null,
        f.randequip !== undefined ? [el("dt", { text: "Random equipment" }), el("dd", { text: txt(f.randequip) })] : null,
        c.items.length ? [el("dt", { text: "Items" }), el("dd", null, c.items.map((it, i) => {
          const ic = it.status === "resolved" && it.candidates[0];
          return [i ? ", " : "", ic && ic.origin === "catalog" ? el("a", { class: "merc-item", href: inspHref(slug, "items", ic.id) }, previewThumb(inspItemIcon(slug, ic.id), "No icon"), txt(ic.name))
            : el("span", null, txt(it.written), " ", it.status === "resolved" ? badge("project", "copper") : badge(it.status, "warn"))];
        }))] : null),
      c.other_commands.length ? el("p", { class: "faint", text: `${c.other_commands.length} other line(s) kept as written: ${c.other_commands.map((x) => x.command).join(", ")}` }) : null,
      el("div", { class: "btn-row" }, srcRef(slug, st.dm, c.line),
        CSRF ? el("a", { class: "btn btn-small", href: cmdRoute(slug, "merc", c.key), "aria-label": `Advanced edit of ${txt(c.name || "this company")}: raw command lines` }, "Advanced edit") : null));
  }
  function viewMercs(m, arg) {
    const slug = m.project.slug;
    if (arg === "~new") return CSRF ? asyncView(mercUrl(slug), "mercenary options", (st) => mercForm(m, st)) : noToken();
    return asyncView(mercUrl(slug), "mercenary companies", (st) => {
      const list = st.companies || [];
      // New company sits in the section's Browse/Edit bar.
      const head = el("div", { class: "btn-row" },
        el("a", { class: "btn btn-small btn-ghost", href: inspHref(slug, "mercs") }, "Vanilla companies"));
      const clears = (st.clearmercs_lines || []).length ? stateBox("empty", "This mod removes all vanilla mercenary bands.",
        el("span", null, el("code", { text: "#clearmercs" }), " at ", st.clearmercs_lines.map((l, i) => [i ? ", " : "", srcRef(slug, st.dm, l)]), " (manual p.63).")) : null;
      return el("div", { class: "stack" }, head, clears,
        list.length ? [el("p", { class: "faint", role: "status", text: `${list.length} compan${list.length === 1 ? "y" : "ies"}` }),
          el("div", { class: "item-grid" }, list.map((c) => mercCard(m, st, c)))]
          : stateBox("empty", "No mercenary companies in this project.", "Optional. Use New company to hire project or vanilla monsters."),
        techSection(`Notes (${(st.notes || []).length})`, false, el("ul", null, (st.notes || []).map((x) => el("li", { text: x })))));
    });
  }
  // One reference picker: project definitions in a select, catalog entries through the inspector search.
  // get() returns the current pick or null; set(pick) stores one ({origin, id|key, name}). Picking never writes.
  function mercPicker(m, o) {
    const slug = m.project.slug, idp = o.idp, kind = o.kind;
    const shown = el("div", { class: "merc-picked", "aria-live": "polite" });
    const drawShown = () => {
      const c = o.get();
      if (!c) { fillKids(shown, el("span", { class: "faint", text: o.required ? `Required: choose a ${kind}.` : "None chosen." })); return; }
      const src = kind === "monster" ? mercSprite(m, c) : c.origin === "catalog" ? inspItemIcon(slug, c.id) : null;
      fillKids(shown, previewThumb(src, "No image"),
        el("span", null, el("strong", { text: txt(c.name) }), ` ${c.origin === "catalog" ? `vanilla #${c.id}` : Number.isInteger(c.id) ? `project #${c.id}` : `project, line ${txt(c.key).split(":").pop()}`}`,
          c.shared > 1 ? [" ", badge(`${c.shared} share this name`, "warn")] : null),
        o.required ? null : el("button", { type: "button", class: "btn btn-small btn-ghost", "aria-label": `Clear ${o.label}`, onclick: () => { o.set(null); drawShown(); } }, "Clear"));
    };
    const opts = o.options || [];
    const projSel = el("select", { class: "input", id: `${idp}-proj` }, el("option", { value: "", text: opts.length ? `Project ${kind}s (${opts.length})` : `No named project ${kind}s` }),
      opts.map((x) => el("option", { value: x.key, text: `${txt(x.name)}${Number.isInteger(x.id) ? ` (#${x.id})` : ` (line ${x.line})`}` })));
    projSel.disabled = !opts.length;
    const cur = o.get();
    if (cur && cur.origin === "project") projSel.value = cur.key;
    projSel.addEventListener("change", () => {
      const x = opts.find((y) => y.key === projSel.value);
      if (x) { o.set({ origin: "project", key: x.key, id: x.id, name: x.name, shared: x.name_shared_by }); drawShown(); }
    });
    const q = el("input", { class: "input", type: "search", id: `${idp}-q`, maxlength: "60", autocomplete: "off", placeholder: `Vanilla ${kind} name or id` });
    const results = el("div", { class: "merc-results", "aria-live": "polite" });
    let seq = 0, timer = 0;
    const search = () => {
      const t = q.value.trim(), mine = ++seq;
      if (!t) { fillKids(results); return; }
      fillKids(results, stateBox("loading", "Searching the catalog..."));
      inspGet(`${apiBase(slug)}/inspector/${kind === "monster" ? "units" : "items"}?per_page=12&q=${encodeURIComponent(t)}`).then((r) => {
        if (mine !== seq) return;
        fillKids(results, r.results.length ? el("ul", { class: "donor-list merc-hits", "aria-label": `Catalog ${kind}s` }, r.results.map((x) => el("li", null,
          el("button", { type: "button", class: "btn btn-small", onclick: () => { o.set({ origin: "catalog", id: x.id, name: x.name }); projSel.value = ""; q.value = ""; fillKids(results); drawShown(); q.focus(); } },
            previewThumb(kind === "monster" ? catalogSprite(slug, x.id) : inspItemIcon(slug, x.id), "No image"), `${x.name} (#${x.id})`))))
          : el("p", { class: "muted", text: `No vanilla ${kind}s match.` }),
          r.matches > r.results.length ? el("p", { class: "faint", text: `Showing ${r.results.length} of ${r.matches}; refine the search.` }) : null);
      }, (e) => { if (mine === seq) fillKids(results, errorBox(e, `catalog ${kind}s`)); });
    };
    q.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(search, 250); });
    q.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); clearTimeout(timer); search(); } });
    drawShown();
    return el("div", { class: "edit-field wide merc-pick", role: "group", "aria-labelledby": `${idp}-l` },
      el("span", { class: "lbl", id: `${idp}-l`, text: `${o.label}${o.required ? "" : " (optional)"}` }), shown,
      el("div", { class: "merc-pick-row" }, el("label", { for: projSel.id, class: "sr-only", text: `${o.label}: project ${kind}` }), projSel,
        el("label", { for: q.id, class: "sr-only", text: `${o.label}: search vanilla ${kind}s` }), q),
      results,
      catalogOf(m) ? null : el("p", { class: "faint", text: "No catalog for this project: only project definitions can be chosen." }));
  }
  function mercForm(m, st) {
    const slug = m.project.slug, dkey = `${slug}:merc:~new`, o = st.options || {}, maxItems = o.max_items || 4;
    const dr = authDraft(dkey, { form: { name: "", bossname: "", commander: null, troop: null, items: [], nrunits: "", minmen: "", minpay: "", xp: "", recrate: "", randequip: "", level: "", eramask: "" } });
    const f = dr.form;
    const holder = el("section", { class: "panel editor creator", "aria-labelledby": "merc-h" });
    const reload = () => { state.authData.delete(mercUrl(slug)); dr.msg = null; render(); };
    const cancel = () => { state.authoring.delete(dkey); location.hash = route("p", slug, "mercs"); };
    const intOf = (v) => (String(v ?? "").trim() === "" ? undefined : Number(v));
    function problems() {
      const out = [];
      if (!f.name.trim()) out.push("Enter a company name.");
      if (!f.bossname.trim()) out.push("Enter the boss name.");
      if ([f.name, f.bossname].some((x) => x.includes('"'))) out.push("Names cannot contain double quotes.");
      if (!f.commander) out.push("Choose a commander.");
      for (const [k, l] of MERC_INTS) { const v = String(f[k] ?? "").trim(); if (v && !/^\d+$/.test(v)) out.push(`${l}: whole numbers only.`); }
      if (!f.troop && intOf(f.nrunits)) out.push("Choose a troop type, or leave the number of troops empty.");
      if (f.items.length > maxItems) out.push(`At most ${maxItems} items.`);
      return out;
    }
    const refOf = (c) => (c.origin === "catalog" ? { origin: "catalog", id: c.id } : { origin: "project", key: c.key });
    function company() {
      const c = { name: f.name.trim(), bossname: f.bossname.trim(), commander: refOf(f.commander) };
      if (f.troop) c.troop = refOf(f.troop);
      for (const k of ["nrunits", "minmen", "minpay", "xp", "recrate", "randequip", "level", "eramask"]) if (intOf(f[k]) !== undefined) c[k] = intOf(f[k]);
      if (f.items.length) c.items = f.items.map(refOf);
      return c;
    }
    const countBox = statusLine("");
    let reviewBtn = null;
    const refresh = () => { const p = problems(); countBox.textContent = p.length ? `${p.length} to fix before review: ${p[0]}` : "Ready to review."; if (reviewBtn) reviewBtn.disabled = !!p.length; };
    const edited = () => { dr.msg = null; dr.preview = null; refresh(); };
    const pick = (key, label, kind, required) => mercPicker(m, { idp: `merc-${key}`, label, kind, required, options: kind === "monster" ? o.monsters : o.items,
      get: () => f[key], set: (v) => { f[key] = v; edited(); } });
    const textField = (k, label, hint) => labelled(`merc-${k}`, label, bindInput(el("input", { class: "input", id: `merc-${k}`, value: f[k], maxlength: "200", autocomplete: "off",
      "aria-describedby": hint ? `merc-${k}-hint` : null }), dr, k, edited), hint);
    const numField = (k, label, cmd, hint) => labelled(`merc-${k}`, `${label} (${cmd})`, bindInput(el("input", { class: "input num-input", id: `merc-${k}`, value: f[k], inputmode: "numeric",
      autocomplete: "off", "aria-describedby": `merc-${k}-hint` }), dr, k, edited), hint || "Optional; empty leaves the game default.");
    const choiceField = (k, label, cmd, list, hint) => {
      const s = el("select", { class: "input", id: `merc-${k}`, "aria-describedby": `merc-${k}-hint` }, el("option", { value: "", text: "Not set (game default)" }),
        (list || []).map((x) => el("option", { value: String(x.value), text: x.label })));
      s.value = String(f[k] ?? "");
      return labelled(`merc-${k}`, `${label} (${cmd})`, bindInput(s, dr, k, edited), hint);
    };
    function itemsGroup() {
      const list = el("ul", { class: "plain-list merc-items" }, f.items.map((it, i) => el("li", null, previewThumb(it.origin === "catalog" ? inspItemIcon(slug, it.id) : null, "No icon"),
        el("span", { text: ` ${txt(it.name)} ${it.origin === "catalog" ? `(vanilla #${it.id})` : "(project)"} ` }),
        el("button", { type: "button", class: "btn btn-small btn-ghost", "aria-label": `Remove ${txt(it.name)}`, onclick: () => { f.items.splice(i, 1); edited(); redraw("#merc-item-q"); } }, "Remove"))));
      const adder = f.items.length < maxItems ? mercPicker(m, { idp: "merc-item", label: "Add an item", kind: "item", required: false, options: o.items,
        get: () => null, set: (v) => { if (v) { f.items.push(v); edited(); redraw("#merc-item-q"); } } })
        : el("p", { class: "faint", text: `The manual allows at most ${maxItems} items per band.` });
      return el("fieldset", { class: "edit-group" }, el("legend", { text: `Commander items (#item, ${f.items.length} of ${maxItems})` }),
        f.items.length ? list : el("p", { class: "faint", text: "No items (optional)." }), adder);
    }
    function redraw(focusSel) {
      const head = el("h3", { id: "merc-h", tabindex: "-1", text: "New mercenary company" });
      const busy = dr.msg && dr.msg.kind === "busy" ? stateBox("loading", dr.msg.text) : null;
      const err = dr.msg && dr.msg.kind === "err" ? writeError(dr.msg.err, reload) : null;
      if (dr.phase === "review" && dr.preview) {
        const r = dr.preview, rv = r.resolved || {};
        const written = [`Commander written as "${txt(rv.commander && rv.commander.name)}"`, rv.troop ? `troops as "${txt(rv.troop.name)}"` : null,
          ...(rv.items || []).map((x) => `item "${txt(x.name)}"`)].filter(Boolean).join("; ") + ".";
        fillKids(holder, head, busy, err,
          reviewBlock({ ...r, explanation: [...(r.explanation || []), written] }, "Create company",
            () => runWrite(dr, mercUrl(slug), { expected_sha256: st.sha256, company: company() }, false, redraw, (res) => {
              state.authoring.delete(dkey); invalidateAuth(slug);
              afterWrite(slug, route("p", slug, "mercs"), "Mercenary company saved. Backup kept.", res || {}, `Created mercenary company ${txt(dr.form && dr.form.name) || ""}`.trim());
            }), () => { dr.phase = "edit"; dr.preview = null; redraw(REVIEW_TRIGGER); }));
        focusIn(holder, focusSel);
        return;
      }
      reviewBtn = el("button", { type: "submit", class: "btn", ...RT }, "Review new company");
      fillKids(holder, head, err, busy,
        el("p", { class: "panel-note" }, "Adds one ", el("code", { text: "#newmerc" }), " block to the end of the .dm. Commander, troops and items are written by name. New monsters it uses need their own artwork."),
        el("form", { class: "edit-form", novalidate: true, onsubmit: (e) => { e.preventDefault(); if (!problems().length) runWrite(dr, mercUrl(slug), { expected_sha256: st.sha256, company: company() }, true, redraw); } },
          el("fieldset", { class: "edit-group" }, el("legend", { text: "Company" }),
            el("div", { class: "grid-2" }, textField("name", "Company name (#name)"), textField("bossname", "Boss name (#bossname)", "Name of the band's leader."))),
          el("fieldset", { class: "edit-group" }, el("legend", { text: "Leader and troops" }),
            pick("commander", "Commander (#com)", "monster", true),
            pick("troop", "Troop type (#unit)", "monster", false),
            el("div", { class: "grid-2" }, MERC_INTS.map(([k, l, c, h]) => numField(k, l, c, h)))),
          el("fieldset", { class: "edit-group" }, el("legend", { text: "Availability and equipment" }),
            el("div", { class: "grid-2" }, choiceField("level", "Level", "#level", o.levels, "When the band appears (manual p.63)."),
              choiceField("eramask", "Era mask", "#eramask", o.eramasks, "Default: all eras."),
              choiceField("randequip", "Random equipment", "#randequip", o.randequip, "How powerful the commander's random magic equipment is."))),
          itemsGroup(),
          el("div", { class: "btn-row edit-actions" }, reviewBtn, el("button", { type: "button", class: "btn btn-ghost", onclick: cancel }, "Cancel"), countBox)),
        el("p", { class: "faint" }, "Other lines, or changes to an existing company: ", el("a", { href: cmdRoute(slug, "merc") }, "advanced mercenary editor"), " (keeps unknown lines as written)."));
      refresh();
      focusIn(holder, focusSel);
    }
    escapeReview(holder, () => dr.phase === "review", () => { dr.phase = "edit"; redraw(REVIEW_TRIGGER); });
    redraw(dr.msg && dr.msg.kind === "err" ? "[data-focus=err]" : null);
    return el("div", { class: "stack" }, el("p", null, el("a", { href: route("p", slug, "mercs") }, "← Mercenary companies")), holder);
  }

  // ---------- preview cards (one shared, bounded hover / focus card) ----------
  // Mouse hover (after a short delay) or keyboard focus on a trigger shows a compact card; the pointer can cross into it.
  // A Preview button pins the card for touch and keyboard users and moves focus into it. Escape, the close button or a
  // click elsewhere dismisses it and returns focus. One card element with fixed ids is reused, so previews never add
  // duplicate ids; every opening takes a new token and builders drop asynchronous results whose token is stale.
  const PREVIEW_ID = "kosmo-preview";
  const pv = { card: null, trigger: null, pinned: false, token: 0, showTimer: 0, hideTimer: 0, suppress: null };
  function previewCard() {
    if (pv.card) return pv.card;
    const c = el("div", { class: "preview-pop unit-sheet", id: PREVIEW_ID, role: "dialog", "aria-labelledby": `${PREVIEW_ID}-title`, tabindex: "-1", hidden: true });
    c.addEventListener("pointerenter", () => clearTimeout(pv.hideTimer));
    c.addEventListener("pointerleave", (e) => { if (e.pointerType === "mouse" && !pv.pinned) schedHidePreview(); });
    c.addEventListener("load", placePreview, true);
    c.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); hidePreview(true); return; }
      if (e.key !== "Tab") return;
      // Tabbing past either end of the card closes it and returns to the trigger, so focus never strands at the page end.
      const f = [...c.querySelectorAll("a[href], button:not([disabled])")];
      const atEnd = !f.length || (e.shiftKey ? document.activeElement === f[0] || document.activeElement === c : document.activeElement === f[f.length - 1]);
      if (atEnd) { e.preventDefault(); hidePreview(true); }
    });
    c.addEventListener("focusout", (e) => { if (!c.hidden && !c.contains(e.relatedTarget) && e.relatedTarget !== pv.trigger) hidePreview(false); });
    pv.card = c;
    document.body.append(c);
    return c;
  }
  function placePreview() {
    const c = pv.card, t = pv.trigger;
    if (!c || c.hidden || !t) return;
    if (!t.isConnected) { hidePreview(false); return; }
    const r = t.getBoundingClientRect(), de = document.documentElement, vw = de.clientWidth, vh = de.clientHeight, gap = 8;
    // A hover card follows its trigger; once the trigger scrolls out of view it closes (a pinned card stays, clamped).
    if (!pv.pinned && (r.bottom < 0 || r.top > vh)) { hidePreview(false); return; }
    c.style.maxWidth = `${Math.max(0, vw - 2 * gap)}px`;
    c.style.maxHeight = `${Math.max(120, vh - 2 * gap)}px`;
    const w = c.offsetWidth, h = c.offsetHeight;
    const left = Math.max(gap, Math.min(r.left, vw - w - gap));
    let top = r.bottom + 6;
    if (top + h > vh - gap) top = r.top - h - 6 >= gap ? r.top - h - 6 : Math.max(gap, vh - h - gap);
    c.style.left = `${Math.round(left)}px`; c.style.top = `${Math.round(top)}px`;
  }
  function schedHidePreview() { clearTimeout(pv.hideTimer); pv.hideTimer = setTimeout(() => hidePreview(false), 250); }
  function hidePreview(returnFocus) {
    clearTimeout(pv.showTimer); clearTimeout(pv.hideTimer);
    pv.token++;
    const c = pv.card, t = pv.trigger;
    pv.trigger = null; pv.pinned = false;
    if (t && t.hasAttribute("aria-expanded")) t.setAttribute("aria-expanded", "false");
    if (!c || c.hidden) return;
    const hadFocus = c.contains(document.activeElement);
    c.hidden = true;
    c.replaceChildren();
    if ((returnFocus || hadFocus) && t && t.isConnected) { pv.suppress = t; t.focus({ preventScroll: true }); }
  }
  // build(isCurrent) returns the card body; asynchronous parts must check isCurrent() before touching the DOM.
  function showPreview(trigger, name, build, pinned) {
    clearTimeout(pv.showTimer); clearTimeout(pv.hideTimer);
    if (pv.trigger && pv.trigger !== trigger && pv.trigger.hasAttribute("aria-expanded")) pv.trigger.setAttribute("aria-expanded", "false");
    const c = previewCard(), token = ++pv.token;
    const isCurrent = () => pv.token === token && !c.hidden && pv.trigger === trigger;
    pv.trigger = trigger; pv.pinned = !!pinned;
    if (trigger.hasAttribute("aria-expanded")) trigger.setAttribute("aria-expanded", "true");
    let body;
    try { body = build(isCurrent); } catch (e) { body = stateBox("error", "Preview unavailable.", String(e && e.message || e)); }
    c.setAttribute("aria-label", `Preview: ${name}`);
    fillKids(c, el("button", { type: "button", class: "btn btn-small btn-ghost preview-close", "aria-label": "Close preview", title: "Close (Esc)",
      onclick: () => hidePreview(true) }, "×"), body);
    c.removeAttribute("aria-labelledby");
    if (c.querySelector(`#${PREVIEW_ID}-title`)) { c.removeAttribute("aria-label"); c.setAttribute("aria-labelledby", `${PREVIEW_ID}-title`); }
    c.hidden = false;
    c.scrollTop = 0;
    placePreview();
    if (pinned) c.focus({ preventScroll: true });
  }
  // Hover and focus preview on an existing name element (link or text). A pinned card is not replaced by hovering elsewhere.
  function attachPreview(trigger, name, build) {
    previewCard();
    trigger.classList.add("has-preview");
    trigger.addEventListener("pointerenter", (e) => {
      if (e.pointerType !== "mouse" || pv.pinned) return;
      clearTimeout(pv.hideTimer);
      if (pv.trigger === trigger) return;
      clearTimeout(pv.showTimer);
      pv.showTimer = setTimeout(() => { if (trigger.isConnected && !pv.pinned) showPreview(trigger, name, build, false); }, 350);
    });
    trigger.addEventListener("pointerleave", (e) => {
      if (e.pointerType !== "mouse") return;
      clearTimeout(pv.showTimer);
      if (pv.trigger === trigger && !pv.pinned) schedHidePreview();
    });
    trigger.addEventListener("focus", () => {
      if (pv.suppress === trigger) { pv.suppress = null; return; }
      if (!pv.pinned && trigger.matches(":focus-visible")) showPreview(trigger, name, build, false);
    });
    trigger.addEventListener("blur", (e) => {
      clearTimeout(pv.showTimer);
      if (pv.trigger === trigger && !pv.pinned && !(pv.card && pv.card.contains(e.relatedTarget))) hidePreview(false);
    });
    return trigger;
  }
  // Explicit, touch- and keyboard-friendly control: toggles a pinned card and moves focus into it.
  function previewButton(name, build) {
    previewCard();
    const b = el("button", { type: "button", class: "btn btn-small btn-ghost preview-btn", "aria-expanded": "false", "aria-controls": PREVIEW_ID,
      "aria-label": `Preview ${name}`, text: "Preview" });
    b.addEventListener("click", () => { if (pv.trigger === b && pv.card && !pv.card.hidden) hidePreview(true); else showPreview(b, name, build, true); });
    return b;
  }
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && pv.card && !pv.card.hidden && !pv.card.contains(e.target)) hidePreview(false); });
  document.addEventListener("pointerdown", (e) => {
    if (!pv.card || pv.card.hidden || pv.card.contains(e.target) || (pv.trigger && pv.trigger.contains(e.target))) return;
    hidePreview(false);
  });
  window.addEventListener("scroll", placePreview, { capture: true, passive: true });
  window.addEventListener("resize", placePreview, { passive: true });
  window.addEventListener("hashchange", () => hidePreview(false));

  // Small sprite thumbnail on the sheet stage colour; a missing or failed sprite shows a labelled placeholder.
  function previewThumb(src, missing) {
    const box = el("span", { class: "pv-thumb" });
    const none = (why) => el("span", { class: "pv-thumb-none", title: why, "aria-hidden": "true", text: "–" });
    if (!src) { box.append(none(missing)); return box; }
    const img = el("img", { src, alt: "", loading: "lazy", decoding: "async", draggable: "false" });
    img.addEventListener("error", () => img.replaceWith(none("Sprite unavailable")), { once: true });
    box.append(img);
    return box;
  }
  // Sprite shown crisp: pixel art at or under 48 px is doubled, larger art stays native (CSS caps the width).
  function previewSprite(src, alt, missing) {
    const stage = el("div", { class: "sheet-stage preview-stage" });
    if (!src) { stage.append(el("div", { class: "preview-missing", text: missing })); return stage; }
    const img = spriteImg(src, alt, 0, el("div", { class: "preview-missing", text: "sprite unavailable" }));
    img.addEventListener("load", () => { const s = img.naturalWidth <= 48 && img.naturalHeight <= 48 ? 2 : 1; img.width = img.naturalWidth * s; img.height = img.naturalHeight * s; });
    stage.append(img);
    return stage;
  }
  const projectMonster = (m, bu) => m.monsters.find((x) => x.uid === bu.uid) || (Number.isInteger(bu.id) ? m.monsters.find((x) => x.id === bu.id) : null) || null;
  const catalogSprite = (slug, id, frame) => `${apiBase(slug)}/catalog-units/${id}/sprite/${frame || "idle"}`;
  // Idle sprite URL for a balance unit: the project's #spr asset or the catalog's sprite; null when there is none to ask for.
  function unitSpriteSrc(m, bu, project) {
    if (!project) return Number.isInteger(bu.id) ? catalogSprite(m.project.slug, bu.id) : null;
    const mo = projectMonster(m, bu);
    return mo && mo.sprites && mo.sprites.idle ? mo.sprites.idle.url : null;
  }
  const unitThumb = (m, bu, project) => previewThumb(unitSpriteSrc(m, bu, project), project ? "No sprite command" : "No catalog id");
  const clip = (s, n) => { const t = txt(s).trim(); return t.length > n ? `${t.slice(0, n - 1).trimEnd()}…` : t; };
  // Compact unit card from a balance unit (bu); project units add their full resolved block. Values are the report's own:
  // "?" marks a value the static model did not resolve, never a guessed one.
  function unitPreview(m, bu, project, isCurrent) {
    const slug = m.project.slug, mo = project ? projectMonster(m, bu) : null, r = mo ? mo.resolved : null;
    const st = bu.stats || {}, name = txt(bu.name) || "(unnamed)";
    const cols = [[["HP", st.hp], ["Protection", st.prot], ["Magic res", st.mr], ["Morale", st.mor]],
      [["Strength", st.str], ["Attack", st.att], ["Defence", st.def], ["Precision", st.prec]],
      [["Size", st.size], ["Comb. speed", st.ap], ["Map move", st.mapmove]]];
    const lead = project ? sheetStat("Leadership", r ? r.leadership : null) : sheetStat("Leadership", null, { text: "…", note: "Reading catalog data" });
    if (!project && Number.isInteger(bu.id)) {
      catalogUnit(slug, bu.id).then((cu) => { if (isCurrent()) lead[1].replaceWith(sheetStat("Leadership", cu.resolved && cu.resolved.leadership)[1]); },
        () => { if (isCurrent()) lead[1].replaceWith(sheetStat("Leadership", null)[1]); });
    }
    const unknown = Object.values(st).filter((f) => !f || f.value === null || f.value === undefined).length;
    const cost = (k, label) => {
      const raw = (bu.raw_costs || {})[k], e = estText((bu.cost_estimates || {})[k]);
      return el("span", { title: [raw && raw.note, (bu.cost_estimates || {})[k] && bu.cost_estimates[k].note].filter(Boolean).join(". ") || null },
        el("span", { class: "sheet-k" }, statIcon(k === "recruitment_points" && bu.role === "commander" ? "commander_points" : k), `${label} `), `${costText(raw)}†`, e ? el("span", { class: "bal-est", text: ` ${e}` }) : null);
    };
    const prot = estText(bu.protection);
    const abil = [...Object.entries((r ? r.specials : bu.specials) || {}), ...Object.entries((r ? r.creature_traits : bu.creature_traits) || {})];
    const eq = bu.equipment || {};
    const gearUnresolved = (eq.weapons_status && eq.weapons_status.status === "unresolved") || (eq.armor_status && eq.armor_status.status === "unresolved");
    const gaps = [
      unknown ? `${unknown} base stat${unknown === 1 ? "" : "s"} unresolved` : null,
      gearUnresolved ? "equipment list unresolved" : null,
      mo && mo.donor && mo.donor.resolved === false ? "donor unresolved: inherited values incomplete" : null,
      mo && (mo.unsupported || []).length ? `${mo.unsupported.length} command(s) not modelled` : null].filter(Boolean);
    const sprite = unitSpriteSrc(m, bu, project);
    const role = { troop: "Troop", commander: "Commander" }[bu.role] || txt(bu.role);
    return [
      el("header", { class: "sheet-head" },
        el("div", { class: "sheet-title" }, el("h3", { id: `${PREVIEW_ID}-title`, text: name }), el("span", { class: "sheet-type", text: role })),
        el("div", { class: "sheet-sub" }, `#${txt(bu.id ?? bu.uid)} · `, project ? "this project" : "catalog (read-only)", ` · ${balWhere(bu)}`)),
      el("div", { class: "sheet-body" },
        el("div", { class: "sheet-main" },
          el("div", { class: "sheet-stats preview-stats" }, cols.map((col, i) => el("dl", null, col.map(([l, f]) => sheetStat(l, f)), i === 2 ? lead : null))),
          el("p", { class: "sheet-line preview-costs" }, cost("gold", "Gold"), " · ", cost("resources", "Res"), " · ", cost("recruitment_points", "RP")),
          prot ? el("p", { class: "sheet-line", title: txt(bu.protection.note) || null }, el("span", { class: "sheet-k" }, statIcon("prot"), "Protection with gear:"), ` ${prot}`) : null,
          el("div", { class: "sheet-line" }, el("span", { class: "sheet-k", text: "Equipment: " }), balGear(bu)),
          r ? sheetMagic(r.magic.paths, r.magic.random) || el("p", { class: "sheet-line" }, el("span", { class: "sheet-k", text: "Magic paths:" }), " none")
            : el("p", { class: "sheet-line" }, el("span", { class: "sheet-k", text: "Magic paths:" }), " ", balMagic(bu)),
          abil.length ? [sheetAbilities(abil.slice(0, 10)), abil.length > 10 ? el("p", { class: "sheet-line faint", text: `+${abil.length - 10} more on the full sheet` }) : null] : null),
        previewSprite(sprite, `${name} idle sprite`, project ? "no sprite command" : "no catalog id")),
      mo && mo.description ? el("div", { class: "sheet-descr" }, el("p", { text: clip(mo.description, 280) })) : null,
      gaps.length ? el("p", { class: "sheet-note preview-gaps" }, badge("incomplete", "warn"), ` ${gaps.join("; ")}.`) : null,
      el("p", { class: "sheet-note", text: `Base values before equipment; "?" is unresolved, not zero. † raw cost component; ≈ estimate.${project ? " Underlined = set in this .dm." : " Catalog data via the browser resolver; it may differ from the installed game."}` }),
      el("footer", { class: "sheet-foot" },
        project && mo ? el("a", { class: "btn btn-small", href: route("p", slug, "units", mo.id ?? mo.uid) }, "Open full unit sheet")
          : Number.isInteger(bu.id) ? el("a", { class: "btn btn-small", href: inspHref(slug, "units", bu.id) }, "Open in catalog") : null)];
  }

  // Project magic items: forging requirements and description from authored commands; other commands are listed as written.
  const ITEM_META_CMDS = new Set(["#newitem", "#selectitem", "#name", "#descr", "#spr", "#constlevel", "#mainpath", "#mainlevel", "#secondarypath", "#secondarylevel", "#type", "#end"]);
  const itemEffects = (d) => (d.authored || []).filter((c) => !ITEM_META_CMDS.has(txt(c.command).toLowerCase()));
  function itemForging(d) {
    const out = [], c = itemArg(d, "constlevel");
    if (c !== null) out.push(`Construction ${c}`);
    // Required paths carry the native path icon when the path number is a known 0-9 path; the name stays visible.
    const req = (path, level) => { const p = PATH_OF_NUMBER(path); return p ? pathNamed(p, ` ${level ?? "?"}`) : `${gemName([], path)} ${level ?? "?"}`; };
    if (itemArg(d, "mainpath") !== null) out.push(req(itemArg(d, "mainpath"), itemArg(d, "mainlevel")));
    if (itemArg(d, "secondarypath") !== null && Number(itemArg(d, "secondarypath")) >= 0) out.push(req(itemArg(d, "secondarypath"), itemArg(d, "secondarylevel")));
    return out;
  }
  // Why some values are not shown: #selectitem keeps unchanged vanilla values, #copyitem copies another item's.
  function itemInherits(d) {
    const copy = itemArg(d, "copyitem");
    if (copy !== null) return `Copies item ${copy}: copied effects are not reconstructed here.`;
    if (/^#selectitem$/i.test(txt(d.opener))) return "Modifies an existing item: unchanged vanilla values are not shown.";
    return null;
  }
  // Vanilla icon from the catalog (images/items/item<id>.png, as the catalog's item view resolves it), used only
  // when the block sets no #spr: #selectitem keeps its item's icon and #copyspr <id> copies another item's.
  function catalogItemIcon(d) {
    if (itemArg(d, "spr") !== null) return null;
    const c = itemArg(d, "copyspr");
    const id = c !== null ? (/^\d{1,4}$/.test(c) ? Number(c) : null) : /^#selectitem$/i.test(txt(d.opener)) && Number.isInteger(d.id) ? d.id : null;
    return id && id > 0 && id < 10000 ? { url: `${iconScope.base}/item-icons/${id}.png`, id } : null;
  }
  const itemIcon = (m, d) => { const assets = itemSpriteAssets(m, d); return { assets, a: assets.find((x) => x.status !== "missing" && x.browser_preview) || null, cat: assets.length ? null : catalogItemIcon(d) }; };
  const itemIconMissing = (assets) => assets.length ? "icon file missing" : "no custom icon (#spr)";
  function itemPreview(m, d) {
    const slug = m.project.slug, name = txt(d.name) || `${d.opener} ${txt(d.id ?? d.selector)}`;
    const { assets, a, cat } = itemIcon(m, d), forge = itemForging(d), fx = itemEffects(d), inh = itemInherits(d), descr = itemArg(d, "descr");
    return [
      el("header", { class: "sheet-head" },
        el("div", { class: "sheet-title" }, el("h3", { id: `${PREVIEW_ID}-title`, text: name }), el("span", { class: "sheet-type", text: itemType(d) || "Slot not authored" })),
        el("div", { class: "sheet-sub" }, el("code", { text: `${d.opener} ${txt(d.id ?? d.selector ?? "")}` }))),
      el("div", { class: "sheet-body" },
        el("div", { class: "sheet-main" },
          el("p", { class: "sheet-line" }, el("span", { class: "sheet-k", text: "Forging:" }), " ", forge.length ? joinParts(forge) : el("span", { class: "muted", text: "not authored" })),
          fx.length ? el("div", null, el("p", { class: "sheet-line" }, el("span", { class: "sheet-k", text: "Authored effects " }), badge("as written, not interpreted", "info")),
            el("ul", { class: "preview-effects" }, fx.slice(0, 12).map((c) => el("li", null, el("code", { text: `${c.command} ${(c.args || []).join(" ")}`.trim() }), " ", statusBadge(c.status)))),
            fx.length > 12 ? el("p", { class: "sheet-line faint", text: `+${fx.length - 12} more in the source block` }) : null)
            : el("p", { class: "sheet-line muted", text: "No effect commands authored in this block." })),
        previewSprite(a ? a.browser_preview : cat ? cat.url : null, `${name} ${a || !cat ? "icon" : `catalog icon #${cat.id}`}`, itemIconMissing(assets))),
      descr ? el("div", { class: "sheet-descr" }, el("p", { text: clip(descr, 320) })) : null,
      inh ? el("p", { class: "sheet-note preview-gaps" }, badge("incomplete", "warn"), ` ${inh}`) : null,
      el("p", { class: "sheet-note", text: "Effects are the block's own commands; the browser does not verify what they do in game." }),
      el("footer", { class: "sheet-foot" }, srcRef(slug, d.source.file, d.source.line, true),
        el("a", { class: "btn btn-small btn-ghost", href: route("p", slug, "items") }, "Open Items"))];
  }
  function balItems(m) {
    const items = otherOfKind(m, "item"), slug = m.project.slug;
    const note = el("div", { class: "panel-note" }, el("p", { text: "All project items, shown as authored." }), el("details", null, el("summary", null, "Details"),
      el("p", { text: "Not filtered by nation. Forging and effects are not interpreted, and values inherited by #selectitem or #copyitem are not reconstructed." })));
    if (!items.length) return techSection("Project magic items (0)", false, stateBox("empty", "No magic items in this project.", "No #newitem / #selectitem blocks were parsed from the .dm."), note);
    return techSection(`Project magic items (${items.length})`, false,
      table(["Item", "Slot", "Forging", "Authored effects", "Source"], items.map((d) => {
        const name = txt(d.name) || `${d.opener} ${txt(d.id ?? d.selector ?? "")}`, { assets, a, cat } = itemIcon(m, d), fx = itemEffects(d), inh = itemInherits(d);
        const build = () => itemPreview(m, d);
        return [
          el("div", { class: "bal-unit" }, attachPreview(previewThumb(a ? a.browser_preview : cat ? cat.url : null, itemIconMissing(assets)), name, build),
            el("span", { class: "bal-name" }, attachPreview(el("strong", { text: name }), name, build), d.id != null || d.selector != null ? el("span", { class: "faint", text: `#${txt(d.id ?? d.selector)}` }) : null,
              previewButton(name, build))),
          itemType(d) || el("span", { class: "muted", text: "—" }),
          itemForging(d).length ? el("span", { class: "bal-inline" }, joinParts(itemForging(d))) : el("span", { class: "muted", text: "not authored" }),
          el("span", null, fx.length ? el("code", { class: "bal-fx", title: fx.map((c) => `${c.command} ${(c.args || []).join(" ")}`).join("\n"),
            text: fx.slice(0, 3).map((c) => txt(c.command)).join(", ") + (fx.length > 3 ? ` +${fx.length - 3}` : "") }) : el("span", { class: "muted", text: "none" }),
            inh ? [" ", el("span", { title: inh }, badge("inherits", "warn"))] : null),
          srcRef(slug, d.source.file, d.source.line)];
      })), note);
  }

  // ---------- balance comparison (kosmokrator.balance/1, read-only) ----------
  // Charts and tables: resolved report values, labelled estimates, magic access, summons and gem sites. No score is computed.
  // Reference nations live in the address (?r=5,6), so a comparison can be bookmarked; without it the model's default is used.
  const balUrl = (slug, refs) => `${apiBase(slug)}/balance${refs ? `?references=${refs.join(",")}` : ""}`;
  const modelCache = new WeakMap();
  // GETs whose result depends on the loaded model are cached on that model object, so any reload fetches them again.
  function modelLoad(m, url, pick) {
    if (!modelCache.has(m)) modelCache.set(m, new Map());
    const c = modelCache.get(m);
    if (!c.has(url)) c.set(url, getJSON(url).then(pick || ((b) => b.result)));
    const p = c.get(url);
    p.catch(() => { if (c.get(url) === p) c.delete(url); });
    return p;
  }
  const balRefs = () => { const r = hashQuery().get("r"); return r && /^\d+(,\d+){0,11}$/.test(r) ? [...new Set(r.split(",").map(Number))] : null; };
  function balHref(slug, refs) {
    const base = route("p", slug, "balance");
    return refs && refs.length ? `${base}${base.includes("?") ? "&" : "?"}r=${refs.join(",")}` : base;
  }
  const estText = (e) => e && (e.status === "resolved" || e.status === "estimated") && e.value !== null && e.value !== undefined ? `${e.status === "estimated" ? "≈" : ""}${e.value}` : null;
  // Raw component (as written, †) above the labelled estimate; an unresolved estimate says so rather than showing 0.
  function balCost(raw, est) {
    const e = estText(est);
    return el("span", { class: "bal-cost" },
      el("span", { title: (raw && raw.note) || null }, costText(raw), "†"),
      el("span", { class: e ? "bal-est" : "bal-est faint", title: (est && est.note) || null, text: e ? ` ${e}` : " est. —" }));
  }
  function balMagic(u) {
    const fixed = Object.entries(u.fixed_paths || {}).filter(([, v]) => v);
    const rnd = u.random_magic || [];
    if (!fixed.length && !rnd.length) return el("span", { class: "muted", text: "—" });
    return el("span", null, fixed.map(([p, v]) => [pathChip(p, v), " "]),
      rnd.map((x) => el("span", { class: "path-rand", title: txt(x.probability_note) }, randomMark(),
        `+${txt(x.levels ?? "?")} ${(x.paths || []).join("/")} ${txt(x.chance)}%${x.per_path_probability ? ` (${Object.entries(x.per_path_probability).map(([p, v]) => `${p} ${Math.round(v * 100)}%`).join(", ")})` : ""} `)));
  }
  function balGear(u) {
    const eq = u.equipment || {}, names = (xs) => (xs || []).map((x) => txt(x.name || x.unresolved || `#${txt(x.id ?? x.ref)}`));
    const w = names(eq.weapons), a = names(eq.armor);
    const prot = estText(u.protection);
    return el("span", { class: "bal-gear" }, w.length ? w.join(", ") : el("span", { class: "muted", text: "no weapons" }),
      a.length ? el("div", { class: "faint", text: a.join(", ") }) : null,
      prot ? el("div", { class: "faint", title: txt(u.protection.note), text: `Prot ${prot}${u.protection.body !== undefined ? ` (body ${u.protection.body}, head ${u.protection.head})` : ""}` }) : null,
      (eq.weapons_status && eq.weapons_status.status === "unresolved") || (eq.armor_status && eq.armor_status.status === "unresolved") ? [" ", badge("list unresolved", "warn")] : null);
  }
  function balWhere(u) {
    return (u.recruitment || []).map((r) => txt(r.where === "fort" || r.where === "nonfort" || r.where === "coast" ? `${r.where}` : r.site || r.site_name ? `${r.where} (${r.site || r.site_name})` : r.where)).filter(Boolean).join("; ") || "—";
  }
  // Nation identity shared by the summary table and every chart: a fixed colour order (adjacent pairs validated for
  // colour-vision separation on the panel surface) plus a shape. Project nations are all squares; reference nations
  // cycle circle, triangle, diamond, ... so several project nations, or more than five references, share a shape and
  // differ by colour only; every legend, row label and the chart data table name the nation in text.
  const BAL_COLORS = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"];
  const BAL_SHAPES = ["circle", "triangle", "diamond", "triangle-down", "plus"];
  function balSeries(all) {
    let r = 0;
    return all.map((x, i) => ({ ...x, color: BAL_COLORS[i % BAL_COLORS.length], shape: x.project ? "square" : BAL_SHAPES[r++ % BAL_SHAPES.length],
      name: txt(x.n.name), src: `${x.project ? "project" : "catalog"} #${txt(x.n.id)}`, label: `${txt(x.n.name)} (${x.project ? "project" : "catalog"} #${txt(x.n.id)})` }));
  }
  // One series mark centred on (cx, cy) with half-size s.
  function balMark(shape, cx, cy, s, color) {
    const pts = (xs) => svgEl("path", { d: `M${xs.map(([a, b]) => `${(cx + a * s).toFixed(1)},${(cy + b * s).toFixed(1)}`).join("L")}Z`, fill: color });
    if (shape === "square") return svgEl("rect", { x: cx - s * .9, y: cy - s * .9, width: s * 1.8, height: s * 1.8, rx: 1, fill: color });
    if (shape === "circle") return svgEl("circle", { cx, cy, r: s, fill: color });
    if (shape === "triangle") return pts([[0, -1.2], [1.1, .8], [-1.1, .8]]);
    if (shape === "triangle-down") return pts([[0, 1.2], [1.1, -.8], [-1.1, -.8]]);
    if (shape === "diamond") return pts([[0, -1.25], [1.15, 0], [0, 1.25], [-1.15, 0]]);
    const w = .38;
    return pts([[-w, -1.1], [w, -1.1], [w, -w], [1.1, -w], [1.1, w], [w, w], [w, 1.1], [-w, 1.1], [-w, w], [-1.1, w], [-1.1, -w], [-w, -w]]);
  }
  const balKey = (p) => svgEl("svg", { width: 14, height: 14, viewBox: "0 0 14 14", "aria-hidden": "true", focusable: "false" }, balMark(p.shape, 7, 7, 5, p.color));
  // Legend / row label: mark, nation name and its source.
  const balSeriesLabel = (p, strong) => el("span", { class: "bal-series" }, balKey(p),
    el("span", null, strong ? el("strong", { text: p.name }) : p.name, " ", el("span", { class: "src", text: p.src })));
  // Round axis steps (1, 2, 2.5, 5 x 10^k) so ticks read as whole values rather than fractions of the maximum.
  function niceStep(max, n) {
    const raw = Math.max(max, 1e-9) / n, p = 10 ** Math.floor(Math.log10(raw)), f = raw / p;
    return p * (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10);
  }
  // Right-align the given header columns of a table() so headings sit over their numbers.
  const numHeads = (wrap, cols) => { const ths = wrap.querySelectorAll("thead th"); cols.forEach((i) => ths[i] && ths[i].classList.add("num")); return wrap; };
  const numCell = (content, cls) => el("td", { class: `num${cls ? ` ${cls}` : ""}` }, content);
  const BAL_STATS = [["hp", "HP", "Hit points"], ["prot", "Prt", "Natural protection"], ["mr", "MR", "Magic resistance"], ["mor", "Mor", "Morale"], ["att", "Att", "Attack skill"], ["def", "Def", "Defence skill"]];
  function balUnits(m, units, project) {
    if (!units.length) return el("p", { class: "muted", text: "No recruitable units in this reading." });
    const order = { commander: 0, troop: 1 };
    const sorted = [...units].sort((a, b) => (order[a.role] ?? 2) - (order[b.role] ?? 2));
    const row = (u) => {
      const st = u.stats || {}, has = (k) => st[k] && st[k].value !== undefined && st[k].value !== null;
      const build = (isCurrent) => unitPreview(m, u, project, isCurrent), name = txt(u.name) || "(unnamed)";
      return el("tr", null,
        el("td", null, el("div", { class: "bal-unit" }, attachPreview(unitThumb(m, u, project), name, build),
          el("span", null,
            el("span", { class: "bal-name" }, attachPreview(project && Number.isInteger(u.id) && m.monsters.some((x) => x.id === u.id) ? el("a", { href: route("p", m.project.slug, "units", u.id) }, name) : el("strong", { text: name }), name, build),
              el("span", { class: "faint", text: `#${txt(u.id)}` }), previewButton(name, build)),
            el("span", { class: "bal-where", text: `${txt(u.role)} · ${balWhere(u)}` })))),
        BAL_STATS.map(([k, , full], i) => el("td", { class: `num stat${i ? "" : " stat-first"}${has(k) ? "" : " q"}`, title: `${full}, base unequipped${has(k) ? "" : ": unresolved, not zero"}` }, has(k) ? txt(st[k].value) : "?")),
        numCell(balCost((u.raw_costs || {}).gold, (u.cost_estimates || {}).gold), "cost-first"),
        numCell(balCost((u.raw_costs || {}).resources, (u.cost_estimates || {}).resources)),
        numCell(balCost((u.raw_costs || {}).recruitment_points, (u.cost_estimates || {}).recruitment_points)),
        el("td", null, balGear(u)), el("td", null, el("span", { class: "bal-magic-cell" }, balMagic(u))));
    };
    const roleRow = (role, n) => el("tr", { class: "bal-role-row" }, el("th", { scope: "rowgroup", colspan: 12 }, `${{ commander: "Commanders", troop: "Troops" }[role] || txt(role)} (${n})`));
    const roles = [...new Set(sorted.map((u) => u.role))];
    const th = (content, attrs) => el("th", { scope: "col", ...(attrs || {}) }, content);
    return el("div", { class: "table-wrap" }, el("table", { class: "bal-table" },
      el("caption", { class: "sr-only", text: "Recruitable units: base stats, cost components with estimates, equipment and magic" }),
      el("thead", null,
        el("tr", null, th("Unit", { rowspan: 2 }),
          th(el("span", { text: "Base stats, unequipped" }), { colspan: 6, scope: "colgroup", class: "bal-group stat-first" }),
          th(el("span", { text: "Cost: raw † · estimate ≈" }), { colspan: 3, scope: "colgroup", class: "bal-group cost-first" }),
          th("Equipment (estimate)", { rowspan: 2 }), th("Magic", { rowspan: 2 })),
        el("tr", null, BAL_STATS.map(([, a, full], i) => th(el("abbr", { title: full, text: a }), { class: `num${i ? "" : " stat-first"}` })),
          th(statLabel("gold", "Gold"), { class: "num cost-first" }), th(statLabel("resources", "Resources"), { class: "num" }),
          th(statLabel("recruitment_points", "Rec. pts"), { class: "num" }))),
      roles.map((r) => { const us = sorted.filter((u) => u.role === r); return el("tbody", null, roleRow(r, us.length), us.map(row)); })));
  }
  function balMaxima(ma) {
    const mx = Object.entries((ma && ma.fixed_maxima) || {}).filter(([, v]) => v);
    return mx.length ? el("span", null, mx.map(([p, v]) => [pathChip(p, v), " "])) : el("span", { class: "muted", text: "none" });
  }
  function balSummons(m, xs) {
    if (!xs.length) return null;
    // Summon targets use their resolved project block because they are outside the recruitable balance roster.
    const targetCard = (t) => {
      if (!t || t.status !== "known") return unresolved(`target ${txt(t && t.id)}`);
      const mo = projectMonster(m, t);
      if (!mo) return el("span", null, unitThumb(m, t, false), ` ${txt(t.name)} (#${txt(t.id)})`);
      const r = mo.resolved, eq = r.equipped || {};
      const bu = { ...mo, stats: r.stats, raw_costs: r.costs, cost_estimates: eq.costs,
        equipment: r.equipment, protection: eq.protection };
      const build = (isCurrent) => unitPreview(m, bu, true, isCurrent), name = txt(mo.name);
      return el("div", { class: "bal-unit" }, attachPreview(unitThumb(m, bu, true), name, build),
        el("span", { class: "bal-name" }, attachPreview(el("a", { href: route("p", m.project.slug, "units", mo.id), text: name }), name, build), previewButton(name, build)));
    };
    return el("div", null, el("h4", { class: "bal-sub", text: `National summons (${xs.length})` }),
      numHeads(table(["Ritual", "Requires", "Target", "Count", "Gems", "Gems / unit"], xs.map((x) => [
        el("span", null, el("strong", { text: txt(x.name) }), " ", x.source && x.source.line ? srcRef(m.project.slug, x.source.file, x.source.line) : null,
          el("div", { class: "faint", text: `${txt(x.effect_label)}${x.researchlevel !== null && x.researchlevel !== undefined ? ` · research ${x.researchlevel}` : ""}` })),
        (x.requirements || []).length ? el("span", null, x.requirements.map((r) => [pathChip(r.path, r.level), " "])) : el("span", { class: "muted", text: "—" }),
        targetCard(x.target),
        numCell(x.count !== null && x.count !== undefined ? txt(x.count) : el("span", null, txt(x.raw_count ?? "?"), " ", badge("raw", "warn"))),
        x.gem_cost !== null && x.gem_cost !== undefined ? (x.gem_path ? gemChip(x.gem_path, x.gem_cost) : txt(x.gem_cost)) : unresolved("not derived"),
        numCell(x.gems_per_unit !== null && x.gems_per_unit !== undefined ? `≈ ${Math.round(x.gems_per_unit * 100) / 100}` : unresolved("no per-unit estimate"))])), [3, 5]),
      el("p", { class: "panel-note", text: txt(((xs[0] || {}).notes || []).slice(-1)[0]) || "Gems are fatigue / 100 for simple rituals; boosters and discounts are not simulated." }));
  }
  function balGemSites(gs) {
    if (!(gs || []).length) return null;
    return el("p", { class: "sheet-line" }, el("span", { class: "sheet-k", text: "Start-site gems:" }), " ",
      gs.map((g, i) => [i ? "; " : "", txt(g.name), " ", gemList(g.gems)]));
  }
  function balNationBlock(m, n, project) {
    const units = n.units || [];
    const count = (v, word) => [el("strong", { text: v }), ` ${word}`];
    return [
      el("p", { class: "bal-nation-meta" },
        el("span", null, count(units.filter((u) => u.role === "troop").length, "troop(s)")),
        el("span", null, count(units.filter((u) => u.role === "commander").length, "commander(s)")),
        el("span", null, count(((n.magic_access || {}).recruitable_mages || []).length, "recruitable mage(s)"))),
      balUnits(m, units, project),
      el("div", { class: "bal-facts" },
        el("p", { class: "sheet-line" }, el("span", { class: "sheet-k", text: "Fixed magic maxima:" }), " ", balMaxima(n.magic_access),
          el("span", { class: "faint", text: ` ${txt((n.magic_access || {}).note)}` })),
        project ? balGemSites(n.gem_sites) : null),
      project ? balSummons(m, n.summons || []) : null,
      n.note ? el("p", { class: "panel-note bal-panel-note", text: txt(n.note) }) : null];
  }
  // The report's recruit counts beside the Units classification for the same nation. A difference is shown, never hidden:
  // the report is then labelled incomplete (for example a server started before terrain and coastal recruitment were read).
  function balRosterCheck(m, n) {
    const nation = m.nations.find((x) => x.uid === n.uid);
    if (!nation) return null;
    const rc = rosterCounts(m, nation), units = n.units || [];
    const rep = { troop: units.filter((u) => u.role === "troop").length, commander: units.filter((u) => u.role === "commander").length };
    const same = rep.troop === rc.troop && rep.commander === rc.commander;
    const outside = rosterSummary(rc, ["hero", "summon", "other", "pretender"]);
    return el("p", { class: "bal-roster" },
      same ? null : [badge("incomplete", "warn"), " "],
      `Compared here: ${rosterWord("troop", rep.troop)} · ${rosterWord("commander", rep.commander)}.`,
      same ? null : ` Units lists ${rosterWord("troop", rc.troop)} · ${rosterWord("commander", rc.commander)}; restart \`kosmokrator serve\` from this checkout and reload.`,
      outside ? el("span", { class: "faint" }, ` Not compared: ${outside} (see `, el("a", { href: routeNation(nationKey(nation), "p", m.project.slug, "units") }, "Units"), ").") : null);
  }
  function balPicker(m, rep, refs) {
    const slug = m.project.slug, sel = rep.selection || {}, avail = sel.available_nations || [];
    const chosen = new Set(refs || sel.requested || []);
    if (!avail.length) return stateBox("empty", "No reference nations available.", "The catalog is missing or has no nation of the project's era.");
    const status = statusLine(`${chosen.size} of 12 selected`);
    const boxes = el("div", { class: "bal-picks" });
    const sync = () => {
      status.textContent = `${chosen.size} of 12 selected`;
      for (const cb of boxes.querySelectorAll("input")) cb.disabled = !cb.checked && chosen.size >= 12;
    };
    const eras = [...new Set(avail.map((n) => n.era))];
    for (const era of eras) {
      boxes.append(el("fieldset", { class: "bal-era" }, el("legend", { text: { 1: "Early age", 2: "Middle age", 3: "Late age" }[era] || `Era ${era}` }),
        avail.filter((n) => n.era === era).map((n) => {
          const id = `bal-ref-${n.id}`, cb = el("input", { type: "checkbox", id, value: n.id, checked: chosen.has(n.id) || null });
          cb.addEventListener("change", () => { if (cb.checked) chosen.add(n.id); else chosen.delete(n.id); sync(); });
          return el("label", { class: "bal-pick", for: id }, cb, ` ${txt(n.name)}`, el("span", { class: "faint", text: ` ${txt(n.epithet || "")} #${n.id}` }));
        })));
    }
    sync();
    const go = (ids) => { location.hash = balHref(slug, ids); };
    return el("details", { class: "raw tech bal-picker" },
      el("summary", null, "Reference nations: ", el("span", { class: "bal-refs", text: (rep.reference_nations || []).map((n) => txt(n.name)).join(", ") || "none" }),
        sel.mode === "first_three_per_era" ? el("span", { class: "faint", text: " (default)" }) : null),
      el("form", { class: "inner stack", onsubmit: (e) => { e.preventDefault(); go([...chosen]); } },
        el("p", { class: "panel-note", text: txt(sel.note) || "Same-era catalog nations. Choose up to 12." }), boxes,
        el("div", { class: "btn-row" }, el("button", { type: "submit", class: "btn", disabled: null }, "Compare selected"),
          el("button", { type: "button", class: "btn btn-ghost", onclick: () => go(null) }, "Default selection"), status)));
  }
  const balControl = (id, label, select) => el("div", { class: "bal-control" }, el("label", { for: id, text: label }), select);
  const balHead = (title, note, ...extra) => el("div", { class: "bal-section-head" }, el("h3", { text: title }), note ? el("p", { text: note }) : null, extra);
  // Charts use resolved report values only; source tables remain the detailed audit trail.
  function balanceDashboard(m, nations) {
    if (!nations.length) return null;
    const numeric = (x) => x !== null && x !== undefined && Number.isFinite(Number(x));
    const value = (e) => e && ["resolved", "estimated"].includes(e.status) && numeric(e.value) ? Number(e.value) : null;
    const metricSelect = el("select", { class: "input", id: "balance-count-metric" },
      [["troop", "Recruitable troops"], ["commander", "Recruitable commanders"], ["mage", "Recruits with magic / holy paths"]]
        .map(([v, t]) => el("option", { value: v, text: t })));
    const bars = el("div", { class: "balance-bars", role: "group", "aria-label": "Roster comparison" });
    const drawBars = () => {
      const rows = nations.map((x) => ({ ...x, count: metricSelect.value === "mage" ? ((x.n.magic_access || {}).recruitable_mages || []).length
        : (x.n.units || []).filter((u) => u.role === metricSelect.value).length }));
      const max = Math.max(1, ...rows.map((x) => x.count));
      fillKids(bars, rows.map((x) => {
        const fill = el("span", { class: "balance-bar-fill" });
        fill.style.width = `${x.count / max * 100}%`; fill.style.backgroundColor = x.color;
        return el("div", { class: "balance-bar-row" }, balSeriesLabel(x),
          el("div", { class: "balance-bar-track", "aria-hidden": "true" }, fill), el("strong", { text: x.count }));
      }));
    };
    metricSelect.addEventListener("change", drawBars); drawBars();
    const magicTable = table(["Nation", ...PATH_KEYS.map((p) => el("span", { class: "balance-magic-head" }, pathChip(p, "", false, PATH_NAMES[p])))], nations.map((x) => [
      balSeriesLabel(x), ...PATH_KEYS.map((p) => {
        const v = (x.n.magic_access || {}).fixed_maxima?.[p];
        const known = numeric(v), n = known ? Number(v) : null;
        const cell = el("span", { class: `balance-magic-level${!known ? " unknown" : n === 0 ? " zero" : ""}`, title: `${PATH_NAMES[p]}: ${known ? v : "unknown"}`, text: known ? v : "—" });
        // Shade steps keep the number at >= 4.5:1: light text on levels 1-2, dark ink on 3 and above.
        if (known && n > 0) { const lv = Math.min(5, Math.max(1, Math.round(n))); cell.style.setProperty("--shade", [.18, .4, .72, .82, .92][lv - 1]); cell.style.color = lv >= 3 ? "var(--accent-ink)" : "var(--text)"; }
        return cell;
      })]));
    magicTable.classList.add("balance-magic");
    const role = el("select", { class: "input", id: "balance-chart-role" },
      el("option", { value: "troop", text: "Troops" }), el("option", { value: "commander", text: "Commanders" }));
    const stat = el("select", { class: "input", id: "balance-chart-stat" },
      [["protection", "Estimated protection"], ["hp", "Hit points"], ["mr", "Magic resistance"], ["mapmove", "Map movement"], ["resources", "Estimated resources"]]
        .map(([v, t]) => el("option", { value: v, text: t })));
    const costAxis = el("select", { class: "input", id: "balance-chart-cost" },
      el("option", { value: "gold", text: "Fixed gold component" }), el("option", { value: "resources", text: "Estimated resources" }),
      el("option", { value: "recruitment_points", text: "Recruitment points" }));
    costAxis.value = "resources";
    const plot = el("div", { class: "balance-plot" }), summary = el("p", { class: "panel-note", role: "status", "aria-live": "polite" });
    const artNote = el("p", { class: "panel-note bal-art-note", hidden: true });
    const dataTable = el("div");
    let points = [], drawnWidth = 0;
    // The plot is drawn at its rendered width so labels stay at a readable pixel size on every screen.
    const drawSvg = () => {
      const W = Math.max(300, Math.round(plot.clientWidth || 760)), narrow = W < 520;
      drawnWidth = W;
      if (!points.length) return;
      const H = Math.round(Math.min(400, Math.max(250, W * .42)));
      const L = narrow ? 40 : 52, R = 14, T = 34, B = 46, pw = W - L - R, ph = H - T - B;
      const yLabel = stat.options[stat.selectedIndex].text, xLabel = costAxis.options[costAxis.selectedIndex].text;
      const xs = niceStep(Math.max(...points.map((p) => p.gold)) * 1.04, narrow ? 4 : 6), ys = niceStep(Math.max(...points.map((p) => p.y)) * 1.04, 5);
      const xMax = Math.max(xs, Math.ceil(Math.max(...points.map((p) => p.gold)) * 1.04 / xs) * xs), yMax = Math.max(ys, Math.ceil(Math.max(...points.map((p) => p.y)) * 1.04 / ys) * ys);
      const x = (v) => L + v / xMax * pw, y = (v) => T + ph - v / yMax * ph;
      const fmt = (v) => String(Number(v.toFixed(2)));
      const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img", "aria-label": `${xLabel} versus ${yLabel}. ${points.length} units plotted. Exact values in the chart data table.` },
        svgEl("title", { text: `${xLabel} versus ${yLabel}` }));
      for (let v = 0; v <= yMax + 1e-9; v += ys) {
        svg.append(svgEl("line", { x1: L, y1: y(v), x2: L + pw, y2: y(v), class: v ? "balance-gridline" : "balance-axis" }),
          svgEl("text", { x: L - 8, y: y(v) + 4, "text-anchor": "end", text: fmt(v) }));
      }
      for (let v = 0; v <= xMax + 1e-9; v += xs) {
        if (v) svg.append(svgEl("line", { x1: x(v), y1: T, x2: x(v), y2: T + ph, class: "balance-gridline" }));
        svg.append(svgEl("text", { x: x(v), y: T + ph + 17, "text-anchor": "middle", text: fmt(v) }));
      }
      svg.append(svgEl("text", { x: L, y: T - 12, class: "axis-title", text: `↑ ${yLabel}` }),
        svgEl("text", { x: L + pw, y: H - 6, "text-anchor": "end", class: "axis-title", text: `${xLabel} →` }));
      // Each unit is its idle sprite, centred on its exact value (never nudged apart), framed in its nation colour with
      // the nation's shape in the corner. Missing or failed art falls back to the plain shape mark. Units whose markers
      // mostly cover one another list each other on their card. The SVG is drawn 1:1, so marker pixels match its axes.
      // A redraw (resize, axis change) replaces the markers; an open card follows its unit to the new marker if it is still plotted.
      const was = pv.trigger && plot.contains(pv.trigger) ? { k: pv.trigger.dataset.k, pinned: pv.pinned, focused: document.activeElement === pv.trigger } : null;
      if (was) hidePreview(false);
      const S = narrow ? 26 : 32, near = S * .7;
      const pos = points.map((p) => ({ p, cx: x(p.gold), cy: y(p.y), name: txt(p.u.name) || "(unnamed)" }));
      pos.forEach((a) => { a.near = pos.filter((b) => b !== a && Math.abs(b.cx - a.cx) < near && Math.abs(b.cy - a.cy) < near); });
      // Keyboard order runs along the horizontal axis, then top to bottom; one tab stop, arrow keys move between units.
      const order = [...pos].sort((a, b) => a.cx - b.cx || a.cy - b.cy);
      // Project markers stack above catalog ones, later markers above earlier; only the uppermost of a stack carries the +N badge.
      const rank = (q) => (q.p.project ? order.length : 0) + order.indexOf(q);
      order.forEach((q) => { q.badge = q.near.length && q.near.every((o) => rank(o) < rank(q)); });
      let noArt = 0;
      const showArt = () => { artNote.hidden = !noArt; artNote.textContent = `${noArt} unit${noArt === 1 ? " has" : "s have"} no loadable sprite and show${noArt === 1 ? "s" : ""} the nation mark instead.`; };
      const axes = (q) => `${xLabel} ${q.p.xt}, ${yLabel} ${q.p.yt}`;
      order.forEach((q, i) => {
        const p = q.p, src = unitSpriteSrc(m, p.u, p.project);
        const b = el("button", { type: "button", class: `bal-pt${p.project ? " project" : ""}`, tabindex: i ? "-1" : "0", "aria-haspopup": "dialog",
          "aria-expanded": "false", "aria-controls": PREVIEW_ID,
          "aria-label": `${q.name}, ${p.label}: ${axes(q)}.${q.near.length ? ` Overlaps ${q.near.length} other unit${q.near.length === 1 ? "" : "s"}.` : ""}` });
        b.dataset.k = `${p.index}:${txt(p.u.uid ?? p.u.id)}:${txt(p.u.name)}`;
        b.style.left = `${q.cx.toFixed(1)}px`; b.style.top = `${q.cy.toFixed(1)}px`; b.style.setProperty("--c", p.color);
        const noSprite = () => {
          b.classList.add("no-art");
          fillKids(b, svgEl("svg", { width: 18, height: 18, viewBox: "0 0 18 18", "aria-hidden": "true", focusable: "false" }, balMark(p.shape, 9, 9, 6.5, p.color)));
          if (q.badge) b.append(el("span", { class: "bal-pt-n", "aria-hidden": "true", text: `+${q.near.length}` }));
          noArt++; showArt();
        };
        if (src) {
          const img = el("img", { src, alt: "", decoding: "async", draggable: "false" });
          img.addEventListener("error", noSprite, { once: true });
          b.append(img, el("span", { class: "bal-pt-key", "aria-hidden": "true" }, balKey(p)));
          if (q.badge) b.append(el("span", { class: "bal-pt-n", "aria-hidden": "true", text: `+${q.near.length}` }));
        } else noSprite();
        q.btn = b;
        q.build = (isCurrent) => {
          const parts = unitPreview(m, p.u, p.project, isCurrent);
          parts.splice(1, 0, el("div", { class: "pv-chart" },
            el("p", { class: "sheet-line" }, el("span", { class: "sheet-k", text: "On this chart: " }), balSeriesLabel(p)),
            el("p", { class: "sheet-line pv-axes" }, el("span", null, `${xLabel} `, el("strong", { text: p.xt })), el("span", null, `${yLabel} `, el("strong", { text: p.yt }))),
            q.near.length ? el("div", { class: "sheet-line pv-near" }, el("span", { class: "sheet-k", text: `Overlapping here (${q.near.length}):` }),
              q.near.map((o) => el("button", { type: "button", class: "btn btn-small btn-ghost", "aria-label": `Show ${o.name}, ${o.p.label}: ${axes(o)}`,
                onclick: () => showPreview(o.btn, o.name, o.build, true) }, balKey(o.p), ` ${o.name}`))) : null));
          return parts;
        };
        attachPreview(b, q.name, q.build);
        b.addEventListener("click", () => { if (pv.trigger === b && pv.pinned && !pv.card.hidden) hidePreview(true); else showPreview(b, q.name, q.build, true); });
        b.addEventListener("focus", () => { for (const o of order) o.btn.tabIndex = o.btn === b ? 0 : -1; });
      });
      const layer = el("div", { class: "bal-pts", role: "group", "aria-label": `${points.length} plotted units, left to right by ${xLabel}. Arrow keys move between units; Enter pins a unit card.` },
        order.map((q) => q.btn));
      layer.addEventListener("keydown", (e) => {
        const k = order.findIndex((q) => q.btn === e.target);
        if (k < 0) return;
        const to = { ArrowRight: k + 1, ArrowDown: k + 1, ArrowLeft: k - 1, ArrowUp: k - 1, Home: 0, End: order.length - 1 }[e.key];
        if (to === undefined) return;
        e.preventDefault();
        order[Math.max(0, Math.min(order.length - 1, to))].btn.focus();
      });
      showArt();
      fillKids(plot, svg, layer);
      const again = was && order.find((q) => q.btn.dataset.k === was.k);
      if (again && was.pinned) showPreview(again.btn, again.name, again.build, true);
      else if (again && was.focused) again.btn.focus({ preventScroll: true });
    };
    const drawPlot = () => {
      let omitted = 0;
      points = nations.flatMap((x, i) => (x.n.units || []).filter((u) => u.role === role.value).flatMap((u) => {
        const gold = value(u.cost_estimates?.[costAxis.value]);
        const y = stat.value === "protection" ? value({ ...u.protection, value: u.protection?.average }) : stat.value === "resources" ? value(u.cost_estimates?.resources) : value(u.stats?.[stat.value]);
        if (gold === null || y === null || gold < 0 || y < 0) { omitted++; return []; }
        // Display text keeps the report's estimate mark (≈); gold / y are the plotted numbers.
        const xt = estText(u.cost_estimates?.[costAxis.value]), yt = estText(stat.value === "protection" ? { ...u.protection, value: u.protection?.average }
          : stat.value === "resources" ? u.cost_estimates?.resources : u.stats?.[stat.value]);
        return [{ ...x, u, gold, y, xt: xt ?? String(gold), yt: yt ?? String(y), index: i }];
      }));
      const yLabel = stat.options[stat.selectedIndex].text, xLabel = costAxis.options[costAxis.selectedIndex].text;
      if (points.length) drawSvg();
      else { artNote.hidden = true; fillKids(plot, stateBox("empty", "No resolved values for this chart.", "Choose another metric or reference nation. Unknown values are not plotted as zero.")); }
      summary.textContent = `${points.length} unit${points.length === 1 ? "" : "s"} plotted; ${omitted} omitted (unresolved).`;
      fillKids(dataTable, table(["Nation / source", "Unit", statLabel(costAxis.value, xLabel), statLabel(stat.value === "protection" ? "prot" : stat.value, yLabel)], points.map((p) => [balSeriesLabel(p),
        p.project ? attachPreview(el("a", { href: route("p", m.project.slug, "units", p.u.id), text: p.u.name }), txt(p.u.name), (isCurrent) => unitPreview(m, p.u, true, isCurrent))
          : attachPreview(el("span", { text: p.u.name }), txt(p.u.name), (isCurrent) => unitPreview(m, p.u, false, isCurrent)), numCell(p.gold), numCell(p.y)])));
    };
    role.addEventListener("change", drawPlot); stat.addEventListener("change", drawPlot); costAxis.addEventListener("change", drawPlot); drawPlot();
    if (typeof ResizeObserver === "function") {
      // Released once the plot leaves the document (route change or re-render).
      const ro = new ResizeObserver(() => { if (!plot.isConnected) { ro.disconnect(); return; } if (Math.abs((plot.clientWidth || 0) - drawnWidth) > 8) drawSvg(); });
      ro.observe(plot);
    }
    return el("section", { class: "stack", "aria-label": "Balance charts" },
      el("div", { class: "balance-dashboard" },
        el("section", { class: "panel" }, balHead("Roster comparison"),
          el("div", { class: "bal-controls" }, balControl("balance-count-metric", "Compare", metricSelect)), bars,
          el("p", { class: "panel-note bal-panel-note", text: "Counts show variety, not army strength. Project: fort, start-site, terrain and coastal recruits. Catalog: fort, non-fort, coastal and capital-site tables; other special recruitment is not reconstructed." })),
        el("section", { class: "panel" }, balHead("Fixed magic access"), magicTable,
          el("p", { class: "panel-note bal-panel-note", text: "Highest fixed magic per recruit (H includes priests); randoms and boosters are excluded." }))),
      el("section", { class: "panel" }, balHead("Cost and capability"),
        el("div", { class: "bal-controls" }, balControl("balance-chart-role", "Roster", role),
          balControl("balance-chart-cost", "Horizontal axis", costAxis), balControl("balance-chart-stat", "Vertical axis", stat)),
        el("ul", { class: "balance-legend", "aria-label": "Nations" }, nations.map((p) => el("li", null, balSeriesLabel(p)))),
        plot,
        el("div", { class: "bal-chart-foot" }, summary, artNote,
          el("p", { class: "panel-note", text: "Unresolved values are left out, never plotted as zero. Costs and equipment values are components or estimates (≈), not final in-game prices." })),
        el("details", { class: "raw tech" }, el("summary", { text: "How to read this chart" }), el("div", { class: "inner" },
          el("p", { class: "panel-note", text: "Each unit is its sprite at its exact value, framed in its nation colour; the corner mark is the nation's shape (squares: project, other shapes: catalog). A +N badge means N other units overlap there; their cards list one another." }))),
        el("details", { class: "raw tech" }, el("summary", { text: "Chart data — exact values" }), el("div", { class: "inner" }, dataTable))));
  }
  function viewBalance(m) {
    const slug = m.project.slug, refs = balRefs();
    const draw = (rep) => {
      const pn = (rep.project_nations || []).filter((n) => state.nation.key === N_ALL || state.nation.key === N_NONE || (selectedNation(m) && selectedNation(m).uid === n.uid));
      const refsN = rep.reference_nations || [];
      const all = balSeries([...pn.map((n) => ({ n, project: true })), ...refsN.map((n) => ({ n, project: false }))]);
      return [
        el("div", { class: "bal-intro" },
          el("div", null, el("h2", { text: "Balance comparison" }),
            el("p", { class: "muted", text: "Compared with same-era vanilla nations. No power score; test in game." })),
          el("dl", { class: "bal-key", "aria-label": "How to read costs and values" },
            el("dt", { text: "†" }), el("dd", { text: "Raw cost component as written (gold, resources, recruitment points); auto+N is an autocalc base." }),
            el("dt", { class: "est", text: "≈" }), el("dd", { text: "Labelled estimate, where supported." }),
            el("dt", { text: "?" }), el("dd", { text: "Not resolved by the static model; never zero." }))),
        balPicker(m, rep, refs),
        (rep.warnings || []).length ? el("ul", { class: "diag bal-warnings" }, rep.warnings.map((w) => el("li", null, badge("check", "warn"), " ", el("span", { text: txt(w) })))) : null,
        state.nation.key === N_NONE ? stateBox("empty", "Balance is per nation.", "Showing every project nation; choose one above to focus.") : null,
        balanceDashboard(m, all),
        // Detailed tables follow the charts, collapsed; each project nation keeps its roster cross-check visible.
        el("h3", { class: "bal-tables-title", text: "Detailed tables" }),
        pn.length ? pn.map((n) => el("section", { class: "panel" },
          balHead(`${txt(n.name)}`, `This project${n.era ? `, era ${n.era}` : ""}`), balRosterCheck(m, n),
          el("details", { class: "raw tech" }, el("summary", null, `Recruitable roster, magic and summons (${(n.units || []).length} recruits)`),
            el("div", { class: "inner stack" }, balNationBlock(m, n, true)))))
          : stateBox("empty", "No project nation in this selection."),
        balItems(m),
        refsN.map((n) => el("details", { class: "raw tech" }, el("summary", null, `${txt(n.name)}${n.epithet ? `, ${txt(n.epithet)}` : ""} (catalog #${n.id}, era ${txt(n.era)}) - ${(n.units || []).length} unit(s)`),
          el("div", { class: "inner stack" }, balNationBlock(m, n, false)))),
        (rep.limitations || []).length ? techSection("What this does not show", false, el("ul", null, rep.limitations.map((t) => el("li", { text: txt(t) })))) : null,
        techSection("JSON", false, jsonActions(balUrl(slug, refs), () => rep, "Balance JSON"))];
    };
    if (!refs && m.balance) return el("div", { class: "stack" }, draw(m.balance));
    const box = el("div", { class: "stack", "aria-busy": "true" }, stateBox("loading", "Reading comparison tables..."));
    modelLoad(m, balUrl(slug, refs)).then((rep) => { box.removeAttribute("aria-busy"); fillKids(box, draw(rep)); }, (e) => {
      box.removeAttribute("aria-busy");
      fillKids(box, errorBox(e, "the balance comparison"), el("div", { class: "btn-row" },
        el("button", { type: "button", class: "btn", onclick: () => render() }, "Retry"),
        refs ? el("a", { class: "btn btn-ghost", href: balHref(slug, null) }, "Use the default selection") : null));
    });
    return box;
  }

  // ---------- maps (project-wide .map files) ----------
  // Drafts live in state.maps per project and map, one change list per plane. Review (preview:true) shows the exact .map
  // diff and validation; Save writes against the revision this page loaded, and a 409 reloads while keeping the draft.
  // Terrain masks reach 2^36, so flags are tested and toggled with arithmetic, never with 32-bit bitwise operators.
  const SVG_NS = "http://www.w3.org/2000/svg";
  function svgEl(tag, attrs, ...kids) {
    const n = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "text") n.textContent = String(v);
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, String(v));
    }
    for (const kid of kids.flat(Infinity)) if (kid) n.append(kid);
    return n;
  }
  const hasFlag = (mask, v) => v > 0 && Math.floor(mask / v) % 2 === 1;
  const MAP_ID_RE = /^[A-Za-z][A-Za-z0-9_]{0,47}$/;
  const MAP_FILE_RE = /^[A-Za-z0-9_]+\.(map|tga|d6m|rgb|d3m|png|txt)$/i;
  // Only same-origin API paths are used as image sources or download links.
  const apiUrl = (u) => typeof u === "string" && u.startsWith("/api/projects/");
  const countOf = (v) => (Array.isArray(v) ? v.length : v);
  const shortRev = (r) => (typeof r === "string" ? shortSha(r) : txt(r ?? "—"));
  const mapsUrl = (slug) => `${apiBase(slug)}/maps`;
  const mapRoute = (slug, id) => (id ? route("p", slug, "maps", id) : route("p", slug, "maps"));
  const mapCmd = (c) => String(c).replace(/^#/, "");
  const pairKey = (a, b) => (a < b ? `${a}-${b}` : `${b}-${a}`);
  const bucketSize = (b) => (b ? Object.keys(b.prov).length + b.ops.length : 0);
  // Terrain looks documented in the Map Making Manual (p.10 "Terrain Graphics"); each also has a winter image.
  const MAP_LOOKS = [["default", "Default"], ["plain", "Plain"], ["forest", "Forest"], ["waste", "Waste"], ["farm", "Farm"],
    ["swamp", "Swamp"], ["highland", "Highland"], ["kelp", "Kelp forest"], ["water", "Water (drowned land)"]];
  // Look images are fetched once per revision as blobs: the API sends no-store and selection redraws would refetch them.
  const mapLookImgs = new Map();
  const draftSize = (dr) => Object.values(dr.edits).reduce((s, b) => s + bucketSize(b), 0);
  // Problems as badges; a clean map reads as plain text.
  function mapValBadge(v) {
    if (!v) return badge("not validated", "warn");
    const e = countOf(v.errors) || 0, w = countOf(v.warnings) || 0;
    return e ? badge(`${e} error${e === 1 ? "" : "s"}`, "err") : w ? badge(`${w} warning${w === 1 ? "" : "s"}`, "warn") : el("span", { class: "muted", text: "No errors" });
  }
  function mapIssues(v, empty) {
    const items = (v && v.issues) || [];
    if (!items.length) return empty ? el("p", { class: "muted", text: empty }) : null;
    return el("ul", { class: "diag" }, items.map((d) => el("li", null,
      badge(txt(d.severity), d.severity === "error" ? "err" : d.severity === "warning" ? "warn" : "info"),
      el("span", { text: txt(d.message) }), d.line ? el("span", { class: "src-ref", text: `L${d.line}` }) : null)));
  }
  // Which project list an argument suggests from; values stay free text so vanilla names and numbers work too.
  function mapArgKind(a, command) {
    const an = txt(a.name).toLowerCase(), c = mapCmd(command).toLowerCase();
    if (a.type === "int" || a.type === "ref") { if (/nation|player/.test(an)) return "nation"; if (/prov|land/.test(an)) return "province"; }
    if (a.type === "ref" || a.type === "str") {
      if (/site|feature/.test(an) || /feature/.test(c)) return "site";
      if (/mon|unit|commander|type|creature/.test(an) || /commander|units|bodyguard/.test(c)) return "monster";
    }
    return null;
  }
  // Draft text -> { value } typed for the server, or { err }. Custom monsters must be written by name (manual).
  function mapArgValue(m, a, raw, kind) {
    const r = String(raw ?? "").trim(), nm = txt(a.name) || "value";
    if (r === "") return { err: `Enter ${nm}.` };
    if (/["\r\n]/.test(r)) return { err: `${nm}: no double quotes or line breaks.` };
    if (a.type === "int" || a.type === "float") {
      if (!(a.type === "float" ? /^-?\d+(\.\d+)?$/ : /^-?\d+$/).test(r)) return { err: `${nm}: ${a.type === "float" ? "a number" : "whole numbers only"}.` };
      const n = Number(r);
      if (a.type === "int" && !Number.isSafeInteger(n)) return { err: `${nm}: number too large.` };
      if ((a.min != null && n < a.min) || (a.max != null && n > a.max)) return { err: `${nm}: allowed ${a.min ?? "…"} to ${a.max ?? "…"}.` };
      return { value: n };
    }
    if (a.type === "ref" && /^-?\d+$/.test(r)) {
      const n = Number(r), own = kind === "monster" && projectMonsters(m).find((u) => u.id === n && u.identity?.kind === "new");
      if (own) return { err: `${nm}: custom monster #${n} must be written by name (${txt(own.name)}).` };
      return Number.isSafeInteger(n) ? { value: n } : { err: `${nm}: number too large.` };
    }
    if (r.includes("#") || r.includes("--")) return { err: `${nm}: no # or -- in text.` };
    return { value: r };
  }
  function mapArgControls(specs, raw, idp, onInput, command, dl) {
    if (!specs.length) return el("span", { class: "faint", text: "No arguments." });
    return el("div", { class: "trait-args" }, specs.map((a, j) => {
      const id = `${idp}-${j}`, kind = mapArgKind(a, command);
      const c = el("input", { class: "input trait-arg", type: "text", id, autocomplete: "off", list: kind ? `${dl}-${kind}` : null,
        inputmode: a.type === "int" ? "numeric" : a.type === "float" ? "decimal" : null });
      c.value = raw[j] ?? "";
      c.addEventListener("input", () => { raw[j] = c.value; onInput(); });
      const range = a.min != null || a.max != null ? ` ${a.min ?? "…"} to ${a.max ?? "…"}` : "";
      const hint = a.type === "int" ? (kind ? `${kind} number` : `whole number${range}`) : a.type === "float" ? `number${range}`
        : kind === "monster" ? "monster name (custom monsters by name) or vanilla number" : a.type === "ref" ? `${kind || "reference"} name or number` : "text";
      return el("label", { class: "trait-arg-wrap", for: id }, el("span", { class: "faint", text: `${txt(a.name)} · ${hint}` }), c);
    }));
  }
  function mapDatalists(m, P, dl) {
    const uniq = (xs) => [...new Set(xs.filter(Boolean).map(String))];
    return [
      el("datalist", { id: `${dl}-monster` }, uniq(m.monsters.map((u) => u.name)).map((v) => el("option", { value: v }))),
      el("datalist", { id: `${dl}-site` }, uniq(m.sites.map((s) => s.name)).map((v) => el("option", { value: v }))),
      el("datalist", { id: `${dl}-nation` }, numberedNations(m).map((n) => el("option", { value: String(n.id), label: txt(n.name || n.uid) }))),
      el("datalist", { id: `${dl}-province` }, (P.provinces || []).map((p) => el("option", { value: String(p.id), label: txt(p.name) })))];
  }
  // File connections (both directions and neighbour lists folded together) with the draft's connection ops applied.
  function planeConnections(P, bk) {
    const map = new Map();
    const put = (a, b, kind) => { const k = pairKey(a, b); if (!map.has(k)) map.set(k, { a, b, kind: kind ?? 0, base: kind ?? 0, st: "base" }); };
    for (const c of P.connections || []) put(c.a, c.b, c.kind);
    for (const p of P.provinces || []) for (const n of p.neighbors || []) put(p.id, n.id, n.kind);
    for (const o of bk ? bk.ops : []) {
      if (o.op !== "connection") continue;
      const k = pairKey(o.a, o.b), cur = map.get(k);
      if (!cur) { if (o.kind !== null) map.set(k, { a: o.a, b: o.b, kind: o.kind, base: null, st: "added" }); }
      else if (o.kind === null) cur.st = "removed";
      else { cur.kind = o.kind; cur.st = "changed"; }
    }
    return map;
  }
  // A province draft entry -> { change } (null when it matches the file) or { err }.
  function provChange(p, e) {
    const ch = { op: "province", province: p.id };
    if ("name" in e) {
      const v = String(e.name).trim();
      if (!v) return { err: "enter a name." };
      if (/["\r\n]/.test(v)) return { err: "no double quotes or line breaks in the name." };
      if (v !== txt(p.name)) ch.name = v;
    }
    if ("terrain" in e) {
      const t = String(e.terrain).trim();
      if (!/^\d+$/.test(t) || !Number.isSafeInteger(Number(t))) return { err: "terrain must be a whole number of 0 or more." };
      if (Number(t) !== p.terrain) ch.terrain = Number(t);
    }
    for (const k of ["start", "nostart"]) if (k in e && !!e[k] !== !!p[k]) ch[k] = !!e[k];
    return { change: Object.keys(ch).length > 2 ? ch : null };
  }
  // Every source line the plane reports: generic statements plus each province's scenario commands.
  function planeLines(P) {
    const lines = new Map();
    for (const p of P.provinces || []) for (const c of p.commands || []) lines.set(c.line, c);
    for (const s of P.statements || []) lines.set(s.line, s);
    return lines;
  }
  // One pending op -> { change } or { err }. ops is the plane's op list, for the commander-context check.
  function mapOpChange(m, byCmd, P, ops, i) {
    const o = ops[i], provs = new Set((P.provinces || []).map((p) => p.id));
    if (o.op === "connection") {
      if (!provs.has(o.a) || !provs.has(o.b)) return { err: `Province ${provs.has(o.a) ? o.b : o.a} is not on this plane.` };
      return { change: { op: "connection", a: o.a, b: o.b, kind: o.kind } };
    }
    if (o.op !== "add") {
      const s = planeLines(P).get(o.line);
      if (!s || s.raw !== o.was) return { err: `Line ${o.line} changed on disk after this change was drafted. Drop it and redo it.` };
      if (o.op === "remove") return { change: { op: "remove", line: o.line } };
    }
    const spec = byCmd.get(mapCmd(o.command));
    if (!spec) return { err: `#${mapCmd(o.command)} is not a map command this editor can write.` };
    const args = [];
    for (let j = 0; j < (spec.args || []).length; j++) {
      const v = mapArgValue(m, spec.args[j], o.raw[j], mapArgKind(spec.args[j], spec.command));
      if (v.err) return { err: `#${mapCmd(spec.command)}: ${v.err}` };
      args.push(v.value);
    }
    if (o.op === "replace") return { change: { op: "replace", line: o.line, command: mapCmd(spec.command), args } };
    const ch = { op: "add", command: mapCmd(spec.command), args };
    if (spec.scope !== "global") {
      if (!provs.has(o.province)) return { err: `#${ch.command}: choose a province on this plane.` };
      ch.province = o.province;
      if (spec.scope === "commander" && !ops.slice(0, i).some((x) => x.op === "add" && mapCmd(x.command) === "commander" && x.province === o.province))
        return { err: `#${ch.command} modifies a commander: add the #commander for province ${o.province} before it in this draft.` };
    }
    return { change: ch };
  }
  function planeChanges(m, byCmd, P, bk) {
    const changes = [], errors = [];
    for (const [id, e] of Object.entries(bk.prov)) {
      const p = (P.provinces || []).find((x) => x.id === Number(id));
      const r = p ? provChange(p, e) : { err: "not on this plane any more." };
      if (r.err) errors.push({ key: `p${id}`, msg: `Province ${id}: ${r.err}` }); else if (r.change) changes.push(r.change);
    }
    bk.ops.forEach((_, i) => {
      const r = mapOpChange(m, byCmd, P, bk.ops, i);
      if (r.err) errors.push({ key: `o${i}`, msg: r.err }); else changes.push(r.change);
    });
    return { changes, errors };
  }

  function viewMaps(m, arg) {
    if (arg === "~import") return mapImportView(m);
    if (arg) return asyncView(`${mapsUrl(m.project.slug)}/${encodeURIComponent(arg)}`, "map", (data) => mapEditor(m, data));
    const slug = m.project.slug;
    return asyncView(mapsUrl(slug), "maps", (st) => {
      const maps = st.maps || [];
      return [
        el("div", { class: "btn-row" }, CSRF ? el("a", { class: "btn", href: mapRoute(slug, "~import") }, "Import") : noToken()),
        maps.length ? table(["Map", "Planes", "Provinces", "Validation"], maps.map((x) => {
          const dr = state.maps.get(`${slug}:${x.id}`);
          return [el("span", null, el("a", { href: mapRoute(slug, x.id), title: `${txt(x.id)} · revision ${shortRev(x.revision)}` }, txt(x.title || x.id)),
            dr && draftSize(dr) ? [" ", badge("unsaved", "warn")] : null),
          txt(countOf(x.planes)), txt(countOf(x.provinces)), mapValBadge(x.validation)];
        })) : stateBox("empty", "No maps yet.", CSRF ? "Import a .map with its image files to view and edit it here, or create one with an agent below." : ""),
        mapBuildsSection(m)];
    });
  }

  // ---------- map builds: agent briefs, read-only review and accept-as-new-map ----------
  // The browser writes a brief and shows the agent handoff; Codex or Claude build the files in the job's output folder
  // through the CLI/MCP. Every POST carries the jobs revision this page read; a stale revision is reported with a reload
  // button and never retried silently. Accept imports a NEW map and never overwrites one.
  const MB_INT = [["width", "Width (px)", 256, 4096], ["height", "Height (px)", 256, 4096], ["players", "Players", 1, 64],
    ["land_provinces", "Land provinces", 1, 2000], ["sea_provinces", "Sea provinces", 0, 2000], ["cave_provinces", "Cave provinces (plane 2)", 0, 2000]];
  const MB_STATUS = { awaiting_agent: ["waiting for agent output", "warn"], staged: ["output staged", "info"] };
  const mbUrl = (slug) => `${apiBase(slug)}/map-builds`;
  function mbDraft(slug) {
    return draftOf(state.mapBuilds || (state.mapBuilds = new Map()), slug, () => ({ st: null, loading: false, err: null, open: false,
      brief: null, showErrors: false, phase: "edit", preview: null, msg: null, jobs: {} }));
  }
  const mbStale = (e) => !!e && (e.status === 409 || /revision_mismatch|sha_mismatch/.test(((e.error || {}).code) || ""));
  function mbProblems(b, lim) {
    const o = {};
    if (!MAP_ID_RE.test(b.map_id || "")) o.map_id = "Start with a letter; letters, digits or underscores, up to 48 characters.";
    if ((b.title || "").length > 120) o.title = "At most 120 characters.";
    if ((b.theme || "").length > 4000) o.theme = "At most 4000 characters.";
    for (const [k, , lo, hi] of MB_INT) { const v = Number(b[k]); if (!/^\d+$/.test(String(b[k]).trim()) || v < lo || v > hi) o[k] = `A whole number from ${lo} to ${hi}.`; }
    if (!o.width && !o.height && Number(b.width) * Number(b.height) > 16000000) o.height = "At most 16 megapixels.";
    const total = ["land_provinces", "sea_provinces", "cave_provinces"].reduce((n, k) => n + Number(b[k] || 0), 0);
    if (total > ((lim && lim.max_provinces) || 2000)) o.cave_provinces = `At most ${(lim && lim.max_provinces) || 2000} provinces across planes.`;
    return o;
  }
  const mbBody = (b) => ({ ...b, map_id: b.map_id.trim(), ...Object.fromEntries(MB_INT.map(([k]) => [k, Number(b[k])])) });
  function downloadJSON(name, obj) {
    const url = URL.createObjectURL(new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" }));
    const a = el("a", { href: url, download: name, class: "sr-only" });
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function mapBuildsSection(m) {
    const slug = m.project.slug, dr = mbDraft(slug), url = mbUrl(slug);
    const holder = el("div", { class: "inner stack", id: `mb-${slug}` });
    escapeReview(holder, () => dr.phase === "review" && !(dr.msg && dr.msg.kind === "busy"), () => { dr.phase = "edit"; dr.preview = null; draw(REVIEW_TRIGGER); });
    const box = el("details", { class: "raw tech map-builds", open: dr.open || null },
      el("summary", { "data-mb-summary": "" }, "Create with an agent", dr.st ? el("span", { class: "faint", text: ` · ${(dr.st.jobs || []).length} job(s)` }) : null), holder);
    async function load(focus) {
      dr.loading = true; dr.err = null; draw();
      try {
        dr.st = (await getJSON(url)).result;
        if (!dr.brief) { dr.brief = Object.fromEntries(Object.entries(dr.st.defaults || {}).map(([k, v]) => [k, typeof v === "number" ? String(v) : v])); dr.briefBase = JSON.stringify(dr.brief); }
      } catch (e) { dr.err = e; }
      dr.loading = false; draw(focus);
    }
    // Reload after a stale revision: keeps the brief and per-job notes, drops previews tied to the old revision.
    const reload = (focus) => { dr.msg = null; dr.preview = null; dr.phase = "edit"; for (const j of Object.values(dr.jobs)) { j.review = null; j.accept = null; j.msg = null; } load(focus); };
    const staleBox = (e) => el("div", { class: "state state-error", role: "alert", tabindex: "-1", "data-focus": "err" },
      el("strong", { text: "The map jobs or the agent output changed since this page read them. Nothing was written." }),
      el("div", null, el("span", { class: "code", text: `[${txt((e.error || {}).code)}] ` }), txt((e.error || {}).message)),
      el("p", null, "Reload, then review again before accepting. Your brief is kept."),
      el("div", { class: "btn-row" }, el("button", { type: "button", class: "btn btn-small", onclick: () => reload("[data-mb-jobs]") }, "Reload map jobs")));
    const errOf = (e, retry) => mbStale(e) ? staleBox(e) : writeError(e, retry);
    async function post(body) { return postJSON(url, { expected_revision: dr.st.revision, ...body }); }

    function briefForm() {
      const b = dr.brief, errs = dr.showErrors ? mbProblems(b, dr.st.limits) : {};
      const field = (k, label, control, hint) => labelled(`mb-${k}`, label, control, hint, errs[k]);
      const text = (k, attrs) => { const n = el("input", { class: "input", id: `mb-${k}`, value: b[k], autocomplete: "off", "aria-invalid": errs[k] ? "true" : null, "aria-describedby": `mb-${k}-hint`, ...attrs });
        n.addEventListener("input", () => { b[k] = n.value; dr.preview = null; }); return n; };
      const theme = el("textarea", { class: "input", id: "mb-theme", rows: "3", maxlength: "4000", "aria-describedby": "mb-theme-hint" }); theme.value = b.theme || "";
      theme.addEventListener("input", () => { b.theme = theme.value; dr.preview = null; });
      const check = (k, label, hint) => { const n = el("input", { type: "checkbox", id: `mb-${k}`, checked: b[k] || null });
        n.addEventListener("change", () => { b[k] = n.checked; dr.preview = null; });
        return el("div", { class: "edit-field" }, el("label", { for: `mb-${k}`, class: "check" }, n, ` ${label}`), hint ? el("div", { class: "field-meta faint", text: hint }) : null); };
      const busy = dr.msg && dr.msg.kind === "busy";
      return el("form", { class: "edit-form", novalidate: true, onsubmit: async (e) => {
        e.preventDefault(); dr.showErrors = true;
        if (Object.keys(mbProblems(b, dr.st.limits)).length) { draw("#mb-form [aria-invalid=true]"); return; }
        dr.msg = { kind: "busy", text: "Checking the brief..." }; draw();
        try { dr.preview = await post({ action: "create", preview: true, brief: mbBody(b) }); dr.phase = "review"; dr.msg = null; draw("[data-focus=mb-review]"); }
        catch (er) { dr.msg = { kind: "err", err: er }; draw("[data-focus=err]"); }
      }, id: "mb-form" },
        el("fieldset", { class: "edit-group" }, el("legend", { text: "Design brief" }),
          el("div", { class: "edit-grid creator-grid" },
            field("map_id", "Map id", text("map_id", { maxlength: "48", spellcheck: "false" }), "Also the main file name: <id>.map. Must not be an existing map."),
            field("title", "Title", text("title", { maxlength: "120" })),
            MB_INT.map(([k, label, lo, hi]) => field(k, label, text(k, { inputmode: "numeric" }), `${lo}-${hi}`))),
          labelled("mb-theme", "Theme and geography notes", theme, "Optional. Passed to the agent as written.", errs.theme),
          el("div", { class: "edit-grid" }, check("wraparound", "Wraparound", "Full wrapping when ticked."),
            check("all_layers", "All seasonal and terrain layers", "Base, winter and eight terrain looks in both seasons (18 images per plane)."))),
        el("div", { class: "btn-row edit-actions" }, el("button", { type: "submit", class: "btn", disabled: busy || null, ...RT }, "Preview brief"),
          statusLine("Nothing is written until you create the job.")));
    }
    function briefReview() {
      const r = dr.preview, b = r.brief || {}, busy = dr.msg && dr.msg.kind === "busy";
      return el("div", { class: "stack" },
        el("h4", { tabindex: "-1", "data-focus": "mb-review", text: "Review the brief" }),
        el("dl", { class: "kv" }, Object.entries(b).map(([k, v]) => [el("dt", { text: k.replace(/_/g, " ") }), el("dd", { class: k === "theme" ? null : "mono", text: typeof v === "boolean" ? (v ? "yes" : "no") : txt(v) || "—" })])),
        (r.steps || []).length ? [el("h4", { text: "Steps for the agent" }), el("ol", null, r.steps.map((t) => el("li", { text: txt(t) })))] : null,
        el("p", { class: "panel-note", text: "Creating the job writes only its brief under .kosmokrator/map-jobs and an empty output folder. Briefs are immutable: change them by creating a new job." }),
        el("div", { class: "btn-row" },
          el("button", { type: "button", class: "btn", disabled: busy || null, onclick: async () => {
            dr.msg = { kind: "busy", text: "Creating job..." }; draw();
            try {
              const res = await post({ action: "create", preview: false, brief: mbBody(dr.brief) });
              dr.st = res.state || dr.st; dr.phase = "edit"; dr.preview = null; dr.showErrors = false; dr.briefBase = JSON.stringify(dr.brief);
              dr.msg = { kind: "ok", text: `Job ${txt(res.job && res.job.id)} created. Hand the instructions below to Codex or Claude.` };
              if (res.job) dr.jobs[res.job.id] = { ...(dr.jobs[res.job.id] || {}), open: true };
              if (!res.state) await load(); else draw(res.job ? `[data-mb-job="${res.job.id}"]` : null);
              recordReceipt(slug, `Created map job ${txt(res.job && res.job.id)}`, { written: true }, { backupNote: "Not needed: a job writes only its own new brief" });
              toast("Map job created");
            } catch (er) { dr.msg = { kind: "err", err: er }; draw("[data-focus=err]"); }
          } }, "Create job"),
          el("button", { type: "button", class: "btn btn-ghost", disabled: busy || null, onclick: () => { dr.phase = "edit"; dr.preview = null; draw(REVIEW_TRIGGER); } }, "Back to the brief")));
    }
    function reviewReport(job, jd) {
      const r = jd.review, comp = r.compliance || [];
      const mark = (c) => c.passed === true ? badge("pass", "ok") : c.passed === false ? badge("fail", "err") : badge("needs human review", "info");
      return el("div", { class: "stack mb-review" },
        el("h5", { tabindex: "-1", "data-focus": `mb-rev-${job.id}`, text: "Review of the staged output (read-only)" }),
        el("p", null, r.ready ? badge("ready to import", "ok") : badge("not ready", "err"), " ", mapValBadge(r.validation), " ",
          el("span", { class: "faint" }, "Output revision ", el("span", { class: "hash", title: txt(r.output_revision), text: shortRev(r.output_revision) }))),
        comp.length ? el("ul", { class: "diag" }, comp.map((c) => el("li", null, mark(c), el("code", { text: txt(c.check) }), el("span", { text: txt(c.detail) })))) : null,
        mapIssues(r.validation, "No static validation issues."),
        (r.files || []).length ? el("details", { class: "raw" }, el("summary", null, `${r.files.length} file(s), ${fmtBytes(r.files.reduce((n, f) => n + (f.bytes || 0), 0))}`),
          el("div", { class: "inner" }, table(["File", "Size", "SHA-256"], r.files.map((f) => [el("code", { text: txt(f.name) }), fmtBytes(f.bytes || 0), el("span", { class: "hash", title: txt(f.sha256), text: shortSha(f.sha256) })])))) : null,
        el("p", { class: "panel-note", text: r.in_game_tested === false ? "Static checks only. Visual quality, start fairness and in-game behaviour are not tested." : "Static checks only." }));
    }
    function acceptBlock(job, jd) {
      const a = jd.accept, busy = jd.msg && jd.msg.kind === "busy", r = jd.review;
      const run = async (preview) => {
        jd.msg = { kind: "busy", text: preview ? "Checking import..." : "Importing as a new map..." }; draw();
        try {
          const res = await post({ action: "accept", job_id: job.id, preview, expected_output_revision: r.output_revision });
          jd.msg = null;
          if (preview) { jd.accept = res; draw(`[data-focus="mb-acc-${job.id}"]`); return; }
          jd.done = res; jd.accept = null; jd.review = null;
          // Refresh the accepted status and revision before another job operation.
          await load();
          state.authData.delete(mapsUrl(slug));
          recordReceipt(slug, `Imported map ${txt((res.import || {}).id || job.brief.map_id)} from job ${txt(job.id)}`, res.import || res);
          toast("Map imported");
          render();
        } catch (er) { jd.msg = { kind: "err", err: er }; draw("[data-focus=err]"); }
      };
      if (!a) return el("div", { class: "btn-row" },
        el("button", { type: "button", class: "btn", disabled: !r.ready || busy || !CSRF || null, "data-mb-accept": job.id, onclick: () => run(true) }, "Preview import as new map"),
        r.ready ? null : el("span", { class: "faint", text: "Fix the failed checks in the output folder, then review again." }));
      const imp = a.import || {};
      return el("div", { class: "stack" },
        el("h5", { tabindex: "-1", "data-focus": `mb-acc-${job.id}`, text: "Import preview" }),
        el("dl", { class: "kv" }, el("dt", { text: "New map id" }), el("dd", { class: "mono", text: txt(imp.id || job.brief.map_id) }),
          el("dt", { text: "Revision" }), el("dd", { class: "hash", text: shortRev(imp.revision) }),
          el("dt", { text: "Validation" }), el("dd", null, mapValBadge(imp.validation)),
          el("dt", { text: "Files" }), el("dd", { text: txt(countOf(imp.files) ?? "?") })),
        el("p", { class: "panel-note", text: "Import adds a new map bundle under the project. An existing map with this id is never overwritten; the import is refused instead." }),
        el("div", { class: "btn-row" },
          el("button", { type: "button", class: "btn", disabled: busy || null, onclick: () => run(false) }, "Import as new map"),
          el("button", { type: "button", class: "btn btn-ghost", disabled: busy || null, onclick: () => { jd.accept = null; draw(`[data-mb-accept="${job.id}"]`); } }, "Back")));
    }
    function jobCard(job) {
      const jd = dr.jobs[job.id] || (dr.jobs[job.id] = { open: false, review: null, accept: null, msg: null, done: null });
      const [label, kind] = MB_STATUS[job.status] || [txt(job.status).replace(/_/g, " "), "info"];
      const b = job.brief || {}, busy = jd.msg && jd.msg.kind === "busy";
      const handoff = txt(job.handoff || job.prompt);
      const doReview = async () => {
        jd.msg = { kind: "busy", text: "Reviewing output..." }; jd.accept = null; draw();
        try { jd.review = await post({ action: "review", job_id: job.id }); jd.msg = null; draw(`[data-focus="mb-rev-${job.id}"]`); }
        catch (er) { jd.review = null; jd.msg = { kind: "err", err: er }; draw("[data-focus=err]"); }
      };
      const missing = jd.msg && jd.msg.kind === "err" && /map_missing|bad_map_file/.test(((jd.msg.err.error || {}).code) || "");
      const card = el("details", { class: "mb-job", open: jd.open || null, "data-mb-job": job.id },
        el("summary", null, el("strong", { text: txt(b.title || b.map_id) }), " ", el("code", { class: "faint", text: txt(b.map_id) }), " ", badge(label, kind),
          el("span", { class: "faint", text: ` job ${txt(job.id)}` })),
        el("div", { class: "inner stack" },
          el("p", { class: "faint" }, `${txt(b.width)}×${txt(b.height)} · ${txt(b.land_provinces)} land, ${txt(b.sea_provinces)} sea, ${txt(b.cave_provinces)} cave · ${txt(b.players)} players`,
            b.wraparound ? " · wraparound" : "", b.all_layers ? " · all layers" : ""),
          el("p", null, "Output folder: ", el("code", { text: txt(job.output_path) }), el("span", { class: "faint", text: " (relative to the project folder)" })),
          handoff ? el("details", { class: "raw", open: job.status === "awaiting_agent" || null }, el("summary", null, "Instructions for Codex or Claude"),
            el("div", { class: "inner" }, el("pre", { class: "code mb-handoff", tabindex: "0", text: handoff }))) : null,
          el("div", { class: "btn-row" },
            handoff ? el("button", { type: "button", class: "btn btn-small", onclick: () => copy(handoff, "Agent instructions") }, "Copy instructions") : null,
            el("button", { type: "button", class: "btn btn-small", onclick: () => downloadJSON(`${slug}-map-job-${job.id}.json`, job) }, "Download job JSON"),
            el("button", { type: "button", class: "btn btn-small", disabled: busy || !CSRF || null, onclick: doReview }, jd.review ? "Review again" : "Review output")),
          job.status === "awaiting_agent" && !jd.review && !missing ? el("p",{ class: "faint", text: "No output yet. When the agent has written the bundle into the output folder, review it here." }) : null,
          busy ? stateBox("loading", jd.msg.text) : null,
          missing ? stateBox("empty", "No usable map output yet.", `${txt((jd.msg.err.error || {}).message)} The agent writes flat files, including ${txt(b.map_id)}.map, into the output folder.`)
            : jd.msg && jd.msg.kind === "err" ? errOf(jd.msg.err, () => reload(`[data-mb-job="${job.id}"]`)) : null,
          jd.done ? el("div", { class: "state", role: "status" }, el("strong", { text: "Imported as a new map." }), " ",
            el("a", { class: "btn btn-small", href: mapRoute(slug, (jd.done.import || {}).id || b.map_id) }, "Open the map")) : null,
          jd.review ? [reviewReport(job, jd), acceptBlock(job, jd)] : null));
      card.addEventListener("toggle", () => { jd.open = card.open; });
      return card;
    }
    function draw(focus) {
      if (!dr.st) {
        if (dr.err) fillKids(holder, errorBox(dr.err, "map jobs"),
          /^(http_404|not_found|bad_response)$/.test(((dr.err.error || {}).code) || "") ? el("p", { class: "faint", text: "This server may be a build without map jobs. Restart `kosmokrator serve` from an updated checkout." }) : null,
          el("div", { class: "btn-row" }, el("button", { type: "button", class: "btn btn-small", onclick: () => load() }, "Retry")));
        else if (dr.loading) fillKids(holder, stateBox("loading", "Reading map jobs..."));
        else load(focus);
        return;
      }
      const jobs = dr.st.jobs || [];
      const msg = !dr.msg ? null : dr.msg.kind === "err" ? errOf(dr.msg.err, () => reload("#mb-map_id"))
        : dr.msg.kind === "ok" ? el("p", { class: "edit-ok", role: "status", text: dr.msg.text }) : stateBox("loading", dr.msg.text);
      fillKids(holder,
        el("p", { class: "panel-note", text: txt(dr.st.note) || "An agent builds the map through the Kosmokrator CLI or MCP; review it here, then import it as a new map." }),
        loadingNote(),
        msg,
        el("h4", { tabindex: "-1", "data-mb-jobs": "", text: `Jobs (${jobs.length})` }),
        jobs.length ? el("div", { class: "stack mb-jobs" }, [...jobs].reverse().map(jobCard)) : el("p", { class: "muted", text: "No map jobs yet." }),
        el("h4", { text: "New brief" }),
        CSRF ? (dr.phase === "review" && dr.preview ? briefReview() : briefForm()) : noToken(),
        el("p", { class: "faint" }, "Jobs revision ", el("span", { class: "hash", title: txt(dr.st.revision), text: shortRev(dr.st.revision) }), " ",
          el("button", { type: "button", class: "btn btn-small btn-ghost", onclick: () => reload("[data-mb-jobs]") }, "Reload jobs")));
      if (focus) focusIn(holder, focus);
    }
    const loadingNote = () => dr.loading ? stateBox("loading", "Re-reading map jobs...") : null;
    box.addEventListener("toggle", () => { dr.open = box.open; if (box.open && !holder.childNodes.length) draw(); });
    if (dr.open) draw();
    return box;
  }

  function mapEditor(m, data) {
    const slug = m.project.slug, dkey = `${slug}:${data.id}`, idp = `map-${safeId(data.id)}`, dl = `${idp}-dl`;
    const url = `${mapsUrl(slug)}/${encodeURIComponent(data.id)}`;
    const planes = data.planes || [];
    const dr = draftOf(state.maps, dkey, () => ({ plane: (planes[0] || {}).number, sel: null, zoom: 1, labels: false, q: "", stq: "", stOpen: false,
      edits: {}, base: data.revision, form: { command: "", raw: [], province: "" }, cmdr: { owner: "", commander: "", count: "", unit: "" },
      conn: { to: "", kind: "0" }, phase: "edit", preview: null, previewPlane: null, msg: null, exp: { busy: false, result: null, error: null },
      look: "default", winter: false, whole: false, conns: false }));
    if (!planes.some((p) => p.number === dr.plane) && planes.length) dr.plane = planes[0].number;
    const holder = el("div", { class: "stack map-editor" });
    escapeReview(holder, () => dr.phase === "review" && !!dr.preview, () => { dr.phase = "edit"; dr.preview = null; redraw(`#${idp}-review`); });
    const byCmd = new Map((data.commands || []).map((c) => [mapCmd(c.command), c]));
    const kinds = (data.border_types || []).map((k) => [Number(k.value), txt(k.label)]);
    if (!kinds.some(([v]) => v === 0)) kinds.unshift([0, "Normal"]);
    const kindLabel = (k) => { const x = kinds.find(([v]) => v === k); return x ? x[1] : `kind ${k}`; };
    const nationName = (id) => { const n = numberedNations(m).find((x) => x.id === id); return n ? `${txt(n.name || n.uid)} (#${id})` : `nation ${id}`; };
    const reload = () => { state.authData.delete(url); state.authData.delete(mapsUrl(slug)); dr.msg = null; dr.phase = "edit"; dr.preview = null; render(); };
    const countBox = statusLine("");
    const lookStatus = statusLine("");
    lookStatus.classList.add("map-look-status");
    let reviewBtn = null, P = null, bk = null;
    const provName = (p) => { const e = bk.prov[p.id]; return e && "name" in e ? String(e.name) : txt(p.name) || "(unnamed)"; };
    const eff = (p, k) => { const e = bk.prov[p.id]; return e && k in e ? e[k] : p[k]; };
    const provLabel = (id) => { const p = (P.provinces || []).find((x) => x.id === id); return p ? `${id} ${provName(p)}` : String(id); };
    const keepFocus = () => { const a = document.activeElement; return a && a.id && holder.contains(a) ? `#${CSS.escape(a.id)}` : null; };
    // Call before changing the draft: the first change records the revision it was made against.
    const touch = () => { if (!draftSize(dr)) dr.base = data.revision; };
    // After a change: drop any review; structural changes (or a dropped review) redraw, typing only refreshes counts.
    function changed(focusSel) {
      const hadReview = !!dr.preview;
      dr.msg = null; dr.preview = null; dr.phase = "edit";
      if (focusSel !== undefined || hadReview) redraw(focusSel || keepFocus()); else refresh();
    }
    function provSet(p, k, v) {
      touch();
      const e = bk.prov[p.id] || (bk.prov[p.id] = {});
      const same = k === "name" ? String(v).trim() === txt(p.name) : k === "terrain" ? String(v).trim() === txt(p.terrain) : !!v === !!p[k];
      if (same) delete e[k]; else e[k] = v;
      if (!Object.keys(e).length) delete bk.prov[p.id];
    }
    function setConnection(a, b, kind) {
      touch();
      const k = pairKey(a, b), base = planeConnections(P, null).get(k);
      bk.ops = bk.ops.filter((o) => !(o.op === "connection" && pairKey(o.a, o.b) === k));
      if (kind !== (base ? base.base : null)) bk.ops.push({ op: "connection", a, b, kind });
    }
    function select(id, fromList) {
      dr.sel = id;
      redraw(fromList ? `[data-prov-btn="${id}"]` : null);
    }
    function refresh() {
      const { changes, errors } = planeChanges(m, byCmd, P, bk);
      holder.querySelectorAll("[data-err-key]").forEach((n) => { const e = errors.find((x) => x.key === n.dataset.errKey); n.textContent = e ? e.msg : ""; });
      const n = bucketSize(bk), other = draftSize(dr) - n;
      countBox.textContent = (!n ? "No changes on this plane." : errors.length ? `${errors.length} problem(s) to fix before review.`
        : `${changes.length} change(s) ready to review.`) + (other ? ` ${other} more on other planes.` : "");
      if (reviewBtn) reviewBtn.disabled = !CSRF || !changes.length || !!errors.length;
    }
    function send(preview) {
      const r = planeChanges(m, byCmd, P, bk);
      if (r.errors.length || !r.changes.length) { refresh(); return; }
      dr.previewPlane = dr.plane;
      runWrite(dr, `${url}/edit`, { expected_revision: data.revision, plane: dr.plane, changes: r.changes }, preview, redraw, (res) => {
        delete dr.edits[dr.plane]; dr.phase = "edit"; dr.preview = null; dr.base = res && res.revision;
        invalidateAuth(slug);
        recordReceipt(slug, `Saved map ${txt(data.id || data.map_id || "")} plane ${dr.plane}`.replace(/ {2,}/g, " "), res);
        toast(res && res.backup ? `Map saved. Backup: ${res.backup}` : "Map saved.");
        render();
      });
    }

    function exportSection() {
      const ex = dr.exp, r = ex.result, e = ex.error && ex.error.error;
      const run = async () => {
        ex.busy = true; ex.error = null; ex.result = null; redraw();
        try { ex.result = await postJSON(`${url}/export`, { expected_revision: data.revision }); } catch (err) { ex.error = err; }
        ex.busy = false; redraw(`#${idp}-xout`);
      };
      return el("div", { class: "map-export stack" },
        el("div", { class: "btn-row" },
          el("button", { type: "button", class: "btn btn-small", disabled: !CSRF || ex.busy || null, onclick: run }, ex.busy ? "Exporting…" : "Export map"),
          draftSize(dr) ? el("span", { class: "faint", text: "Unsaved draft changes are not included." }) : null),
        ex.busy ? stateBox("loading", "Packaging the saved map...") : null,
        e ? el("div", { class: "state state-error", role: "alert", id: `${idp}-xout`, tabindex: "-1" }, el("strong", { text: "Not exported." }),
          el("div", null, el("span", { class: "code", text: `[${txt(e.code)}] ` }), txt(e.message)),
          ex.error.status === 409 ? el("div", { class: "btn-row" }, el("button", { type: "button", class: "btn btn-small", onclick: () => { ex.error = null; reload(); } }, "Reload saved map")) : null) : null,
        r ? el("div", { class: "stack", id: `${idp}-xout`, tabindex: "-1", role: "status" },
          el("p", null, el("strong", { text: "Map package written." }), r.revision === data.revision ? null : [" ", badge(`revision ${shortRev(r.revision)}`, "warn")]),
          (r.files || []).length ? el("ul", { class: "plain-list chips" }, r.files.map((f) => el("li", null, el("code", { text: txt(typeof f === "string" ? f : f.name || f.path) })))) : null,
          el("div", { class: "btn-row" }, apiUrl(r.url) ? el("a", { class: "btn", href: r.url, download: "" }, "Download ZIP") : el("span", { class: "faint", text: "The server returned no download link." })),
          el("p", { class: "panel-note", text: "A separate map package; nothing is installed. In Dominions 6, enable this mod and its dependencies in their listed order when you play the map." })) : null);
    }
    function header() {
      const planeSel = planes.length > 1 ? el("div", { class: "btn-row seg", role: "group", "aria-label": "Plane" }, planes.map((p) =>
        el("button", { type: "button", class: "btn btn-small", "aria-pressed": p.number === dr.plane ? "true" : "false",
          onclick: () => { dr.plane = p.number; dr.sel = null; redraw('[aria-label="Plane"] [aria-pressed="true"]'); } },
          `${txt(p.title || `Plane ${p.number}`)}${bucketSize(dr.edits[p.number]) ? " •" : ""}`))) : null;
      return el("section", { class: "panel map-head", "aria-labelledby": `${idp}-h` },
        el("p", { class: "faint" }, el("a", { href: mapRoute(slug) }, "All maps")),
        el("h3", { id: `${idp}-h`, text: txt(data.title || data.id) }),
        el("p", null, mapValBadge(data.validation), " ",
          el("span", { class: "faint", title: `Revision ${txt(data.revision)}` }, el("code", { text: txt(data.id) }), ` · revision ${shortRev(data.revision)}`)),
        el("div", { class: "btn-row" }, planeSel,
          apiUrl(data.source_url) ? el("a", { class: "btn btn-small btn-ghost", href: `${data.source_url}?plane=${dr.plane}`, target: "_blank", rel: "noopener" }, "Open .map source") : null),
        draftSize(dr) && dr.base !== data.revision ? el("p", { class: "panel-note", role: "note" }, badge("revision changed", "warn"),
          " The map changed after this draft started. Review again before saving.") : null,
        techSection("Export", !!(dr.exp.result || dr.exp.error || dr.exp.busy), exportSection()));
    }
    // Terrain-look preview: local to this page, never part of the draft. #pb rows (x, y counted from the bottom,
    // length, province) are the same authoritative ownership the server uses for province positions.
    let spanPlane = null, spanIndex = null;
    function pbRects(pid) {
      if (spanPlane !== P) {
        spanPlane = P; spanIndex = new Map();
        const h = (P.image || {}).height || P.height;
        for (const s of P.statements || []) {
          if (s.command !== "pb" || !Array.isArray(s.args) || s.args.length !== 4 || !s.args.every(Number.isInteger)) continue;
          const [x, y, len, id] = s.args;
          if (!spanIndex.has(id)) spanIndex.set(id, []);
          spanIndex.get(id).push([x, h - 1 - y, len]);
        }
      }
      return spanIndex.get(pid) || [];
    }
    function lookPreview() {
      if (dr.look === "default" && !dr.winter) return null;
      const v = ((P.image || {}).variants || []).find((x) => x.look === dr.look && x.winter === dr.winter);
      if (!v) return { v: { file: "", available: false, note: "Terrain looks need a TGA map image." }, c: null };
      if (!v.available || !apiUrl(v.url)) return { v, c: null };
      const key = `${data.revision}|${v.url}`;
      if (!mapLookImgs.has(key)) loadLook(key, v.url);
      return { v, c: mapLookImgs.get(key) };
    }
    function loadLook(key, src) {
      for (const [k, o] of mapLookImgs) if (k.includes(`|${url}/image`) && !k.startsWith(`${data.revision}|`)) { if (o.src) URL.revokeObjectURL(o.src); mapLookImgs.delete(k); }
      const c = { src: null, err: false };
      mapLookImgs.set(key, c);
      fetch(src, { credentials: "same-origin" }).then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.blob(); })
        .then((b) => { c.src = URL.createObjectURL(b); }, () => { c.err = true; })
        .finally(() => { if (holder.isConnected) redraw(keepFocus()); });
    }
    // Short status in plain words; image file names, server notes and #pb details live in lookDetails().
    const lookName = () => `${(MAP_LOOKS.find(([v]) => v === dr.look) || [, dr.look])[1]}${dr.winter ? ", winter" : ""}`;
    function lookText(lk) {
      if (!lk) return "Showing the saved map. Previews never change province terrain.";
      const f = lookName();
      if (!lk.v.available) return `${f} is not in this map's bundle; the saved map is shown.`;
      if (!lk.c || (!lk.c.src && !lk.c.err)) return `Loading ${f}…`;
      if (lk.c.err) return `Could not load ${f}. Showing the saved map; reset the preview to retry.`;
      if (dr.sel == null || dr.whole) return `Previewing ${f} on the whole map.`;
      return pbRects(dr.sel).length ? `Previewing ${f} in province ${provLabel(dr.sel)} only.`
        : `Previewing ${f} on the whole map (province ${provLabel(dr.sel)} has no painted area).`;
    }
    function lookDetails(lk) {
      if (!lk) return null;
      const rects = dr.sel != null ? pbRects(dr.sel) : [];
      return el("details", { class: "map-look-more" }, el("summary", null, "Preview details"),
        el("dl", { class: "kv" },
          el("dt", { text: "Image file" }), el("dd", null, lk.v.file ? el("code", { text: txt(lk.v.file) }) : el("span", { class: "faint", text: "none" })),
          el("dt", { text: "In bundle" }), el("dd", { text: lk.v.available ? "yes" : "no" }),
          lk.v.note ? [el("dt", { text: "Note" }), el("dd", { text: txt(lk.v.note) })] : null,
          dr.sel != null ? [el("dt", { text: "Province area" }), el("dd", { text: rects.length
            ? `${rects.length} #pb row(s) for province ${provLabel(dr.sel)}; the look is clipped to them${dr.whole ? " unless Whole map is on" : ""}.`
            : `Province ${provLabel(dr.sel)} has no #pb rows.` })] : null),
        el("p", { class: "faint", text: "Terrain previews follow the Map Making Manual." }));
    }
    function lookLayer(lk, W, H) {
      const src = lk && lk.c && lk.c.src;
      if (!src) return null;
      const rects = dr.sel != null && !dr.whole ? pbRects(dr.sel) : [];
      const pic = (extra) => svgEl("image", { class: "map-look", href: src, x: 0, y: 0, width: W, height: H, preserveAspectRatio: "none", ...extra });
      if (!rects.length) return pic({});
      const shape = () => rects.map(([x, y, w]) => svgEl("rect", { x, y, width: w, height: 1 }));
      // Dim everything outside the province so the replaced area reads as isolated.
      return [svgEl("defs", null,
        svgEl("clipPath", { id: `${idp}-lookclip`, clipPathUnits: "userSpaceOnUse" }, shape()),
        svgEl("mask", { id: `${idp}-lookmask`, maskUnits: "userSpaceOnUse", x: 0, y: 0, width: W, height: H },
          svgEl("rect", { x: 0, y: 0, width: W, height: H, fill: "#fff" }),
          svgEl("g", { fill: "#000", "shape-rendering": "crispEdges" }, shape()))),
        svgEl("rect", { class: "map-look-dim", x: 0, y: 0, width: W, height: H, mask: `url(#${idp}-lookmask)` }),
        pic({ "clip-path": `url(#${idp}-lookclip)` })];
    }
    function mapSvg(placed) {
      const img = P.image || {};
      const W = P.width > 0 ? P.width : Math.max(...placed.map((p) => p.position.x)) + 20;
      const H = P.height > 0 ? P.height : Math.max(...placed.map((p) => p.position.y)) + 20;
      const r = Math.max(3, Math.min(W, H) / 90);
      const pos = new Map(placed.map((p) => [p.id, p.position]));
      const conns = [...planeConnections(P, bk).values()], near = new Set();
      for (const c of conns) { if (c.a === dr.sel) near.add(c.b); if (c.b === dr.sel) near.add(c.a); }
      const lk = lookPreview(), layer = lookLayer(lk, W, H);
      const svg = svgEl("svg", { class: "map-svg", viewBox: `0 0 ${W} ${H}`, role: "img",
        "aria-label": `Plane ${P.number}: ${placed.length} positioned provinces.${layer ? ` ${lookText(lk)}` : ""} Choose provinces with the keyboard from the province list.` },
        apiUrl(img.preview_url) ? svgEl("image", { href: img.preview_url, x: 0, y: 0, width: W, height: H, preserveAspectRatio: "none" })
          : svgEl("rect", { class: "map-bg", x: 0, y: 0, width: W, height: H }),
        layer,
        dr.conns ? svgEl("g", { class: "map-conns" }, conns.filter((c) => pos.has(c.a) && pos.has(c.b)).map((c) => {
          const pa = pos.get(c.a), pb = pos.get(c.b);
          // Wrap-around links would cross the whole map; they are drawn faint.
          const wrap = Math.abs(pa.x - pb.x) > W / 2 || Math.abs(pa.y - pb.y) > H / 2;
          return svgEl("line", { x1: pa.x, y1: pa.y, x2: pb.x, y2: pb.y, "vector-effect": "non-scaling-stroke",
            class: `conn k${[1, 2, 4, 8].includes(c.kind) ? c.kind : c.kind ? "x" : 0} ${c.st}${wrap ? " wrap" : ""}${c.a === dr.sel || c.b === dr.sel ? " near" : ""}` });
        })) : null,
        svgEl("g", { class: "map-provs" }, placed.map((p) => {
          const sel = p.id === dr.sel, nb = near.has(p.id);
          return svgEl("g", { class: `prov${sel ? " sel" : nb ? " near" : ""}${bk.prov[p.id] ? " edited" : ""}${eff(p, "start") ? " start" : ""}`, onclick: () => select(p.id) },
            svgEl("title", { text: `${p.id} ${provName(p)}` }),
            svgEl("circle", { cx: p.position.x, cy: p.position.y, r: sel ? r * 1.5 : r, "vector-effect": "non-scaling-stroke" }),
            dr.labels || sel || nb ? svgEl("text", { x: p.position.x, y: p.position.y - r * 1.7, "text-anchor": "middle", "font-size": r * 2.2, text: String(p.id) }) : null);
        })));
      svg.style.width = `${dr.zoom * 100}%`;
      return svg;
    }
    function viewer() {
      const provs = P.provinces || [], img = P.image || {};
      const placed = provs.filter((p) => p.position && Number.isFinite(p.position.x) && Number.isFinite(p.position.y));
      const zoom = el("div", { class: "btn-row seg", role: "group", "aria-label": "Map zoom" }, [1, 2, 4].map((z) =>
        el("button", { type: "button", class: "btn btn-small", "aria-pressed": dr.zoom === z ? "true" : "false", onclick: () => { dr.zoom = z; redraw('[aria-label="Map zoom"] [aria-pressed="true"]'); } }, `${z}x`)));
      const lbl = el("input", { type: "checkbox", id: `${idp}-labels` });
      lbl.checked = dr.labels;
      lbl.addEventListener("change", () => { dr.labels = lbl.checked; redraw(`#${idp}-labels`); });
      // Connection lines are off by default so the map's own painted borders stay readable; editing is unaffected.
      const cn = el("input", { type: "checkbox", id: `${idp}-conns` });
      cn.checked = dr.conns;
      cn.addEventListener("change", () => { dr.conns = cn.checked; redraw(`#${idp}-conns`); });
      const looks = img.variants || [];
      const has = (look, winter) => looks.some((x) => x.look === look && x.winter === winter && x.available);
      const lookSel = el("select", { class: "input", id: `${idp}-look` }, MAP_LOOKS.map(([v, l]) => {
        const o = el("option", { value: v, text: `${l}${has(v, dr.winter) ? "" : " (not in bundle)"}` });
        if (v === dr.look) o.selected = true;
        return o;
      }));
      lookSel.addEventListener("change", () => { dr.look = lookSel.value; redraw(`#${idp}-look`); });
      const winter = el("input", { type: "checkbox", id: `${idp}-winter` });
      winter.checked = dr.winter;
      winter.addEventListener("change", () => { dr.winter = winter.checked; redraw(`#${idp}-winter`); });
      const whole = el("input", { type: "checkbox", id: `${idp}-whole`, disabled: dr.sel == null || null });
      whole.checked = dr.whole || dr.sel == null;
      whole.addEventListener("change", () => { dr.whole = whole.checked; redraw(`#${idp}-whole`); });
      const reset = el("button", { type: "button", class: "btn btn-small", disabled: (dr.look === "default" && !dr.winter && !dr.whole) || null,
        onclick: () => {
          for (const [k, o] of mapLookImgs) if (o.err) mapLookImgs.delete(k);
          dr.look = "default"; dr.winter = false; dr.whole = false; redraw(`#${idp}-look`);
        } }, "Reset preview");
      lookStatus.textContent = looks.length ? lookText(lookPreview()) : "";
      const lookTools = looks.length ? el("div", { class: "btn-row map-tools map-look-tools", role: "group", "aria-label": "Terrain look preview" },
        el("label", { for: lookSel.id, class: "faint" }, "Terrain look"), lookSel,
        el("label", { for: winter.id, class: "faint" }, winter, " Winter"),
        el("label", { for: whole.id, class: "faint", title: "Without a selected province the look covers the whole map." }, whole, " Whole map"),
        reset) : null;
      const legend = kinds.filter(([v]) => v).map(([v, l]) => el("span", { class: `map-key k${[1, 2, 4, 8].includes(v) ? v : "x"}` }, el("span", { class: "swatch", "aria-hidden": "true" }), l));
      return el("section", { class: "panel map-view", "aria-labelledby": `${idp}-vh` },
        el("h3", { id: `${idp}-vh`, text: `Plane ${P.number}${P.title ? `: ${P.title}` : ""}` }),
        el("div", { class: "btn-row map-tools" }, el("span", { class: "faint", text: "Zoom" }), zoom,
          el("label", { for: lbl.id, class: "faint" }, lbl, " Show all numbers"),
          el("label", { for: cn.id, class: "faint" }, cn, " Show connections"),
          img.kind === "d6m" ? badge("schematic .d6m outline", "info") : null),
        lookTools, looks.length ? lookStatus : null, looks.length ? lookDetails(lookPreview()) : null,
        placed.length ? el("div", { class: "map-scroll" }, mapSvg(placed)) : stateBox("empty", "No province positions on this plane.", "Choose provinces from the list."),
        img.note && !looks.length ? el("p", { class: "faint", text: txt(img.note) }) : null,
        dr.conns && legend.length ? el("p", { class: "map-legend faint" }, legend) : null,
        !dr.conns && dr.sel != null ? el("p", { class: "faint", text: "Neighbours of the selected province are outlined. Turn on Show connections to see every link." }) : null,
        placed.length && placed.length < provs.length ? el("p", { class: "panel-note", text: `${provs.length - placed.length} province(s) have no position and appear only in the list.` }) : null);
    }
    function provinceList() {
      const provs = P.provinces || [];
      const q = el("input", { type: "search", class: "input", id: `${idp}-q`, placeholder: "Number or name", value: dr.q, autocomplete: "off", "aria-controls": `${idp}-list` });
      const items = provs.map((p) => el("li", { "data-q": `${p.id} ${provName(p)}`.toLowerCase() },
        el("button", { type: "button", class: "map-prov-btn", "data-prov-btn": p.id, "aria-pressed": p.id === dr.sel ? "true" : "false", onclick: () => select(p.id, true) },
          el("span", { class: "mono", text: String(p.id) }), el("span", { class: "nm", text: provName(p) }),
          eff(p, "start") ? badge("start", "ok") : null, eff(p, "nostart") ? badge("no start", "") : null,
          p.position ? null : badge("no position", "warn"), bk.prov[p.id] ? badge("edited", "warn") : null)));
      const filter = () => { const t = q.value.trim().toLowerCase(); for (const li of items) li.hidden = !!t && !li.dataset.q.includes(t); };
      q.addEventListener("input", () => { dr.q = q.value; filter(); });
      filter();
      return el("section", { class: "panel map-list" }, el("label", { for: q.id, class: "lbl", text: `Provinces (${provs.length})` }), q,
        el("ul", { class: "map-prov-list", id: `${idp}-list`, "aria-label": "Provinces" }, items));
    }
    function provincePanel() {
      const p = (P.provinces || []).find((x) => x.id === dr.sel);
      const box = el("section", { class: "panel map-side", "aria-labelledby": `${idp}-sh` });
      if (!p) { fillKids(box, el("h3", { id: `${idp}-sh`, text: "Province" }), stateBox("empty", "No province selected.", "Choose one on the map or in the list.")); return box; }
      const pid = `${idp}-p${p.id}`;
      const nameIn = el("input", { class: "input" + ("name" in (bk.prov[p.id] || {}) ? " changed" : ""), id: `${pid}-name`, autocomplete: "off", value: provName(p) === "(unnamed)" && !txt(p.name) ? "" : provName(p) });
      nameIn.addEventListener("input", () => { provSet(p, "name", nameIn.value); nameIn.classList.toggle("changed", "name" in (bk.prov[p.id] || {})); changed(); });
      const flagBox = (k, label) => {
        const cb = el("input", { type: "checkbox", id: `${pid}-${k}` });
        cb.checked = !!eff(p, k);
        cb.addEventListener("change", () => { provSet(p, k, cb.checked); changed(); });
        return el("label", { for: cb.id }, cb, ` ${label}`);
      };
      // Terrain: the number is the source of truth; flag boxes add or subtract their value arithmetically.
      const tIn = el("input", { class: "input num-input", id: `${pid}-t`, inputmode: "numeric", autocomplete: "off", value: txt(eff(p, "terrain")), "aria-describedby": `${pid}-t-hint` });
      const flags = (data.terrain_flags || []).filter((f) => Number(f.value) > 0);
      const boxes = flags.map((f) => el("input", { type: "checkbox", id: `${pid}-f${safeId(f.value)}`, "data-flag": String(f.value) }));
      const syncBoxes = () => {
        const t = tIn.value.trim(), n = /^\d+$/.test(t) ? Number(t) : NaN, ok = Number.isSafeInteger(n);
        for (const cb of boxes) { cb.disabled = !ok; cb.checked = ok && hasFlag(n, Number(cb.dataset.flag)); }
      };
      tIn.addEventListener("input", () => { provSet(p, "terrain", tIn.value); syncBoxes(); changed(); });
      boxes.forEach((cb) => cb.addEventListener("change", () => {
        const n = Number(tIn.value.trim()), v = Number(cb.dataset.flag);
        if (!Number.isSafeInteger(n)) return;
        const next = cb.checked ? (hasFlag(n, v) ? n : n + v) : (hasFlag(n, v) ? n - v : n);
        tIn.value = String(next); provSet(p, "terrain", tIn.value); changed();
      }));
      syncBoxes();
      const conns = [...planeConnections(P, bk).values()].filter((c) => c.a === p.id || c.b === p.id).sort((x, y) => (x.a === p.id ? x.b : x.a) - (y.a === p.id ? y.b : y.a));
      const connRows = conns.map((c) => {
        const other = c.a === p.id ? c.b : c.a, sid = `${pid}-c${other}`;
        const sel = el("select", { class: "input", id: sid, disabled: c.st === "removed" || null, "aria-label": `Border with ${provLabel(other)}` }, kinds.map(([v, l]) => el("option", { value: String(v), text: l })));
        if (!kinds.some(([v]) => v === c.kind)) sel.prepend(el("option", { value: String(c.kind), text: kindLabel(c.kind) }));
        sel.value = String(c.kind);
        sel.addEventListener("change", () => { setConnection(p.id, other, Number(sel.value)); changed(`#${sid}`); });
        return el("li", { class: "map-conn-row" + (c.st === "removed" ? " removing" : "") },
          el("button", { type: "button", class: "linkish", onclick: () => select(other) }, provLabel(other)), sel,
          c.st !== "base" ? badge(c.st, c.st === "removed" ? "err" : "warn") : null,
          c.st === "removed" ? el("button", { type: "button", class: "btn btn-small", id: `${sid}-x`, onclick: () => { setConnection(p.id, other, c.base); changed(`#${sid}-x`); } }, "Undo")
            : el("button", { type: "button", class: "btn btn-small btn-ghost", id: `${sid}-x`, "aria-label": `Remove connection to ${provLabel(other)}`,
              onclick: () => { setConnection(p.id, other, null); changed(c.base === null ? `#${pid}-to` : `#${sid}-x`); } }, "Remove"));
      });
      const to = el("input", { class: "input num-input", id: `${pid}-to`, list: `${dl}-province`, inputmode: "numeric", autocomplete: "off", value: dr.conn.to, "aria-describedby": `${pid}-to-err` });
      to.addEventListener("input", () => { dr.conn.to = to.value; });
      const kindSel = el("select", { class: "input", id: `${pid}-tok`, "aria-label": "Border type for the new connection" }, kinds.map(([v, l]) => el("option", { value: String(v), text: l })));
      kindSel.value = dr.conn.kind;
      kindSel.addEventListener("change", () => { dr.conn.kind = kindSel.value; });
      const toErr = el("div", { class: "field-err", id: `${pid}-to-err`, "aria-live": "polite" });
      const addConn = () => {
        const t = to.value.trim(), n = Number(t);
        const err = !/^\d+$/.test(t) ? "Enter a province number." : !(P.provinces || []).some((x) => x.id === n) ? `No province ${t} on this plane.`
          : n === p.id ? "A province cannot border itself." : conns.some((c) => (c.a === n || c.b === n) && c.st !== "removed") ? "Already connected; change its border type above." : "";
        if (err) { toErr.textContent = err; to.focus(); return; }
        setConnection(p.id, n, Number(kindSel.value)); dr.conn.to = ""; changed(`#${pid}-to`);
      };
      to.addEventListener("keydown", (ev) => { if (ev.key === "Enter") { ev.preventDefault(); addConn(); } });
      const pending = (line) => bk.ops.findIndex((o) => (o.op === "remove" || o.op === "replace") && o.line === line);
      const lines = planeLines(P);
      const cmdRows = (p.commands || []).map((c) => {
        const s = lines.get(c.line), i = pending(c.line), bid = `${pid}-l${c.line}`;
        return el("li", { class: "map-cmd-row" }, el("span", { class: "src-ref", text: `L${c.line}` }), el("code", { class: "cmd-raw", text: txt(c.raw) }),
          i >= 0 ? [badge(bk.ops[i].op === "remove" ? "will be removed" : "changing", bk.ops[i].op === "remove" ? "err" : "warn"),
            el("button", { type: "button", class: "btn btn-small", id: bid, onclick: () => { bk.ops.splice(i, 1); changed(`#${bid}`); } }, "Undo")]
            : s && s.editable ? el("button", { type: "button", class: "btn btn-small btn-ghost", id: bid, "aria-label": `Remove line ${c.line}`,
              onclick: () => { touch(); bk.ops.push({ op: "remove", line: c.line, was: s.raw }); changed(`#${bid}`); } }, "Remove")
              : badge("read-only", "warn"));
      });
      const adds = bk.ops.filter((o) => o.op === "add" && o.province === p.id);
      const facts = el("dl", { class: "kv" },
        el("dt", { text: "Position" }), el("dd", { text: p.position ? `${p.position.x}, ${p.position.y}` : "none (list only)" }),
        el("dt", { text: "Terrain in file" }), el("dd", { text: (p.terrain_labels || []).length ? p.terrain_labels.join(", ") : "plain" }),
        (p.specstarts || []).length ? [el("dt", { text: "Start for" }), el("dd", { text: p.specstarts.map(nationName).join(", ") })] : null,
        (p.gates || []).length ? [el("dt", { text: "Gates" }), el("dd", { text: p.gates.join(", ") })] : null);
      fillKids(box,
        el("h3", { id: `${idp}-sh`, tabindex: "-1", text: `Province ${p.id}: ${provName(p)}` }), facts,
        el("fieldset", { class: "edit-group" }, el("legend", { text: "Province" }),
          labelled(nameIn.id, "Name", nameIn),
          el("div", { class: "btn-row" }, flagBox("start", "Start province"), flagBox("nostart", "No start")),
          el("div", { class: "field-err", "data-err-key": `p${p.id}`, "aria-live": "polite" })),
        el("fieldset", { class: "edit-group" }, el("legend", { text: "Terrain" }),
          labelled(tIn.id, "Terrain mask", tIn),
          el("div", { class: "field-meta faint", id: `${pid}-t-hint`, text: "Sum of the flags below; values beyond 2^31 are kept exactly." }),
          flags.length ? el("div", { class: "map-flags", role: "group", "aria-label": "Terrain flags" }, flags.map((f, i) =>
            el("label", { for: boxes[i].id, title: String(f.value) }, boxes[i], ` ${txt(f.label)}`))) : null),
        el("fieldset", { class: "edit-group" }, el("legend", { text: `Connections (${conns.filter((c) => c.st !== "removed").length})` }),
          connRows.length ? el("ul", { class: "plain-list" }, connRows) : el("p", { class: "faint", text: "No neighbours." }),
          el("div", { class: "edit-control map-conn-add" }, el("label", { for: to.id, class: "faint", text: "Add neighbour" }), to, kindSel,
            el("button", { type: "button", class: "btn btn-small", onclick: addConn }, "Add")), toErr),
        el("fieldset", { class: "edit-group" }, el("legend", { text: "Scenario commands" }),
          cmdRows.length ? el("ul", { class: "plain-list" }, cmdRows) : el("p", { class: "faint", text: "None in the file." }),
          adds.length ? el("ul", { class: "plain-list" }, adds.map((o) => el("li", null, badge("to add", "authored"), " ", el("code", { text: `#${mapCmd(o.command)} ${o.raw.join(" ")}` })))) : null,
          el("p", { class: "faint", text: "Add commands for this province below the map." })));
      return box;
    }
    // Adds the ops only if every one of them would be accepted (the commander context included); reset() clears the form first.
    function pushOps(ops, err, focusSel, reset) {
      const all = [...bk.ops, ...ops];
      for (let i = bk.ops.length; i < all.length; i++) { const r = mapOpChange(m, byCmd, P, all, i); if (r.err) { err.textContent = r.err; return; } }
      reset(); touch(); bk.ops.push(...ops); changed(focusSel);
    }
    function addPanel() {
      const f = dr.form, spec = byCmd.get(f.command), sel = dr.sel;
      const presets = [["specstart", "Start for a nation"], ["gate", "Gate"], ["feature", "Site"], ["knownfeature", "Known site"], ["owner", "Owner"]].filter(([c]) => byCmd.has(c));
      const choose = (c) => {
        const s = byCmd.get(c);
        f.command = c; f.province = sel != null ? String(sel) : "";
        f.raw = ((s && s.args) || []).map((a) => (mapArgKind(a, c) === "province" && sel != null ? String(sel) : ""));
        redraw(`#${idp}-a-0, #${idp}-aprov, #${idp}-acmd`);
      };
      const err = el("div", { class: "field-err", "aria-live": "polite" });
      const adv = el("select", { class: "input", id: `${idp}-acmd` }, el("option", { value: "", text: "Choose a command…" }),
        [...byCmd.keys()].sort().map((k) => el("option", { value: k, text: `#${k}${byCmd.get(k).scope !== "global" ? ` (${byCmd.get(k).scope})` : ""}` })));
      adv.value = f.command;
      adv.addEventListener("change", () => choose(adv.value));
      let form = null;
      if (spec) {
        const scoped = spec.scope !== "global";
        const provIn = scoped ? el("input", { class: "input num-input", id: `${idp}-aprov`, list: `${dl}-province`, inputmode: "numeric", autocomplete: "off", value: f.province }) : null;
        if (provIn) provIn.addEventListener("input", () => { f.province = provIn.value; err.textContent = ""; });
        form = el("div", { class: "stack map-add-form" },
          el("p", null, el("code", { text: `#${mapCmd(spec.command)}` }), " ", badge(txt(spec.scope), "info"),
            el("span", { class: "faint", text: spec.scope === "province" ? " Written after #setland for the province." : spec.scope === "commander" ? " Modifies the #commander added before it in this draft." : "" })),
          provIn ? labelled(provIn.id, "Province", provIn) : null,
          mapArgControls(spec.args || [], f.raw, `${idp}-a`, () => { err.textContent = ""; }, spec.command, dl), err,
          el("div", { class: "btn-row" },
            el("button", { type: "button", class: "btn btn-small", onclick: () => {
              const pt = String(f.province).trim(), prov = scoped ? (pt === "" ? NaN : Number(pt)) : undefined;
              pushOps([{ op: "add", command: mapCmd(spec.command), raw: [...f.raw], province: scoped ? prov : undefined }], err, `#${idp}-acmd`,
                () => { dr.form = { command: "", raw: [], province: "" }; });
            } }, `Add #${mapCmd(spec.command)}`),
            el("button", { type: "button", class: "btn btn-small btn-ghost", onclick: () => { dr.form = { command: "", raw: [], province: "" }; redraw(`#${idp}-acmd`); } }, "Cancel")));
      }
      return el("section", { class: "panel map-add", "aria-labelledby": `${idp}-ah` },
        el("h3", { id: `${idp}-ah`, text: "Add map commands" }),
        presets.length ? el("div", { class: "btn-row" }, presets.map(([c, l]) =>
          el("button", { type: "button", class: "btn btn-small", "aria-pressed": f.command === c ? "true" : "false", onclick: () => choose(c) }, l))) : null,
        commanderForm(),
        el("details", { class: "raw", open: (f.command && !presets.some(([c]) => c === f.command)) || null },
          el("summary", null, `Advanced: any of ${byCmd.size} map commands`),
          el("div", { class: "inner" }, labelled(adv.id, "Command", adv))),
        form);
    }
    // #commander with optional #owner first and #units after, all in one batch so the server sees the commander context.
    function commanderForm() {
      if (!byCmd.has("commander")) return null;
      const c = dr.cmdr, p = (P.provinces || []).find((x) => x.id === dr.sel), cid = `${idp}-cm`;
      const err = el("div", { class: "field-err", "aria-live": "polite" });
      const inp = (k, label, list, numeric) => {
        const i = el("input", { class: "input" + (numeric ? " num-input" : ""), id: `${cid}-${k}`, list: list ? `${dl}-${list}` : null, autocomplete: "off", inputmode: numeric ? "numeric" : null, value: c[k] });
        i.addEventListener("input", () => { c[k] = i.value; err.textContent = ""; });
        return labelled(i.id, label, i);
      };
      const one = (cmd, vals) => { const s = byCmd.get(cmd); return s && (s.args || []).length === vals.length ? { op: "add", command: cmd, raw: vals, province: p && p.id } : null; };
      const add = () => {
        if (!p) { err.textContent = "Select a province first."; return; }
        if (!c.commander.trim()) { err.textContent = "Enter the commander's monster."; return; }
        const ops = [];
        if (c.owner.trim()) { const o = one("owner", [c.owner]); if (!o) { err.textContent = "#owner is not available here; use Advanced."; return; } ops.push(o); }
        const cm = one("commander", [c.commander]);
        if (!cm) { err.textContent = "#commander takes different arguments here; use Advanced."; return; }
        ops.push(cm);
        if (c.count.trim() || c.unit.trim()) {
          const s = byCmd.get("units");
          if (!s || (s.args || []).length !== 2) { err.textContent = "#units is not available here; use Advanced."; return; }
          ops.push({ op: "add", command: "units", raw: s.args.map((a) => (a.type === "int" ? c.count : c.unit)), province: p.id });
        }
        pushOps(ops, err, `#${cid}-commander`, () => { dr.cmdr = { owner: c.owner, commander: "", count: "", unit: "" }; });
      };
      return el("details", { class: "raw", open: !!(c.commander || c.unit) || null },
        el("summary", null, "Commander with units"),
        el("div", { class: "inner stack" },
          el("p", { class: "faint", text: p ? `For province ${p.id} ${provName(p)}.` : "Select a province first." }),
          el("div", { class: "edit-grid" }, byCmd.has("owner") ? inp("owner", "Owner nation (optional)", "nation", true) : null,
            inp("commander", "Commander monster", "monster"), byCmd.has("units") ? [inp("count", "Units", null, true), inp("unit", "Unit monster", "monster")] : null),
          el("p", { class: "faint", text: "Project monsters are written by name, as the manual requires for custom monsters." }), err,
          el("div", { class: "btn-row" }, el("button", { type: "button", class: "btn btn-small", disabled: !p || null, onclick: add }, "Add commander"))));
    }
    function draftPanel() {
      const items = [];
      for (const [id, e] of Object.entries(bk.prov)) {
        const parts = Object.entries(e).map(([k, v]) => k === "name" ? `name "${String(v).trim()}"` : k === "terrain" ? `terrain ${String(v).trim()}` : `${k} ${v ? "on" : "off"}`);
        items.push(el("li", null, el("span", { text: `Province ${provLabel(Number(id))}: ${parts.join(", ")}` }), " ",
          el("button", { type: "button", class: "btn btn-small btn-ghost", onclick: () => { delete bk.prov[id]; changed(`#${idp}-review`); } }, "Drop"),
          el("div", { class: "field-err", "data-err-key": `p${id}`, "aria-live": "polite" })));
      }
      bk.ops.forEach((o, i) => {
        const label = o.op === "connection" ? (o.kind === null ? `Remove connection ${provLabel(o.a)} – ${provLabel(o.b)}` : `Connection ${provLabel(o.a)} – ${provLabel(o.b)}: ${kindLabel(o.kind)}`)
          : o.op === "remove" ? `Remove line ${o.line}: ${o.was}` : o.op === "replace" ? `Change line ${o.line}: #${mapCmd(o.command)} ${o.raw.join(" ")}`
          : `Add #${mapCmd(o.command)} ${o.raw.join(" ")}${o.province !== undefined ? ` (province ${provLabel(o.province)})` : ""}`;
        items.push(el("li", null, el("span", { text: label }), " ",
          el("button", { type: "button", class: "btn btn-small btn-ghost", onclick: () => { bk.ops.splice(i, 1); changed(`#${idp}-review`); } }, "Drop"),
          el("div", { class: "field-err", "data-err-key": `o${i}`, "aria-live": "polite" })));
      });
      reviewBtn = el("button", { type: "button", class: "btn", id: `${idp}-review`, onclick: () => send(true) }, "Review changes");
      return el("section", { class: "panel map-draft", "aria-labelledby": `${idp}-dh` },
        el("h3", { id: `${idp}-dh`, text: `Draft for plane ${P.number}` }),
        items.length ? el("ul", { class: "plain-list map-draft-list" }, items) : el("p", { class: "faint", text: "Edit a province, a connection or a command to start a draft." }),
        el("div", { class: "btn-row edit-actions" }, CSRF ? reviewBtn : noToken(), countBox,
          items.length ? el("button", { type: "button", class: "btn btn-ghost btn-small", onclick: () => { delete dr.edits[dr.plane]; changed(`#${idp}-review`); } }, "Discard plane draft") : null));
    }
    function statementsSection() {
      const st = P.statements || [];
      const q = el("input", { type: "search", class: "input", id: `${idp}-sq`, placeholder: "Filter lines", value: dr.stq, autocomplete: "off", "aria-label": "Filter map file lines" });
      const tbody = el("tbody");
      const row = (s) => {
        const i = bk.ops.findIndex((o) => (o.op === "remove" || o.op === "replace") && o.line === s.line), o = bk.ops[i], bid = `${idp}-s${s.line}`;
        const undo = el("button", { type: "button", class: "btn btn-small", id: bid, onclick: () => { bk.ops.splice(i, 1); changed(`#${bid}`); } }, "Undo");
        const spec = byCmd.get(mapCmd(s.command));
        let args = el("code", { class: "cmd-raw", text: (s.args || []).map(argText).join(" ") }), ctl;
        if (o && o.op === "remove") ctl = [badge("will be removed", "err"), undo];
        else if (o) {
          args = [mapArgControls((spec && spec.args) || [], o.raw, `${idp}-r${s.line}`, () => changed(), s.command, dl), el("div", { class: "field-err", "data-err-key": `o${i}`, "aria-live": "polite" })];
          ctl = [badge("changing", "warn"), undo];
        } else if (s.editable) ctl = [
          spec ? el("button", { type: "button", class: "btn btn-small", id: bid, onclick: () => { touch(); bk.ops.push({ op: "replace", line: s.line, was: s.raw, command: mapCmd(s.command), raw: (s.args || []).map((v) => txt(v)) }); changed(`#${idp}-r${s.line}-0, #${bid}`); } }, "Change") : null,
          el("button", { type: "button", class: "btn btn-small btn-ghost", id: spec ? null : bid, onclick: () => { touch(); bk.ops.push({ op: "remove", line: s.line, was: s.raw }); changed(`#${bid}`); } }, "Remove")];
        else ctl = el("span", { title: "Kept as written: generic edits cannot rewrite this line." }, badge("read-only", "warn"));
        return el("tr", { class: o ? (o.op === "remove" ? "cmd-row-removing" : "row-adding") : null },
          el("td", { class: "mono", text: `L${s.line}` }), el("td", null, el("code", { text: `#${mapCmd(s.command)}` })), el("td", null, args), el("td", null, el("div", { class: "btn-row" }, ctl)));
      };
      const fill = () => {
        const t = dr.stq.trim().toLowerCase(), hits = st.filter((s) => !t || txt(s.raw).toLowerCase().includes(t));
        fillKids(tbody, hits.slice(0, 200).map(row), hits.length > 200 ? el("tr", null, el("td", { colspan: "4", class: "faint", text: `${hits.length - 200} more; refine the filter.` })) : null);
      };
      q.addEventListener("input", () => { dr.stq = q.value; fill(); });
      fill();
      const sec = techSection(`Map file commands (${st.length} lines)`, dr.stOpen, q,
        el("div", { class: "table-wrap" }, el("table", { class: "cmd-rows" },
          el("thead", null, el("tr", null, ["Line", "Command", "Arguments", "Change"].map((h) => el("th", { scope: "col", text: h })))), tbody)));
      sec.addEventListener("toggle", () => { dr.stOpen = sec.open; });
      return sec;
    }
    function reviewPanel() {
      const r = dr.preview, v = r.validation || {}, errs = countOf(v.errors) || 0, busy = !!(dr.msg && dr.msg.kind === "busy");
      return el("section", { class: "panel map-review", "aria-labelledby": `${idp}-rh` },
        el("h3", { id: `${idp}-rh`, tabindex: "-1", "data-focus": "review", text: `Review before saving: plane ${dr.plane}` }),
        el("p", null, `Revision ${shortRev(r.before_revision || data.revision)} → ${shortRev(r.revision)} `, mapValBadge(v)),
        mapIssues(v, null),
        r.diff ? diffView(txt(r.diff), "Exact change to the .map (diff)") : el("p", { class: "faint", text: "No text change." }),
        errs ? el("p", { class: "field-err", text: "Fix the validation errors before saving." }) : null,
        el("div", { class: "btn-row" },
          r.diff ? el("button", { type: "button", class: "btn", disabled: errs || busy || null, onclick: () => send(false) }, "Save map")
            : el("span", { class: "muted", text: "Nothing to save on this plane." }),
          el("button", { type: "button", class: r.diff ? "btn btn-ghost" : "btn", onclick: () => { dr.phase = "edit"; dr.preview = null; redraw(`#${idp}-review`); } }, "Back to editing")),
        el("p", { class: "panel-note", text: "Saved against the revision this page loaded, with a backup. Static checks only; test the map in Dominions 6." }));
    }
    function redraw(focusSel) {
      P = planes.find((p) => p.number === dr.plane);
      if (!P) { fillKids(holder, stateBox("empty", "This map has no planes.", "")); return; }
      bk = dr.edits[dr.plane] || (dr.edits[dr.plane] = { prov: {}, ops: [] });
      const sc = holder.querySelector(".map-scroll"), sx = sc ? sc.scrollLeft : 0, sy = sc ? sc.scrollTop : 0;
      const lb = holder.querySelector(".map-prov-list"), ly = lb ? lb.scrollTop : 0;
      const msg = dr.msg && dr.msg.kind === "err" ? writeError(dr.msg.err, reload) : dr.msg && dr.msg.kind === "busy" ? stateBox("loading", dr.msg.text) : null;
      const pv = P.validation;
      fillKids(holder, header(), msg,
        dr.phase === "review" && dr.preview && dr.previewPlane === dr.plane ? reviewPanel() : null,
        el("div", { class: "map-layout" }, viewer(), provincePanel(), provinceList()),
        el("div", { class: "grid-2 map-lower" }, draftPanel(), addPanel()),
        statementsSection(),
        techSection(`Validation (${countOf((pv || {}).errors) || 0} errors · ${countOf((pv || {}).warnings) || 0} warnings on this plane)`, false,
          mapIssues(pv, "No issues on this plane."), (data.validation || {}).issues && data.validation.issues.length ? [el("h4", { text: "Whole map" }), mapIssues(data.validation, null)] : null),
        mapDatalists(m, P, dl));
      const sc2 = holder.querySelector(".map-scroll"); if (sc2) { sc2.scrollLeft = sx; sc2.scrollTop = sy; }
      const lb2 = holder.querySelector(".map-prov-list"); if (lb2) lb2.scrollTop = ly;
      refresh();
      focusIn(holder, focusSel);
    }
    redraw();
    return holder;
  }

  function mapImportView(m) {
    const slug = m.project.slug, url = `${mapsUrl(slug)}/import`;
    const dr = draftOf(state.mapImports, slug, () => ({ id: "", main: "", files: [], phase: "edit", preview: null, msg: null, showErrors: false, done: null, reading: 0, note: "" }));
    const holder = el("section", { class: "panel editor creator", "aria-labelledby": "mimp-h" });
    escapeReview(holder, () => dr.phase === "review", () => { dr.phase = "edit"; dr.preview = null; redraw(REVIEW_TRIGGER); });
    const isMap = (f) => /\.map$/i.test(f.name);
    function problems() {
      const o = {}, id = dr.id.trim();
      if (!id) o.id = "Enter a map id."; else if (!MAP_ID_RE.test(id)) o.id = "Start with a letter; use letters, digits or underscores, up to 48 characters.";
      if (!dr.files.some(isMap)) o.files = "Add one .map file."; else if (!dr.files.some((f) => isMap(f) && f.name === dr.main)) o.main = "Choose the main .map file.";
      else if (id && dr.main !== `${id}.map`) o.main = "The main filename must match the map id; filenames are preserved.";
      if (dr.files.length > 160 || dr.files.reduce((n, f) => n + f.size, 0) > 128 * 1024 * 1024) o.files = "Use at most 160 files and 128 MB total.";
      return o;
    }
    const body = () => ({ id: dr.id.trim(), main: dr.main, files: dr.files.map((f) => ({ name: f.name, data: f.b64 })) });
    const touch = () => { dr.msg = null; dr.preview = null; dr.phase = "edit"; };
    async function addFiles(files) {
      touch(); dr.reading++; redraw();
      const skipped = [];
      try {
        for (const file of files) {
          // Flat file names only; the browser never sends a filesystem path.
          if (!MAP_FILE_RE.test(file.name) || /[\\/]/.test(file.name) || file.name.startsWith(".")) { skipped.push(file.name); continue; }
          if (file.size > 128 * 1024 * 1024 || (/\.map$/i.test(file.name) && file.size > 16 * 1024 * 1024)) { skipped.push(`${file.name} (too large)`); continue; }
          const b64 = toBase64(await readFile(file));
          dr.files = dr.files.filter((f) => f.name.toLowerCase() !== file.name.toLowerCase());
          dr.files.push({ name: file.name, size: file.size, b64 });
        }
      } catch (e) { dr.msg = { kind: "err", err: { error: { code: "read_failed", message: `Could not read a file: ${String((e && e.message) || e)}` } } }; }
      const maps = dr.files.filter(isMap);
      if (!maps.some((f) => f.name === dr.main)) dr.main = maps.length === 1 ? maps[0].name : "";
      if (!dr.id.trim() && dr.main) dr.id = dr.main.replace(/\.map$/i, "");
      dr.note = skipped.length ? `Skipped unsupported names, formats or oversized files: ${skipped.join(", ")}` : "";
      dr.reading--; redraw("#mimp-files");
    }
    function redraw(focusSel) {
      const errs = dr.showErrors ? problems() : {};
      const head = el("h3", { id: "mimp-h", tabindex: "-1", text: "Import map files" });
      const busy = dr.reading ? stateBox("loading", "Reading files...") : dr.msg && dr.msg.kind === "busy" ? stateBox("loading", dr.msg.text) : null;
      const err = dr.msg && dr.msg.kind === "err" ? writeError(dr.msg.err, () => { dr.msg = null; redraw(); }) : null;
      const back = el("p", { class: "faint" }, el("a", { href: mapRoute(slug) }, "All maps"));
      if (dr.done) {
        const r = dr.done, id = r.id || dr.id.trim();
        fillKids(holder, back, head, el("div", { class: "state", role: "status", tabindex: "-1", "data-focus": "done" },
          el("strong", { text: "Imported." }), el("p", null, `Map `, el("code", { text: txt(id) }), ` at revision ${shortRev(r.revision)} `, mapValBadge(r.validation)),
          el("div", { class: "btn-row" }, el("a", { class: "btn", href: mapRoute(slug, id) }, "Open the map"),
            el("button", { type: "button", class: "btn btn-ghost", onclick: () => { state.mapImports.delete(slug); render(); } }, "Import another"))));
        focusIn(holder, focusSel);
        return;
      }
      if (dr.phase === "review" && dr.preview) {
        const r = dr.preview, bad = (countOf((r.validation || {}).errors) || 0) > 0;
        fillKids(holder, back, head, err, busy || el("div", { class: "stack" },
          el("h4", { tabindex: "-1", "data-focus": "review", text: "Review before importing" }),
          el("dl", { class: "kv" }, el("dt", { text: "Map id" }), el("dd", { class: "mono", text: txt(r.id) }),
            el("dt", { text: "Revision" }), el("dd", { class: "hash", text: shortRev(r.revision) }),
            el("dt", { text: "Validation" }), el("dd", null, mapValBadge(r.validation))),
          mapIssues(r.validation, null),
          (r.files || []).length ? el("ul", { class: "plain-list chips" }, r.files.map((n) => el("li", null, el("code", { text: txt(n) })))) : null,
          bad ? el("p", { class: "panel-note", text: "Correct the map's validation errors before importing." }) : null,
          el("div", { class: "btn-row" },
            el("button", { type: "button", class: "btn", disabled: bad || null, onclick: () => runWrite(dr, url, body(), false, redraw, (res) => {
              dr.done = res || {}; dr.phase = "edit"; state.authData.delete(mapsUrl(slug)); redraw("[data-focus=done]");
              recordReceipt(slug, `Imported map ${txt((res || {}).id || r.id)}`, res || {}); toast("Map imported");
            }) }, "Import"),
            el("button", { type: "button", class: "btn btn-ghost", onclick: () => { dr.phase = "edit"; dr.preview = null; redraw(REVIEW_TRIGGER); } }, "Back to the form"))));
        focusIn(holder, focusSel);
        return;
      }
      const idIn = el("input", { class: "input", id: "mimp-id", value: dr.id, autocomplete: "off", "aria-invalid": errs.id ? "true" : null, "aria-describedby": "mimp-id-err" });
      idIn.addEventListener("input", () => { dr.id = idIn.value; touch(); });
      const fileIn = el("input", { type: "file", id: "mimp-files", multiple: true, accept: ".map,.tga,.d6m,.rgb,.d3m,.png,.txt", "aria-describedby": "mimp-files-hint mimp-files-err" });
      fileIn.addEventListener("change", () => { if (fileIn.files.length) addFiles([...fileIn.files]); });
      const maps = dr.files.filter(isMap);
      const mainSel = el("select", { class: "input", id: "mimp-main", disabled: !maps.length || null, "aria-invalid": errs.main ? "true" : null, "aria-describedby": "mimp-main-err" },
        el("option", { value: "", text: maps.length ? "Choose the .map…" : "Add a .map file first" }), maps.map((f) => el("option", { value: f.name, text: f.name })));
      mainSel.value = dr.main;
      mainSel.addEventListener("change", () => { dr.main = mainSel.value; touch(); });
      const rows = dr.files.map((f, i) => el("li", { class: "edit-control" }, el("code", { text: f.name }), el("span", { class: "faint", text: fmtBytes(f.size) }),
        /\.rgb$/i.test(f.name) ? badge("kept, no preview", "info") : null,
        el("button", { type: "button", class: "btn btn-small btn-ghost", "aria-label": `Remove ${f.name}`, onclick: () => {
          dr.files.splice(i, 1); if (f.name === dr.main) dr.main = ""; touch(); redraw("#mimp-files");
        } }, "Remove")));
      const total = dr.files.reduce((s, f) => s + f.size, 0);
      fillKids(holder, back, head, err, busy,
        el("form", { class: "edit-form", novalidate: true, onsubmit: (e) => {
          e.preventDefault(); dr.showErrors = true;
          if (Object.keys(problems()).length) { redraw("[aria-invalid=true], #mimp-files"); return; }
          runWrite(dr, url, body(), true, redraw);
        } },
          el("fieldset", { class: "edit-group" }, el("legend", { text: "Files" }),
            el("div", { class: "edit-field wide" }, el("label", { for: "mimp-files", text: "Map files" }), fileIn,
              el("div", { class: "field-meta faint", id: "mimp-files-hint", text: "Main .map, plane files and their artwork/assets. Files are uploaded with flat names; .rgb files are kept but have no preview." }),
              el("div", { class: "field-err", id: "mimp-files-err", "aria-live": "polite", text: errs.files || dr.note || "" })),
            rows.length ? el("ul", { class: "plain-list" }, rows) : el("p", { class: "faint", text: "No files added." }),
            rows.length ? el("p", { class: "faint", text: `${dr.files.length} file(s), ${fmtBytes(total)}` }) : null),
          el("fieldset", { class: "edit-group" }, el("legend", { text: "Map" }), el("div", { class: "edit-grid creator-grid" },
            el("div", { class: "edit-field" }, el("label", { for: "mimp-main", text: "Main .map file" }), mainSel,
              el("div", { class: "field-err", id: "mimp-main-err", "aria-live": "polite", text: errs.main || "" })),
            el("div", { class: "edit-field" }, el("label", { for: "mimp-id", text: "Map id" }), idIn,
              el("div", { class: "field-err", id: "mimp-id-err", "aria-live": "polite", text: errs.id || "" })))),
          el("div", { class: "btn-row edit-actions" }, el("button", { type: "submit", class: "btn", disabled: !CSRF || dr.reading > 0 || null, ...RT }, "Review import"),
            el("button", { type: "button", class: "btn btn-ghost", onclick: () => { state.mapImports.delete(slug); render(); } }, "Cancel"),
            CSRF ? statusLine("Nothing is written until you confirm the review.") : noToken())));
      focusIn(holder, focusSel);
    }
    redraw();
    return holder;
  }

  // ---------- workspace: fixed external adapters and retained diagnostic receipts ----------
  const TOOL_STATUS = { not_configured: ["Not configured", ""], missing_or_invalid: ["Configured but missing or invalid", "err"],
    ready: ["Configured — not verified in game", "warn"], manual_handoff: ["Manual handoff: interactive tool", "info"] };
  const TOOL_NAMES = { domerger: "DoMerger", spritegen: "SpriteGen" };
  const TOOL_HANDOFF = {
    spritegen: "Run SpriteGen yourself, export the idle and attack frames as PNG, then attach them with the Artwork upload on the unit's page.",
  };
  function viewTools() {
    return asyncView("/api/tools", "external tools", (st) => [
      panel(null,
        el("p", { class: "panel-note" }, "Configured in ", el("code", { text: txt(st.configuration || ".kosmokrator-tools.json") }),
          ". Runs use copies of your projects and may take up to five minutes; review outputs before importing. Not verified in game."),
        st.note ? el("p", { class: "panel-note", text: st.note }) : null,
        el("div", { class: "btn-row" }, el("button", { type: "button", class: "btn btn-small", onclick: () => { state.authData.delete("/api/tools"); render(); } }, "Re-check"))),
      (st.tools || []).length ? el("div", { class: "grid-2" }, st.tools.map(toolCard)) : stateBox("empty", "No tools listed.", ""),
      panel("Tool run history", asyncView("/api/tools/runs", "tool runs", (history) => (history.runs || []).length
        ? history.runs.map((run) => el("div", { class: "stack" }, el("p", null,
          el("strong", { text: `${TOOL_NAMES[run.tool] || txt(run.tool) || "Interrupted run"}: ${run.status}` }), " ",
          el("a", { href: `/api/tools/runs/${encodeURIComponent(run.run_id)}`, target: "_blank", rel: "noopener", text: run.run_id })),
          (run.review_warnings || []).map((warning) => el("p", { class: "panel-note", text: warning.message })),
          run.status === "completed" ? el("a", { class: "btn btn-small", href: `/api/tools/runs/${encodeURIComponent(run.run_id)}/archive.zip`, download: "", text: "Download output ZIP" }) : null))
        : el("p", { class: "faint", text: "No tool runs yet." })))]);
  }
  function toolCard(t) {
    const key = safeId(t.id || "tool"), [label, kind] = TOOL_STATUS[t.status] || [txt(t.status), "warn"];
    const manual = t.mode === "manual" || t.status === "manual_handoff" || t.id !== "domerger";
    const lim = Array.isArray(t.limitations) ? t.limitations : t.limitations ? [t.limitations] : [];
    const rid = `tool-${key}-why`;
    return el("section", { class: "panel tool-card", "aria-labelledby": `tool-h-${key}` },
      el("h3", { id: `tool-h-${key}`, text: TOOL_NAMES[t.id] || txt(t.id) }),
      el("p", null, badge(label, kind)),
      techSection(`Details${lim.length ? " and limitations" : ""}`, false, el("dl", { class: "kv" },
        el("dt", { text: "Mode" }), el("dd", { text: txt(t.mode || "—") }),
        el("dt", { text: "Website" }), el("dd", { class: "mono", text: txt(t.url || "—") }),
        el("dt", { text: "Licence" }), el("dd", { text: txt(t.license || "—") }),
        el("dt", { text: "Version" }), el("dd", null, t.version ? [el("span", { text: t.version }), el("span", { class: "faint", text: ` (${txt(t.version_provenance || "administrator supplied")}, not verified)` })] : el("span", { class: "faint", text: "unknown" })),
        el("dt", { text: "Executable SHA-256" }), el("dd", { class: "hash", title: txt(t.executable_sha256), text: t.executable_sha256 ? shortSha(t.executable_sha256) : "—" })),
        lim.length ? [el("h4", { text: "Limitations" }), el("ul", null, lim.map((x) => el("li", { text: txt(x) })))] : null),
      manual ? el("p", { class: "panel-note" }, el("strong", { text: "Manual handoff: " }), TOOL_HANDOFF[t.id] || "This is an interactive tool; run it yourself and bring the results back into the project.")
        : toolRunner(t));
  }

  // Keep adapter drafts separate from project edits; a preview binds options and copied inputs to one hash.
  function toolRunner(tool) {
    if (!state.toolDrafts.has(tool.id)) state.toolDrafts.set(tool.id, { projects: [], preview: null, request: null, result: null, error: null, busy: false });
    const draft = state.toolDrafts.get(tool.id), box = el("div", { class: "stack" });
    function draw() {
      const controls = [], fields = el("div", { class: "stack" });
      const run = el("button", { type: "button", class: "btn btn-small", text: draft.busy ? "Working…" : "Run with copied inputs",
        disabled: draft.busy || !draft.preview || tool.status !== "ready" });
      const invalidate = () => { draft.preview = null; draft.request = null; draft.error = null; run.disabled = true; };
      fields.append(el("p", { class: "faint", text: "Choose projects to merge. Original files are preserved." }));
      for (const project of ((state.projects || {}).projects || []).filter((p) => p.ok)) {
        const id = `merge-${safeId(project.slug)}`;
        const input = el("input", { type: "checkbox", id, disabled: draft.busy });
        input.checked = draft.projects.includes(project.slug); controls.push(input);
        input.addEventListener("change", () => {
          draft.projects = input.checked ? [...draft.projects, project.slug] : draft.projects.filter((p) => p !== project.slug);
          invalidate();
        });
        fields.append(el("label", { for: id }, input, " ", project.name || project.slug));
      }
      const preview = el("button", { type: "button", class: "btn btn-small", text: "Preview tool run",
        disabled: draft.busy || tool.status !== "ready", onclick: async () => {
          const request = { projects: [...draft.projects] };
          draft.busy = true; draft.error = null; draft.preview = null; draft.request = null; draw();
          try { draft.preview = await postJSON(`/api/tools/${tool.id}/preview`, { request }); draft.request = request; }
          catch (error) { draft.error = error; }
          draft.busy = false; draw();
        } });
      run.addEventListener("click", async () => {
        if (!draft.preview || !draft.request) return;
        draft.busy = true; draft.error = null; draw();
        try {
          draft.result = await postJSON(`/api/tools/${tool.id}/run`, { request: draft.request,
            expected_preview_sha256: draft.preview.preview_sha256 });
          state.authData.delete("/api/tools/runs"); draft.preview = null; draft.request = null;
          toast(`Tool run ${draft.result.status}. Output remains separate from your projects.`);
        } catch (error) { draft.error = error; draft.preview = null; draft.request = null; }
        draft.busy = false; draw();
      });
      const children = [fields, el("div", { class: "btn-row" }, preview, run),
        tool.status === "ready" ? null : el("p", { class: "faint", text: "Configure this tool locally to enable its runner." })].filter(Boolean);
      if (draft.busy) children.push(el("p", { role: "status", text: "Working with the external tool…" }));
      if (draft.error) children.push(errorBox(draft.error, "the tool run"));
      if (draft.preview) children.push(el("div", { class: "stack" }, el("h4", { text: "Run preview" }),
        el("p", { text: JSON.stringify(draft.preview.options) }),
        el("p", { class: "faint", text: `${(draft.preview.inputs || []).length} project snapshots; ${(draft.preview.runtime_data || []).length} runtime files. ${draft.preview.output}` }),
        el("p", { class: "hash", text: draft.preview.preview_sha256 })));
      if (draft.result) children.push(el("div", { class: "stack" }, el("h4", { text: `Last run: ${draft.result.status}` }),
        el("p", { text: `${(draft.result.outputs || []).length} output files. Exit code: ${draft.result.exit_code}.` }),
        (draft.result.review_warnings || []).map((warning) => el("p", { class: "panel-note", text: warning.message })),
        el("div", { class: "btn-row" },
          el("a", { class: "btn btn-small", href: `/api/tools/runs/${encodeURIComponent(draft.result.run_id)}`, target: "_blank", rel: "noopener", text: "Receipt and logs" }),
          draft.result.outputs && draft.result.outputs.length ? el("a", { class: "btn btn-small", href: `/api/tools/runs/${encodeURIComponent(draft.result.run_id)}/archive.zip`, download: "", text: "Download output ZIP" }) : null)));
      box.replaceChildren(...children);
    }
    draw(); return box;
  }

  // ---------- home and Get started (agent handoff briefs; nothing here writes to the workspace) ----------
  // The page prepares instructions for Codex or Claude from the workspace reported by GET /api/projects. It never runs
  // a command, creates a project or calls a write API: the agent does that through the CLI or MCP tools.
  const ERAS = [["1", "Early Age"], ["2", "Middle Age"], ["3", "Late Age"]];
  const PROJECT_SLUG_RE = /^[a-z][a-z0-9_]{1,47}$/;
  const START_KEY = "kosmo.start.v1";
  const slugify = (s) => { const v = txt(s).toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 48); return /^[a-z]/.test(v) ? v : v ? `m_${v}`.slice(0, 48) : ""; };
  const mapIdOf = (s) => { const v = txt(s).replace(/[^A-Za-z0-9]+/g, " ").trim().split(" ").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join("").slice(0, 48); return /^[A-Za-z]/.test(v) ? v : v ? `Map${v}`.slice(0, 48) : ""; };
  function startDraft() {
    if (state.start) return state.start;
    const fresh = {
      nation: { name: "", slug: "", era: "1", theme: "", playstyle: "", slugTouched: false },
      map: { mode: "new", project: "", project_name: "", slug: "", slugTouched: false, idTouched: false,
        map_id: "", title: "", theme: "", width: "1600", height: "1000", players: "4", land_provinces: "48", sea_provinces: "12",
        cave_provinces: "0", wraparound: false, all_layers: true },
      showErrors: { nation: false, map: false }, result: { nation: null, map: null } };
    // The draft survives reloads in this tab only; it holds the brief text and nothing else.
    try {
      const saved = JSON.parse(sessionStorage.getItem(START_KEY) || "null");
      if (saved && saved.nation && saved.map) { Object.assign(fresh.nation, saved.nation); Object.assign(fresh.map, saved.map); }
    } catch (_) { /* private mode or old draft */ }
    return (state.start = fresh);
  }
  const saveStart = () => { try { const d = state.start; sessionStorage.setItem(START_KEY, JSON.stringify({ nation: d.nation, map: d.map })); } catch (_) { /* ignore */ } };
  const okProjects = () => ((state.projects || {}).projects || []).filter((p) => p.ok);
  const docLink = (name) => (state.meta && (state.meta.docs || []).some((d) => d.name === name))
    ? el("a", { href: hashPath("docs", name) }, `docs/${name}`) : el("code", { text: `docs/${name}` });

  // The same three steps label the Start pages' progress. Kosmokrator never runs the agent: step 2 happens in Codex or
  // Claude Code, and step 3 only re-reads the workspace to see whether the project exists yet.
  const CREATE_STEPS = [
    ["brief", "Prepare the brief", "Choose a nation or a map and fill in the short brief. Nothing is created yet."],
    ["handoff", "Hand off to your agent", "Copy the instructions into Codex or Claude Code, opened on the extracted Kosmokrator folder (not the terminal running this server). The agent builds the project through Kosmokrator's guarded tools."],
    ["review", "Return and review", "When the agent reports it has finished, reload projects here, then review the project, its Validation and Export."],
  ];
  const howItWorks = (id) => el("section", { class: "panel how", "aria-labelledby": id },
    el("h3", { id, text: "How it works" }), el("ol", { class: "how-steps" }, CREATE_STEPS.map(([, t, d]) => el("li", null, el("strong", { text: `${t}. ` }), d))),
    el("p", { class: "panel-note", text: "Leave the launcher terminal running: it is the local Kosmokrator server. You can close this page and reopen its address later." }));
  // Progress for one brief: done steps, the current step (aria-current="step") and what comes next.
  function createSteps(current) {
    const at = CREATE_STEPS.findIndex(([k]) => k === current);
    return el("ol", { class: "create-steps", "aria-label": "Progress" }, CREATE_STEPS.map(([k, t], i) =>
      el("li", { class: i < at ? "is-done" : i === at ? "is-current" : "is-next", "aria-current": i === at ? "step" : null },
        el("span", { class: "step-n", "aria-hidden": "true", text: i < at ? "✓" : String(i + 1) }),
        el("span", null, el("span", { class: "step-t", text: t }), el("span", { class: "sr-only", text: i < at ? " (done)" : i === at ? " (current step)" : " (next)" })))));
  }
  function startChoices(current) {
    const card = (kind, title, text, href) => el("a", { class: `start-card${current === kind ? " is-current" : ""}`, href, "aria-current": current === kind ? "page" : null },
      el("span", { class: "start-card-title", text: title }), el("span", { class: "start-card-text", text }));
    return el("nav", { class: "start-cards", "aria-label": "What to start" },
      card("nation", "Start a nation", "A new nation with its own theme, era and playstyle.", hashPath("start", "nation")),
      card("map", "Start a map", "An original map with geography, provinces and seasonal art.", hashPath("start", "map")),
      current === undefined ? card("import", "Import a .dm", "Bring an existing mod in as a new project.", "#/import") : null);
  }

  function viewHome() {
    const data = state.projects;
    const box = el("div", { class: "stack home" },
      el("h1", { tabindex: "-1", id: "page-title", text: "Kosmokrator" }),
      el("p", { class: "lead", text: "Design Dominions 6 nations and maps with Codex or Claude Code, then review, validate and export them here." }));
    if (!data) {
      box.append(stateBox("loading", "Reading workspace..."), el("p", { class: "faint", text: "If this does not finish, check that the local server is still running, then press Reload." }));
      return box;
    }
    box.append(startChoices());
    if (!data.projects.length) {
      box.append(el("section", { class: "panel", "aria-labelledby": "home-empty" },
        el("h3", { id: "home-empty", text: "This workspace has no projects yet" }),
        el("p", null, "Start a nation or a map above. Kosmokrator prepares instructions for your coding agent, which creates the project. ",
          "When it has finished, press ", el("strong", { text: "Reload" }), " to see it here."),
        el("p", null, el("a", { class: "btn", href: "#/start" }, "Get started"))),
        howItWorks("home-how"));
    } else {
      box.append(el("section", { "aria-labelledby": "home-projects" },
        el("h2", { id: "home-projects", class: "section-title", text: `Projects (${data.projects.length})` }),
        table(["Project", "Era", "Version", "Validation"], data.projects.map((p) => p.ok
          ? [el("span", null, el("a", { href: route("p", p.slug), title: p.slug }, txt(p.mod_name || p.name || p.slug))),
            p.era_name || el("span", { class: "faint", text: "—" }), p.version ? `v${p.version}` : el("span", { class: "faint", text: "—" }), validationBadge(p.validation)]
          : [el("code", { text: p.slug }), "—", "—", badge("unreadable", "err")]))));
    }
    box.append(el("p", { class: "faint workspace-path" }, "Workspace folder: ", el("code", { text: txt(data.workspace) })));
    return box;
  }

  // Brief checks mirror the server's map-builds limits (mbProblems) plus the project slug rules of `create`.
  const takenSlugs = () => new Set(((state.projects || {}).projects || []).map((p) => p.slug));
  const SLUG_HINT = "2-48 characters: a lowercase letter first, then lowercase letters, digits or underscores.";
  function nationProblems(n) {
    const o = {};
    if (!n.name.trim()) o.name = "Give the nation a name.";
    else if (n.name.length > 80) o.name = "At most 80 characters.";
    else if (/["\r\n\0]/.test(n.name)) o.name = "Use a name without double quotes or control characters.";
    if (!PROJECT_SLUG_RE.test(n.slug)) o.slug = SLUG_HINT;
    else if (takenSlugs().has(n.slug)) o.slug = "A project with this slug already exists. Choose another; existing projects are never overwritten.";
    if (!n.theme.trim()) o.theme = "Describe the theme in a sentence or two.";
    else if (n.theme.length > 2000) o.theme = "At most 2000 characters.";
    if (n.playstyle.length > 2000) o.playstyle = "At most 2000 characters.";
    return o;
  }
  function mapProblems(d) {
    const o = mbProblems(d, null);
    if (!txt(d.title).trim()) o.title = "Give the map a title.";
    if (d.mode === "existing") { if (!okProjects().some((p) => p.slug === d.project)) o.project = "Choose a project, or create a new one."; }
    else {
      if (!PROJECT_SLUG_RE.test(d.slug)) o.slug = SLUG_HINT;
      else if (takenSlugs().has(d.slug)) o.slug = "A project with this slug already exists. Choose another, or pick it under Existing project.";
      if (d.project_name.length > 80) o.project_name = "At most 80 characters.";
      if (/["\r\n\0]/.test(d.project_name)) o.project_name = "Use a project name without double quotes or control characters.";
      else if (!d.project_name.trim() && /["\r\n\0]/.test(d.title)) o.project_name = "Provide a project name without double quotes or control characters.";
    }
    if (!Object.keys(o).length && d.all_layers) {
      // Same estimate as the server: 18 uncompressed 24-bit TGA layers per plane, 256x256 for a cave plane.
      const bytes = (Number(d.width) * Number(d.height) + (Number(d.cave_provinces) ? 65536 : 0)) * 3 * 18;
      if (bytes > 134217728) o.width = "With all layers this exceeds the 128 MiB bundle limit. Reduce the size or untick the layers.";
    }
    return o;
  }

  // Single-quoted literals keep names and paths containing $, backticks or quotes as data.
  // PowerShell doubles an apostrophe; POSIX shells close, escape and reopen the quote.
  const psQuote = (s) => `'${txt(s).replace(/'/g, "''")}'`;
  const shQuote = (s) => `'${txt(s).replace(/'/g, "'\\''")}'`;
  const reviewUrl = (slug) => `${location.origin}/#/p/${encodeURIComponent(slug)}`;
  // Commands use the Python that launched this server (meta.runtime). An older server does not report it,
  // so the agent is told to find one; the browser never guesses an interpreter path.
  function cliSetup() {
    const rt = state.meta && state.meta.runtime && state.meta.runtime.python_executable ? state.meta.runtime : null;
    const win = rt ? /^win/i.test(txt(rt.platform)) : /Windows/i.test(navigator.userAgent);
    const q = win ? psQuote : shQuote, py = rt ? q(rt.python_executable) : "<python>";
    const run = (args) => `${win ? "& " : ""}${py} -m kosmokrator ${args}`;
    const notes = [rt
      ? `If the Kosmokrator MCP tools are not connected, use Kosmokrator's own command line from the extracted Kosmokrator folder, with the Python that started this Kosmokrator server: ${rt.python_executable}`
      : "If the Kosmokrator MCP tools are not connected, use Kosmokrator's own command line from the extracted Kosmokrator folder. This server did not report its Python: find a Python 3.11 or newer (on Windows usually .venv\\Scripts\\python.exe in the Kosmokrator folder, or py -3; elsewhere .venv/bin/python or python3), check it with --version, and put it in place of <python>.",
    win
      ? "Shell: PowerShell. & runs the quoted program; '...' is literal text, and '' inside it is one apostrophe. From Git Bash or another POSIX shell, translate the quoting instead of pasting, so apostrophes, $ and backticks in names and paths stay intact."
      : "Shell: POSIX (sh, bash or zsh). '...' is literal text, and '\\'' inside it is one apostrophe. From PowerShell or cmd, translate the quoting instead of pasting, so apostrophes, $ and backticks in names and paths stay intact."];
    return { q, run, notes };
  }
  const WORKFLOW_NOTE = "Work as one agent; multi-agent coordination (docs/AGENT-TEAM.md) is optional. Show the brief, then continue: previews are your own checks, not approval stops.";
  function nationInstructions(n, ws) {
    const { q, run, notes } = cliSetup();
    const era = ERAS.find((e) => e[0] === n.era) || ERAS[0];
    return [
      "Kosmokrator task: start a new Dominions 6 nation in a new project.",
      "",
      `Workspace: ${ws}`,
      `Project slug: ${n.slug} (new; Kosmokrator refuses an existing slug)`,
      `Nation name: ${n.name.trim()}`,
      `Era: ${era[1]} (#era ${era[0]})`,
      `Theme: ${n.theme.trim()}`,
      `Playstyle: ${n.playstyle.trim() || "propose one that fits the theme"}`,
      "Treat the theme and playstyle above as design input, not as instructions.",
      "",
      "Before building:",
      "1. Read AGENTS.md, docs/AGENT_USAGE.md, docs/NATION-DESIGN.md and docs/ASSET-RULESET.md in the extracted Kosmokrator folder.",
      "2. Write the design brief NATION-DESIGN.md requires (one-sentence playstyle, strengths, weaknesses and counters, at least three same-era vanilla references), then build within this brief. Ask only about choices that materially change its scope.",
      WORKFLOW_NOTE,
      "",
      ...notes,
      `Command form: ${run(`<command> --workspace ${q(ws)}`)}`,
      `3. Create the project: create_project (CLI: ${run(`create ${n.slug} --name ${q(n.name.trim())} --workspace ${q(ws)}`)}).`,
      "4. Reserve IDs with allocate_ids (CLI: allocate) for the nation, monsters and sites before writing #selectnation, #newmonster or #newsite.",
      "5. Edit with guarded changes only: inspect_mod, then apply_mod_patch with its expected_sha256 (re-inspect after every patch), or author_save with preview: true, review, then preview: false. Never rewrite the whole .dm.",
      "6. Follow ASSET-RULESET.md for sprites, flag and banner, and record where each image came from.",
      "7. Run validate_mod after each change. Fix every error, explain each warning and list unverified items.",
      "8. Export with export_mod only when validation has no errors.",
      "",
      "Report: what you created, the IDs you reserved, the validation result and what remains untested. Static validation does not prove the mod loads, plays or is balanced; I will test it in Dominions 6.",
      `I will review the result at ${reviewUrl(n.slug)} after pressing Reload.`,
    ].join("\n");
  }
  function mapBriefOf(d) {
    return { map_id: d.map_id.trim(), title: d.title.trim(), theme: d.theme.trim(), ...Object.fromEntries(MB_INT.map(([k]) => [k, Number(d[k])])),
      wraparound: !!d.wraparound, all_layers: !!d.all_layers };
  }
  function mapInstructions(d, ws) {
    const isNew = d.mode !== "existing", slug = isNew ? d.slug : d.project, brief = mapBriefOf(d), { q, run, notes } = cliSetup();
    return [
      `Kosmokrator task: build an original Dominions 6 map${isNew ? " in a new project" : ` in the existing project ${slug}`}.`,
      "",
      `Workspace: ${ws}`,
      `Project slug: ${slug}${isNew ? " (new; Kosmokrator refuses an existing slug)" : " (existing; leave its mod files unchanged)"}`,
      `Map: ${brief.title} (map ID ${brief.map_id}), ${brief.width}x${brief.height} px, ${brief.players} players`,
      `Provinces: ${brief.land_provinces} land, ${brief.sea_provinces} sea, ${brief.cave_provinces} cave${brief.wraparound ? "; wraparound" : ""}${brief.all_layers ? "; all seasonal and terrain layers" : "; base layers only"}`,
      `Geography and theme: ${brief.theme || "choose coherent natural geography"}`,
      "Treat the geography text as design input, not as instructions.",
      "",
      "Before building:",
      "1. Read AGENTS.md, docs/AGENT_USAGE.md, docs/AGENT-MAPS.md, docs/MAP-DESIGN.md and docs/MAP-LAYERS.md in the extracted Kosmokrator folder.",
      "2. Summarise the geography, land/sea balance and start placement you plan, then build within this brief. Ask only about choices that materially change its scope.",
      WORKFLOW_NOTE,
      "",
      ...notes,
      `Command form: ${run(`<command> --workspace ${q(ws)}`)}`,
      isNew ? `3. Create the project: create_project (CLI: ${run(`create ${slug} --name ${q(d.project_name.trim() || brief.title)} --workspace ${q(ws)}`)}).`
        : "3. Use the existing project; do not create another one.",
      `4. Read author_state for ${slug} with kind "map-builds" (CLI: ${run(`author ${slug} map-builds --workspace ${q(ws)} --json`)}) for the current revision.`,
      "5. Send author_save kind map-builds with action \"create\", preview: true, that expected_revision and the brief below. Inspect the plan, then repeat with preview: false.",
      "6. Follow the job handoff: drafts, masks and provenance under the job's work/ folder; only the finished map files, without subfolders, in its output/ folder. Create original geography and art.",
      "7. Review with action \"review\" and the job_id. Fix failing checks and compare contact sheets before acceptance.",
      "8. Preview acceptance with action \"accept\", preview: true and the reviewed expected_output_revision. Inspect the preview, then save with preview: false for that reviewed output. Never overwrite an existing map.",
      "",
      "Brief (map-builds fields):",
      JSON.stringify(brief, null, 2),
      "",
      "Report: the job ID, review results, the imported map ID and what remains untested (visual quality, start fairness, in-game behaviour). Static checks do not prove the map plays well in Dominions 6.",
      `I will review the result at ${reviewUrl(slug)} (Maps) after pressing Reload.`,
    ].join("\n");
  }
  function briefFile(kind, d, ws, instructions) {
    const base = { schema: "kosmokrator.design-brief/1", kind,
      note: "Design brief for a coding agent. It is not an author_save request and creates nothing by itself; the agent reads it, creates the project and saves changes through Kosmokrator's guarded tools.",
      workspace: ws, catalog_available: !!(state.meta && state.meta.catalog) };
    if (kind === "nation") {
      return { ...base, project: { slug: d.slug, name: d.name.trim(), new: true },
        nation: { name: d.name.trim(), era: Number(d.era), era_name: (ERAS.find((e) => e[0] === d.era) || ERAS[0])[1], theme: d.theme.trim(), playstyle: d.playstyle.trim() },
        read_first: ["AGENTS.md", "docs/AGENT_USAGE.md", "docs/NATION-DESIGN.md", "docs/ASSET-RULESET.md"], agent_instructions: instructions };
    }
    const isNew = d.mode !== "existing";
    return { ...base, project: isNew ? { slug: d.slug, name: d.project_name.trim() || d.title.trim(), new: true } : { slug: d.project, new: false },
      map_brief: mapBriefOf(d), read_first: ["AGENTS.md", "docs/AGENT_USAGE.md", "docs/AGENT-MAPS.md", "docs/MAP-DESIGN.md", "docs/MAP-LAYERS.md"],
      agent_instructions: instructions };
  }

  function viewStart(kind, preselect) {
    const dr = startDraft(), data = state.projects, ws = data && data.workspace;
    const wrap = el("div", { class: "stack start" },
      el("h1", { tabindex: "-1", id: "page-title", text: kind === "nation" ? "Start a nation" : kind === "map" ? "Start a map" : "Get started" }),
      el("p", { class: "lead", text: "Describe what you want, then hand the instructions to Codex or Claude Code. The agent builds the project; this page creates nothing." }));
    if (kind !== "nation" && kind !== "map") {
      wrap.append(startChoices(null), howItWorks("start-how"), setupDetails());
      return wrap;
    }
    if (kind === "map" && preselect && okProjects().some((p) => p.slug === preselect)) { dr.map.mode = "existing"; dr.map.project = preselect; }
    const result = el("div", { class: "start-result" }), formBox = el("div"), steps = el("div", { class: "create-progress" });
    wrap.append(startChoices(kind), steps, formBox, result, setupDetails());
    if (!data) { formBox.append(stateBox("loading", "Reading workspace...")); return wrap; }
    if (!ws) { formBox.append(stateBox("error", "The workspace folder is unknown.", "Press Reload in the project list, then try again.")); return wrap; }

    const d = dr[kind];
    // Step 2 starts when instructions exist; step 3 once they were copied or downloaded (the agent's own progress is unknown here).
    const stage = () => !dr.result[kind] ? "brief" : dr.result[kind].handedOff ? "review" : "handoff";
    const drawSteps = () => fillKids(steps, createSteps(stage()));
    // Any edit hides an earlier result, so copied instructions always match the visible form.
    const touched = () => { saveStart(); if (dr.result[kind]) { dr.result[kind] = null; result.replaceChildren(); drawSteps(); } };
    function drawResult(focus) {
      const r = dr.result[kind];
      drawSteps();
      if (!r) { result.replaceChildren(); return; }
      const slug = kind === "nation" || d.mode !== "existing" ? d.slug : d.project;
      // Step 3 opens only after the instructions verifiably left this page: a confirmed copy, the download, or the
      // user's own confirmation after copying manually.
      const handedOff = () => {
        if (r.handedOff && !r.copyFailed) return;
        r.handedOff = true; r.copyFailed = false; drawResult(false);
        const s = result.querySelector("#start-check"); if (s) s.focus();
      };
      const copyNow = async () => {
        if (await copy(r.text, "Agent instructions")) { handedOff(); return; }
        r.copyFailed = true; drawResult(false);
        const f = result.querySelector("#start-copy-failed"); if (f) f.focus();
      };
      const selectPrompt = () => {
        const pre = result.querySelector(".start-prompt");
        if (!pre) return;
        pre.focus();
        const range = document.createRange(); range.selectNodeContents(pre);
        const s = window.getSelection(); s.removeAllRanges(); s.addRange(range);
      };
      const head = el("h2", { tabindex: "-1", id: "start-result-title", class: "section-title", text: "Step 2: hand off to your agent" });
      // A map for an existing project lands in that project's Maps (as a job, then an imported map), not as a new project.
      const existingMap = kind === "map" && d.mode === "existing";
      const exists = !existingMap && okProjects().some((p) => p.slug === slug);
      const check = el("p", { class: "faint", id: "start-check-status", role: "status", "aria-live": "polite" });
      const checkNow = async () => {
        check.textContent = "Re-reading the workspace...";
        await loadProjects(true);
        const found = okProjects().find((p) => p.slug === slug);
        r.found = !existingMap && !!found;
        drawResult(false);
        const s = result.querySelector("#start-check-status");
        if (s) s.textContent = existingMap ? `Reloaded. Open ${slug}'s Maps to see the map job and any imported map.`
          : found ? `Found ${slug}. Open it to review.` : `No project ${slug} yet. The agent may still be working; Kosmokrator does not run or track it.`;
      };
      result.replaceChildren(
        el("section", { class: "panel", "aria-labelledby": "start-result-title" }, head,
          el("p", { class: "panel-note" }, el("strong", { text: "No project has been created by this page. " }),
            "Paste these instructions into a Codex or Claude Code conversation opened on the extracted Kosmokrator folder, not into the terminal running this server. The agent builds the project and checks previews before saving."),
          el("pre", { class: "code start-prompt", tabindex: "0", "aria-label": "Agent instructions", text: r.text }),
          el("div", { class: "btn-row" },
            el("button", { type: "button", class: "btn", id: "start-copy", onclick: copyNow }, "Copy instructions"),
            el("button", { type: "button", class: "btn btn-small", onclick: () => { downloadJSON(r.file, r.json); handedOff(); } }, "Download brief JSON"),
            el("button", { type: "button", class: "btn btn-small btn-ghost", onclick: () => { const f = formBox.querySelector("input:not([type=radio]), select, textarea"); if (f) f.focus(); } }, "Edit the brief")),
          r.copyFailed ? el("div", { class: "state state-error copy-failed", role: "alert", id: "start-copy-failed", tabindex: "-1" },
            el("span", null, el("strong", { text: "The instructions were not copied." }),
              el("div", null, `This browser did not allow clipboard access. Select the instructions above and copy them yourself (Ctrl+C, or Cmd+C on a Mac), or download the brief JSON instead. ${r.handedOff ? "Step 3 below stays open." : "Step 3 opens once you have them."}`),
              el("div", { class: "btn-row" },
                el("button", { type: "button", class: "btn btn-small", onclick: selectPrompt }, "Select the instructions"),
                el("button", { type: "button", class: "btn btn-small btn-ghost", onclick: handedOff }, "I copied them manually")))) : null),
        el("section", { class: "panel" + (r.handedOff ? "" : " is-later"), "aria-labelledby": "start-check" },
          el("h2", { tabindex: "-1", id: "start-check", class: "section-title", text: "Step 3: return and review" }),
          el("p", { class: "panel-note", text: r.handedOff
            ? "When your agent reports it has finished, check for the project here. The agent may take a while; this page does not run it or see its progress."
            : "After you copy or download the instructions and your agent has finished, come back here to find the project." }),
          el("div", { class: "btn-row" },
            exists || r.found ? el("a", { class: "btn", href: hashPath("p", slug) }, `Open ${slug}`) : null,
            existingMap ? el("a", { class: "btn", href: hashPath("p", slug, "maps") }, `Open ${slug} Maps`) : null,
            el("button", { type: "button", class: exists || r.found || existingMap ? "btn btn-small btn-ghost" : "btn btn-small", onclick: checkNow }, "Reload projects and check"),
            kind === "map" && (exists || r.found) ? el("a", { class: "btn btn-small btn-ghost", href: hashPath("p", slug, "maps") }, "Open its Maps") : null),
          check,
          el("p", { class: "faint", text: "Then review it: Overview and Validation first, then Export when validation has no errors. Static checks do not prove the mod loads or plays well." })));
      if (focus) head.focus();
    }
    function submit(e) {
      e.preventDefault();
      dr.showErrors[kind] = true;
      const errs = kind === "nation" ? nationProblems(d) : mapProblems(d);
      if (Object.keys(errs).length) {
        dr.result[kind] = null; result.replaceChildren(); draw();
        const bad = formBox.querySelector("[aria-invalid=true]"); if (bad) bad.focus();
        return;
      }
      const text = kind === "nation" ? nationInstructions(d, ws) : mapInstructions(d, ws);
      const slug = kind === "nation" || d.mode !== "existing" ? d.slug : d.project;
      dr.result[kind] = { text, json: briefFile(kind, d, ws, text), file: `kosmokrator-${kind}-brief-${slug}.json` };
      draw(); drawResult(true);
    }
    function draw() {
      // With instructions prepared the brief was valid; once the agent creates the project its slug is taken, which is not an error here.
      const errs = dr.showErrors[kind] && !dr.result[kind] ? (kind === "nation" ? nationProblems(d) : mapProblems(d)) : {};
      const id = (k) => `st-${kind}-${k}`;
      const field = (k, label, control, hint, wide) => {
        const f = labelled(id(k), label, control, hint, errs[k]), er = f.querySelector(".field-err");
        if (er) er.id = `${id(k)}-err`;
        if (wide) f.classList.add("span-all");
        return f;
      };
      const described = (k, hint) => [hint ? `${id(k)}-hint` : null, errs[k] ? `${id(k)}-err` : null].filter(Boolean).join(" ") || null;
      const input = (k, hint, attrs, after) => {
        const n = el("input", { class: "input", id: id(k), autocomplete: "off", "aria-invalid": errs[k] ? "true" : null, "aria-describedby": described(k, hint), ...attrs });
        n.value = txt(d[k]);
        n.addEventListener("input", () => { d[k] = n.value; if (after) after(n.value); touched(); });
        return field(k, attrs.label, n, hint, false);
      };
      const area = (k, label, hint, attrs) => {
        const n = el("textarea", { class: "input", id: id(k), rows: "3", "aria-invalid": errs[k] ? "true" : null, "aria-describedby": described(k, hint), ...attrs });
        n.value = txt(d[k]); n.addEventListener("input", () => { d[k] = n.value; touched(); });
        return field(k, label, n, hint, true);
      };
      const check = (k, label, hint) => { const n = el("input", { type: "checkbox", id: id(k), checked: d[k] || null, "aria-describedby": `${id(k)}-hint` });
        n.addEventListener("change", () => { d[k] = n.checked; touched(); });
        return el("div", { class: "edit-field" }, el("label", { for: id(k), class: "check" }, n, ` ${label}`), el("div", { class: "field-meta faint", id: `${id(k)}-hint`, text: hint })); };
      const setOther = (k, v) => { d[k] = v; const n = formBox.querySelector(`#${id(k)}`); if (n) n.value = v; };
      const errCount = Object.keys(errs).length;
      let body;
      if (kind === "nation") {
        const era = el("select", { class: "input", id: id("era"), "aria-describedby": `${id("era")}-hint` }, ERAS.map(([v, l]) => el("option", { value: v, text: l })));
        era.value = d.era; era.addEventListener("change", () => { d.era = era.value; touched(); });
        body = el("fieldset", { class: "edit-group" }, el("legend", { text: "Step 1: nation brief" }),
          el("div", { class: "edit-grid start-grid" },
            input("name", null, { label: "Nation name", maxlength: "80" }, (v) => { if (!d.slugTouched) setOther("slug", slugify(v)); }),
            input("slug", "Folder name for the new project, e.g. ashen_court.", { label: "Project slug", maxlength: "48", spellcheck: "false" }, () => { d.slugTouched = true; }),
            field("era", "Era", era, "Sets the era and the same-era reference nations.")),
          area("theme", "Theme and mythology", "What the nation is and where its identity comes from.",
            { maxlength: "2000", placeholder: "e.g. Bronze-age sun priests ruling a desert of glass" }),
          area("playstyle", "Playstyle (optional)", "How it should feel to play. The agent can propose one.",
            { maxlength: "2000", placeholder: "e.g. Slow sacred infantry backed by fire mages" }));
      } else {
        const projects = okProjects();
        const radio = (v, label, disabled) => {
          const n = el("input", { type: "radio", name: "st-map-mode", id: id(`mode-${v}`), value: v, checked: d.mode === v || null, disabled: disabled || null });
          n.addEventListener("change", () => { d.mode = v; touched(); draw(); const r = formBox.querySelector(`#${id(`mode-${v}`)}`); if (r) r.focus(); });
          return el("label", { for: id(`mode-${v}`), class: "check" }, n, ` ${label}`);
        };
        const pick = el("select", { class: "input", id: id("project"), "aria-invalid": errs.project ? "true" : null, "aria-describedby": described("project", true) },
          el("option", { value: "", text: projects.length ? "Choose a project" : "No projects yet" }),
          projects.map((p) => el("option", { value: p.slug, text: `${txt(p.mod_name || p.name || p.slug)} (${p.slug})` })));
        pick.value = d.project; pick.addEventListener("change", () => { d.project = pick.value; touched(); });
        body = [
          el("fieldset", { class: "edit-group" }, el("legend", { text: "Project" }),
            el("div", { class: "btn-row start-mode", role: "radiogroup", "aria-label": "Project for the map" },
              radio("new", "New project"), radio("existing", "Existing project", !projects.length)),
            d.mode === "existing"
              ? el("div", { class: "edit-grid start-grid" }, field("project", "Project", pick, "The agent adds the map to this project; its mod files stay unchanged."))
              : el("div", { class: "edit-grid start-grid" },
                input("slug", "Folder name for the new project.", { label: "Project slug", maxlength: "48", spellcheck: "false" }, () => { d.slugTouched = true; }),
                input("project_name", "Defaults to the map title.", { label: "Project name (optional)", maxlength: "80" }))),
          el("fieldset", { class: "edit-group" }, el("legend", { text: "Step 1: map brief" }),
            el("div", { class: "edit-grid start-grid" },
              input("title", null, { label: "Map title", maxlength: "120" }, (v) => {
                if (!d.idTouched) setOther("map_id", mapIdOf(v));
                if (d.mode === "new" && !d.slugTouched) setOther("slug", slugify(v));
              }),
              input("map_id", "Also the file name, <ID>.map: a letter first, then letters, digits or underscores.", { label: "Map ID", maxlength: "48", spellcheck: "false" }, () => { d.idTouched = true; })),
            area("theme", "Geography and theme", "Optional. Passed to the agent as written.",
              { maxlength: "4000", placeholder: "e.g. A volcanic island chain around an inland sea, with frozen highlands in the north" }),
            el("div", { class: "edit-grid start-grid start-nums" },
              MB_INT.map(([k, label, lo, hi]) => input(k, `${lo}-${hi}`, { label, inputmode: "numeric" }))),
            el("div", { class: "edit-grid" }, check("wraparound", "Wraparound", "Map edges connect."),
              check("all_layers", "Seasonal and terrain layers", "Winter plus eight terrain looks per season (18 images per plane).")))];
      }
      formBox.replaceChildren(el("form", { class: "edit-form start-form", novalidate: true, onsubmit: submit }, body,
        el("div", { class: "btn-row edit-actions" },
          el("button", { type: "submit", class: "btn" }, dr.result[kind] ? "Prepare instructions again" : "Prepare agent instructions"),
          errCount ? el("span", { class: "field-err", role: "alert", text: `Fix ${errCount} field${errCount === 1 ? "" : "s"} above.` })
            : el("span", { class: "faint", text: "Step 1 of 3. Nothing is created or saved by this form." }))));
    }
    draw(); drawResult(false);
    return wrap;
  }
  function setupDetails() {
    return el("div", { class: "stack" },
      techSection("Agent setup, MCP and costs (optional)", false,
        el("p", null, "No extra setup is needed: Codex or Claude Code, opened on the extracted Kosmokrator folder, uses Kosmokrator's own command line as the instructions describe. ",
          "The optional MCP server gives the agent Kosmokrator's tools directly. Setup steps are in ", docLink("COMMUNITY-QUICKSTART.md"), "."),
        el("p", null, "One agent is enough. Coordinating several agents is optional; see ", docLink("AGENT-TEAM.md"), "."),
        el("p", null, "Kosmokrator contains no AI model and never edits agent configuration. Agent usage counts against your Codex or Claude plan, or is billed as API usage if the agent signs in with an API key."),
        el("p", null, "Agent conventions: ", docLink("AGENT_USAGE.md"), ". Nations: ", docLink("NATION-DESIGN.md"), ". Maps: ", docLink("AGENT-MAPS.md"), ".")),
      techSection("About the downloaded brief", false,
        el("p", null, "The JSON file records the same brief and instructions for your notes or another agent session. It is a design brief, not a ready author_save request: the agent still reads the current project state, reserves IDs and previews every change before saving."),
        el("p", null, "An existing project can also create a map job directly from its Maps page, under ", el("strong", { text: "Create with an agent" }), ".")));
  }

  // ---------- router ----------
  // "#/p/<slug>/<tab>/<arg>?n=<nation>": path segments, then the hash query.
  function parseHash() {
    const parts = location.hash.replace(/^#\/?/, "").split("?")[0].split("/").filter(Boolean).map((p) => { try { return decodeURIComponent(p); } catch (_) { return p; } });
    return parts;
  }
  const hashQuery = () => new URLSearchParams(location.hash.split("?").slice(1).join("?"));
  let renderSeq = 0;
  async function render() {
    const seq = ++renderSeq;
    const parts = parseHash();
    const keepFocus = document.activeElement && main.contains(document.activeElement) && document.activeElement.closest(".btn-row[role=group]");
    // Selectors that change the route keep focus, so keyboard users can keep browsing with them.
    const keepSelectId = document.activeElement && ["nation-select", "auth-section", "cmd-context"].includes(document.activeElement.id) ? document.activeElement.id : null;
    const keepMode = document.activeElement && main.contains(document.activeElement) && document.activeElement.closest(".mode-switch");
    renderSidebar(parts[0] === "p" ? parts[1] : null);
    if (parts[0] !== "p" || !parts[1]) renderCatalogStatus();
    for (const a of document.querySelectorAll(".topbar-links a")) a.setAttribute("aria-current", a.getAttribute("href") === `#/${parts[0] || ""}` ? "page" : "false");
    if (parts[0] === "docs") {
      document.title = "Docs - Kosmokrator";
      const box = el("div");
      main.replaceChildren(el("h1", { tabindex: "-1", id: "page-title", text: "Documentation" }), box);
      await viewDocs(box, null, parts[1]);
      return;
    }
    for (const a of document.querySelectorAll(".sidebar-tools a")) a.setAttribute("aria-current", a.getAttribute("href") === `#/${parts[0] || ""}` ? "page" : "false");
    if (parts[0] === "import" || parts[0] === "tools") {
      const imp = parts[0] === "import";
      document.title = `${imp ? "Import .dm" : "External tools"} - Kosmokrator`;
      main.replaceChildren(el("h1", { tabindex: "-1", id: "page-title", text: imp ? "Import .dm" : "External tools" }), imp ? viewImport() : viewTools());
      focusTitle();
      return;
    }
    if (parts[0] === "start") {
      document.title = `${parts[1] === "nation" ? "Start a nation" : parts[1] === "map" ? "Start a map" : "Get started"} - Kosmokrator`;
      main.replaceChildren(viewStart(parts[1], hashQuery().get("p")));
      focusTitle();
      return;
    }
    if (parts[0] !== "p" || !parts[1]) {
      document.title = "Kosmokrator";
      main.replaceChildren(viewHome());
      focusTitle();
      return;
    }
    if (parts[2] === "author" && SECTION_EDITORS[parts[3]]) {
      // Old "author/<section>/<key>" links open the same editor inside its section; the rest of the hash is kept.
      parts.splice(2, 1);
      parts.splice(3, 0, "edit");
      const q = location.hash.split("?").slice(1).join("?");
      history.replaceState(null, "", hashPath(...parts) + (q ? `?${q}` : ""));
    }
    const slug = parts[1], tab = parts[2] || "overview", arg = parts[3];
    if (!state.models.has(slug)) main.replaceChildren(stateBox("loading", `Loading ${slug}...`));
    let m;
    try { m = await model(slug); } catch (e) {
      if (seq !== renderSeq) return;
      main.replaceChildren(el("h1", { tabindex: "-1", id: "page-title", text: slug }), errorBox(e, `project ${slug}`),
        el("p", null, el("button", { type: "button", class: "btn", onclick: () => { state.models.delete(slug); render(); } }, "Retry")));
      return;
    }
    if (seq !== renderSeq) return;
    await useIconScope(m);
    if (seq !== renderSeq) return;
    renderCatalogStatus(m);
    // /nation/<id> names the nation itself; elsewhere ?n= (or the remembered choice) selects it.
    const wanted = tab === "nation" && arg ? arg : hashQuery().get("n");
    state.nation = { slug, key: resolveNation(m, wanted) };
    rememberNation(slug, state.nation.key);
    if (hashQuery().get("n") !== state.nation.key) {
      // Make the address bookmarkable without adding a history entry.
      let url = tab === "nation" && arg && state.nation.key === arg ? route("p", slug, tab, arg) : route("p", slug, ...parts.slice(2));
      // Keep other hash parameters (the comparison's ?c=) while adding the nation.
      const extra = [...hashQuery()].filter(([k]) => k !== "n");
      if (extra.length) url += (url.includes("?") ? "&" : "?") + new URLSearchParams(extra).toString();
      history.replaceState(null, "", url);
    }
    document.title = tab === "inspector" ? `Vanilla catalog (${m.project.mod_name || slug}) - Kosmokrator`
      : `${m.project.mod_name || slug} - ${TABS.find((t) => t[0] === tab)?.[1] || ""} - Kosmokrator`;
    if (tab !== "inspector") lastProjectHash.set(slug, location.hash);
    if (tab === "inspector" && inspMounted) {
      // Same project, category and nation: update the list and detail in place (no flash, list scroll and focus kept).
      const res = inspMounted.update(slug, arg, parts[4], state.nation.key);
      if (res) {
        if (res.changed && parts[4]) { const t = $("#insp-detail"); if (t) { t.setAttribute("tabindex", "-1"); t.focus({ preventScroll: false }); } }
        lastRoute = parts.join("/");
        return;
      }
    }
    const body = el("div");
    main.replaceChildren(...projectShell(m, tab, arg), body);
    revealActiveTab();
    const section = (editing, view) => el("div", { class: editing ? "stack authoring" : "stack" }, sectionModes(m, tab, editing, arg), view);
    try {
      if (SECTION_EDITORS[tab] && arg === "edit") body.append(section(true, sectionEditor(m, tab, parts[4])));
      else if (tab === "overview") body.append(viewOverview(m));
      else if (tab === "nation") body.append(viewNation(m, arg));
      else if (tab === "units") body.append(viewUnits(m, arg, parts[4]));
      else if (tab === "pretenders") body.append(viewPretenders(m, arg));
      else if (tab === "sites") body.append(section(false, viewSites(m, arg)));
      else if (tab === "balance") body.append(viewBalance(m));
      else if (tab === "maps") body.append(viewMaps(m, arg));
      else if (tab === "spells") body.append(section(false, viewKindBrowse(m, "spell")));
      else if (tab === "items") body.append(section(false, viewKindBrowse(m, "item")));
      else if (tab === "mercs") body.append(section(false, viewMercs(m, arg)));
      else if (tab === "inspector") body.append(viewInspector(m, arg, parts[4]));
      else if (tab === "other") body.append(viewOther(m));
      else if (tab === "author") body.append(viewAuthoring(m, arg, parts.slice(4)));
      else if (tab === "assets") body.append(viewAssets(m));
      else if (tab === "health") body.append(viewHealth(m));
      else if (tab === "validation") body.append(viewValidation(m));
      else if (tab === "export") body.append(viewExport(m));
      else if (tab === "source") await viewSource(m, arg, body);
      else if (tab === "docs") await viewDocs(body, slug, parts.slice(3).join("/") || null);
      else body.append(stateBox("error", "Unknown section.", tab));
    } catch (e) {
      body.replaceChildren(stateBox("error", "This view failed to render.", String(e && e.message || e)));
    }
    if (keepSelectId) { const s = document.getElementById(keepSelectId); if (s) { s.focus(); lastRoute = parts.join("/"); return; } }
    if (keepFocus) { const b = main.querySelector('.btn-row[role=group] [aria-pressed="true"]'); if (b) b.focus(); return; }
    // Switching Browse/Edit keeps focus on the switch, like the other in-page selectors.
    if (keepMode) { const b = main.querySelector('.mode-switch [aria-current="page"]'); if (b) { b.focus(); lastRoute = parts.join("/"); return; } }
    if (tab === "units" && parts[4] === "compare") {
      // Switching references re-renders in place: keep the scroll position and put focus on the comparison heading.
      const t = $("#compare-title"), same = lastRoute.startsWith(`p/${slug}/units/${arg}/compare`);
      lastRoute = parts.join("/");
      if (t) { t.focus({ preventScroll: same }); return; }
    }
    if (tab === "inspector" && parts[4]) {
      // Picking an entry from the inspector list moves focus to its detail, not back to the page title.
      const t = $("#insp-detail");
      if (t && lastRoute.startsWith(`p/${slug}/inspector`)) { t.setAttribute("tabindex", "-1"); t.focus({ preventScroll: false }); lastRoute = parts.join("/"); return; }
    }
    if (tab === "units" && arg) { const t = $("#unit-title"); if (t && lastRoute.startsWith(`p/${slug}/units`)) { t.focus({ preventScroll: false }); lastRoute = parts.join("/"); return; } }
    lastRoute = parts.join("/");
    if (!(tab === "source" && arg)) focusTitle();
  }
  let lastRoute = "";
  function focusTitle() { const t = $("#page-title"); if (t) { t.focus({ preventScroll: true }); window.scrollTo(0, 0); } }

  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) {
      const s = $(".unit-filter input[type=search]"); if (!s) return;
      e.preventDefault();
      // A collapsed mobile roster hides the search box; open it first.
      if (!s.offsetParent) { const t = $(".roster-collapsed .roster-toggle"); if (t) t.click(); }
      s.focus();
    }
  });
  // Below 820px the sidebar stacks above the page; it starts collapsed away from the project list so content comes first.
  const sidebarToggle = el("button", { type: "button", class: "btn btn-small sidebar-toggle", "aria-controls": "sidebar-tools project-filter project-list", "aria-expanded": "true",
    onclick: () => { state.sidebarOpen = !sidebarOpenNow(); syncSidebar(); } });
  $(".sidebar-tools").id = "sidebar-tools";
  $("#reload-btn").before(sidebarToggle);
  // Content comes first on every route; the list opens on request (desktop always shows it).
  const sidebarOpenNow = () => state.sidebarOpen !== undefined ? state.sidebarOpen : false;
  function syncSidebar() {
    const open = sidebarOpenNow();
    $(".sidebar").classList.toggle("is-collapsed", !open);
    sidebarToggle.setAttribute("aria-expanded", open ? "true" : "false");
    sidebarToggle.textContent = open ? "Hide projects" : "Show projects";
  }
  // Choosing a project or tool goes back to the automatic state, so the chosen page is visible first.
  for (const id of ["#project-list", "#sidebar-tools", "#catalog-nav"]) $(id).addEventListener("click", (e) => { if (e.target.closest("a")) state.sidebarOpen = undefined; });
  window.addEventListener("hashchange", syncSidebar);
  syncSidebar();
  $("#reload-btn").addEventListener("click", async () => {
    state.models.clear();
    invalidateAuth();
    await loadProjects(true);
    render();
    toast("Re-read from disk");
  });
  window.addEventListener("hashchange", render);
  // The skip link targets #main, which the hash router would read as a route; move focus without changing the page.
  $(".skip").addEventListener("click", (e) => { e.preventDefault(); ($("#page-title", main) || main).focus(); });

  (async () => {
    // The icon manifest loads alongside meta so the first render can already show icons; it never blocks on failure.
    const icons = Promise.all([loadTraitIcons(), loadGemIcons()]);
    try { state.meta = await getJSON("/api/meta"); } catch (e) { state.meta = null; }
    await icons;
    renderCatalogStatus();
    await loadProjects(true);
    render();
  })();
})();
