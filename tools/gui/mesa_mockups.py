"""Capturas da aba «Mesa» com dados reais do alpes: a aba atual e dois PROTÓTIPOS descartáveis (não estão em src/).

Uso::

    python tools/gui/mesa_mockups.py [--project $PPF_SCRATCH/g_alpes] [--out docs/gui/screenshots]

Arranca ``python -m src.server`` sobre ``--project`` (usar uma CÓPIA de projects/alpes) e, por cada viewport
(1366x768 e 390x844), guarda ``mesa_atual_*``, ``mesa_a_fila_*`` e ``mesa_b_lista_*``. As alternativas são
desenhadas por JavaScript injetado na página (as funções abaixo), sobre ``S.sections`` reais; nada é gravado no projeto.
Também imprime as métricas de cada variante (botões e caracteres, no ecrã e no total).
"""

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from screenshot import REPO, free_port, save_small, settle, wait_ready  # noqa: E402

MOCK_CSS = """
#tab-mesa .mk-count { color: var(--muted); font-size: 13px; margin: 2px 0 8px; display: flex; justify-content: space-between; }
#tab-mesa .mk-card { border: 1px solid var(--line); border-radius: 14px; padding: 12px; background: var(--bg3); }
#tab-mesa .mk-head { display: flex; gap: 12px; align-items: center; }
#tab-mesa .mk-head img { width: 84px; height: 84px; object-fit: contain; border-radius: 8px; background: #262626; flex-shrink: 0; }
#tab-mesa .mk-title { font-size: 20px; font-weight: 700; }
#tab-mesa .mk-sub { color: var(--muted); font-size: 13px; }
#tab-mesa .mk-zone { font-size: 17px; margin: 12px 0 4px; }
#tab-mesa .chip { display: inline-block; border-radius: 999px; padding: 1px 9px; font-size: 12px; font-weight: 650; }
#tab-mesa .chip.ok { background: rgba(110, 200, 120, .2); color: #8fdc98; }
#tab-mesa .chip.mid { background: rgba(255, 176, 0, .18); color: var(--amber); }
#tab-mesa .mk-actions { display: flex; gap: 8px; margin-top: 12px; }
#tab-mesa .mk-actions .btn { flex: 1; }
#tab-mesa .mk-more { margin-top: 10px; font-size: 13px; color: var(--muted); }
#tab-mesa .mk-more .row { display: flex; gap: 8px; align-items: center; margin-top: 6px; }
#tab-mesa .mk-row { display: grid; grid-template-columns: 44px minmax(0, 1fr) auto; gap: 10px; align-items: center;
  padding: 6px 4px; border-bottom: 1px solid var(--line); cursor: pointer; }
#tab-mesa .mk-row img { width: 44px; height: 44px; object-fit: contain; border-radius: 6px; background: #262626; }
#tab-mesa .mk-row .t { font-weight: 650; }
#tab-mesa .mk-row .s { color: var(--muted); font-size: 12.5px; }
#tab-mesa .mk-row.on { background: rgba(180, 140, 255, .12); }
#tab-mesa .mk-exp { padding: 6px 4px 12px 58px; border-bottom: 1px solid var(--line); background: rgba(180, 140, 255, .06); }
#tab-mesa .mk-exp .row { display: flex; gap: 8px; align-items: center; margin-top: 6px; flex-wrap: wrap; }
"""

