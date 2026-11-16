"""P-a (2026-11-16, DETALHE.md §13.10), no browser: depois de uma escrita, a recarga (``/api/board``, ``/api/ghosts``,
``/api/montar``) cede ao detalhe da versão nova no servidor, com a espera limitada a ``DETALHE_ESPERA_S``. Um detalhe
que falha não a prende; um que nunca acaba (ou que o browser cancela: a composição continua no servidor) prende-a no
máximo o limite; o cartão seguinte do Montar aparece; a GUI antiga também. Playwright, ``slow``."""
import time

import pytest

pytestmark = pytest.mark.slow
sync_api = pytest.importorskip("playwright.sync_api")

from src import server as SV  # noqa: E402
from test_gui_detalhe_escrita import TRACE, _post  # noqa: E402
from test_gui_novo import DETAIL_TIMES, base, browser  # noqa: E402,F401 - fixtures
from test_gui_novo_p0 import _away, _open, _settle_on  # noqa: E402

EPS = 1.0          # s: the browser, the SSE and the reload itself on a loaded machine
HANG = 4.0         # s: a detail that does not end before the limit


def _regions(gui, monkeypatch):
	"""``st["mode"]``: None (normal), ``"hang"`` (each region composition takes ``HANG`` s), ``"fail"`` (raises)."""
	real = gui._compose
	st = {"mode": None}

	def comp(ppc, region=None):
		if region is not None and st["mode"] == "hang":
			time.sleep(HANG)
		if region is not None and st["mode"] == "fail":
			time.sleep(0.2)
			raise RuntimeError("composição partida (teste)")
		return real(ppc, region)
	monkeypatch.setattr(gui, "_compose", comp)
	return st


def _trace(pg):
	pg.evaluate(TRACE.replace("(() => {", "(() => { if (window.__tr) return;", 1))
	# one more EventSource only (the browser has 6 connections per host: the page's own, this one and the requests)
	pg.evaluate("(() => { const es = new EventSource('/api/events'); es.addEventListener('board_changed', (e) => { window.__tr.push({ ev: 'sse2', t: performance.now(), v: JSON.parse(e.data).versao }); if (window.__cancel) setTimeout(() => abortDetail(), 50); }); })()")


def _after_write(pg, v, path, timeout=20.0):
	"""Seconds from the ``board_changed`` of version ``v`` to the end of the first ``path`` request after it."""
	t0 = time.time()
	while time.time() - t0 < timeout:
		tr = pg.evaluate("window.__tr")
		sse = [e for e in tr if e["ev"] == "sse2" and e["v"] == v]
		if sse:
			ts = sse[0]["t"]
			done = [e for e in tr if e["ev"] == "fetch" and e["url"].split("?")[0] == path and e["t0"] >= ts - 50 and e["t1"]]
			if done:
				return (done[0]["t1"] - ts) / 1000.0
		pg.wait_for_timeout(50)
	raise AssertionError(f"{path} não acabou em {timeout} s")


@pytest.mark.parametrize("mode", ["hang", "fail", "cancel"])
def test_novo_reload_waits_for_the_detail_at_most_the_limit(base, browser, monkeypatch, mode):
	url, gui, tw = base
	st = _regions(gui, monkeypatch)
	pg, errs, _ = _open(browser, url)
	try:
		_trace(pg)
		_settle_on(pg, _away(pg))                         # zoomed in: a detail is on screen
		pg.evaluate("window.__tr.length = 0")
		st["mode"] = "hang" if mode == "cancel" else mode
		if mode == "cancel":                              # the tab drops the detail 50 ms after asking for it
			pg.evaluate("window.__cancel = true")
		n0 = gui.det_waits["n"]
		_post(url, {"acao": "place", "piece": tw, "cell": [3, 4]})
		v = gui.version()
		b = _after_write(pg, v, "/api/board")
		m = _after_write(pg, v, "/api/montar")
		g = _after_write(pg, v, "/api/ghosts")
		lim = SV.DETALHE_ESPERA_S
		if mode == "fail":
			assert max(b, m, g) < 0.2 + EPS, (b, m, g)          # went on when the detail failed, not at the limit
		else:
			# cancelled in the tab: the server goes on composing it (or never saw it), so at most the limit
			assert max(b, m, g) < lim + EPS, (b, m, g)
		if mode == "hang":
			# they did wait for the detail being composed (the server counts it; a request that reached the server
			# before the detail's own request did not wait, which only costs time)
			assert gui.det_waits["n"] > n0 and gui.det_waits["s"] >= 0.5 * lim, gui.det_waits
		st["mode"] = None
		pg.wait_for_function("S.detailKey === null || document.body.dataset.detail !== undefined", timeout=30_000)
		assert not errs, errs
	finally:
		st["mode"] = None
		pg.close()


def test_novo_next_card_appears_while_the_detail_never_ends(base, browser, monkeypatch):
	url, gui, tw = base
	st = _regions(gui, monkeypatch)
	pg, errs, _ = _open(browser, url)
	try:
		_settle_on(pg, _away(pg))
		p0 = pg.get_attribute("#tab-montar .card[data-piece]", "data-piece")
		assert pg.locator("#b-encaixa").count() == 1
		st["mode"] = "hang"
		t0 = time.time()
		pg.click("#b-encaixa")
		pg.wait_for_function(f"(() => {{ const c = document.querySelector('#tab-montar .card[data-piece]'); return !S.pendente && (!c || c.dataset.piece !== '{p0}'); }})()",
							 timeout=30_000)
		dt = time.time() - t0
		assert dt < SV.DETALHE_ESPERA_S + 2 * EPS + 1.0, dt     # the POST + the reload held at most the limit
		assert not errs, errs
	finally:
		st["mode"] = None
		pg.close()


def test_old_gui_reload_is_not_held_beyond_the_limit(base, browser, monkeypatch):
	url, gui, tw = base
	st = _regions(gui, monkeypatch)
	pg = browser.new_page(viewport={"width": 1366, "height": 768})
	pg.add_init_script(DETAIL_TIMES)
	errs = []
	pg.on("pageerror", lambda e: errs.append(str(e)))
	try:
		pg.goto(url + "/")
		pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
		_trace(pg)
		hr = pg.evaluate("S.hr")
		_settle_on(pg, {"x": 0.5, "y": 0.5 * hr, "w": 2})
		pg.evaluate("window.__tr.length = 0")
		st["mode"] = "hang"
		pg.evaluate("S.detailKey = null; loadDetail()")    # a detail of the old GUI being composed during the write
		_post(url, {"acao": "place", "piece": tw, "cell": [3, 4]})
		v = gui.version()
		b = _after_write(pg, v, "/api/board")
		assert b < 0.35 + SV.DETALHE_ESPERA_S + EPS, b      # the 350 ms of scheduleReload + at most the limit
		assert not errs, errs
	finally:
		st["mode"] = None
		pg.close()
