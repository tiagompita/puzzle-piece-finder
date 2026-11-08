/* Molde do buraco (M11, src/fit.py): «Candidatas para este buraco» na gaveta de uma célula vazia com ≥ 1 vizinha
 * montada, as sugestões `alta` em «Vai buscar» (M11_CRITERIOS §8: a rank 1 de um buraco `alta`, coerente com a afetação
 * conjunta; contador acertos/falhas/total com Wilson 95 % e regra de pausa 3 em 20), a página «Buracos» (média, baixa
 * = vizinha única, sem candidata fiável; 3 melhores por buraco, «Não encaixa» em um clique) e a camada #hole-layer no
 * tabuleiro. Confirmar/rejeitar grava hole_confirmed/hole_rejected (rank, custo, margem, confiança, versão do fit): é a
 * verdade de terreno de `python -m src.fit --relatorio`. Usa globais de app.js ($, $$, h, s, S, api, toast, fmt,
 * cellTxt, openCell, fitRect, refreshAfterWrite, reportButton, showTab, miniMap). Nada da simetria do puzzle está aqui.
 */
"use strict";

const HOLE_CONF_TXT = { alta: "confiança alta", media: "confiança média", sem: "sem candidata fiável" };
const HOLE_CONF_SHORT = { alta: "alta", media: "média", sem: "sem fiável" };
const HOLE_SPAN = 1.8;          // células: o PNG da peça (pose=scan) tem o centro do corpo no meio e cobre 1,8 células
/** Rótulo da página «Buracos» (decisão de GUI, M11_CRITERIOS §8): `media` com 1 vizinha mostra-se como «baixa». */
const HOLE_GROUP_TXT = { alta_pausa: "alta · em pausa", alta_buscar: "alta · em «Vai buscar»", conflito: "alta · afetação em conflito",
  media: "média", baixa: "baixa (1 vizinha)", sem: "sem candidata fiável" };
const HOLE_GROUP_HELP = {
  alta_pausa: "≥ 3 rejeições nas últimas 20 decisões alta: estas sugestões saíram de «Vai buscar» até as reativares.",
  alta_buscar: "já estão em «Vai buscar»; ficam aqui só para referência.",
  conflito: "a candidata nº 1 ficou atribuída a outro buraco na afetação conjunta: não é sugestão.",
  media: "≥ 2 vizinhas mas margem < 1,5, ou candidata única com margem: confirma pelo encaixe físico.",
  baixa: "vizinha única: o molde não chega para decidir; nunca é alta.",
  sem: "nenhuma solta passa a rejeição com margem; as 3 mais próximas ficam só para orientar.",
};

