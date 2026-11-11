/* GUI nova (redesenho, ESPEC §4.1–§4.3; fase F1b): casca nova + ecrã «Montar» em /novo/ (a antiga continua em /).
 * Uma pergunta: «que peça vou buscar agora e onde a ponho?». A fila, a confiança («quase certo» / «a confirmar por ti»)
 * e os traços do «Porquê» vêm do servidor (GET /api/montar, src/montar.py); aqui só a ordem da sessão («Saltar»), o
 * desfazer da última ação e o desenho. Os textos não mostram (l, c), P####, mm, margem nem ΔE (ESPEC §2, §6); os
 * números ficam no Diagnóstico (a interface completa, em /).
 * Usa core.js e board.js; define a interface de board.js (S.board, S.showGrid, S.showGhost, S.pose, S.onBoardTap).
 */
"use strict";

const S = {
  // interface de board.js (cabeçalho de board.js)
  board: null, showGrid: true, showGhost: lsGet("novo-fantasmas") === "1", pose: null,
  rows: 47, cols: 64, hr: 1, ppc: 60, ver: 0, vb: { x: 0, y: 0, w: 64, h: 47 }, detailKey: null,
  // casca nova
  ghosts: [], montar: null, erro: null, tab: "montar", modo: "cartao", pick: null, ultimo: null, undo: null, busy: false,
  showBorda: lsGet("novo-borda") === "1", showGuardadas: lsGet("novo-guardadas") === "1", lots: null, importando: null,
};

// ------------------------------------------------------------ sessão: saco atual e «Saltar» (§8.2: só nesta sessão)
function ssGet(k, d) { try { const v = sessionStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } }
function ssSet(k, v) { try { sessionStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* sem armazenamento: só em memória */ } }
const sess = { saltos: ssGet("novo-saltos", {}), saco: ssGet("novo-saco", null), scan: ssGet("novo-scan", null) };
function saveSess() { ssSet("novo-saltos", sess.saltos); ssSet("novo-saco", sess.saco); ssSet("novo-scan", sess.scan); }

// ------------------------------------------------------------ palavras
const CONF_TXT = { quase_certo: "quase certo", a_confirmar: "a confirmar por ti" };
const CONF_LONG = { quase_certo: "O programa tem quase a certeza", a_confirmar: "A confirmar por ti" };
const lugarTxt = (cell) => (cell ? `Linha ${cell[0]} · coluna ${cell[1]}` : "sem lugar");
const quem = (it) => (it.lote !== null && it.lote !== undefined ? `Saco ${it.lote} · nº ${it.n_no_lote ?? "?"}` : "Peça sem saco");

// ------------------------------------------------------------ fila com os saltos da sessão
function queue() {
  const m = S.montar;
  if (!m) return [];
  const order = (m.ordem_sacos || []).map(String);
  const bagIx = (it) => { const i = order.indexOf(String(it.lote)); return i < 0 ? order.length : i; };
  return m.itens.map((it, i) => ({ it, i, n: sess.saltos[it.piece] || 0 }))
    .sort((a, b) => ((a.n >= 2) - (b.n >= 2)) || (bagIx(a.it) - bagIx(b.it)) || ((a.n >= 1) - (b.n >= 1)) || (a.i - b.i))
    .map((x) => x.it);
}
function current() {
  const q = queue();
  if (S.pick) { const p = q.find((it) => it.piece === S.pick); if (p) return p; S.pick = null; }
  return q[0] || null;
}

