/* Editor de contorno por traços (docs/gui-design.md §18, contrato em docs/diagnostico/editor/TRACOS.md §7).
 *
 * Sobreposição de janela inteira (div#ced). O utilizador marca o scan com laço / pincel / borracha em três
 * marcas (peca / fundo / incerto); cada traço é desenhado já, em local, e o servidor resolve o contorno
 * (POST /api/pieces/{id}/contorno/resolver, debounce de 150 ms, 1 pedido em voo, respostas antigas
 * descartadas). As pegas de vértice ficam como retoque opcional do polígono resolvido. Tudo em px do recorte.
 * Carregado antes de app.js (usa S, h, $, api, toast, fmt, cellTxt, loadAll, loadLots, openCell, openPiece
 * de app.js só em tempo de execução).
 */
"use strict";

const CED_HIT = 6;          // vertex / edge hit radius, screen px (mouse); touch uses CED_HIT_TOUCH
const CED_HIT_TOUCH = 14;
const CED_DEBOUNCE_MS = 150;
const CED_RGB = { peca: "255,255,255", fundo: "0,0,0", incerto: "150,150,150" };
const CED_MARCAS = [["peca", "É peça", "1"], ["fundo", "Não é peça", "2"], ["incerto", "Incerto", "3"]];
const CED_FERRS = [["laco", "Laço", "L"], ["pincel", "Pincel", "P"], ["borracha", "Borracha", "B"]];
const CED_VISTAS = [["scan", "Scan"], ["atual", "Atual"], ["diff", "Diferença"], ["final", "Final"]];
const CED_AJUDA = "«Não é peça» com pincel fino sobre a linha negra da sombra colada à peça · «É peça» sobre arte clara cor do papel que o automático cortou · «Incerto» onde quiser que o algoritmo decida. Shift força «é peça», Alt força «não é peça».";

async function openContourEditor(pid, back) {
  let d;
  try { d = await api(`/api/pieces/${pid}/contorno`); } catch (e) { toast(e.message, true); return; }
  const img = new Image();
  img.src = d.crop_png_url;
  try { await img.decode(); } catch (e) { toast(`${pid}: recorte do scan indisponível`, true); return; }
  const tracos = (d.tracos || []).map((t) => ({ ferramenta: t.ferramenta, marca: t.marca === undefined ? null : t.marca, raio_px: t.raio_px, pontos: t.pontos }));
  const layer = document.createElement("canvas");
  layer.width = d.tamanho[0]; layer.height = d.tamanho[1];
  const E = { pid, d, back: back || { kind: "piece", pid }, img, layer, layerDirty: true,
    tracos, pos: tracos.length, tool: "pincel", marca: "fundo", raio: 8,
    view: { z: 1, cx: d.tamanho[0] / 2, cy: d.tamanho[1] / 2 }, ptrs: new Map(), drag: null, pinch: null, live: null, cur: null,
    space: false, dirty: false, seq: 0, timer: null, inflight: false, again: false, busy: false, res: null,
    vt: null, retouch: false, diff: null, maskA: null, modeUser: null, vista: "scan", raf: 0 };
  S.ced = E;
  cedBuild();
  const el = $("#ced");
  el.hidden = false;
  document.body.classList.add("ced-open");
  requestAnimationFrame(() => { cedLayout(); cedFit(); cedDraw(); cedSchedule(0); });
}

function cedLeave() {
  const E = S.ced;
  clearTimeout(E && E.timer);
  S.ced = null;
  const el = $("#ced");
  if (el) { el.hidden = true; el.replaceChildren(); }
  document.body.classList.remove("ced-open");
  const b = E ? E.back : null;
  if (b && b.kind === "cell") openCell(b.cell[0], b.cell[1], { zoom: false });
  else if (b && b.kind === "piece") openPiece(b.pid);
}

function cedClose() {
  const E = S.ced;
  if (E && E.dirty && !confirm("Descartar as alterações ao contorno?")) return;
  cedLeave();
}

