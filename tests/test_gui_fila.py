"""Playwright (``slow``): the bottom drawer has two tabs, «Atividade» and «Fila de importação» (queue.js,
docs/gui-design.md §24), without horizontal overflow at 1366×768, 911×512 @1.5 and 390×844; a job put in the queue
by the «Importar» form shows up in the list and changes state live (SSE ``queue_changed``)."""

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

from src import server as S  # noqa: E402
from test_consistency import _row_project  # noqa: E402
from test_ingest_multi import _scan  # noqa: E402

VIEWPORTS = [(1366, 768), (911, 512), (390, 844)]


@pytest.fixture(scope="module")
def env(tmp_path_factory):
	import uvicorn
	from src.segmentation import segment_scan
	tmp = tmp_path_factory.mktemp("fila")
	pr, ids = _row_project(tmp)
	gui = S.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp / "uploads"), log=None, queue=True)

	def slow(photo, **k):
		time.sleep(1.5)
		return segment_scan(photo, **k)
	gui.ingest_segment = slow
	s = socket.socket()
	s.bind(("127.0.0.1", 0))
	port = s.getsockname()[1]
	s.close()
	server = uvicorn.Server(uvicorn.Config(S.create_app(gui), host="127.0.0.1", port=port, log_level="warning"))
	th = threading.Thread(target=server.run, daemon=True)
	th.start()
	t0 = time.time()
	while not server.started and time.time() - t0 < 30:
		time.sleep(0.05)
	yield f"http://127.0.0.1:{port}", gui, tmp
	server.should_exit = True
	th.join(10)
	gui.stop()


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
def test_queue_tab_and_live_job(env, browser, w, h):
	base, gui, tmp = env
	phone = w <= 430
	ctx = browser.new_context(viewport={"width": w, "height": h}, has_touch=phone, is_mobile=phone,
							  device_scale_factor=1.5 if (w, h) == (911, 512) else 1.0)
	pg = ctx.new_page()
	errs = []
	pg.on("pageerror", lambda e: errs.append(str(e)))
	pg.goto(base + "/")
	pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
	# the drawer: same toggle as before, two tabs, «Atividade» first
	vis = [b for b in pg.query_selector_all("[data-act-toggle]") if b.is_visible()]
	assert len(vis) == 1
	vis[0].click()
	pg.wait_for_selector("#atividade:not([hidden])")
	assert pg.evaluate("document.querySelector('#atividade').dataset.pane") == "atividade"
	assert pg.is_visible("#act-lines") and not pg.is_visible("#fila-pane")
	pg.click("#act-tab-fila")
	assert pg.evaluate("document.querySelector('#atividade').dataset.pane") == "fila"
	assert pg.is_visible("#fila-pane") and not pg.is_visible("#act-lines") and not pg.is_visible("#act-filters")
	assert pg.evaluate("localStorage.getItem('gaveta-separador')") == "fila"
	assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
	for t in ("#act-tab-atividade", "#act-tab-fila", "#act-close"):
		assert pg.is_visible(t), t
	box = pg.query_selector("#atividade").bounding_box()
	assert box["x"] >= 0 and box["x"] + box["width"] <= w + 0.5
	# a job through the «Importar» form
	n_before = len(gui.queue_json()["fila"])
	png = _scan(tmp / f"v{w}.png", 2, seed=w)
	lote = 20 + VIEWPORTS.index((w, h))
	pg.evaluate("showTab('importar')")
	pg.wait_for_selector("#import-form")
	pg.set_input_files("#import-form input[type=file]", png)
	pg.fill("#import-form input[name=lote]", str(lote))
	pg.eval_on_selector("#import-form", "f => f.requestSubmit()")
	jid = f"Q{n_before + 1:04d}"
	pg.wait_for_selector(f"#fila-jobs li[data-job='{jid}']", timeout=15_000)
	seen = pg.evaluate(f"document.querySelector(\"#fila-jobs li[data-job='{jid}']\").dataset.estado")
	assert seen in ("em_fila", "a_correr")
	pg.wait_for_selector(f"#fila-jobs li[data-job='{jid}'][data-estado='concluido']", timeout=120_000)
	txt = pg.text_content(f"#fila-jobs li[data-job='{jid}']")
	assert f"saco {lote}" in txt and "folhas 1/1" in txt and "2 peças" in txt
	assert any(r["estado"] == "concluido" and r["id"] == jid for r in gui.queue_json()["fila"])
	assert "trabalho" in (pg.text_content("#joblog") or "") and jid in (pg.text_content("#joblog") or "")
	assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
	# the drawer remembers the tab after a reload
	pg.reload()
	pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
	assert pg.evaluate("document.querySelector('#atividade').dataset.pane") == "fila"
	assert errs == [], errs
	ctx.close()