// ------------------------------------------------------------ dados
async function loadBoard() {
  const [b, gh] = await Promise.all([api("/api/board?ui=novo"), api("/api/ghosts").catch(() => ({ fantasmas: [] }))]);
  S.board = b; S.ghosts = gh.fantasmas || [];
  const first = !svg().getAttribute("viewBox");
  drawRaster(); drawGrid(); drawLayers(); drawLegend();
  if (first) fitBoard(); else setView(S.vb);
}
async function loadMontar() {
  // o saco que o browser está a esgotar fica fixo; um scan novo importado manda para o saco dele (§8.2)
  const q = sess.saco !== null && sess.saco !== undefined ? `?saco=${encodeURIComponent(sess.saco)}` : "";
  try {
    let m = await api("/api/montar" + q);
    if (sess.scan !== null && m.ultimo_scan && m.ultimo_scan !== sess.scan && q) m = await api("/api/montar");
    S.montar = m; S.erro = null;
    sess.scan = m.ultimo_scan; sess.saco = m.saco;
    saveSess();
  } catch (e) {
    S.erro = e.message;
  }
  drawProgress();
  renderMontar();
}
async function loadAll() { await loadBoard(); await loadMontar(); }

// ------------------------------------------------------------ topo
function drawProgress() {
  const m = S.montar;
  if (!m) return;
  $("#puzzle-name").textContent = m.puzzle || "Puzzle";
  document.title = `Montar · ${m.puzzle || ""}`;
  const n = m.progresso.n, t = m.total_celulas;
  $("#progress-txt").textContent = `${n} de ${t} peças`;
  $("#pb-n").style.width = `${(100 * n / Math.max(1, t)).toFixed(2)}%`;
  $("#n-montar").textContent = m.total ? String(m.total) : "";
}

// ------------------------------------------------------------ tabuleiro (camadas da casca nova)
function drawLayers() {
  const b = S.board; if (!b) return;
  const leg = $("#lyr-legado"); leg.replaceChildren();
  b.cells.forEach((row, i) => row.forEach((cell, j) => {
    if (cell.estado === "ocupada_legado") leg.append(rectEl(i + 1, j + 1, cls("legado"), 0));
  }));
  const bor = $("#lyr-borda"); bor.replaceChildren();
  if (S.showBorda) for (const [l, c] of b.borda_em_falta) bor.append(rectEl(l, c, cls("borda"), 0.05));
  const kn = $("#lyr-conhecida"); kn.replaceChildren();
  if (S.showGuardadas) for (const k of b.posicoes_conhecidas) kn.append(rectEl(k.cell[0], k.cell[1], cls("conhecida"), 0.07));
  const g = $("#lyr-fantasma"); g.replaceChildren();
  for (const gh of S.ghosts) g.append(s("path", { d: ghostPath(gh.path, gh.cell[1] - 0.5, (gh.cell[0] - 0.5) * S.hr), class: cls("fantasma") }));
  drawTarget(false);
}
function drawTarget(move = true) {
  const a = $("#lyr-alvo"), nx = $("#lyr-seguinte");
  a.replaceChildren(); nx.replaceChildren();
  if (!S.board || S.tab !== "montar") return;
  const q = queue(), cur = current();
  if (!cur || !cur.cell) return;
  for (const it of q.filter((x) => x !== cur).slice(0, 3)) if (it.cell) nx.append(rectEl(it.cell[0], it.cell[1], cls("seguinte"), 0.06));
  const [l, c] = cur.cell;
  a.append(rectEl(l, c, cls("alvo"), 0.02));
  const x = c - 0.5, y = (l - 1) * S.hr - 0.12;
  const lab = s("g", { class: "alvo-tag", transform: `translate(${x} ${y})` });
  lab.append(s("rect", { x: -0.62, y: -0.42, width: 1.24, height: 0.36, rx: 0.08 }), s("text", { x: 0, y: -0.17 }, document.createTextNode("vai aqui")));
  a.append(lab);
  if (move) showCell(l, c);
}
/** Desloca o tabuleiro até ao lugar, com contexto à volta (só se não estiver já bem à vista). */
function showCell(l, c) {
  const x = c - 0.5, y = (l - 0.5) * S.hr;
  const v = S.vb, mx = v.w * 0.12, my = v.h * 0.12;
  const inside = x > v.x + mx && x < v.x + v.w - mx && y > v.y + my && y < v.y + v.h - my;
  if (inside && v.w <= 30) return;
  zoomCells(Math.max(1, l - 5), Math.max(1, c - 8), Math.min(S.rows, l + 5), Math.min(S.cols, c + 8), 0.04);
}
function drawLegend() {
  const L = $("#legend"); L.replaceChildren();
  for (const row of (S.board ? S.board.legend : []).filter((r) => r.curta)) {
    const sw = s("svg", { class: "lg-sw", viewBox: "0 0 1 1", "aria-hidden": "true" });
    if (row.classe) sw.append(s("rect", { x: 0.1, y: 0.1, width: 0.8, height: 0.8, class: row.classe }));
    else sw.append(s("rect", { x: 0.1, y: 0.1, width: 0.8, height: 0.8, class: "lg-raster" }));
    L.append(h("span", { class: "lg", "data-legend": row.id, title: row.detalhe }, sw, row.rotulo));
  }
}
S.onBoardTap = (l, c) => {
  // F1b: tocar no lugar de uma peça da fila torna-a a peça atual (o painel da célula / lugar vazio vem na F2)
  const it = queue().find((x) => x.cell && x.cell[0] === l && x.cell[1] === c);
  if (it) { S.pick = it.piece; S.modo = "cartao"; renderMontar(); }
};