// ------------------------------------------------------------ construção da janela
function cedBuild() {
  const E = S.ced, d = E.d, root = $("#ced");
  const who = d.lote !== null && d.lote !== undefined ? `Saco ${d.lote} · nº ${d.n_no_lote}` : d.piece;
  const b = (txt, fn, attrs = {}) => h("button", Object.assign({ class: "ced-b", type: "button", onclick: fn }, attrs), txt);
  const view = (kind, label, main) => h("div", { class: "ced-vw" + (main ? " main" : ""), "data-vista": kind },
    h("canvas", { id: main ? "ced-canvas" : `ced-v-${kind}`, tabindex: main ? "0" : null, "aria-label": main ? `contorno de ${d.piece} sobre o scan` : `${label} de ${d.piece}` }),
    h("span", { class: "ced-lab" }, label));
  const views = h("div", { id: "ced-views" },
    view("scan", "Scan + traços + contorno resolvido", true), view("atual", "Máscara atual", false),
    view("diff", "Diferença (ganho magenta, perda ciano)", false), view("final", "Recorte final", false));
  const tools = h("aside", { id: "ced-tools", "aria-label": "Ferramentas do editor de contorno" },
    h("div", { class: "ced-thead" }, h("h2", {}, `Contorno · ${who}`),
      b("▾", () => { $("#ced-tools").classList.toggle("min"); requestAnimationFrame(cedOnResize); }, { id: "ced-collapse", "aria-label": "Recolher a barra de ferramentas", title: "recolher / abrir a barra" }),
      b("Fechar", () => cedClose(), { id: "ced-close", title: "fechar (Esc)" })),
    h("div", { class: "ced-body" },
      h("p", { class: "small muted ced-who" }, `${d.piece} · ${d.scan_id}` + (d.celula ? ` · ${cellTxt(d.celula)}` : "") + ` · classe ${d.cls || "?"} · `,
        d.manual_override ? h("span", { class: "chip manual" }, "contorno manual") : "contorno da segmentação",
        d.override_pendente ? h("span", { class: "chip mid" }, "por aplicar") : null),
      h("div", { class: "ced-sec" }, h("span", { class: "ced-k" }, "Ferramenta"),
        h("div", { class: "ced-row" }, ...CED_FERRS.map(([k, t, key]) => b(`${t} (${key})`, () => cedSet({ tool: k }), { "data-ferr": k, title: `${t} (tecla ${key})` })))),
      h("div", { class: "ced-sec" }, h("span", { class: "ced-k" }, "Marca"),
        h("div", { class: "ced-row" }, ...CED_MARCAS.map(([k, t, key]) => b([h("i", { class: `ced-sw ${k}` }), `${t} (${key})`], () => cedSet({ marca: k }), { "data-marca": k, title: `${t} (tecla ${key})` })))),
      h("label", { class: "ced-sec ced-raio" }, h("span", { class: "ced-k" }, "Raio ", h("b", { id: "ced-raio-v" }, "8"), " px ([ e ])"),
        h("input", { id: "ced-raio", type: "range", min: "2", max: "60", step: "1", value: "8", oninput: (ev) => cedSet({ raio: Number(ev.target.value) }) })),
      h("p", { class: "small ced-active", id: "ced-active" }),
      h("div", { class: "ced-row" },
        b("Desfazer", () => cedUndo(), { id: "ced-undo", title: "desfazer (Ctrl+Z)" }),
        b("Refazer", () => cedRedo(), { id: "ced-redo", title: "refazer (Ctrl+Y ou Ctrl+Shift+Z)" }),
        b("Limpar traços", () => cedClear(), { id: "ced-clear" })),
      h("div", { class: "ced-row" },
        b("−", () => cedZoom(1 / 1.4), { "aria-label": "Afastar", title: "afastar (roda)" }),
        b("+", () => cedZoom(1.4), { "aria-label": "Aproximar", title: "aproximar (roda)" }),
        b("Ajustar", () => { cedFit(); cedDraw(); cedDrawViews(); }, { title: "ver o recorte inteiro" })),
      h("div", { class: "ced-sec" }, h("span", { class: "ced-k" }, "Vistas"),
        h("div", { class: "ced-row" }, ...CED_VISTAS.map(([k, t]) => b(t, () => cedSetVista(k), { "data-vista-btn": k })),
          b("Lado a lado", () => cedToggleMode(), { id: "ced-mode", title: "alternar entre as vistas lado a lado e uma de cada vez" }))),
      h("div", { class: "ced-row" }, b("Afinar vértices", () => cedToggleRetouch(), { id: "ced-vertices", "aria-pressed": "false", title: "retoque opcional: arrastar vértices do contorno resolvido (clique numa aresta: novo vértice · Delete: apaga)" })),
      h("p", { class: "small ced-status", id: "ced-status" }),
      h("p", { class: "small ced-busy", id: "ced-busy", "aria-live": "polite" }),
      h("p", { class: "small muted ced-help" }, CED_AJUDA),
      h("label", { class: "ced-nota" }, h("span", { class: "small muted" }, "Nota (opcional)"),
        h("input", { id: "ced-nota", type: "text", maxlength: "200", value: d.nota || "", placeholder: "ex.: comido no lado de baixo" })),
      h("div", { class: "ced-row ced-save-row" },
        h("button", { class: "ced-b primary", type: "button", id: "ced-save", onclick: (ev) => cedSave(ev.currentTarget) }, "Gravar"),
        b("Cancelar", () => cedClose(), { id: "ced-cancel" }))));
  root.replaceChildren(views, tools);
  cedBind($("#ced-canvas"));
  cedSyncUI();
}

function cedLayout() {
  const E = S.ced; if (!E) return;
  const mode = E.modeUser || (window.innerWidth >= 1200 ? "grid" : "one");
  E.mode = mode;
  const views = $("#ced-views");
  views.classList.toggle("grid", mode === "grid");
  views.classList.toggle("one", mode === "one");
  $$(".ced-vw", views).forEach((v) => v.classList.toggle("show", v.dataset.vista === E.vista));
  const btn = $("#ced-mode");
  if (btn) { btn.textContent = mode === "grid" ? "Uma vista" : "Lado a lado"; btn.setAttribute("aria-pressed", mode === "grid" ? "true" : "false"); }
  cedResize();
}
function cedToggleMode() {
  const E = S.ced; if (!E) return;
  E.modeUser = E.mode === "grid" ? "one" : "grid";
  cedLayout(); cedFit(); cedDraw(); cedDrawViews(); cedSyncUI();
}
function cedSetVista(k) {
  const E = S.ced; if (!E) return;
  E.vista = k;
  if (E.mode === "grid") { toast(k === "scan" ? "vista principal" : "em «lado a lado» todas as vistas estão visíveis; use «Uma vista» para ver só esta"); return; }
  cedLayout(); cedFit(); cedDraw(); cedDrawViews(); cedSyncUI();
}
function cedOnResize() {
  if (!S.ced) return;
  cedLayout(); cedDraw(); cedDrawViews();
}

