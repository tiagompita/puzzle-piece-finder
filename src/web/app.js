/* Mesa de montagem — frontend without a build step (vanilla JS).
 *
 * Board = raster from the server (/api/board.jpg: art + real cleaned crops, compose_board)
 * + an SVG overlay in the same viewBox (cell units: x = column, y = row * hr). Every overlay
 * element uses a "b-*" class that has a row in the legend (the legend comes from /api/board,
 * the same LEGEND table the server defines; tests/test_server.py checks the coverage).
 * No puzzle rule lives here: twin cells, ghosts, poses and proposals come from the server.
 */
"use strict";

const SVGNS = "http://www.w3.org/2000/svg";
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));

function lsGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
function lsSet(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* the page works without storage */ } }

const S = {
  board: null, fetch: null, ghosts: [], lots: null, sections: null, status: null,
  rows: 47, cols: 64, hr: 1, ppc: 60, ver: 0,
  vb: { x: 0, y: 0, w: 64, h: 47 }, sel: null, tab: "buscar", prevTab: "buscar",
  showGhost: lsGet("tg-ghost") !== "0", showGrid: lsGet("tg-grid") !== "0", showSug: lsGet("tg-sug") === "1",
  mesa: null, mesaOpen: null, mesaQuery: "", mesaFilter: null, detailKey: null, jobLog: [], lastLote: null,
};

// ------------------------------------------------------------ utilities
function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "html") el.innerHTML = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
function s(tag, attrs = {}, ...kids) {
  const el = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined) continue;
    el.setAttribute(k, v);
  }
  for (const kid of kids.flat()) if (kid) el.append(kid);
  return el;
}
const fmt = (v, nd = 1) => (v === null || v === undefined) ? "—" : Number(v).toFixed(nd).replace(".", ",");
const cellTxt = (c) => c ? `(${c[0]}, ${c[1]})` : "—";

async function api(path, opts = {}) {
  const r = await fetch(path, opts);
  let body = null;
  try { body = await r.json(); } catch (e) { body = null; }
  if (!r.ok) {
    const d = body && (body.detail || body.error);
    const msg = typeof d === "string" ? d : (d && d.a_preparar ? "a preparar o projeto…" : `erro ${r.status}`);
    const err = new Error(msg); err.status = r.status; err.body = body; throw err;
  }
  return body;
}

function toast(msg, err = false) {
  const el = h("div", { class: err ? "err" : "" }, msg);
  $("#toast").append(el);
  setTimeout(() => el.remove(), err ? 7000 : 4500);
}

function lightbox(src, cap) {
  $("#lb-img").src = src;
  $("#lb-cap").textContent = cap || "";
  $("#lightbox").hidden = false;
}

const legendRow = (id) => (S.board ? S.board.legend : []).find((r) => r.id === id) || {};
const cls = (id) => legendRow(id).classe;

// ------------------------------------------------------------ board geometry
const cellRect = (l, c, inset = 0) => ({ x: c - 1 + inset, y: (l - 1) * S.hr + inset * S.hr, w: 1 - 2 * inset,
  h: S.hr * (1 - 2 * inset) });
function rectEl(l, c, klass, inset = 0.04, extra = {}) {
  const r = cellRect(l, c, inset);
  return s("rect", { x: r.x.toFixed(4), y: r.y.toFixed(4), width: r.w.toFixed(4), height: r.h.toFixed(4), class: klass, ...extra });
}
function ghostPath(path, cx, cy) {
  if (!path || !path.length) return "";
  return "M" + path.map(([x, y]) => `${(cx + x).toFixed(3)} ${(cy + y * S.hr).toFixed(3)}`).join("L") + "Z";
}
const boardW = () => S.cols;
const boardH = () => S.rows * S.hr;

// ------------------------------------------------------------ view (zoom / pan)
const svg = () => $("#board");
function svgRect() { return svg().getBoundingClientRect(); }
function pxPerCell() { const r = svgRect(); return r.width / S.vb.w; }

function setView(vb) {
  const r = svgRect();
  const asp = r.height / Math.max(1, r.width);
  let { x, y, w } = vb;
  w = Math.min(Math.max(w, 1.2), boardW() * 3);
  const hh = w * asp;
  // keep some of the board on screen
  x = Math.min(Math.max(x, -w * 0.8), boardW() - w * 0.2);
  y = Math.min(Math.max(y, -hh * 0.8), boardH() - hh * 0.2);
  S.vb = { x, y, w, h: hh };
  svg().setAttribute("viewBox", `${x} ${y} ${w} ${hh}`);
  const ppc = pxPerCell();
  $("#lyr-grelha").classList.toggle("off", !(S.showGrid && ppc >= 22));
  $("#lyr-fantasma").classList.toggle("off", !(S.showGhost && ppc >= 7));
  scheduleDetail();
}
function fitRect(x0, y0, x1, y1, pad = 0.04) {
  const r = svgRect();
  const asp = r.height / Math.max(1, r.width);
  const bw = x1 - x0, bh = y1 - y0;
  let w = Math.max(bw, bh / asp) * (1 + 2 * pad);
  const hh = w * asp;
  // keep the view inside the board when the board is larger than the view (no empty band)
  const clamp = (v, size, total) => (size >= total ? (total - size) / 2 : Math.min(Math.max(v, 0), total - size));
  setView({ x: clamp(x0 + bw / 2 - w / 2, w, boardW()), y: clamp(y0 + bh / 2 - hh / 2, hh, boardH()), w });
}
function fitBoard() { fitRect(0, 0, boardW(), boardH(), 0.015); }
function zoomCells(l0, c0, l1, c1, pad = 0.08) { fitRect(c0 - 1, (l0 - 1) * S.hr, c1, l1 * S.hr, pad); }
function zoomAt(factor, cx, cy) {
  const r = svgRect();
  const px = cx === undefined ? 0.5 : (cx - r.left) / r.width;
  const py = cy === undefined ? 0.5 : (cy - r.top) / r.height;
  const mx = S.vb.x + px * S.vb.w, my = S.vb.y + py * S.vb.h;
  const w = S.vb.w / factor;
  const asp = r.height / Math.max(1, r.width);
  setView({ x: mx - px * w, y: my - py * w * asp, w });
}
function clientToBoard(cx, cy) {
  const r = svgRect();
  return { x: S.vb.x + (cx - r.left) / r.width * S.vb.w, y: S.vb.y + (cy - r.top) / r.height * S.vb.h };
}

// detail raster: the visible cells composed at a higher ppc when zoomed in
let detailTimer = null;
function scheduleDetail() {
  clearTimeout(detailTimer);
  detailTimer = setTimeout(loadDetail, 280);
}
function loadDetail() {
  const det = $("#detail");
  const need = pxPerCell() * (window.devicePixelRatio || 1);
  if (!S.board || need <= S.ppc * 1.1) { det.setAttribute("visibility", "hidden"); S.detailKey = null; return; }
  const c0 = Math.max(1, Math.floor(S.vb.x) + 1 - 1), c1 = Math.min(S.cols, Math.ceil(S.vb.x + S.vb.w) + 1);
  const l0 = Math.max(1, Math.floor(S.vb.y / S.hr) + 1 - 1), l1 = Math.min(S.rows, Math.ceil((S.vb.y + S.vb.h) / S.hr) + 1);
  if (c1 < c0 || l1 < l0) return;
  const n = (c1 - c0 + 1) * (l1 - l0 + 1);
  let ppc = Math.min(240, Math.ceil(need / 20) * 20);
  ppc = Math.min(ppc, Math.floor(Math.sqrt(11e6 / n)));
  if (ppc <= S.ppc * 1.1) { det.setAttribute("visibility", "hidden"); S.detailKey = null; return; }
  const key = `${l0},${c0},${l1},${c1}@${ppc}#${S.ver}`;
  if (key === S.detailKey) return;
  S.detailKey = key;
  const url = `/api/board.jpg?ppc=${ppc}&region=${l0},${c0},${l1},${c1}&v=${S.ver}`;
  const img = new Image();
  img.onload = () => {
    if (S.detailKey !== key) return;
    det.setAttribute("href", url);
    det.setAttribute("x", c0 - 1); det.setAttribute("y", (l0 - 1) * S.hr);
    det.setAttribute("width", c1 - c0 + 1); det.setAttribute("height", (l1 - l0 + 1) * S.hr);
    det.setAttribute("visibility", "visible");
    document.body.dataset.detail = key;
  };
  img.src = url;
}

function initPointer() {
  const el = svg();
  const ptrs = new Map();
  let start = null, pinch = null, moved = false;
  el.addEventListener("wheel", (e) => {
    if (e.ctrlKey || e.metaKey) return;   // Ctrl+wheel / trackpad pinch = browser page zoom
    e.preventDefault();
    const f = Math.exp(-e.deltaY * (e.deltaMode === 1 ? 0.05 : 0.0018));
    zoomAt(f, e.clientX, e.clientY);
  }, { passive: false });
  el.addEventListener("pointerdown", (e) => {
    el.setPointerCapture(e.pointerId);
    ptrs.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (ptrs.size === 1) { start = { x: e.clientX, y: e.clientY, vb: { ...S.vb } }; moved = false; }
    if (ptrs.size === 2) {
      const [a, b] = [...ptrs.values()];
      pinch = { d: Math.hypot(a.x - b.x, a.y - b.y), vb: { ...S.vb }, mx: (a.x + b.x) / 2, my: (a.y + b.y) / 2 };
      moved = true;
    }
  });
  el.addEventListener("pointermove", (e) => {
    if (!ptrs.has(e.pointerId)) return;
    ptrs.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const r = svgRect();
    if (ptrs.size >= 2 && pinch) {
      const [a, b] = [...ptrs.values()];
      const d = Math.hypot(a.x - b.x, a.y - b.y);
      const f = d / Math.max(1, pinch.d);
      const px = (pinch.mx - r.left) / r.width, py = (pinch.my - r.top) / r.height;
      const mx = pinch.vb.x + px * pinch.vb.w, my = pinch.vb.y + py * pinch.vb.h;
      const w = pinch.vb.w / f, asp = r.height / r.width;
      const nmx = (a.x + b.x) / 2, nmy = (a.y + b.y) / 2;
      const qx = (nmx - r.left) / r.width, qy = (nmy - r.top) / r.height;
      setView({ x: mx - qx * w, y: my - qy * w * asp, w });
      return;
    }
    if (start && ptrs.size === 1) {
      const dx = e.clientX - start.x, dy = e.clientY - start.y;
      if (Math.hypot(dx, dy) > 6) moved = true;
      if (moved) {
        el.classList.add("dragging");
        setView({ x: start.vb.x - dx / r.width * start.vb.w, y: start.vb.y - dy / r.height * start.vb.h, w: start.vb.w });
      }
    }
  });
  const up = (e) => {
    if (!ptrs.has(e.pointerId)) return;
    ptrs.delete(e.pointerId);
    el.classList.remove("dragging");
    if (ptrs.size < 2) pinch = null;
    if (ptrs.size === 0) {
      if (!moved && start && e.type === "pointerup") {
        const p = clientToBoard(e.clientX, e.clientY);
        const c = Math.floor(p.x) + 1, l = Math.floor(p.y / S.hr) + 1;
        hideSugPicker();
        if (l >= 1 && l <= S.rows && c >= 1 && c <= S.cols) {
          const hits = suggestionsAt(l, c);
          if (hits.length === 1) openMesaGroup(hits[0].g.id, 1);
          else if (hits.length > 1) showSugPicker(hits, l, c, e.clientX, e.clientY);
          else openCell(l, c, { zoom: false });
        }
      }
      start = null;
    } else if (ptrs.size === 1) {
      const [a] = [...ptrs.values()];
      start = { x: a.x, y: a.y, vb: { ...S.vb } };
    }
  };
  el.addEventListener("pointerup", up);
  el.addEventListener("pointercancel", up);
  el.addEventListener("dblclick", (e) => zoomAt(2, e.clientX, e.clientY));
  $("#z-in").onclick = () => zoomAt(1.6);
  $("#z-out").onclick = () => zoomAt(1 / 1.6);
  $("#z-fit").onclick = fitBoard;
  window.addEventListener("resize", () => setView(S.vb));
}

