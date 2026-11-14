"""F2b da GUI nova em Chromium headless (slow): a lupa de dois separadores, a faixa «Ligação perdida» e o indicador de
trabalho («A gravar…», «A atualizar sugestões…»). Projeto sintético de ``tests/test_query.py`` (grelha 4 × 6, saco 3 com
os nºs 1 a 3).
"""

import re
import socket
import threading
import time

import pytest

pytestmark = pytest.mark.slow
pytest.importorskip("fastapi")
pytest.importorskip("uvicorn")
sync_api = pytest.importorskip("playwright.sync_api")

from src import fit as F  # noqa: E402
from src import server as SV  # noqa: E402
from test_gui_novo import base, browser, _buscar_lugar, _buscar_peca, _no_forbidden, _montar_text  # noqa: E402,F401
from test_query import _project  # noqa: E402


def _open(browser, url, w=1366, h=768):
	pg = browser.new_page(viewport={"width": w, "height": h})
	errs = []
	pg.on("pageerror", lambda e: errs.append(str(e)))
	pg.goto(url + "/novo/")
	pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
	return pg, errs


def _toast_text(pg):
	return pg.locator("#toast").inner_text()


# ---------------------------------------------------------------- 1. lupa com separadores «Peça» e «Lugar»
def test_lupa_two_tabs_default_and_remembered(base, browser):
	url, gui, tw = base
	pg, errs = _open(browser, url)
	try:
		# «Peça» por omissão: Saco e nº; «Lugar» escondido
		assert pg.get_attribute("#s-peca", "aria-selected") == "true" and pg.get_attribute("#s-lugar", "aria-selected") == "false"
		assert pg.locator("#q-saco").is_visible() and pg.locator("#q-n").is_visible()
		assert pg.locator("#q-linha").is_hidden() and pg.locator("#q-coluna").is_hidden()
		assert "Saco" in pg.locator("#s-campos-peca").inner_text() and "nº" in pg.locator("#s-campos-peca").inner_text()
		pg.click("#s-lugar")
		assert pg.locator("#q-linha").is_visible() and pg.locator("#q-coluna").is_visible() and pg.locator("#q-saco").is_hidden()
		txt = pg.locator("#s-campos-lugar").inner_text()
		assert "Linha" in txt and "Coluna" in txt
		# guardado por aparelho: sobrevive a recarregar a página
		pg.reload()
		pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
		assert pg.get_attribute("#s-lugar", "aria-selected") == "true" and pg.locator("#q-linha").is_visible()
		pg.click("#s-peca")
		pg.reload()
		pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
		assert pg.get_attribute("#s-peca", "aria-selected") == "true" and pg.locator("#q-saco").is_visible()
		assert not errs, errs
	finally:
		pg.close()


def test_lupa_finds_piece_by_bag_number_and_by_pid_and_place(base, browser):
	url, gui, tw = base
	p = gui.pr.piece(tw)
	pg, errs = _open(browser, url)
	try:
		_buscar_peca(pg, p.lote, p.n_no_lote)                   # Saco + nº
		pg.wait_for_selector("#lupa-res[data-kind=peca]:not([hidden])", timeout=30_000)
		assert f"Saco {p.lote} · nº {p.n_no_lote}" in pg.locator("#lupa-res").inner_text()
		pg.click("#lupa-fechar")
		_buscar_peca(pg, tw.lower())                            # P#### no 1.º campo (minúsculas também)
		pg.wait_for_selector("#lupa-res[data-kind=peca]:not([hidden])", timeout=30_000)
		assert f"Saco {p.lote} · nº {p.n_no_lote}" in pg.locator("#lupa-res").inner_text()
		pg.click("#lupa-fechar")
		_buscar_peca(pg, "P1")                                  # P1 = P0001 (a peça colocada)
		pg.wait_for_selector("#lupa-res[data-kind=peca]:not([hidden])", timeout=30_000)
		pg.click("#lupa-fechar")
		_buscar_lugar(pg, 2, 3)
		pg.wait_for_selector("#lupa-res[data-kind=lugar]:not([hidden])", timeout=30_000)
		assert "Linha 2 · coluna 3" in pg.locator("#lupa-res").inner_text()
		assert not errs, errs
	finally:
		pg.close()


