"""F2 da GUI nova em Chromium headless (slow): painel da peça, lugar vazio, «Pôr uma peça à mão», desfazer global e
«Definições › Cor das peças» (ESPEC §4.4–§4.6; plano de 2026-11-14 com as decisões c e g).

Projeto sintético de ``tests/test_query.py`` (grelha 4 × 6; P0001 colocada em (2,3); gémea de (l, c) = (5 − l, 7 − c)).
"""

import hashlib
import os
import re
import socket
import threading
import time

import pytest

pytestmark = pytest.mark.slow
pytest.importorskip("fastapi")
pytest.importorskip("uvicorn")
sync_api = pytest.importorskip("playwright.sync_api")

from src import server as SV  # noqa: E402
from test_query import _project  # noqa: E402
from test_gui_novo import FORBIDDEN, browser  # noqa: E402,F401  (fixture do Chromium)


def _serve(gui):
	import uvicorn
	s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
	server = uvicorn.Server(uvicorn.Config(SV.create_app(gui), host="127.0.0.1", port=port, log_level="warning"))
	th = threading.Thread(target=server.run, daemon=True)
	th.start()
	t0 = time.time()
	while not server.started and time.time() - t0 < 30:
		time.sleep(0.05)
	return server, th, f"http://127.0.0.1:{port}"


@pytest.fixture
def f2(tmp_path):
	from src.query import run_query
	pr, placed, tw, dec = _project(tmp_path)
	run_query(pr, use_image=False)
	gui = SV.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp_path / "uploads"), log=None, queue=False)
	server, th, url = _serve(gui)
	yield url, gui, placed, tw, dec
	server.should_exit = True
	th.join(10)


def _open(browser, url, w=1366, h=768):
	pg = browser.new_page(viewport={"width": w, "height": h})
	errs = []
	pg.on("pageerror", lambda e: errs.append(str(e)))
	pg.goto(url + "/novo/")
	pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
	return pg, errs


def _tap(pg, l, c):
	pg.evaluate(f"S.onBoardTap({l}, {c})")


def _panel_text(pg):
	return pg.evaluate("""(() => { const c = document.querySelector('#tab-montar').cloneNode(true);
		c.querySelectorAll('.pid').forEach((x) => x.remove()); return c.innerText; })()""")


def test_piece_panel_sheet_and_tirar_with_undo(f2, browser):
	"""Tocar numa peça: saco, nº, linha · coluna, a folha com a peça marcada e o P#### pequeno; «Tirar do lugar» sem
	confirmação, desfeito pela faixa e por Ctrl+Z."""
	url, gui, placed, tw, dec = f2
	pg, errs = _open(browser, url)
	try:
		_tap(pg, 2, 3)
		pg.wait_for_selector("#painel[data-kind='peca']", timeout=20_000)
		p = gui.pr.piece(placed)
		t = _panel_text(pg)
		assert f"Saco {p.lote}" in t and f"nº {p.n_no_lote}" in t and "Linha 2 · coluna 3" in t and "No lugar" in t
		assert pg.locator("#p-pid").inner_text() == placed
		assert f"highlight={placed}" in pg.locator("#p-folha img").get_attribute("src")
		assert pg.locator("#lyr-alvo rect.painel-sel").count() == 1
		for pat in FORBIDDEN:
			assert not re.search(pat, t), (pat, t)
		assert pg.locator("#p-recorte").get_attribute("href") == f"/?peca={placed}&contorno=1"
		pg.click("#p-tirar")
		pg.wait_for_selector("#m-ultimo[data-tipo='tirar']", timeout=30_000)
		pg.wait_for_selector("#painel[data-kind='vazio']", timeout=30_000)
		assert gui.pr.piece(placed).estado in ("solta", "emparelhada")
		ev = [e for e in gui.pr.events() if e["action"] == "unplaced"][-1]
		assert "desfaz" not in ev
		pg.click("#b-desfazer-ultimo")
		pg.wait_for_selector("#painel[data-kind='peca']", timeout=30_000)
		assert gui.pr.piece(placed).estado == "colocada" and gui.pr.piece(placed).celula == (2, 3)
		assert [e for e in gui.pr.events() if e["action"] == "placed"][-1].get("reposicao") is True
		# Ctrl+Z from the panel
		pg.click("#p-tirar")
		pg.wait_for_selector("#m-ultimo[data-tipo='tirar']", timeout=30_000)
		pg.locator("#painel").click(position={"x": 5, "y": 5})
		pg.keyboard.press("Control+z")
		pg.wait_for_function("document.querySelector('#painel') && document.querySelector('#painel').dataset.kind === 'peca'", timeout=30_000)
		assert gui.pr.piece(placed).estado == "colocada"
		assert not errs, errs
	finally:
		pg.close()