// ------------------------------------------------------------ board layers
function drawBoard() {
  const b = S.board;
  S.rows = b.rows; S.cols = b.cols; S.hr = b.hr; S.rotGemea = b.rotacao_gemea_deg; S.ppc = b.board_ppc; S.ver = b.versao;
  $("#board-bg").setAttribute("width", boardW()); $("#board-bg").setAttribute("height", boardH());
  const r = $("#raster");
  r.setAttribute("width", boardW()); r.setAttribute("height", boardH());
  const url = `/api/board.jpg?ppc=${S.ppc}&v=${S.ver}`;
  if (r.getAttribute("href") !== url) {
    const img = new Image();
    img.onload = () => { r.setAttribute("href", url); document.body.dataset.raster = String(S.ver); };
    img.src = url;
  }
  S.detailKey = null;
  // legacy (occupied without a silhouette)
  const leg = $("#lyr-legado"); leg.replaceChildren();
  const bor = $("#lyr-borda"); bor.replaceChildren();
  b.cells.forEach((row, i) => row.forEach((cell, j) => {
    if (cell.estado === "ocupada_legado") leg.append(rectEl(i + 1, j + 1, cls("legado"), 0));
  }));
  for (const [l, c] of b.borda_em_falta) bor.append(rectEl(l, c, cls("borda"), 0.05));
  const kn = $("#lyr-conhecida"); kn.replaceChildren();
  for (const k of b.posicoes_conhecidas) kn.append(rectEl(k.cell[0], k.cell[1], cls("conhecida"), 0.07));
  // grid
  let d = "";
  for (let c = 0; c <= S.cols; c++) d += `M${c} 0V${boardH().toFixed(4)}`;
  for (let l = 0; l <= S.rows; l++) d += `M0 ${(l * S.hr).toFixed(4)}H${S.cols}`;
  $("#lyr-grelha").replaceChildren(s("path", { d, class: cls("grelha") }));
  drawProgress();
  drawSel();
  drawLegend();
}
function drawProgress() {
  const p = S.board.progresso;
  $("#puzzle-name").textContent = S.board.puzzle || "Mesa de montagem";
  const pct = (100 * p.colocadas / p.total);
  const st = S.board.stats || {};
  const semSil = st.celulas_so_foto !== undefined
    ? `${st.celulas_so_foto} por confirmar (foto)` + (st.celulas_pista ? ` · ${st.celulas_pista} marcadas por ti` : "")
    : `${p.sem_silhueta} ocupadas sem silhueta`;
  $("#progress-txt").textContent = `${p.colocadas} colocadas · ${semSil} · ${p.total - p.ocupadas} por colocar (de ${p.total})`;
  $("#pb-placed").style.width = pct + "%";
  $("#pb-legacy").style.width = (100 * p.sem_silhueta / p.total) + "%";
}
function fetchClass(e) {
  if (e.origin === "par") return cls("buscar_par");
  if (e.origin === "posicao_conhecida") return cls("conhecida");
  if (e.decision === "aceite" || e.decision === "colocavel" || e.decision === "confirmado") return cls("buscar");
  return cls("buscar_amb");
}
function drawFetchLayer() {
  const g = $("#lyr-buscar"); g.replaceChildren();
  const seen = new Set();
  for (const e of fetchPieces()) {
    if (!e.cell || e.grupo === "guarda_posicao") continue;
    const k = e.cell.join(",");
    if (seen.has(k)) continue;
    seen.add(k);
    g.append(rectEl(e.cell[0], e.cell[1], fetchClass(e), 0.1));
  }
}
function drawGhosts() {
  const g = $("#lyr-fantasma"); g.replaceChildren();
  for (const gh of S.ghosts) {
    const cx = gh.cell[1] - 0.5, cy = (gh.cell[0] - 0.5) * S.hr;
    g.append(s("path", { d: ghostPath(gh.path, cx, cy), class: cls("fantasma") }));
  }
}
function drawSel() {
  const g = $("#lyr-sel"); g.replaceChildren();
  if (S.sel) g.append(rectEl(S.sel[0], S.sel[1], cls("selecao"), 0.0));
}
function drawMesa() {
  const g = $("#lyr-mesa"); g.replaceChildren();
  if (!S.mesa) return;
  for (const [l, c] of S.mesa.footprint) if (l >= 1 && l <= S.rows && c >= 1 && c <= S.cols) g.append(rectEl(l, c, cls("mesa"), 0.06));
}

// legend: the server's table; swatches use the very same classes as the board
function legendSwatch(row) {
  const sw = s("svg", { viewBox: `-0.1 ${-0.1 * S.hr} 1.2 ${1.2 * S.hr}`, "aria-hidden": "true" });
  if (row.tipo === "raster") {
    // a real piece of the raster: a placed cell for "peca", an empty one for "vazia"
    const want = row.id === "peca" ? "colocada" : "vazia";
    let found = null;
    const prefer = row.id === "peca" ? [[44, 6], [46, 3], [40, 30]] : [[10, 30], [20, 20], [5, 5]];
    for (const [l, c] of prefer) if (S.board.cells[l - 1] && S.board.cells[l - 1][c - 1] && S.board.cells[l - 1][c - 1].estado === want) { found = [l, c]; break; }
    if (!found) {
      outer: for (let i = 0; i < S.rows; i++) for (let j = 0; j < S.cols; j++) if (S.board.cells[i][j].estado === want) { found = [i + 1, j + 1]; break outer; }
    }
    if (found) {
      const [l, c] = found;
      sw.setAttribute("viewBox", `${c - 1.1} ${(l - 1.1) * S.hr} 1.2 ${1.2 * S.hr}`);
      sw.append(s("image", { href: `/api/board.jpg?ppc=${S.ppc}&v=${S.ver}`, x: 0, y: 0, width: boardW(), height: boardH(),
        preserveAspectRatio: "none" }));
    }
    return sw;
  }
  if (row.id === "fantasma") {
    const gh = S.ghosts[0];
    const path = gh ? gh.path : [[-0.45, -0.45], [0.45, -0.45], [0.45, 0.45], [-0.45, 0.45]];
    sw.append(s("path", { d: ghostPath(path, 0.5, 0.5 * S.hr), class: row.classe }));
  } else if (row.id === "grelha") {
    sw.append(s("path", { d: `M0.5 -0.1V${1.1 * S.hr}M-0.1 ${0.5 * S.hr}H1.1`, class: row.classe }));
  } else {
    const inset = row.id === "legado" || row.id === "selecao" ? 0.02 : 0.08;
    sw.append(s("rect", { x: inset, y: inset * S.hr, width: 1 - 2 * inset, height: S.hr * (1 - 2 * inset), class: row.classe }));
  }
  return sw;
}
function drawLegend() {
  const L = $("#legend"); L.replaceChildren(h("span", { class: "lg-title" }, "Legenda"));
  for (const row of S.board.legend) {
    L.append(h("span", { class: "lg", title: `${row.rotulo}: ${row.detalhe || row.texto}`, "data-legend": row.id },
      legendSwatch(row), h("b", {}, row.rotulo), h("span", { class: "lg-t" }, row.texto)));
  }
}

// ------------------------------------------------------------ data loading
async function loadBoard() {
  const [b, gh] = await Promise.all([api("/api/board"), api("/api/ghosts")]);
  S.board = b; S.ghosts = gh.fantasmas || [];
  const first = !svg().getAttribute("viewBox");
  drawBoard(); drawGhosts();
  if (first) fitBoard(); else setView(S.vb);
}
async function loadFetch() {
  S.fetch = await api("/api/fetch");
  warnPlaceable();
  drawFetchLayer();
  renderBuscar();
}
/** A stored position (saquinho) whose cell now has a mounted neighbour: tell Tiago to fetch the bag. */
function warnPlaceable() {
  const now = new Set(fetchPieces().filter((e) => e.estado_atual === "posicao_conhecida" && e.grupo === "coloca_agora").map((e) => e.piece));
  if (S.placeable) {
    for (const e of fetchPieces()) {
      if (now.has(e.piece) && !S.placeable.has(e.piece)) {
        toast(`Peça ${e.piece} (saquinho ${cellTxt(e.cell)}) já tem vizinha montada: vai buscar o saquinho`);
        $("#n-buscar").classList.add("aviso");
      }
    }
  }
  S.placeable = now;
}
const fetchPieces = () => (S.fetch ? S.fetch.entries.filter((e) => e.piece) : []);
async function loadLots() { S.lots = await api("/api/lots"); renderLotes(); }
async function loadSections() { S.sections = await api("/api/sections"); renderMesa(); }

async function loadAll() {
  await loadBoard();
  await loadFetch();
  loadSections().catch((e) => toast(e.message, true));
  loadReports().catch(() => {});
  if (S.tab === "lotes") loadLots().catch((e) => toast(e.message, true));
  renderImportar();
}

