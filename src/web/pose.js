/* Editar posicionamento — pose manual de uma peça colocada (docs/gui-design.md §20, docs/diagnostico/render/POSE_MANUAL.md).
 *
 * O tabuleiro é o editor: por cima dele (#pose-layer) vê-se o contorno das vizinhas (ciano, fixo) e a peça
 * com o scan (opaco a 85 %) e o contorno (âmbar) na pose candidata. A candidata só muda por ação explícita
 * do utilizador (arrastar, pega de rotação, Alt+roda, teclas, campos, e os dois botões «Pose automática» e
 * «Alinhar a 90°»): NÃO há snap automático. A cada mudança, debounce de 120 ms, 1 pedido em voo e respostas
 * antigas descartadas: POST /api/pieces/{id}/pose/avaliar (folgas, consistência), sem escrever nada.
 * Gravar = POST /api/pieces/{id}/pose (≈ 9 s), repor = POST /api/pieces/{id}/pose/repor (≈ 4 s).
 * Usa globais de app.js ($, $$, h, s, S, api, toast, fmt, fitRect, clientToBoard, svg, openCell, loadAll, cellTxt).
 */
"use strict";

const POSE_DEBOUNCE_MS = 120;
const POSE_ROT_R = 1.1;             // pega de rotação, em células a partir do pivô
const POSE_EPS = 1e-6;
const r3 = (v) => Math.round(v * 1000) / 1000;
const fz = (v, nd) => fmt(Number(v.toFixed(nd)) + 0, nd);          // no «-0,0»
const wrap180 = (a) => { let x = ((a + 180) % 360 + 360) % 360 - 180; return x === -180 ? 180 : x; };

// ------------------------------------------------------------ botão / chip (usados por app.js)
function poseButton(pid) {
  return h("button", { class: "btn slim", type: "button", "data-pose-btn": pid, "aria-label": "Editar posicionamento",
    title: "ajustar levemente a rotação e a posição da peça no tabuleiro (sem encaixe automático)",
    disabled: S.pose ? true : null, onclick: () => openPoseEditor(pid) }, "⤧ Editar posicionamento");
}
function poseBadge(p) {
  const m = p && p.pose_manual;
  if (!m) return null;
  return h("div", { class: "manual-badge small", "data-pose-badge": p.id || "" },
    h("span", { class: "chip manual", title: "posição desenhada à mão: a peça fica fora das métricas de registo e de orientação" }, "pose manual"),
    h("span", { class: "muted" }, ` θ ${fmt(m.theta_deg, 1)}° · dx ${fmt(m.dx_mm, 1)} · dy ${fmt(m.dy_mm, 1)} mm` + (m.nota ? ` · ${m.nota}` : "")));
}

// ------------------------------------------------------------ geometria
function poseSvgTransform(P, c) {
  const d = P.d;
  const tx = (d.cell[1] - 0.5) + c.dx / d.w_mm, ty = (d.cell[0] - 0.5) * d.hr + c.dy / d.w_mm;
  return { tx, ty, str: `translate(${tx.toFixed(5)} ${ty.toFixed(5)}) rotate(${c.theta.toFixed(4)})` };
}
const poseClose2 = (a, b) => Math.abs(a - b) < POSE_EPS;
function poseIsDirty(P) {
  const e = P.d.efetiva, c = P.cand;
  return !(poseClose2(wrap180(c.theta - e.theta_deg), 0) && poseClose2(c.dx, e.dx_mm) && poseClose2(c.dy, e.dy_mm));
}

// ------------------------------------------------------------ abrir / fechar
async function openPoseEditor(pid) {
  if (S.ced) return;
  if (S.pose) { if (S.pose.pid === pid) return; if (!(await poseCancel())) return; }
  let d;
  try { d = await api(`/api/pieces/${pid}/pose`); } catch (e) { toast(e.message, true); return; }
  const e = d.efetiva;
  const P = S.pose = { pid, d, cand: { theta: r3(wrap180(e.theta_deg)), dx: r3(e.dx_mm), dy: r3(e.dy_mm) }, res: null, err: null, dirty: false,
    seq: 0, timer: null, inflight: false, again: false, busy: false, nota: "", limited: false, drag: null, tEval: null };
  $("#app").classList.remove("sheet-up");
  document.body.dataset.pose = pid;
  $$("[data-pose-btn]").forEach((b) => { b.disabled = true; });
  const [l, c] = d.cell;
  fitRect(c - 1 - 1.5, (l - 1) * S.hr - 1.5, c + 1.5, l * S.hr + 1.5, 0.02);
  poseBuildLayer();
  poseBuildPanel();
  poseMountPanel();
  poseRefresh();
  poseSchedule(0);
}