// ------------------------------------------------------------ estado das ferramentas
function cedSet(patch) {
  const E = S.ced; if (!E) return;
  Object.assign(E, patch);
  if (patch.raio !== undefined) E.raio = Math.max(2, Math.min(60, Math.round(E.raio)));
  cedSyncUI(); cedDraw();
}
function cedSyncUI() {
  const E = S.ced; if (!E) return;
  $$("[data-ferr]").forEach((el) => { el.classList.toggle("on", el.dataset.ferr === E.tool); el.setAttribute("aria-pressed", String(el.dataset.ferr === E.tool)); });
  $$("[data-marca]").forEach((el) => {
    el.classList.toggle("on", el.dataset.marca === E.marca && E.tool !== "borracha");
    el.setAttribute("aria-pressed", String(el.dataset.marca === E.marca));
    el.disabled = E.tool === "borracha";
  });
  $$("[data-vista-btn]").forEach((el) => el.classList.toggle("on", el.dataset.vistaBtn === E.vista && E.mode === "one"));
  const rv = $("#ced-raio-v"), rg = $("#ced-raio");
  if (rv) rv.textContent = String(E.raio);
  if (rg && Number(rg.value) !== E.raio) rg.value = String(E.raio);
  if (rg) rg.disabled = E.tool === "laco";
  const fn = CED_FERRS.find((x) => x[0] === E.tool)[1];
  const mn = E.tool === "borracha" ? "apaga marcas" : CED_MARCAS.find((x) => x[0] === E.marca)[1];
  const act = $("#ced-active");
  if (act) act.textContent = `Ativo: ${fn} · ${mn}` + (E.retouch ? " · modo vértices" : "");
  const u = $("#ced-undo"), r = $("#ced-redo"), cl = $("#ced-clear");
  const vtUndo = E.retouch && E.vt && E.vt.undo.length > 0;
  if (u) u.disabled = !(E.pos > 0 || vtUndo);
  if (r) r.disabled = E.pos >= E.tracos.length;
  if (cl) cl.disabled = E.pos === 0 && E.tracos.length === 0;
  const vb = $("#ced-vertices");
  if (vb) { vb.classList.toggle("on", E.retouch); vb.setAttribute("aria-pressed", String(E.retouch)); }
  const cv = $("#ced-canvas");
  if (cv) { cv.classList.toggle("retouch", E.retouch); cv.classList.toggle("pen", !E.retouch && E.tool !== "laco"); }
  cedStatus();
}

// ------------------------------------------------------------ geometria (px do recorte <-> px css do canvas)
// view = {z, cx, cy}: zoom relativo ao ajuste e o ponto da imagem no centro; cada canvas calcula o seu
// ajuste, por isso as quatro vistas partilham a mesma transformação com tamanhos diferentes.
function cedXf(id = "ced-canvas") {
  const E = S.ced, c = $("#" + id);
  const r = c ? c.getBoundingClientRect() : { width: 1, height: 1 }, [w, hh] = E.d.tamanho;
  const fit = Math.min(r.width / w, r.height / hh) * 0.97 || 1, s = fit * E.view.z;
  return { s, ox: E.view.cx - r.width / (2 * s), oy: E.view.cy - r.height / (2 * s), w: r.width, h: r.height, fit };
}
const cedToImg = (x, y, xf = cedXf()) => [x / xf.s + xf.ox, y / xf.s + xf.oy];
const cedToScreen = (p, xf = cedXf()) => [(p[0] - xf.ox) * xf.s, (p[1] - xf.oy) * xf.s];
/** page (client) coordinates of a point in crop px on the main canvas (for tests / tools). */
function cedPagePoint(p) {
  const r = $("#ced-canvas").getBoundingClientRect(), [x, y] = cedToScreen(p);
  return [r.left + x, r.top + y];
}
function cedResize() {
  const dpr = window.devicePixelRatio || 1;
  $$("#ced canvas").forEach((c) => {
    const r = c.getBoundingClientRect();
    c.width = Math.max(1, Math.round(r.width * dpr)); c.height = Math.max(1, Math.round(r.height * dpr));
  });
}
function cedFit() {
  const E = S.ced; if (!E) return;
  E.view = { z: 1, cx: E.d.tamanho[0] / 2, cy: E.d.tamanho[1] / 2 };
}
function cedZoom(f, x, y) {
  const E = S.ced; if (!E) return;
  const xf = cedXf(), r = $("#ced-canvas").getBoundingClientRect();
  const px = x === undefined ? r.width / 2 : x, py = y === undefined ? r.height / 2 : y;
  const [ix, iy] = cedToImg(px, py, xf);
  const z = Math.min(40, Math.max(0.3, E.view.z * f)), s = xf.fit * z;
  E.view = { z, cx: ix + (r.width / 2 - px) / s, cy: iy + (r.height / 2 - py) / s };
  cedDraw(); cedDrawViews();
}