// ------------------------------------------------------------ Montar
function bars(n, label) {
  const b = h("span", { class: "bars" + (n === 0 ? " vazio" : ""), "data-tracos": n, "aria-label": label || `${n} de 3` });
  for (let i = 1; i <= 3; i++) b.append(h("i", { class: i <= n ? "on" : "" }));
  return b;
}
const passes = (it) => (it.tracos || []).filter((t) => t.tracos >= 2).length;
function pieceImg(it, size = 220) {
  const pose = it.pose_known ? "board" : "scan";
  const box = h("button", { type: "button", class: "pimg", "aria-label": "Ver a peça na folha", onclick: () => openSheet(it) },
    h("img", { src: `/api/pieces/${it.piece}.png?pose=${pose}&size=${size * 2}&v=${S.ver}`, alt: `${quem(it)}` }));
  return box;
}
function openSheet(it) {
  if (!it.scan_id) return;
  lightbox(`/api/sheets/${it.scan_id}.jpg?highlight=${it.piece}&max=1400&v=${S.ver}`,
    `Folha do saco ${it.lote ?? "—"}: a peça nº ${it.n_no_lote ?? "?"} está marcada a âmbar`);
}
function renderMontar() {
  const T = $("#tab-montar");
  T.replaceChildren();
  if (S.erro && !S.montar) {
    T.append(h("div", { class: "empty", "data-estado": "erro" }, h("strong", {}, "Não consegui ler as sugestões."), h("p", {}, S.erro),
      h("button", { class: "btn", type: "button", onclick: () => loadMontar() }, "Tentar de novo")));
    return;
  }
  const m = S.montar;
  if (!m) { T.append(h("div", { class: "empty", "data-estado": "a_carregar" }, h("strong", {}, "A carregar…"))); return; }
  const q = queue(), cur = current();
  if (S.modo === "nao" && S.undo && S.undo.tipo === "nao") { renderNao(T); drawTarget(false); return; }
  if (!cur) {
    T.append(h("div", { class: "empty", "data-estado": "vazio" }, h("strong", {}, "Nada para ir buscar."), h("p", {}, "Digitaliza mais um saco."),
      h("button", { class: "btn primary", type: "button", onclick: () => showTab("importar") }, "Importar scan")));
    if (m.a_preparar && m.a_preparar.buracos) T.append(prepLine(m));
    if (m.em_pausa) T.append(pauseLine());
    drawTarget(false);
    return;
  }
  if (S.modo === "porque") { renderPorque(T, cur); drawTarget(); return; }
  const inBag = q.filter((it) => String(it.lote) === String(cur.lote));
  const k = inBag.indexOf(cur) + 1;
  const card = h("div", { class: "card", "data-piece": cur.piece, "data-tipo": cur.tipo, "data-confianca": cur.confianca });
  card.append(h("div", { class: "card-head" }, h("span", { class: "kicker" }, "Próxima peça"),
    h("span", { class: "count", id: "m-count" }, `${k} de ${inBag.length} neste saco · ${q.length} no total`)));
  const who = h("div", { class: "who" },
    h("div", { class: "bag" }, cur.lote !== null && cur.lote !== undefined ? `Saco ${cur.lote}` : "Peça sem saco"),
    h("div", { class: "num" }, `peça nº ${cur.n_no_lote ?? "?"}`),
    h("div", { class: "where" }, lugarTxt(cur.cell)),
    cur.pose_known ? null : h("div", { class: "small muted" }, "rotação por confirmar"),
    h("div", { class: "pid" }, cur.piece));
  card.append(h("div", { class: "card-top" }, pieceImg(cur), who));
  card.append(h("div", { class: "conf", "data-conf": cur.confianca }, bars(passes(cur)), h("span", {}, CONF_LONG[cur.confianca])));
  const acts = h("div", { class: "actions" });
  acts.append(h("button", { class: "btn primary big", type: "button", id: "b-encaixa", onclick: () => doEncaixa(cur) }, "Encaixa"));
  if (cur.nao_encaixa) acts.append(h("button", { class: "btn big", type: "button", id: "b-nao", onclick: () => doNao(cur) }, "Não encaixa"));
  card.append(acts);
  card.append(h("div", { class: "links" },
    h("button", { class: "linkish", type: "button", id: "b-saltar", onclick: () => doSaltar(cur) }, "Saltar por agora"),
    h("button", { class: "linkish", type: "button", id: "b-porque", onclick: () => { S.modo = "porque"; renderMontar(); } }, "Porquê esta peça?")));
  T.append(card);
  const nxt = q.filter((x) => x !== cur).slice(0, 3);
  if (nxt.length) {
    const same = nxt.every((x) => String(x.lote) === String(cur.lote));
    T.append(h("h2", {}, same ? "A seguir, do mesmo saco" : "A seguir, primeiro as do mesmo saco"));
    const ul = h("ul", { class: "next", id: "m-seguir" });
    for (const it of nxt) ul.append(h("li", {}, h("button", { type: "button", class: "next-row", onclick: () => { S.pick = it.piece; renderMontar(); } },
      h("span", {}, quem(it)), h("span", { class: "w " + it.confianca }, CONF_TXT[it.confianca]))));
    T.append(ul);
  }
  if (m.a_preparar && m.a_preparar.buracos) T.append(prepLine(m));
  if (m.em_pausa) T.append(pauseLine());
  drawTarget();
}
function prepLine(m) {
  const p = S.holesProgress || (m.a_preparar && m.a_preparar.progresso);
  return h("p", { class: "small muted prep-line", id: "m-prep" }, "A preparar mais sugestões…" + (p && p.N ? ` ${p.n} de ${p.N}` : ""));
}
function pauseLine() {
  return h("p", { class: "small muted", id: "m-pausa" }, "Algumas sugestões estão em pausa. ", h("a", { href: "/" }, "Ver no Diagnóstico"));
}
function renderPorque(T, it) {
  T.append(h("div", { class: "card porque", "data-piece": it.piece },
    h("h3", {}, "Porquê esta peça?"),
    h("div", { class: "small muted" }, `${quem(it)} · ${lugarTxt(it.cell)}`),
    h("ul", { class: "why", id: "m-porque" }, (it.tracos || []).map((t) => h("li", { "data-chave": t.chave, "data-estado": t.estado },
      bars(t.tracos, t.estado === "nao_testado" ? "não verificado" : `${t.tracos} de 3`),
      h("span", {}, t.frase), t.estado === "nao_testado" ? h("em", { class: "nv" }, "não verificado") : null))),
    h("details", { class: "numeros" }, h("summary", {}, "Ver números"),
      h("p", { class: "small muted" }, "Os números ficam no diagnóstico."),
      h("ul", { class: "small" }, (it.reasons || []).map((r) => h("li", {}, r)))),
    h("div", { class: "actions" }, h("button", { class: "btn", type: "button", onclick: () => { S.modo = "cartao"; renderMontar(); } }, "Voltar"))));
}
function renderNao(T) {
  const u = S.undo, it = u.item;
  const box = h("div", { class: "card nao", "data-piece": it.piece },
    h("h3", {}, "Não encaixou"),
    h("div", { class: "small muted" }, `Saco ${it.lote ?? "—"} · peça nº ${it.n_no_lote ?? "?"} · linha ${it.cell[0]}, coluna ${it.cell[1]}`),
    h("p", {}, "Porquê? ", h("span", { class: "muted" }, "Podes saltar")));
  const opts = h("div", { class: "motivos", id: "m-motivos" });
  for (const [k, t] of [["forma", "A forma não entra"], ["imagem", "Entra, mas a imagem não bate"], ["nao_sei", "Não sei"]]) {
    opts.append(h("button", { class: "btn" + (u.motivo === k ? " on" : ""), type: "button", "data-motivo": k, onclick: () => doMotivo(k) }, t));
  }
  box.append(opts);
  box.append(h("div", { class: "actions" }, h("button", { class: "btn primary big", type: "button", id: "b-proxima", onclick: () => { S.modo = "cartao"; renderMontar(); } }, "Próxima peça")));
  box.append(h("div", { class: "links" }, h("button", { class: "linkish", type: "button", id: "b-desfazer", onclick: () => doUndo() }, "Enganei-me, desfazer")));
  T.append(box);
}

