/* Molde do buraco (M11, src/fit.py): «Candidatas para este buraco» na gaveta de uma célula vazia com ≥ 1 vizinha
 * montada, a aba «Buracos» (lista por confiança) e a camada #hole-layer no tabuleiro (candidata desenhada no buraco
 * com os contornos das vizinhas). É um RANKING: «sem candidata fiável» é um resultado legítimo; vizinha única nunca
 * é «alta». Confirmar/rejeitar grava hole_confirmed/hole_rejected (rank, custo, margem, confiança, versão do fit):
 * é a verdade de terreno de `python -m src.fit --relatorio`. Usa globais de app.js ($, $$, h, s, S, api, toast, fmt,
 * cellTxt, openCell, fitRect, refreshAfterWrite, reportButton, showTab). Nada da simetria do puzzle está aqui.
 */
"use strict";

const HOLE_CONF_TXT = { alta: "confiança alta", media: "confiança média", sem: "sem candidata fiável" };
const HOLE_CONF_SHORT = { alta: "alta", media: "média", sem: "sem fiável" };
const HOLE_SPAN = 1.8;          // células: o PNG da peça (pose=scan) tem o centro do corpo no meio e cobre 1,8 células

// ------------------------------------------------------------ dados
async function loadHoles() {
  const d = await api("/api/holes");
  S.holes = d;
  renderHolesTab();
  renderHolesBadge();
  return d;
}
function renderHolesBadge() {
  const r = (S.holes && S.holes.resumo) || {};
  for (const b of $$("[data-holes-entry] b")) b.textContent = r.alta_m2 ? String(r.alta_m2) : "";
}
/** Entrada para a secção «Buracos» (não é uma aba do topo: a barra está dimensionada para 6; também pela pesquisa «buracos»). */
function holesEntry() {
  const r = (S.holes && S.holes.resumo) || {};
  return h("div", { class: "holes-entry" },
    h("button", { class: "btn slim", type: "button", "data-holes-entry": "1", title: "ranking das soltas para cada célula vazia com vizinha montada (não é proposta)",
      onclick: () => showTab("buracos") }, "Buracos: candidatas por confiança ", h("b", {}, r.alta_m2 ? String(r.alta_m2) : "")),
    h("span", { class: "small muted" }, " ranking, não proposta · pesquisa: «buracos»"));
}
function holeConfChip(conf, m) {
  const cls = conf === "alta" ? "chip ok" : (conf === "media" ? "chip mid" : "chip sem");
  const txt = m === 1 && conf !== "sem" ? `${HOLE_CONF_SHORT[conf]} · 1 vizinha: baixa` : HOLE_CONF_SHORT[conf];
  return h("span", { class: cls, "data-conf": conf, title: HOLE_CONF_TXT[conf] }, txt);
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
async function holesFill(box, cell) {
  const hd = await api(`/api/holes/${cell[0]}/${cell[1]}`);
  if (!box.isConnected) return;
  box.replaceChildren();
  const head = h("h2", {}, "Candidatas para este buraco");
  box.append(head);
  if (!hd.buraco) {
    box.append(h("p", { class: "note" }, hd.a_calcular ? "O ranking dos buracos ainda está a ser calculado (primeira vez: alguns minutos). Volta a abrir a célula daqui a pouco."
      : (hd.erro ? `Sem ranking: ${hd.erro}` : "Esta célula não tem vizinha montada com forma e pose: sem molde.")));
    return;
  }
  const viz = (hd.vizinhas || []).map((v) => `${v.dir} ${v.piece}`).join(", ");
  const lead = h("div", { class: "hole-lead" }, holeConfChip(hd.confianca, hd.m),
    h("span", { class: "small muted" }, ` ${hd.m} vizinha${hd.m === 1 ? "" : "s"} (${viz}) · ${hd.n_finitas} de ${hd.n_pool} soltas com custo finito`
      + (hd.margem !== null && hd.margem !== undefined ? ` · margem ${fmt(hd.margem, 2)}` : "") + (hd.parcial ? " · parcial (sem afetação conjunta)" : "")));
  box.append(lead);
  if (hd.m === 1) box.append(h("p", { class: "note hole-warn" }, "Só uma vizinha: o molde não chega para decidir; a confiança fica baixa (nunca «alta»). Confirma pelo encaixe físico."));
  if (hd.confianca === "sem") box.append(h("p", { class: "note" }, "Sem candidata fiável: nenhuma solta passa a rejeição com margem. As três mais próximas ficam abaixo só para orientar; não é uma proposta."));
  const calib = S.holes && S.holes.calib;
  if (calib && calib.calibrated === false) box.append(h("p", { class: "note" }, "Parâmetros por calibrar: o ranking usa valores por omissão."));
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
    i === 0 && hd.margem !== null && hd.margem !== undefined ? h("span", { title: "custo da 2.ª / custo da 1.ª" }, `margem ${fmt(hd.margem, 2)}`) : null,
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
  const acts = h("div", { class: "actions" });
  acts.append(h("button", { class: "btn primary", type: "button", "data-hole-act": "confirmar", onclick: (ev) => holeAct(hd.cell, cd.piece, "confirmar", ev.currentTarget) }, "Coloquei"));
  acts.append(h("button", { class: "btn", type: "button", "data-hole-act": "rejeitar", onclick: (ev) => holeAct(hd.cell, cd.piece, "rejeitar", ev.currentTarget) }, "Não encaixa"));
  acts.append(h("button", { class: "btn slim", type: "button", "data-hole-act": "ver", onclick: () => holeShowOnBoard(hd, i) }, "Ver no tabuleiro"));
  acts.append(reportButton({ piece: cd.piece, cell: hd.cell, vista: "buraco" }));
  card.append(acts);
  return card;
}
async function holeAct(cell, pid, what, btn) {
  const btns = btn ? $$("button", btn.closest(".actions") || btn.parentElement) : [];
  btns.forEach((b) => (b.disabled = true));
  const old = btn ? btn.textContent : null;
  if (btn) btn.textContent = "a gravar…";
  try {
    const r = await api(`/api/holes/${cell[0]}/${cell[1]}/${what}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ piece: pid }) });
    for (const m of r.mensagens || []) toast(m);
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

// ------------------------------------------------------------ aba «Buracos»: lista por confiança
function renderHolesTab() {
  const T = $("#tab-buracos");
  if (!T) return;
  T.replaceChildren();
  T.append(h("div", { class: "cell-head" },
    h("button", { class: "btn slim", type: "button", onclick: () => showTab(S.prevTab && S.prevTab !== "buracos" ? S.prevTab : "buscar") }, "← voltar"),
    h("h3", {}, "Buracos: candidatas por confiança")));
  const d = S.holes;
  if (!d) { T.append(h("p", { class: "muted" }, "a carregar…")); return; }
  if (d.a_calcular) {
    T.append(h("div", { class: "empty" }, h("strong", {}, "A calcular os moldes dos buracos…"), "primeira vez: alguns minutos (tiras de imagem das peças montadas; ficam em cache)."));
    return;
  }
  const r = d.resumo || {};
  if (r.erro) { T.append(h("div", { class: "empty" }, h("strong", {}, "Sem ranking de buracos"), r.erro)); return; }
  const pc = r.por_confianca || {};
  T.append(h("p", { class: "summary" }, `${r.n_buracos} buracos (célula vazia com ≥ 1 vizinha montada) × ${r.n_soltas} soltas · alta ${pc.alta || 0} (${r.alta_m2 || 0} com ≥ 2 vizinhas) · média ${pc.media || 0} · sem candidata fiável ${pc.sem || 0}`
    + (r.calibrado ? "" : " · parâmetros por calibrar")));
  T.append(h("p", { class: "small muted" }, "Ranking, não proposta: cada linha abre a célula com as 3 melhores desenhadas no buraco. Primeiro os buracos de ≥ 2 vizinhas com confiança alta; «vizinha única» nunca é alta. A afetação conjunta dá cada solta a um só buraco."));
  const q = h("input", { type: "search", class: "susp-filter", placeholder: "filtrar (célula, peça, saco, zona, confiança)", "aria-label": "filtrar buracos", value: S.holesQuery || "" });
  const norm = (x) => String(x || "").toLowerCase().replace(/[()\s]/g, "");
  const list = h("div", { class: "holes-list" });
  const apply = () => {
    S.holesQuery = q.value;
    const k = norm(q.value);
    for (const row of list.querySelectorAll(".hole-row")) row.hidden = !!k && !row.dataset.q.includes(k);
  };
  q.addEventListener("input", apply);
  T.append(q, list);
  const rows = (d.buracos || []).filter((x) => x.candidatas.length || x.confianca !== "sem");
  const hidden = (d.buracos || []).length - rows.length;
  if (!rows.length) list.append(h("div", { class: "empty" }, h("strong", {}, "Nenhum buraco com candidatas.")));
  if (hidden > 0) T.insertBefore(h("p", { class: "small muted" }, `${hidden} buraco${hidden === 1 ? "" : "s"} sem nenhuma solta com custo finito ficam fora da lista.`), list);
  for (const x of rows) {
    const c0 = x.candidatas[0];
    const qtxt = norm([cellTxt(x.cell), x.zona, x.confianca, HOLE_CONF_SHORT[x.confianca], c0 ? c0.piece : "", c0 ? `saco${c0.lote}` : "", c0 ? `s${c0.lote}` : "", x.m + "viz"].join(" "));
    const row = h("button", { type: "button", class: "hole-row" + (x.confianca === "alta" && x.m >= 2 ? " hole-top1" : ""), "data-q": qtxt, "data-cell": `${x.cell[0]},${x.cell[1]}`,
      onclick: () => openCell(x.cell[0], x.cell[1], { zoom: true }) },
      h("span", { class: "hole-cellt" }, cellTxt(x.cell)),
      h("span", { class: "small muted" }, `${x.m} viz. · ${x.zona || ""}`),
      holeConfChip(x.confianca, x.m),
      h("span", { class: "small" }, c0 ? `→ saco ${c0.lote ?? "?"} nº ${c0.n_no_lote ?? "?"} (${c0.piece})` + (x.margem !== null && x.margem !== undefined ? ` · margem ${fmt(x.margem, 2)}` : "") : "sem candidatas finitas"),
      x.atribuida && c0 && x.atribuida !== c0.piece ? h("span", { class: "chip mid" }, `atribuída ${x.atribuida}`) : null);
    list.append(row);
  }
  apply();
}
