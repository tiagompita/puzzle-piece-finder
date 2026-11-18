/* GUI nova, grupos soltos no tabuleiro (F4, B4, etapa 1: desenho e lista; docs/gui/redesenho/F4_PLANO.md §1, §2, §4).
 * Carregado ANTES de novo.js: só declara funções (nada corre aqui); ``S``, ``h``, ``s``, ``api``, ``post``, ``ico``, ``plural``,
 * ``renderMontar``, ``drawLegend``, ``drawProgress``, ``toast`` e ``showCell`` vêm de core.js, board.js e novo.js e só se usam
 * depois de a página arrancar. Estado em ``S``: ``grupos`` (resposta de GET /api/grupos), ``vista`` («pecas» | «grupos»,
 * o comutador) e ``grupoSel`` (o grupo escolhido).
 *
 * - Q1 b: só o grupo escolhido (na vista «Grupos soltos») leva a imagem ``/api/grupos/{gid}.png?rot=``, o contorno violeta
 *   e a sombra; os outros grupos mostrados ficam com o contorno violeta ténue. Q4 b: o lugar provável a tracejado.
 * - A camada ``#lyr-grupos`` está por baixo dos alvos das sugestões (``#lyr-seguinte``, ``#lyr-alvo``) e não apanha o toque:
 *   o toque numa célula de um grupo passa por ``grupoEm`` em ``S.onBoardTap``.
 * - «Mostrar no tabuleiro» (Q3) grava a posição inicial com o centro da vista; NÃO entra no desfazer (C2, do Tiago).
 * - Os textos não mostram P####, G#### nem «âncora» (ESPEC §6): os ids só vão para atributos ``data-*`` e URLs.
 * Mover, rodar, fixar e soltar são das etapas 2 e 3. */
"use strict";

const GRP_VIOLETA = "#b9a3ff";
const grupo = (gid) => ((S.grupos && S.grupos.grupos) || []).find((g) => g.id === gid) || null;
const grupoEscolhido = () => (S.vista === "grupos" && S.grupoSel ? grupo(S.grupoSel) : null);
/** «3», «3 e 7», «3, 7 e 9». */
function listaE(xs) {
  const a = xs.map(String);
  return a.length <= 1 ? a.join("") : `${a.slice(0, -1).join(", ")} e ${a[a.length - 1]}`;
}
const mesmaPos = (a, b) => !!a && !!b && JSON.stringify(a.footprint) === JSON.stringify(b.footprint);

// ------------------------------------------------------------ dados (uma recarga de cada vez; um pedido a meio repete-se uma vez)
let gruposP = null, gruposDeNovo = false;
function loadGrupos() {
  if (gruposP) { gruposDeNovo = true; return gruposP; }
  gruposP = (async () => {
    try {
      do {
        gruposDeNovo = false;
        try { S.grupos = await api("/api/grupos"); S.gruposErro = null; } catch (e) { S.gruposErro = e.message; }
        if (S.grupoSel && !grupo(S.grupoSel)) S.grupoSel = null;
        drawGrupos(); drawVistaSw(); drawProgress(); drawLegend();
        if (S.vista === "grupos" && S.tab === "montar") renderMontar();
      } while (gruposDeNovo);
    } finally { gruposP = null; }
  })();
  return gruposP;
}

// ------------------------------------------------------------ comutador «Peça a peça · N | Grupos soltos · N»
function drawVistaSw() {
  const sw = $("#vista-sw");
  if (!sw) return;
  const nP = typeof queue === "function" ? queue().length : 0;
  const nG = S.grupos ? S.grupos.n_grupos : 0;
  const bp = $("#vista-pecas"), bg = $("#vista-grupos");
  bp.textContent = `Peça a peça · ${nP}`;
  bg.textContent = `Grupos soltos · ${nG}`;
  bp.setAttribute("aria-pressed", S.vista === "pecas" ? "true" : "false");
  bg.setAttribute("aria-pressed", S.vista === "grupos" ? "true" : "false");
}
function setVista(v) {
  if (S.vista === v) return;
  S.vista = v;
  drawVistaSw(); drawGrupos(); renderMontar();
}
function initVista() {
  $("#vista-pecas").onclick = () => setVista("pecas");
  $("#vista-grupos").onclick = () => setVista("grupos");
  drawVistaSw();
}