def test_lupa_clear_messages_for_bad_values(base, browser):
	"""Valores fora da grelha ou inexistentes: mensagem clara, nada de adivinhar (sem interpretar texto livre)."""
	url, gui, tw = base
	pg, errs = _open(browser, url)
	try:
		rows, cols = gui.pr.profile.rows, gui.pr.profile.cols
		lote = gui.pr.piece(tw).lote
		_buscar_lugar(pg, rows + 1, 1)
		pg.wait_for_function("document.querySelector('#toast').innerText.includes('Linha')", timeout=5_000)
		assert f"Linha 1 a {rows}" in _toast_text(pg)
		_buscar_lugar(pg, 1, cols + 5)
		pg.wait_for_function("document.querySelector('#toast').innerText.includes('Coluna 1 a')", timeout=5_000)
		assert f"Coluna 1 a {cols}" in _toast_text(pg)
		_buscar_lugar(pg, 0, 1)
		pg.wait_for_function("document.querySelector('#toast').innerText.includes('a linha 0')", timeout=5_000)
		_buscar_lugar(pg, "", "")
		pg.wait_for_function("document.querySelector('#toast').innerText.includes('Escreve a linha e a coluna')", timeout=5_000)
		_buscar_peca(pg, lote, 200)
		pg.wait_for_function(f"document.querySelector('#toast').innerText.includes('Saco {lote} não tem nº 200')", timeout=5_000)
		_buscar_peca(pg, 9, 1)
		pg.wait_for_function("document.querySelector('#toast').innerText.includes('Não há o saco 9')", timeout=5_000)
		_buscar_peca(pg, lote, "")
		pg.wait_for_function("document.querySelector('#toast').innerText.includes('Escreve também o nº')", timeout=5_000)
		_buscar_peca(pg, "banana", 1)
		pg.wait_for_function("document.querySelector('#toast').innerText.includes('não é um saco')", timeout=5_000)
		_buscar_peca(pg, "P9999", "")
		pg.wait_for_function("document.querySelector('#toast').innerText.includes('Não encontrei')", timeout=5_000)
		assert pg.locator("#lupa-res").is_hidden()              # nenhum erro abriu a lupa
		assert not errs, errs
	finally:
		pg.close()


def test_lupa_phone_layout(base, browser):
	url, gui, tw = base
	pg, errs = _open(browser, url, 390, 844)
	try:
		assert not pg.evaluate("document.documentElement.scrollWidth > window.innerWidth")
		for sel in ("#s-peca", "#s-lugar", "#q-saco", "#q-n", "#search-btn", "#menu-btn"):
			bb = pg.locator(sel).bounding_box()
			assert bb and bb["height"] >= 44 - 0.5 and bb["x"] >= 0 and bb["x"] + bb["width"] <= 390, (sel, bb)
		pg.click("#s-lugar")
		for sel in ("#q-linha", "#q-coluna"):
			bb = pg.locator(sel).bounding_box()
			assert bb and bb["height"] >= 44 - 0.5 and bb["x"] + bb["width"] <= 390, (sel, bb)
		assert not pg.evaluate("document.documentElement.scrollWidth > window.innerWidth")
		assert not errs, errs
	finally:
		pg.close()


# ---------------------------------------------------------------- 2. «Ligação perdida, a tentar religar…»
def _serve_on(gui, port):
	import uvicorn
	server = uvicorn.Server(uvicorn.Config(SV.create_app(gui), host="127.0.0.1", port=port, log_level="warning",
										   timeout_graceful_shutdown=3))
	th = threading.Thread(target=server.run, daemon=True)
	th.start()
	t0 = time.time()
	while not server.started and time.time() - t0 < 30:
		time.sleep(0.05)
	assert server.started
	return server, th