// ------------------------------------------------------------ tabs
function showTab(t) {
  if (t !== "celula") S.prevTab = t;
  if (t === "buscar") $("#n-buscar").classList.remove("aviso");
  S.tab = t;
  $$("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === t));
  $$(".tab").forEach((el) => el.classList.toggle("on", el.id === `tab-${t}`));
  if (t === "lotes" && !S.lots) loadLots().catch((e) => toast(e.message, true));
  if (t === "reports") loadReports().catch((e) => toast(e.message, true));
  if (t === "mesa" && !S.sections) loadSections().catch((e) => toast(e.message, true));
  if (t === "mesa" && S.mesaOpen && S.sections) {
    const g = S.sections.find((x) => x.id === S.mesaOpen.id), c = g && (g.candidatos.find((x) => x.rank === S.mesaOpen.rank) || groupBest(g));
    if (c) { S.mesa = { id: g.id, rank: c.rank, footprint: c.footprint }; drawMesa(); }
  }
  if (t !== "celula" && t !== "report" && S.sel) { S.sel = null; drawSel(); }
  if (t !== "mesa" && S.mesa) { S.mesa = null; drawMesa(); }
}

// ------------------------------------------------------------ actions
async function act(body, btn) {
  const btns = btn ? $$("button", btn.closest(".actions") || btn.parentElement) : [];
  btns.forEach((b) => (b.disabled = true));
  const old = btn ? btn.textContent : null;
  if (btn) btn.textContent = "a gravar…";
  try {
    const r = await api("/api/confirm", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    for (const m of r.mensagens || []) toast(m);
    if (r.invariantes && r.invariantes.length) toast("INVARIANTES: " + r.invariantes.join("; "), true);
    await refreshAfterWrite();
    return r;
  } catch (e) {
    toast(e.message, true);
  } finally {
    btns.forEach((b) => (b.disabled = false));
    if (btn) btn.textContent = old;
  }
}
async function refreshAfterWrite() {
  await Promise.all([loadBoard(), loadFetch()]);
  if (S.lots) loadLots().catch(() => {});
  loadSections().catch(() => {});
  if (S.tab === "celula" && S.sel) openCell(S.sel[0], S.sel[1], { zoom: false, keep: true });
}

// ------------------------------------------------------------ "vai buscar"
function pieceImage(e, size = 150) {
  const box = h("div", { class: "pimg" });
  const pose = e.pose_known ? "board" : "scan";
  box.append(h("img", { src: `/api/pieces/${e.piece}.png?pose=${pose}&size=${size * 2}&v=${S.ver}`, alt: `peça ${e.piece}`,
    loading: "lazy" }));
  const span = S.board ? S.board.span_cells : 1.8;
  const half = span / 2;
  const ov = s("svg", { viewBox: `${-half} ${-half} ${span} ${span}`, "aria-hidden": "true" });
  ov.append(s("rect", { x: -0.5, y: -S.hr / 2, width: 1, height: S.hr, class: "pv-cell" }));
  if (e.ghost && e.pose_known && S.showGhost) ov.append(s("path", { d: ghostPath(e.ghost, 0, 0), class: cls("fantasma") }));
  if (e.pose_known) ov.append(s("path", { d: `M0 ${-half + 0.02}L-0.06 ${-half + 0.13}L0.06 ${-half + 0.13}Z`, class: "pv-top" }));
  box.append(ov);
  return box;
}
function imageCaption(e) {
  return e.pose_known ? "rodada como fica (▲ = topo)" : "como foi digitalizada (rotação desconhecida)";
}
const CARD_KEY = "Em cada peça: ▲ = topo do tabuleiro, quadrado tracejado = a célula, contorno claro = fantasma da gémea " +
  "(a forma esperada). À direita, a folha do saco com a peça a âmbar.";
function miniMap(cell) {
  const m = s("svg", { class: "mini", viewBox: `0 0 ${boardW()} ${boardH()}`, role: "img", "aria-label": `célula ${cellTxt(cell)}` });
  m.append(s("image", { href: `/api/board.jpg?ppc=6&v=${S.ver}`, x: 0, y: 0, width: boardW(), height: boardH(), preserveAspectRatio: "none" }));
  if (cell) {
    const cx = cell[1] - 0.5, cy = (cell[0] - 0.5) * S.hr;
    m.append(s("path", { d: `M${cx} 0V${boardH()}M0 ${cy}H${boardW()}`, class: "mini-cruz" }));
    m.append(s("rect", { x: cell[1] - 1.9, y: (cell[0] - 1.9) * S.hr, width: 2.8, height: 2.8 * S.hr, class: "mini-alvo" }));
  }
  return m;
}
const DEC_TXT = { aceite: "aceite", ambigua: "ambígua", colocavel: "colocável", candidata: "candidata", proposto: "par proposto",
  confirmado: "confirmado", por_ancorar: "sem lugar" };
function proposalCard(e, opts = {}) {
  const card = h("div", { class: "card" + (e.decision === "ambigua" ? " amb" : ""), "data-piece": e.piece });
  const head = h("div", {},
    h("div", { class: "who" }, e.lote !== null && e.lote !== undefined ? ["Saco ", h("span", { class: "n" }, e.lote), " · nº ",
      h("span", { class: "n" }, e.n_no_lote)] : [`${e.piece}`]),
    h("div", { class: "where" }, "→ célula ", h("b", {}, cellTxt(e.cell)), " ", h("span", { class: `tag ${e.decision}` }, DEC_TXT[e.decision] || e.decision)),
    h("div", { class: "small muted" }, `${e.origem_txt || e.origin}` + (e.twin_id ? ` ${e.twin_id} em ${cellTxt(e.twin_cell)}` : "") +
      ` · ${e.piece}` + (e.pose_known ? ` · rodar ${fmt(e.theta_deg, 0)}°` : "")),
    h("ul", { class: "reasons" }, (e.razoes_txt || []).map((t) => h("li", {}, t))),
  );
  const top = h("div", { class: "card-top" }, h("div", {}, pieceImage(e), h("div", { class: "pimg-cap" }, imageCaption(e))), head);
  card.append(top);
  const sheetUrl = e.scan_id ? `/api/sheets/${e.scan_id}.jpg?highlight=${e.piece}` : null;
  const mid = h("div", { class: "card-mid" },
    h("div", {}, miniMap(e.cell), h("div", { class: "mini-cap" }, `linha ${e.cell ? e.cell[0] : "—"} · coluna ${e.cell ? e.cell[1] : "—"}`)),
    sheetUrl ? h("div", {},
      h("img", { class: "sheet-thumb", loading: "lazy", src: `${sheetUrl}&max=640&v=${S.ver}`, alt: `folha ${e.scan_id}`,
        onclick: () => lightbox(`${sheetUrl}&max=1400&v=${S.ver}`, `Folha ${e.scan_id} do saco ${e.lote}: a peça nº ${e.n_no_lote} está a âmbar`) }),
      h("div", { class: "sheet-cap" }, `folha ${e.scan_id}: nº ${e.n_no_lote ?? "?"} a âmbar (toca para ampliar)`)) : h("div"));
  card.append(mid);
  const acts = h("div", { class: "actions" });
  if (e.cell && e.grupo === "guarda_posicao") {
    acts.append(h("button", { class: "btn primary", type: "button", title: "sem vizinha montada para confirmar o encaixe: guarda a peça num saquinho com esta posição",
      onclick: (ev) => act({ acao: "position_known", piece: e.piece, cell: e.cell, origin: e.origin, nota: "saquinho" }, ev.currentTarget) }, `Guardei num saquinho ${cellTxt(e.cell)}`));
    acts.append(h("button", { class: "btn", type: "button", onclick: (ev) => act({ acao: "reject", piece: e.piece }, ev.currentTarget) }, "Não encaixa"));
  } else if (e.cell) {
    acts.append(h("button", { class: "btn primary", type: "button", onclick: (ev) => act({ acao: "place", piece: e.piece, cell: e.cell, origin: e.origin }, ev.currentTarget) }, "Coloquei"));
    if (e.origin !== "posicao_conhecida") {
      acts.append(h("button", { class: "btn", type: "button", onclick: (ev) => act({ acao: "reject", piece: e.piece }, ev.currentTarget) }, "Não encaixa"));
      acts.append(h("button", { class: "btn", type: "button", title: "a peça fica guardada à parte, à espera de uma vizinha", onclick: (ev) => act({ acao: "position_known", piece: e.piece, cell: e.cell, origin: e.origin }, ev.currentTarget) }, "Guardar posição"));
    }
  }
  acts.append(reportButton({ piece: e.piece, cell: e.cell, vista: "cartao" }));
  if (!opts.noLocate && e.cell) acts.append(h("button", { class: "btn slim", type: "button", onclick: () => showCellOnBoard(e.cell[0], e.cell[1]) }, "Ver no tabuleiro"));
  card.append(acts);
  card.append(h("details", { class: "tech" }, h("summary", {}, "razões técnicas"), h("ul", {}, (e.reasons || []).map((t) => h("li", {}, t)))));
  return card;
}
// a piece without a mounted orthogonal neighbour is not fetched yet (rule of Tiago): it lives in "Guardadas"
const isStored = (e) => e.grupo === "guarda_posicao";
const pendingPieces = () => fetchPieces().filter((e) => !e.estado_atual || ["solta", "emparelhada", "posicao_conhecida"].includes(e.estado_atual));
function renderBuscar() {
  const T = $("#tab-buscar"); T.replaceChildren();
  const es = pendingPieces().filter((e) => !isStored(e));
  $("#n-buscar").textContent = es.length ? String(es.length) : "";
  renderGuardadas();
  if (!es.length) {
    T.append(h("div", { class: "empty" }, h("strong", {}, "Nada a ir buscar agora."),
      "Importa o scan de um saco para o programa procurar gémeas e pares.",
      h("div", { class: "actions", style: "justify-content:center" }, h("button", { class: "btn primary", type: "button", onclick: () => showTab("importar") }, "Importar scan"))));
  } else {
    const nAc = es.filter((e) => e.decision === "aceite" || e.decision === "colocavel").length;
    T.append(h("p", { class: "summary" }, `${es.length} peças para ir buscar em ${new Set(es.map((e) => e.lote ?? "—")).size} saco(s): ` +
      `${nAc} aceites, ${es.length - nAc} com dúvida. Pela ordem: as mais seguras primeiro. Todas têm uma vizinha montada para confirmar o encaixe.`),
      h("p", { class: "summary small" }, CARD_KEY));
    const by = new Map();
    for (const e of es) { const k = e.lote ?? "—"; if (!by.has(k)) by.set(k, []); by.get(k).push(e); }
    const keys = [...by.keys()].sort((a, b) => (a === "—") - (b === "—") || a - b);
    T.append(h("h2", { class: "grupo-head", "data-grupo": "coloca_agora" }, `Coloca agora (${es.length})`, h("span", { class: "muted small" }, " têm uma vizinha montada para confirmar o encaixe")));
    for (const k of keys) {
      T.append(h("div", { class: "lot-head" }, h("span", { class: "bag" }, k === "—" ? "Sem saco" : `Saco ${k}`), h("span", { class: "muted small" }, `${by.get(k).length} peças`)));
      for (const e of by.get(k).sort((a, b) => a.ordem - b.ordem)) T.append(proposalCard(e));
    }
  }
  const sup = S.fetch.suprimidas || [];
  if (sup.length) {
    T.append(h("details", { class: "tech" }, h("summary", {}, `${sup.length} sugestões não mostradas (candidata única, por política)`),
      h("ul", {}, sup.map((x) => h("li", {}, `saco ${x.lote ?? "—"} nº ${x.n_no_lote ?? "—"} (${x.piece}) → ${cellTxt(x.cell)}: ${x.reason || ""}`)))));
  }
}

// locate icon (target with a crosshair): the button takes the view to the piece
function locateIcon() {
  const i = h("span", { class: "ico", "aria-hidden": "true" });
  i.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="1.5" fill="currentColor"/><path d="M12 2v4M12 18v4M2 12h4M18 12h4"/></svg>';
  return i;
}
// ------------------------------------------------------------ guardadas (sem vizinha ortogonal montada)
function renderGuardadas() {
  const T = $("#tab-guardadas");
  const wasOpen = !!(T.querySelector("details.guardadas") || {}).open;   // a re-render (new report, new fetch) keeps it as it was
  T.replaceChildren();
  const gs = pendingPieces().filter(isStored);
  $("#n-guardadas").textContent = gs.length ? String(gs.length) : "";
  T.append(h("p", { class: "aviso-box" }, "Não procurar ainda: estas peças têm posição provável mas nenhuma vizinha ortogonal montada (diagonais e moldura não contam), por isso o encaixe ainda não se pode confirmar. Só aparecem em «Vai buscar» quando uma vizinha for montada."));
  if (!gs.length) { T.append(h("div", { class: "empty" }, h("strong", {}, "Nenhuma peça guardada à espera de vizinha."))); return; }
  const d = h("details", { class: "guardadas", "data-grupo": "guarda_posicao" },
    h("summary", {}, `Guardadas com posição, ainda sem vizinha (${gs.length})`));
  for (const e of gs.sort((a, b) => a.ordem - b.ordem)) d.append(proposalCard(e));
  d.open = wasOpen;
  T.append(d);
}

// ------------------------------------------------------------ reports (lista, detalhe, estados como eventos)
const ESTADO_TXT = { aberto: "aberto", fechado: "resolvido", eliminado: "eliminado" };
const when = (t) => (t ? String(t).replace("T", " ").slice(0, 16) : "");
async function loadReports() {
  const r = await api("/api/reports?todos=true&eliminados=true");
  S.reports = r.reports || [];
  loadSuspeitas().catch(() => {});
  S.reportFilter = S.reportFilter || "aberto";
  renderReports();
  if (S.tab === "report" && S.reportOpen) {
    const cur = S.reports.find((x) => x.id === S.reportOpen);
    if (cur) renderReportDetail(cur);
  }
  renderBuscar();               // the cards' button is «Editar report» for pieces that already have one
  if (S.tab === "celula" && S.sel) openCell(S.sel[0], S.sel[1], { keep: true });
}
function renderReports() {
  const T = $("#tab-reports"); T.replaceChildren();
  if (typeof renderSuspeitas === "function") renderSuspeitas(T);
  const all = S.reports || [];
  const cnt = (e) => all.filter((r) => r.estado === e).length;
  const nOpen = cnt("aberto"), nRes = cnt("fechado"), nDel = cnt("eliminado");
  $("#n-reports").textContent = nOpen ? String(nOpen) : "";
  const f = S.reportFilter || "aberto";
  T.append(h("p", { class: "summary", id: "reports-count" }, `${nOpen} aberto${nOpen === 1 ? "" : "s"} · ${nRes} resolvido${nRes === 1 ? "" : "s"}` + (nDel ? ` · ${nDel} eliminado${nDel === 1 ? "" : "s"}` : "")));
  const bar = h("div", { class: "actions", id: "reports-filter" });
  for (const [k, t] of [["aberto", "Abertos"], ["fechado", "Resolvidos"], ["eliminado", "Eliminados"]]) {
    bar.append(h("button", { class: "btn slim" + (f === k ? " primary" : ""), type: "button", "data-filter": k, onclick: () => { S.reportFilter = k; renderReports(); } }, t));
  }
  T.append(bar);
  const rows = all.filter((r) => r.estado === f);
  if (!rows.length) { T.append(h("div", { class: "empty" }, h("strong", {}, `Sem reports ${f === "aberto" ? "abertos" : f === "fechado" ? "resolvidos" : "eliminados"}.`))); return; }
  for (const r of rows) {
    // clickable (read-only): highlights the piece / cell on the board and STAYS in this tab; nothing is written
    const go = () => locateReportInPlace(r).catch((e) => toast(e.message, true));
    const row = h("div", { class: "card report-row" + (r.piece ? " has-thumb" : ""), "data-report": r.id, role: "button", tabindex: "0",
      title: "Ver no tabuleiro", onclick: go,
      onkeydown: (ev) => { if (ev.target === ev.currentTarget && (ev.key === "Enter" || ev.key === " ")) { ev.preventDefault(); go(); } } },
      r.piece ? h("img", { class: "rthumb", loading: "lazy", src: `/api/pieces/${r.piece}.png?pose=scan&size=64`, alt: "", width: 64, height: 64 }) : null,
      h("div", { class: "rbody" },
        h("div", { class: "small rhead" }, h("b", {}, r.id),
          r.piece ? h("span", { class: "chip" }, r.piece) : null,
          r.cell ? h("span", { class: "chip" }, cellTxt(r.cell)) : null,
          !r.piece && !r.cell ? h("span", { class: "chip" }, "geral") : null,
          ` ${ESTADO_TXT[r.estado] || r.estado} · ${r.tipo}` + (r.n_edicoes ? ` · editado ${r.n_edicoes}×` : "")),
        h("div", {}, r.texto || h("span", { class: "muted" }, "(sem texto)")),
        r.nota ? h("div", { class: "small muted" }, `nota: ${r.nota}`) : null),
      h("button", { class: "rgo", type: "button", "aria-label": `Abrir report ${r.id}`, title: "Abrir o report",
        onclick: (ev) => { ev.stopPropagation(); openReportDetail(r); } }, "→"));
    T.append(row);
  }
}
/** Row click: highlight + zoom on the board, WITHOUT leaving the Reports tab and without writing anything. */
async function locateReportInPlace(r) {
  if (r.piece) {
    let d = null;
    try { d = await api(`/api/pieces/${r.piece}`); } catch (e) { d = null; }
    if (d && d.celula && (d.estado === "colocada" || d.estado === "posicao_conhecida")) { showCellOnBoard(d.celula[0], d.celula[1]); return; }
    const e = pendingPieces().find((x) => x.piece === r.piece);
    if (e) { toast(`${r.piece} está em ${isStored(e) ? "Guardadas" : "Vai buscar"}`); return; }
    if (r.cell) { showCellOnBoard(r.cell[0], r.cell[1]); return; }
    toast(d ? `${r.piece} existe: ${ST_TXT[d.estado] || d.estado}, sem célula no tabuleiro` : `${r.piece}: não encontrada`);
    return;
  }
  if (r.cell) { showCellOnBoard(r.cell[0], r.cell[1]); return; }
  toast(`${r.id}: report geral, sem localização`);
}
function openReportDetail(r) {
  S.reportOpen = r.id;
  renderReportDetail(r);
  showTab("report");
}
function renderReportDetail(r) {
  const T = $("#tab-report"); T.replaceChildren();
  const ctx = { piece: r.piece || null, cell: r.cell || null, vista: r.vista || null };
  const chips = h("div", { class: "rhead" },
    r.piece ? h("button", { class: "chip chip-btn", type: "button", title: "ver no tabuleiro", onclick: () => locateReportInPlace(r).catch((e) => toast(e.message, true)) }, r.piece) : null,
    r.cell ? h("button", { class: "chip chip-btn", type: "button", title: "ver no tabuleiro", onclick: () => showCellOnBoard(r.cell[0], r.cell[1]) }, cellTxt(r.cell)) : null,
    !r.piece && !r.cell ? h("span", { class: "chip" }, "geral") : null);
  const hist = [{ estado: "criado", t: r.t, nota: "" }].concat((r.historico && r.historico.length) ? r.historico
    : (r.estado === "fechado" && r.fechado_em ? [{ estado: "fechado", t: r.fechado_em, nota: r.nota || "" }] : []));
  const histTxt = { criado: "criado", aberto: "reaberto", fechado: "resolvido", eliminado: "eliminado" };
  const nCap = !r.captura ? null : h("img", { class: "rcap", alt: `captura de ${r.id}`, src: `/api/reports/${r.id}/captura`, onerror: (ev) => ev.target.remove() });
  const act = h("div", { class: "actions rdetail-actions" });
  const btn = (txt, fn, cls = "") => h("button", { class: `btn slim ${cls}`.trim(), type: "button", onclick: fn }, txt);
  act.append(btn("Ver no tabuleiro", () => locateReportInPlace(r).catch((e) => toast(e.message, true))));
  if (r.estado === "aberto") {
    act.append(btn("Editar", () => openReport(ctx, r)));
    act.append(btn("Marcar resolvido", () => askEstado(r, "close"), "primary"));
    act.append(btn("Eliminar", () => askEstado(r, "delete")));
  } else if (r.estado === "fechado") {
    act.append(btn("Reabrir", () => setEstado(r, "reopen")));
    act.append(btn("Eliminar", () => askEstado(r, "delete")));
  } else {
    act.append(btn("Restaurar", () => setEstado(r, "restore"), "primary"));
  }
  T.append(...[
    h("div", { class: "cell-head" }, btn("← Reports", () => showTab("reports"))),
    h("h3", { class: "rtitle" }, r.id, h("span", { class: `chip rstate st-${r.estado}` }, ESTADO_TXT[r.estado] || r.estado)),
    h("p", { class: "small muted" }, `${TIPOS_TXT[r.tipo] || r.tipo} · ${when(r.t)}` + (r.n_edicoes ? ` · editado ${r.n_edicoes}×` : "")),
    chips,
    r.piece ? h("div", { class: "rthumbs" },
      h("figure", {}, h("img", { src: `/api/pieces/${r.piece}.png?pose=board&size=160`, alt: `${r.piece} no tabuleiro`, width: 160, height: 160 }), h("figcaption", { class: "small muted" }, "no tabuleiro")),
      h("figure", {}, h("img", { src: `/api/pieces/${r.piece}.png?pose=scan&size=160`, alt: `${r.piece} no scan`, width: 160, height: 160 }), h("figcaption", { class: "small muted" }, "no scan"))) : null,
    nCap,
    h("p", { class: "rtexto" }, r.texto || h("span", { class: "muted" }, "(sem texto)")),
    r.nota ? h("p", { class: "small" }, h("b", {}, "Nota: "), r.nota) : null,
    h("div", { class: "small rhist" }, h("b", {}, "Histórico"),
      h("ul", {}, hist.map((x) => h("li", {}, `${histTxt[x.estado] || x.estado} · ${when(x.t)}` + (x.nota ? ` · ${x.nota}` : ""))))),
    act].filter(Boolean));
}
const TIPOS_TXT = { mal_lida: "mal lida / mal recortada", mal_colocada: "mal colocada", nao_encaixa: "não encaixa", outro: "outro" };
function askEstado(r, acao) {
  const dlg = $("#estado-dlg"), form = $("#estado-form"), nota = $("#estado-nota");
  form.reset();
  const del = acao === "delete";
  $("#estado-title").textContent = del ? `Eliminar ${r.id}` : `Marcar ${r.id} como resolvido`;
  $("#estado-msg").textContent = del ? `Eliminar ${r.id}? Fica escondido e pode ser restaurado.` : "A nota é opcional.";
  nota.hidden = del;
  form.onsubmit = async (ev) => {
    ev.preventDefault();
    const ok = $("#estado-ok"); ok.disabled = true;
    try { dlg.close(); await setEstado(r, acao, del ? "" : nota.value); } finally { ok.disabled = false; }
  };
  dlg.showModal();
}
async function setEstado(r, acao, nota = "") {
  try {
    const n = await api(`/api/report/${r.id}/estado`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ acao, nota }) });
    toast({ close: `${r.id} marcado como resolvido`, reopen: `${r.id} reaberto`, delete: `${r.id} eliminado (pode ser restaurado)`, restore: `${r.id} restaurado` }[acao] || `${r.id}: ${n.estado}`);
    await loadReports();
  } catch (e) { toast(e.message, true); }
}