// ------------------------------------------------------------ desenho
function cedPath(ctx, poly) {
  ctx.beginPath();
  poly.forEach((p, i) => { if (i) ctx.lineTo(p[0] + 0.5, p[1] + 0.5); else ctx.moveTo(p[0] + 0.5, p[1] + 0.5); });
  ctx.closePath();
}
function cedBegin(ctx, c, xf) {
  const dpr = window.devicePixelRatio || 1;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.fillStyle = "#202226"; ctx.fillRect(0, 0, c.width, c.height);
  ctx.setTransform(dpr * xf.s, 0, 0, dpr * xf.s, -xf.ox * xf.s * dpr, -xf.oy * xf.s * dpr);
  ctx.imageSmoothingEnabled = xf.s < 2.5;
}
/** paints one stroke in crop px (the context transform is the caller's). */
function cedPaint(ctx, t) {
  ctx.lineCap = "round"; ctx.lineJoin = "round";
  const p = t.pontos;
  if (t.ferramenta === "laco") {
    ctx.beginPath(); p.forEach((q, i) => { if (i) ctx.lineTo(q[0], q[1]); else ctx.moveTo(q[0], q[1]); }); ctx.closePath(); ctx.fill();
  } else if (p.length === 1) {
    ctx.beginPath(); ctx.arc(p[0][0], p[0][1], t.raio_px, 0, 2 * Math.PI); ctx.fill();
  } else {
    ctx.lineWidth = 2 * t.raio_px;
    ctx.beginPath(); p.forEach((q, i) => { if (i) ctx.lineTo(q[0], q[1]); else ctx.moveTo(q[0], q[1]); }); ctx.stroke();
  }
}
function cedRenderLayer() {
  const E = S.ced, ctx = E.layer.getContext("2d");
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, E.layer.width, E.layer.height);
  for (const t of E.tracos.slice(0, E.pos)) {
    ctx.globalCompositeOperation = t.ferramenta === "borracha" ? "destination-out" : "source-over";
    const col = t.marca ? CED_RGB[t.marca] : "0,0,0";
    ctx.fillStyle = ctx.strokeStyle = `rgb(${col})`;
    cedPaint(ctx, t);
  }
  ctx.globalCompositeOperation = "source-over";
  E.layerDirty = false;
}
function cedFinalPoly() {
  const E = S.ced;
  if (E.vt && E.vt.edited) return cedVExpanded(E.vt);
  return (E.res && E.res.contour) || [];
}
function cedRaf() {
  const E = S.ced; if (!E || E.raf) return;
  E.raf = requestAnimationFrame(() => { E.raf = 0; if (S.ced === E) cedDraw(); });
}
function cedDraw() {
  const E = S.ced, c = $("#ced-canvas"); if (!E || !c) return;
  const ctx = c.getContext("2d"), dpr = window.devicePixelRatio || 1, xf = cedXf(), lw = 1 / xf.s;
  cedBegin(ctx, c, xf);
  ctx.drawImage(E.img, 0, 0);
  if (E.layerDirty) cedRenderLayer();
  ctx.globalAlpha = 0.5; ctx.drawImage(E.layer, 0, 0); ctx.globalAlpha = 1;
  const A = E.d.denso || [];
  if (A.length) { cedPath(ctx, A); ctx.setLineDash([4 * lw, 4 * lw]); ctx.strokeStyle = "rgba(41, 211, 230, .9)"; ctx.lineWidth = 1.2 * lw; ctx.stroke(); ctx.setLineDash([]); }
  const poly = cedFinalPoly();
  if (poly.length) { cedPath(ctx, poly); ctx.fillStyle = "rgba(255, 176, 0, .2)"; ctx.fill(); ctx.strokeStyle = "#ffb000"; ctx.lineWidth = 1.2 * lw; ctx.stroke(); }
  const L = E.live;
  if (L) {
    ctx.globalAlpha = 0.5;
    ctx.fillStyle = ctx.strokeStyle = L.ferramenta === "borracha" ? "rgb(255,70,70)" : `rgb(${CED_RGB[L.marca]})`;
    cedPaint(ctx, L);
    ctx.globalAlpha = 1;
    if (L.ferramenta === "laco") { ctx.strokeStyle = "#fff"; ctx.lineWidth = lw; ctx.setLineDash([3 * lw, 3 * lw]); ctx.stroke(); ctx.setLineDash([]); }
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  if (E.retouch && E.vt) {
    const V = E.vt;
    let per = 0;
    for (let i = 0; i < V.pts.length; i++) { const a = V.pts[i], b = V.pts[(i + 1) % V.pts.length]; per += Math.hypot(b[0] - a[0], b[1] - a[1]); }
    const dot = Math.max(1.5, Math.min(3.2, 0.3 * per * xf.s / Math.max(1, V.pts.length)));
    V.pts.forEach((p, i) => {
      const [x, y] = cedToScreen(p, xf), sel = i === V.sel;
      ctx.beginPath(); ctx.arc(x + 0.5 * xf.s, y + 0.5 * xf.s, sel ? CED_HIT : dot, 0, 2 * Math.PI);
      ctx.fillStyle = sel ? "#ffb000" : "#1a1300"; ctx.fill();
      ctx.lineWidth = sel ? 2 : 1.3; ctx.strokeStyle = sel ? "#fff" : "#ffb000"; ctx.stroke();
    });
  } else if (E.cur && !E.drag && !E.pinch && E.tool !== "laco") {
    const r = E.raio * xf.s;
    ctx.beginPath(); ctx.arc(E.cur[0], E.cur[1], r, 0, 2 * Math.PI);
    ctx.lineWidth = 3; ctx.strokeStyle = "rgba(0,0,0,.6)"; ctx.stroke();
    ctx.lineWidth = 1.2; ctx.strokeStyle = E.tool === "borracha" ? "#ff6a62" : "#fff"; ctx.stroke();
  }
}
function cedMaskAlpha(poly, w, h) {
  const c = document.createElement("canvas"); c.width = w; c.height = h;
  const x = c.getContext("2d", { willReadFrequently: true });
  x.fillStyle = x.strokeStyle = "#fff"; x.lineWidth = 1;
  cedPath(x, poly); x.fill(); x.stroke();
  return x.getImageData(0, 0, w, h).data;
}
/** rebuilds the difference raster (resolved vs current): gain magenta, loss cyan, agreement grey. */
function cedDiffBuild() {
  const E = S.ced, [w, hh] = E.d.tamanho, poly = cedFinalPoly();
  if (!E.maskA) E.maskA = cedMaskAlpha(E.d.denso || [], w, hh);
  const out = document.createElement("canvas"); out.width = w; out.height = hh;
  const x = out.getContext("2d"), im = x.createImageData(w, hh), D = im.data;
  const R = poly.length ? cedMaskAlpha(poly, w, hh) : null, A = E.maskA;
  for (let i = 0; i < w * hh; i++) {
    const a = A[i * 4 + 3] > 127, r = R ? R[i * 4 + 3] > 127 : false, o = i * 4;
    if (a && r) { D[o] = 200; D[o + 1] = 200; D[o + 2] = 200; D[o + 3] = 70; }
    else if (r) { D[o] = 255; D[o + 1] = 0; D[o + 2] = 220; D[o + 3] = 235; }
    else if (a) { D[o] = 0; D[o + 1] = 225; D[o + 2] = 255; D[o + 3] = 235; }
  }
  x.putImageData(im, 0, 0);
  E.diff = out;
}
function cedDrawViews() {
  const E = S.ced; if (!E) return;
  const [w, hh] = E.d.tamanho, poly = cedFinalPoly();
  for (const k of ["atual", "diff", "final"]) {
    const c = $(`#ced-v-${k}`); if (!c || !c.offsetParent) continue;
    const ctx = c.getContext("2d"), xf = cedXf(`ced-v-${k}`);
    cedBegin(ctx, c, xf);
    if (k === "atual") {
      ctx.fillStyle = "#000"; ctx.fillRect(0, 0, w, hh);
      if ((E.d.denso || []).length) { cedPath(ctx, E.d.denso); ctx.fillStyle = "#fff"; ctx.fill(); ctx.strokeStyle = "#fff"; ctx.lineWidth = 1; ctx.stroke(); }
    } else if (k === "diff") {
      ctx.drawImage(E.img, 0, 0);
      ctx.fillStyle = "rgba(0,0,0,.5)"; ctx.fillRect(0, 0, w, hh);
      if (E.diff) ctx.drawImage(E.diff, 0, 0);
    } else {
      if (!cedViews.checker) {
        const p = document.createElement("canvas"); p.width = p.height = 16;
        const q = p.getContext("2d"); q.fillStyle = "#3a3d42"; q.fillRect(0, 0, 16, 16); q.fillStyle = "#2a2c30"; q.fillRect(0, 0, 8, 8); q.fillRect(8, 8, 8, 8);
        cedViews.checker = ctx.createPattern(p, "repeat");
      }
      ctx.fillStyle = cedViews.checker; ctx.fillRect(0, 0, w, hh);
      if (poly.length) { ctx.save(); cedPath(ctx, poly); ctx.clip(); ctx.drawImage(E.img, 0, 0); ctx.restore(); }
    }
  }
}
const cedViews = { checker: null };

// ------------------------------------------------------------ estado / texto
function cedArea(pts) {
  let a = 0;
  for (let i = 0; i < pts.length; i++) { const p = pts[i], q = pts[(i + 1) % pts.length]; a += p[0] * q[1] - q[0] * p[1]; }
  return Math.abs(a) / 2;
}
function cedSimple(pts) {
  const n = pts.length;
  const o = (a, b, c) => (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
  for (let i = 0; i < n; i++) {
    const a = pts[i], b = pts[(i + 1) % n];
    for (let j = i + 2; j < n; j++) {
      if (i === 0 && j === n - 1) continue;
      const c = pts[j], d = pts[(j + 1) % n];
      const d1 = o(c, d, a), d2 = o(c, d, b), d3 = o(a, b, c), d4 = o(a, b, d);
      if (((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) && ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0))) return false;
    }
  }
  return true;
}
/** {ok, texto, aviso} about the polygon that would be saved. */
function cedValidity() {
  const E = S.ced, res = E.res;
  if (!res) return { ok: false, texto: "", aviso: "" };
  if (E.vt && E.vt.edited) {
    const lim = E.d.limites || { min_pontos: 20, area_min: 0.5, area_max: 1.5 };
    const poly = cedVExpanded(E.vt), ref = Math.max(1, cedArea(E.d.denso || []));
    const f = cedArea(poly) / ref, warn = [];
    if (poly.length < lim.min_pontos) warn.push(`precisa de pelo menos ${lim.min_pontos} pontos`);
    if (f < lim.area_min || f > lim.area_max) warn.push(`área fora de ${Math.round(lim.area_min * 100)}–${Math.round(lim.area_max * 100)} %`);
    if (!cedSimple(poly)) warn.push("o contorno cruza-se");
    const mm2 = cedArea(poly) * E.d.mmpp * E.d.mmpp;
    return { ok: warn.length === 0, texto: `retocado · ${fmt(mm2, 1)} mm² (${Math.round(f * 100)} % da atual) · ${poly.length} pontos`, aviso: warn.join(" · ") };
  }
  const pct = E.d.area_mm2 ? Math.round(100 * res.area_mm2 / E.d.area_mm2) : null;
  const txt = res.contour && res.contour.length
    ? `${fmt(res.area_mm2, 1)} mm²` + (pct !== null ? ` (${pct} % da atual)` : "") + ` · ${res.n_pontos} pontos · ${Math.round(res.ms)} ms` : "sem contorno";
  return { ok: !!res.valido, texto: txt, aviso: res.valido ? "" : (res.erro || "contorno inválido") };
}
function cedStatus() {
  const E = S.ced, el = $("#ced-status"); if (!E || !el) return;
  const v = cedValidity();
  el.replaceChildren(v.texto || (E.busy ? "" : "—"), ...(v.aviso ? [h("span", { class: "ced-warn" }, ` · ${v.aviso}`)] : []));
  el.classList.toggle("bad", !!v.aviso);
  const busy = $("#ced-busy");
  if (busy) busy.textContent = E.busy ? "a resolver…" : "";
  const sv = $("#ced-save");
  if (sv) sv.disabled = !v.ok || E.busy || E.inflight;
}

// ------------------------------------------------------------ traços: histórico + resolução ao vivo
function cedStrokesChanged() {
  const E = S.ced;
  E.layerDirty = true; E.dirty = true;
  if (E.vt && E.vt.edited) toast("o retoque de vértices perdeu-se: o contorno foi resolvido de novo com os traços");
  E.vt = null;
  cedSyncUI(); cedDraw();
  cedSchedule(CED_DEBOUNCE_MS);
}
function cedCommit(t) {
  const E = S.ced;
  E.tracos.length = E.pos;               // a stroke after an undo cuts the tail
  E.tracos.push(t); E.pos = E.tracos.length;
  cedStrokesChanged();
}
function cedUndo() {
  const E = S.ced; if (!E) return;
  if (E.retouch && E.vt && E.vt.undo.length) { cedVUndo(); return; }
  if (E.pos > 0) { E.pos--; cedStrokesChanged(); }
}
function cedRedo() {
  const E = S.ced; if (!E || E.pos >= E.tracos.length) return;
  E.pos++; cedStrokesChanged();
}
function cedClear() {
  const E = S.ced; if (!E || (!E.tracos.length)) return;
  if (!confirm("Limpar todos os traços?")) return;
  E.tracos = []; E.pos = 0; cedStrokesChanged();
}
function cedSchedule(delay) {
  const E = S.ced; if (!E) return;
  E.seq++; E.busy = true;
  clearTimeout(E.timer);
  E.timer = setTimeout(cedFire, delay);
  cedStatus();
}
async function cedFire() {
  const E = S.ced; if (!E) return;
  if (E.inflight) { E.again = true; return; }
  const seq = E.seq;
  E.inflight = true;
  let r = null, err = null;
  try {
    r = await api(`/api/pieces/${E.pid}/contorno/resolver`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tracos: E.tracos.slice(0, E.pos), origem: E.d.origem, tamanho: E.d.tamanho }) });
  } catch (e) { err = e.message; }
  E.inflight = false;
  if (S.ced !== E) return;
  if (seq !== E.seq) {                    // a newer change arrived: this answer is stale
    if (E.again) { E.again = false; cedFire(); }
    return;
  }
  E.busy = false; E.again = false;
  if (err) { E.res = { contour: [], area_mm2: 0, valido: false, erro: err, n_pontos: 0, ms: 0 }; toast(err, true); }
  else E.res = r;
  E.vt = null;
  if (E.retouch) cedVInit();
  cedDiffBuild();
  cedSyncUI(); cedDraw(); cedDrawViews();
}