MOCK_JS = """
(() => {
  const css = document.createElement('style'); css.id = 'mock-css'; css.textContent = %s; document.head.appendChild(css);
  const chipOf = (m) => (m >= 1.5 ? '<span class="chip ok">segura</span>' : '<span class="chip mid">a confirmar</span>');
  const ordered = () => (S.sections || []).slice().sort((a, b) => ((b.candidatos[0] || {}).margin || 0) - ((a.candidatos[0] || {}).margin || 0));
  const preview = (g, c) => { S.mesa = { id: g.id, rank: c.rank, footprint: c.footprint }; drawMesa();
    const ls = c.footprint.map((x) => x[0]), cs = c.footprint.map((x) => x[1]);
    zoomCells(Math.max(1, Math.min(...ls) - 3), Math.max(1, Math.min(...cs) - 5), Math.min(S.rows, Math.max(...ls) + 3), Math.min(S.cols, Math.max(...cs) + 5)); };
  const el = (html) => { const d = document.createElement('div'); d.innerHTML = html.trim(); return d.firstChild; };
  const cellT = (c) => `(${c[0]}, ${c[1]})`;

  // ---- A: uma de cada vez (fila de decisão)
  window.mockFila = (i = 0) => {
    const T = document.getElementById('tab-mesa'); T.replaceChildren();
    const secs = ordered(); const g = secs[i]; const c = g.candidatos[0];
    T.append(el(`<div class="mk-count"><span>${i + 1} de ${secs.length} · das mais seguras às menos</span></div>`));
    const card = el(`<div class="mk-card"><div class="mk-head"><img src="${g.thumb}"><div><div class="mk-title">${g.id}</div>
      <div class="mk-sub">${g.n} peça${g.n > 1 ? 's' : ''}</div></div></div>
      <div class="mk-zone">Melhor zona: <b>${c ? cellT(c.cell0) : '—'}</b> ${c ? chipOf(c.margin) : ''}</div></div>`);
    const acts = el('<div class="mk-actions"></div>');
    const anchor = el('<button class="btn primary" type="button">Ancorar aqui</button>');
    const next = el('<button class="btn" type="button">Seguinte →</button>');
    next.onclick = () => window.mockFila((i + 1) %% secs.length);
    acts.append(anchor, next); card.append(acts);
    const rest = g.candidatos.slice(1);
    if (rest.length) {
      const d = el(`<details class="mk-more"><summary>Outras zonas (${rest.length})</summary></details>`);
      for (const r of rest) { const row = el(`<div class="row"><span>${r.rank}) <b>${cellT(r.cell0)}</b> ${chipOf(r.margin)}</span></div>`);
        const b = el('<button class="btn slim" type="button">Ver</button>'); b.onclick = () => preview(g, r); row.append(b); d.append(row); }
      card.append(d);
    }
    T.append(card);
    if (c) preview(g, c);
  };

  // ---- B: lista compacta, uma linha por grupo; abre-se uma de cada vez
  window.mockLista = (openId = null) => {
    const T = document.getElementById('tab-mesa'); T.replaceChildren();
    const secs = ordered();
    T.append(el('<input class="search" type="search" placeholder="Procurar: G0012, P0194 ou (3,32)">'));
    T.append(el(`<div class="mk-count"><span>${secs.length} grupos por ancorar</span></div>`));
    for (const g of secs) {
      const c = g.candidatos[0];
      const row = el(`<div class="mk-row ${g.id === openId ? 'on' : ''}"><img src="${g.thumb}" loading="lazy">
        <div><div class="t">${g.id} · ${g.n} peça${g.n > 1 ? 's' : ''}</div><div class="s">${c ? 'melhor zona ' + cellT(c.cell0) + ' ' : 'sem zona '}${c ? chipOf(c.margin) : ''}</div></div>
        <button class="btn slim ${g.id === openId ? '' : 'primary'}" type="button">${g.id === openId ? 'Fechar' : 'Ver'}</button></div>`);
      row.onclick = () => { window.mockLista(g.id === openId ? null : g.id); };
      T.append(row);
      if (g.id === openId) {
        if (c) preview(g, c);
        const ex = el('<div class="mk-exp"></div>');
        const a = el('<div class="row"></div>'); const ab = el('<button class="btn primary" type="button">Ancorar em ' + (c ? cellT(c.cell0) : '—') + '</button>'); a.append(ab); ex.append(a);
        for (const r of g.candidatos.slice(1)) { const rr = el(`<div class="row"><span>ou ${cellT(r.cell0)} ${chipOf(r.margin)}</span></div>`);
          const b = el('<button class="btn slim" type="button">Ver</button>'); b.onclick = (ev) => { ev.stopPropagation(); preview(g, r); }; rr.append(b); ex.append(rr); }
        T.append(ex);
      }
    }
  };
})();
""" % json.dumps(MOCK_CSS)

