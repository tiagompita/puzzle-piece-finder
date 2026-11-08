/* Painel «Atividade» (docs/gui-design.md §23): as últimas linhas do registo do servidor (src/activity.py) em tempo real
 * (SSE `atividade`), com filtro por tipo e por nível e o carimbo de tempo. Não é uma aba: é uma gaveta fixa no fundo do
 * ecrã, aberta por um botão na barra de ferramentas; fechada não ocupa espaço (display: none). Só leitura. A gaveta tem um
 * segundo separador, «Fila de importação» (queue.js).
 * Usa globais de app.js ($, $$, h, api, lsGet, lsSet).
 */
"use strict";

const ACT_MAX = 300;
const ACT_NIVEL_TXT = { info: "info", aviso: "aviso", erro: "erro" };
const A = { open: false, lines: [], tipos: null, niveis: new Set(["info", "aviso", "erro"]), seq: 0, tiposAll: [], stick: true };

function actTime(t) { return t ? String(t).slice(11, 19) : ""; }
function actVisible(rec) {
  if (!A.niveis.has(rec.nivel)) return false;
  if (A.tipos && !A.tipos.has(rec.tipo)) return false;
  return true;
}
function actLine(rec) {
  return h("li", { class: `act-line ${rec.nivel}`, "data-tipo": rec.tipo, "data-nivel": rec.nivel, "data-seq": rec.seq },
    h("span", { class: "act-t" }, actTime(rec.t)), h("span", { class: `act-n ${rec.nivel}` }, ACT_NIVEL_TXT[rec.nivel] || rec.nivel),
    h("span", { class: "act-k" }, rec.tipo), h("span", { class: "act-m" }, rec.msg));
}
function actRender() {
  const ol = $("#act-lines");
  if (!ol) return;
  ol.replaceChildren(...A.lines.filter(actVisible).map(actLine));
  const n = $("#act-count");
  if (n) n.textContent = `${A.lines.filter(actVisible).length} de ${A.lines.length}`;
  if (A.stick) ol.scrollTop = ol.scrollHeight;
}
function actPush(rec) {
  if (!rec || typeof rec.seq !== "number") return;
  if (rec.seq <= A.seq) return;
  A.seq = rec.seq;
  A.lines.push(rec);
  if (A.lines.length > ACT_MAX) A.lines.splice(0, A.lines.length - ACT_MAX);
  if (!A.tiposAll.includes(rec.tipo)) { A.tiposAll.push(rec.tipo); actRenderFilters(); }
  if (rec.nivel !== "info") for (const btn of $$("[data-act-toggle]")) btn.classList.add(rec.nivel === "erro" ? "err" : "warn");
  if (!A.open) return;
  const ol = $("#act-lines");
  if (ol && actVisible(rec)) {
    ol.append(actLine(rec));
    if (A.stick) ol.scrollTop = ol.scrollHeight;
    const n = $("#act-count");
    if (n) n.textContent = `${ol.children.length} de ${A.lines.length}`;
  }
}
/** SSE `atividade` (app.js connectEvents chama isto). */
function actOnLine(d) { actPush(d); }
function actRenderFilters() {
  const box = $("#act-filters");
  if (!box) return;
  box.replaceChildren();
  for (const t of A.tiposAll) {
    const on = !A.tipos || A.tipos.has(t);
    box.append(h("button", { type: "button", class: "fchip act-f", "aria-pressed": on ? "true" : "false", "data-tipo": t,
      onclick: () => { A.tipos = A.tipos || new Set(A.tiposAll); if (A.tipos.has(t)) A.tipos.delete(t); else A.tipos.add(t); if (A.tipos.size === A.tiposAll.length) A.tipos = null; actRenderFilters(); actRender(); } }, t));
  }
  for (const n of ["info", "aviso", "erro"]) {
    box.append(h("button", { type: "button", class: `fchip act-f act-nv ${n}`, "aria-pressed": A.niveis.has(n) ? "true" : "false", "data-nivel": n,
      onclick: () => { if (A.niveis.has(n)) A.niveis.delete(n); else A.niveis.add(n); actRenderFilters(); actRender(); } }, n));
  }
}
async function actLoad() {
  const d = await api(`/api/atividade?n=${ACT_MAX}`);
  A.tiposAll = [...new Set([...(d.tipos || []), ...(d.linhas || []).map((r) => r.tipo)])];
  A.lines = (d.linhas || []).slice(-ACT_MAX);
  A.seq = Math.max(A.seq, ...A.lines.map((r) => r.seq), 0);
  const f = $("#act-file");
  if (f) f.textContent = d.ficheiro ? `ficheiro: ${d.ficheiro}` : "sem ficheiro (servidor sem registo em disco)";
  actRenderFilters();
  actRender();
}
function actSetOpen(on) {
  A.open = !!on;
  const box = $("#atividade");
  if (!box) return;
  box.hidden = !A.open;
  for (const btn of $$("[data-act-toggle]")) { btn.setAttribute("aria-pressed", A.open ? "true" : "false"); if (A.open) btn.classList.remove("warn", "err"); }
  lsSet("atividade-open", A.open ? "1" : "0");
  if (A.open) actLoad().catch((e) => { const ol = $("#act-lines"); if (ol) ol.replaceChildren(h("li", { class: "act-line erro" }, e.message)); });
  if (A.open && typeof queueOnOpen === "function") queueOnOpen();
}
function initActivity() {
  const btns = $$("[data-act-toggle]");
  if (!btns.length) return;
  for (const btn of btns) btn.onclick = () => actSetOpen(!A.open);
  const box = $("#atividade");
  $("#act-close").onclick = () => actSetOpen(false);
  $("#act-clear").onclick = () => { A.lines = []; actRender(); };
  const ol = $("#act-lines");
  ol.addEventListener("scroll", () => { A.stick = ol.scrollTop + ol.clientHeight >= ol.scrollHeight - 8; });
  box.hidden = true;
  if (lsGet("atividade-open") === "1") actSetOpen(true);
}