// ------------------------------------------------------------ reportar
// the open report of this piece / cell (the latest one), if any: the button then edits it instead of adding a duplicate
function openReportsFor(ctx) {
  const same = (x, y) => x && y && x[0] === y[0] && x[1] === y[1];
  return (S.reports || []).filter((r) => r.estado === "aberto"
    && ((ctx.piece && r.piece === ctx.piece) || ((!ctx.piece || !r.piece) && same(r.cell, ctx.cell)))).sort((p, q) => (p.id < q.id ? 1 : -1));
}
function reportButton(ctx) {
  const ex = openReportsFor(ctx);
  if (ex.length) {
    return h("button", { class: "btn slim report edit", type: "button", title: `já há um report aberto (${ex[0].id}): edita-o em vez de criar outro`, "aria-label": "Editar report",
      "data-report": ex[0].id, onclick: () => openReport(ctx, ex[0], ex.length) }, "✎ Editar report");
  }
  return h("button", { class: "btn slim report", type: "button", title: "avisar de um problema: fica guardado com uma captura do que vês", "aria-label": "Reportar um problema", onclick: () => openReport(ctx) }, "⚠ Reportar");
}
function openReport(ctx, existing = null, nOpen = 0) {
  const dlg = $("#report-dlg");
  const where = [ctx.piece ? `peça ${ctx.piece}` : null, ctx.cell ? `célula ${cellTxt(ctx.cell)}` : null].filter(Boolean).join(" · ");
  const form = $("#report-form");
  form.reset();
  $("#report-title").textContent = existing ? `Editar ${existing.id}` : "Reportar um problema";
  $("#report-where").textContent = (where || "geral") + (existing && nOpen > 1 ? ` · há ${nOpen} reports abertos para isto; edita o ${existing.id}` : "");
  const radio = form.querySelector(`input[value=${existing ? existing.tipo : "mal_lida"}]`) || form.querySelector("input[value=mal_lida]");
  radio.checked = true;
  if (existing) $("#report-text").value = existing.texto || "";
  $("#report-send").textContent = existing ? "Guardar edição" : "Enviar";
  form.onsubmit = async (ev) => {
    ev.preventDefault();
    const btn = $("#report-send"); btn.disabled = true;
    const tipo = (form.querySelector("input[name=tipo]:checked") || {}).value || "outro";
    try {
      if (existing) {
        const r = await api(`/api/report/${existing.id}/edit`, { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tipo, texto: $("#report-text").value }) });
        toast(`Report ${r.id} editado`);
      } else {
        const r = await api("/api/report", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tipo, texto: $("#report-text").value, piece: ctx.piece || null, cell: ctx.cell || null, vista: ctx.vista || null }) });
        toast(`Reportado ${r.id}`);
      }
      dlg.close();
      await loadReports().catch(() => {});
    } catch (e) { toast(e.message, true); } finally { btn.disabled = false; }
  };
  dlg.showModal();
}