METRICS_JS = """
() => {
  const T = document.getElementById('tab-mesa'); const pr = T.closest('#panel').getBoundingClientRect();
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.top < pr.bottom && r.bottom > pr.top; };
  const btns = [...T.querySelectorAll('button')]; const text = T.innerText;
  const visBtns = btns.filter(vis);
  const visText = [...T.querySelectorAll('*')].filter((e) => e.children.length === 0 && vis(e)).map((e) => e.textContent.trim()).join(' ');
  return { botoes_total: btns.length, botoes_no_ecra: visBtns.length, caracteres_total: text.length, caracteres_no_ecra: visText.length,
           grupos_no_ecra: [...T.querySelectorAll('.card, .mk-card, .mk-row')].filter(vis).length };
}
"""


def main(argv=None) -> int:
    scratch = os.environ.get("PPF_SCRATCH", os.path.join(REPO, "scratch"))
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project", default=os.path.join(scratch, "g_alpes"))
    ap.add_argument("--out", default=os.path.join(REPO, "docs", "gui", "screenshots"))
    args = ap.parse_args(argv)
    from playwright.sync_api import sync_playwright

    os.makedirs(args.out, exist_ok=True)
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    srv = subprocess.Popen([sys.executable, "-m", "src.server", "--project", args.project, "--port", str(port)],
                           cwd=REPO, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    metrics = {}
    try:
        wait_ready(base)
        with sync_playwright() as pw:
            br = pw.chromium.launch()
            for tag, (w, h, mobile) in (("1366", (1366, 768, False)), ("390", (390, 844, True))):
                kw = {"is_mobile": True, "has_touch": True} if mobile else {}
                pg = br.new_page(viewport={"width": w, "height": h}, device_scale_factor=1.0, **kw)
                pg.goto(base + "/")
                pg.wait_for_selector("body[data-ready='1']", timeout=120_000)
                pg.wait_for_selector("body[data-raster]", timeout=120_000)
                pg.evaluate("showTab('mesa')")
                pg.wait_for_selector("#tab-mesa .card, #tab-mesa .empty", timeout=60_000)
                settle(pg, 1500)

                def shot(name):
                    path = save_small(pg.screenshot(), args.out, f"{name}_{tag}.jpg")
                    print(f"  {path} ({os.path.getsize(path) // 1024} KB)")

                n = pg.evaluate("(S.sections || []).length")
                metrics.setdefault("grupos", n)
                metrics[f"atual_{tag}"] = pg.evaluate(METRICS_JS)
                shot("mesa_atual")
                pg.evaluate(MOCK_JS)
                pg.evaluate("mockFila(0)")
                settle(pg, 1500)
                metrics[f"A_fila_{tag}"] = pg.evaluate(METRICS_JS)
                pg.evaluate("document.querySelector('#tab-mesa details.mk-more').open = true")
                settle(pg, 300)
                shot("mesa_a_fila")
                pg.evaluate("mockLista(null)")
                settle(pg, 800)
                metrics[f"B_lista_{tag}"] = pg.evaluate(METRICS_JS)
                shot("mesa_b_lista")
                pg.evaluate("mockLista(ordered_first())" if False else "mockLista((S.sections.slice().sort((a, b) => ((b.candidatos[0] || {}).margin || 0) - ((a.candidatos[0] || {}).margin || 0))[1] || S.sections[0]).id)")
                settle(pg, 1500)
                metrics[f"B_lista_aberta_{tag}"] = pg.evaluate(METRICS_JS)
                shot("mesa_b_lista_aberta")
                pg.close()
            br.close()
    finally:
        srv.terminate()
    print(json.dumps(metrics, ensure_ascii=False, indent=1))
    with open(os.path.join(args.out, "mesa_metricas.json"), "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
