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
  pendente: null,
  // F2: painel do lugar tocado (peça / lugar vazio / marcado por ti) e «Pôr uma peça à mão»
  painel: null, porMao: null,
  // F1d: as peças «por confirmar» (posição conhecida) desenham-se no lugar por omissão; o menu esconde-as
  showBorda: lsGet("novo-borda") === "1", showGuardadas: lsGet("novo-por-confirmar") !== "0", lots: null, importando: null,
};

// ------------------------------------------------------------ ícones (Lucide, ISC; SVG locais em icons/, ver icons/LICENSE-lucide.txt)
// Desenhados por máscara CSS (cor = currentColor); decorativos (aria-hidden): o texto ou o aria-label do botão diz o nome.
const ico = (n) => h("span", { class: `ico i-${n}`, "aria-hidden": "true" });

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
  // cartões sem vizinha montada («Colocar aqui», F1c/F1d) só depois de esgotadas as «coloca agora»; saltada 2 vezes vai para o fim de tudo
  const g = (it) => (it.tipo === "guardar" ? 1 : 0);
  return m.itens.map((it, i) => ({ it, i, n: sess.saltos[it.piece] || 0 }))
    .sort((a, b) => ((a.n >= 2) - (b.n >= 2)) || (g(a.it) - g(b.it)) || (bagIx(a.it) - bagIx(b.it)) || ((a.n >= 1) - (b.n >= 1)) || (a.i - b.i))
    .map((x) => x.it);
}
const isGuardar = (it) => !!it && it.tipo === "guardar";
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
  // F1d: peça «por confirmar» (posicao_conhecida: posta no lugar sem vizinha montada) no lugar, ténue e a tracejado;
  // a célula continua vazia para o motor (não é molde nem vizinha, não conta no progresso)
  const kn = $("#lyr-conhecida"); kn.replaceChildren();
  if (S.showGuardadas) for (const k of b.posicoes_conhecidas) kn.append(porConfirmarEl(k));
  const g = $("#lyr-fantasma"); g.replaceChildren();
  for (const gh of S.ghosts) g.append(s("path", { d: ghostPath(gh.path, gh.cell[1] - 0.5, (gh.cell[0] - 0.5) * S.hr), class: cls("fantasma") }));
  drawTarget(false);
}
/** Peça «por confirmar»: a imagem rodada como fica (se a rotação é conhecida), ténue, e o contorno tracejado da célula. */
function porConfirmarEl(k) {
  const [l, c] = k.cell, span = S.board.span_cells || 1.8;
  const g = s("g", { class: "por-confirmar", "data-piece": k.piece, "data-cell": `${l},${c}` });
  if (k.theta_deg !== null && k.theta_deg !== undefined) {
    g.append(s("image", { href: `/api/pieces/${k.piece}.png?pose=board&size=240&v=${S.ver}`, class: "por-confirmar-img",
      x: c - 0.5 - span / 2, y: (l - 0.5) * S.hr - span / 2, width: span, height: span, preserveAspectRatio: "xMidYMid meet" }));
  }
  // contorno tracejado da própria peça (o mesmo pivô e rotação da imagem); sem rotação, o da célula
  if (k.path && k.path.length) g.append(s("path", { d: ghostPath(k.path, c - 0.5, (l - 0.5) * S.hr), class: cls("por_confirmar") }));
  else g.append(rectEl(l, c, cls("por_confirmar"), 0.06));
  return g;
}
function drawTarget(move = true) {
  const a = $("#lyr-alvo"), nx = $("#lyr-seguinte");
  a.replaceChildren(); nx.replaceChildren();
  if (!S.board || S.tab !== "montar") return;
  if ((S.modo === "painel" && S.painel) || (S.modo === "por_mao" && S.porMao)) {
    // F2: o lugar do painel aberto, tracejado branco (a fila não se desenha por baixo)
    const [pl, pc] = (S.modo === "painel" ? S.painel : S.porMao).cell;
    a.append(rectEl(pl, pc, "painel-sel", 0.03));
    return;
  }
  const q = queue(), cur = current();
  if (!cur || !cur.cell) return;
  for (const it of q.filter((x) => x !== cur).slice(0, 3)) if (it.cell) nx.append(rectEl(it.cell[0], it.cell[1], cls("seguinte"), 0.06));
  const [l, c] = cur.cell;
  // sem vizinha montada: alvo tracejado (lugar provável, sem vizinha para verificar), nunca o «vai aqui» cheio
  const g = isGuardar(cur);
  a.append(rectEl(l, c, cls(g ? "alvo_guardar" : "alvo"), 0.02));
  const x = c - 0.5, y = (l - 1) * S.hr - 0.12, w = g ? 1.9 : 1.24;
  const lab = s("g", { class: "alvo-tag" + (g ? " tracejado" : ""), transform: `translate(${x} ${y})` });
  lab.append(s("rect", { x: -w / 2, y: -0.42, width: w, height: 0.36, rx: 0.08 }),
    s("text", { x: 0, y: -0.17 }, document.createTextNode(g ? "lugar provável" : "vai aqui")));
  a.append(lab);
  if (move) showCell(l, c);
}
/** Desloca o tabuleiro até ao lugar, com contexto à volta (só se não estiver já bem à vista; ``force``: sempre,
 * centrado, o botão «localizar» do cartão). */
