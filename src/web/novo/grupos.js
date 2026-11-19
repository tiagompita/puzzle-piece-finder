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
 * - Etapa 2: «Mover» (Ctrl+arrastar com o rato; botão «Mover» … «Feito», que é o único caminho no telemóvel) e «Rodar» (±90).
 *   O arrasto intercepta o ``pointerdown`` em captura, antes de board.js (que não muda: sem o ponteiro no seu mapa, o
 *   pan não arranca), encaixa às células com um ``transform`` no grupo e valida no cliente com o que já tem (tabuleiro,
 *   outros grupos): uma posição inválida volta atrás sem POST. Só uma posição válida escreve (``POST …/mover``, que
 *   copia o ``rodado`` da linha atual; «Rodar» manda ``{rodar}``). O desfazer (faixa e Ctrl+Z, um nível) é o ``mover``
 *   inverso com a ``anterior`` da resposta e o ``rodado`` explícito dela; «Mostrar» continua fora dele (C2).
 *   Estado: ``S.mover`` = ``{gid, dl, dc}`` (o «Mover» ativo e o deslocamento pendente, em células) ou null.
 * - Etapa 3: «Fixar aqui» (confirmação de um clique, Q8 a; ``POST …/fixar`` sem corpo), o aviso depois de fixar (Q9 c: contorno
 *   âmbar nas células das peças que discordam, «Esta peça diz outra rotação», «Desfazer» = ``unanchor``) em ``S.fixado``, e o
 *   encaixe do arrasto pela célula debaixo do ponteiro (B2). «Tirar o grupo inteiro do lugar» é o do painel da peça (F2):
 *   o servidor deixa o grupo onde estava fixado (Q10 a) e ``grupos_changed`` traz-o de volta à camada.
 *   Estado novo: ``S.fixarConf`` (o grupo à espera da confirmação) e ``S.fixado`` ({n, confianca, discordam: [[l, c]]}). */
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
        if (S.mover && (!grupo(S.mover.gid) || !grupo(S.mover.gid).mostrado)) S.mover = null;
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
/** O deslocamento pendente do «Mover» (em células) para o grupo ``id``: [dl, dc]. */
const pendente = (id) => (arrasto && arrasto.gid === id ? [arrasto.dl, arrasto.dc] : (S.mover && S.mover.gid === id ? [S.mover.dl, S.mover.dc] : [0, 0]));
/** Põe (ou tira, se for 0 0) o ``transform`` que mostra o grupo deslocado ``dl`` linhas e ``dc`` colunas. */
function deslocar(el, dl, dc) {
  if (!el) return;
  if (!dl && !dc) el.removeAttribute("transform");
  else el.setAttribute("transform", `translate(${dc} ${(dl * S.hr).toFixed(4)})`);
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
  const [dl, dc] = pendente(g.id);
  deslocar(el, dl, dc);
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
  // o «Mover» só vive no painel do próprio grupo: sair de lá (outra vista, outro grupo, a lista) repõe a posição
  if (S.mover && (S.vista !== "grupos" || S.grupoSel !== S.mover.gid || !grupo(S.mover.gid))) S.mover = null;
  if (S.fixarConf && S.grupoSel !== S.fixarConf) S.fixarConf = null;
  svg().classList.toggle("modo-mover", !!S.mover);
  L.replaceChildren();
  const G = S.grupos;
  if (!G || !S.board) return;
  const esc = grupoEscolhido();
  for (const g of G.grupos) if (g.mostrado && g.footprint) L.append(grupoEl(g, !!esc && esc.id === g.id));
  const pv = esc ? provavelEl(esc) : null;
  if (pv) L.append(pv);
  if (S.fixado && S.fixado.discordam.length) L.append(celulasEl(S.fixado.discordam, "grupo-aviso"));     // Q9 c: a peça que discorda, a âmbar
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
  if (S.grupoSel !== gid) { S.grupoAviso = null; S.fixarConf = null; }
  S.grupoSel = gid; S.vista = "grupos";
  drawVistaSw(); drawGrupos(); renderMontar();
  const t = $("#tab-montar"); if (t) t.scrollTop = 0;
}
function voltarLista() { S.grupoSel = null; S.grupoAviso = null; S.fixarConf = null; drawGrupos(); renderMontar(); }
/** «Mostrar no tabuleiro» (Q3): grava a posição inicial (o servidor escolhe perto do centro da vista); não se desfaz (C2).
 * Num grupo que já está mostrado («Ver no tabuleiro») não escreve nada: só leva a vista até lá. */