// ------------------------------------------------------------ ações
async function post(url, body) {
  return api(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}
function lockButtons(on) { S.busy = on; $$("#tab-montar button").forEach((b) => { b.disabled = on; }); }
async function afterWrite() { await Promise.all([loadBoard(), loadMontar()]); }
function writeFailed(r) {
  if (r && r.invariantes && r.invariantes.length) toast("Algo correu mal ao gravar (ver Diagnóstico).", true);
}
async function doEncaixa(it) {
  if (S.busy || !it || !it.encaixa) return;
  lockButtons(true);
  try {
    const r = await post(it.encaixa.url, it.encaixa.body);
    writeFailed(r);
    S.undo = { tipo: "encaixa", item: it };
    S.pick = null; S.modo = "cartao";
    toastUndo(`${quem(it)} no lugar.`);
    await afterWrite();
  } catch (e) { toast(e.message, true); } finally { lockButtons(false); }
}
async function doNao(it) {
  if (S.busy || !it || !it.nao_encaixa) return;
  lockButtons(true);
  try {
    const r = await post(it.nao_encaixa.url, it.nao_encaixa.body);
    writeFailed(r);
    const rej = (r.escritos || []).filter((e) => ["twin_rejected", "hole_rejected", "pair_rejected"].includes(e.action))
      .map((e) => (e.action === "pair_rejected" ? { pair: e.pair, t: e.t } : { piece: e.piece, cell: e.cell, origin: e.origin, t: e.t }));
    S.undo = { tipo: "nao", item: it, rejeicoes: rej, motivo: null };
    S.pick = null; S.modo = "nao";
    await afterWrite();
  } catch (e) { toast(e.message, true); } finally { lockButtons(false); }
}
async function doMotivo(k) {
  const u = S.undo;
  if (!u || u.tipo !== "nao" || !u.rejeicoes.length) { S.modo = "cartao"; renderMontar(); return; }
  try {
    await post("/api/confirm", { acao: "reject_reason", motivo: k, rejeicoes: u.rejeicoes });
    u.motivo = k;
    toast("Obrigado. Fica registado.");
  } catch (e) { toast(e.message, true); }
  S.modo = "cartao"; renderMontar();
}
function doSaltar(it) {
  if (!it) return;
  sess.saltos[it.piece] = (sess.saltos[it.piece] || 0) + 1;
  saveSess();
  S.pick = null; S.modo = "cartao";
  renderMontar();
}
async function doUndo() {
  const u = S.undo;
  if (!u || S.busy) return;
  lockButtons(true);
  try {
    if (u.tipo === "encaixa") await post("/api/confirm", { acao: "unplace", piece: u.item.piece, desfaz: true });
    else if (u.tipo === "nao" && u.rejeicoes.length) await post("/api/confirm", { acao: "undo_reject", rejeicoes: u.rejeicoes });
    S.undo = null; S.modo = "cartao"; S.pick = u.item.piece;
    toast(`Desfeito: ${quem(u.item)}.`);
    await afterWrite();
  } catch (e) { toast(e.message, true); } finally { lockButtons(false); }
}
function toastUndo(msg) {
  const el = h("div", { class: "undo-toast" }, h("span", {}, msg),
    h("button", { type: "button", class: "linkish", onclick: () => { el.remove(); doUndo(); } }, "Desfazer"));
  $("#toast").append(el);
  setTimeout(() => el.remove(), 9000);
}

// ------------------------------------------------------------ separadores
function showTab(t) {
  S.tab = t;
  $$("#tabs button").forEach((b) => { const on = b.dataset.tab === t; b.classList.toggle("on", on); b.setAttribute("aria-selected", on ? "true" : "false"); });
  $$("#panel .tab").forEach((x) => x.classList.toggle("on", x.id === `tab-${t}`));
  if (t === "importar") renderImportar();
  if (t === "pecas") renderPecas();
  drawTarget(false);
}
function renderPecas() {
  const T = $("#tab-pecas"); T.replaceChildren(
    h("div", { class: "empty" }, h("strong", {}, "Peças chega na próxima fase."),
      h("p", {}, "Por agora, os sacos e as peças estão na interface completa."),
      h("a", { class: "btn", href: "/" }, "Abrir a interface completa")));
}
async function renderImportar() {
  const T = $("#tab-importar");
  if (T.dataset.built) { importStatus(); return; }
  T.dataset.built = "1";
  let next = 1;
  try { const lots = await api("/api/lots"); next = 1 + Math.max(0, ...lots.map((x) => Number(x.lote) || 0)); } catch (e) { /* fica 1 */ }
  const form = h("form", { class: "form", id: "import-form" },
    h("ol", { class: "steps" },
      h("li", {}, h("label", {}, "Escolhe o scan do saco (imagem ou PDF; várias folhas podem ir juntas)",
        h("input", { type: "file", name: "files", accept: ".pdf,application/pdf,image/*", multiple: true, required: true }))),
      h("li", {}, h("label", {}, "Número do saco", h("input", { type: "number", name: "lote", min: 1, step: 1, value: next, required: true }))),
      h("li", {}, h("button", { class: "btn primary big", type: "submit", id: "import-btn" }, "Importar"))));
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const fd = new FormData(form);
    $("#import-btn").disabled = true;
    try {
      const r = await api("/api/ingest", { method: "POST", body: fd });
      S.importando = { lote: Number(fd.get("lote")), msg: null };
      toast(`Saco ${fd.get("lote")} na fila (${r.folhas} folha${r.folhas === 1 ? "" : "s"}).`);
      form.reset();
      importStatus();
    } catch (e) { toast(e.message, true); } finally { $("#import-btn").disabled = false; }
  });
  T.append(h("h2", {}, "Importar scan"), form,
    h("p", { class: "chip-line", id: "import-chip", hidden: true }),
    h("ul", { class: "rules" },
      h("li", {}, h("span", { class: "rule-ico verde", "aria-hidden": "true" }), "Peças sobre papel verde"),
      h("li", {}, h("span", { class: "rule-ico afastadas", "aria-hidden": "true" }), "Peças afastadas umas das outras"),
      h("li", {}, h("span", { class: "rule-ico dpi", "aria-hidden": "true" }), "Scanner a 300 dpi")));
  importStatus();
}
function importStatus() {
  const c = $("#import-chip");
  if (!c) return;
  if (S.importando) { c.hidden = false; c.textContent = S.importando.msg || `a importar saco ${S.importando.lote}…`; }
  else c.hidden = true;
}

