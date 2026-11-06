"""Capturas da aba «Mesa» (alternativa B já implementada), do botão «Sugestões» e dos PROTÓTIPOS descartáveis de seleção.

Uso::

    python tools/gui/mesa_b_capturas.py [--project $PPF_SCRATCH/g_alpes] [--out docs/gui/screenshots]

Arranca ``python -m src.server`` sobre ``--project`` (usar uma CÓPIA de projects/alpes) e, por viewport (1366x768 e
390x844), guarda ``mesa_b_impl_*`` (a lista implementada, com uma linha aberta), ``sugestoes_*`` (botão ligado, com a
lista de escolha onde há sobreposição) e ``mesa_sel_a_*`` / ``mesa_sel_b_*`` (propostas de seleção SEM escrever, só
desenhadas por JavaScript injetado, nada em ``src/``). Imprime as métricas de cada proposta.
"""

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from screenshot import REPO, free_port, save_small, settle as _settle, wait_ready  # noqa: E402


def settle(pg, ms):
    """Like screenshot.settle but tolerant: the SSE stream and lazy thumbnails can keep the network busy."""
    try:
        _settle(pg, ms)
    except Exception:
        pg.wait_for_timeout(ms)

MOCK_CSS = """
#tab-mesa .sel-bar { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 4px 0 8px; padding: 6px 8px; border-radius: 10px;
  background: rgba(180, 140, 255, .12); border: 1px solid var(--violet); font-size: 13px; }
#tab-mesa .sel-chip { display: inline-flex; gap: 6px; align-items: center; min-height: 32px; padding: 0 10px; border-radius: 999px;
  background: var(--bg3); border: 1px solid var(--line); font-size: 13px; }
#tab-mesa .sel-chip b { cursor: pointer; padding: 0 2px; }
#tab-mesa .mk-check { width: 26px; height: 26px; accent-color: var(--violet); margin: 0 8px 0 0; flex: 0 0 auto; }
#tab-mesa .mk-wrap { display: flex; align-items: center; }
#tab-mesa .mk-wrap .mhead { flex: 1 1 auto; min-width: 0; }
#tab-mesa .sel-sticky { position: sticky; top: 0; z-index: 5; background: var(--bg2); }
"""

# A: modo «Selecionar células» no tabuleiro: tocar em células acrescenta chips; a Mesa filtra por zonas que as cobrem (OU).
MOCK_A = """
(cells) => {
  const css = document.createElement('style'); css.textContent = %s; document.head.appendChild(css);
  const T = document.getElementById('tab-mesa');
  const cellHit = (g, l, c) => g.candidatos.some((cd) => cd.footprint.some((x) => x[0] === l && x[1] === c));
  const shown = (S.sections || []).filter((g) => cells.some(([l, c]) => cellHit(g, l, c)));
  const ids = new Set(shown.map((g) => g.id));
  const bar = document.createElement('div'); bar.className = 'sel-bar';
  bar.innerHTML = '<b>Selecionar no tabuleiro</b> (toca em células) ' + cells.map(([l, c]) => `<span class="sel-chip">(${l}, ${c}) <b>✕</b></span>`).join('') +
    `<span class="sel-chip">${shown.length} de ${S.sections.length} grupos · OU</span><button class="btn slim" type="button">Limpar</button>`;
  T.insertBefore(bar, T.firstChild);
  for (const row of T.querySelectorAll('.mrow')) row.style.display = ids.has(row.dataset.g) ? '' : 'none';
  const g = document.getElementById('lyr-sel'); g.replaceChildren();
  for (const [l, c] of cells) g.append(rectEl(l, c, cls('selecao'), 0.0));
  if (cells.length) zoomCells(Math.max(1, Math.min(...cells.map((x) => x[0])) - 4), Math.max(1, Math.min(...cells.map((x) => x[1])) - 6),
                              Math.min(S.rows, Math.max(...cells.map((x) => x[0])) + 4), Math.min(S.cols, Math.max(...cells.map((x) => x[1])) + 6));
  return { grupos_visiveis: shown.length, toques: cells.length, botoes_novos: 1 };
}
""" % json.dumps(MOCK_CSS)

# B: caixas de seleção nas linhas + chips das peças + barra «Só estes (n)».
MOCK_B = """
(pick) => {
  const css = document.createElement('style'); css.textContent = %s; document.head.appendChild(css);
  const T = document.getElementById('tab-mesa');
  const chosen = new Set(pick);
  for (const row of T.querySelectorAll('.mrow')) {
    const wrap = document.createElement('div'); wrap.className = 'mk-wrap';
    const cb = document.createElement('input'); cb.type = 'checkbox'; cb.className = 'mk-check'; cb.checked = chosen.has(row.dataset.g);
    cb.setAttribute('aria-label', 'Selecionar ' + row.dataset.g);
    const head = row.querySelector('.mhead'); head.replaceWith(wrap); wrap.append(cb, head);
  }
  const bar = document.createElement('div'); bar.className = 'sel-bar sel-sticky';
  const pieces = (S.sections || []).filter((g) => chosen.has(g.id)).flatMap((g) => g.pecas.map((p) => p.id)).slice(0, 4);
  bar.innerHTML = `<b>${chosen.size} selecionados</b> ` + pieces.map((p) => `<span class="sel-chip">${p} <b>✕</b></span>`).join('') +
    '<button class="btn slim primary" type="button">Só estes</button><button class="btn slim" type="button">Limpar</button>';
  T.insertBefore(bar, T.firstChild);
  return { toques_para_3: 3 + 1, botoes_novos: (S.sections || []).length + 2, caixas: (S.sections || []).length };
}
""" % json.dumps(MOCK_CSS)