function poseBuildLayer() {
  const P = S.pose, d = P.d, lay = $("#pose-layer");
  lay.replaceChildren();
  const neigh = s("g", { id: "pose-neigh" });
  for (const dir of ["N", "E", "S", "W"]) {
    const n = d.vizinhas[dir];
    if (!n || !n.contorno || !n.contorno.length) continue;
    neigh.append(s("path", { class: "pose-neigh", "data-dir": dir, d: poseDraw(n.contorno), transform: n.svg.transform }));
  }
  lay.append(neigh);
  const g = s("g", { id: "pose-piece" });
  g.append(s("image", { id: "pose-img", href: `/api/pieces/${P.pid}.png?pose=scan&size=600&v=${S.ver}`, x: -0.9, y: -0.9, width: 1.8, height: 1.8,
    opacity: 0.85, "pointer-events": "none" }));
  g.append(s("path", { id: "pose-hit", class: "pose-contour", d: poseDraw(d.contorno) }));
  g.append(s("line", { class: "pose-arm", x1: 0, y1: 0, x2: 0, y2: -POSE_ROT_R }));
  g.append(s("circle", { class: "pose-pivot", cx: 0, cy: 0, r: 0.035 }));
  g.append(s("circle", { id: "pose-rot-hit", class: "pose-rot-hit", cx: 0, cy: -POSE_ROT_R, r: 0.32 }));
  g.append(s("circle", { id: "pose-rot", class: "pose-rot", cx: 0, cy: -POSE_ROT_R, r: 0.11, "pointer-events": "none" }));
  lay.append(g);
  poseWireDrag($("#pose-hit"), "move");
  poseWireDrag($("#pose-rot-hit"), "rot");
}
function poseDraw(pts) { return "M" + pts.map(([x, y]) => `${x.toFixed(4)} ${y.toFixed(4)}`).join("L") + "Z"; }

function poseClose() {
  const P = S.pose;
  if (P) { clearTimeout(P.timer); P.seq++; if (P.panel) P.panel.remove(); }
  S.pose = null;
  const lay = $("#pose-layer"); if (lay) lay.replaceChildren();
  delete document.body.dataset.pose;
  $$("[data-pose-btn]").forEach((b) => { b.disabled = false; });
}
async function poseCancel() {
  const P = S.pose; if (!P) return true;
  if (P.busy) return false;
  if (poseIsDirty(P) && !confirm("Descartar as alterações à posição da peça?")) return false;
  poseClose();
  return true;
}

