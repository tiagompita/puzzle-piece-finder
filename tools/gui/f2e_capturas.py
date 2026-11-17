"""Capturas da F2e da GUI nova (/novo/) sobre o projeto sintetico dos testes, a 1366x768 e 390x844:
menu aberto e painel do lugar aberto por «Ver lugar» (``F2e_<antes|depois>_<ecra>_<vp>.png``).

Uso::

    .venv/Scripts/python.exe tools/gui/f2e_capturas.py antes|depois
"""

import os
import sys
import tempfile
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "tests")]
OUT = REPO / "docs" / "gui" / "screenshots" / "redesenho"
VPS = {"1366": (1366, 768), "390": (390, 844)}


def main(prefix):
	import pytest  # noqa: F401
	from playwright.sync_api import sync_playwright
	from src import server as SV
	from src.query import run_query, load_fetch
	from test_gui_novo import _serve
	from test_query import _project
	tmp = pathlib.Path(tempfile.mkdtemp())
	pr, placed, tw, dec = _project(tmp)
	run_query(pr, use_image=False)
	cell = [e for e in load_fetch(pr)["entries"] if e.get("piece")][0]["cell"]
	nb = [n for n in pr.board.neighbours(tuple(cell)) if pr.board[n]["estado"] == "vazia"][0]
	pr.mark_cell_full(nb)
	pr.save()
	gui = SV.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp / "uploads"), log=None)
	url, server, th = _serve(gui)
	try:
		with sync_playwright() as pw:
			br = pw.chromium.launch()
			for vp, (w, h) in VPS.items():
				pg = br.new_page(viewport={"width": w, "height": h})
				pg.goto(url + "/novo/")
				pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
				pg.wait_for_selector("#tab-montar .card[data-piece]", timeout=60_000)
				pg.wait_for_timeout(600)
				pg.click("#b-ver-lugar")
				pg.wait_for_selector("#painel[data-kind]:not([data-kind='a_carregar'])", timeout=20_000)
				pg.wait_for_timeout(500)
				pg.screenshot(path=str(OUT / f"F2e_{prefix}_ver_lugar_{vp}.png"))
				pg.click("#p-voltar")
				pg.wait_for_selector("#tab-montar .card #b-ver-lugar")
				pg.click("#menu-btn")
				pg.wait_for_timeout(500)
				pg.screenshot(path=str(OUT / f"F2e_{prefix}_menu_{vp}.png"))
				pg.close()
			br.close()
	finally:
		server.should_exit = True
		th.join(10)


if __name__ == "__main__":
	main(sys.argv[1])