def test_por_confirmar_survives_reload_and_is_taken_off(f2, browser):
	"""Requisito 1: uma peça posta «por confirmar» tira-se pelo painel mesmo depois de recarregar a página."""
	url, gui, placed, tw, dec = f2
	pg, errs = _open(browser, url)
	try:
		pg.evaluate("""fetch('/api/confirm', {method: 'POST', headers: {'Content-Type': 'application/json'},
			body: JSON.stringify({acao: 'position_known', piece: '%s', cell: [4, 1], origin: 'manual', theta_deg: 10})})""" % dec)
		pg.wait_for_function(f"() => true", timeout=1000)
		t0 = time.time()
		while gui.pr.piece(dec).estado != "posicao_conhecida" and time.time() - t0 < 30:
			time.sleep(0.1)
		pg.reload()
		pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
		_tap(pg, 4, 1)
		pg.wait_for_selector("#painel[data-kind='por_confirmar']", timeout=20_000)
		assert "Por confirmar · ainda sem peças ao lado" in _panel_text(pg)
		pg.click("#p-tirar")
		pg.wait_for_selector("#painel[data-kind='vazio']", timeout=30_000)
		assert gui.pr.piece(dec).estado == "solta"
		pg.click("#b-desfazer-ultimo")
		pg.wait_for_selector("#painel[data-kind='por_confirmar']", timeout=30_000)
		assert gui.pr.piece(dec).estado == "posicao_conhecida" and abs(gui.pr.piece(dec).theta_deg - 10.0) < 1e-6
		assert not errs, errs
	finally:
		pg.close()


def _slow_verify(gui, delay_s):
	"""Atrasa o ``verificar`` no servidor (um atraso no route do Playwright bloquearia o próprio teste)."""
	real = gui.verify_json

	def slow(*a, **k):
		time.sleep(delay_s)
		return real(*a, **k)
	gui.verify_json = slow