// ------------------------------------------------------------ tabuleiro (camada #lyr-grupos)
/** O contorno da união das células (só as arestas que não têm vizinha do mesmo grupo). */
function contornoD(fp) {
  const set = new Set(fp.map(([l, c]) => `${l},${c}`));
  let d = "";
  for (const [l, c] of fp) {
    const x0 = c - 1, x1 = c, y0 = (l - 1) * S.hr, y1 = l * S.hr;
    if (!set.has(`${l - 1},${c}`)) d += `M${x0} ${y0}H${x1}`;
    if (!set.has(`${l + 1},${c}`)) d += `M${x0} ${y1}H${x1}`;
    if (!set.has(`${l},${c - 1}`)) d += `M${x0} ${y0}V${y1}`;
    if (!set.has(`${l},${c + 1}`)) d += `M${x1} ${y0}V${y1}`;
  }
  return d;
}
function celulasEl(fp, klass, dx = 0, dy = 0) {
  const g = s("g", { class: klass });
  for (const [l, c] of fp) {
    g.append(s("rect", { x: (c - 1 + dx).toFixed(3), y: ((l - 1) * S.hr + dy * S.hr).toFixed(3), width: 1, height: S.hr.toFixed(4), class: "grupo-cel" }));
  }
  return g;
}
function grupoEl(g, esc) {
  const klass = ["grupo", esc ? "escolhido" : "tenue", g.sobreposto ? "sobreposto" : ""].filter(Boolean).join(" ");
  const el = s("g", { class: klass, "data-grupo": g.id, "data-n": g.n });
  const fp = g.footprint;
  if (esc) {
    el.append(celulasEl(fp, "grupo-sombra", 0.05, 0.08));            // a sombra: as células deslocadas (em unidades do tabuleiro, não px)
    el.append(celulasEl(fp, "grupo-fundo"));
    const im = g.imagem, p = g.posicao;
    if (im && p) {
      const [r0, q0] = im.origem_local, [rn, cn] = im.celulas_n, m = im.margem;
      el.append(s("image", { class: "grupo-img", href: `${im.url}&v=${S.ver}`, preserveAspectRatio: "none",
        x: (p.c0 + q0 - 1 - m).toFixed(3), y: ((p.l0 + r0 - 1 - m) * S.hr).toFixed(3), width: (cn + 2 * m).toFixed(3), height: ((rn + 2 * m) * S.hr).toFixed(3) }));
    }
  } else el.append(celulasEl(fp, "grupo-fundo"));
  el.append(s("path", { class: "grupo-contorno", d: contornoD(fp) }));
  return el;
}
/** O lugar provável do grupo escolhido (Q4 b): contorno tracejado, véu violeta e o rótulo; some quando o grupo já lá está. */
function provavelEl(g) {
  const lp = g.lugar_provavel;
  if (!lp || (g.mostrado && mesmaPos(g, lp))) return null;
  const el = s("g", { class: "grupo-provavel", "data-grupo": g.id });
  el.append(celulasEl(lp.footprint, "grupo-fundo"));
  el.append(s("path", { class: "grupo-contorno", d: contornoD(lp.footprint) }));
  const ls = lp.footprint.map((x) => x[0]), cs = lp.footprint.map((x) => x[1]);
  const x = (Math.min(...cs) - 1 + Math.max(...cs)) / 2, y = (Math.min(...ls) - 1) * S.hr - 0.12;
  const tag = s("g", { class: "prov-tag", transform: `translate(${x} ${y})` });
  tag.append(s("rect", { x: -0.8, y: -0.42, width: 1.6, height: 0.36, rx: 0.08 }), s("text", { x: 0, y: -0.17 }, document.createTextNode("Lugar provável")));
  el.append(tag);
  return el;
}
function drawGrupos() {
  const L = $("#lyr-grupos");
  if (!L) return;
  L.replaceChildren();
  const G = S.grupos;
  if (!G || !S.board) return;
  const esc = grupoEscolhido();
  for (const g of G.grupos) if (g.mostrado && g.footprint) L.append(grupoEl(g, !!esc && esc.id === g.id));
  const pv = esc ? provavelEl(esc) : null;
  if (pv) L.append(pv);
}
/** O grupo mostrado que contém a célula (para o toque no tabuleiro), ou null. */
function grupoEm(l, c) {
  const G = S.grupos;
  if (!G) return null;
  return G.grupos.find((g) => g.mostrado && g.footprint && g.footprint.some((x) => x[0] === l && x[1] === c)) || null;
}
/** A legenda do grupo solto (só quando há algum no tabuleiro). */
function legendaGrupo(L) {
  if (!S.grupos || !S.grupos.n_mostrados) return;
  const sw = s("svg", { class: "lg-sw", viewBox: "0 0 1 1", "aria-hidden": "true" });
  sw.append(s("rect", { x: 0.1, y: 0.1, width: 0.8, height: 0.8, class: "lg-grupo" }));
  L.append(h("span", { class: "lg", "data-legend": "grupo_solto" }, sw, "Grupo solto: ainda não conta como montado"));
}
const gruposTopo = () => (S.grupos && S.grupos.n_pecas ? ` · ${S.grupos.n_pecas} em grupos soltos` : "");