// ------------------------------------------------------------ painel (na gaveta da célula)
function poseBuildPanel() {
  const P = S.pose, d = P.d;
  const num = (key, label, unit) => h("label", { class: "pose-f" }, h("span", {}, label),
    h("input", { type: "number", step: "0.1", "data-pose-f": key, inputmode: "decimal", "aria-label": `${label} (${unit})`,
      oninput: (ev) => poseSetFromInput(key, ev.target) }), h("em", {}, unit));
  P.panel = h("section", { id: "pose-panel", class: "pose-panel", "aria-label": "Editar posicionamento" },
    h("h2", {}, `Editar posicionamento · ${P.pid} em ${cellTxt(d.cell)}`),
    h("div", { class: "pose-fields" }, num("theta", "θ", "°"), num("dx", "dx", "mm"), num("dy", "dy", "mm")),
    h("div", { class: "actions" },
      h("button", { class: "btn slim", type: "button", "data-pose-act": "auto", title: "repõe os campos com a pose automática (não grava)", onclick: poseUseAuto }, "Pose automática"),
      h("button", { class: "btn slim", type: "button", "data-pose-act": "r90", title: "arredonda θ ao múltiplo de 90° mais próximo (não grava)", onclick: poseSnap90 }, "Alinhar a 90°")),
    h("div", { class: "pose-juntas", id: "pose-juntas", "aria-live": "polite" }),
    h("div", { class: "pose-cons small", id: "pose-cons" }),
    h("div", { class: "pose-diff small muted", id: "pose-diff" }),
    h("label", { class: "pose-nota" }, h("span", { class: "small muted" }, "nota (opcional)"),
      h("input", { type: "text", id: "pose-nota", maxlength: "200", placeholder: "porquê esta pose", oninput: (ev) => { P.nota = ev.target.value; } })),
    h("div", { class: "actions pose-save" },
      h("button", { class: "btn primary", type: "button", id: "pose-save", onclick: poseSave }, "Gravar"),
      d.manual ? h("button", { class: "btn", type: "button", id: "pose-reset", title: "apaga a pose manual e volta à pose automática", onclick: poseReset }, "Repor automática") : null,
      h("button", { class: "btn", type: "button", id: "pose-cancel", onclick: () => { poseCancel(); } }, "Cancelar")),
    h("p", { class: "small muted pose-help" },
      "Arrasta a peça (ou a bola âmbar para rodar). Setas ±0,1 mm (Shift ±0,5), Q/E ±0,1° (Shift ±1°), Alt+roda ±0,2°, Enter grava, Esc cancela. " +
      "Não há encaixe automático. A pose antiga continua visível no fundo até gravar."));
}
function poseMountPanel() {
  const P = S.pose; if (!P || !P.panel) return;
  // wide screens: under the piece card; phone (bottom sheet): right under the head so the gaps are visible without scrolling
  const narrow = window.matchMedia("(max-width: 900px)").matches;
  const anchor = narrow ? $("#tab-celula .cell-head") : $("#tab-celula .card");
  if (anchor) anchor.after(P.panel); else $("#tab-celula").prepend(P.panel);
}

const POSE_DIRS = { N: "Norte", E: "Este", S: "Sul", W: "Oeste" };
function poseGapClass(g) { const a = Math.abs(g); return a <= 0.3 ? "ok" : (a <= 0.8 ? "mid" : "bad"); }
function poseRender() {
  const P = S.pose; if (!P) return;
  const box = $("#pose-juntas");
  const res = P.res;
  box.replaceChildren(...["N", "E", "S", "W"].map((k) => {
    const j = res && res.juntas ? res.juntas[k] : null;
    const nb = P.d.vizinhas[k];
    const row = h("div", { class: "pose-j", "data-dir": k });
    row.append(h("b", {}, POSE_DIRS[k]), h("span", { class: "muted small" }, nb ? nb.piece : ""));
    if (!res) row.append(h("span", { class: "muted" }, "a medir…"));
    else if (!j || j.gap_mm === null || j.gap_mm === undefined) row.append(h("span", { class: "muted" }, "—"));
    else {
      const g = j.gap_mm;
      row.append(h("span", { class: `pose-gap ${poseGapClass(g)}` }, `${g >= 0 ? "+" : "−"}${fmt(Math.abs(g), 2)} mm`), h("span", { class: "small muted" }, g < 0 ? "sobrepõe" : "folga"));
    }
    return row;
  }));
  const cons = $("#pose-cons");
  if (P.err) { cons.textContent = P.err; cons.className = "pose-cons small bad"; }
  else if (!res) { cons.textContent = ""; cons.className = "pose-cons small"; }
  else {
    const c = res.consistencia || {};
    const lab = c.grau === "impossivel" ? "orientação impossível" : (c.grau === "melhor_rotacao" ? "há melhor rotação" : "orientação consistente");
    const worst = res.pior_mm === null || res.pior_mm === undefined ? "sem vizinhas" : `pior junta ${fmt(res.pior_mm, 2)} mm${res.pior_dir ? " (" + (POSE_DIRS[res.pior_dir] || res.pior_dir) + ")" : ""}`;
    cons.className = `pose-cons small ${c.grau === "impossivel" ? "bad" : (c.grau === "melhor_rotacao" ? "mid" : "ok")}`;
    cons.textContent = `${worst} · ${lab}${c.texto ? " — " + c.texto : ""}`;
  }
  const a = P.d.automatica, c = P.cand;
  $("#pose-diff").textContent = `face à automática: Δθ ${fz(wrap180(c.theta - a.theta_deg), 1)}° · Δdx ${fz(c.dx - a.dx_mm, 2)} · Δdy ${fz(c.dy - a.dy_mm, 2)} mm` +
    (res && res.ms !== undefined ? ` · ${fmt(res.ms, 0)} ms` : "") + (P.limited ? " · no limite do deslocamento" : "");
}
function poseRefresh() {
  const P = S.pose; if (!P) return;
  const c = P.cand, t = poseSvgTransform(P, c);
  const g = $("#pose-piece"); if (g) g.setAttribute("transform", t.str);
  for (const inp of $$("[data-pose-f]", P.panel)) {
    if (document.activeElement === inp) continue;
    inp.value = String(c[inp.dataset.poseF]);
  }
  P.dirty = poseIsDirty(P);
  poseRender();
}