function showCell(l, c, force = false) {
  const x = c - 0.5, y = (l - 0.5) * S.hr;
  const v = S.vb, mx = v.w * 0.12, my = v.h * 0.12;
  const inside = x > v.x + mx && x < v.x + v.w - mx && y > v.y + my && y < v.y + v.h - my;
  if (!force && inside && v.w <= 30) return;
  zoomCells(Math.max(1, l - 5), Math.max(1, c - 8), Math.min(S.rows, l + 5), Math.min(S.cols, c + 8), 0.04);
}
function drawLegend() {
  const L = $("#legend"); L.replaceChildren();
  // «Por confirmar» (F1d) só entra na legenda curta quando há peças assim desenhadas
  const extra = (r) => r.id === "por_confirmar" && S.showGuardadas && S.board && S.board.posicoes_conhecidas.length > 0;
  for (const row of (S.board ? S.board.legend : []).filter((r) => r.curta || extra(r))) {
    const sw = s("svg", { class: "lg-sw", viewBox: "0 0 1 1", "aria-hidden": "true" });
    if (row.classe) sw.append(s("rect", { x: 0.1, y: 0.1, width: 0.8, height: 0.8, class: row.classe }));
    else sw.append(s("rect", { x: 0.1, y: 0.1, width: 0.8, height: 0.8, class: "lg-raster" }));
    L.append(h("span", { class: "lg", "data-legend": row.id, title: row.detalhe }, sw, row.rotulo));
  }
}
S.onBoardTap = (l, c) => {
  // F1b: tocar no alvo de uma peça da fila torna-a a peça atual; F2: tocar outra vez no alvo da peça atual, ou
  // noutro lugar, abre o painel desse lugar (com a sugestão do programa e «Pôr uma peça aqui»)
  const it = queue().find((x) => x.cell && x.cell[0] === l && x.cell[1] === c);
  if (it && !(S.tab === "montar" && S.modo === "cartao" && current() === it)) {
    S.pick = it.piece; S.modo = "cartao"; S.painel = null; if (S.tab !== "montar") showTab("montar"); renderMontar(); return;
  }
  openPainel(l, c);
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
  const ult = undoStrip();
  if (ult) T.append(ult);
  if (S.modo === "painel" && S.painel) { renderPainel(T); drawTarget(false); return; }
  if (S.modo === "por_mao" && S.porMao) { renderPorMao(T); drawTarget(false); return; }
  if (!cur) {
    T.append(emptyScreen(m));
    if (m.a_preparar && m.a_preparar.buracos) T.append(prepLine(m));
    if (m.em_pausa) T.append(pauseLine());
    drawTarget(false);
    return;
  }
  if (S.modo === "porque") { renderPorque(T, cur); drawTarget(); return; }
  const g = isGuardar(cur);
  const inBag = g ? q.filter(isGuardar) : q.filter((it) => !isGuardar(it) && String(it.lote) === String(cur.lote));
  const k = inBag.indexOf(cur) + 1;
  const card = h("div", { class: "card" + (g ? " guardar" : ""), "data-piece": cur.piece, "data-tipo": cur.tipo, "data-confianca": cur.confianca });
  card.append(h("div", { class: "card-head" }, h("span", { class: "kicker" }, g ? "Ainda sem peças ao lado" : "Próxima peça"),
    h("span", { class: "count", id: "m-count" }, g ? `${k} de ${inBag.length} ainda sem peças ao lado` : `${k} de ${inBag.length} neste saco · ${q.length} no total`)));
  // «localizar» (F1d): só ícone, com aria-label e dica; volta a centrar o tabuleiro no alvo sem mudar de peça
  const loc = cur.cell ? h("button", { type: "button", class: "icon-btn loc", id: "b-localizar", title: "Mostrar o lugar no tabuleiro",
    "aria-label": "Mostrar o lugar no tabuleiro", onclick: () => showCell(cur.cell[0], cur.cell[1], true) }, ico("locate-fixed")) : null;
  const who = h("div", { class: "who" },
    h("div", { class: "bag" }, cur.lote !== null && cur.lote !== undefined ? `Saco ${cur.lote}` : "Peça sem saco"),
    h("div", { class: "num" }, `peça nº ${cur.n_no_lote ?? "?"}`),
    h("div", { class: "where-row" }, h("span", { class: "where" }, g ? `Lugar provável: ${lugarTxt(cur.cell).toLowerCase()}` : lugarTxt(cur.cell)), loc),
    cur.pose_known ? null : h("div", { class: "small muted" }, "rotação por confirmar"),
    h("div", { class: "pid" }, cur.piece));
  card.append(h("div", { class: "card-top" }, pieceImg(cur), who));
  card.append(h("div", { class: "conf", "data-conf": cur.confianca }, bars(passes(cur)), h("span", {}, CONF_LONG[cur.confianca])));
  if (g) card.append(h("p", { class: "small muted guardar-txt", id: "m-guardar-txt" },
    "Ainda não há nenhuma peça montada ao lado deste lugar, por isso o encaixe não se pode verificar. ",
    "Põe-na no lugar: fica no tabuleiro «por confirmar» até uma vizinha encaixar."));
  const acts = h("div", { class: "actions" });
  if (g) {
    acts.append(h("button", { class: "btn primary big", type: "button", id: "b-guardar", onclick: () => doGuardar(cur) }, ico("map-pin"), "Colocar aqui"));
    acts.append(h("button", { class: "btn big", type: "button", id: "b-nao", onclick: () => doNao(cur) }, ico("x"), "Não pertence aqui"));
  } else {
    acts.append(h("button", { class: "btn primary big", type: "button", id: "b-encaixa", onclick: () => doEncaixa(cur) }, ico("check"), "Encaixa"));
    if (cur.nao_encaixa) acts.append(h("button", { class: "btn big", type: "button", id: "b-nao", onclick: () => doNao(cur) }, ico("x"), "Não encaixa"));
  }
  card.append(acts);
  card.append(h("div", { class: "links" },
    h("button", { class: "linkish", type: "button", id: "b-saltar", onclick: () => doSaltar(cur) }, ico("skip-forward"), "Saltar por agora"),
    h("button", { class: "linkish", type: "button", id: "b-porque", onclick: () => { S.modo = "porque"; renderMontar(); } }, ico("circle-question-mark"), "Porquê esta peça?")));
  T.append(card);
  const nxt = q.filter((x) => x !== cur).slice(0, 3);
  if (nxt.length) {
    const same = nxt.every((x) => String(x.lote) === String(cur.lote));
    const allG = nxt.every(isGuardar);
    T.append(h("h2", {}, allG ? "A seguir, ainda sem peças ao lado" : (same ? "A seguir, do mesmo saco" : "A seguir, primeiro as do mesmo saco")));
    const ul = h("ul", { class: "next", id: "m-seguir" });
    for (const it of nxt) ul.append(h("li", {}, h("button", { type: "button", class: "next-row", "data-tipo": it.tipo, onclick: () => { S.pick = it.piece; renderMontar(); } },
      h("span", {}, quem(it)), h("span", { class: "w " + it.confianca }, isGuardar(it) ? "ainda sem peças ao lado" : CONF_TXT[it.confianca]))));
    T.append(ul);
  }
  const fora = groupsLine(m);
  if (fora) T.append(fora);
  if (m.a_preparar && m.a_preparar.buracos) T.append(prepLine(m));
  if (m.em_pausa) T.append(pauseLine());
  drawTarget();
}
const plural = (n, um, varios) => `${n} ${n === 1 ? um : varios}`;
/** Ecrã vazio (F1c): diz a verdade sobre o que ficou de fora da fila; «Nada para ir buscar» só sem propostas nenhumas. */
function emptyScreen(m) {
  const f = m.fora_da_fila || {};
  // F1d: conta as peças já guardadas à parte (posicao_conhecida, no tabuleiro «por confirmar»), não os cartões
  // «para guardar» da fila (com a fila vazia são sempre 0)
  const n = (f.guardadas || 0) + (f.grupos_sem_lugar || 0);
  if (!n) {
    return h("div", { class: "empty", "data-estado": "vazio" }, h("strong", {}, "Nada para ir buscar."), h("p", {}, "Digitaliza mais um saco."),
      h("button", { class: "btn primary", type: "button", onclick: () => showTab("importar") }, ico("scan-line"), "Importar scan"));
  }
  const ul = h("ul", { class: "resumo", id: "m-resumo" });
  if (f.guardadas) ul.append(h("li", { "data-k": "guardadas" }, `${plural(f.guardadas, "peça guardada", "peças guardadas")} à parte, no tabuleiro «por confirmar» até uma vizinha encaixar.`));
  if (f.grupos_sem_lugar) ul.append(h("li", { "data-k": "grupos" }, `${plural(f.grupos_sem_lugar, "grupo", "grupos")} sem lugar: por agora só na interface completa.`));
  return h("div", { class: "empty", "data-estado": "vazio_com_propostas" },
    h("strong", {}, "Nenhuma peça para pôr agora."),
    h("p", {}, "Nenhuma sugestão tem ainda uma peça montada ao lado para confirmar o encaixe."),
    ul,
    h("div", { class: "actions center" },
      h("a", { class: "btn", href: "/", id: "m-completa" }, ico("layout-dashboard"), "Abrir a interface completa"),
      h("button", { class: "btn primary", type: "button", onclick: () => showTab("importar") }, ico("scan-line"), "Importar scan")));
}
function groupsLine(m) {
  const n = (m.fora_da_fila || {}).grupos_sem_lugar || 0;
  if (!n) return null;
  return h("p", { class: "small muted", id: "m-grupos" }, `${plural(n, "grupo", "grupos")} sem lugar: `, h("a", { href: "/" }, "ver na interface completa"));
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
    h("div", { class: "actions" }, h("button", { class: "btn", type: "button", onclick: () => { S.modo = "cartao"; renderMontar(); } }, ico("arrow-left"), "Voltar"))));
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
  box.append(h("div", { class: "actions" }, h("button", { class: "btn primary big", type: "button", id: "b-proxima", onclick: () => { S.modo = "cartao"; renderMontar(); } }, ico("arrow-right"), "Próxima peça")));
  box.append(h("div", { class: "links" }, h("button", { class: "linkish", type: "button", id: "b-desfazer", onclick: () => doUndo() }, ico("undo-2"), "Enganei-me, desfazer")));
  T.append(box);
}
/** F1d (ponto 1): a última ação fica à vista no topo do painel, com «Desfazer», até à ação seguinte ou ao desfazer
 * (o aviso temporário de 9 s não chegava: o Tiago não o viu). Enquanto grava: «A gravar…», sem botão. */