METRICS = """
() => { const T = document.getElementById('tab-mesa'); const pr = T.closest('#panel').getBoundingClientRect();
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && r.top < pr.bottom && r.bottom > pr.top; };
  return { linhas_no_ecra: [...T.querySelectorAll('.mrow')].filter(vis).length, botoes_total: T.querySelectorAll('button, input[type=checkbox]').length }; }
"""

CLIENT_XY = """([l, c]) => { const r = svgRect(); return [r.left + (c - 0.5 - S.vb.x) / S.vb.w * r.width, r.top + ((l - 0.5) * S.hr - S.vb.y) / S.vb.h * r.height]; }"""

OVERLAP_JS = """
() => { const items = suggestionItems(); const cnt = {};
  for (const it of items) for (const [l, c] of it.cells) { const k = l + ',' + c; (cnt[k] = cnt[k] || []).push(it.g.id); }
  const k = Object.keys(cnt).find((x) => cnt[x].length > 1); return k ? k.split(',').map(Number) : null; }
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
                pg.wait_for_selector("#tab-mesa .mrow, #tab-mesa .empty", timeout=60_000)
                settle(pg, 1500)

                def shot(name):
                    path = save_small(pg.screenshot(), args.out, f"{name}_{tag}.jpg")
                    print(f"  {path} ({os.path.getsize(path) // 1024} KB)")

                ids = pg.evaluate("mesaSorted().map((g) => g.id)")
                metrics["grupos"] = len(ids)
                metrics["seguras"] = pg.evaluate("mesaSorted().filter(isSafe).length")
                metrics[f"B_real_{tag}"] = pg.evaluate(METRICS)
                shot("mesa_b_impl_lista")
                pg.evaluate("openMesaGroup(mesaSorted()[2].id, 1)")
                settle(pg, 1500)
                shot("mesa_b_impl_aberta")
                # Sugestões: ligadas, vista inteira; e a lista de escolha onde há sobreposição
                pg.evaluate("document.querySelector('#tg-sug').click()")
                settle(pg, 500)
                pg.evaluate("S.mesaOpen = null; S.mesa = null; drawMesa(); fitBoard(); renderMesa()")
                settle(pg, 800)
                metrics[f"sugestoes_{tag}"] = pg.evaluate("(() => { const it = suggestionItems(); return { grupos: it.length, seguras: it.filter((x) => x.safe).length, celulas: it.reduce((a, x) => a + x.cells.length, 0) }; })()")
                shot("sugestoes")
                ov = pg.evaluate(OVERLAP_JS)
                metrics[f"sobreposicao_{tag}"] = ov
                if ov:
                    pg.evaluate(f"zoomCells({max(1, ov[0] - 3)}, {max(1, ov[1] - 5)}, {min(47, ov[0] + 3)}, {min(64, ov[1] + 5)})")
                    settle(pg, 1200)
                    x, y = pg.evaluate(CLIENT_XY, ov)
                    if mobile:
                        pg.touchscreen.tap(x, y)
                    else:
                        pg.mouse.click(x, y)
                    settle(pg, 500)
                    metrics[f"picker_{tag}"] = pg.evaluate("(() => { const p = document.querySelector('#sug-pick'); if (!p) return null; "
                                                           "return [...p.querySelectorAll('.sug-item')].map((b) => Math.round(b.getBoundingClientRect().height)); })()")
                    shot("sugestoes_escolha")
                pg.evaluate("document.querySelector('#tg-sug').click()")           # desligar antes das propostas
                # propostas de seleção (protótipos)
                three = ids[:3]
                cells = pg.evaluate("(ids) => ids.map((id) => S.sections.find((g) => g.id === id).candidatos[0].cell0)", [ids[0], ids[3]])
                pg.evaluate("showTab('mesa'); S.mesaOpen = null; S.mesa = null; renderMesa()")
                settle(pg, 500)
                metrics[f"A_celulas_{tag}"] = pg.evaluate(MOCK_A, cells)
                settle(pg, 1200)
                metrics[f"A_celulas_{tag}"].update(pg.evaluate(METRICS))
                shot("mesa_sel_a_celulas")
                pg.evaluate("S.mesaOpen = null; S.mesa = null; drawMesa(); document.getElementById('lyr-sel').replaceChildren(); fitBoard(); renderMesa()")
                settle(pg, 500)
                metrics[f"B_caixas_{tag}"] = pg.evaluate(MOCK_B, three)
                metrics[f"B_caixas_{tag}"].update(pg.evaluate(METRICS))
                settle(pg, 800)
                shot("mesa_sel_b_caixas")
                pg.close()
            br.close()
    finally:
        srv.terminate()
    print(json.dumps(metrics, ensure_ascii=False, indent=1))
    with open(os.path.join(args.out, "mesa_b_metricas.json"), "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
