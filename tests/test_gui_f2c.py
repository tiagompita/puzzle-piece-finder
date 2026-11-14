"""F2c em Chromium headless (slow): o ecrã de arranque das duas GUIs («A refazer imagens: folha n de N») e a faixa
«Ligação perdida» (só quando a ligação cai mesmo, nunca com o servidor vivo mas ocupado).

Causa do aviso vermelho visto no arranque da GUI antiga [V no que se mediu]: o servidor, ocupado ou a arrancar, mantém o
``/api/events`` vivo (``test_busy_server_keeps_the_events_stream`` e o teste de arranque abaixo: a faixa nunca aparece com
o servidor vivo). Duas coisas podiam, sim, mostrar um aviso vermelho: (a) a faixa legítima, se a página estava aberta
enquanto o servidor era reiniciado; (b) um ``core.js`` antigo na cache do browser ao lado de um ``app.js`` novo
(«watchConnection is not defined»): os ficheiros da página não tinham ``Cache-Control``; agora levam ``no-cache``
(``test_page_files_are_revalidated``).
"""

import socket
import threading
import time
import urllib.request

import pytest

pytestmark = pytest.mark.slow
pytest.importorskip("fastapi")
pytest.importorskip("uvicorn")
sync_api = pytest.importorskip("playwright.sync_api")

from src import render  # noqa: E402
from src import server as SV  # noqa: E402
from test_gui_novo import browser  # noqa: E402,F401
from test_gui_novo_f2b import _serve_on  # noqa: E402
from test_query import _project  # noqa: E402

N_FOLHAS = 4


def _port():
	s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close()
	return p


def _ligacao_visivel(pg) -> bool:
	return bool(pg.evaluate("(() => { const e = document.querySelector('#ligacao'); return !!e && getComputedStyle(e).display !== 'none'; })()"))


@pytest.fixture
def arranque(tmp_path, monkeypatch):
	"""Um servidor que arranca devagar: ``stale_assets`` diz que há 4 folhas por refazer e ``rebuild_stale`` só avança
	quando o teste solta cada passo (o servidor está VIVO e ocupado). Devolve ``(url, gui, passos)``."""
	pr, placed, tw, dec = _project(tmp_path)
	from src.query import run_query
	run_query(pr, use_image=False)
	passos = [threading.Event() for _ in range(N_FOLHAS + 1)]
	real_stale = render.stale_assets
	feito = {"v": False}

	def stale(project, *a, **kw):
		if feito["v"]:
			return real_stale(project, *a, **kw)
		return {"n_pecas": 8, "n_folhas": N_FOLHAS, "sheets": {f"S{i:04d}" for i in range(1, N_FOLHAS + 1)}, "pecas": {}}

	def rebuild(project, *, progress=print, **kw):
		for i in range(1, N_FOLHAS + 1):
			passos[i - 1].wait(60)
			progress(f"S{i:04d} (folha{i}.jpg): 2 peças, 0 contornos novos, 0 silhuetas mudadas (-) em 0.1 s")
		passos[N_FOLHAS].wait(60)
		feito["v"] = True
		return {"depois": {"n_pecas": 0}, "eventos": 0, "aviso": None, "errors": [], "changed": []}

	monkeypatch.setattr(SV, "missing_assets", lambda project: [])      # o projeto sintético não tem as pastas de ativos
	monkeypatch.setattr(render, "stale_assets", stale)
	monkeypatch.setattr(render, "rebuild_stale", rebuild)
	gui = SV.Gui(pr.path, prepare=True, use_image=False, uploads=str(tmp_path / "uploads"), log=None, queue=False)
	port = _port()
	url = f"http://127.0.0.1:{port}"
	server, th = _serve_on(gui, port)
	yield url, gui, passos
	for e in passos:
		e.set()
	gui.begin_shutdown()
	server.should_exit = True
	th.join(15)


def test_status_says_what_the_start_up_is_doing(arranque):
	url, gui, passos = arranque
	import json
	t0 = time.time()
	st = {}
	while time.time() - t0 < 20:
		st = json.loads(urllib.request.urlopen(url + "/api/status", timeout=5).read())
		if (st.get("preparacao") or {}).get("fase") == "imagens":
			break
		time.sleep(0.1)
	assert st["estado"] == "a_preparar"          # desde o 1.º instante (antes era «pronto» até a thread começar)
	assert st["preparacao"] == {"fase": "imagens", "texto": "A refazer imagens: folha", "n": 0, "N": N_FOLHAS}, st["preparacao"]
	passos[0].set()
	t0 = time.time()
	while time.time() - t0 < 20 and (json.loads(urllib.request.urlopen(url + "/api/status", timeout=5).read()).get("preparacao") or {}).get("n") != 1:
		time.sleep(0.1)
	assert json.loads(urllib.request.urlopen(url + "/api/status", timeout=5).read())["preparacao"]["n"] == 1
	for e in passos:
		e.set()
	t0 = time.time()
	while time.time() - t0 < 60 and gui.state != "pronto":
		time.sleep(0.1)
	st = json.loads(urllib.request.urlopen(url + "/api/status", timeout=5).read())
	assert st["estado"] == "pronto" and st["preparacao"] is None