// ------------------------------------------------------------ alterar a candidata (só por ação do utilizador)
function poseLimit(P, c) {
  const L = P.d.limites; let lim = false;
  const cl = (v, m) => { if (v > m) { lim = true; return m; } if (v < -m) { lim = true; return -m; } return v; };
  c.dx = r3(cl(c.dx, L.dx_max_mm)); c.dy = r3(cl(c.dy, L.dy_max_mm)); c.theta = r3(wrap180(c.theta));
  P.limited = lim;
  return c;
}
function poseSet(patch) {
  const P = S.pose; if (!P || P.busy) return;
  const c = { ...P.cand };
  for (const k of ["theta", "dx", "dy"]) if (patch[k] !== undefined && Number.isFinite(patch[k])) c[k] = patch[k];
  P.cand = poseLimit(P, c);
  poseRefresh();
  poseSchedule(POSE_DEBOUNCE_MS);
}
function poseSetFromInput(key, el) {
  const v = parseFloat(el.value);
  if (!Number.isFinite(v)) return;
  poseSet({ [key]: v });
}
function poseUseAuto() {
  const P = S.pose; if (!P) return;
  const a = P.d.automatica;
  poseSet({ theta: a.theta_deg, dx: a.dx_mm, dy: a.dy_mm });
}
function poseSnap90() {
  const P = S.pose; if (!P) return;
  poseSet({ theta: Math.round(P.cand.theta / 90) * 90 });
}

// ------------------------------------------------------------ rato / toque
function poseBoardPt(e) { return clientToBoard(e.clientX, e.clientY); }
function poseWireDrag(el, mode) {
  el.addEventListener("pointerdown", (e) => {
    const P = S.pose; if (!P || P.busy) return;
    if (e.button !== undefined && e.button !== 0) return;     // botão do meio / direito: pan e menus ficam como estão
    e.stopPropagation();
    el.setPointerCapture(e.pointerId);
    const p0 = poseBoardPt(e), t = poseSvgTransform(P, P.cand);
    P.drag = { id: e.pointerId, mode, p0, c0: { ...P.cand }, a0: Math.atan2(p0.y - t.ty, p0.x - t.tx), pivot: t };
    el.classList.add("grab");
  });
  el.addEventListener("pointermove", (e) => {
    const P = S.pose, D = P && P.drag; if (!D || D.id !== e.pointerId) return;
    e.stopPropagation();
    const p = poseBoardPt(e), w = P.d.w_mm;
    if (D.mode === "move") poseSet({ dx: D.c0.dx + (p.x - D.p0.x) * w, dy: D.c0.dy + (p.y - D.p0.y) * w });
    else {
      const a = Math.atan2(p.y - D.pivot.ty, p.x - D.pivot.tx);
      poseSet({ theta: D.c0.theta + wrap180((a - D.a0) * 180 / Math.PI) });
    }
  });
  const end = (e) => {
    const P = S.pose, D = P && P.drag; if (!D || D.id !== e.pointerId) return;
    e.stopPropagation();
    P.drag = null; el.classList.remove("grab");
  };
  el.addEventListener("pointerup", end);
  el.addEventListener("pointercancel", end);
}
function poseWheel(e) {
  const P = S.pose; if (!P) return;
  poseSet({ theta: P.cand.theta + (e.deltaY < 0 ? 0.2 : -0.2) });
}

