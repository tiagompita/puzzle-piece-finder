"""Capturas da F1d do redesenho (correções do teste do Tiago) em /novo/.

Uso::

    python tools/gui/f1d_capturas.py --project COPIA_DE_ALPES --out DIR

Arranca ``python -m src.server`` sobre ``--project`` (uma CÓPIA de projects/alpes: os passos ``colocar`` e ``vazio``
gravam posições conhecidas e desfazem-nas a seguir pela API) e, a 1366x768 e a 390x844, guarda em PNG:

* ``F1d_montar_<vp>.png``: o cartão sem vizinha montada («Colocar aqui» / «Não pertence aqui», «localizar», ícones);
* ``F1d_menu_<vp>.png``: o menu «⋯» aberto (ícones com texto);
* ``F1d_colocar_<vp>.png``: logo depois de «Colocar aqui»: a faixa da última ação com «Desfazer» e o aviso (visíveis);
* ``F1d_porconfirmar_<vp>.png``: o tabuleiro aproximado ao lugar dessa peça, desenhada «por confirmar»;
* ``F1d_vazio_<vp>.png``: o ecrã vazio com a contagem das peças guardadas à parte, depois de «Colocar aqui» em todos os
  cartões (desfeito a seguir pela API, ``position_clear`` com ``desfaz``).

Escreve ``F1d_contagens.json``: palavras e botões visíveis em ``#top`` + painel em cada estado, e a fila.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from f1b_capturas import _COUNT, VIEWPORTS, _novo, _server, _settle, _stop  # noqa: E402

HIDE = "#toast { visibility: hidden !important; } * { caret-color: transparent !important; }"


def _shot(pg, out, name, hide_toast=True, settle=900):
	if hide_toast:
		pg.add_style_tag(content=HIDE)
	_settle(pg, settle)
	pg.screenshot(path=os.path.join(out, name))
	print("  ", name)


def _show_toast(pg):
	pg.add_style_tag(content="#toast { visibility: visible !important; }")


def _undo_all(pg, pids):
	for pid in pids:
		r = pg.evaluate("""async (pid) => { const r = await fetch('/api/confirm', { method: 'POST',
			headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ acao: 'position_clear', piece: pid, desfaz: true }) });
			return r.status; }""", pid)
		assert r == 200, (pid, r)


def capture(project, out):
	from playwright.sync_api import sync_playwright
	os.makedirs(out, exist_ok=True)
	counts = {}
	srv, base = _server(project)
	try:
		with sync_playwright() as pw:
			br = pw.chromium.launch()
			for tag, (w, h) in VIEWPORTS.items():
				ctx = br.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
				pg = ctx.new_page()
				_novo(pg, base)
				pg.wait_for_selector("#tab-montar .card[data-tipo='guardar']", timeout=120_000)
				m = pg.evaluate("S.montar")
				counts[f"fila_{tag}"] = {"total": m["total"], "n_coloca": m["n_coloca"], "n_guardar": m["n_guardar"],
										"fora_da_fila": m["fora_da_fila"], "progresso": m["progresso"],
										"itens": [(it["piece"], it["tipo"], it["lote"], it["n_no_lote"], it["cell"]) for it in m["itens"]],
										"por_confirmar": pg.evaluate("S.board.posicoes_conhecidas")}
				_shot(pg, out, f"F1d_montar_{tag}.png")
				counts[f"montar_{tag}"] = pg.evaluate(_COUNT, ["#top", "#tab-montar"])
				pg.click("#menu-btn")
				_shot(pg, out, f"F1d_menu_{tag}.png", settle=300)
				counts[f"menu_{tag}"] = pg.evaluate(_COUNT, ["#menu"])
				pg.keyboard.press("Escape")
				pg.mouse.click(5, h - 5)
				pg.wait_for_function("document.querySelector('#menu').hidden")
				pid = pg.locator("#tab-montar .card").get_attribute("data-piece")
				cell = next(it["cell"] for it in m["itens"] if it["piece"] == pid)
				pg.click("#b-guardar")
				pg.wait_for_selector("#m-ultimo #b-desfazer-ultimo", timeout=120_000)
				_show_toast(pg)
				_shot(pg, out, f"F1d_colocar_{tag}.png", hide_toast=False, settle=600)
				pg.wait_for_function("!S.busy", timeout=120_000)
				pg.wait_for_selector(f"#lyr-conhecida .por-confirmar[data-piece='{pid}']", timeout=120_000)
				_settle(pg, 2000)                   # a recarga por SSE volta a centrar no alvo seguinte; depois aproxima
				pg.evaluate(f"zoomCells({max(1, cell[0] - 2)}, {max(1, cell[1] - 3)}, {cell[0] + 2}, {cell[1] + 3}, 0.04)")
				_shot(pg, out, f"F1d_porconfirmar_{tag}.png", settle=2500)
				guardadas = [pid]
				for _ in range(m["n_guardar"] - 1):
					p2 = pg.locator("#tab-montar .card").get_attribute("data-piece")
					pg.click("#b-guardar")
					guardadas.append(p2)
					pg.wait_for_function("(pid) => !(S.montar.itens || []).some((it) => it.piece === pid) && !S.busy", arg=p2,
										 timeout=180_000)
				pg.wait_for_selector("#tab-montar [data-estado^=vazio]", timeout=120_000)
				_shot(pg, out, f"F1d_vazio_{tag}.png")
				counts[f"vazio_{tag}"] = pg.evaluate(_COUNT, ["#top", "#tab-montar"])
				counts[f"vazio_{tag}"]["fora_da_fila"] = pg.evaluate("S.montar.fora_da_fila")
				counts[f"vazio_{tag}"]["resumo"] = pg.locator("#m-resumo").inner_text()
				counts[f"vazio_{tag}"]["progresso"] = pg.locator("#progress-txt").inner_text()
				_undo_all(pg, guardadas)        # desfaz na cópia, para o viewport seguinte partir do mesmo estado
				ctx.close()
			br.close()
	finally:
		_stop(srv)
	with open(os.path.join(out, "F1d_contagens.json"), "w", encoding="utf-8") as f:
		json.dump(counts, f, ensure_ascii=False, indent=1)
	print(json.dumps(counts, ensure_ascii=False))


def main(argv=None) -> int:
	ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	ap.add_argument("--project", required=True)
	ap.add_argument("--out", required=True)
	a = ap.parse_args(argv)
	capture(os.path.abspath(a.project), a.out)
	return 0


if __name__ == "__main__":
	sys.exit(main())