function undoStrip() {
  if (S.pendente) return h("div", { class: "ultimo", id: "m-ultimo", "data-estado": "a_gravar" }, h("span", {}, S.pendente));
  const u = S.undo;
  if (!u || !u.msg || (u.tipo === "nao" && S.modo === "nao")) return null;
  return h("div", { class: "ultimo", id: "m-ultimo", "data-tipo": u.tipo }, h("span", { class: "ultimo-txt" }, u.msg),
    h("button", { class: "btn", type: "button", id: "b-desfazer-ultimo", onclick: () => doUndo() }, ico("undo-2"), "Desfazer"));
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
/** Uma ação desfazível: «A gravar…» no painel enquanto o servidor escreve (a recarga por SSE pode mostrar o cartão
 * seguinte antes da resposta), depois a faixa «última ação» com «Desfazer» (fica até à ação seguinte) e o aviso. */
async function act(it, req, pend, undo, after) {
  lockButtons(true);
  S.pendente = pend; renderMontar();
  try {
    const r = await post(req.url, req.body);
    writeFailed(r);
    S.undo = { item: it, ...undo(r) };
    S.pick = null; S.modo = after || "cartao";
    S.pendente = null;
    renderMontar();
    $("#tab-montar").scrollTop = 0;              // a faixa «Desfazer» fica no topo do painel: mostra-a
    if (S.modo === "cartao") toastUndo(S.undo.msg);
    await afterWrite();
  } catch (e) { S.pendente = null; renderMontar(); toast(e.message, true); } finally { lockButtons(false); }
}
async function doEncaixa(it) {
  if (S.busy || !it || !it.encaixa) return;
  await act(it, it.encaixa, `A pôr ${quem(it).toLowerCase()} no lugar…`, () => ({ tipo: "encaixa", msg: `${quem(it)} no lugar.` }));
}
async function doGuardar(it) {
  // «Colocar aqui» (F1d; antes «Guardei à parte»): por dentro continua a ser position_known (posição conhecida)
  if (S.busy || !it || !it.guardar) return;
  await act(it, it.guardar, `A pôr ${quem(it).toLowerCase()} no lugar…`,
    () => ({ tipo: "guardar", msg: `${quem(it)} no lugar, por confirmar.` }));
}
const rejeicoes = (r) => (r.escritos || []).filter((e) => ["twin_rejected", "hole_rejected", "pair_rejected"].includes(e.action))
  .map((e) => (e.action === "pair_rejected" ? { pair: e.pair, t: e.t } : { piece: e.piece, cell: e.cell, origin: e.origin, t: e.t }));
async function doNao(it) {
  if (S.busy || !it || !it.nao_encaixa) return;
  // «Não pertence aqui» (cartão sem vizinha montada, F1d) não pergunta «Porquê?»: segue para o cartão seguinte
  const g = isGuardar(it);
  await act(it, it.nao_encaixa, "A gravar…", (r) => ({ tipo: "nao", rejeicoes: rejeicoes(r), motivo: null,
    msg: g ? `${quem(it)}: não pertence à ${lugarTxt(it.cell).toLowerCase()}.` : `${quem(it)}: não encaixa.` }), g ? "cartao" : "nao");
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
  S.pendente = "A desfazer…"; renderMontar();
  try {
    // F2: desfazer global de um nível: as ações dos painéis guardam o pedido inverso (``inversa``); as do Montar, o tipo
    if (u.inversa) for (const q of [].concat(u.inversa)) await post(q.url, q.body);
    else if (u.tipo === "encaixa") await post("/api/confirm", { acao: "unplace", piece: u.item.piece, desfaz: true });
    else if (u.tipo === "guardar") await post("/api/confirm", { acao: "position_clear", piece: u.item.piece, desfaz: true });
    else if (u.tipo === "nao" && u.rejeicoes.length) await post("/api/confirm", { acao: "undo_reject", rejeicoes: u.rejeicoes });
    S.undo = null; S.pendente = null;
    if (!u.painel) { S.modo = "cartao"; S.pick = u.item ? u.item.piece : null; }
    $$("#toast .undo-toast").forEach((x) => x.remove());
    renderMontar();
    toast(`Desfeito: ${u.item ? quem(u.item) : u.msg}`);
    await afterWrite();
    if (u.painel) await refreshPainel();
  } catch (e) { S.pendente = null; renderMontar(); toast(e.message, true); } finally { lockButtons(false); }
}
function toastUndo(msg) {
  const el = h("div", { class: "undo-toast" }, h("span", {}, msg),
    h("button", { type: "button", class: "linkish", onclick: () => { el.remove(); doUndo(); } }, ico("undo-2"), "Desfazer"));
  $("#toast").append(el);
  setTimeout(() => el.remove(), 9000);
}

// ------------------------------------------------------------ F2: painel do lugar tocado (ESPEC §4.4, §4.5)
// Tocar no tabuleiro abre: a peça (colocada ou «por confirmar»), o lugar vazio, ou o lugar marcado por ti (cheio sem
// peça digitalizada). As ações guardam o pedido inverso em S.undo (desfazer de um nível, faixa no topo e Ctrl+Z).
const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
function dataCurta(t) {
  if (!t) return null;
  const d = new Date(t);
  return isNaN(d) ? null : `${d.getDate()} ${MESES[d.getMonth()]}`;
}
function bordaTxt(l, c) {
  const v = l === 1 ? "de cima" : (l === S.rows ? "de baixo" : null);
  const hz = c === 1 ? "esquerda" : (c === S.cols ? "direita" : null);
  if (v && hz) return `no canto ${v}, à ${hz}`;
  if (v) return `na borda ${v}`;
  if (hz) return `na borda da ${hz}`;
  return null;
}
const lugarLongo = (cell) => { const b = bordaTxt(cell[0], cell[1]); return lugarTxt(cell) + (b ? `, ${b}` : ""); };
/** Imagem de peça no lightbox, com o ajuste de cor (só as imagens de peça; a folha e a arte ficam como são). */
function lightboxPeca(src, cap) { lightbox(src, cap); $("#lb-img").classList.add("peca-img"); }
function lightboxFolha(src, cap) { lightbox(src, cap); $("#lb-img").classList.remove("peca-img"); }

async function openPainel(l, c) {
  if (S.tab !== "montar") showTab("montar");
  closeLupa();
  S.modo = "painel"; S.porMao = null;
  S.painel = { cell: [l, c], d: null, erro: null, seq: (S.painel ? S.painel.seq : 0) + 1, report: null };
  renderMontar();
  await refreshPainel();
}
async function refreshPainel() {
  const P = S.painel;
  if (!P) return;
  const seq = ++P.seq;
  try {
    const d = await api(`/api/cell/${P.cell[0]}/${P.cell[1]}`);
    if (S.painel !== P || P.seq !== seq) return;
    P.d = d; P.erro = null;
  } catch (e) { if (S.painel === P) P.erro = e.message; }
  if (S.modo === "painel" && S.painel === P) renderMontar();
}
function painelKind(d) {
  if (d.estado === "colocada" && d.peca) return "peca";
  if ((d.conhecidas || []).length) return "por_confirmar";
  if (d.estado === "ocupada_legado" && d.pista) return "marcado";
  return "vazio";
}
function voltarFila() { S.modo = "cartao"; S.painel = null; S.porMao = null; renderMontar(); }
function renderPainel(T) {
  const P = S.painel, d = P.d;
  const box = h("div", { class: "card painel", id: "painel" });
  T.append(box);
  if (P.erro && !d) {
    box.dataset.kind = "erro";
    box.append(h("strong", {}, "Não consegui ler este lugar."), h("p", { class: "small muted" }, P.erro));
  } else if (!d) {
    box.dataset.kind = "a_carregar";
    box.append(h("strong", {}, "A carregar…"));
  } else {
    const kind = painelKind(d);
    box.dataset.kind = kind;
    if (kind === "peca" || kind === "por_confirmar") painelPeca(box, d, kind);
    else painelVazio(box, d, kind);
  }
  box.append(h("div", { class: "links" }, h("button", { class: "linkish", type: "button", id: "p-voltar", onclick: voltarFila }, ico("arrow-left"), "Voltar à fila")));
}
/** Uma ação de um painel: «A gravar…», depois a faixa «Desfazer» com o pedido inverso; o painel recarrega o lugar. */
async function actPainel(req, pend, undo) {
  if (S.busy) return;
  lockButtons(true);
  S.pendente = pend; renderMontar();
  try {
    const r = await post(req.url, req.body);
    writeFailed(r);
    S.undo = { painel: true, ...undo(r) };
    S.pendente = null; renderMontar();
    $("#tab-montar").scrollTop = 0;
    toastUndo(S.undo.msg);
    await afterWrite();
    await refreshPainel();
  } catch (e) { S.pendente = null; renderMontar(); toast(e.message, true); } finally { lockButtons(false); }
}
const confirmReq = (body) => ({ url: "/api/confirm", body });
function painelPeca(box, d, kind) {
  const pc = kind === "peca" ? d.peca : d.conhecidas[0];
  const cell = d.cell, nome = nomePeca(pc);
  const sec = kind === "peca" && pc.seccao_id ? d.secao : null;
  box.append(h("span", { class: "kicker" }, kind === "peca" ? "Peça no lugar" : "Peça por confirmar"),
    h("div", { class: "bag" }, pc.lote !== null && pc.lote !== undefined ? `Saco ${pc.lote}` : "Peça sem saco"),
    h("div", { class: "num" }, `nº ${pc.n_no_lote ?? "?"}`),
    h("div", { class: "where", id: "p-lugar" }, lugarLongo(cell)));
  let est, key;
  if (kind === "por_confirmar") { est = "Por confirmar · ainda sem peças ao lado"; key = "por_confirmar"; }
  else if (sec) { est = `Veio do grupo (${sec.n} peças)`; key = "grupo"; }
  else { const dt = dataCurta(d.posta_em); est = dt ? `No lugar · posta por ti a ${dt}` : "No lugar"; key = "no_lugar"; }
  box.append(h("div", { class: "estado", id: "p-estado", "data-estado": key }, est));
  const folha = pc.scan_id ? h("button", { type: "button", class: "folha-btn", id: "p-folha", "aria-label": "Ampliar a folha que digitalizaste",
    onclick: () => lightboxFolha(`/api/sheets/${pc.scan_id}.jpg?highlight=${pc.id}&max=1400&v=${S.ver}`,
      `Folha do saco ${pc.lote ?? "—"}: a peça nº ${pc.n_no_lote ?? "?"} está marcada a âmbar`) },
    h("img", { src: `/api/sheets/${pc.scan_id}.jpg?highlight=${pc.id}&max=700&v=${S.ver}`, alt: "" }),
    h("span", {}, "Na folha que digitalizaste (toca para ampliar)")) : null;
  box.append(h("div", { class: "painel-imgs" },
    h("button", { type: "button", class: "pimg", id: "p-peca", "aria-label": "Ampliar a peça",
      onclick: () => lightboxPeca(`/api/pieces/${pc.id}.png?pose=board&size=700&v=${S.ver}`, nome) },
    h("img", { src: `/api/pieces/${pc.id}.png?pose=board&size=240&v=${S.ver}`, alt: nome })), folha));
  box.append(h("div", { class: "pid", id: "p-pid" }, pc.id));
  const col = h("div", { class: "btn-col" });
  if (sec) {
    col.append(h("button", { class: "btn", type: "button", id: "p-tirar", onclick: () => actPainel(
      confirmReq({ acao: "unanchor", section: sec.id }), `A tirar o grupo de ${sec.n} peças…`,
      () => ({ tipo: "tirar_grupo", msg: `Grupo de ${sec.n} peças tirado do lugar.`, inversa: confirmReq({ acao: "anchor", section: sec.id,
        cell: [sec.anchor.l0, sec.anchor.c0], rot: sec.anchor.rot || 0, mirror: !!sec.anchor.mirror }) })) },
    ico("arrow-up-from-line"), `Tirar o grupo inteiro do lugar (${sec.n} peças)`));
  } else if (kind === "por_confirmar") {
    // sem «desfaz»: tirar é neutro (P7b); o desfazer põe-na outra vez «por confirmar» no mesmo lugar e rotação
    col.append(h("button", { class: "btn", type: "button", id: "p-tirar", onclick: () => actPainel(
      confirmReq({ acao: "position_clear", piece: pc.id }), `A tirar ${nome.toLowerCase()}…`,
      () => ({ tipo: "tirar", msg: `${nome} tirada do lugar.`, inversa: confirmReq({ acao: "position_known", piece: pc.id, cell,
        origin: "manual", theta_deg: pc.theta_deg }) })) }, ico("arrow-up-from-line"), "Tirar do lugar"));
  } else {
    // «Tirar do lugar»: neutro (P7b); numa peça de par também limpa a outra «por confirmar» que veio desta colocação (c)
    col.append(h("button", { class: "btn", type: "button", id: "p-tirar", onclick: () => actPainel(
      confirmReq({ acao: "unplace", piece: pc.id, tirar: true }), `A tirar ${nome.toLowerCase()}…`,
      () => ({ tipo: "tirar", msg: `${nome} tirada do lugar.`, inversa: confirmReq({ acao: "place", piece: pc.id, cell,
        origin: "manual", theta_deg: pc.theta_deg, reposicao: true }) })) }, ico("arrow-up-from-line"), "Tirar do lugar"));
  }
  col.append(h("a", { class: "btn", id: "p-recorte", href: `/?peca=${pc.id}&contorno=1`, target: "_blank", rel: "noopener",
    title: "Abre o editor do recorte na interface completa (o editor novo chega mais tarde)" }, ico("scissors"), "Corrigir recorte"));
  box.append(col);
  reportBlock(box, d, pc);
}
const REPORT_TIPOS = [["mal_lida", "O recorte está mal"], ["mal_colocada", "Está no lugar errado"], ["nao_encaixa", "Não encaixa"],
  ["outro", "Outra coisa"]];
function reportBlock(box, d, pc) {
  const P = S.painel;
  for (const r of d.reports_abertos || []) {
    const t = (REPORT_TIPOS.find((x) => x[0] === r.tipo) || [null, "algo"])[1];
    box.append(h("p", { class: "small muted p-reportado" }, `Já reportaste: ${t.toLowerCase()}${r.texto ? ` («${r.texto}»)` : ""}.`));
  }
  if (!P.report) {
    box.append(h("div", { class: "btn-col" }, h("button", { class: "btn", type: "button", id: "p-errado",
      onclick: () => { P.report = { tipo: null }; renderMontar(); } }, ico("flag"), "Algo está errado")));
    return;
  }
  const rb = h("div", { class: "report-box", id: "p-report" }, h("strong", {}, "O que está errado?"));
  const tipos = h("div", { class: "tipos" });
  for (const [k, t] of REPORT_TIPOS) tipos.append(h("button", { class: "btn" + (P.report.tipo === k ? " on" : ""), type: "button", "data-tipo": k,
    onclick: () => { P.report.tipo = k; $$("#p-report .tipos .btn").forEach((b) => b.classList.toggle("on", b.dataset.tipo === k)); } }, t));
  const txt = h("textarea", { id: "p-report-txt", placeholder: "O que viste (opcional)", "aria-label": "O que viste (opcional)" });
  rb.append(tipos, txt, h("div", { class: "actions" },
    h("button", { class: "btn primary", type: "button", id: "p-report-enviar", onclick: async () => {
      if (!P.report.tipo) { toast("Escolhe o que está errado."); return; }
      try {
        await post("/api/report", { piece: pc ? pc.id : null, cell: d.cell, tipo: P.report.tipo, texto: txt.value || "", vista: "novo/painel" });
        P.report = null; toast("Obrigado. Fica registado."); await refreshPainel();
      } catch (e) { toast(e.message, true); }
    } }, "Enviar"),
    h("button", { class: "btn", type: "button", onclick: () => { P.report = null; renderMontar(); } }, "Cancelar")));
  box.append(rb);
}
function painelVazio(box, d, kind) {
  const [l, c] = d.cell;
  box.append(h("span", { class: "kicker" }, kind === "marcado" ? "Lugar marcado por ti" : "Lugar vazio"), h("h3", { id: "p-lugar" }, lugarLongo(d.cell)));
  if (kind === "marcado") box.append(h("p", { class: "estado", id: "p-estado", "data-estado": "marcado" }, "Marcaste este lugar como montado, mas a peça ainda não foi digitalizada."));
  else if (d.estado === "ocupada_legado") box.append(h("p", { class: "small muted", id: "p-foto" }, "Na foto do tabuleiro parece cheio: por confirmar."));
  box.append(h("div", { class: "arte-box" }, h("img", { id: "p-arte", src: `/api/cell/${l}/${c}/zoom.jpg?side=art&dpi=150&v=${S.ver}`, alt: "" }),
    h("span", {}, "A arte da caixa neste sítio, com o que fica à volta")));
  const sug = h("div", { class: "sugestao", id: "p-sugestao" });
  const inQ = queue().filter((it) => it.cell && it.cell[0] === l && it.cell[1] === c);
  if (inQ.length) {
    for (const it of inQ) {
      const g = isGuardar(it);
      sug.append(h("p", {}, `O programa acha que pode ser: ${quem(it)}`),
        h("div", { class: "conf", "data-conf": it.confianca }, bars(passes(it)), h("span", {}, g ? "a confirmar por ti" : CONF_TXT[it.confianca])),
        h("div", { class: "actions" }, g
          ? h("button", { class: "btn primary", type: "button", onclick: () => doGuardar(it) }, ico("map-pin"), "Colocar aqui")
          : h("button", { class: "btn primary", type: "button", onclick: () => doEncaixa(it) }, ico("check"), "Encaixa")));
    }
  } else if ((d.propostas || []).length) {
    for (const e of d.propostas) sug.append(h("p", {}, `O programa acha que pode ser: ${nomePeca(e)} (a confirmar por ti).`));
  } else sug.append(h("p", { class: "muted" }, "Sem sugestão por agora."));
  box.append(sug);
  const col = h("div", { class: "btn-col" });
  if (kind === "marcado") {
    col.append(h("button", { class: "btn primary", type: "button", id: "p-por", onclick: () => startPorMao(d) }, ico("plus"), "Pôr a peça digitalizada aqui"),
      h("button", { class: "btn", type: "button", id: "p-vazio", onclick: () => actPainel(confirmReq({ acao: "cell_empty", cell: d.cell }),
        "A gravar…", () => ({ tipo: "vazio", msg: `${lugarTxt(d.cell)}: afinal está vazio.`, inversa: confirmReq({ acao: "cell_full", cell: d.cell }) })) },
      ico("x"), "Afinal está vazio"));
  } else {
    col.append(h("button", { class: "btn primary", type: "button", id: "p-por", onclick: () => startPorMao(d) }, ico("plus"), "Pôr uma peça aqui"),
      h("button", { class: "btn", type: "button", id: "p-cheio", onclick: () => actPainel(confirmReq({ acao: "cell_full", cell: d.cell }),
        "A gravar…", () => ({ tipo: "cheio", msg: `${lugarTxt(d.cell)}: marcado como montado.`, inversa: confirmReq({ acao: "cell_empty", cell: d.cell }) })) },
      ico("square-dashed"), "Já tem peça, mas não a digitalizei"));
  }
  box.append(col);
}

// ------------------------------------------------------------ F2: «Pôr uma peça à mão» (ESPEC §4.6, §8.7 P10b)
// Passo 1: saco e nº (ou a grelha das soltas do saco); passo 2: a peça no lugar, «Rodar», 3 verificações que não
// bloqueiam. Grava `por_mao`: `place` com uma vizinha montada, senão fica «por confirmar» (decisão g, 2026-11-14).
function startPorMao(d) {
  S.porMao = { cell: d.cell, d, passo: 1, saco: sess.saco !== null && sess.saco !== undefined ? String(sess.saco) : "", n: "",
    look: null, lseq: 0, piece: null, theta: null, verif: null, aVerificar: false, vseq: 0, ctrl: null, grade: false, erroVer: null };
  S.modo = "por_mao"; renderMontar();
  $("#pm-saco") && ($("#pm-saco").value ? $("#pm-n") : $("#pm-saco")).focus();
}
function cancelPorMao() { const M = S.porMao; if (M && M.ctrl) M.ctrl.abort(); S.porMao = null; S.modo = "painel"; renderMontar(); }
let lookTimer = null;
function scheduleLookup(now = false) {
  clearTimeout(lookTimer);
  lookTimer = setTimeout(doLookup, now ? 0 : 250);
}
async function doLookup() {
  const M = S.porMao;
  if (!M) return;
  const seq = ++M.lseq;
  if (!M.saco || !M.n) { M.look = null; updLook(); return; }
  try {
    const r = await api(`/api/pieces/lookup?saco=${encodeURIComponent(M.saco)}&n=${encodeURIComponent(M.n)}`);
    if (S.porMao !== M || seq !== M.lseq) return;
    M.look = r;
  } catch (e) { if (S.porMao === M && seq === M.lseq) M.look = { pode_por: false, frase: e.message }; }
  updLook();
}
/** Só a frase e o botão (sem refazer o painel: o cursor fica no campo onde se escreve). */
function updLook() {
  const M = S.porMao, f = $("#pm-frase"), b = $("#pm-continuar");
  if (!M || !f) return;
  const L = M.look;
  f.textContent = L ? L.frase : "";
  f.dataset.estado = L ? (L.pode_por ? "ok" : "nao") : "";
  if (b) b.disabled = !(L && L.pode_por);
  $$("#pm-grade button").forEach((x) => x.classList.toggle("on", !!L && x.dataset.piece === L.piece));
}
async function toggleGrade() {
  const M = S.porMao;
  M.grade = !M.grade;
  if (M.grade) { try { S.lots = await api("/api/lots"); } catch (e) { toast(e.message, true); } }
  renderMontar();
}
function gradeEl(M) {
  const g = h("div", { class: "pm-grade", id: "pm-grade" });
  const L = (S.lots || []).find((x) => String(x.lote) === String(M.saco));
  if (!M.saco) { g.append(h("p", { class: "small muted" }, "Escreve primeiro o número do saco.")); return g; }
  const pcs = L ? L.pecas.filter((p) => ["solta", "emparelhada", "posicao_conhecida"].includes(p.estado)) : [];
  if (!pcs.length) { g.append(h("p", { class: "small muted" }, `O saco ${M.saco} não tem peças soltas.`)); return g; }
  for (const p of pcs) {
    g.append(h("button", { type: "button", "data-piece": p.id, class: M.look && M.look.piece === p.id ? "on" : "", "aria-label": `nº ${p.n_no_lote}`,
      onclick: () => { M.n = String(p.n_no_lote); $("#pm-n").value = M.n; scheduleLookup(true); } },
    h("img", { src: `/api/pieces/${p.id}.png?pose=scan&size=112&v=${S.ver}`, alt: "", loading: "lazy" }), `nº ${p.n_no_lote}`));
  }
  return g;
}
function goPasso2() {
  const M = S.porMao, L = M.look;
  if (!L || !L.pode_por) return;
  M.passo = 2; M.piece = L.piece; M.theta = L.theta_base; M.verif = null;
  renderMontar();
  verify(null);
}
function rodar() {
  const M = S.porMao;
  if (!M || M.theta === null || M.theta === undefined) return;
  verify(((M.theta + 90 + 180) % 360 + 360) % 360 - 180);
}
async function verify(theta) {
  const M = S.porMao;
  if (!M || !M.piece) return;
  if (M.ctrl) M.ctrl.abort();                     // mudar a rotação aborta a verificação anterior (como o detalhe, B)
  const ctrl = new AbortController(), seq = ++M.vseq;
  M.ctrl = ctrl; M.aVerificar = true; M.verif = null; M.erroVer = null;
  if (theta !== null) M.theta = theta;
  renderMontar();
  try {
    const r = await fetch(`/api/cell/${M.cell[0]}/${M.cell[1]}/verificar`, { method: "POST", signal: ctrl.signal,
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ piece: M.piece, theta_deg: theta }) });
    const b = await r.json().catch(() => ({}));
    if (S.porMao !== M || seq !== M.vseq) return;
    if (!r.ok) throw new Error(b.error || b.detail || `erro ${r.status}`);
    M.verif = b;
    if (theta === null) M.theta = b.theta_deg;
  } catch (e) {
    if (e.name === "AbortError" || S.porMao !== M || seq !== M.vseq) return;
    M.erroVer = e.message;
  }
  M.aVerificar = false;
  if (S.modo === "por_mao" && S.porMao === M) renderMontar();
}
function previewEl(M) {
  const [l, c] = M.cell, reg = (M.d.zoom && M.d.zoom.region) || [l, c, l, c];
  const [l0, c0, l1, c1] = reg, hr = S.hr, span = (S.board && S.board.span_cells) || 1.8;
  const x0 = c0 - 1, y0 = (l0 - 1) * hr, w = c1 - c0 + 1, hh = (l1 - l0 + 1) * hr;
  const th = M.theta;
  const src = th === null || th === undefined ? `/api/pieces/${M.piece}.png?pose=board&size=360&v=${S.ver}`
    : `/api/pieces/${M.piece}.png?theta=${Number(th).toFixed(2)}&size=360&v=${S.ver}`;
  return s("svg", { class: "pm-preview", id: "pm-preview", viewBox: `${x0} ${y0} ${w} ${hh}`, role: "img",
    "aria-label": "A peça no lugar, com as peças à volta", "data-theta": th === null || th === undefined ? "" : Number(th).toFixed(2) },
  s("image", { href: `/api/cell/${l}/${c}/zoom.jpg?side=render&dpi=150&v=${S.ver}`, x: x0, y: y0, width: w, height: hh, preserveAspectRatio: "none" }),
  s("image", { class: "pm-peca", href: src, x: c - 0.5 - span / 2, y: (l - 0.5) * hr - span / 2, width: span, height: span, preserveAspectRatio: "xMidYMid meet" }),
  rectEl(l, c, "pm-cell", 0.02));
}
function renderPorMao(T) {
  const M = S.porMao;
  const box = h("div", { class: "card painel", id: "por-mao", "data-passo": String(M.passo) });
  T.append(box);
  box.append(h("span", { class: "kicker" }, "Pôr uma peça à mão"), h("h3", {}, lugarLongo(M.cell)));
  if (M.passo === 1) {
    box.append(h("p", { class: "small muted" }, "Que peça tens na mão? Escreve o saco e o número."));
    const saco = h("input", { id: "pm-saco", type: "number", inputmode: "numeric", min: 1, value: M.saco, "aria-label": "Saco" });
    const num = h("input", { id: "pm-n", type: "number", inputmode: "numeric", min: 1, value: M.n, "aria-label": "Número da peça" });
    const onIn = () => { M.saco = saco.value.trim(); M.n = num.value.trim(); scheduleLookup(); if (M.grade) { const g = $("#pm-grade"); if (g) g.replaceWith(gradeEl(M)); } };
    saco.addEventListener("input", onIn); num.addEventListener("input", onIn);
    num.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); goPasso2(); } });
    box.append(h("div", { class: "pm-campos" }, h("label", {}, "Saco", saco), h("label", {}, "nº", num)),
      h("p", { class: "pm-frase", id: "pm-frase", "data-estado": "" }),
      h("div", { class: "actions" },
        h("button", { class: "btn primary big", type: "button", id: "pm-continuar", disabled: true, onclick: goPasso2 }, ico("arrow-right"), "Continuar"),
        h("button", { class: "btn", type: "button", id: "pm-folha", onclick: toggleGrade }, ico("layout-grid"), M.grade ? "Esconder a folha" : "Escolher na folha")));
    if (M.grade) box.append(gradeEl(M));
    box.append(h("div", { class: "links" }, h("button", { class: "linkish", type: "button", id: "pm-cancelar", onclick: cancelPorMao }, ico("arrow-left"), "Cancelar")));
    updLook();
    if (M.saco && M.n && !M.look) scheduleLookup(true);
    return;
  }
  const L = M.look || {}, nome = `Saco ${L.lote ?? "?"} · nº ${L.n_no_lote ?? "?"}`;
  box.append(h("div", { class: "small", id: "pm-peca-nome" }, nome), previewEl(M));
  box.append(h("div", { class: "actions" }, h("button", { class: "btn", type: "button", id: "pm-rodar", onclick: rodar,
    disabled: M.theta === null || M.theta === undefined }, ico("rotate-cw"), "Rodar")));
  const ul = h("ul", { class: "why ver-lista", id: "pm-ver" });
  const nViz = M.verif ? M.verif.vizinhas_com_forma : (M.d.vizinhas_com_forma || 0);
  const borda = !!bordaTxt(M.cell[0], M.cell[1]);
  if (M.aVerificar || (!M.verif && !M.erroVer)) {
    const keys = (borda ? [["borda", "Lado liso"]] : []).concat([["forma", "Forma com as peças ao lado"], ["imagem", "Imagem com as peças ao lado"]]);
    for (const [k, t] of keys) ul.append(h("li", { "data-chave": k, "data-estado": "a_verificar" }, bars(0, "a verificar"), h("span", {}, `${t}: a verificar…`)));
  } else if (M.erroVer) {
    ul.append(h("li", { "data-chave": "erro", "data-estado": "nao_testado" }, bars(0, "não verificado"), h("span", {}, `Não consegui verificar: ${M.erroVer}`)));
  } else {
    for (const t of M.verif.verificacoes) ul.append(h("li", { "data-chave": t.chave, "data-estado": t.estado },
      bars(t.tracos, t.estado === "nao_testado" ? "não verificado" : `${t.tracos} de 3`), h("span", {}, t.frase),
      t.estado === "nao_testado" ? h("em", { class: "nv" }, "não verificado") : null));
  }
  box.append(ul);
  box.append(h("p", { class: "estado-linha", id: "pm-estado", "data-modo": nViz ? "colocar" : "por_confirmar" }, nViz
    ? `Tem ${nViz === 1 ? "uma peça montada ao lado" : `${nViz} peças montadas ao lado`}: fica no lugar.`
    : "Ainda sem peças ao lado: fica no tabuleiro «por confirmar» até uma vizinha encaixar."));
  const falha = !!(M.verif && M.verif.falha);
  if (falha) box.append(h("p", { class: "aviso", id: "pm-aviso" }, "Uma verificação falhou. Confirma na mão antes de a pôr; se encaixa mesmo, põe na mesma."));
  const label = nViz ? (falha ? "Pôr na mesma" : "Pôr aqui") : "Colocar aqui, por confirmar";
  box.append(h("div", { class: "actions" }, h("button", { class: "btn primary big", type: "button", id: "pm-por", onclick: doPorMao }, ico(nViz ? "check" : "map-pin"), label)));
  box.append(h("div", { class: "links" },
    h("button", { class: "linkish", type: "button", id: "pm-outra", onclick: () => { if (M.ctrl) M.ctrl.abort(); M.passo = 1; M.verif = null; renderMontar(); } }, ico("arrow-left"), "Outra peça"),
    h("button", { class: "linkish", type: "button", id: "pm-cancelar", onclick: cancelPorMao }, ico("x"), "Cancelar")));
}
async function doPorMao() {
  const M = S.porMao;
  if (!M || !M.piece || S.busy) return;
  if (M.ctrl) M.ctrl.abort();
  const L = M.look || {}, nome = `Saco ${L.lote ?? "?"} · nº ${L.n_no_lote ?? "?"}`, cell = M.cell, pid = M.piece;
  lockButtons(true);
  S.pendente = `A pôr ${nome.toLowerCase()} no lugar…`; renderMontar();
  try {
    const r = await post("/api/confirm", { acao: "por_mao", piece: pid, cell, theta_deg: M.theta });
    writeFailed(r);
    const conf = r.modo === "por_confirmar";
    S.undo = { tipo: "por_mao", painel: true, msg: conf ? `${nome} no lugar, por confirmar.` : `${nome} no lugar.`,
      inversa: confirmReq(conf ? { acao: "position_clear", piece: pid, desfaz: true } : { acao: "unplace", piece: pid, desfaz: true }) };
    S.pendente = null; S.porMao = null; S.modo = "painel";
    S.painel = { cell, d: null, erro: null, seq: (S.painel ? S.painel.seq : 0) + 1, report: null };
    renderMontar();
    toastUndo(S.undo.msg);
    await afterWrite();
    await refreshPainel();
  } catch (e) { S.pendente = null; renderMontar(); toast(e.message, true); } finally { lockButtons(false); }
}

