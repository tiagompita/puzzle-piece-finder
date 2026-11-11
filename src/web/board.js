/* Tabuleiro comum às interfaces web: raster do servidor (/api/board.jpg: arte + recortes reais) + sobreposição SVG no
 * mesmo viewBox (unidades de célula: x = coluna, y = linha * hr). Aqui: classes da legenda do servidor, geometria,
 * vista (zoom / deslocar), raster de detalhe com zoom, ponteiro (roda, pinça, arrastar) e grelha. O toque numa célula
 * vai para o gancho ``S.onBoardTap(l, c, ev)``, que a casca define (app.js: sugestões / gaveta da célula).
 * Lê o estado ``S`` da casca (declarado em app.js, carregado depois: só é usado em tempo de execução).
 */
"use strict";

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
    if (S.pose && e.altKey) { e.preventDefault(); poseWheel(e); return; }   // Alt+wheel = rotate the piece (pose.js)
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
      if (!moved && start && e.type === "pointerup" && !S.pose) {
        const p = clientToBoard(e.clientX, e.clientY);
        const c = Math.floor(p.x) + 1, l = Math.floor(p.y / S.hr) + 1;
        if (typeof S.onBoardTap === "function") S.onBoardTap(l, c, e);   // the shell decides (app.js: suggestions / cell)
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

/** Board geometry from ``S.board`` (/api/board) + the cached full-board raster (#board-bg, #raster). */
function drawRaster() {
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
}
/** Cell grid (#lyr-grelha; shown by setView only when zoomed in enough). */
function drawGrid() {
  let d = "";
  for (let c = 0; c <= S.cols; c++) d += `M${c} 0V${boardH().toFixed(4)}`;
  for (let l = 0; l <= S.rows; l++) d += `M0 ${(l * S.hr).toFixed(4)}H${S.cols}`;
  $("#lyr-grelha").replaceChildren(s("path", { d, class: cls("grelha") }));
}