def test_por_mao_non_blocking_rodar_and_undo(f2, browser):
	"""Lugar vazio → «Pôr uma peça aqui» → saco e nº → «a verificar…» com «Pôr aqui» ativo → «Rodar» aborta a anterior →
	grava ``place`` (vizinha montada) com o θ escolhido → Desfazer."""
	url, gui, placed, tw, dec = f2
	pg, errs = _open(browser, url)
	failed = []
	pg.on("requestfailed", lambda r: failed.append(r.url) if r.url.endswith("/verificar") else None)
	try:
		_tap(pg, 2, 4)
		pg.wait_for_selector("#painel[data-kind='vazio']", timeout=20_000)
		assert "Sem sugestão por agora." in _panel_text(pg) or pg.locator("#p-sugestao").count() == 1
		pg.click("#p-por")
		p = gui.pr.piece(tw)
		pg.fill("#pm-saco", str(p.lote))
		pg.fill("#pm-n", str(p.n_no_lote))
		pg.wait_for_selector("#pm-frase[data-estado='ok']", timeout=10_000)
		assert "está solta" in pg.locator("#pm-frase").inner_text()
		_slow_verify(gui, 1.5)
		pg.click("#pm-continuar")
		pg.wait_for_selector("#por-mao[data-passo='2']", timeout=10_000)
		assert pg.locator("#pm-ver li[data-estado='a_verificar']").count() >= 2
		assert "a verificar…" in pg.locator("#pm-ver").inner_text()
		assert pg.locator("#pm-por").is_enabled()                       # does not block
		assert pg.locator("#pm-por").inner_text().strip() == "Pôr aqui"     # (2,4) has a placed neighbour
		th0 = float(pg.locator("#pm-preview").get_attribute("data-theta"))
		pg.click("#pm-rodar")                                             # aborts the 1st check
		pg.click("#pm-rodar")                                             # and the 2nd
		pg.wait_for_selector("#pm-ver li:not([data-estado='a_verificar'])", timeout=30_000)
		assert len(failed) >= 2, failed
		th = float(pg.locator("#pm-preview").get_attribute("data-theta"))
		assert abs(((th - th0 - 180) + 180) % 360 - 180) < 0.02, (th0, th)
		keys = pg.eval_on_selector_all("#pm-ver li", "els => els.map(e => e.dataset.chave)")
		assert keys[-2:] == ["forma", "imagem"]
		assert "fica no lugar" in pg.locator("#pm-estado").inner_text()
		pg.click("#pm-por")
		pg.wait_for_selector("#painel[data-kind='peca']", timeout=30_000)
		q = gui.pr.piece(tw)
		assert q.estado == "colocada" and q.celula == (2, 4) and abs(((q.theta_deg - th) + 180) % 360 - 180) < 0.02
		assert f"Saco {p.lote} · nº {p.n_no_lote} no lugar." in pg.locator("#m-ultimo").inner_text()
		pg.click("#b-desfazer-ultimo")
		pg.wait_for_selector("#painel[data-kind='vazio']", timeout=30_000)
		assert gui.pr.piece(tw).estado == "solta"
		assert [e for e in gui.pr.events() if e["action"] == "unplaced"][-1].get("desfaz") is True
		assert not errs, errs
	finally:
		pg.close()


def test_por_mao_without_neighbour_stays_por_confirmar(f2, browser):
	"""Decisão g: sem vizinha montada o botão diz «Colocar aqui, por confirmar» e grava ``position_known``."""
	url, gui, placed, tw, dec = f2
	pg, errs = _open(browser, url)
	try:
		_tap(pg, 4, 1)
		pg.wait_for_selector("#painel[data-kind='vazio']", timeout=20_000)
		pg.click("#p-por")
		p = gui.pr.piece(dec)
		pg.fill("#pm-saco", str(p.lote))
		pg.fill("#pm-n", str(p.n_no_lote))
		pg.wait_for_selector("#pm-frase[data-estado='ok']", timeout=10_000)
		pg.click("#pm-continuar")
		pg.wait_for_selector("#pm-ver li:not([data-estado='a_verificar'])", timeout=30_000)
		assert pg.locator("#pm-por").inner_text().strip() == "Colocar aqui, por confirmar"
		assert "por confirmar" in pg.locator("#pm-estado").inner_text()
		assert pg.locator("#pm-ver li[data-chave='forma'][data-estado='nao_testado']").count() == 1
		pg.click("#pm-por")
		pg.wait_for_selector("#painel[data-kind='por_confirmar']", timeout=30_000)
		assert gui.pr.piece(dec).estado == "posicao_conhecida" and gui.pr.board[(4, 1)]["estado"] == "vazia"
		assert "por confirmar" in pg.locator("#m-ultimo").inner_text()
		pg.click("#b-desfazer-ultimo")
		pg.wait_for_selector("#painel[data-kind='vazio']", timeout=30_000)
		assert gui.pr.piece(dec).estado == "solta"
		assert not errs, errs
	finally:
		pg.close()


