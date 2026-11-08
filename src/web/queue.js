/* Fila de importação (docs/gui-design.md §24): o separador «Fila de importação» da gaveta do fundo (#atividade, a mesma
 * do registo de atividade; o separador ativo fica em localStorage), o resumo da fila no separador «Importar» e o texto
 * do #job-pill. Carregamento por GET /api/import_queue, atualização em direto pelo SSE `queue_changed` (app.js
 * connectEvents chama queueOnChanged). Ações: «Cancelar» (em fila), «Repetir» (falhado / cancelado), «▲»/«▼» (mover).
 * Usa globais de app.js ($, $$, h, api, toast, lsGet, lsSet, setJob).
 */
"use strict";

const Q = { jobs: [], resumo: null, job: null, loaded: false, tab: "atividade" };
const Q_ESTADO_TXT = { em_fila: "em fila", a_correr: "a correr", concluido: "concluído", falhado: "falhou", cancelado: "cancelado" };

function qTime(t) { return t ? String(t).slice(11, 16) : ""; }
/** Há um trabalho a correr ou em fila (o botão de gravar diz «a aguardar a importação…»). */
function queueBusy() { return !!(Q.resumo && (Q.resumo.a_correr || Q.resumo.n_em_fila)); }

function queueApply(d) {
  if (!d) return;
  Q.jobs = d.fila || [];
  Q.resumo = d.resumo || null;
  Q.job = d.job || null;
  Q.loaded = true;
  queueRender();
  queueRenderSummary();
  if (typeof setJob === "function") setJob(Q.job);
}
async function queueLoad() {
  const d = await api("/api/import_queue");
  queueApply(d);
  return d;
}
/** SSE `queue_changed` (o snapshot inteiro). */
function queueOnChanged(d) { queueApply(d); }

function queueJobLine(j) {
  const pend = Q.jobs.filter((x) => x.estado === "em_fila");
  const i = pend.findIndex((x) => x.id === j.id);
  const acts = [];
  if (j.estado === "em_fila") {
    acts.push(h("button", { type: "button", class: "btn slim q-up", title: "subir na fila", "aria-label": `subir ${j.id}`, disabled: i <= 0 ? true : null,
      onclick: () => queueAction(j.id, "mover", { posicao: Math.max(0, i - 1) }) }, "▲"));
    acts.push(h("button", { type: "button", class: "btn slim q-down", title: "descer na fila", "aria-label": `descer ${j.id}`, disabled: i >= pend.length - 1 ? true : null,
      onclick: () => queueAction(j.id, "mover", { posicao: i + 1 }) }, "▼"));
    acts.push(h("button", { type: "button", class: "btn slim q-cancel", onclick: () => queueAction(j.id, "cancelar") }, "Cancelar"));
  }
  if (j.estado === "falhado" || j.estado === "cancelado") acts.push(h("button", { type: "button", class: "btn slim q-retry", onclick: () => queueAction(j.id, "repetir") }, "Repetir"));
  const ign = (j.resultados || []).filter((r) => r.estado === "ignorada").length;
  const quando = j.estado === "em_fila" ? `na fila às ${qTime(j.t_adicionado)}` : j.t_fim ? `${qTime(j.t_inicio)}–${qTime(j.t_fim)}` : j.t_inicio ? `desde ${qTime(j.t_inicio)}` : "";
  const li = h("li", { class: `fila-job ${j.estado}`, "data-job": j.id, "data-estado": j.estado },
    h("div", { class: "fila-l1" },
      h("b", {}, j.id), h("span", {}, `saco ${j.lote}`), h("span", { class: `chip q-estado ${j.estado}` }, Q_ESTADO_TXT[j.estado] || j.estado),
      h("span", { class: "q-prog", title: "folhas feitas / total" }, `folhas ${j.progresso}`),
      j.n_pecas ? h("span", {}, `${j.n_pecas} peças`) : null,
      ign ? h("span", { class: "muted" }, `${ign} já importada${ign > 1 ? "s" : ""}`) : null,
      j.propostas !== null && j.propostas !== undefined ? h("span", {}, `${j.propostas} propostas`) : null,
      h("span", { class: "muted small" }, quando),
      acts.length ? h("span", { class: "q-acts" }, ...acts) : null),
    j.erro ? h("div", { class: "q-erro" }, j.erro) : null,
    ...(j.avisos || []).slice(0, 4).map((a) => h("div", { class: "q-aviso" }, a)));
  return li;
}
function queueRender() {
  const ol = $("#fila-jobs");
  if (!ol) return;
  ol.replaceChildren(...(Q.jobs.length ? Q.jobs.map(queueJobLine) : [h("li", { class: "fila-vazia muted" }, "Nenhum trabalho de importação.")]));
  const n = Q.resumo ? (Q.resumo.n_em_fila + (Q.resumo.a_correr ? 1 : 0)) : 0;
  const b = $("#fila-n");
  if (b) b.textContent = n ? String(n) : "";
  const r = $("#fila-resumo");
  if (r) r.textContent = Q.resumo ? (Q.resumo.a_correr ? `a correr: ${Q.resumo.a_correr} · ` : "") + `${Q.resumo.n_em_fila} em fila` : "";
}
/** O resumo da fila no separador «Importar» (#import-queue). */
function queueRenderSummary() {
  const box = $("#import-queue");
  if (!box) return;
  const vis = Q.jobs.filter((j) => j.estado === "a_correr" || j.estado === "em_fila").concat(Q.jobs.filter((j) => !["a_correr", "em_fila"].includes(j.estado)).slice(0, 3));
  box.replaceChildren(h("h3", {}, "Fila de importação"),
    vis.length ? h("ol", { class: "fila-jobs compact" }, ...vis.map(queueJobLine)) : h("p", { class: "muted small" }, "Nenhum trabalho de importação."),
    h("button", { type: "button", class: "linkish", onclick: () => { drawerSetTab("fila"); if (typeof actSetOpen === "function") actSetOpen(true); } }, "ver a fila inteira"));
}
async function queueAction(id, acao, body) {
  try {
    const opts = { method: "POST" };
    if (body) { opts.headers = { "Content-Type": "application/json" }; opts.body = JSON.stringify(body); }
    queueApply(await api(`/api/import_queue/${id}/${acao}`, opts));
  } catch (e) { toast(e.message, true); }
}
/** Separador da gaveta: «atividade» | «fila». */
function drawerSetTab(t) {
  Q.tab = t === "fila" ? "fila" : "atividade";
  const box = $("#atividade");
  if (box) box.dataset.pane = Q.tab;
  for (const b of $$("[data-act-tab]")) b.setAttribute("aria-selected", b.dataset.actTab === Q.tab ? "true" : "false");
  lsSet("gaveta-separador", Q.tab);
  if (Q.tab === "fila" && box && !box.hidden) queueLoad().catch((e) => toast(e.message, true));
}
/** activity.js chama isto ao abrir a gaveta. */
function queueOnOpen() { if (Q.tab === "fila") queueLoad().catch(() => {}); }
function initQueue() {
  for (const b of $$("[data-act-tab]")) b.onclick = () => drawerSetTab(b.dataset.actTab);
  drawerSetTab(lsGet("gaveta-separador") === "fila" ? "fila" : "atividade");
  queueLoad().catch(() => {});
}