async function mostrarGrupo(gid) {
  const g0 = grupo(gid);
  if (g0 && g0.mostrado && g0.footprint && g0.footprint.length) {
    S.grupoSel = gid; S.vista = "grupos";
    drawVistaSw(); drawGrupos(); renderMontar();
    showCell(g0.footprint[0][0], g0.footprint[0][1]);
    return;
  }
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
/** O pedido inverso de uma escrita de posição: um ``mover`` de volta à ``anterior`` da resposta, com o ``rodado`` dela
 * explícito (o desfazer de um «Rodar» repõe o valor antigo, C1). */
function undoGrupo(gid, msg, ant) {
  return { tipo: "grupo", painel: true, msg, depois: loadGrupos,
    inversa: [{ url: `/api/grupos/${gid}/mover`, body: { l0: ant.l0, c0: ant.c0, rot: ant.rot, rodado: !!ant.rodado } }] };
}
/** Uma escrita de posição desfazível (``POST …/mover``): trava os botões, grava, deixa a faixa «Desfazer» e recarrega os
 * grupos. ``antes``: um passo a fazer primeiro (mostrar o grupo). Devolve true se gravou. Uma recusa do servidor fica no
 * painel (``S.grupoAviso``) e num aviso; a posição não muda. */
async function gravarGrupo(gid, body, msg, antes = null) {
  if (S.busy) return false;
  lockButtons(true);
  let ok = false;
  try {
    if (antes) await antes();
    const r = await post(`/api/grupos/${gid}/mover`, body);
    S.undo = undoGrupo(gid, msg, r.anterior);
    S.grupoAviso = null;
    toastUndo(msg);
    ok = true;
  } catch (e) { S.grupoAviso = e.message; toast(e.message, true); }
  finally { lockButtons(false); }
  await loadGrupos();
  return ok;
}
/** «Levar para o lugar provável»: leva o grupo (mostrando-o primeiro, se ainda não estava) à posição do candidato. A rotação é
 * a do solver, por isso manda ``rodado: false``; desfaz-se pela ``anterior``. */
async function levarGrupo(gid) {
  const g = grupo(gid), lp = g && g.lugar_provavel;
  if (!lp) return;
  const v = S.vb, centro = [(v.y + v.h / 2) / S.hr + 0.5, v.x + v.w / 2 + 0.5];
  const ok = await gravarGrupo(gid, { l0: lp.cell0[0], c0: lp.cell0[1], rot: lp.rot, rodado: false }, "Grupo levado para o lugar provável.",
    g.mostrado ? null : () => post(`/api/grupos/${gid}/mostrar`, { centro }));
  const g2 = grupo(gid);
  if (ok && g2 && g2.footprint && g2.footprint.length) showCell(g2.footprint[0][0], g2.footprint[0][1]);
}

// ------------------------------------------------------------ fixar (Q8 a, Q9 c) e o aviso
const pecasTxt = (n) => plural(n, "peça", "peças");
function pedirFixar(gid) {
  const g = grupo(gid);
  if (!g || g.sobreposto || S.busy) return;
  S.fixarConf = gid; S.grupoAviso = null;
  renderMontar();
  const c = $("#g-confirma"); if (c) c.scrollIntoView({ block: "nearest" });      // a pergunta inteira à vista (telemóvel)
}
function cancelarFixar() { S.fixarConf = null; renderMontar(); }
/** Fixar o grupo na posição em que está (o corpo do pedido é ignorado pelo servidor). A resposta diz que peças discordam; os ids
 * só servem para achar as células (a ordem de ``g.pecas`` é a de ``g.footprint``) e nunca vão para o texto. */
async function fixarGrupo(gid) {
  const g = grupo(gid);
  if (!g || S.busy) return;
  const celula = {};
  (g.pecas || []).forEach((p, i) => { celula[p.id] = g.footprint[i]; });
  const n = g.n;
  lockButtons(true);
  S.pendente = "A fixar o grupo…"; S.fixarConf = null; S.fixado = null;
  renderMontar();
  try {
    const r = await post(`/api/grupos/${gid}/fixar`, {});
    writeFailed(r);
    const dis = Object.entries(r.vizinhas_pecas || {}).filter(([, w]) => w === "discordam").map(([pid]) => celula[pid]).filter(Boolean);
    S.fixado = { n, confianca: r.confianca, vizinhas: r.vizinhas, discordam: dis };
    const msg = `Grupo de ${pecasTxt(n)} fixado.`;
    // o desfazer é a inversa completa: ``unanchor`` e, se a rotação era a do Tiago (``rot_fonte`` tiago), um «Mover» para o
    // mesmo sítio com ``rodado: true``, para voltar a fixar dar tiago outra vez (M4, decisão do Tiago 2026-11-19; exceção à C1)
    const inversa = [confirmReq({ acao: "unanchor", section: gid })];
    if (r.rot_fonte === "tiago" && r.posicao) {
      inversa.push({ url: `/api/grupos/${gid}/mover`, body: { l0: r.posicao.l0, c0: r.posicao.c0, rot: r.posicao.rot, rodado: true } });
    }
    S.undo = { tipo: "fixar", painel: true, msg, inversa,
      depois: async () => { S.fixado = null; S.grupoSel = gid; S.vista = "grupos"; await loadGrupos(); drawVistaSw(); } };
    S.pendente = null; S.grupoSel = null;
    toastUndo(msg);
    await afterWrite();
  } catch (e) { S.pendente = null; S.grupoAviso = e.message; toast(e.message, true); }
  finally { lockButtons(false); }
  await loadGrupos();
  const t = $("#tab-montar"); if (t) t.scrollTop = 0;                  // o cartão do que aconteceu fica à vista
}
function fecharFixado() { S.fixado = null; drawGrupos(); renderMontar(); }
/** O cartão que fica depois de fixar: o que aconteceu, em palavras simples, e «Desfazer». */
function fixadoCartao() {
  const f = S.fixado;
  if (!f) return null;
  const nd = f.discordam.length;
  const box = h("div", { class: "card grp-fixado", id: "g-fixado", "data-confianca": f.confianca }, h("strong", {}, `Grupo de ${pecasTxt(f.n)} fixado.`));
  if (f.vizinhas === "discordam") {
    box.append(h("p", { class: "small aviso", id: "g-fixado-aviso", role: "alert" }, "As peças ao lado dizem outra rotação."),
      h("p", { class: "small", id: "g-fixado-esta" }, nd > 1 ? "Estas peças dizem outra rotação: estão marcadas a âmbar no tabuleiro." : "Esta peça diz outra rotação: está marcada a âmbar no tabuleiro."));
  }
  box.append(h("p", { class: "small muted", id: "g-fixado-rot" }, f.confianca === "confirmado" ? "A rotação está confirmada." : "A rotação ainda está por confirmar: vê na mesa se as peças estão nesta rotação."));
  box.append(h("div", { class: "actions" },
    h("button", { type: "button", class: "btn", id: "g-fixado-desfazer", onclick: () => doUndo() }, ico("undo-2"), "Desfazer"),
    h("button", { type: "button", class: "btn", id: "g-fixado-ok", onclick: fecharFixado }, "Está bem")));
  return box;
}

// ------------------------------------------------------------ mover (Ctrl+arrastar; «Mover» … «Feito») e rodar
function entrarMover(gid) {
  S.mover = { gid, dl: 0, dc: 0 }; S.grupoAviso = null; S.fixarConf = null;
  drawGrupos(); renderMontar();
}
/** Sair do «Mover» sem gravar: o grupo volta à posição gravada. */
function cancelarMover() {
  if (!S.mover) return;
  S.mover = null; arrasto = null;
  drawGrupos(); renderMontar();
}
/** «Feito»: grava a posição pendente (uma só escrita); sem deslocamento, só sai do modo. */
async function feitoMover() {
  const m = S.mover, g = m && grupo(m.gid);
  if (!m || !g || (!m.dl && !m.dc)) { cancelarMover(); return; }
  const p = g.posicao;
  S.mover = null;                                  // o transform fica no desenho até a recarga trazer a posição gravada
  await gravarGrupo(g.id, { l0: p.l0 + m.dl, c0: p.c0 + m.dc, rot: p.rot }, "Grupo movido.");
}
async function rodarGrupo(gid, d) {
  S.grupoAviso = null;
  await gravarGrupo(gid, { rodar: d }, "Grupo rodado.");
}

/** Porque é que o grupo ``gid`` deslocado ``dl`` linhas e ``dc`` colunas não cabe (as frases do servidor, na mesma ordem:
 * fora da grelha, peça colocada, lugar marcado, outro grupo), ou null se cabe. É só um pré-teste: o servidor valida de novo. */
function motivoNaoCabe(gid, dl, dc) {
  const g = grupo(gid), B = S.board;
  if (!g || !g.footprint || !B) return null;
  const cel = g.footprint.map(([l, c]) => [l + dl, c + dc]);
  for (const [l, c] of cel) if (l < 1 || c < 1 || l > S.rows || c > S.cols) return "Não cabe aqui: sai do tabuleiro.";
  for (const [l, c] of cel) {
    const x = B.cells[l - 1][c - 1];
    if (x.estado === "colocada") return `Não cabe aqui: a linha ${l}, coluna ${c} já tem uma peça.`;
    if (x.estado === "ocupada_legado" && x.fonte !== "foto") return `Não cabe aqui: a linha ${l}, coluna ${c} está marcada como montada.`;
  }
  const meus = new Set(cel.map(([l, c]) => `${l},${c}`));
  for (const o of ((S.grupos && S.grupos.grupos) || [])) {
    if (o.id === gid || !o.mostrado || !o.footprint) continue;
    for (const [l, c] of o.footprint) if (meus.has(`${l},${c}`)) return `Não cabe aqui: fica por cima de outro grupo (linha ${l}, coluna ${c}).`;
  }
  return null;
}
/** O grupo mostrado que está na célula (l, c) tal como se vê (com o deslocamento pendente do «Mover»), ou null. */
function grupoVisivelEm(l, c) {
  const G = S.grupos;
  if (!G) return null;
  const esc = grupoEscolhido();
  const nele = (g) => { const [dl, dc] = pendente(g.id); return g.mostrado && g.footprint && g.footprint.some((x) => x[0] + dl === l && x[1] + dc === c); };
  if (esc && nele(esc)) return esc;
  return G.grupos.find(nele) || null;
}

let arrasto = null, abandonarArrasto = () => {};
function initArrasto() {
  const noTabuleiro = (e) => { const sv = svg(); return !!sv && (e.target === sv || sv.contains(e.target)); };
  const aplicar = () => {
    const a = arrasto;
    if (!a.el || !a.el.isConnected) a.el = $(`#lyr-grupos [data-grupo="${a.gid}"]`);
    deslocar(a.el, a.dl, a.dc);
    if (a.el) a.el.classList.toggle("invalido", !!(a.dl || a.dc) && !!motivoNaoCabe(a.gid, a.dl, a.dc));
  };
  // captura em janela: corre antes do ``pointerdown`` de board.js e, ao parar a propagação, o pan nem arranca
  window.addEventListener("pointerdown", (e) => {
    if (!noTabuleiro(e)) return;
    // um dedo primário novo com um arrasto por acabar: o ``pointerup`` do anterior perdeu-se; repõe o grupo e segue (M3)
    if (e.pointerType === "touch" && e.isPrimary && arrasto && arrasto.id !== e.pointerId) abandonarArrasto();
    if (arrasto) { e.stopPropagation(); e.preventDefault(); return; }       // um 2.º ponteiro durante o arrasto não faz pinça
    if (e.pointerType === "touch" && !e.isPrimary) return;                 // um 2.º dedo é do board.js (pinça), nunca arrasto (M2)
    if (S.gesto) return;                                                   // o board.js já tem um gesto em curso
    if (e.pointerType === "mouse" && e.button !== 0) return;
    const ctrl = e.pointerType === "mouse" && (e.ctrlKey || e.metaKey);
    if (!ctrl && !S.mover) return;
    const p = clientToBoard(e.clientX, e.clientY);
    const g = grupoVisivelEm(Math.floor(p.y / S.hr) + 1, Math.floor(p.x) + 1);
    if (!g || (S.mover && g.id !== S.mover.gid)) return;                    // fora do grupo: o tabuleiro faz o que faz sempre
    e.stopPropagation(); e.preventDefault();
    if (S.busy) return;                                                    // a gravar: nem arranca (M4)
    try { svg().setPointerCapture(e.pointerId); } catch (err) { /* o ponteiro já acabou */ }
    if (!S.mover && (S.vista !== "grupos" || S.grupoSel !== g.id)) escolherGrupo(g.id);   // o escolhido é o que leva a imagem
    const [dl, dc] = pendente(g.id);
    arrasto = { id: e.pointerId, gid: g.id, c0: [Math.floor(p.y / S.hr), Math.floor(p.x)], base: [dl, dc], dl, dc, el: null, modo: !!S.mover };
    aplicar();
  }, true);
  window.addEventListener("pointermove", (e) => {
    const a = arrasto;
    if (!a || e.pointerId !== a.id) return;
    const p = clientToBoard(e.clientX, e.clientY);
    // B2: o encaixe é pela célula debaixo do ponteiro (a de agora menos a do ``pointerdown``), não um arredondamento em px
    const dl = a.base[0] + Math.floor(p.y / S.hr) - a.c0[0], dc = a.base[1] + Math.floor(p.x) - a.c0[1];
    if (dl === a.dl && dc === a.dc) return;
    a.dl = dl; a.dc = dc;
    aplicar();
  });
  abandonarArrasto = () => {
    const a = arrasto;
    if (!a) return;
    arrasto = null;
    const el = a.el && a.el.isConnected ? a.el : $(`#lyr-grupos [data-grupo="${a.gid}"]`);
    if (el) { el.classList.remove("invalido"); deslocar(el, a.base[0], a.base[1]); }
  };
  const fim = (e) => {
    const a = arrasto;
    if (!a || e.pointerId !== a.id) return;
    arrasto = null;
    try { svg().releasePointerCapture(a.id); } catch (err) { /* já solto */ }
    const el = a.el && a.el.isConnected ? a.el : $(`#lyr-grupos [data-grupo="${a.gid}"]`);
    if (el) el.classList.remove("invalido");
    const g = grupo(a.gid);
    if (e.type !== "pointerup" || !g || (a.dl === a.base[0] && a.dc === a.base[1])) {       // sem movimento (ou cancelado): fica como estava
      deslocar(el, a.base[0], a.base[1]);
      return;
    }
    const porque = motivoNaoCabe(a.gid, a.dl, a.dc);
    if (porque) { deslocar(el, a.base[0], a.base[1]); S.grupoAviso = porque; toast(porque, true); if (S.vista === "grupos") renderMontar(); return; }
    if (S.busy) { deslocar(el, a.base[0], a.base[1]); toast("Espera um momento…", true); return; }   // a gravar outra coisa (M4)
    S.grupoAviso = null;
    if (a.modo) {                                                           // «Mover»: fica pendente até ao «Feito»
      if (S.mover && S.mover.gid === a.gid) { S.mover.dl = a.dl; S.mover.dc = a.dc; } else deslocar(el, 0, 0);   // o modo acabou a meio (M1)
      return;
    }
    const pos = g.posicao;
    gravarGrupo(a.gid, { l0: pos.l0 + a.dl, c0: pos.c0 + a.dc, rot: pos.rot }, "Grupo movido.");
  };
  window.addEventListener("pointerup", fim);
  window.addEventListener("pointercancel", fim);
  window.addEventListener("lostpointercapture", fim);                       // tratado como cancelamento (M3)
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
  if (g.mostrado) {
    const mod = !!S.mover && S.mover.gid === g.id;
    const flip = ico("rotate-cw"); flip.classList.add("flip");
    const conf = S.fixarConf === g.id && !mod;
    if (conf) {
      box.append(h("div", { class: "card grp-confirma", id: "g-confirma" },
        h("p", { id: "g-confirma-txt" }, `Fixar o grupo de ${pecasTxt(g.n)} aqui? Confirma na mesa que está nesta rotação.`),
        h("div", { class: "actions" },
          h("button", { type: "button", class: "btn big primary", id: "g-fixar-sim", onclick: () => fixarGrupo(g.id) }, ico("check"), "Fixar"),
          h("button", { type: "button", class: "btn big", id: "g-fixar-nao", onclick: cancelarFixar }, ico("x"), "Cancelar"))));
    }
    if (!conf) box.append(mod
      ? h("div", { class: "actions grp-barra", id: "g-barra" },
          h("button", { type: "button", class: "btn big primary", id: "g-feito", onclick: feitoMover }, ico("check"), "Feito"),
          h("button", { type: "button", class: "btn big", id: "g-cancelar", onclick: cancelarMover }, ico("x"), "Cancelar"))
      : h("div", { class: "actions grp-barra", id: "g-barra" },
          h("button", { type: "button", class: "btn big", id: "g-mover", onclick: () => entrarMover(g.id) }, "Mover"),
          h("button", { type: "button", class: "btn big", id: "g-rodar-esq", "aria-label": "Rodar para a esquerda", onclick: () => rodarGrupo(g.id, -90) }, flip, "Rodar"),
          h("button", { type: "button", class: "btn big", id: "g-rodar-dir", "aria-label": "Rodar para a direita", onclick: () => rodarGrupo(g.id, 90) }, ico("rotate-cw"), "Rodar")));
    if (!conf && !mod) {
      const fx = h("button", { type: "button", class: "btn big primary", id: "g-fixar", onclick: () => pedirFixar(g.id) }, ico("check"), "Fixar aqui");
      if (g.sobreposto) { fx.disabled = true; fx.setAttribute("aria-describedby", "g-sobreposto"); }
      box.append(h("div", { class: "actions" }, fx));
    }
    box.append(h("p", { class: "small muted", id: "g-dica" }, mod ? "Arrasta o grupo no tabuleiro e toca em «Feito»." : "No computador: Ctrl + arrastar move o grupo."));
  }
  if (S.grupoAviso) box.append(h("p", { class: "small aviso", id: "g-aviso", role: "alert" }, S.grupoAviso));
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
  const fx = fixadoCartao();
  if (fx) T.append(fx);
  const repete = !!fx && S.undo && S.undo.tipo === "fixar" && !S.pendente;          // o cartão já traz o «Desfazer»
  const ult = typeof undoStrip === "function" && !repete ? undoStrip() : null;
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
