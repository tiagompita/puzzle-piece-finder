"""Playwright (``slow``): o painel «Atividade» (activity.js, docs/gui-design.md §23): fechado não ocupa espaço nem muda o
layout (1366×768 a 150 % = 911×512 e telemóvel), abre pelo botão da barra, mostra as linhas do servidor em tempo real
(SSE ``atividade``) com carimbo de tempo, e os filtros por tipo e nível escondem linhas. Só leitura."""

import os
import socket
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
pytestmark = pytest.mark.slow
pytest.importorskip("httpx")
sync_api = pytest.importorskip("playwright.sync_api")

from src import activity as A  # noqa: E402
from src import server as S  # noqa: E402
from test_consistency import _row_project  # noqa: E402

VIEWPORTS = [(1366, 768), (911, 512), (390, 844)]


@pytest.fixture(scope="module")
def env(tmp_path_factory):
	import uvicorn
	tmp = tmp_path_factory.mktemp("act")
	pr, ids = _row_project(tmp)
	ring = A.RingHandler()
	gui = S.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp / "uploads"), ring=ring)
	gui.activity_setup(console=False, file=True)
	A.get("arranque").info("tabuleiro pronto (0,2 s)")
	A.get("cache").info("buracos: cache usada (versão 1)")
	s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
	server = uvicorn.Server(uvicorn.Config(S.create_app(gui), host="127.0.0.1", port=port, log_level="warning"))
	th = threading.Thread(target=server.run, daemon=True)
	th.start()
	t0 = time.time()
	while not server.started and time.time() - t0 < 30:
		time.sleep(0.05)
	yield f"http://127.0.0.1:{port}", gui, pr, ids
	server.should_exit = True
	th.join(10)
	A.teardown()


@pytest.fixture(scope="module")
def browser():
	with sync_api.sync_playwright() as pw:
		try:
			br = pw.chromium.launch()
		except Exception as e:  # chromium not installed
			pytest.skip(f"chromium indisponível: {e}")
		yield br
		br.close()


@pytest.mark.parametrize("w,h", VIEWPORTS)
def test_activity_drawer_closed_takes_no_space_and_opens(env, browser, w, h):
	base, gui, pr, ids = env
	phone = w <= 430
	ctx = browser.new_context(viewport={"width": w, "height": h}, has_touch=phone, is_mobile=phone, device_scale_factor=1.5 if (w, h) == (911, 512) else 1.0)
	pg = ctx.new_page()
	errs = []
	pg.on("pageerror", lambda e: errs.append(str(e)))
	pg.goto(base + "/")
	pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
	pg.wait_for_timeout(200)
	assert pg.evaluate("document.querySelector('#atividade').hidden") is True
	assert pg.evaluate("getComputedStyle(document.querySelector('#atividade')).display") == "none"
	layout_before = pg.evaluate("[...document.querySelectorAll('#top, #board-wrap, #panel, #legend-wrap')].map((e) => { const r = e.getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; })")
	# wide bars: the «Atividade» toggle in the top bar; <= 1300 px: the «≣» button of the zoom controls (absolute, no layout space)
	vis = [b for b in pg.query_selector_all("[data-act-toggle]") if b.is_visible()]
	assert len(vis) == 1 and vis[0].get_attribute("id") == ("tg-act" if w > 1300 else "z-act")
	assert vis[0].bounding_box()["height"] >= (40 if phone else 28)
	assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
	vis[0].click()
	pg.wait_for_selector("#atividade:not([hidden]) .act-line", timeout=10_000)
	lines = pg.evaluate("[...document.querySelectorAll('#act-lines .act-line')].map((l) => [l.dataset.tipo, l.dataset.nivel, l.querySelector('.act-t').textContent, l.querySelector('.act-m').textContent])")
	assert any(t == "arranque" and m.startswith("tabuleiro pronto") for t, n, ts, m in lines)
	assert all(len(ts) == 8 and ts[2] == ":" for _, _, ts, _ in lines)                      # HH:MM:SS
	# the drawer is fixed: the app layout underneath did not move
	assert pg.evaluate("[...document.querySelectorAll('#top, #board-wrap, #panel, #legend-wrap')].map((e) => { const r = e.getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; })") == layout_before
	assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
	# live: a new line arrives by SSE
	n0 = pg.evaluate("document.querySelectorAll('#act-lines .act-line').length")
	A.get("buracos").warning("aviso de teste em direto")
	pg.wait_for_function(f"document.querySelectorAll('#act-lines .act-line').length > {n0}", timeout=10_000)
	last = pg.evaluate("(() => { const l = [...document.querySelectorAll('#act-lines .act-line')].pop(); return [l.dataset.tipo, l.dataset.nivel, l.querySelector('.act-m').textContent]; })()")
	assert last == ["buracos", "aviso", "aviso de teste em direto"]
	# filter by level: hide info -> only the warning stays; by type: hide 'buracos' too -> nothing
	pg.click("#act-filters .act-nv.info")
	pg.wait_for_timeout(100)
	assert pg.evaluate("[...document.querySelectorAll('#act-lines .act-line')].every((l) => l.dataset.nivel !== 'info')")
	assert pg.evaluate("document.querySelectorAll('#act-lines .act-line').length") >= 1
	pg.click("#act-filters .act-f[data-tipo='buracos']")
	pg.wait_for_timeout(100)
	assert pg.evaluate("document.querySelectorAll('#act-lines .act-line').length") == 0
	pg.click("#act-filters .act-f[data-tipo='buracos']")
	pg.click("#act-filters .act-nv.info")
	pg.wait_for_timeout(100)
	assert pg.evaluate("document.querySelectorAll('#act-lines .act-line').length") >= n0
	# close: hidden again, state remembered
	pg.click("#act-close")
	assert pg.evaluate("document.querySelector('#atividade').hidden") is True
	assert pg.evaluate("localStorage.getItem('atividade-open')") == "0"
	assert errs == [], errs
	ctx.close()
