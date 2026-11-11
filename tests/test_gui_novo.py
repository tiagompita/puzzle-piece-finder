"""GUI nova em /novo/ (redesenho F1b): casca + «Montar» em Chromium headless sobre o projeto sintético (slow).

A proposta de gémea do projeto de ``tests/test_query.py`` passa a «coloca agora» com uma vizinha marcada pelo
Tiago. Verifica: o cartão (saco, nº, linha · coluna, confiança em palavras), nenhum termo proibido no ecrã
Montar (ESPEC §2, §6), «Encaixa» em 1 clique e «Desfazer» em 1 clique, «Não encaixa» → «Porquê?» → motivo →
Ctrl+Z, «Saltar» e teclas, «Porquê esta peça?» com 3 traços, e a 390 px sem scroll horizontal e alvos ≥ 44 px.
"""

import re
import socket
import threading
import time

import pytest

pytestmark = pytest.mark.slow
pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("uvicorn")
sync_api = pytest.importorskip("playwright.sync_api")

from src import server as SV  # noqa: E402
from test_query import _project  # noqa: E402

# ESPEC §2/§6: nada disto no ecrã Montar (o identificador P#### só no elemento pequeno .pid)
FORBIDDEN = [r"\(\s*\d+\s*,\s*\d+\s*\)", r"\baceite\b", r"\balta\b", r"amb[ií]gua", r"\bColoquei\b", r"Vai buscar",
			 r"\bmm\b", r"\bmargem\b", "ΔE", "fit_version", r"\bclasse\b", r"\bP\d{4}\b", r"\bm[eé]dia\b"]


@pytest.fixture
def base(tmp_path):
	import uvicorn
	from src.query import run_query
	pr, placed, tw, dec = _project(tmp_path)
	run_query(pr, use_image=False)
	from src.query import load_fetch
	cell = [e for e in load_fetch(pr)["entries"] if e.get("piece")][0]["cell"]
	nb = [n for n in pr.board.neighbours(tuple(cell)) if pr.board[n]["estado"] == "vazia"][0]
	pr.mark_cell_full(nb)
	pr.save()
	gui = SV.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp_path / "uploads"), log=None)
	s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
	server = uvicorn.Server(uvicorn.Config(SV.create_app(gui), host="127.0.0.1", port=port, log_level="warning"))
	th = threading.Thread(target=server.run, daemon=True)
	th.start()
	t0 = time.time()
	while not server.started and time.time() - t0 < 30:
		time.sleep(0.05)
	yield f"http://127.0.0.1:{port}", gui, tw
	server.should_exit = True
	th.join(10)


@pytest.fixture(scope="module")
def browser():
	with sync_api.sync_playwright() as pw:
		try:
			br = pw.chromium.launch()
		except Exception as e:  # chromium not installed
			pytest.skip(f"chromium indisponível: {e}")
		yield br
		br.close()


def _open(browser, base, w=1366, h=768):
	pg = browser.new_page(viewport={"width": w, "height": h})
	errs = []
	pg.on("pageerror", lambda e: errs.append(str(e)))
	pg.goto(base + "/novo/")
	pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
	pg.wait_for_selector("#tab-montar .card[data-piece]", timeout=30_000)
	return pg, errs


def _montar_text(pg):
	return pg.evaluate("""(() => { const c = document.querySelector('#tab-montar').cloneNode(true);
		c.querySelectorAll('.pid, details.numeros').forEach((x) => x.remove()); return c.innerText + '\\n' + document.querySelector('#top').innerText; })()""")