// ------------------------------------------------------------ dados
async function loadHoles() {
  const d = await api("/api/holes");
  S.holes = d;
  renderHolesTab();
  renderHolesBadge();
  return d;
}
const altaInfo = () => (S.fetch && S.fetch.buracos_alta) || null;
/** Sugestões `alta` para «Vai buscar» (sem as fundidas com uma proposta de gémea: essas são um só cartão). */
function altaEntries() {
  const a = altaInfo();
  if (!a || a.em_pausa) return [];
  return (a.entries || []).filter((e) => !e.fundida_com_gemea);
}
function altaFusedFor(e) {
  const a = altaInfo();
  if (!a || !e || !e.cell) return null;
  return (a.entries || []).find((x) => x.fundida_com_gemea && x.piece === e.piece && x.cell[0] === e.cell[0] && x.cell[1] === e.cell[1]) || null;
}
function renderHolesBadge() {
  const r = (S.holes && S.holes.resumo) || {};
  for (const b of $$("[data-holes-entry] b")) b.textContent = r.alta_m2 ? String(r.alta_m2) : "";
}
/** Entrada para a secção «Buracos» (não é uma aba do topo: a barra está dimensionada para 6; também pela pesquisa «buracos»). */
function holesEntry() {
  const r = (S.holes && S.holes.resumo) || {};
  const pc = r.por_confianca || {};
  const n = (pc.media || 0) + (pc.sem || 0);
  return h("div", { class: "holes-entry" },
    h("button", { class: "btn slim", type: "button", "data-holes-entry": "1", title: "média, baixa (1 vizinha) e sem candidata fiável: as 3 melhores por buraco",
      onclick: () => showTab("buracos") }, "Buracos: média, baixa e sem fiável ", h("b", {}, n ? String(n) : "")),
    h("span", { class: "small muted" }, " «se não for esta, talvez seja uma destas» · pesquisa: «buracos»"));
}
function holeConfChip(conf, m) {
  const cls = conf === "alta" ? "chip ok" : (conf === "media" ? "chip mid" : "chip sem");
  const txt = m === 1 && conf !== "sem" ? `${HOLE_CONF_SHORT[conf]} · 1 vizinha: baixa` : HOLE_CONF_SHORT[conf];
  return h("span", { class: cls, "data-conf": conf, title: HOLE_CONF_TXT[conf] }, txt);
}
/** Chip das sugestões por buraco em «Vai buscar» (distinto do .tag da decisão da gémea). */
function holeSugChip(e) {
  const hl = (e && e.hole) || {};
  return h("span", { class: "chip buraco", "data-chip": "buraco", title: `molde do buraco: ${hl.m || "?"} vizinhas, custo ${fmt(hl.J, 2)}, margem ${fmtMargin(hl.margem)}, ${hl.fit_version || ""}` }, "por buraco · alta");
}
const fmtMargin = (m) => (m === null || m === undefined ? "—" : (m > 999 ? "> 999" : fmt(m, 2)));
const altaPct = (c) => (c && c.precisao !== null && c.precisao !== undefined ? `${fmt(100 * c.precisao, 0)} %` : "—");
const altaIc = (c) => (c && c.ic95 ? ` (IC 95 % ${fmt(100 * c.ic95[0], 0)}–${fmt(100 * c.ic95[1], 0)} %)` : "");
/** Linha de estado das sugestões por buraco: a calcular (tiras n/N) · contador acertos/falhas/total com Wilson · aviso de pausa + «Reativar». */
function altaBanner(where) {
  const a = altaInfo();
  const box = h("div", { class: "alta-banner", "data-alta": where });
  if (!a) return box;
  if (a.a_calcular) {
    const p = S.holesProgress || a.progresso;
    box.append(h("p", { class: "small muted alta-calc" }, "buracos: a calcular" + (p && p.N ? ` tiras ${p.n}/${p.N} (${fmt(p.segundos, 0)} s)` : " (primeira vez: alguns minutos)")));
    return box;
  }
  if (a.erro) { box.append(h("p", { class: "small muted" }, `buracos: sem ranking (${a.erro})`)); return box; }
  const c = a.contador;
  const n = (a.entries || []).length;
  box.append(h("p", { class: "small alta-count", "data-acertos": c ? c.acertos : "", "data-falhas": c ? c.falhas : "", "data-total": c ? c.total : "" },
    h("span", { class: "chip buraco" }, "por buraco · alta"),
    ` ${a.em_pausa ? "em pausa" : `${n} sugest${n === 1 ? "ão" : "ões"}`}`,
    c ? ` · acertos ${c.acertos} / falhas ${c.falhas} / total ${c.total} · precisão ${altaPct(c)}${altaIc(c)}` : "",
    c && c.janela ? h("span", { class: "muted" }, ` · últimas ${c.janela.n}: ${c.janela.falhas} falha${c.janela.falhas === 1 ? "" : "s"} (pausa a partir de ${c.janela.max_falhas} em ${c.janela.tamanho})`) : null));
  if (a.em_pausa) {
    box.append(h("p", { class: "note alta-pause hole-warn" },
      h("strong", {}, `≥ ${c.janela.max_falhas} rejeições nas últimas ${c.janela.n} decisões alta: `),
      "as sugestões por buraco saíram de «Vai buscar» (estão na página «Buracos», grupo «alta · em pausa») até as reativares. ",
      h("button", { class: "btn slim", type: "button", "data-alta-reativar": "1", onclick: (ev) => altaResume(ev.currentTarget) }, "Reativar sugestões alta")));
  }
  if (a.conflitos && a.conflitos.length && where === "buracos") {
    box.append(h("p", { class: "small muted" }, `${a.conflitos.length} buraco(s) alta com a candidata nº 1 atribuída a outro buraco (afetação conjunta): fora das sugestões.`));
  }
  return box;
}
async function altaResume(btn) {
  if (btn) { btn.disabled = true; btn.textContent = "a gravar…"; }
  try {
    const r = await api("/api/holes/alta/reativar", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) });
    toast(`Sugestões alta reativadas (acertos ${r.contador.acertos} / falhas ${r.contador.falhas} / total ${r.contador.total}; a janela recomeça agora)`);
    await refreshAfterWrite();
    loadHoles().catch(() => {});
  } catch (e) {
    toast(e.message, true);
    if (btn) { btn.disabled = false; btn.textContent = "Reativar sugestões alta"; }
  }
}
/** Progresso das tiras (SSE holes_progress): só a linha de estado muda. */
function renderAltaStatus() {
  for (const el of $$(".alta-banner")) el.replaceWith(altaBanner(el.dataset.alta));
}

