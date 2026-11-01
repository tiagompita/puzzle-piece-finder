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

const S = {
  board: null, fetch: null, ghosts: [], lots: null, sections: null, status: null,
  rows: 47, cols: 64, hr: 1, ppc: 60, ver: 0,
  vb: { x: 0, y: 0, w: 64, h: 47 }, sel: null, tab: "buscar", prevTab: "buscar",
  showGhost: localStorage.getItem("tg-ghost") !== "0", showGrid: localStorage.getItem("tg-grid") !== "0",
  mesa: null, detailKey: null, jobLog: [], lastLote: null,
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
        if (l >= 1 && l <= S.rows && c >= 1 && c <= S.cols) openCell(l, c, { zoom: false });
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
  $("#progress-txt").textContent =
    `${p.colocadas} colocadas · ${p.sem_silhueta} ocupadas sem silhueta · ${p.total - p.ocupadas} por colocar (de ${p.total})`;
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
    if (!e.cell) continue;
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
  drawFetchLayer();
  renderBuscar();
}
const fetchPieces = () => (S.fetch ? S.fetch.entries.filter((e) => e.piece) : []);
async function loadLots() { S.lots = await api("/api/lots"); renderLotes(); }
async function loadSections() { S.sections = await api("/api/sections"); renderMesa(); }

async function loadAll() {
  await loadBoard();
  await loadFetch();
  loadSections().catch((e) => toast(e.message, true));
  if (S.tab === "lotes") loadLots().catch((e) => toast(e.message, true));
  renderImportar();
}

// ------------------------------------------------------------ tabs
function showTab(t) {
  if (t !== "celula") S.prevTab = t;
  S.tab = t;
  $$("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === t));
  $$(".tab").forEach((el) => el.classList.toggle("on", el.id === `tab-${t}`));
  if (t === "lotes" && !S.lots) loadLots().catch((e) => toast(e.message, true));
  if (t === "mesa" && !S.sections) loadSections().catch((e) => toast(e.message, true));
  if (t !== "celula" && S.sel) { S.sel = null; drawSel(); }
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
  confirmado: "confirmado", por_ancorar: "por ancorar" };
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
  if (e.cell) {
    acts.append(h("button", { class: "btn primary", type: "button", onclick: (ev) => act({ acao: "place", piece: e.piece, cell: e.cell, origin: e.origin }, ev.currentTarget) }, "Coloquei"));
    if (e.origin !== "posicao_conhecida") {
      acts.append(h("button", { class: "btn", type: "button", onclick: (ev) => act({ acao: "reject", piece: e.piece }, ev.currentTarget) }, "Não encaixa"));
      acts.append(h("button", { class: "btn", type: "button", title: "a peça fica guardada à parte, à espera de uma vizinha", onclick: (ev) => act({ acao: "position_known", piece: e.piece, cell: e.cell, origin: e.origin }, ev.currentTarget) }, "Guardar posição"));
    }
  }
  if (!opts.noLocate && e.cell) acts.append(h("button", { class: "btn slim", type: "button", onclick: () => { openCell(e.cell[0], e.cell[1], { zoom: true }); } }, "Ver no tabuleiro"));
  card.append(acts);
  card.append(h("details", { class: "tech" }, h("summary", {}, "razões técnicas"), h("ul", {}, (e.reasons || []).map((t) => h("li", {}, t)))));
  return card;
}
function renderBuscar() {
  const T = $("#tab-buscar"); T.replaceChildren();
  const es = fetchPieces().filter((e) => !e.estado_atual || ["solta", "emparelhada", "posicao_conhecida"].includes(e.estado_atual));
  $("#n-buscar").textContent = es.length ? String(es.length) : "";
  if (!es.length) {
    T.append(h("div", { class: "empty" }, h("strong", {}, "Nada a ir buscar agora."),
      "Importa o scan de um saco para o programa procurar gémeas e pares.",
      h("div", { class: "actions", style: "justify-content:center" }, h("button", { class: "btn primary", type: "button", onclick: () => showTab("importar") }, "Importar scan"))));
    return;
  }
  const by = new Map();
  for (const e of es) { const k = e.lote ?? "—"; if (!by.has(k)) by.set(k, []); by.get(k).push(e); }
  const nAc = es.filter((e) => e.decision === "aceite" || e.decision === "colocavel").length;
  T.append(h("p", { class: "summary" }, `${es.length} peças para ir buscar em ${by.size} saco${by.size > 1 ? "s" : ""}: ` +
    `${nAc} aceites, ${es.length - nAc} com dúvida. Pela ordem: as mais seguras primeiro.`),
    h("p", { class: "summary small" }, CARD_KEY));
  const keys = [...by.keys()].sort((a, b) => (a === "—") - (b === "—") || a - b);
  for (const k of keys) {
    T.append(h("div", { class: "lot-head" }, h("span", { class: "bag" }, k === "—" ? "Sem saco" : `Saco ${k}`), h("span", { class: "muted small" }, `${by.get(k).length} peças`)));
    for (const e of by.get(k).sort((a, b) => a.ordem - b.ordem)) T.append(proposalCard(e));
  }
  const sup = S.fetch.suprimidas || [];
  if (sup.length) {
    T.append(h("details", { class: "tech" }, h("summary", {}, `${sup.length} sugestões não mostradas (candidata única, por política)`),
      h("ul", {}, sup.map((x) => h("li", {}, `saco ${x.lote ?? "—"} nº ${x.n_no_lote ?? "—"} (${x.piece}) → ${cellTxt(x.cell)}: ${x.reason || ""}`)))));
  }
}