// ------------------------------------------------------------ painel (lista e grupo escolhido)
function estadoGrupo(g) {
  if (g.sobreposto) return "por cima de peças já montadas";
  return g.mostrado ? "ainda sem lugar certo no puzzle" : "ainda fora do tabuleiro";
}
function escolherGrupo(gid) {
  S.grupoSel = gid; S.vista = "grupos";
  drawVistaSw(); drawGrupos(); renderMontar();
  const t = $("#tab-montar"); if (t) t.scrollTop = 0;
}
function voltarLista() { S.grupoSel = null; drawGrupos(); renderMontar(); }
/** «Mostrar no tabuleiro» (Q3): grava a posição inicial (o servidor escolhe perto do centro da vista); não se desfaz (C2). */
async function mostrarGrupo(gid) {
  const v = S.vb, centro = [(v.y + v.h / 2) / S.hr + 0.5, v.x + v.w / 2 + 0.5];
  try {
    await post(`/api/grupos/${gid}/mostrar`, { centro });
  } catch (e) { toast(e.message, true); return; }
  S.grupoSel = gid; S.vista = "grupos";
  await loadGrupos();
  const g = grupo(gid);
  if (g && g.footprint && g.footprint.length) showCell(g.footprint[0][0], g.footprint[0][1]);
  drawVistaSw();
}
/** «Levar para o lugar provável»: leva o grupo (mostrando-o primeiro, se ainda não estava) à posição do candidato. */
async function levarGrupo(gid) {
  const g = grupo(gid), lp = g && g.lugar_provavel;
  if (!lp) return;
  const v = S.vb, centro = [(v.y + v.h / 2) / S.hr + 0.5, v.x + v.w / 2 + 0.5];
  try {
    if (!g.mostrado) await post(`/api/grupos/${gid}/mostrar`, { centro });
    await post(`/api/grupos/${gid}/mover`, { l0: lp.cell0[0], c0: lp.cell0[1], rot: lp.rot });
  } catch (e) { toast(e.message, true); }
  await loadGrupos();
  const g2 = grupo(gid);
  if (g2 && g2.footprint && g2.footprint.length) showCell(g2.footprint[0][0], g2.footprint[0][1]);
}
function grupoRow(g) {
  const sacos = g.sacos || [];
  const sub = sacos.length ? `${sacos.length === 1 ? "saco" : "sacos"} ${listaE(sacos)}` : "sem saco";
  return h("div", { class: "grp-row" + (S.grupoSel === g.id ? " on" : "") + (g.sobreposto ? " sobreposto" : ""), "data-grupo": g.id, role: "listitem" },
    h("button", { type: "button", class: "grp-open", onclick: () => escolherGrupo(g.id) },
      h("span", { class: "grp-n" }, plural(g.n, "peça", "peças")),
      h("span", { class: "grp-sub small muted" }, sub),
      h("span", { class: "grp-est small" + (g.sobreposto ? " aviso" : " muted") }, g.sobreposto ? "por cima de peças já montadas" : (g.mostrado ? "no tabuleiro" : "ainda fora do tabuleiro"))),
    h("button", { type: "button", class: "btn grp-mostrar", onclick: () => mostrarGrupo(g.id) }, ico("map-pin"), "Mostrar no tabuleiro"));
}
function nomePecaGrupo(p, i) {
  return p.lote !== null && p.lote !== undefined ? `Saco ${p.lote} · ${p.n_no_lote ?? "?"}` : `Sem saco · peça ${i + 1}`;
}
function grupoPainel(T, g) {
  const box = h("div", { class: "card grp-painel", "data-vista": "grupos", "data-grupo": g.id });
  box.append(h("h3", { class: "grp-titulo" }, `Grupo de ${plural(g.n, "peça", "peças")}`),
    h("div", { class: "grp-estado small muted" }, h("span", { class: "dot-violeta", "aria-hidden": "true" }), `Solto · ${estadoGrupo(g)}`));
  if (g.sobreposto) box.append(h("p", { class: "small aviso", id: "g-sobreposto" }, g.sobreposto.texto || "O grupo está por cima de peças já montadas."));
  const acts = h("div", { class: "actions" });
  acts.append(h("button", { type: "button", class: "btn big", id: "g-mostrar", onclick: () => mostrarGrupo(g.id) }, ico("map-pin"), g.mostrado ? "Ver no tabuleiro" : "Mostrar no tabuleiro"));
  box.append(acts);
  const lp = g.lugar_provavel;
  if (lp && !(g.mostrado && mesmaPos(g, lp))) box.append(h("div", { class: "actions" }, h("button", { type: "button", class: "btn big primary", id: "g-levar", onclick: () => levarGrupo(g.id) }, ico("locate-fixed"), "Levar para o lugar provável")));
  else if (lp) box.append(h("p", { class: "small muted", id: "g-no-lugar" }, "Está no lugar provável."));
  else box.append(h("p", { class: "small muted", id: "g-sem-lugar" }, "Ainda sem lugar provável fiável"));
  box.append(h("div", { class: "grp-pecas" }, h("div", { class: "small muted" }, "Peças do grupo"),
    h("div", { class: "grp-chips" }, (g.pecas || []).map((p, i) => h("span", { class: "grp-peca" }, nomePecaGrupo(p, i))))));
  box.append(h("div", { class: "links" }, h("button", { class: "linkish", type: "button", id: "grp-voltar", onclick: voltarLista }, ico("arrow-left"), "Voltar à lista")));
  T.append(box);
}
/** O conteúdo de #tab-montar na vista «Grupos soltos»: a lista, o painel do grupo escolhido ou o vazio. */
function renderGrupos(T) {
  const ult = typeof undoStrip === "function" ? undoStrip() : null;
  if (ult) T.append(ult);
  const G = S.grupos;
  if (!G) {
    T.append(h("div", { class: "empty", "data-vista": "grupos", "data-estado": S.gruposErro ? "erro" : "a_carregar" },
      h("strong", {}, S.gruposErro ? "Não consegui ler os grupos." : "A carregar…"), S.gruposErro ? h("p", {}, S.gruposErro) : null));
    return;
  }
  const g = grupoEscolhido();
  if (g) { grupoPainel(T, g); return; }
  if (!G.grupos.length) {
    T.append(h("div", { class: "empty", "data-vista": "grupos", "data-estado": "vazio" }, h("strong", {}, "Não há grupos soltos."),
      h("p", {}, "Quando houver peças que encaixam umas nas outras sem lugar no puzzle, aparecem aqui.")));
    return;
  }
  T.append(h("p", { class: "small muted grp-intro" }, "Peças soltas que encaixam umas nas outras, mesmo sem tocarem no que já montaste."));
  const ul = h("div", { class: "grp-lista", "data-vista": "grupos", role: "list" });
  for (const x of G.grupos) ul.append(grupoRow(x));
  T.append(ul);
}