def test_connection_lost_banner_and_recovery(tmp_path, browser):
	"""O servidor pára com a página aberta: aparece a faixa; quando volta (mesma porta) a faixa some, a página recarrega
	o estado sozinha e volta a reagir aos eventos."""
	from src.query import run_query
	pr, placed, tw, dec = _project(tmp_path)
	run_query(pr, use_image=False)
	gui = SV.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp_path / "uploads"), log=None, queue=False)
	s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
	url = f"http://127.0.0.1:{port}"
	server, th = _serve_on(gui, port)
	pg = browser.new_page(viewport={"width": 1366, "height": 768})
	errs, reqs = [], []
	pg.on("pageerror", lambda e: errs.append(str(e)))
	pg.on("request", lambda r: reqs.append(r.url))
	try:
		pg.goto(url + "/novo/")
		pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
		t0 = time.time()
		while not gui._sse_waiters and time.time() - t0 < 15:      # o EventSource ligou-se
			time.sleep(0.1)
		assert gui._sse_waiters
		assert pg.locator("#ligacao").count() == 0 or pg.locator("#ligacao").is_hidden()
		# o servidor pára (como o Ctrl+C: os fluxos SSE acabam primeiro)
		gui.begin_shutdown()
		server.should_exit = True
		th.join(15)
		assert not th.is_alive()
		pg.wait_for_selector("#ligacao", state="visible", timeout=15_000)
		assert pg.locator("#ligacao").inner_text() == "Ligação perdida, a tentar religar…"
		n_montar = sum(1 for u in reqs if u.endswith("/api/montar") or "/api/montar?" in u)
		# o servidor volta
		gui.closing = False
		server, th = _serve_on(gui, port)
		pg.wait_for_selector("#ligacao", state="hidden", timeout=30_000)
		t0 = time.time()
		while time.time() - t0 < 20 and sum(1 for u in reqs if "/api/montar" in u) <= n_montar:
			pg.wait_for_timeout(200)          # a API síncrona do Playwright só entrega eventos dentro das suas chamadas
		assert sum(1 for u in reqs if "/api/montar" in u) > n_montar, "a página não recarregou o estado ao religar"
		# e continua ligada: um evento do servidor faz recarregar outra vez
		n2 = sum(1 for u in reqs if "/api/montar" in u)
		gui.emit("fetch_changed", {})
		t0 = time.time()
		while time.time() - t0 < 15 and sum(1 for u in reqs if "/api/montar" in u) <= n2:
			pg.wait_for_timeout(200)          # a API síncrona do Playwright só entrega eventos dentro das suas chamadas
		assert sum(1 for u in reqs if "/api/montar" in u) > n2, f"depois de religar, os eventos do servidor não chegam {gui.seq} {len(gui._sse_waiters)} {gui.closing} {[u[-30:] for u in reqs]}"
		assert not errs, errs
	finally:
		pg.close()
		gui.begin_shutdown()
		server.should_exit = True
		th.join(15)


# ---------------------------------------------------------------- 4. indicador de trabalho
def _gate(monkeypatch, mod, name):
	gate, started = threading.Event(), threading.Event()
	real = getattr(mod, name)

	def slow(*a, **kw):
		started.set()
		gate.wait(60)
		return real(*a, **kw)
	monkeypatch.setattr(mod, name, slow)
	return gate, started


def test_working_indicator_while_suggestions_recompute(base, browser, monkeypatch):
	"""«A atualizar sugestões…» no cartão e no tabuleiro enquanto o ranking dos buracos se calcula; o cartão e o resto
	continuam utilizáveis; some quando acaba."""
	url, gui, tw = base
	gate, started = _gate(monkeypatch, F, "rank_all")
	gui._holes = None
	try:
		pg, errs = _open(browser, url)
		try:
			pg.wait_for_selector("#tab-montar .card .trabalho[data-trabalho=sugestoes]", timeout=30_000)
			pg.wait_for_selector("#board-wrap .trabalho.no-tabuleiro[data-trabalho=sugestoes]", timeout=5_000)
			assert "A atualizar sugestões…" in pg.locator("#tab-montar .card .trabalho").inner_text()
			assert pg.locator("#b-encaixa").is_enabled() and pg.locator("#b-nao").is_enabled()     # nada bloqueado
			pg.click("#z-in")                                                                      # o tabuleiro responde
			_no_forbidden(_montar_text(pg))
			gate.set()
			pg.wait_for_function("!document.querySelector('.trabalho')", timeout=60_000)
			assert not errs, errs
		finally:
			pg.close()
	finally:
		gate.set()


def test_working_indicator_while_saving(base, browser, monkeypatch):
	"""«A gravar…» no cartão e no tabuleiro enquanto o servidor grava; durante isso o tabuleiro continua a responder."""
	import src.confirm as C
	url, gui, tw = base
	gate, started = _gate(monkeypatch, C, "confirm")
	pg, errs = _open(browser, url)
	try:
		pg.click("#b-encaixa")
		assert started.wait(15)
		pg.wait_for_selector("#tab-montar .card .trabalho[data-trabalho=gravar]", timeout=5_000)
		pg.wait_for_selector("#board-wrap .trabalho.no-tabuleiro[data-trabalho=gravar]", timeout=5_000)
		assert "A gravar…" in pg.locator("#board-wrap .trabalho").inner_text()
		pg.click("#z-in")
		pg.click("#z-out")
		gate.set()
		pg.wait_for_function("!document.querySelector('.trabalho[data-trabalho=gravar]')", timeout=60_000)
		assert gui.pr.piece(tw).estado == "colocada"
		assert not errs, errs
	finally:
		gate.set()
		pg.close()