@pytest.mark.parametrize("pagina", ["/novo/", "/"])
def test_both_guis_show_progress_while_starting_and_no_red_banner(arranque, browser, pagina):
	"""Com o servidor vivo mas a trabalhar, as duas GUIs mostram o que ele faz e o n de N (e nunca a faixa vermelha)."""
	url, gui, passos = arranque
	pg = browser.new_page(viewport={"width": 1366, "height": 768})
	errs = []
	pg.on("pageerror", lambda e: errs.append(str(e)))
	try:
		pg.goto(url + pagina)
		sel = "#prep-texto" if pagina == "/novo/" else "#prep-now"
		pg.wait_for_function(f"(document.querySelector('{sel}') || {{}}).textContent === 'A refazer imagens: folha 0 de {N_FOLHAS}'", timeout=30_000)
		for n in range(1, N_FOLHAS + 1):
			passos[n - 1].set()
			pg.wait_for_function(f"document.querySelector('{sel}').textContent === 'A refazer imagens: folha {n} de {N_FOLHAS}'", timeout=30_000)
			bar = pg.locator("#prep-barra" if pagina == "/" else "#tab-montar .prep-barra")
			assert bar.get_attribute("aria-valuenow") == str(n) and bar.get_attribute("aria-valuemax") == str(N_FOLHAS)
			assert not _ligacao_visivel(pg)
		if pagina == "/novo/":
			assert "A preparar o puzzle…" in pg.locator("#tab-montar").inner_text()
		else:
			assert pg.locator("#prep").is_visible()
		pg.wait_for_timeout(1500)                       # o servidor continua ocupado e vivo: nada de faixa
		assert not _ligacao_visivel(pg)
		passos[N_FOLHAS].set()
		pg.wait_for_selector("body[data-ready='1']", timeout=90_000)
		assert not _ligacao_visivel(pg)
		assert not errs, errs
	finally:
		pg.close()


@pytest.mark.parametrize("pagina", ["/novo/", "/"])
def test_busy_server_keeps_the_events_stream(tmp_path, browser, pagina):
	"""O servidor vivo mas ocupado (um pedido lento, o bloqueio de escrita tomado, sem eventos durante vários
	segundos, com o keep-alive do SSE a 1 s) NÃO faz aparecer «Ligação perdida»; com o servidor morto, aparece."""
	pr, placed, tw, dec = _project(tmp_path)
	from src.query import run_query
	run_query(pr, use_image=False)
	gui = SV.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp_path / "uploads"), log=None, queue=False)
	port = _port()
	url = f"http://127.0.0.1:{port}"
	old = SV.SSE_KEEPALIVE_S
	SV.SSE_KEEPALIVE_S = 1.0
	server, th = _serve_on(gui, port)
	pg = browser.new_page(viewport={"width": 1366, "height": 768})
	try:
		pg.goto(url + pagina)
		pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
		t0 = time.time()
		while not gui._sse_waiters and time.time() - t0 < 15:
			time.sleep(0.1)
		assert gui._sse_waiters
		# ocupado: o bloqueio de escrita tomado 5 s e uma composição lenta do tabuleiro em curso
		def ocupa():
			with gui.wlock:
				time.sleep(5)
		threading.Thread(target=ocupa, daemon=True).start()
		fetches = []
		for _ in range(4):
			fetches.append(pg.evaluate("fetch('/api/status').then(r => r.status)"))
		t0 = time.time()
		while time.time() - t0 < 6:
			pg.wait_for_timeout(300)
			assert not _ligacao_visivel(pg), "a faixa apareceu com o servidor vivo"
		assert pg.evaluate("document.body.dataset.ready") == "1"
		# morto: aparece
		gui.begin_shutdown()
		server.should_exit = True
		th.join(15)
		assert not th.is_alive()
		pg.wait_for_function("(() => { const e = document.querySelector('#ligacao'); return !!e && getComputedStyle(e).display !== 'none'; })()", timeout=20_000)
		assert pg.locator("#ligacao").inner_text() == "Ligação perdida, a tentar religar…"
	finally:
		SV.SSE_KEEPALIVE_S = old
		pg.close()
		gui.begin_shutdown()
		server.should_exit = True
		th.join(15)


def test_page_files_are_revalidated(tmp_path):
	"""Os ficheiros da página (js/css/html) levam ``Cache-Control: no-cache``: nunca um core.js velho ao lado de um app.js novo."""
	pr, placed, tw, dec = _project(tmp_path)
	gui = SV.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp_path / "uploads"), log=None, queue=False)
	port = _port()
	server, th = _serve_on(gui, port)
	try:
		for path in ("/core.js", "/app.js", "/novo/novo.js", "/novo/novo.css", "/novo/", "/board.css"):
			r = urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10)
			assert r.headers.get("Cache-Control") == "no-cache", (path, r.headers.get("Cache-Control"))
		r = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=10)
		assert r.headers.get("Cache-Control") != "no-cache"
	finally:
		gui.begin_shutdown()
		server.should_exit = True
		th.join(15)


@pytest.mark.parametrize("pagina", ["/novo/", "/"])
def test_stale_core_js_does_not_throw_watchconnection_error(tmp_path, browser, pagina):
	"""Reproduz o aviso vermelho «watchConnection is not defined»: um core.js de antes da F2b (sem a função) ao lado do
	app.js novo. A página já não rebenta (a faixa é opcional) e abre sem erro."""
	pr, placed, tw, dec = _project(tmp_path)
	gui = SV.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp_path / "uploads"), log=None, queue=False)
	port = _port()
	server, th = _serve_on(gui, port)
	pg = browser.new_page(viewport={"width": 1366, "height": 768})
	errs = []
	pg.on("pageerror", lambda e: errs.append(str(e)))
	try:
		core = urllib.request.urlopen(f"http://127.0.0.1:{port}/core.js", timeout=10).read().decode("utf8")
		i, j = core.index("/** Faixa"), core.index("async function api")
		pg.route("**/core.js", lambda r: r.fulfill(body=core[:i] + core[j:], content_type="application/javascript"))
		pg.goto(f"http://127.0.0.1:{port}{pagina}")
		pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
		assert pg.locator("#toast .err").count() == 0 and not errs, errs
	finally:
		pg.close()
		gui.begin_shutdown()
		server.should_exit = True
		th.join(15)