def test_encaixa_pair_piece_by_hand_then_undo_clears_the_other(tmp_path, browser):
	"""Requisito 2 / decisão c pela GUI: pôr à mão uma peça de par num lugar com vizinha deixa a outra «por confirmar»
	no lugar gémeo; Desfazer tira as duas e o par volta a «proposto»."""
	from src.query import run_query
	pr, placed, a, b = _project(tmp_path)
	tid = pr.register_pair(a, b)
	pr.save()
	run_query(pr, use_image=False)
	gui = SV.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp_path / "uploads"), log=None, queue=False)
	server, th, url = _serve(gui)
	pg, errs = _open(browser, url)
	try:
		_tap(pg, 2, 4)                              # neighbour (2,3) placed; twin cell (3,3) free
		pg.wait_for_selector("#painel[data-kind='vazio']", timeout=20_000)
		pg.click("#p-por")
		p = gui.pr.piece(a)
		pg.fill("#pm-saco", str(p.lote))
		pg.fill("#pm-n", str(p.n_no_lote))
		pg.wait_for_selector("#pm-frase[data-estado='ok']", timeout=10_000)
		pg.click("#pm-continuar")
		pg.click("#pm-por")
		pg.wait_for_selector("#painel[data-kind='peca']", timeout=30_000)
		assert gui.pr.pairs[tid].estado == "confirmado" and gui.pr.piece(b).estado == "posicao_conhecida"
		assert gui.pr.piece(b).celula == (3, 3)
		pg.click("#b-desfazer-ultimo")
		pg.wait_for_selector("#painel[data-kind='vazio']", timeout=30_000)
		assert gui.pr.pairs[tid].estado == "proposto"
		assert gui.pr.piece(a).estado == "emparelhada" and gui.pr.piece(b).estado == "emparelhada"
		assert not errs, errs
	finally:
		pg.close()
		server.should_exit = True
		th.join(10)


def test_marked_place_and_cell_full_undo(f2, browser):
	"""«Já tem peça, mas não a digitalizei» → o lugar passa a «marcado por ti» (com «Pôr a peça digitalizada aqui» e
	«Afinal está vazio»); o desfazer repõe-no vazio."""
	url, gui, placed, tw, dec = f2
	pg, errs = _open(browser, url)
	try:
		_tap(pg, 1, 1)
		pg.wait_for_selector("#painel[data-kind='vazio']", timeout=20_000)
		assert "/zoom.jpg?side=art" in pg.locator("#p-arte").get_attribute("src")
		pg.click("#p-cheio")
		pg.wait_for_selector("#painel[data-kind='marcado']", timeout=30_000)
		assert pg.locator("#p-vazio").count() == 1 and "Pôr a peça digitalizada aqui" in pg.locator("#p-por").inner_text()
		pg.click("#b-desfazer-ultimo")
		pg.wait_for_selector("#painel[data-kind='vazio']", timeout=30_000)
		assert gui.pr.board[(1, 1)]["estado"] == "vazia"
		assert not errs, errs
	finally:
		pg.close()


def test_phone_layout_panels(f2, browser):
	"""390 × 844: sem scroll horizontal e alvos ≥ 44 px em cada painel novo."""
	url, gui, placed, tw, dec = f2
	pg, errs = _open(browser, url, 390, 844)

	def check(sels):
		assert not pg.evaluate("document.documentElement.scrollWidth > window.innerWidth")
		for sel in sels:
			n = pg.locator(sel).count()
			assert n, sel
			for i in range(n):
				bb = pg.locator(sel).nth(i).bounding_box()
				assert bb and bb["height"] >= 44 - 0.5 and bb["x"] >= 0 and bb["x"] + bb["width"] <= 390 + 0.5, (sel, bb)
	try:
		_tap(pg, 2, 3)
		pg.wait_for_selector("#painel[data-kind='peca']", timeout=20_000)
		check(["#p-tirar", "#p-recorte", "#p-errado", "#p-voltar"])
		pg.click("#p-errado")
		check(["#p-report .tipos .btn", "#p-report-enviar"])
		_tap(pg, 2, 4)
		pg.wait_for_selector("#painel[data-kind='vazio']", timeout=20_000)
		check(["#p-por", "#p-cheio", "#p-voltar"])
		pg.click("#p-por")
		check(["#pm-saco", "#pm-n", "#pm-continuar", "#pm-folha", "#pm-cancelar"])
		p = gui.pr.piece(tw)
		pg.fill("#pm-saco", str(p.lote))
		pg.click("#pm-folha")
		pg.wait_for_selector("#pm-grade button", timeout=10_000)
		check(["#pm-grade button"])
		pg.fill("#pm-n", str(p.n_no_lote))
		pg.wait_for_selector("#pm-frase[data-estado='ok']", timeout=10_000)
		pg.click("#pm-continuar")
		pg.wait_for_selector("#por-mao[data-passo='2']", timeout=10_000)
		check(["#pm-rodar", "#pm-por", "#pm-outra", "#pm-cancelar"])
		assert not errs, errs
	finally:
		pg.close()