// ------------------------------------------------------------ desenho (mini-SVG do cartão e camada do tabuleiro)
function holePath(pts) { return "M" + pts.map(([x, y]) => `${x.toFixed(4)} ${y.toFixed(4)}`).join("L") + "Z"; }
/** SVG (unidades de célula, 3 × 3 células à volta do buraco) com as vizinhas (ciano) e a candidata (âmbar) no buraco. */
function holeMiniSvg(hd, cell, cand, dr) {
  const hr = dr.hr || S.hr;
  const [l, c] = cell;
  const vb = `${c - 2} ${(l - 2) * hr} 3 ${3 * hr}`;
  const svg = s("svg", { class: "hole-mini", viewBox: vb, role: "img", "aria-label": `candidata ${cand ? cand.piece : "—"} no buraco ${cellTxt(cell)}` });
  svg.append(s("rect", { x: c - 1, y: (l - 1) * hr, width: 1, height: hr, class: "hole-cell" }));
  for (const d of ["N", "E", "S", "W"]) {
    const n = dr.vizinhas && dr.vizinhas[d];
    if (!n || !n.contorno || !n.contorno.length) continue;
    svg.append(s("path", { class: "hole-neigh", d: holePath(n.contorno), transform: n.svg.transform }));
  }
  if (cand) {
    const g = s("g", { transform: cand.svg.transform });
    g.append(s("image", { href: `${cand.img}&v=${S.ver}`, x: -HOLE_SPAN / 2, y: -HOLE_SPAN / 2, width: HOLE_SPAN, height: HOLE_SPAN, opacity: 0.9 }));
    g.append(s("path", { class: "hole-cand", d: holePath(cand.contorno) }));
    svg.append(g);
  }
  return svg;
}
/** Candidata desenhada sobre o tabuleiro (#hole-layer), com as vizinhas; limpa com holeLayerClear(). */
function holeShowOnBoard(hd, idx) {
  const lay = $("#hole-layer");
  if (!lay) return;
  lay.replaceChildren();
  const dr = hd.desenho || {};
  const [l, c] = hd.cell;
  for (const d of ["N", "E", "S", "W"]) {
    const n = dr.vizinhas && dr.vizinhas[d];
    if (!n || !n.contorno || !n.contorno.length) continue;
    lay.append(s("path", { class: "hole-neigh", d: holePath(n.contorno), transform: n.svg.transform }));
  }
  const cand = dr.candidatas && dr.candidatas[idx];
  if (cand) {
    const g = s("g", { transform: cand.svg.transform, id: "hole-piece" });
    g.append(s("image", { href: `${cand.img}&v=${S.ver}`, x: -HOLE_SPAN / 2, y: -HOLE_SPAN / 2, width: HOLE_SPAN, height: HOLE_SPAN, opacity: 0.88, "pointer-events": "none" }));
    g.append(s("path", { class: "hole-cand", d: holePath(cand.contorno) }));
    lay.append(g);
  }
  S.holeShown = { cell: hd.cell, idx };
  fitRect(c - 1 - 1.5, (l - 1) * S.hr - 1.5, c + 1.5, l * S.hr + 1.5, 0.02);
}
function holeLayerClear() {
  const lay = $("#hole-layer");
  if (lay) lay.replaceChildren();
  S.holeShown = null;
}

