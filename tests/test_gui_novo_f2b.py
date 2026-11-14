"""F2b/F2c da GUI nova em Chromium headless (slow): a lupa de dois botões (F2c; na F2b eram separadores), a faixa «Ligação perdida» e o indicador de
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


# ---------------------------------------------------------------- 1. lupa de dois botões «Peça» e «Posição» (F2c)
def _vis(pg, sel):
	return pg.locator(sel).is_visible()


def _boxes(pg):
	return _vis(pg, "#lupa-c-peca"), _vis(pg, "#lupa-c-pos")


def _msg(pg, modo):
	"""A mensagem da caixa (as buscas à API chegam um instante depois: espera que apareça alguma)."""
	try:
		pg.wait_for_function(f"!document.querySelector('#lupa-m-{modo}').hidden", timeout=5_000)
	except Exception:  # noqa: BLE001 - devolve vazio e o assert diz o que faltou
		pass
	return pg.locator(f"#lupa-m-{modo}").inner_text()


def test_lupa_two_buttons_one_box_at_a_time(base, browser):
	"""Os dois botões abrem cada um a sua caixa de texto; abrir um fecha o outro; os botões ficam sempre à vista."""
	url, gui, tw = base
	pg, errs = _open(browser, url)
	try:
		assert pg.locator("#lupa-b-peca").inner_text().strip() == "Peça" and pg.locator("#lupa-b-pos").inner_text().strip() == "Posição"
		assert _boxes(pg) == (False, False)                       # fechada por omissão
		pg.click("#lupa-b-peca")
		assert _boxes(pg) == (True, False)
		assert pg.get_attribute("#lupa-b-peca", "aria-expanded") == "true" and pg.get_attribute("#lupa-b-pos", "aria-expanded") == "false"
		assert pg.evaluate("document.activeElement.id") == "lupa-q-peca"          # o cursor já está na caixa
		pg.click("#lupa-b-pos")                                   # abrir um fecha o outro
		assert _boxes(pg) == (False, True)
		assert pg.evaluate("document.activeElement.id") == "lupa-q-pos"
		# nenhuma caixa tapa os botões
		pg.wait_for_timeout(300)                                  # a caixa já deslizou até ao sítio
		bb = {k: pg.locator(f"#lupa-b-{k}").bounding_box() for k in ("peca", "pos")}
		cx = pg.locator("#lupa-c-pos").bounding_box()
		for k, b in bb.items():
			assert cx["y"] >= b["y"] + b["height"] - 0.5, (k, b, cx)
		pg.click("#lupa-b-pos")                                   # o mesmo botão fecha
		assert _boxes(pg) == (False, False)
		pg.click("#lupa-b-peca")
		pg.keyboard.press("Escape")                               # Esc fecha
		assert _boxes(pg) == (False, False)
		assert not errs, errs
	finally:
		pg.close()


def test_lupa_remembers_last_mode_per_device(base, browser):
	"""O último modo usado fica guardado (marcado nos botões; a tecla «/» abre-o) e sobrevive a recarregar a página."""
	url, gui, tw = base
	pg, errs = _open(browser, url)
	try:
		assert "lupa-ult" in pg.get_attribute("#lupa-b-peca", "class")           # por omissão «Peça»
		pg.click("#lupa-b-pos")
		pg.keyboard.press("Escape")
		assert "lupa-ult" in pg.get_attribute("#lupa-b-pos", "class")
		pg.reload()
		pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
		assert "lupa-ult" in pg.get_attribute("#lupa-b-pos", "class") and "lupa-ult" not in pg.get_attribute("#lupa-b-peca", "class")
		assert _boxes(pg) == (False, False)
		pg.locator("#board-wrap").hover()
		pg.keyboard.press("/")                                    # «/» abre o último modo
		assert _boxes(pg) == (False, True)
		pg.keyboard.press("Escape")
		pg.click("#lupa-b-peca")
		pg.keyboard.press("Escape")
		pg.reload()
		pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
		assert "lupa-ult" in pg.get_attribute("#lupa-b-peca", "class")
		assert not errs, errs
	finally:
		pg.close()


def test_lupa_parsers_accept_every_format(base, browser):
	"""Posição: «1,29», «1 29», «1.29», «1-29»; Peça: «9 89», «9/89», «9,89» e «P1422» (as funções puras da página)."""
	url, gui, tw = base
	pg, errs = _open(browser, url)
	try:
		for t in ("1,29", "1 29", "1.29", "1-29", " 1 , 29 ", "1/29", "01 029"):
			assert pg.evaluate("t => parsePosicao(t, 47, 64)", t) == {"l": 1, "c": 29}, t
		for t in ("9 89", "9/89", "9,89", "9.89", "9-89", "9  89"):
			assert pg.evaluate("t => parsePeca(t)", t) == {"lote": 9, "n": 89}, t
		for t, pid in (("P1422", "P1422"), ("p1422", "P1422"), ("P 1422", "P1422"), ("P89", "P0089"), ("p0089", "P0089")):
			assert pg.evaluate("t => parsePeca(t)", t) == {"pid": pid}, t
		for t in ("", "abc", "1", "1 2 3", "1,2,3", "-1 29", "1.5 29", "a b"):
			r = pg.evaluate("t => parsePosicao(t, 47, 64)", t)
			assert "erro" in r and "l" not in r, (t, r)
		for t in ("", "banana 1", "9", "9 89 1", "P", "P12345", "0 5", "5 0"):
			r = pg.evaluate("t => parsePeca(t)", t)
			assert "erro" in r and "lote" not in r and "pid" not in r, (t, r)
		assert not errs, errs
	finally:
		pg.close()


def test_lupa_finds_piece_by_bag_number_pid_and_position(base, browser):
	url, gui, tw = base
	p = gui.pr.piece(tw)
	pg, errs = _open(browser, url)
	try:
		for txt in (f"{p.lote} {p.n_no_lote}", f"{p.lote}/{p.n_no_lote}", f"{p.lote},{p.n_no_lote}", tw.lower(), tw):
			_buscar_peca(pg, txt)
			pg.wait_for_selector("#lupa-res[data-kind=peca]:not([hidden])", timeout=30_000)
			assert f"Saco {p.lote} · nº {p.n_no_lote}" in pg.locator("#lupa-res").inner_text(), txt
			assert _boxes(pg) == (False, False)                   # a caixa fecha ao achar
			pg.click("#lupa-fechar")
		_buscar_peca(pg, "P1")                                    # P1 = P0001 (a peça colocada)
		pg.wait_for_selector("#lupa-res[data-kind=peca]:not([hidden])", timeout=30_000)
		pg.click("#lupa-fechar")
		for txt in ("2 3", "2,3", "2.3", "2-3"):
			_buscar_lugar(pg, txt)
			pg.wait_for_selector("#lupa-res[data-kind=lugar]:not([hidden])", timeout=30_000)
			assert "Linha 2 · coluna 3" in pg.locator("#lupa-res").inner_text(), txt
			pg.click("#lupa-fechar")
		assert not errs, errs
	finally:
		pg.close()


def test_lupa_clear_messages_for_bad_values(base, browser):
	"""Valores fora da grelha ou inexistentes: mensagem clara na própria caixa (que fica aberta), nada de adivinhar."""
	url, gui, tw = base
	pg, errs = _open(browser, url)
	try:
		rows, cols = gui.pr.profile.rows, gui.pr.profile.cols
		lote = gui.pr.piece(tw).lote
		_buscar_lugar(pg, f"{rows + 1} 1")
		assert f"A linha {rows + 1} não existe: o puzzle tem as linhas 1 a {rows}." in _msg(pg, "pos")
		assert _boxes(pg) == (False, True)                        # fica aberta, com o texto selecionado para corrigir
		_buscar_lugar(pg, f"1 {cols + 5}")
		assert f"A coluna {cols + 5} não existe: o puzzle tem as colunas 1 a {cols}." in _msg(pg, "pos")
		_buscar_lugar(pg, "0 1")
		assert "A linha 0 não existe" in _msg(pg, "pos")
		_buscar_lugar(pg, "")
		assert "Escreve a linha e a coluna" in _msg(pg, "pos")
		_buscar_lugar(pg, "linha um")
		assert "não é uma posição" in _msg(pg, "pos")
		_buscar_peca(pg, f"{lote} 200")
		assert f"O saco {lote} não tem a peça nº 200: vai de 1 a " in _msg(pg, "peca")
		_buscar_peca(pg, "99 1")
		assert "Não há o saco 99." in _msg(pg, "peca") and f"{lote}" in _msg(pg, "peca")
		_buscar_peca(pg, f"{lote}")
		assert f"Falta o nº da peça no saco {lote}" in _msg(pg, "peca")
		_buscar_peca(pg, "banana 1")
		assert "não é uma peça" in _msg(pg, "peca")
		_buscar_peca(pg, "P9999")
		assert "Não encontrei a peça P9999." in _msg(pg, "peca")
		assert pg.locator("#lupa-res").is_hidden()               # nenhum erro abriu o resultado nem destacou nada
		assert pg.locator("#lyr-achado rect").count() == 0
		pg.fill("#lupa-q-peca", "9")                              # escrever limpa a mensagem
		assert pg.locator("#lupa-m-peca").is_hidden()
		assert not errs, errs
	finally:
		pg.close()


def test_lupa_box_slides_in_at_most_200ms_and_not_with_reduced_motion(base, browser):
	url, gui, tw = base
	pg, errs = _open(browser, url)
	try:
		pg.click("#lupa-b-peca")
		a = pg.evaluate("""(() => { const el = document.querySelector('#lupa-c-peca'); const an = el.getAnimations();
			return an.map((x) => ({ n: x.animationName, d: x.effect.getComputedTiming().duration })); })()""")
		assert a and a[0]["n"] == "lupa-abre" and 0 < a[0]["d"] <= 200, a
	finally:
		pg.close()
	ctx = browser.new_context(viewport={"width": 1366, "height": 768}, reduced_motion="reduce")
	pg = ctx.new_page()
	try:
		pg.goto(url + "/novo/")
		pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
		pg.click("#lupa-b-pos")
		assert pg.evaluate("document.querySelector('#lupa-c-pos').getAnimations().length") == 0
		assert pg.evaluate("getComputedStyle(document.querySelector('#lupa-c-pos')).animationName") == "none"
		assert _vis(pg, "#lupa-c-pos")
	finally:
		ctx.close()


def test_lupa_phone_layout(base, browser):
	url, gui, tw = base
	pg, errs = _open(browser, url, 390, 844)
	try:
		assert not pg.evaluate("document.documentElement.scrollWidth > window.innerWidth")
		for sel in ("#lupa-b-peca", "#lupa-b-pos", "#menu-btn"):
			bb = pg.locator(sel).bounding_box()
			assert bb and bb["height"] >= 44 - 0.5 and bb["x"] >= 0 and bb["x"] + bb["width"] <= 390, (sel, bb)
		for k in ("peca", "pos"):
			pg.click(f"#lupa-b-{k}")
			pg.wait_for_timeout(300)
			for sel in (f"#lupa-q-{k}", f"#lupa-c-{k} .lupa-go"):
				bb = pg.locator(sel).bounding_box()
				assert bb and bb["height"] >= 44 - 0.5 and bb["x"] >= 0 and bb["x"] + bb["width"] <= 390, (sel, bb)
			cx, b = pg.locator(f"#lupa-c-{k}").bounding_box(), pg.locator(f"#lupa-b-{k}").bounding_box()
			assert cx["y"] >= b["y"] + b["height"] - 0.5                         # por baixo dos botões, nunca por cima
			assert not pg.evaluate("document.documentElement.scrollWidth > window.innerWidth")
		assert not errs, errs
	finally:
		pg.close()


# ---------------------------------------------------------------- 1b. o resultado fica destacado no tabuleiro
def _achado(pg):
	return pg.evaluate("""(() => [...document.querySelectorAll('#lyr-achado rect.achado')].map((r) =>
		({ x: Number(r.getAttribute('x')), y: Number(r.getAttribute('y')), w: Number(r.getAttribute('width')) })))()""")


def test_lupa_result_is_highlighted_on_the_board_until_next_tap(base, browser):
	"""Achar um lugar ou uma peça desenha um contorno animado nesse lugar, até ao próximo toque no tabuleiro."""
	url, gui, tw = base
	pg, errs = _open(browser, url)
	try:
		assert _achado(pg) == []
		_buscar_lugar(pg, "2 3")
		pg.wait_for_selector("#lupa-res[data-kind=lugar]:not([hidden])", timeout=30_000)
		a = _achado(pg)
		assert len(a) == 1 and abs(a[0]["x"] - (3 - 1 + 0.02)) < 1e-3, a              # coluna 3 → x = 2
		an = pg.evaluate("[...document.querySelectorAll('#lyr-achado rect')].map((r) => getComputedStyle(r).animationName)")
		assert all(n != "none" for n in an) and len(an) == 2, an                        # contorno + onda, ambos animados
		# a peça achada: destaca o lugar dela
		p = gui.pr.piece(tw)
		_buscar_peca(pg, tw)
		pg.wait_for_selector("#lupa-res[data-kind=peca]:not([hidden])", timeout=30_000)
		cell = None
		for e in gui.fetch_entries():
			if e.get("piece") == tw and e.get("cell"):
				cell = e["cell"]
				break
		assert cell is not None
		a = _achado(pg)
		assert len(a) == 1 and abs(a[0]["x"] - (cell[1] - 1 + 0.02)) < 1e-3, (a, cell)
		# arrastar o tabuleiro NÃO tira o destaque; tocar nele tira
		bb = pg.locator("#board").bounding_box()
		pg.mouse.move(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2)
		pg.mouse.down(); pg.mouse.move(bb["x"] + bb["width"] / 2 + 40, bb["y"] + bb["height"] / 2 + 10, steps=4); pg.mouse.up()
		assert len(_achado(pg)) == 1
		pg.mouse.click(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2)
		pg.wait_for_function("document.querySelectorAll('#lyr-achado rect').length === 0", timeout=5_000)
		# fechar o resultado também o tira
		_buscar_lugar(pg, "1 1")
		pg.wait_for_selector("#lyr-achado rect.achado", timeout=30_000)
		pg.click("#lupa-fechar")
		assert _achado(pg) == []
		assert not errs, errs
	finally:
		pg.close()


def test_highlight_does_not_animate_with_reduced_motion(base, browser):
	url, gui, tw = base
	ctx = browser.new_context(viewport={"width": 1366, "height": 768}, reduced_motion="reduce")
	pg = ctx.new_page()
	try:
		pg.goto(url + "/novo/")
		pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
		_buscar_lugar(pg, "2 3")
		pg.wait_for_selector("#lyr-achado rect.achado", timeout=30_000)
		an = pg.evaluate("[...document.querySelectorAll('#lyr-achado rect')].map((r) => getComputedStyle(r).animationName)")
		assert an == ["none", "none"], an
	finally:
		ctx.close()


# ---------------------------------------------------------------- 1c. «Mostrar a borda em falta» sem borda em falta
def test_border_toggle_says_when_nothing_is_missing(base, browser):
	url, gui, tw = base
	pg, errs = _open(browser, url)
	try:
		falta = pg.evaluate("S.board.borda_em_falta.length")
		pg.click("#menu-btn")
		pg.check("#m-borda")
		if falta == 0:
			assert pg.locator("#m-borda-nota").inner_text() == "Não falta nenhuma peça de borda."
			assert "Não falta nenhuma peça de borda." in pg.locator("#toast").inner_text()
			assert pg.locator("#lyr-borda rect").count() == 0
		else:
			assert pg.locator("#lyr-borda rect").count() == falta
			assert "Falt" in pg.locator("#m-borda-nota").inner_text()
		# sem a borda completa: simula com uma célula de borda marcada como em falta
		pg.evaluate("S.board.borda_em_falta = [[1, 29]]; drawLayers()")
		assert pg.locator("#lyr-borda rect").count() == 1
		assert pg.locator("#m-borda-nota").inner_text() == "Falta 1 peça de borda."
		pg.evaluate("S.board.borda_em_falta = []; drawLayers()")
		assert pg.locator("#m-borda-nota").inner_text() == "Não falta nenhuma peça de borda."
		pg.uncheck("#m-borda")
		assert pg.locator("#m-borda-nota").is_hidden()
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
			assert "A preparar sugestões…" in pg.locator("#tab-montar .card .trabalho").inner_text()      # F2c: a 1.ª vez «preparar»
			assert pg.locator("#b-encaixa").is_enabled() and pg.locator("#b-nao").is_enabled()     # nada bloqueado
			pg.click("#z-in")                                                                      # o tabuleiro responde
			_no_forbidden(_montar_text(pg))
			gate.set()
			pg.wait_for_function("!document.querySelector('.trabalho')", timeout=60_000)
			# depois de as ter visto, o recálculo seguinte (depois de uma escrita) já diz «atualizar»
			txt = pg.evaluate("(() => { S.montar.a_preparar = { buracos: true }; return trabalho().txt; })()")
			assert txt == "A atualizar sugestões…", txt
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