def _tree_hash(root, subdirs):
	h = hashlib.sha256()
	for sd in subdirs:
		for dp, dn, fn in sorted(os.walk(os.path.join(root, sd))):
			dn.sort()
			for f in sorted(fn):
				with open(os.path.join(dp, f), "rb") as fh:
					h.update(f.encode() + fh.read())
	return h.hexdigest()


def test_cor_das_pecas_is_display_only(f2, browser):
	"""Item 9: os dois controlos mudam só o filtro CSS das imagens de peça e do tabuleiro, guardado no aparelho;
	nenhum pedido de escrita sai do browser, e os scans, recortes, índice, log e as imagens servidas ficam iguais."""
	url, gui, placed, tw, dec = f2
	path = gui.path
	before = _tree_hash(path, ["crops", "pieces", "scans"]) + hashlib.sha256(open(os.path.join(path, "log.jsonl"), "rb").read()).hexdigest()
	png_before = gui.piece_png(placed, "board", 220)[0]
	pg, errs = _open(browser, url)
	posts = []
	pg.on("request", lambda r: posts.append(r.url) if r.method != "GET" else None)
	try:
		assert pg.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--cor-b').trim()") == "0.92"
		pg.click("#menu-btn")
		pg.click("#m-definicoes")
		pg.wait_for_selector("#definicoes", timeout=5000)
		for sel, v in (("#cor-b", "1.2"), ("#cor-s", "0.6")):
			pg.eval_on_selector(sel, "(el, v) => { el.value = v; el.dispatchEvent(new Event('input', {bubbles: true})); }", v)
		assert pg.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--cor-b').trim()") == "1.2"
		assert pg.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--cor-s').trim()") == "0.6"
		assert "brightness(1.2)" in pg.evaluate("getComputedStyle(document.querySelector('#raster')).filter")
		assert pg.evaluate("JSON.parse(localStorage.getItem('novo-cor'))") == {"b": 1.2, "s": 0.6}
		pg.reload()
		pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
		assert pg.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--cor-b').trim()") == "1.2"
		pg.click("#menu-btn")
		pg.click("#m-definicoes")
		pg.click("#cor-repor")
		assert pg.evaluate("JSON.parse(localStorage.getItem('novo-cor'))") == {"b": 0.92, "s": 1.0}
		pg.click("#def-fechar")
		assert posts == [], posts
		assert not errs, errs
	finally:
		pg.close()
	after = _tree_hash(path, ["crops", "pieces", "scans"]) + hashlib.sha256(open(os.path.join(path, "log.jsonl"), "rb").read()).hexdigest()
	assert after == before
	assert gui.piece_png(placed, "board", 220)[0] == png_before


def test_corrigir_recorte_bridge_opens_the_old_editor(f2, browser):
	"""Decisão d: «Corrigir recorte» abre ``/?peca=P####&contorno=1``; a GUI antiga abre a peça e o editor do recorte."""
	url, gui, placed, tw, dec = f2
	pg = browser.new_page(viewport={"width": 1366, "height": 900})
	errs = []
	pg.on("pageerror", lambda e: errs.append(str(e)))
	try:
		pg.goto(f"{url}/?peca={placed}&contorno=1")
		pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
		pg.wait_for_selector("#ced:not([hidden]) #ced-canvas", timeout=30_000)
		assert pg.evaluate("S.ced && S.ced.pid") == placed
		pg.goto(f"{url}/?peca=nada")                     # anything else: the old GUI as always
		pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
		assert pg.evaluate("!S.ced")
		assert not errs, errs
	finally:
		pg.close()