// ------------------------------------------------------------ F2 (9): «⋯ › Definições › Cor das peças» (só visualização)
// Um filtro CSS (brilho e saturação) nas imagens de peça dos cartões e painéis e no tabuleiro; guardado por aparelho
// (localStorage), nunca enviado ao servidor: scans, recortes e índice não mudam. Valor inicial: o desvio scan/arte
// medido (docs/estado-e-plano.md §3: L*scan ≈ 1,06·L*arte + 1,3, ≈ +5 L* uniforme; croma quase igual): brilho 0,92.
const COR_INICIAL = { b: 0.92, s: 1.0 };
const COR_TABULEIRO = true;              // F2: medido (DETALHE.md §9.2): no tabuleiro, 0 frames perdidos a arrastar e com a roda
function corGet() {
  try { const v = JSON.parse(lsGet("novo-cor") || "null"); if (v && Number.isFinite(v.b) && Number.isFinite(v.s)) return v; } catch (e) { /* inicial */ }
  return { ...COR_INICIAL };
}
function corApply(v) {
  const r = document.documentElement.style;
  r.setProperty("--cor-b", String(v.b)); r.setProperty("--cor-s", String(v.s));
  document.body.classList.toggle("cor-tabuleiro", COR_TABULEIRO);
}
function openDefinicoes() {
  let v = corGet();
  const set = (nv) => { v = nv; lsSet("novo-cor", JSON.stringify(v)); corApply(v); b.value = v.b; sa.value = v.s; };
  const b = h("input", { type: "range", id: "cor-b", min: 0.7, max: 1.3, step: 0.01, value: v.b, "aria-label": "Mais escuro ou mais claro" });
  const sa = h("input", { type: "range", id: "cor-s", min: 0.5, max: 1.5, step: 0.01, value: v.s, "aria-label": "Cor menos viva ou mais viva" });
  b.addEventListener("input", () => set({ b: Number(b.value), s: v.s }));
  sa.addEventListener("input", () => set({ b: v.b, s: Number(sa.value) }));
  const amostra = current() || null;
  const back = h("div", { class: "dlg-back", id: "definicoes", role: "dialog", "aria-modal": "true", "aria-labelledby": "def-titulo" });
  const close = () => back.remove();
  back.addEventListener("click", (e) => { if (e.target === back) close(); });
  back.append(h("div", { class: "dlg" },
    h("h3", { id: "def-titulo" }, "Definições"),
    h("h2", {}, "Cor das peças"),
    h("p", { class: "small muted" }, "Só muda como as peças aparecem neste aparelho (cartões, painéis e tabuleiro). Os scans e o que o programa compara ficam iguais."),
    amostra ? h("div", { class: "cor-amostra" }, h("img", { class: "peca-img", src: `/api/pieces/${amostra.piece}.png?pose=scan&size=240&v=${S.ver}`, alt: "" })) : null,
    h("div", { class: "slider" }, ico("sun"), b),
    h("div", { class: "slider-ends" }, h("span", {}, "mais escuro"), h("span", {}, "mais claro")),
    h("div", { class: "slider" }, ico("droplet"), sa),
    h("div", { class: "slider-ends" }, h("span", {}, "cor menos viva"), h("span", {}, "cor mais viva")),
    h("div", { class: "actions" },
      h("button", { class: "btn", type: "button", id: "cor-repor", onclick: () => set({ ...COR_INICIAL }) }, ico("undo-2"), "Repor"),
      h("button", { class: "btn primary", type: "button", id: "def-fechar", onclick: close }, "Fechar"))));
  document.body.append(back);
  b.focus();
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
      h("a", { class: "btn", href: "/" }, ico("layout-dashboard"), "Abrir a interface completa")));
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
      h("li", {}, h("button", { class: "btn primary big", type: "submit", id: "import-btn" }, ico("scan-line"), "Importar"))));
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
// A lupa mostra as propostas da peça e do lugar (F1c) numa caixa no topo do painel (#lupa-res), não só num aviso.
const nomePeca = (pc) => (pc && pc.lote !== null && pc.lote !== undefined ? `Saco ${pc.lote} · nº ${pc.n_no_lote ?? "?"}` : "Peça sem saco");
const GRUPO_TXT = { coloca_agora: "pôr agora: tem uma peça montada ao lado", guarda_posicao: "ainda sem peças ao lado: pôr no lugar, por confirmar" };
function propLine(e, quemTxt) {
  const inQ = queue().find((it) => it.piece === e.piece && it.cell && e.cell && it.cell[0] === e.cell[0] && it.cell[1] === e.cell[1]);
  const conf = inQ ? (isGuardar(inQ) ? "a confirmar por ti" : CONF_TXT[inQ.confianca]) : "a confirmar por ti";
  const li = h("li", { "data-piece": e.piece, "data-grupo": e.grupo || "" },
    h("span", {}, `${quemTxt}: ${GRUPO_TXT[e.grupo] || "proposta do programa"} (${conf}).`));
  if (inQ) li.append(h("button", { type: "button", class: "linkish", onclick: () => { closeLupa(); S.pick = inQ.piece; S.modo = "cartao"; showTab("montar"); renderMontar(); } }, "Ver o cartão"));
  return li;
}
function showLupa(titulo, linhas, props, kind) {
  const box = $("#lupa-res");
  box.replaceChildren(
    h("div", { class: "lupa-head" }, h("strong", {}, titulo), h("button", { type: "button", class: "btn", id: "lupa-fechar", onclick: closeLupa }, ico("x"), "Fechar")),
    ...linhas.map((t) => h("p", { class: "small" }, t)),
    props.length ? h("ul", { class: "lupa-props", id: "lupa-props" }, ...props) : h("p", { class: "small muted", id: "lupa-sem" }, "Sem propostas do programa."));
  box.dataset.kind = kind;
  box.hidden = false;
}
function closeLupa() { const b = $("#lupa-res"); b.hidden = true; b.replaceChildren(); }
async function findPiece(pid) {
  let p;
  try { p = await api(`/api/pieces/${pid}`); } catch (e) { toast(`Não encontrei «${pid}».`); return; }
  const pc = p.peca || p, nome = nomePeca(pc);
  const linhas = [];
  if (pc.estado === "colocada" && pc.celula) { showCell(pc.celula[0], pc.celula[1]); linhas.push(`Está no lugar: ${lugarTxt(pc.celula).toLowerCase()}.`); }
  else if (pc.estado === "posicao_conhecida" && pc.celula) { showCell(pc.celula[0], pc.celula[1]); linhas.push(`No lugar por confirmar: ${lugarTxt(pc.celula).toLowerCase()}, à espera de uma vizinha montada.`); }
  else if (pc.estado === "em_seccao") linhas.push("Está num grupo sem lugar (por agora só na interface completa).");
  else if (pc.estado === "descartada") linhas.push("Foi posta de lado.");
  else linhas.push("Ainda não tem lugar.");
  const withCell = (p.propostas || []).filter((e) => e.cell);
  const props = withCell.map((e) => propLine(e, lugarTxt(e.cell)));
  if (!pc.celula && withCell.length) showCell(withCell[0].cell[0], withCell[0].cell[1]);
  const inQ = queue().find((it) => it.piece === pid);
  if (inQ) { S.pick = pid; S.modo = "cartao"; showTab("montar"); renderMontar(); }
  showLupa(nome, linhas, props, "peca");
}
async function findPlace(l, c) {
  if (!S.board || l < 1 || c < 1 || l > S.rows || c > S.cols) { toast(`Linha ${l} · coluna ${c} fica fora do tabuleiro.`); return; }
  showCell(l, c);
  let d;
  try { d = await api(`/api/cell/${l}/${c}`); } catch (e) { toast(e.message, true); return; }
  const pc = d.peca;
  const linhas = [pc ? `Tem a peça do saco ${pc.lote ?? "—"} · nº ${pc.n_no_lote ?? "?"}.` : (d.estado === "vazia" ? "Ainda vazio." : "Marcado como montado.")];
  for (const k of d.conhecidas || []) linhas.push(`Por confirmar aqui: ${nomePeca(k)}.`);
  const props = (d.propostas || []).map((e) => propLine(e, nomePeca(e)));
  showLupa(lugarTxt([l, c]), linhas, props, "lugar");
}