// ------------------------------------------------------------ retoque por vértices (opcional)
// V.pts are handles over V.d (the resolved polygon), V.oi their index in V.d (null once moved / created) and
// V.keep[i] = edge i -> i+1 untouched: an untouched edge expands back to the exact points of V.d.
function cedVInit() {
  const E = S.ced, D = (E.res && E.res.contour) || [];
  if (D.length < 20) { toast("sem contorno resolvido para afinar", true); E.retouch = false; return; }
  const step = 1 / E.d.mmpp, idx = [0];       // about one handle per mm
  let acc = 0;
  for (let i = 1; i < D.length; i++) { acc += Math.hypot(D[i][0] - D[i - 1][0], D[i][1] - D[i - 1][1]); if (acc >= step) { idx.push(i); acc = 0; } }
  E.vt = { d: D.map((p) => [p[0], p[1]]), pts: idx.map((i) => [D[i][0], D[i][1]]), oi: idx.slice(), keep: idx.map(() => true), undo: [], sel: null, edited: false };
}
function cedVExpanded(V) {
  const n = V.pts.length, D = V.d, m = D.length, out = [];
  for (let i = 0; i < n; i++) {
    out.push(V.pts[i]);
    const a = V.oi[i], b = V.oi[(i + 1) % n];
    if (V.keep[i] && a !== null && b !== null && m && n > 1) {
      for (let j = (a + 1) % m, g = 0; j !== b && g < m; j = (j + 1) % m, g++) out.push(D[j]);
    }
  }
  return out;
}
function cedVSnap(V) { return { pts: V.pts.map((p) => p.slice()), oi: V.oi.slice(), keep: V.keep.slice(), sel: V.sel, edited: V.edited }; }
function cedVPush() {
  const V = S.ced.vt;
  V.undo.push(cedVSnap(V));
  if (V.undo.length > 200) V.undo.shift();
  V.edited = true; S.ced.dirty = true;
}
function cedVUndo() {
  const E = S.ced, V = E.vt; if (!V || !V.undo.length) return;
  const u = V.undo.pop();
  V.pts = u.pts; V.oi = u.oi; V.keep = u.keep; V.sel = null; V.edited = u.edited;
  cedDiffBuild(); cedSyncUI(); cedDraw(); cedDrawViews();
}
function cedVDelete() {
  const E = S.ced, V = E && E.vt; if (!V || V.sel === null) return;
  if (V.pts.length <= 3) { toast("um contorno precisa de pelo menos 3 vértices", true); return; }
  cedVPush();
  const i = V.sel;
  V.pts.splice(i, 1); V.oi.splice(i, 1); V.keep.splice(i, 1);
  V.keep[(i - 1 + V.pts.length) % V.pts.length] = false; V.sel = null;
  cedDiffBuild(); cedSyncUI(); cedDraw(); cedDrawViews();
}
function cedToggleRetouch() {
  const E = S.ced; if (!E) return;
  if (E.retouch) { E.retouch = false; cedSyncUI(); cedDraw(); return; }
  if (!E.res || !E.res.contour || !E.res.contour.length) { toast("ainda não há contorno resolvido", true); return; }
  E.retouch = true;
  if (!E.vt) cedVInit();
  cedSyncUI(); cedDraw();
}
function cedVHitVertex(x, y, r, xf) {
  let best = null, bd = r;
  S.ced.vt.pts.forEach((p, i) => { const [sx, sy] = cedToScreen([p[0] + 0.5, p[1] + 0.5], xf); const dd = Math.hypot(sx - x, sy - y); if (dd <= bd) { bd = dd; best = i; } });
  return best;
}
function cedVHitEdge(x, y, r, xf) {
  const V = S.ced.vt, n = V.pts.length; let best = null, bd = r;
  for (let i = 0; i < n; i++) {
    const a = cedToScreen([V.pts[i][0] + 0.5, V.pts[i][1] + 0.5], xf), b = cedToScreen([V.pts[(i + 1) % n][0] + 0.5, V.pts[(i + 1) % n][1] + 0.5], xf);
    const dx = b[0] - a[0], dy = b[1] - a[1], L = dx * dx + dy * dy || 1;
    const t = Math.max(0, Math.min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / L));
    const dd = Math.hypot(a[0] + t * dx - x, a[1] + t * dy - y);
    if (dd <= bd) { bd = dd; const q = cedToImg(a[0] + t * dx, a[1] + t * dy, xf); best = { i, p: [q[0] - 0.5, q[1] - 0.5] }; }
  }
  return best;
}
function cedClampPt(p) {
  const [w, hh] = S.ced.d.tamanho;
  return [Math.max(0, Math.min(w - 1, Math.round(p[0] * 100) / 100)), Math.max(0, Math.min(hh - 1, Math.round(p[1] * 100) / 100))];
}