// ------------------------------------------------------------ célula drawer
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
    h("button", { class: "btn slim", type: "button", onclick: () => zoomCells(Math.max(1, d.cell[0] - 3), Math.max(1, d.cell[1] - 5), Math.min(S.rows, d.cell[0] + 3), Math.min(S.cols, d.cell[1] + 5)) }, "Centrar")));
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
  if (d.peca) {
    const p = d.peca;
    wrap.append(h("div", { class: "card" }, h("div", { class: "card-top" },
      h("div", {}, pieceImage({ piece: p.id, pose_known: true, ghost: null }), h("div", { class: "pimg-cap" }, "como está no tabuleiro")),
      h("div", {}, h("div", { class: "who" }, p.lote !== null && p.lote !== undefined ? ["Saco ", h("span", { class: "n" }, p.lote), " · nº ", h("span", { class: "n" }, p.n_no_lote)] : p.id),
        h("div", { class: "small muted" }, `${p.id} · classe ${p.cls || "?"} · ${p.n_flat} lado(s) liso(s)`),
        p.scan_id ? h("button", { class: "linkish", type: "button", onclick: () => lightbox(`/api/sheets/${p.scan_id}.jpg?highlight=${p.id}&max=1400&v=${S.ver}`, `Folha ${p.scan_id}`) }, "ver na folha do scan") : null)),
      h("div", { class: "actions" },
        d.pode_desfazer ? h("button", { class: "btn danger", type: "button", onclick: (ev) => { if (confirm(`Retirar ${p.id} de ${cellTxt(d.cell)}?`)) act({ acao: "unplace", piece: p.id }, ev.currentTarget); } }, "Desfazer colocação") : null,
        p.seccao_id ? h("button", { class: "btn danger", type: "button", onclick: (ev) => { if (confirm(`Desancorar o grupo ${p.seccao_id}? Todas as suas peças saem do tabuleiro.`)) act({ acao: "unanchor", section: p.seccao_id }, ev.currentTarget); } }, `Desancorar grupo ${p.seccao_id}`) : null)));
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
    h("div", {}, h("div", { class: "small muted" }, `${d.id} · ${d.estado_txt}`), h("div", { class: "small muted" }, `classe ${d.cls || "?"} · ${d.n_flat} lado(s) liso(s)` + (d.seccao_id ? ` · grupo ${d.seccao_id}` : "")),
      h("button", { class: "linkish", type: "button", onclick: () => lightbox(`${d.folha}&max=1400&v=${S.ver}`, `Folha ${d.scan_id}`) }, "ver na folha do scan")))));
  if (d.propostas.length) for (const e of d.propostas) T.append(proposalCard(e));
  else T.append(h("p", { class: "note" }, "Sem proposta para esta peça por agora: fica na memória e volta a ser testada sempre que algo é colocado."));
  if (["solta", "emparelhada"].includes(d.estado)) {
    T.append(h("div", { class: "actions" }, h("button", { class: "btn danger", type: "button", onclick: (ev) => { if (confirm(`Descartar ${d.id} (não é uma peça / duplicada)?`)) act({ acao: "discard", piece: d.id, reason: "gui" }, ev.currentTarget); } }, "Descartar (não é peça / repetida)")));
  }
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
function renderMesa() {
  const T = $("#tab-mesa"); T.replaceChildren();
  const secs = (S.sections || []).slice().sort((a, b) => ((b.candidatos[0] || {}).margin || 0) - ((a.candidatos[0] || {}).margin || 0));
  $("#n-mesa").textContent = secs.length ? String(secs.length) : "";
  if (!secs.length) { T.append(h("div", { class: "empty" }, h("strong", {}, "A mesa está vazia."), "Não há grupos soltos por ancorar.")); return; }
  T.append(h("p", { class: "summary" }, `${secs.length} grupos soltos (montados ou em blocos) ainda sem lugar. Para cada um, as 3 melhores zonas pela imagem; ` +
    "«Ver» mostra no tabuleiro onde ficaria (violeta); «Ancorar aqui» coloca o grupo todo."));
  for (const g of secs) {
    const card = h("div", { class: "card" });
    card.append(h("div", { class: "grp-top" }, h("img", { src: g.thumb, loading: "lazy", alt: `grupo ${g.id}` }),
      h("div", {}, h("h3", {}, `Grupo ${g.id}`), h("div", { class: "small muted" }, `${g.kind} · ${g.n} peça${g.n > 1 ? "s" : ""}` + (g.scan_id ? ` · folha ${g.scan_id}` : "")),
        g.notes ? h("details", { class: "tech" }, h("summary", {}, "notas da ingestão"), h("div", {}, g.notes)) : null)));
    const cl = h("div", { class: "cands" });
    if (!g.candidatos.length) cl.append(h("div", { class: "muted small" }, "sem zonas candidatas"));
    for (const c of g.candidatos) {
      const row = h("div", { class: "cand" },
        h("div", {}, h("b", {}, `${c.rank}) ${cellTxt(c.cell0)}`), ` rot ${c.rot}°${c.mirror ? " espelho" : ""} · margem ${fmt(c.margin, 2)}`,
          c.fora ? h("span", { class: "warn" }, "parte fica fora da grelha") : null,
          c.ocupadas ? h("span", { class: "warn" }, `${c.ocupadas} célula(s) já colocadas`) : null),
        h("button", { class: "btn slim", type: "button", onclick: () => {
          S.mesa = { id: g.id, rank: c.rank, footprint: c.footprint }; drawMesa();
          $$(".cand", T).forEach((x) => x.classList.remove("on")); row.classList.add("on");
          const ls = c.footprint.map((x) => x[0]), cs = c.footprint.map((x) => x[1]);
          zoomCells(Math.max(1, Math.min(...ls) - 3), Math.max(1, Math.min(...cs) - 5), Math.min(S.rows, Math.max(...ls) + 3), Math.min(S.cols, Math.max(...cs) + 5));
        } }, "Ver"),
        h("button", { class: "btn slim primary", type: "button", disabled: c.fora ? true : null, onclick: (ev) => {
          if (confirm(`Ancorar ${g.id} em ${cellTxt(c.cell0)} rot ${c.rot}°? As ${g.n} peças passam a colocadas.`)) act({ acao: "anchor", section: g.id, cell: c.cell0, rot: c.rot, mirror: c.mirror }, ev.currentTarget);
        } }, "Ancorar aqui"));
      cl.append(row);
    }
    card.append(cl);
    T.append(card);
  }
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
  $("#lb-close").onclick = () => { $("#lightbox").hidden = true; };
  $("#lightbox").addEventListener("click", (e) => { if (e.target.id === "lightbox" || e.target.classList.contains("lb-body")) $("#lightbox").hidden = true; });
  $("#sheet-handle").onclick = () => $("#app").classList.toggle("sheet-up");
  const tg = $("#tg-ghost"), tgr = $("#tg-grid");
  tg.checked = S.showGhost; tgr.checked = S.showGrid;
  tg.onchange = () => { S.showGhost = tg.checked; localStorage.setItem("tg-ghost", tg.checked ? "1" : "0"); setView(S.vb); renderBuscar(); };
  tgr.onchange = () => { S.showGrid = tgr.checked; localStorage.setItem("tg-grid", tgr.checked ? "1" : "0"); setView(S.vb); };
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { if (!$("#lightbox").hidden) $("#lightbox").hidden = true; else if (S.tab === "celula") showTab(S.prevTab); }
  });
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