// ------------------------------------------------------------ procurar peça ou lugar (T10)
async function onSearch(txt) {
  const t = String(txt || "").trim().toLowerCase();
  if (!t) return;
  let m;
  if ((m = t.match(/^p\s*0*(\d{1,4})$/))) return findPiece(`P${m[1].padStart(4, "0")}`);
  if ((m = t.match(/^(?:linha\s*)?(\d{1,2})\s*(?:,|\s+coluna\s*)\s*(\d{1,2})$/))) return findPlace(Number(m[1]), Number(m[2]));
  if ((m = t.match(/^(?:saco\s*)?(\d{1,3})\s*(?:\s|\/|\s*n[º°o.]?\s*)\s*(\d{1,3})$/))) return findBagNumber(Number(m[1]), Number(m[2]));
  toast(`Não encontrei «${txt}». Escreve o saco e o nº, ou a linha e a coluna.`);
}
async function findBagNumber(lote, n) {
  if (!S.lots) S.lots = await api("/api/lots");
  const L = S.lots.find((x) => Number(x.lote) === lote);
  const p = L && L.pecas.find((x) => Number(x.n_no_lote) === n);
  if (!p) { toast(`Não encontrei o nº ${n} no saco ${lote}.`); return; }
  return findPiece(p.id);
}
async function findPiece(pid) {
  const inQ = queue().find((it) => it.piece === pid);
  if (inQ) { S.pick = pid; S.modo = "cartao"; showTab("montar"); renderMontar(); toast(`${quem(inQ)} está na fila.`); return; }
  let p;
  try { p = await api(`/api/pieces/${pid}`); } catch (e) { toast(`Não encontrei «${pid}».`); return; }
  const pc = p.peca || p;
  const nome = pc.lote !== null && pc.lote !== undefined ? `Saco ${pc.lote} · nº ${pc.n_no_lote ?? "?"}` : "Esta peça";
  if (pc.celula) { showCell(pc.celula[0], pc.celula[1]); toast(`${nome} está no lugar: ${lugarTxt(pc.celula).toLowerCase()}.`); }
  else toast(`${nome} ainda não tem lugar.`);
}
async function findPlace(l, c) {
  if (!S.board || l < 1 || c < 1 || l > S.rows || c > S.cols) { toast(`Linha ${l} · coluna ${c} fica fora do tabuleiro.`); return; }
  showCell(l, c);
  try {
    const d = await api(`/api/cell/${l}/${c}`);
    const pc = d.peca;
    toast(pc ? `${lugarTxt([l, c])}: tem a peça do saco ${pc.lote ?? "—"} · nº ${pc.n_no_lote ?? "?"}.` : `${lugarTxt([l, c])}: ainda vazio.`);
  } catch (e) { toast(e.message, true); }
}