// ------------------------------------------------------------ eventos do servidor
let reloadTimer = null;
function scheduleReload(board) {
  scheduleReload.board = scheduleReload.board || board;
  clearTimeout(reloadTimer);
  reloadTimer = setTimeout(async () => {
    const b = scheduleReload.board; scheduleReload.board = false;
    try {
      if (b) await loadBoard();
      await loadMontar();
      if (b && S.modo === "painel" && !S.busy) await refreshPainel();     // F2: o painel aberto mostra o lugar de agora
    } catch (e) { /* o próximo evento tenta de novo */ }
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
  $("#m-definicoes").onclick = () => { close(); openDefinicoes(); };
  const bind = (id, key, prop, after) => {
    const el = $(id); el.checked = !!S[prop];
    el.onchange = () => { S[prop] = el.checked; lsSet(key, el.checked ? "1" : "0"); after(); };
  };
  bind("#m-fantasmas", "novo-fantasmas", "showGhost", () => setView(S.vb));
  bind("#m-borda", "novo-borda", "showBorda", drawLayers);
  bind("#m-guardadas", "novo-por-confirmar", "showGuardadas", () => { drawLayers(); drawLegend(); });
}
function onKey(e) {
  if (e.key === "Escape") {
    if (!$("#lightbox").hidden) { $("#lightbox").hidden = true; return; }
    if ($("#definicoes")) { $("#definicoes").remove(); return; }
    if (S.modo === "por_mao") { cancelPorMao(); return; }            // F2: volta ao painel do lugar
    if (S.modo !== "cartao") { S.modo = "cartao"; S.painel = null; renderMontar(); }
    return;
  }
  const tag = (e.target && e.target.tagName) || "";
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
  if ((e.ctrlKey || e.metaKey) && (e.key === "z" || e.key === "Z")) { e.preventDefault(); doUndo(); return; }
  if (S.tab !== "montar" || e.ctrlKey || e.metaKey || e.altKey) return;
  const cur = current();
  if (S.modo === "cartao") {
    // o cartão sem vizinha montada não tem «Encaixa»: Enter não faz nada nesse cartão («Colocar aqui» é só por clique)
    if (e.key === "Enter" && tag !== "BUTTON" && tag !== "A") { e.preventDefault(); if (!isGuardar(cur)) doEncaixa(cur); }
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
  corApply(corGet());
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