// ------------------------------------------------------------ célula drawer
/** Centre and highlight a cell on the board WITHOUT leaving the current tab (list stays visible). */
function showCellOnBoard(l, c) {
  $("#app").classList.remove("sheet-up");   // phone: collapse the sheet so the board is visible
  S.sel = [l, c];
  zoomCells(Math.max(1, l - 3), Math.max(1, c - 5), Math.min(S.rows, l + 3), Math.min(S.cols, c + 5));
  drawSel();
}
async function openCell(l, c, opts = {}) {
  S.sel = [l, c]; drawSel();
  if (opts.zoom) zoomCells(Math.max(1, l - 3), Math.max(1, c - 5), Math.min(S.rows, l + 3), Math.min(S.cols, c + 5));
  showTab("celula");
  S.sel = [l, c]; drawSel();
  const T = $("#tab-celula");
  if (!opts.keep) T.replaceChildren(h("p", { class: "muted" }, `a carregar a célula ${cellTxt([l, c])}…`));
  let d;
  try { d = await api(`/api/cell/${l}/${c}`); } catch (e) { toast(e.message, true); return; }
  if (!S.sel || S.sel[0] !== l || S.sel[1] !== c) return;
  T.replaceChildren(renderCell(d));
}
function zoomFigure(d) {
  const [l0, c0, l1, c1] = d.zoom.region;
  const vb = `${c0 - 1} ${(l0 - 1) * S.hr} ${c1 - c0 + 1} ${(l1 - l0 + 1) * S.hr}`;
  const mk = (src, withOverlay) => {
    const z = s("svg", { viewBox: vb, role: "img" });
    z.append(s("image", { href: `${src}&v=${S.ver}`, x: c0 - 1, y: (l0 - 1) * S.hr, width: c1 - c0 + 1, height: (l1 - l0 + 1) * S.hr, preserveAspectRatio: "none" }));
    if (withOverlay) {
      if (d.fantasma && S.showGhost) z.append(s("path", { d: ghostPath(d.fantasma.path, d.cell[1] - 0.5, (d.cell[0] - 0.5) * S.hr), class: cls("fantasma") }));
      for (const p of d.propostas) z.append(rectEl(d.cell[0], d.cell[1], fetchClass(p), 0.1));
      if (d.estado === "ocupada_legado") z.append(rectEl(d.cell[0], d.cell[1], cls("legado"), 0));
      if (d.conhecidas.length) z.append(rectEl(d.cell[0], d.cell[1], cls("conhecida"), 0.07));
      if (d.borda && d.estado === "vazia") z.append(rectEl(d.cell[0], d.cell[1], cls("borda"), 0.05));
    }
    z.append(rectEl(d.cell[0], d.cell[1], cls("selecao"), 0));
    return z;
  };
  return h("div", { class: "zoomrow" },
    h("figure", {}, mk(d.zoom.render, true), h("figcaption", {}, "o teu tabuleiro (300 dpi)")),
    h("figure", {}, mk(d.zoom.arte, false), h("figcaption", {}, "a arte da caixa")));
}
function pieceLine(p, withState = true) {
  if (!p) return "—";
  return `${p.lote !== null && p.lote !== undefined ? `saco ${p.lote} nº ${p.n_no_lote} · ` : ""}${p.id}` + (withState ? ` · ${p.estado_txt}` : "");
}
function renderCell(d) {
  const wrap = h("div");
  wrap.append(h("div", { class: "cell-head" },
    h("button", { class: "btn slim", type: "button", onclick: () => showTab(S.prevTab || "buscar") }, "← voltar"),
    h("h3", {}, `Célula ${cellTxt(d.cell)}`),
    h("button", { class: "btn slim", type: "button", onclick: () => zoomCells(Math.max(1, d.cell[0] - 3), Math.max(1, d.cell[1] - 5), Math.min(S.rows, d.cell[0] + 3), Math.min(S.cols, d.cell[1] + 5)), title: "levar a vista até esta peça / célula", "aria-label": "Localizar peça" }, locateIcon(), "Localizar peça")));
  wrap.append(zoomFigure(d));
  const kv = h("dl", { class: "kv" },
    h("dt", {}, "estado"), h("dd", {}, d.estado_txt + (d.borda ? " · borda" : "") + (d.fonte ? ` · fonte ${d.fonte}` : "")),
    h("dt", {}, "gémea"), h("dd", {}, d.gemea.cell ? [h("button", { class: "linkish", type: "button", onclick: () => openCell(d.gemea.cell[0], d.gemea.cell[1], { zoom: true }) }, cellTxt(d.gemea.cell)),
      ` · ${d.gemea.peca ? "colocada (" + pieceLine(d.gemea.peca, false) + ")" : (d.gemea.estado === "vazia" ? "vazia" : "ocupada, sem silhueta")}`] : "sem gémea"));
  if (d.peca) {
    kv.append(h("dt", {}, "peça"), h("dd", {}, pieceLine(d.peca)));
    if (d.origem) kv.append(h("dt", {}, "como chegou"), h("dd", {}, d.origem));
  }
  if (d.fantasma) kv.append(h("dt", {}, "fantasma"), h("dd", {}, `contorno de ${d.fantasma.piece} (em ${cellTxt(d.fantasma.from)}) rodado ${S.rotGemea}°: procura uma peça com esta forma`));
  wrap.append(kv);
  const hintBtns = [];
  if (!d.peca && (d.estado === "vazia" || d.por_confirmar)) {
    hintBtns.push(h("button", { class: "btn slim", type: "button", title: "marcar a célula como montada (sem peça no índice)",
      onclick: (ev) => act({ acao: "cell_full", cell: d.cell }, ev.currentTarget) }, "Está montada"));
  }
  if (!d.peca && d.estado === "ocupada_legado") {
    hintBtns.push(h("button", { class: "btn slim", type: "button", title: "marcar a célula como vazia",
      onclick: (ev) => act({ acao: "cell_empty", cell: d.cell }, ev.currentTarget) }, "Está vazia"));
  }
  wrap.append(h("div", { class: "actions" }, ...hintBtns, reportButton({ piece: d.peca ? d.peca.id : null, cell: d.cell, vista: "celula" }),
    d.peca ? contourButton(d.peca.id, { kind: "cell", cell: d.cell }) : null));
  if (d.peca) {
    const p = d.peca;
    wrap.append(h("div", { class: "card" }, h("div", { class: "card-top" },
      h("div", {}, pieceImage({ piece: p.id, pose_known: true, ghost: null }), h("div", { class: "pimg-cap" }, "como está no tabuleiro")),
      h("div", {}, h("div", { class: "who" }, p.lote !== null && p.lote !== undefined ? ["Saco ", h("span", { class: "n" }, p.lote), " · nº ", h("span", { class: "n" }, p.n_no_lote)] : p.id),
        h("div", { class: "small muted" }, `${p.id} · classe ${p.cls || "?"} · ${p.n_flat} lado(s) liso(s)`), manualBadge(p),
        p.scan_id ? h("button", { class: "linkish", type: "button", onclick: () => lightbox(`/api/sheets/${p.scan_id}.jpg?highlight=${p.id}&max=1400&v=${S.ver}`, `Folha ${p.scan_id}`) }, "ver na folha do scan") : null)),
      h("div", { class: "actions" },
        d.pode_desfazer ? h("button", { class: "btn danger", type: "button", onclick: (ev) => { if (confirm(`Retirar ${p.id} de ${cellTxt(d.cell)}?`)) act({ acao: "unplace", piece: p.id }, ev.currentTarget); } }, "Desfazer colocação") : null,
        p.seccao_id ? h("button", { class: "btn danger", type: "button", onclick: (ev) => { if (confirm(`Desfazer o «${LBL_AQUI}» do grupo ${p.seccao_id}? Todas as suas peças saem do tabuleiro.`)) act({ acao: "unanchor", section: p.seccao_id }, ev.currentTarget); } }, `Desfazer «${LBL_AQUI}» do grupo ${p.seccao_id}`) : null)));
  }
  if (d.propostas.length) {
    wrap.append(h("h2", {}, d.propostas.length > 1 ? "Propostas para esta célula" : "Proposta para esta célula"));
    wrap.append(h("p", { class: "summary small" }, CARD_KEY));
    for (const e of d.propostas) wrap.append(proposalCard(e, { noLocate: true }));
  }
  if (d.conhecidas.length) {
    wrap.append(h("h2", {}, "Posição conhecida"));
    for (const p of d.conhecidas) wrap.append(h("p", {}, `${pieceLine(p)}: guardada à parte, à espera de uma vizinha montada.`));
  }
  if (!d.peca && !d.propostas.length && !d.conhecidas.length && !d.fantasma && d.estado === "vazia") {
    wrap.append(h("p", { class: "note" }, "Ainda nenhuma pista para esta célula: a gémea não está colocada e nenhuma peça solta foi proposta."));
  }
  wrap.append(h("h2", {}, "Vizinhas"));
  wrap.append(h("div", { class: "neigh" }, d.vizinhas.map((n) => h("div", {}, h("b", {}, n.dir), h("br"),
    h("button", { class: "linkish", type: "button", onclick: () => openCell(n.cell[0], n.cell[1]) }, cellTxt(n.cell)), h("br"),
    n.estado === "vazia" ? "vazia" : (n.estado === "colocada" ? "colocada" : "ocupada")))));
  return wrap;
}
async function openPiece(pid) {
  let d;
  try { d = await api(`/api/pieces/${pid}`); } catch (e) { toast(e.message, true); return; }
  if (d.celula && (d.estado === "colocada" || d.estado === "posicao_conhecida")) { openCell(d.celula[0], d.celula[1], { zoom: true }); return; }
  S.sel = null; drawSel();
  showTab("celula");
  const T = $("#tab-celula");
  T.replaceChildren(h("div", { class: "cell-head" }, h("button", { class: "btn slim", type: "button", onclick: () => showTab(S.prevTab || "lotes") }, "← voltar"),
    h("h3", {}, d.lote !== null && d.lote !== undefined ? `Saco ${d.lote} · nº ${d.n_no_lote}` : d.id)));
  T.append(h("div", { class: "card" }, h("div", { class: "card-top" },
    h("div", {}, pieceImage({ piece: d.id, pose_known: d.pose_tabuleiro !== null, ghost: null }), h("div", { class: "pimg-cap" }, d.pose_tabuleiro !== null ? "rodada como ficará" : "como foi digitalizada")),
    h("div", {}, h("div", { class: "small muted" }, `${d.id} · ${d.estado_txt}`), h("div", { class: "small muted" }, `classe ${d.cls || "?"} · ${d.n_flat} lado(s) liso(s)` + (d.seccao_id ? ` · grupo ${d.seccao_id}` : "")), manualBadge(d),
      h("button", { class: "linkish", type: "button", onclick: () => lightbox(`${d.folha}&max=1400&v=${S.ver}`, `Folha ${d.scan_id}`) }, "ver na folha do scan")))));
  T.append(h("div", { class: "actions" }, reportButton({ piece: d.id, cell: null, vista: "peca" }), contourButton(d.id, { kind: "piece", pid: d.id })));
  if (d.propostas.length) for (const e of d.propostas) T.append(proposalCard(e));
  else T.append(h("p", { class: "note" }, "Sem proposta para esta peça por agora: fica na memória e volta a ser testada sempre que algo é colocado."));
  if (["solta", "emparelhada"].includes(d.estado)) {
    T.append(h("div", { class: "actions" }, h("button", { class: "btn danger", type: "button", onclick: (ev) => { if (confirm(`Descartar ${d.id} (não é uma peça / duplicada)?`)) act({ acao: "discard", piece: d.id, reason: "gui" }, ev.currentTarget); } }, "Descartar (não é peça / repetida)")));
  }
}