// ------------------------------------------------------------ ponteiros, roda, teclas
function cedBind(c) {
  const local = (e) => { const r = c.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
  c.addEventListener("wheel", (e) => {
    e.preventDefault();
    const [x, y] = local(e);
    cedZoom(Math.exp(-e.deltaY * (e.deltaMode === 1 ? 0.05 : 0.0025)), x, y);
  }, { passive: false });
  c.addEventListener("mousedown", (e) => { if (e.button === 1) e.preventDefault(); });   // no autoscroll
  c.addEventListener("pointerdown", (e) => {
    const E = S.ced; if (!E) return;
    c.focus({ preventScroll: true });
    try { c.setPointerCapture(e.pointerId); } catch (err) { /* synthetic pointer: no capture */ }
    const [x, y] = local(e);
    E.ptrs.set(e.pointerId, { x, y });
    if (E.ptrs.size === 2) {               // pinch (touch): zoom about the midpoint, cancels a stroke / vertex drag
      const [a, b] = [...E.ptrs.values()];
      E.live = null;
      if (E.drag && E.drag.kind === "v" && E.drag.pushed) cedVUndo();
      E.drag = null;
      E.pinch = { d: Math.hypot(a.x - b.x, a.y - b.y), view: { ...E.view }, mx: (a.x + b.x) / 2, my: (a.y + b.y) / 2 };
      cedDraw();
      return;
    }
    if (E.ptrs.size > 2) return;
    const xf = cedXf();
    if (e.button === 1 || (e.button === 0 && E.space)) {
      e.preventDefault();
      E.drag = { kind: "pan", x, y, view: { ...E.view }, xf };
      c.classList.add("panning");
      return;
    }
    if (e.button !== 0) return;
    if (E.retouch && E.vt) {
      const V = E.vt, r = e.pointerType === "touch" ? CED_HIT_TOUCH : CED_HIT;
      let i = cedVHitVertex(x, y, r, xf), pushed = false;
      if (i === null) {
        const ed = cedVHitEdge(x, y, r, xf);
        if (ed) {
          cedVPush(); pushed = true;
          V.pts.splice(ed.i + 1, 0, cedClampPt(ed.p)); V.oi.splice(ed.i + 1, 0, null); V.keep.splice(ed.i, 1, false, false);
          i = ed.i + 1;
        }
      }
      if (i !== null) { V.sel = i; E.drag = { kind: "v", i, pushed, x, y }; }
      else { V.sel = null; E.drag = { kind: "pan", x, y, view: { ...E.view }, xf }; c.classList.add("panning"); }
      cedDraw();
      return;
    }
    const pt = cedToImg(x, y, xf).map((v) => Math.round(v * 100) / 100);
    const tool = E.tool;
    const marca = tool === "borracha" ? null : (e.shiftKey ? "peca" : e.altKey ? "fundo" : E.marca);
    E.live = { ferramenta: tool, marca, raio_px: E.raio, pontos: [pt], pid: e.pointerId };
    cedDraw();
  });
  c.addEventListener("pointermove", (e) => {
    const E = S.ced; if (!E) return;
    const [x, y] = local(e);
    if (!E.ptrs.has(e.pointerId)) { E.cur = [x, y]; cedRaf(); return; }
    E.ptrs.set(e.pointerId, { x, y });
    E.cur = e.pointerType === "touch" ? null : [x, y];
    if (E.pinch && E.ptrs.size >= 2) {
      const [a, b] = [...E.ptrs.values()], P = E.pinch, xf0 = cedXf();
      const z = Math.min(40, Math.max(0.3, P.view.z * Math.hypot(a.x - b.x, a.y - b.y) / Math.max(1, P.d)));
      const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2, s0 = xf0.fit * P.view.z, s = xf0.fit * z;
      const ix = P.view.cx + (P.mx - xf0.w / 2) / s0, iy = P.view.cy + (P.my - xf0.h / 2) / s0;
      E.view = { z, cx: ix + (xf0.w / 2 - mx) / s, cy: iy + (xf0.h / 2 - my) / s };
      cedDraw(); cedDrawViews();
      return;
    }
    const D = E.drag, L = E.live;
    if (D && D.kind === "pan") {
      const s = D.xf.s;
      E.view = { z: D.view.z, cx: D.view.cx - (x - D.x) / s, cy: D.view.cy - (y - D.y) / s };
      cedDraw(); cedDrawViews();
    } else if (D && D.kind === "v") {
      const V = E.vt;
      if (!D.pushed) { if (Math.hypot(x - D.x, y - D.y) < 2) return; cedVPush(); D.pushed = true; V.oi[D.i] = null; V.keep[D.i] = false; V.keep[(D.i - 1 + V.pts.length) % V.pts.length] = false; }
      const q = cedToImg(x, y); V.pts[D.i] = cedClampPt([q[0] - 0.5, q[1] - 0.5]);
      cedDraw();
    } else if (L && L.pid === e.pointerId) {
      if (e.shiftKey && L.ferramenta !== "borracha") L.marca = "peca";
      else if (e.altKey && L.ferramenta !== "borracha") L.marca = "fundo";
      const xf = cedXf(), q = cedToImg(x, y, xf).map((v) => Math.round(v * 100) / 100), last = L.pontos[L.pontos.length - 1];
      if (Math.hypot(q[0] - last[0], q[1] - last[1]) * xf.s >= 1.5) L.pontos.push(q);
      cedDraw();
    }
  });
  const up = (e) => {
    const E = S.ced; if (!E) return;
    const had = E.ptrs.has(e.pointerId);
    E.ptrs.delete(e.pointerId);
    if (E.ptrs.size < 2) E.pinch = null;
    const L = E.live;
    if (L && L.pid === e.pointerId && e.type === "pointerup") {
      E.live = null;
      const ok = L.ferramenta === "laco" ? L.pontos.length >= 3 : L.pontos.length >= 1;
      if (ok) cedCommit({ ferramenta: L.ferramenta, marca: L.marca, raio_px: L.ferramenta === "laco" ? 1 : L.raio_px, pontos: L.pontos });
      else cedDraw();
    } else if (L && L.pid === e.pointerId) { E.live = null; cedDraw(); }
    if (had && E.ptrs.size === 0) {
      const D = E.drag;
      E.drag = null; c.classList.remove("panning");
      if (D && D.kind === "v" && D.pushed) { cedDiffBuild(); cedSyncUI(); cedDrawViews(); }
      else if (D && D.kind === "pan") { cedDrawViews(); }
      else cedStatus();
    }
  };
  c.addEventListener("pointerup", up);
  c.addEventListener("pointercancel", up);
  c.addEventListener("pointerleave", () => { const E = S.ced; if (E && !E.ptrs.size) { E.cur = null; cedRaf(); } });
  c.addEventListener("contextmenu", (e) => e.preventDefault());
}
function cedKey(e) {
  const E = S.ced; if (!E) return;
  const tag = (e.target && e.target.tagName) || "";
  const typing = tag === "TEXTAREA" || (tag === "INPUT" && e.target.type !== "range");
  if (e.type === "keyup") { if (e.key === " ") { E.space = false; const c = $("#ced-canvas"); if (c) c.classList.remove("space"); } return; }
  if (e.key === "Escape") { e.preventDefault(); cedClose(); return; }
  if (typing) return;
  const mod = e.ctrlKey || e.metaKey, k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  if (mod && k === "z") { e.preventDefault(); if (e.shiftKey) cedRedo(); else cedUndo(); return; }
  if (mod && k === "y") { e.preventDefault(); cedRedo(); return; }
  if (mod) return;
  if (k === "l") cedSet({ tool: "laco" });
  else if (k === "p") cedSet({ tool: "pincel" });
  else if (k === "b") cedSet({ tool: "borracha" });
  else if (k === "1") cedSet({ marca: "peca" });
  else if (k === "2") cedSet({ marca: "fundo" });
  else if (k === "3") cedSet({ marca: "incerto" });
  else if (k === "[") cedSet({ raio: E.raio - (E.raio > 20 ? 4 : 2) });
  else if (k === "]") cedSet({ raio: E.raio + (E.raio >= 20 ? 4 : 2) });
  else if (k === "Delete" || k === "Backspace") { if (E.retouch) { e.preventDefault(); cedVDelete(); } }
  else if (k === " ") { e.preventDefault(); E.space = true; const c = $("#ced-canvas"); if (c) c.classList.add("space"); }
}

// ------------------------------------------------------------ gravar
async function cedSave(btn) {
  const E = S.ced; if (!E) return;
  const v = cedValidity();
  if (!v.ok) { toast(v.aviso || "contorno inválido", true); return; }
  const poly = cedFinalPoly().map((p) => [p[0], p[1]]);
  const old = btn.textContent;
  btn.disabled = true; btn.textContent = "a gravar…";
  try {
    const r = await api(`/api/pieces/${E.pid}/contorno`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ contour: poly, origem: E.d.origem, tamanho: E.d.tamanho, nota: $("#ced-nota").value,
        tracos: E.tracos.slice(0, E.pos), solver: (E.res && E.res.solver) || E.d.solver_omissao || "grabcut" }) });
    for (const m of r.mensagens || []) toast(m);
    if (r.invariantes && r.invariantes.length) toast("INVARIANTES: " + r.invariantes.join("; "), true);
    E.dirty = false;
    await loadAll();
    if (S.lots) loadLots().catch(() => {});
    cedLeave();
  } catch (e) {
    toast(e.message, true);
    btn.disabled = false;
  } finally { btn.textContent = old; }
}
