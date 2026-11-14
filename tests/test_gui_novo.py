"""GUI nova em /novo/ (redesenho F1b): casca + «Montar» em Chromium headless sobre o projeto sintético (slow).

A proposta de gémea do projeto de ``tests/test_query.py`` passa a «coloca agora» com uma vizinha marcada pelo
Tiago. Verifica: o cartão (saco, nº, linha · coluna, confiança em palavras), nenhum termo proibido no ecrã
Montar (ESPEC §2, §6), «Encaixa» em 1 clique e «Desfazer» em 1 clique, «Não encaixa» → «Porquê?» → motivo →
Ctrl+Z, «Saltar» e teclas, «Porquê esta peça?» com 3 traços, e a 390 px sem scroll horizontal e alvos ≥ 44 px.

F1c (2026-11-14): sem vizinha montada (``guarda_posicao``) o Montar nunca diz «Nada para ir buscar»: cartão «Guardar à
parte» (sem «Encaixa», alvo tracejado, «Guardei à parte» e «Não é esta» desfazíveis), ordem «coloca agora» primeiro,
ecrã vazio com as contagens e a ligação à interface completa, e a lupa com as propostas da peça e do lugar.
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
		assert pg.locator("#legend [data-legend]").count() == 3          # ESPEC §4.1: 3 entradas (F1c: «Lugar provável»)
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
		pg.wait_for_selector(f"#tab-montar .card[data-tipo][data-piece='{tw}']", timeout=60_000)
		assert [e for e in gui.pr.events() if e["action"] == "rejection_undone"]
		# teclas: S salta (só na sessão), N rejeita, «Enganei-me, desfazer» volta
		pg.keyboard.press("s")
		assert pg.locator(f"#tab-montar .card[data-piece='{tw}']").count() == 1      # é a única: volta a ela
		pg.keyboard.press("n")
		pg.wait_for_selector("#b-desfazer", timeout=60_000)
		pg.click("#b-desfazer")
		pg.wait_for_selector(f"#tab-montar .card[data-tipo][data-piece='{tw}']", timeout=60_000)
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


# ---------------------------------------------------------------- F1c: «Guardar à parte», ecrã vazio, lupa
NADA = "Nada para ir buscar"


def _serve(gui):
	import uvicorn
	s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
	server = uvicorn.Server(uvicorn.Config(SV.create_app(gui), host="127.0.0.1", port=port, log_level="warning"))
	th = threading.Thread(target=server.run, daemon=True)
	th.start()
	t0 = time.time()
	while not server.started and time.time() - t0 < 30:
		time.sleep(0.05)
	return f"http://127.0.0.1:{port}", server, th


@pytest.fixture
def guarda(tmp_path):
	"""Sem vizinha montada: a única proposta (gémea) é ``guarda_posicao``; 0 «coloca agora»."""
	from src.query import run_query
	pr, placed, tw, dec = _project(tmp_path)
	run_query(pr, use_image=False)
	gui = SV.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp_path / "uploads"), log=None)
	url, server, th = _serve(gui)
	yield url, gui, tw, dec
	server.should_exit = True
	th.join(10)


def _open_any(browser, url, w=1366, h=768):
	pg = browser.new_page(viewport={"width": w, "height": h})
	errs = []
	pg.on("pageerror", lambda e: errs.append(str(e)))
	pg.goto(url + "/novo/")
	pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
	return pg, errs


def _no_forbidden(txt):
	for pat in FORBIDDEN:
		assert not re.search(pat, txt), f"termo proibido {pat!r}: {txt!r}"


def test_guardar_card_not_nada_no_encaixa_dashed(guarda, browser):
	"""Obrigatório: com propostas no fetch.json e 0 «coloca agora», o Montar NÃO diz «Nada para ir buscar»."""
	url, gui, tw, dec = guarda
	pg, errs = _open_any(browser, url)
	try:
		pg.wait_for_selector("#tab-montar .card[data-tipo='guardar']", timeout=30_000)
		txt = _montar_text(pg)
		assert NADA not in txt
		assert pg.locator("#tab-montar .card").get_attribute("data-piece") == tw
		assert "Guardar à parte" in txt and "A confirmar por ti" in txt and "Lugar provável: linha" in txt
		assert pg.locator("#b-encaixa").count() == 0                                   # sem «Encaixa»
		assert pg.locator("#b-guardar").inner_text() == "Guardei à parte"
		assert pg.locator("#b-nao").inner_text() == "Não é esta"
		assert "quase certo" not in txt
		_no_forbidden(txt)
		# alvo tracejado com «lugar provável», não o «vai aqui» cheio
		assert pg.locator("#lyr-alvo rect.b-alvo-tracejado").count() == 1
		assert pg.locator("#lyr-alvo rect.b-alvo").count() == 0
		assert "lugar provável" in pg.locator("#lyr-alvo").text_content() and "vai aqui" not in pg.locator("#lyr-alvo").text_content()
		dash = pg.evaluate("getComputedStyle(document.querySelector('#lyr-alvo rect.b-alvo-tracejado')).strokeDasharray")
		assert dash and dash != "none", dash
		# Enter não faz nada neste cartão (não há «Encaixa»)
		pg.locator("#board").click(position={"x": 5, "y": 5})
		pg.keyboard.press("Enter")
		pg.wait_for_timeout(600)
		assert gui.pr.piece(tw).estado == "solta"
		assert not errs, errs
	finally:
		pg.close()


def test_guardar_then_undo_toast_and_ctrl_z(guarda, browser):
	url, gui, tw, dec = guarda
	pg, errs = _open_any(browser, url)
	try:
		pg.wait_for_selector("#b-guardar", timeout=30_000)
		pg.click("#b-guardar")
		# ecrã vazio verdadeiro: 1 guardada à parte, ligação à interface completa; nunca «Nada para ir buscar»
		pg.wait_for_selector("#tab-montar [data-estado=vazio_com_propostas]", timeout=60_000)
		assert gui.pr.piece(tw).estado == "posicao_conhecida"
		txt = _montar_text(pg)
		assert NADA not in txt
		assert "1 peça guardada à parte" in pg.locator("#m-resumo [data-k=guardadas]").inner_text()
		assert pg.locator("#m-completa").get_attribute("href") == "/"
		_no_forbidden(txt)
		toast = pg.locator("#toast .undo-toast")
		assert "guardada à parte" in toast.inner_text() and not re.search(r"\bP\d{4}\b", toast.inner_text())
		toast.locator("button").click()
		pg.wait_for_selector(f"#tab-montar .card[data-piece='{tw}'][data-tipo='guardar']", timeout=60_000)
		assert gui.pr.piece(tw).estado == "solta"
		assert [e for e in gui.pr.events() if e["action"] == "position_cleared"][-1].get("desfaz") is True
		# Ctrl+Z também desfaz
		pg.click("#b-guardar")
		pg.wait_for_selector("#tab-montar [data-estado=vazio_com_propostas]", timeout=60_000)
		pg.keyboard.press("Control+z")
		pg.wait_for_selector(f"#tab-montar .card[data-piece='{tw}']", timeout=60_000)
		assert gui.pr.piece(tw).estado == "solta"
		assert not errs, errs
	finally:
		pg.close()


def test_nao_e_esta_undo(guarda, browser):
	url, gui, tw, dec = guarda
	pg, errs = _open_any(browser, url)
	try:
		pg.wait_for_selector("#b-nao", timeout=30_000)
		pg.click("#b-nao")
		pg.wait_for_selector("#m-motivos", timeout=60_000)
		assert "Não é esta" in pg.locator("#tab-montar h3").inner_text()
		assert [e for e in gui.pr.events() if e["action"] == "twin_rejected"]
		pg.click("#b-desfazer")                                                       # «Enganei-me, desfazer»
		pg.wait_for_selector(f"#tab-montar .card[data-tipo][data-piece='{tw}']", timeout=60_000)
		assert not gui.pr.model.rejections
		pg.click("#b-nao")
		pg.wait_for_selector("#m-motivos", timeout=60_000)
		pg.keyboard.press("Control+z")
		pg.wait_for_selector(f"#tab-montar .card[data-tipo][data-piece='{tw}']", timeout=60_000)
		assert not gui.pr.model.rejections
		assert len([e for e in gui.pr.events() if e["action"] == "rejection_undone"]) == 2
		assert not errs, errs
	finally:
		pg.close()


def test_order_coloca_first_then_guardar(guarda, browser):
	"""Mesmo que o servidor mande um «guardar» à frente, o browser mostra primeiro as «coloca agora»; uma «coloca agora»
	saltada uma vez continua antes dos «guardar»; saltada duas vezes vai para o fim de tudo (§8.2)."""
	import json
	url, gui, tw, dec = guarda
	m = gui.montar_json()
	g = m["itens"][0]
	c = dict(g, piece=dec, n_no_lote=3, tipo="gemea", guardar=None, cell=[1, 1],
			 encaixa={"url": "/api/confirm", "body": {"acao": "place", "piece": dec, "cell": [1, 1], "origin": "gemeo"}})
	m.update(itens=[g, c], total=2, n_coloca=1, n_guardar=1, saco=3, ordem_sacos=[3])
	pg = browser.new_page(viewport={"width": 1366, "height": 768})
	errs = []
	pg.on("pageerror", lambda e: errs.append(str(e)))
	pg.route("**/api/montar*", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(m)))
	try:
		pg.goto(url + "/novo/")
		pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
		pg.wait_for_selector("#tab-montar .card[data-piece]", timeout=30_000)
		assert pg.locator("#tab-montar .card").get_attribute("data-piece") == dec
		assert pg.locator("#b-encaixa").count() == 1
		assert pg.locator("#m-seguir [data-tipo=guardar]").count() == 1
		assert "guardar à parte" in pg.locator("#m-seguir").inner_text()
		pg.click("#b-saltar")
		assert pg.locator("#tab-montar .card").get_attribute("data-piece") == dec        # 1.º salto: ainda antes
		pg.click("#b-saltar")
		assert pg.locator("#tab-montar .card").get_attribute("data-piece") == tw         # 2.º salto: fim de tudo
		assert pg.locator("#tab-montar .card").get_attribute("data-tipo") == "guardar"
		assert not errs, errs
	finally:
		pg.close()


def test_empty_screen_counts_groups_only(guarda, browser):
	"""fetch.json só com grupos por ancorar: o vazio conta-os e liga à interface completa (até à F4)."""
	import json
	url, gui, tw, dec = guarda
	fp = gui.pr.p("fetch.json")
	with open(fp, encoding="utf-8") as fh:
		f = json.load(fh)
	f["entries"] = [{"origin": "seccao", "decision": "por_ancorar", "piece": None, "cell": [2, 2], "section": "G0001",
					 "candidates": [], "ordem": 1},
					{"origin": "seccao", "decision": "por_ancorar", "piece": None, "cell": None, "section": "G0002",
					 "candidates": [], "ordem": 2}]
	with open(fp, "w", encoding="utf-8") as fh:
		json.dump(f, fh)
	pg, errs = _open_any(browser, url)
	try:
		pg.wait_for_selector("#tab-montar [data-estado=vazio_com_propostas]", timeout=30_000)
		txt = _montar_text(pg)
		assert NADA not in txt
		assert "2 grupos sem lugar" in pg.locator("#m-resumo [data-k=grupos]").inner_text()
		assert pg.locator("#m-completa").get_attribute("href") == "/"
		_no_forbidden(txt)
		assert not errs, errs
	finally:
		pg.close()


def test_lupa_shows_piece_and_place_proposals(guarda, browser):
	url, gui, tw, dec = guarda
	cell = [e for e in gui.fetch_entries() if e.get("piece") == tw][0]["cell"]
	p = gui.pr.piece(tw)
	pg, errs = _open_any(browser, url)
	try:
		pg.fill("#q", tw)
		pg.press("#q", "Enter")
		pg.wait_for_selector("#lupa-res:not([hidden]) #lupa-props li", timeout=30_000)
		assert pg.locator("#lupa-res").get_attribute("data-kind") == "peca"
		li = pg.locator("#lupa-props li")
		assert li.count() == 1 and li.get_attribute("data-grupo") == "guarda_posicao"
		t = pg.locator("#lupa-res").inner_text()
		assert f"Saco {p.lote} · nº {p.n_no_lote}" in t and f"Linha {cell[0]} · coluna {cell[1]}" in t and "guardar à parte" in t
		_no_forbidden(t)
		pg.click("#lupa-fechar")
		assert pg.locator("#lupa-res").is_hidden()
		pg.fill("#q", f"{cell[0]},{cell[1]}")
		pg.press("#q", "Enter")
		pg.wait_for_selector("#lupa-res[data-kind=lugar]:not([hidden]) #lupa-props li", timeout=30_000)
		t = pg.locator("#lupa-res").inner_text()
		assert "Ainda vazio." in t and f"Saco {p.lote} · nº {p.n_no_lote}" in t and "guardar à parte" in t
		assert pg.locator("#lupa-props li").get_attribute("data-piece") == tw
		_no_forbidden(t.replace(f"Linha {cell[0]} · coluna {cell[1]}", ""))
		# um lugar sem propostas diz-o
		pg.fill("#q", "1,1")
		pg.press("#q", "Enter")
		pg.wait_for_selector("#lupa-res[data-kind=lugar] #lupa-sem", timeout=30_000)
		assert not errs, errs
	finally:
		pg.close()


def test_guardar_phone_layout(guarda, browser):
	url, gui, tw, dec = guarda
	pg, errs = _open_any(browser, url, 390, 844)
	try:
		pg.wait_for_selector("#b-guardar", timeout=30_000)
		assert not pg.evaluate("document.documentElement.scrollWidth > window.innerWidth")
		for sel in ("#b-guardar", "#b-nao", "#b-saltar", "#b-porque"):
			bb = pg.locator(sel).bounding_box()
			assert bb and bb["height"] >= 44 - 0.5 and bb["x"] >= 0 and bb["x"] + bb["width"] <= 390, (sel, bb)
		pg.fill("#q", tw)
		pg.press("#q", "Enter")
		pg.wait_for_selector("#lupa-res:not([hidden])", timeout=30_000)
		bb = pg.locator("#lupa-fechar").bounding_box()
		assert bb["height"] >= 44 - 0.5
		assert not pg.evaluate("document.documentElement.scrollWidth > window.innerWidth")
		pg.click("#lupa-fechar")
		pg.click("#b-guardar")
		pg.wait_for_selector("#m-completa", timeout=60_000)
		assert pg.locator("#m-completa").bounding_box()["height"] >= 44 - 0.5
		assert not pg.evaluate("document.documentElement.scrollWidth > window.innerWidth")
		assert not errs, errs
	finally:
		pg.close()