def test_montar_card_words_and_switch(base, browser):
	url, gui, tw = base
	pg, errs = _open(browser, url)
	try:
		card = pg.locator("#tab-montar .card")
		assert card.get_attribute("data-piece") == tw
		txt = _montar_text(pg)
		p = gui.pr.piece(tw)
		assert f"Saco {p.lote}" in txt and f"peça nº {p.n_no_lote}" in txt
		assert re.search(r"Linha \d+ · coluna \d+", txt)
		assert "A confirmar por ti" in txt                      # sem histórico físico: nunca «quase certo»
		assert "1 de 1 neste saco · 1 no total" in txt
		for pat in FORBIDDEN:
			assert not re.search(pat, txt), f"termo proibido {pat!r} no Montar: {txt!r}"
		assert pg.locator("#lyr-alvo rect.b-alvo").count() == 1
		assert "vai aqui" in pg.locator("#lyr-alvo").text_content()
		assert pg.locator("#legend [data-legend]").count() == 2
		# «Porquê esta peça?»: 3 frases com traços
		pg.click("#b-porque")
		assert pg.locator("#m-porque li").count() == 3
		assert pg.locator("#m-porque li .bars").count() == 3
		for pat in FORBIDDEN:
			assert not re.search(pat, _montar_text(pg)), pat
		pg.keyboard.press("Escape")
		assert pg.locator("#b-encaixa").count() == 1
		# interruptor
		pg.goto(url + "/?ui=novo")
		pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
		assert pg.url.endswith("/novo/")
		assert not errs, errs
	finally:
		pg.close()


def test_encaixa_and_undo(base, browser):
	url, gui, tw = base
	pg, errs = _open(browser, url)
	try:
		pg.click("#b-encaixa")
		pg.wait_for_function("document.querySelector('#tab-montar [data-estado=vazio]')", timeout=60_000)
		assert gui.pr.piece(tw).estado == "colocada"
		toast = pg.locator("#toast .undo-toast")
		assert "no lugar" in toast.inner_text() and not re.search(r"\bP\d{4}\b", toast.inner_text())
		toast.locator("button").click()
		pg.wait_for_selector(f"#tab-montar .card[data-piece='{tw}']", timeout=60_000)
		assert gui.pr.piece(tw).estado == "solta"
		evs = gui.pr.events()
		assert [e for e in evs if e["action"] == "unplaced"][-1].get("desfaz") is True
		assert not errs, errs
	finally:
		pg.close()


def test_nao_encaixa_reason_and_ctrl_z(base, browser):
	url, gui, tw = base
	pg, errs = _open(browser, url)
	try:
		pg.click("#b-nao")
		pg.wait_for_selector("#m-motivos", timeout=60_000)
		assert "Não encaixou" in pg.locator("#tab-montar").inner_text()
		assert pg.locator("#m-motivos button").count() == 3
		pg.click("#m-motivos [data-motivo=imagem]")
		pg.wait_for_selector("#tab-montar [data-estado=vazio]", timeout=30_000)
		noted = [e for e in gui.pr.events() if e["action"] == "rejection_noted"]
		assert noted and noted[-1]["motivo"] == "imagem" and noted[-1]["piece"] == tw
		pg.keyboard.press("Control+z")
		pg.wait_for_selector(f"#tab-montar .card[data-piece='{tw}']", timeout=60_000)
		assert [e for e in gui.pr.events() if e["action"] == "rejection_undone"]
		# teclas: S salta (só na sessão), N rejeita, «Enganei-me, desfazer» volta
		pg.keyboard.press("s")
		assert pg.locator(f"#tab-montar .card[data-piece='{tw}']").count() == 1      # é a única: volta a ela
		pg.keyboard.press("n")
		pg.wait_for_selector("#b-desfazer", timeout=60_000)
		pg.click("#b-desfazer")
		pg.wait_for_selector(f"#tab-montar .card[data-piece='{tw}']", timeout=60_000)
		assert not gui.pr.model.rejections
		assert not errs, errs
	finally:
		pg.close()


def test_phone_layout(base, browser):
	url, gui, tw = base
	pg, errs = _open(browser, url, 390, 844)
	try:
		assert not pg.evaluate("document.documentElement.scrollWidth > window.innerWidth")
		for sel in ("#b-encaixa", "#b-nao", "#b-saltar", "#b-porque", "#tabs button", "#menu-btn", "#z-in"):
			for bb in [pg.locator(sel).nth(i).bounding_box() for i in range(pg.locator(sel).count())]:
				assert bb and bb["height"] >= 44 - 0.5, (sel, bb)
		bb = pg.locator("#b-encaixa").bounding_box()
		assert bb["x"] >= 0 and bb["x"] + bb["width"] <= 390
		assert not errs, errs
	finally:
		pg.close()
