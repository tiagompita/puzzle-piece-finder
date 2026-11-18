"""Capturas da F2f da GUI nova (/novo/): sugestoes sempre no tabuleiro. Projeto sintetico dos testes com a grelha real
47 x 64 e 5 cartoes a mais injetados em /api/montar (``F2f_<antes|depois>_<cena>_<vp>.png``). Cenas: ``cartao`` (vista do cartao),
``painel`` (painel de outro lugar aberto) e ``inteiro`` (tabuleiro inteiro).

Uso::

    .venv/Scripts/python.exe tools/gui/f2f_capturas.py antes|depois
"""

import json
import sys
import tempfile
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "tests")]
OUT = REPO / "docs" / "gui" / "screenshots" / "redesenho"
VPS = {"1366": (1366, 768), "390": (390, 844)}


def main(prefix):
	from playwright.sync_api import sync_playwright
	import synth
	from src import server as SV
	from src.query import run_query, load_fetch
	from test_gui_novo import _serve
	from test_query import _project
	orig = synth.profile
	synth.profile = lambda rows=4, cols=6, **k: orig(rows=47, cols=64, **k)
	tmp = pathlib.Path(tempfile.mkdtemp())
	pr, placed, tw, dec = _project(tmp)
	run_query(pr, use_image=False)
	cell = [e for e in load_fetch(pr)["entries"] if e.get("piece")][0]["cell"]
	nb = [n for n in pr.board.neighbours(tuple(cell)) if pr.board[n]["estado"] == "vazia"][0]
	pr.mark_cell_full(nb)
	pr.save()
	gui = SV.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp / "uploads"), log=None)
	url, server, th = _serve(gui)
	l0, c0 = cell
	extra = [(l0, c0 - 3), (l0 - 2, c0 - 5), (l0 - 2, c0 - 1), (l0 - 3, c0 - 7), (l0 - 1, c0 - 9)]

	def handle(route):
		r = route.fetch()
		m = r.json()
		if m.get("itens"):
			tpl = m["itens"][0]
			for i, ce in enumerate(extra):
				m["itens"].append(dict(tpl, piece=f"P90{i:02d}", n_no_lote=90 + i, cell=list(ce)))
			m["total"] = len(m["itens"])
		route.fulfill(response=r, body=json.dumps(m), headers=dict(r.headers, **{"content-type": "application/json"}))

	try:
		with sync_playwright() as pw:
			br = pw.chromium.launch()
			for vp, (w, h) in VPS.items():
				pg = br.new_page(viewport={"width": w, "height": h})
				pg.route("**/api/montar*", handle)
				pg.goto(url + "/novo/")
				pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
				pg.wait_for_selector("#tab-montar .card[data-piece]", timeout=60_000)
				pg.wait_for_function("S.vb.w < 30", timeout=10_000)
				pg.wait_for_timeout(700)
				pg.evaluate(f"zoomCells({l0 - 5}, {c0 - 10}, {l0}, {c0 + 2}, 0.04)")
				pg.wait_for_timeout(900)
				pg.screenshot(path=str(OUT / f"F2f_{prefix}_cartao_{vp}.png"))
				pg.evaluate(f"openPainel({l0 - 1}, {c0 - 3})")
				pg.wait_for_selector("#painel[data-kind]:not([data-kind='a_carregar'])", timeout=20_000)
				pg.wait_for_timeout(700)
				pg.screenshot(path=str(OUT / f"F2f_{prefix}_painel_{vp}.png"))
				pg.click("#z-fit")
				pg.wait_for_timeout(900)
				pg.screenshot(path=str(OUT / f"F2f_{prefix}_inteiro_{vp}.png"))
				pg.close()
			br.close()
	finally:
		server.should_exit = True
		th.join(10)


if __name__ == "__main__":
	main(sys.argv[1])