// ------------------------------------------------------------ gaveta da célula: «Candidatas para este buraco»
/** Bloco da gaveta (devolve o elemento, que se preenche sozinho); só para célula vazia com ≥ 1 vizinha ocupada. */
function holesBlock(d) {
  const box = h("section", { class: "holes-block", "data-hole": `${d.cell[0]},${d.cell[1]}` });
  box.append(h("h2", {}, "Candidatas para este buraco"), h("p", { class: "muted small" }, "a calcular…"));
  holesFill(box, d.cell).catch((e) => { box.replaceChildren(h("h2", {}, "Candidatas para este buraco"), h("p", { class: "note" }, e.message)); });
  return box;
}
/** SSE holes_changed: refresh the «Candidatas para este buraco» block of the open drawer in place (the rest of the
 * drawer, e.g. the cell hints, is not re-rendered: it depends on S.board, which reloads on board_changed). */
function holesRefreshDrawer() {
  const box = $("#tab-celula .holes-block[data-hole]");
  if (!box || S.tab !== "celula") return;
  const cell = box.dataset.hole.split(",").map(Number);
  holesFill(box, cell).catch(() => {});
}
function holeLead(hd) {
  const viz = (hd.vizinhas || []).map((v) => `${v.dir} ${v.piece}`).join(", ");
  return h("div", { class: "hole-lead" }, holeConfChip(hd.confianca, hd.m),
    h("span", { class: "small muted" }, ` ${hd.m} vizinha${hd.m === 1 ? "" : "s"} (${viz}) · ${hd.n_finitas} de ${hd.n_pool} soltas com custo finito`
      + (hd.margem !== null && hd.margem !== undefined ? ` · margem ${fmtMargin(hd.margem)}` : "") + (hd.parcial ? " · parcial (sem afetação conjunta)" : "")));
}
function holeNotes(hd) {
  const out = [];
  if (hd.m === 1) out.push(h("p", { class: "note hole-warn" }, "Só uma vizinha: o molde não chega para decidir; a confiança fica baixa (nunca «alta»). Confirma pelo encaixe físico."));
  if (hd.confianca === "sem") out.push(h("p", { class: "note" }, "Sem candidata fiável: nenhuma solta passa a rejeição com margem. As três mais próximas ficam abaixo só para orientar; não é uma proposta."));
  const calib = S.holes && S.holes.calib;
  if (calib && calib.calibrated === false) out.push(h("p", { class: "note" }, "Parâmetros por calibrar: o ranking usa valores por omissão."));
  return out;
}
async function holesFill(box, cell) {
  const hd = await api(`/api/holes/${cell[0]}/${cell[1]}`);
  if (!box.isConnected) return;
  box.replaceChildren();
  box.append(h("h2", {}, "Candidatas para este buraco"));
  if (!hd.buraco) {
    box.append(h("p", { class: "note" }, hd.a_calcular ? "O ranking dos buracos ainda está a ser calculado (primeira vez: alguns minutos). Volta a abrir a célula daqui a pouco."
      : (hd.erro ? `Sem ranking: ${hd.erro}` : "Esta célula não tem vizinha montada com forma e pose: sem molde.")));
    return;
  }
  box.append(holeLead(hd), ...holeNotes(hd));
  if (!hd.candidatas.length) { box.append(h("p", { class: "note" }, "Nenhuma solta passa tipo, cordas, lados F ou imagem.")); return; }
  hd.candidatas.forEach((cd, i) => box.append(holeCard(hd, cd, i)));
  box.append(h("details", { class: "tech" }, h("summary", {}, "razões técnicas"), h("ul", {}, (hd.razoes || []).map((t) => h("li", {}, t)))));
}
function holeCard(hd, cd, i) {
  const dr = hd.desenho || {};
  const cand = dr.candidatas ? dr.candidatas[i] : null;
  const card = h("div", { class: "card hole-card" + (hd.confianca === "alta" && i === 0 ? " hole-best" : ""), "data-hole-piece": cd.piece, "data-rank": cd.rank });
  const who = h("div", { class: "who" }, cd.lote !== null && cd.lote !== undefined ? ["Saco ", h("span", { class: "n" }, cd.lote), " · nº ", h("span", { class: "n" }, cd.n_no_lote)] : [cd.piece]);
  const nums = h("div", { class: "hole-nums small" },
    h("span", {}, `#${cd.rank}`), h("span", { title: "custo conjunto E5 (forma + imagem + corda), média sobre as vizinhas" }, `custo ${fmt(cd.J, 2)}`),
    i === 0 && hd.margem !== null && hd.margem !== undefined ? h("span", { title: "custo da 2.ª / custo da 1.ª" }, `margem ${fmtMargin(hd.margem)}`) : null,
    cd.theta_deg !== null && cd.theta_deg !== undefined ? h("span", {}, `rodar ${fmt(cd.theta_deg, 0)}°`) : null,
    i === 0 ? holeConfChip(hd.confianca, hd.m) : null,
    cd.melhor_para ? h("span", { class: "chip mid", title: "na afetação conjunta esta peça ficou com outro buraco" }, `é a melhor para ${cellTxt(cd.melhor_para)}`) : null,
    hd.atribuida === cd.piece ? h("span", { class: "chip ok", title: "afetação conjunta: cada peça num buraco, cada buraco numa peça" }, "atribuída") : null);
  const lados = h("ul", { class: "reasons small" }, (cd.por_lado || []).map((ps) => h("li", {},
    `${ps.direction} ${ps.piece}: forma ${fmt(ps.rms, 2)} mm` + (ps.dE !== null && ps.dE !== undefined ? ` · ΔE ${fmt(ps.dE, 1)}` : " · sem imagem")
    + ` · |ΔL| ${fmt(ps.dl, 2)} mm` + (ps.pen > 0 ? ` (penalização ${fmt(ps.pen, 2)})` : ""))));
  const fig = h("div", { class: "hole-fig" }, cand ? holeMiniSvg(hd, hd.cell, cand, dr) : h("div", { class: "pimg" }, h("img", { src: `/api/pieces/${cd.piece}.png?pose=scan&size=300&v=${S.ver}`, alt: cd.piece })),
    h("div", { class: "pimg-cap" }, cand ? "no buraco, com as vizinhas (ciano)" : "como foi digitalizada"));
  card.append(h("div", { class: "card-top hole-top" }, fig, h("div", {}, who, h("div", { class: "small muted" }, `${cd.piece}` + (cd.scan_id ? ` · folha ${cd.scan_id}` : "")), nums, lados)));
  card.append(holeActions(hd.cell, cd.piece, () => holeShowOnBoard(hd, i), { cell: hd.cell, vista: "buraco" }));
  return card;
}
/** Botões Coloquei / Não encaixa (um clique, grava hole_rejected com rank, custo, margem, confiança, versão) / Ver no tabuleiro / Reportar. */
function holeActions(cell, pid, onVer, rctx, opts = {}) {
  const acts = h("div", { class: "actions" });
  acts.append(h("button", { class: "btn primary", type: "button", "data-hole-act": "confirmar", onclick: (ev) => holeAct(cell, pid, "confirmar", ev.currentTarget, opts) }, "Coloquei"));
  acts.append(h("button", { class: "btn", type: "button", "data-hole-act": "rejeitar", title: "um clique: fica registado com rank, custo, margem, confiança e versão do fit",
    onclick: (ev) => holeAct(cell, pid, "rejeitar", ev.currentTarget, opts) }, "Não encaixa"));
  if (onVer) acts.append(h("button", { class: "btn slim", type: "button", "data-hole-act": "ver", onclick: onVer }, "Ver no tabuleiro"));
  acts.append(reportButton({ piece: pid, cell, vista: (rctx && rctx.vista) || "buraco" }));
  return acts;
}
async function holeAct(cell, pid, what, btn, opts = {}) {
  const btns = btn ? $$("button", btn.closest(".actions") || btn.parentElement) : [];
  btns.forEach((b) => (b.disabled = true));
  const old = btn ? btn.textContent : null;
  if (btn) btn.textContent = "a gravar…";
  try {
    const body = { piece: pid };
    if (opts.gemea) body.gemea = true;
    const r = await api(`/api/holes/${cell[0]}/${cell[1]}/${what}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    for (const m of r.mensagens || []) toast(m);
    if (what === "rejeitar" && r.meta) {
      toast(`Rejeição registada: rank ${r.meta.rank ?? "—"} · custo ${fmt(r.meta.custo, 2)} · margem ${fmt(r.meta.margem, 2)} · ${HOLE_CONF_SHORT[r.meta.confianca] || r.meta.confianca} · ${r.meta.fit_version}`);
    }
    if (r.invariantes && r.invariantes.length) toast("INVARIANTES: " + r.invariantes.join("; "), true);
    holeLayerClear();
    await refreshAfterWrite();
    loadHoles().catch(() => {});
    return r;
  } catch (e) {
    toast(e.message, true);
  } finally {
    btns.forEach((b) => (b.disabled = false));
    if (btn) btn.textContent = old;
  }
}

// ------------------------------------------------------------ «Vai buscar»: cartão de uma sugestão por buraco
/** Cartão de uma entrada `buracos_alta` de /api/fetch (mesma forma dos cartões de gémea: saco · nº, célula, chips, mini-SVG no buraco, razões, ações). */
function altaCard(e) {
  const hl = e.hole || {};
  const hd = { cell: e.cell, desenho: e.desenho || {} };
  const dr = hd.desenho;
  const cand = dr.candidatas ? dr.candidatas[0] : null;
  const card = h("div", { class: "card hole-sug", "data-piece": e.piece, "data-hole-piece": e.piece, "data-rank": hl.rank || 1 });
  const head = h("div", {},
    h("div", { class: "who" }, e.lote !== null && e.lote !== undefined ? ["Saco ", h("span", { class: "n" }, e.lote), " · nº ", h("span", { class: "n" }, e.n_no_lote)] : [e.piece]),
    h("div", { class: "where" }, "→ célula ", h("b", {}, cellTxt(e.cell)), " ", holeSugChip(e),
      e.conflito_gemea ? h("span", { class: "chip mid", title: "a proposta de gémea manda esta peça para outra célula: vê as duas" }, `conflito: gémea diz ${cellTxt(e.conflito_gemea)}`) : null),
    h("div", { class: "small muted" }, `${e.origem_txt || "molde do buraco"} · ${e.piece}` + (e.pose_known ? ` · rodar ${fmt(e.theta_deg, 0)}°` : "")),
    h("ul", { class: "reasons" }, (e.razoes_txt || []).map((t) => h("li", {}, t))));
  const fig = h("div", { class: "hole-fig" }, cand ? holeMiniSvg(hd, e.cell, cand, dr) : h("div", { class: "pimg" }, h("img", { src: `/api/pieces/${e.piece}.png?pose=scan&size=300&v=${S.ver}`, alt: e.piece })),
    h("div", { class: "pimg-cap" }, cand ? "no buraco, com as vizinhas (ciano)" : "como foi digitalizada"));
  card.append(h("div", { class: "card-top hole-top" }, fig, head));
  const sheetUrl = e.scan_id ? `/api/sheets/${e.scan_id}.jpg?highlight=${e.piece}` : null;
  card.append(h("div", { class: "card-mid" },
    h("div", {}, miniMap(e.cell), h("div", { class: "mini-cap" }, `linha ${e.cell[0]} · coluna ${e.cell[1]}`)),
    sheetUrl ? h("div", {}, h("img", { class: "sheet-thumb", loading: "lazy", src: `${sheetUrl}&max=640&v=${S.ver}`, alt: `folha ${e.scan_id}`,
      onclick: () => lightbox(`${sheetUrl}&max=1400&v=${S.ver}`, `Folha ${e.scan_id} do saco ${e.lote}: a peça nº ${e.n_no_lote} está a âmbar`) }),
      h("div", { class: "sheet-cap" }, `folha ${e.scan_id}: nº ${e.n_no_lote ?? "?"} a âmbar (toca para ampliar)`)) : h("div")));
  card.append(holeActions(e.cell, e.piece, cand ? () => holeShowOnBoard(hd, 0) : null, { cell: e.cell, vista: "cartao" }));
  const tech = [`custo ${fmt(hl.J, 3)}, margem ${fmtMargin(hl.margem)}, d1 ${fmt(hl.d1, 3)}, d2 ${fmt(hl.d2, 3)}, ${hl.m} vizinhas, zona ${hl.zona || "?"}, ${hl.fit_version || ""}`, ...(e.reasons || [])];
  card.append(h("details", { class: "tech" }, h("summary", {}, "razões técnicas"), h("ul", {}, tech.map((t) => h("li", {}, t)))));
  return card;
}

// ------------------------------------------------------------ página «Buracos»: média, baixa, sem fiável (3 melhores por buraco)
function holeGroupOf(x, alta) {
  if (x.confianca === "alta") {
    const c0 = x.candidatas[0];
    if (!c0 || c0.rank !== 1 || (x.atribuida && x.atribuida !== c0.piece)) return "conflito";
    return alta && alta.em_pausa ? "alta_pausa" : "alta_buscar";
  }
  if (x.confianca === "media") return x.m === 1 ? "baixa" : "media";
  return "sem";
}
function renderHolesTab() {
  const T = $("#tab-buracos");
  if (!T) return;
  T.replaceChildren();
  T.append(h("div", { class: "cell-head" },
    h("button", { class: "btn slim", type: "button", onclick: () => showTab(S.prevTab && S.prevTab !== "buracos" ? S.prevTab : "buscar") }, "← voltar"),
    h("h3", {}, "Buracos: candidatas por confiança")));
  const d = S.holes;
  if (!d) { T.append(h("p", { class: "muted" }, "a carregar…")); return; }
  T.append(altaBanner("buracos"));
  if (d.a_calcular) {
    T.append(h("div", { class: "empty" }, h("strong", {}, "A calcular os moldes dos buracos…"), "primeira vez: alguns minutos (tiras de imagem das peças montadas; ficam em cache)."));
    return;
  }
  const r = d.resumo || {};
  if (r.erro) { T.append(h("div", { class: "empty" }, h("strong", {}, "Sem ranking de buracos"), r.erro)); return; }
  const pc = r.por_confianca || {};
  T.append(h("p", { class: "summary" }, `${r.n_buracos} buracos (célula vazia com ≥ 1 vizinha montada) × ${r.n_soltas} soltas · alta ${pc.alta || 0} (${r.alta_m2 || 0} com ≥ 2 vizinhas) · média ${pc.media || 0} · sem candidata fiável ${pc.sem || 0}`
    + (r.calibrado ? "" : " · parâmetros por calibrar")));
  T.append(h("p", { class: "small muted" }, "As sugestões alta estão em «Vai buscar». Aqui ficam os buracos de confiança média, baixa (vizinha única, nunca alta) e sem candidata fiável, cada um com as 3 melhores: se não for esta, talvez seja uma destas. «Não encaixa» grava a rejeição num clique."));
  const q = h("input", { type: "search", class: "susp-filter", placeholder: "filtrar (célula, peça, saco, zona, confiança)", "aria-label": "filtrar buracos", value: S.holesQuery || "" });
  const norm = (x) => String(x || "").toLowerCase().replace(/[()\s]/g, "");
  const list = h("div", { class: "holes-list" });
  const apply = () => {
    S.holesQuery = q.value;
    const k = norm(q.value);
    for (const row of list.querySelectorAll(".hole-row")) row.hidden = !!k && !row.dataset.q.includes(k);
    for (const g of list.querySelectorAll(".hole-group")) g.hidden = !!k && ![...g.querySelectorAll(".hole-row")].some((x) => !x.hidden);
  };
  q.addEventListener("input", apply);
  T.append(q, list);
  const alta = altaInfo();
  const rows = (d.buracos || []).filter((x) => x.candidatas.length || x.confianca !== "sem");
  const hidden = (d.buracos || []).length - rows.length;
  if (!rows.length) list.append(h("div", { class: "empty" }, h("strong", {}, "Nenhum buraco com candidatas.")));
  if (hidden > 0) T.insertBefore(h("p", { class: "small muted" }, `${hidden} buraco${hidden === 1 ? "" : "s"} sem nenhuma solta com custo finito ficam fora da lista.`), list);
  const groups = new Map();
  for (const x of rows) { const g = holeGroupOf(x, alta); if (!groups.has(g)) groups.set(g, []); groups.get(g).push(x); }
  S.holesOpen = S.holesOpen || new Set();
  for (const g of ["alta_pausa", "media", "baixa", "sem", "conflito", "alta_buscar"]) {
    const xs = groups.get(g);
    if (!xs || !xs.length) continue;
    const det = h("details", { class: "hole-group", "data-group": g, open: g !== "alta_buscar" && g !== "conflito" },
      h("summary", {}, h("span", { class: "hole-group-t" }, HOLE_GROUP_TXT[g]), h("b", {}, String(xs.length)), h("span", { class: "small muted hole-group-h" }, ` ${HOLE_GROUP_HELP[g]}`)));
    for (const x of xs) det.append(holeRow(x, g));
    list.append(det);
  }
  apply();
}
function holeRow(x, g) {
  const norm = (t) => String(t || "").toLowerCase().replace(/[()\s]/g, "");
  const c0 = x.candidatas[0];
  const qtxt = norm([cellTxt(x.cell), x.zona, x.confianca, HOLE_CONF_SHORT[x.confianca], HOLE_GROUP_TXT[g], c0 ? c0.piece : "", c0 ? `saco${c0.lote}` : "", c0 ? `s${c0.lote}` : "", x.m + "viz"].join(" "));
  const key = `${x.cell[0]},${x.cell[1]}`;
  const row = h("details", { class: "hole-row" + (x.confianca === "alta" && x.m >= 2 ? " hole-top1" : ""), "data-q": qtxt, "data-cell": key, "data-group": g });
  row.append(h("summary", {},
    h("span", { class: "hole-cellt" }, cellTxt(x.cell)),
    h("span", { class: "small muted" }, `${x.m} viz. · ${x.zona || ""}`),
    holeConfChip(x.confianca, x.m),
    h("span", { class: "small" }, c0 ? `→ saco ${c0.lote ?? "?"} nº ${c0.n_no_lote ?? "?"} (${c0.piece})` + (x.margem !== null && x.margem !== undefined ? ` · margem ${fmtMargin(x.margem)}` : "") : "sem candidatas finitas"),
    x.atribuida && c0 && x.atribuida !== c0.piece ? h("span", { class: "chip mid" }, `atribuída ${x.atribuida}`) : null));
  const body = h("div", { class: "hole-row-body" }, h("p", { class: "muted small" }, "a carregar as 3 melhores…"));
  row.append(body);
  row.addEventListener("toggle", () => {
    if (row.open) { S.holesOpen.add(key); holeRowFill(body, x.cell).catch((e) => body.replaceChildren(h("p", { class: "note" }, e.message))); }
    else S.holesOpen.delete(key);
  });
  if (S.holesOpen.has(key)) row.open = true;
  return row;
}
async function holeRowFill(body, cell) {
  const hd = await api(`/api/holes/${cell[0]}/${cell[1]}`);
  if (!body.isConnected) return;
  body.replaceChildren();
  if (!hd.buraco) { body.append(h("p", { class: "note" }, hd.erro ? `Sem ranking: ${hd.erro}` : "Esta célula já não é um buraco.")); return; }
  body.append(h("div", { class: "actions" }, h("button", { class: "btn slim", type: "button", "data-hole-open": "1", onclick: () => openCell(cell[0], cell[1], { zoom: true }) }, "Abrir célula")));
  body.append(...holeNotes(hd));
  if (!hd.candidatas.length) { body.append(h("p", { class: "note" }, "Nenhuma solta passa tipo, cordas, lados F ou imagem.")); return; }
  body.append(h("p", { class: "small muted" }, "Se não for esta, talvez seja uma destas:"));
  hd.candidatas.forEach((cd, i) => body.append(holeCard(hd, cd, i)));
}