// ------------------------------------------------------------ editor de contorno (docs/gui-design.md §18)
// The editor itself (strokes, live solve, full-window overlay) lives in editor.js; only the entry button and
// the «contorno manual» badge are here.
function contourButton(pid, back) {
  return h("button", { class: "btn slim", type: "button", "data-contorno": pid, "aria-label": "Editar contorno",
    title: "desenhar / ajustar o contorno da peça por cima do scan (fica fora das métricas de CV)",
    onclick: () => openContourEditor(pid, back) }, "✎ Editar contorno");
}
function manualBadge(p) {
  if (!p || !p.contorno_manual) return null;
  return h("div", { class: "manual-badge small", title: "contorno desenhado à mão: a peça fica fora das métricas de segmentação" },
    h("span", { class: "chip manual" }, "contorno manual"), p.contorno_nota ? h("span", { class: "muted" }, ` ${p.contorno_nota}`) : null);
}

// ------------------------------------------------------------ pesquisa (barra de topo; só cliente, só leitura)
/** «P0778» / «p778» / «778» → piece; «R0019» / «r19» → report; «S0020» / «s20» → sheet; «4,10» / «4 10» / «(4,10)» / «l4 c10» → cell. */
function parseQuery(q) {
  const t = (q || "").trim().toLowerCase();
  let m;
  if ((m = t.match(/^p?0*(\d{1,4})$/)) && Number(m[1]) > 0) return { kind: "piece", id: "P" + m[1].padStart(4, "0") };
  if ((m = t.match(/^r0*(\d{1,4})$/)) && Number(m[1]) > 0) return { kind: "report", id: "R" + m[1].padStart(4, "0") };
  if ((m = t.match(/^s0*(\d{1,4})$/)) && Number(m[1]) > 0) return { kind: "sheet", id: "S" + m[1].padStart(4, "0") };
  if ((m = t.match(/^\(?\s*l?\s*(\d{1,2})\s*[,; ]\s*c?\s*(\d{1,2})\s*\)?$/))) {
    const l = Number(m[1]), c = Number(m[2]);
    if (l >= 1 && l <= S.rows && c >= 1 && c <= S.cols) return { kind: "cell", cell: [l, c] };
    return { kind: "outside", cell: [l, c] };
  }
  return { kind: "none" };
}
/** Show the proposal card of a piece in "Guardadas" or "Vai buscar" (selected + scrolled into view); false if it has no card there. */
function highlightCard(tab, pid) {
  showTab(tab);                 // before highlighting: showTab clears the selection
  const T = $(`#tab-${tab}`);
  const det = T.querySelector("details.guardadas");
  if (det) det.open = true;
  $$(".card.sel").forEach((x) => x.classList.remove("sel"));
  const card = $$(".card[data-piece]", T).find((x) => x.dataset.piece === pid);
  if (!card) return false;
  card.classList.add("sel");
  card.scrollIntoView({ block: "center" });
  return true;
}
async function locatePiece(pid) {
  let d;
  try { d = await api(`/api/pieces/${pid}`); } catch (e) {
    toast(e.status === 404 ? `${pid}: não encontrado (não existe)` : e.message, true);
    return;
  }
  if (d.celula && (d.estado === "colocada" || d.estado === "posicao_conhecida")) { await openCell(d.celula[0], d.celula[1], { zoom: true }); return; }
  const e = pendingPieces().find((x) => x.piece === pid);
  if (e && highlightCard(isStored(e) ? "guardadas" : "buscar", pid)) {
    toast(`${pid}: ${isStored(e) ? "em «Guardadas»" : "em «Vai buscar»"} → célula ${cellTxt(e.cell)}`);
    return;
  }
  const where = d.lote !== null && d.lote !== undefined ? ` (saco ${d.lote}, nº ${d.n_no_lote})` : "";
  toast(`${pid} existe: ${ST_TXT[d.estado] || d.estado}${where}, sem proposta`);
  await openPiece(pid);
}
async function locateCell(l, c) {
  const cell = S.board && S.board.cells[l - 1] && S.board.cells[l - 1][c - 1];
  await openCell(l, c, { zoom: true });
  if (!cell || !cell.peca_id) toast(cell && cell.estado && cell.estado !== "vazia" ? `célula (${l},${c}) sem peça: ${cell.estado}` : `célula (${l},${c}) vazia`);
}
async function locateSheet(sid) {
  if (!S.lots) await loadLots();
  const idx = S.lots.findIndex((lot) => lot.folhas.some((f) => f.scan_id === sid));
  if (idx < 0) { toast(`${sid}: não encontrado (não existe)`, true); return; }
  const lot = S.lots[idx], f = lot.folhas.find((x) => x.scan_id === sid);
  showTab("lotes");
  const T = $("#tab-lotes");
  const det = $$("details.lot", T)[idx];
  if (det) det.open = true;
  const pcs = lot.pecas.filter((p) => p.scan_id === sid);
  $$(".lot-hit", T).forEach((x) => x.remove());
  const hit = h("div", { class: "card lot-hit", "data-scan": sid },
    h("div", { class: "small" }, h("b", {}, sid), ` · ${lot.lote === null ? "sem saco" : "saco " + lot.lote} · ${f.n} peça${f.n === 1 ? "" : "s"}`),
    h("img", { class: "sheet-thumb", src: `${f.url}?max=480&v=${S.ver}`, alt: sid, onclick: () => lightbox(`${f.url}?max=1400&v=${S.ver}`, `${sid} · ${f.ficheiro} · ${f.n} peças`) }),
    h("div", { class: "pgrid" }, pcs.map((p) => h("div", { class: `ptile st-${p.estado}`, title: `${p.id} · ${ST_TXT[p.estado] || p.estado}`, onclick: () => openPiece(p.id) },
      h("img", { loading: "lazy", src: `/api/pieces/${p.id}.png?pose=scan&size=128`, alt: "" }),
      h("div", { class: "pn" }, p.n_no_lote !== null ? `nº ${p.n_no_lote}` : p.id),
      h("div", { class: "pc" }, p.celula ? cellTxt(p.celula) : (ST_TXT[p.estado] || p.estado))))));
  T.prepend(hit);
  hit.scrollIntoView({ block: "start" });
}
async function locateReport(r) {
  if (r.piece) return locatePiece(r.piece);
  if (r.cell) return locateCell(r.cell[0], r.cell[1]);
  toast(`${r.id}: report geral, sem peça nem célula para localizar`);
}
async function locateQuery(q) {
  const t = (q || "").trim();
  if (!t) { toast("Escreve uma peça (P0778), célula (4,10), report (R0019) ou folha (S0020)"); return; }
  const p = parseQuery(t);
  if (p.kind === "piece") return locatePiece(p.id);
  if (p.kind === "cell") return locateCell(p.cell[0], p.cell[1]);
  if (p.kind === "outside") { toast(`(${p.cell[0]},${p.cell[1]}): não encontrado (fora da grelha ${S.rows}×${S.cols})`, true); return; }
  if (p.kind === "sheet") return locateSheet(p.id);
  if (p.kind === "report") {
    if (!S.reports) await loadReports();
    const r = (S.reports || []).find((x) => x.id === p.id);
    if (!r) { toast(`${p.id}: não encontrado (não existe)`, true); return; }
    return locateReport(r);
  }
  toast(`«${t}»: não encontrado (usa P0778, 4,10, R0019 ou S0020)`, true);
}
function initSearch() {
  const f = $("#search"), q = $("#q"), btn = $("#search-btn");
  const setOpen = (on) => { f.classList.toggle("open", on); btn.setAttribute("aria-expanded", on ? "true" : "false"); if (on) q.focus(); };
  btn.onclick = () => setOpen(!f.classList.contains("open"));
  f.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const v = q.value;
    if (f.classList.contains("open")) setOpen(false);   // phone: the box folds back after searching
    locateQuery(v).catch((e) => toast(e.message, true));
  });
  q.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") { ev.stopPropagation(); q.blur(); if (f.classList.contains("open")) setOpen(false); }
  });
}

// ------------------------------------------------------------ lotes
const ST_TXT = { solta: "solta", emparelhada: "em par", posicao_conhecida: "posição conhecida", colocada: "colocada", em_seccao: "em grupo", descartada: "descartada" };
function renderLotes() {
  const T = $("#tab-lotes"); T.replaceChildren();
  if (!S.lots) { T.append(h("p", { class: "muted" }, "a carregar…")); return; }
  T.append(h("p", { class: "summary" }, "Cada saco tem as suas folhas (scans) e as peças numeradas como na folha impressa."));
  T.append(h("div", { class: "st-key" }, Object.entries(ST_TXT).map(([k, v]) => h("span", { class: `st-${k}` }, v))));
  S.lots.forEach((lot, i) => {
    const counts = h("span", { class: "counts" }, Object.entries(lot.por_estado).map(([k, v]) => h("span", { class: `st-${k}` }, `${v} ${ST_TXT[k] || k}`)));
    const det = h("details", { class: "lot", open: i === 0 && lot.lote !== null ? true : null });
    const name = lot.lote === null ? "Sem saco (legado e GT)" : `Saco ${lot.lote}`;
    det.append(h("summary", {}, h("h3", {}, name), h("span", { class: "muted small" }, `${lot.n} peças · ${lot.folhas.length} folha${lot.folhas.length > 1 ? "s" : ""}`), counts));
    const body = h("div", { class: "lot-body" });
    det.append(body);
    const fill = () => {
      if (body.childElementCount) return;
      body.append(h("div", { class: "sheets" }, lot.folhas.map((f) => h("figure", {},
        h("img", { loading: "lazy", src: `${f.url}?max=480&v=${S.ver}`, alt: f.scan_id, onclick: () => lightbox(`${f.url}?max=1400&v=${S.ver}`, `${f.scan_id} · ${f.ficheiro} · ${f.n} peças`) }),
        h("figcaption", {}, `${f.scan_id} · ${f.n} peças`)))));
      body.append(h("div", { class: "pgrid" }, lot.pecas.map((p) => h("div", { class: `ptile st-${p.estado}`, title: `${p.id} · ${ST_TXT[p.estado] || p.estado}`, onclick: () => openPiece(p.id) },
        h("img", { loading: "lazy", src: `/api/pieces/${p.id}.png?pose=scan&size=128`, alt: "" }),
        h("div", { class: "pn" }, p.n_no_lote !== null ? `nº ${p.n_no_lote}` : p.id),
        h("div", { class: "pc" }, p.celula ? cellTxt(p.celula) : (ST_TXT[p.estado] || p.estado))))));
    };
    det.addEventListener("toggle", () => { if (det.open) fill(); });
    if (det.open) fill();
    T.append(det);
  });
}