// ------------------------------------------------------------ teclado
function poseKey(e) {
  const P = S.pose; if (!P) return;
  const tag = (e.target && e.target.tagName) || "";
  const typing = tag === "TEXTAREA" || (tag === "INPUT");
  if (e.key === "Escape") { e.preventDefault(); poseCancel(); return; }
  if (e.key === "Enter") {
    if (tag === "BUTTON") return;                                // o botão focado trata o seu Enter
    if (tag === "INPUT" && e.target.dataset.poseF) { e.target.blur(); return; }
    e.preventDefault(); poseSave(); return;
  }
  if (typing || e.ctrlKey || e.metaKey || e.altKey) return;
  const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  const sh = e.shiftKey, c = P.cand;
  const mm = sh ? 0.5 : 0.1, dg = sh ? 1 : 0.1;
  let done = true;
  if (k === "ArrowRight") poseSet({ dx: c.dx + mm });
  else if (k === "ArrowLeft") poseSet({ dx: c.dx - mm });
  else if (k === "ArrowDown") poseSet({ dy: c.dy + mm });
  else if (k === "ArrowUp") poseSet({ dy: c.dy - mm });
  else if (k === "q") poseSet({ theta: c.theta - dg });
  else if (k === "e") poseSet({ theta: c.theta + dg });
  else done = false;
  if (done) e.preventDefault();
}

// ------------------------------------------------------------ avaliar ao vivo
function poseSchedule(delay) {
  const P = S.pose; if (!P) return;
  clearTimeout(P.timer);
  P.timer = setTimeout(poseFire, delay);
}
async function poseFire() {
  const P = S.pose; if (!P) return;
  if (P.inflight) { P.again = true; return; }
  P.inflight = true; P.again = false;
  const my = ++P.seq, c = { ...P.cand };
  try {
    const r = await api(`/api/pieces/${P.pid}/pose/avaliar`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ theta_deg: c.theta, dx_mm: c.dx, dy_mm: c.dy }) });
    if (S.pose === P && my === P.seq) { P.res = r; P.err = null; poseRender(); }
  } catch (e) {
    if (S.pose === P && my === P.seq) { P.err = e.message; poseRender(); }
  } finally {
    P.inflight = false;
    if (S.pose === P && P.again) poseSchedule(0);
  }
}

// ------------------------------------------------------------ gravar / repor
function poseBusy(on, label) {
  const P = S.pose; if (!P) return;
  P.busy = on;
  for (const b of $$("button, input", P.panel)) b.disabled = on;
  const sv = $("#pose-save"), rs = $("#pose-reset");
  if (sv) sv.textContent = on && label === "save" ? "a gravar…" : "Gravar";
  if (rs) rs.textContent = on && label === "reset" ? "a repor…" : "Repor automática";
}
function poseJuntasTxt(j) {
  if (!j) return "";
  return ["N", "E", "S", "W"].filter((k) => j[k] && j[k].gap_mm !== null && j[k].gap_mm !== undefined)
    .map((k) => `${k} ${fmt(j[k].gap_mm, 2)}`).join(" · ");
}
async function poseSave() {
  const P = S.pose; if (!P || P.busy) return;
  if (!poseIsDirty(P) && !confirm("A pose não mudou. Gravar na mesma como pose manual?")) return;
  clearTimeout(P.timer);
  poseBusy(true, "save");
  const t0 = performance.now();
  try {
    const c = P.cand;
    const r = await api(`/api/pieces/${P.pid}/pose`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ theta_deg: c.theta, dx_mm: c.dx, dy_mm: c.dy, nota: P.nota || undefined }) });
    const cell = P.d.cell;
    poseClose();
    toast(`pose gravada em ${fmt(r.segundos !== undefined ? r.segundos : (performance.now() - t0) / 1000, 1)} s · juntas ${poseJuntasTxt(r.juntas)} mm`);
    if (r.invariantes && r.invariantes.length) toast("INVARIANTES: " + r.invariantes.join("; "), true);
    if (S.tab === "celula") openCell(cell[0], cell[1], { zoom: false, keep: true });   // the chip first, the raster follows
    await loadAll();
  } catch (e) {
    toast(e.message, true);
    poseBusy(false);
  }
}
async function poseReset() {
  const P = S.pose; if (!P || P.busy) return;
  if (!confirm(`Repor a pose automática de ${P.pid}? A pose manual é apagada.`)) return;
  poseBusy(true, "reset");
  try {
    const r = await api(`/api/pieces/${P.pid}/pose/repor`, { method: "POST" });
    const cell = P.d.cell;
    poseClose();
    toast(`pose automática reposta em ${fmt(r.segundos, 1)} s · juntas ${poseJuntasTxt(r.juntas)} mm`);
    if (S.tab === "celula") openCell(cell[0], cell[1], { zoom: false, keep: true });
    await loadAll();
  } catch (e) {
    toast(e.message, true);
    poseBusy(false);
  }
}