// ------------------------------------------------------------ eventos do servidor
let reloadTimer = null;
function scheduleReload(board) {
  scheduleReload.board = scheduleReload.board || board;
  clearTimeout(reloadTimer);
  reloadTimer = setTimeout(async () => {
    const b = scheduleReload.board; scheduleReload.board = false;
    try { if (b) await loadBoard(); await loadMontar(); } catch (e) { /* o próximo evento tenta de novo */ }
  }, 350);
}
function connectEvents() {
  const es = new EventSource("/api/events");
  es.addEventListener("board_changed", (e) => { const d = JSON.parse(e.data); if (d.versao !== S.ver) scheduleReload(true); });
  es.addEventListener("fetch_changed", () => scheduleReload(false));
  es.addEventListener("holes_changed", () => { S.holesProgress = null; scheduleReload(false); });
  es.addEventListener("holes_progress", (e) => {
    S.holesProgress = JSON.parse(e.data);
    const el = $("#m-prep"); if (el && S.holesProgress.N) el.textContent = `A preparar mais sugestões… ${S.holesProgress.n} de ${S.holesProgress.N}`;
  });
  es.addEventListener("ingest_progress", (e) => {
    const d = JSON.parse(e.data);
    if (d.fim) { S.importando = null; toast(d.etapa === "erro" ? "A importação falhou (ver Diagnóstico)." : "Importação acabada.", d.etapa === "erro"); }
    else if (S.importando) S.importando.msg = `a importar saco ${S.importando.lote}…`;
    importStatus();
  });
  es.addEventListener("ready", () => { if (document.body.dataset.ready !== "1") boot2(); });
  return es;
}