// ------------------------------------------------------------ mesa de apoio
// Alternativa B do docs/gui-design.md §14: uma linha por grupo (selo único + «Ver»); a ação principal só aparece depois de ver a zona.
const LBL_AQUI = "É aqui";    // the one place with the label of the action "this group goes here" (code ids/events keep "anchor")
const MESA_PLACEHOLDER = "Grupo, peça ou célula: G0021, P0294, 3,32";
const marginMin = () => {
  const m = S.board && S.board.calibracao && S.board.calibracao.margin_min;
  return typeof m === "number" ? m : 1.5;
};
const groupBest = (g) => g.candidatos[0] || null;
const isSafe = (g) => { const c = groupBest(g); return !!c && typeof c.margin === "number" && c.margin >= marginMin(); };
const sealEl = (g) => h("span", { class: "chip " + (isSafe(g) ? "ok" : "mid") }, isSafe(g) ? "segura" : "a confirmar");
const mesaSorted = () => (S.sections || []).slice().sort((a, b) => ((b.candidatos[0] || {}).margin || 0) - ((a.candidatos[0] || {}).margin || 0));

// search of the Mesa tab: group id (G0012), piece id (P0194) or cell ("3,32" / "(3, 32)": a candidate zone or footprint cell)
function mesaMatches(g, q) {
  q = (q || "").trim().toLowerCase();
  if (!q) return true;
  const m = q.match(/^\(?\s*(\d{1,2})\s*[,; ]\s*(\d{1,2})\s*\)?$/);
  if (m) {
    const l = Number(m[1]), c = Number(m[2]);
    return g.candidatos.some((cd) => (cd.cell0[0] === l && cd.cell0[1] === c) || cd.footprint.some((x) => x[0] === l && x[1] === c));
  }
  if (g.id.toLowerCase().includes(q)) return true;
  return (g.pecas || []).some((p) => p.id.toLowerCase().includes(q));
}
const mesaShown = (g) => mesaMatches(g, S.mesaQuery) && (!S.mesaFilter || (S.mesaFilter === "segura") === isSafe(g));

function previewZone(g, c) {
  S.mesa = { id: g.id, rank: c.rank, footprint: c.footprint }; drawMesa();
  const ls = c.footprint.map((x) => x[0]), cs = c.footprint.map((x) => x[1]);
  zoomCells(Math.max(1, Math.min(...ls) - 3), Math.max(1, Math.min(...cs) - 5), Math.min(S.rows, Math.max(...ls) + 3), Math.min(S.cols, Math.max(...cs) + 5));
}
/** Open the row of group ``id`` in the Mesa tab and preview zone ``rank`` (used by «Ver» and by a tap on a suggestion). */
async function openMesaGroup(id, rank = 1) {
  if (!S.sections) { try { await loadSections(); } catch (e) { toast(e.message, true); return; } }
  const g = (S.sections || []).find((x) => x.id === id);
  if (!g) return;
  S.mesaOpen = { id, rank };
  if (!mesaShown(g)) { S.mesaQuery = ""; S.mesaFilter = null; }
  if (S.tab !== "mesa") showTab("mesa");
  renderMesa();
  const c = g.candidatos.find((x) => x.rank === rank) || groupBest(g);
  if (c) previewZone(g, c);
  const row = $(`#mesa-list .mrow[data-g="${id}"]`);
  if (row && row.scrollIntoView) row.scrollIntoView({ block: "nearest" });
}
function closeMesaGroup() { S.mesaOpen = null; S.mesa = null; drawMesa(); renderMesa(); }

function renderMesa() {
  const T = $("#tab-mesa");
  const secs = mesaSorted();
  $("#n-mesa").textContent = secs.length ? String(secs.length) : "";
  drawSuggestions();
  T.replaceChildren();
  if (S.mesaOpen && !secs.some((g) => g.id === S.mesaOpen.id)) { S.mesaOpen = null; S.mesa = null; drawMesa(); }
  if (!secs.length) { T.append(h("div", { class: "empty" }, h("strong", {}, "A mesa está vazia."), "Não há grupos soltos sem lugar.")); return; }
  const nSafe = secs.filter(isSafe).length;
  const box = h("input", { type: "search", id: "mesa-q", class: "search", placeholder: MESA_PLACEHOLDER,
    "aria-label": "Procurar grupos da mesa", autocomplete: "off", value: S.mesaQuery || "" });
  const fbtn = (key, label) => h("button", { type: "button", class: "btn slim fchip", "data-filter": key, "aria-pressed": S.mesaFilter === key ? "true" : "false",
    onclick: (ev) => {
      S.mesaFilter = S.mesaFilter === key ? null : key;
      $$(".fchip", T).forEach((b) => b.setAttribute("aria-pressed", S.mesaFilter === b.dataset.filter ? "true" : "false"));
      draw();
    } }, label);
  const filters = h("div", { class: "mesa-filters", role: "group", "aria-label": "Filtrar grupos" },
    fbtn("segura", `Seguras (${nSafe})`), fbtn("confirmar", `A confirmar (${secs.length - nSafe})`));
  const info = h("p", { class: "summary", id: "mesa-info" });
  const list = h("div", { id: "mesa-list" });
  T.append(box, filters, info, list);
  function draw() {
    const shown = secs.filter(mesaShown);
    info.textContent = ((S.mesaQuery || "").trim() || S.mesaFilter)
      ? `${shown.length} de ${secs.length} grupos`
      : `${secs.length} grupos sem lugar. «Ver» mostra no tabuleiro onde o grupo ficaria (violeta); só depois aparece «${LBL_AQUI}».`;
    list.replaceChildren();
    if (!shown.length) { list.append(h("div", { class: "empty" }, h("strong", {}, "Nenhum grupo corresponde."), "Tenta um id (G0012, P0194) ou uma célula (3,32).")); return; }
    for (const g of shown) list.append(mesaRow(g));
  }
  box.addEventListener("input", () => { S.mesaQuery = box.value; draw(); });
  draw();
}
function mesaRow(g) {
  const open = !!S.mesaOpen && S.mesaOpen.id === g.id;
  const c = groupBest(g);
  const row = h("div", { class: "mrow" + (open ? " on" : ""), "data-g": g.id });
  row.append(h("div", { class: "mhead" },
    h("img", { src: g.thumb, loading: "lazy", alt: `grupo ${g.id}` }),
    h("div", { class: "mtxt" },
      h("div", { class: "t" }, `${g.id} · ${g.n} peça${g.n > 1 ? "s" : ""}`),
      h("div", { class: "s" }, c ? ["melhor zona ", h("b", {}, cellTxt(c.cell0)), " ", sealEl(g)] : "sem zonas candidatas")),
    h("button", { class: "btn slim" + (open ? "" : " primary"), type: "button", "aria-expanded": open ? "true" : "false",
      onclick: () => (open ? closeMesaGroup() : openMesaGroup(g.id, 1)) }, open ? "Fechar" : "Ver")));
  if (!open) return row;
  const cur = g.candidatos.find((x) => x.rank === S.mesaOpen.rank) || c;
  const exp = h("div", { class: "mexp" });
  if (cur) {
    exp.append(h("div", { class: "small" }, h("b", {}, `Zona ${cur.rank}) ${cellTxt(cur.cell0)}`), ` rot ${cur.rot}°${cur.mirror ? " espelho" : ""} · margem ${fmt(cur.margin, 2)}`,
      cur.fora ? h("span", { class: "warn" }, "parte fica fora da grelha") : null,
      cur.ocupadas ? h("span", { class: "warn" }, `${cur.ocupadas} célula(s) já colocadas`) : null));
    if (!isSafe(g)) exp.append(h("div", { class: "warn small" }, `O programa não decidiu este grupo: margem ${fmt(cur.margin, 2)}, mínimo ${fmt(marginMin(), 2)}.`));
    exp.append(h("div", { class: "actions" },
      h("button", { class: "btn primary", type: "button", "data-act": "aqui", disabled: cur.fora ? true : null, onclick: (ev) => {
        const q = `${LBL_AQUI}: ${g.id} em ${cellTxt(cur.cell0)} rot ${cur.rot}°? As ${g.n} peças passam a colocadas.`;
        const pre = isSafe(g) ? "" : `O programa não decidiu este grupo (margem ${fmt(cur.margin, 2)}, mínimo ${fmt(marginMin(), 2)}).\n`;
        if (confirm(pre + q)) act({ acao: "anchor", section: g.id, cell: cur.cell0, rot: cur.rot, mirror: cur.mirror }, ev.currentTarget);
      } }, `${LBL_AQUI} em ${cellTxt(cur.cell0)}`)));
  }
  for (const o of g.candidatos.filter((x) => !cur || x.rank !== cur.rank)) {
    exp.append(h("div", { class: "mother" },
      h("span", {}, `ou ${cellTxt(o.cell0)} rot ${o.rot}°${o.mirror ? " espelho" : ""}`),
      h("button", { class: "btn slim", type: "button", onclick: () => openMesaGroup(g.id, o.rank) }, "Ver")));
  }
  if (g.notes) exp.append(h("details", { class: "tech" }, h("summary", {}, "ⓘ notas da ingestão"), h("div", {}, g.notes)));
  row.append(exp);
  return row;
}

// ------------------------------------------------------------ sugestões no tabuleiro (botão «Sugestões»)
function suggestionItems() {
  const out = [];
  for (const g of (S.sections || [])) {
    const c = groupBest(g);
    if (!c || !c.footprint) continue;
    const cells = c.footprint.filter(([l, cc]) => l >= 1 && l <= S.rows && cc >= 1 && cc <= S.cols);
    if (cells.length) out.push({ g, c, safe: isSafe(g), cells });
  }
  return out;
}
function drawSuggestions() {
  const gl = $("#lyr-sug"); if (!gl) return;
  gl.replaceChildren();
  hideSugPicker();
  if (!S.showSug || !S.sections || !S.board) return;
  const items = suggestionItems().sort((a, b) => Number(a.safe) - Number(b.safe));      // weak first, strong on top
  for (const it of items) for (const [l, c] of it.cells) gl.append(rectEl(l, c, cls(it.safe ? "sugestao" : "sugestao_fraca"), 0.05, { "data-g": it.g.id }));
}
const suggestionsAt = (l, c) => (S.showSug ? suggestionItems().filter((it) => it.cells.some(([a, b]) => a === l && b === c))
  .sort((a, b) => Number(b.safe) - Number(a.safe) || (b.c.margin || 0) - (a.c.margin || 0)) : []);
function hideSugPicker() { const p = $("#sug-pick"); if (p) p.remove(); }
function showSugPicker(items, l, c, cx, cy) {
  hideSugPicker();
  const wrap = $("#board-wrap");
  const pick = h("div", { id: "sug-pick", role: "menu", "aria-label": `Sugestões em ${cellTxt([l, c])}` },
    h("div", { class: "sug-title" }, `Sugestões em ${cellTxt([l, c])}`),
    items.map((it) => h("button", { type: "button", class: "sug-item", role: "menuitem", "data-g": it.g.id,
      onclick: () => { hideSugPicker(); openMesaGroup(it.g.id, 1); } },
    h("b", {}, it.g.id), ` · ${it.g.n} peça${it.g.n > 1 ? "s" : ""} · `, h("span", { class: it.safe ? "ok" : "mid" }, it.safe ? "segura" : "a confirmar"))),
    h("button", { type: "button", class: "sug-item alt", role: "menuitem", onclick: () => { hideSugPicker(); openCell(l, c, { zoom: false }); } }, `Abrir a célula ${cellTxt([l, c])}`));
  wrap.append(pick);
  const r = wrap.getBoundingClientRect();
  const w = pick.offsetWidth, hh = pick.offsetHeight;
  pick.style.left = Math.max(4, Math.min(cx - r.left, r.width - w - 4)) + "px";
  pick.style.top = Math.max(4, Math.min(cy - r.top, r.height - hh - 4)) + "px";
}