// ------------------------------------------------------------ arranque
function initMenu() {
  const btn = $("#menu-btn"), menu = $("#menu");
  const close = () => { menu.hidden = true; btn.setAttribute("aria-expanded", "false"); };
  btn.onclick = (e) => { e.stopPropagation(); menu.hidden = !menu.hidden; btn.setAttribute("aria-expanded", menu.hidden ? "false" : "true"); };
  document.addEventListener("click", (e) => { if (!menu.hidden && !menu.contains(e.target)) close(); });
  $("#m-atividade").onclick = () => { lsSet("atividade-open", "1"); window.open("/", "_blank"); close(); };
  const bind = (id, key, prop, after) => {
    const el = $(id); el.checked = !!S[prop];
    el.onchange = () => { S[prop] = el.checked; lsSet(key, el.checked ? "1" : "0"); after(); };
  };
  bind("#m-fantasmas", "novo-fantasmas", "showGhost", () => setView(S.vb));
  bind("#m-borda", "novo-borda", "showBorda", drawLayers);
  bind("#m-guardadas", "novo-guardadas", "showGuardadas", drawLayers);
}
function onKey(e) {
  if (e.key === "Escape") { if (!$("#lightbox").hidden) { $("#lightbox").hidden = true; return; } if (S.modo !== "cartao") { S.modo = "cartao"; renderMontar(); } return; }
  const tag = (e.target && e.target.tagName) || "";
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
  if ((e.ctrlKey || e.metaKey) && (e.key === "z" || e.key === "Z")) { e.preventDefault(); doUndo(); return; }
  if (S.tab !== "montar" || e.ctrlKey || e.metaKey || e.altKey) return;
  const cur = current();
  if (S.modo === "cartao") {
    if (e.key === "Enter" && tag !== "BUTTON" && tag !== "A") { e.preventDefault(); doEncaixa(cur); }
    else if (e.key === "n" || e.key === "N") { e.preventDefault(); doNao(cur); }
    else if (e.key === "s" || e.key === "S") { e.preventDefault(); doSaltar(cur); }
  } else if (S.modo === "nao" && e.key === "Enter" && tag !== "BUTTON") { S.modo = "cartao"; renderMontar(); }
}
async function boot2() {
  try {
    await loadAll();
    document.body.dataset.ready = "1";
  } catch (e) { S.erro = e.message; renderMontar(); }
}
async function boot() {
  $$("#tabs button").forEach((b) => (b.onclick = () => showTab(b.dataset.tab)));
  $("#search").addEventListener("submit", (e) => { e.preventDefault(); onSearch($("#q").value); });
  $("#lb-close").onclick = () => { $("#lightbox").hidden = true; };
  $("#lightbox").addEventListener("click", (e) => { if (e.target.id === "lightbox" || e.target.classList.contains("lb-body")) $("#lightbox").hidden = true; });
  document.addEventListener("keydown", onKey);
  initMenu();
  initPointer();
  connectEvents();
  renderMontar();
  let st;
  try { st = await api("/api/status"); } catch (e) { S.erro = e.message; renderMontar(); return; }
  if (st.estado !== "pronto") {
    $("#tab-montar").replaceChildren(h("div", { class: "empty", "data-estado": "a_preparar" }, h("strong", {}, "A preparar o programa…"),
      h("p", {}, "Isto só acontece depois de atualizar.")));
    const poll = setInterval(async () => {
      try { const s2 = await api("/api/status"); if (s2.estado === "pronto") { clearInterval(poll); if (document.body.dataset.ready !== "1") boot2(); } } catch (e) { /* a reiniciar */ }
    }, 3000);
    return;
  }
  await boot2();
}
boot();