// ------------------------------------------------------------ importar
function renderImportar() {
  const T = $("#tab-importar");
  if (T.dataset.built) { renderJobLog(); return; }
  T.dataset.built = "1";
  const maxLote = Math.max(0, ...((S.lots || []).map((l) => l.lote || 0)), ...fetchPieces().map((e) => e.lote || 0));
  const form = h("form", { class: "form", id: "import-form" },
    h("label", {}, "Scan do saco (JPEG/PNG, 300 dpi, fundo verde)", h("input", { type: "file", name: "file", accept: "image/*", required: true })),
    h("label", {}, "Número do saco (lote)", h("input", { type: "number", name: "lote", min: 1, step: 1, value: maxLote + 1, required: true })),
    h("label", {}, "Resolução (dpi)", h("input", { type: "number", name: "dpi", min: 100, max: 1200, step: 1, value: 300 })),
    h("div", { class: "actions" }, h("button", { class: "btn primary", type: "submit", id: "import-btn" }, "Importar e procurar")));
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const fd = new FormData(form);
    S.jobLog = []; S.lastLote = Number(fd.get("lote"));
    $("#import-btn").disabled = true;
    try {
      const r = await api("/api/ingest", { method: "POST", body: fd });
      S.jobLog.push({ msg: `ficheiro gravado em ${r.ficheiro}` });
      renderJobLog();
    } catch (e) { toast(e.message, true); $("#import-btn").disabled = false; }
  });
  T.append(h("h2", {}, "Importar um scan"),
    h("p", { class: "summary" }, "Um scan = uma folha de um saco. Um saco pode ter várias folhas: usa o mesmo número; a numeração continua."),
    form,
    h("ol", { class: "joblog", id: "joblog" }),
    h("p", { class: "note" }, "O ficheiro fica em images/pieces/lotes/ dentro do repositório: junta-o ao git para o outro PC conseguir regenerar os recortes. " +
      "Depois de segmentar, a lista «vai buscar» é recalculada para todas as peças soltas (alguns minutos)."));
  renderJobLog();
}
function renderJobLog() {
  const ol = $("#joblog"); if (!ol) return;
  ol.replaceChildren(...S.jobLog.map((j) => h("li", { class: j.etapa === "erro" ? "err" : (j.fim ? "done" : "") }, j.msg)));
  const last = S.jobLog[S.jobLog.length - 1];
  if (last && last.fim) {
    $("#import-btn").disabled = false;
    if (last.etapa !== "erro") ol.append(h("li", { class: "done" }, h("button", { class: "linkish", type: "button", onclick: () => showTab("buscar") }, "abrir «Vai buscar»"), " · ",
      h("button", { class: "linkish", type: "button", onclick: () => { showTab("lotes"); loadLots(); } }, `ver o saco ${S.lastLote ?? ""}`)));
  }
}

// ------------------------------------------------------------ suspeitas de orientação (só leitura, topo de Reports)
// /api/suspeitas = src.consistency: peças colocadas com um lado T↔T / B↔B (impossível) ou com outra rotação
// claramente melhor contra as vizinhas montadas. Nada é corrigido aqui: a linha só localiza a peça no tabuleiro.
async function loadSuspeitas() {
  S.susp = await api("/api/suspeitas");
  renderSuspeitas();
}
function renderSuspeitas(T) {
  T = T || $("#tab-reports");
  const old = T.querySelector("details.suspeitas");
  if (!S.susp) { if (old) old.remove(); return; }
  const items = S.susp.items || [], sm = S.susp.summary || {};
  const d = h("details", { class: "suspeitas", id: "suspeitas" },
    h("summary", {}, `Suspeitas (${items.length})`),
    h("p", { class: "small muted" }, `Orientação (contra as vizinhas montadas) e recorte (contra a gémea): ${sm.n_verificadas ?? "—"} de ${sm.n_colocadas ?? "—"} peças verificadas`
      + (sm.n_sem_cantos ? ` · ${sm.n_sem_cantos} sem cantos (não verificadas)` : "") + ". Só leitura: nada é corrigido aqui."));
  d.open = old ? old.open : !!S.suspOpen;
  d.addEventListener("toggle", () => { S.suspOpen = d.open; });
  const q = h("input", { type: "search", class: "susp-filter", placeholder: "filtrar (peça, célula, texto)", "aria-label": "filtrar suspeitas", value: S.suspQuery || "" });
  const norm = (x) => String(x || "").toLowerCase().replace(/[()\s]/g, "");
  const apply = () => {
    S.suspQuery = q.value;
    const k = norm(q.value);
    for (const row of d.querySelectorAll(".suspeita-row")) row.hidden = !!k && !row.dataset.q.includes(k);
  };
  q.addEventListener("input", apply);
  d.append(q);
  if (!items.length) d.append(h("div", { class: "empty" }, h("strong", {}, "Sem suspeitas.")));
  const GRAU = { impossivel: "impossível", melhor_rotacao: "melhor rotação", recorte: "Recorte" };
  for (const it of items) {
    const [l, c] = it.cell;
    const go = () => showCellOnBoard(l, c);
    d.append(h("div", { class: "card suspeita-row", role: "button", tabindex: "0", title: "Ver no tabuleiro",
      "data-piece": it.piece, "data-grau": it.grau,
      "data-q": norm([it.piece, `${l},${c}`, it.grau, GRAU[it.grau], it.texto, ...(it.falhas || [])].join(" ")),
      onclick: go, onkeydown: (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); go(); } } },
      h("img", { class: "rthumb", loading: "lazy", src: `/api/pieces/${it.piece}.png?pose=board&size=64`, alt: "", width: 64, height: 64 }),
      h("div", { class: "rbody" },
        h("div", { class: "small rhead" }, h("span", { class: "chip" }, it.piece), h("span", { class: "chip" }, cellTxt(it.cell)),
          h("span", { class: "chip grau " + it.grau }, GRAU[it.grau] || it.grau)),
        h("div", {}, it.texto),
        it.falhas && it.falhas.length ? h("div", { class: "small muted" }, it.falhas.join(" · ")) : null)));
  }
  apply();
  if (old) old.replaceWith(d); else T.prepend(d);
}

// ------------------------------------------------------------ events (SSE) + start-up
let reloadTimer = null;
function scheduleReload(what) {
  scheduleReload.pending = scheduleReload.pending || new Set();
  scheduleReload.pending.add(what);
  clearTimeout(reloadTimer);
  reloadTimer = setTimeout(async () => {
    const p = scheduleReload.pending; scheduleReload.pending = new Set();
    try {
      if (p.has("board")) await loadBoard();
      if (p.has("fetch")) await loadFetch();
      if (S.lots && (p.has("board") || p.has("fetch"))) loadLots().catch(() => {});
      if (p.has("board") || p.has("fetch")) loadSections().catch(() => {});
    } catch (e) { /* the next event retries */ }
  }, 350);
}
function setJob(job) {
  const pill = $("#job-pill");
  pill.hidden = !job;
  pill.textContent = job ? `a trabalhar: ${job}` : "";
}
function connectEvents() {
  const es = new EventSource("/api/events");
  es.addEventListener("hello", (e) => { const st = JSON.parse(e.data); setJob(st.job); });
  es.addEventListener("board_changed", (e) => { const d = JSON.parse(e.data); if (d.versao !== S.ver) scheduleReload("board"); });
  es.addEventListener("fetch_changed", () => scheduleReload("fetch"));
  for (const ev of ["report_added", "report_edited", "report_changed"]) es.addEventListener(ev, () => loadReports().catch(() => {}));
  es.addEventListener("piece_changed", () => { if (S.lots) loadLots().catch(() => {}); });
  es.addEventListener("ingest_progress", (e) => {
    const d = JSON.parse(e.data);
    S.jobLog.push(d); renderJobLog();
    setJob(d.fim ? null : `importar (${d.etapa})`);
    if (d.fim) toast(d.msg, d.etapa === "erro");
  });
  es.addEventListener("prepare_progress", (e) => {
    const d = JSON.parse(e.data);
    $("#prep-log").append(h("li", {}, d.msg));
    $("#prep-log").scrollTop = 1e9;
  });
  es.addEventListener("ready", () => {
    if ($("#prep").hidden) return;
    $("#prep").hidden = true;
    loadAll().then(() => { document.body.dataset.ready = "1"; }).catch((e) => toast(e.message, true));
  });
  return es;
}

async function boot() {
  $$("#tabs button").forEach((b) => (b.onclick = () => showTab(b.dataset.tab)));
  initSearch();
  $("#lb-close").onclick = () => { $("#lightbox").hidden = true; };
  $("#lightbox").addEventListener("click", (e) => { if (e.target.id === "lightbox" || e.target.classList.contains("lb-body")) $("#lightbox").hidden = true; });
  $("#sheet-handle").onclick = () => $("#app").classList.toggle("sheet-up");
  const tg = $("#tg-ghost"), tgr = $("#tg-grid"), tgs = $("#tg-sug");
  tg.checked = S.showGhost; tgr.checked = S.showGrid; tgs.checked = S.showSug;
  tg.onchange = () => { S.showGhost = tg.checked; lsSet("tg-ghost", tg.checked ? "1" : "0"); setView(S.vb); renderBuscar(); };
  tgr.onchange = () => { S.showGrid = tgr.checked; lsSet("tg-grid", tgr.checked ? "1" : "0"); setView(S.vb); };
  tgs.onchange = () => { S.showSug = tgs.checked; lsSet("tg-sug", tgs.checked ? "1" : "0"); drawSuggestions(); };
  document.addEventListener("keydown", (e) => {
    if (S.ced) { cedKey(e); return; }
    if (e.key === "Escape" && $("#sug-pick")) { hideSugPicker(); return; }
    if (e.key === "Escape") { if (!$("#lightbox").hidden) $("#lightbox").hidden = true; else if (S.tab === "celula") showTab(S.prevTab); }
  });
  document.addEventListener("keyup", cedKey);
  window.addEventListener("resize", () => { if (S.ced) cedOnResize(); });
  const lg = $("#legend-box");
  const stored = lsGet("legend-open");
  lg.open = stored === null ? window.innerHeight >= 900 : stored === "1";
  lg.addEventListener("toggle", () => { lsSet("legend-open", lg.open ? "1" : "0"); setView(S.vb); });
  initPointer();
  connectEvents();
  const st = await api("/api/status");
  S.status = st; setJob(st.job);
  if (st.estado !== "pronto") {
    $("#prep").hidden = false;
    $("#prep-log").replaceChildren(...st.prep_log.map((m) => h("li", {}, m)));
    // fallback if the "ready" event is missed (reconnects): poll the status
    const poll = setInterval(async () => {
      try {
        const st2 = await api("/api/status");
        if (st2.estado === "pronto") {
          clearInterval(poll);
          if (!$("#prep").hidden) { $("#prep").hidden = true; await loadAll(); document.body.dataset.ready = "1"; }
        }
      } catch (e) { /* server restarting */ }
    }, 3000);
    return;
  }
  await loadAll();
  document.body.dataset.ready = "1";
}
boot().catch((e) => toast(e.message, true));
