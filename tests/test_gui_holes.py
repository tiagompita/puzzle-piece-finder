"""Playwright (``slow``): the «Candidatas para este buraco» block of the cell drawer, the «Buracos» tab and the
confirm flow of the hole ranking (M11, ``src/web/holes.js``), at 1366×768, at 1366×768 scaled 150 % (911×512) and
on a phone viewport, without overflow. Synthetic project of :func:`test_consistency._row_project` with A unplaced:
(2,3) is a hole with two mounted neighbours and A is the only loose piece.
"""

import json
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

SHOTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "gui", "screenshots")
VIEWPORTS = [(1366, 768), (911, 512), (390, 844)]


@pytest.fixture(scope="module")
def env(tmp_path_factory):
	import uvicorn
	tmp = tmp_path_factory.mktemp("holes")
	pr, ids = _row_project(tmp)
	pr.unplace(ids["A"])
	pr.save()
	gui = S.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp / "uploads"), log=None)
	gui.holes_json(wait=True)
	s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
	server = uvicorn.Server(uvicorn.Config(S.create_app(gui), host="127.0.0.1", port=port, log_level="warning"))
	th = threading.Thread(target=server.run, daemon=True)
	th.start()
	t0 = time.time()
	while not server.started and time.time() - t0 < 30:
		time.sleep(0.05)
	yield f"http://127.0.0.1:{port}", pr, ids
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


def _events(pr, nome):
	with open(pr.log_path, encoding="utf-8") as f:
		return [json.loads(x) for x in f if x.strip() and json.loads(x).get("action") == nome]


def _no_overflow(pg):
	assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
	assert pg.evaluate("(() => { const t = document.querySelector('.tab.on'); return !t || t.scrollWidth <= t.clientWidth + 1; })()")


def _open_hole(pg, base):
	pg.goto(base + "/")
	pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
	pg.evaluate("openCell(2, 3, {zoom: true})")
	pg.wait_for_selector(".holes-block .hole-card", timeout=20_000)


@pytest.mark.parametrize("w,h", VIEWPORTS)
def test_hole_block_layout(env, browser, w, h):
	base, pr, ids = env
	phone = w <= 430
	ctx = browser.new_context(viewport={"width": w, "height": h}, has_touch=phone, is_mobile=phone, device_scale_factor=1.5 if (w, h) == (911, 512) else 1.0)
	pg = ctx.new_page()
	errs = []
	pg.on("pageerror", lambda e: errs.append(str(e)))
	_open_hole(pg, base)
	block = pg.query_selector(".holes-block")
	assert block is not None
	assert pg.inner_text(".holes-block h2").strip().lower().startswith("candidatas para este buraco")
	cards = pg.query_selector_all(".holes-block .hole-card")
	assert 1 <= len(cards) <= 3
	assert pg.query_selector(".holes-block .hole-card .hole-mini") is not None          # the candidate drawn in the hole
	chip = pg.query_selector(".holes-block .hole-lead .chip")
	assert chip is not None and chip.get_attribute("data-conf") in ("alta", "media", "sem")
	# the three buttons of a card exist and have touch-friendly heights on the phone
	for act in ("confirmar", "rejeitar", "ver", "prever"):   # ronda 8: «ver» só localiza; «prever» desenha o encaixe
		b = pg.query_selector(f".holes-block .hole-card [data-hole-act='{act}']")
		assert b is not None
		assert b.bounding_box()["height"] >= (40 if phone else 28)
	_no_overflow(pg)
	# the card stays inside the panel
	pb = pg.query_selector("#panel").bounding_box()
	cb = cards[0].bounding_box()
	assert cb["x"] >= pb["x"] - 1 and cb["x"] + cb["width"] <= pb["x"] + pb["width"] + 1
	# «Ver no tabuleiro» only locates the cell (as on every other card); «Pré-visualizar encaixe» draws the candidate
	# and the neighbours on the board layer (ronda 8, 1.2)
	pg.click(".holes-block .hole-card [data-hole-act='ver']")
	assert pg.evaluate("Array.isArray(S.sel) && S.sel[0] === 2 && S.sel[1] === 3")
	assert pg.evaluate("document.querySelectorAll('#hole-layer #hole-piece').length") == 0
	pg.click(".holes-block .hole-card [data-hole-act='prever']")
	pg.wait_for_selector("#hole-layer #hole-piece", timeout=5_000)
	assert pg.evaluate("document.querySelectorAll('#hole-layer .hole-neigh').length") >= 2
	# the «Buracos» tab lists the hole with its confidence and opens the cell
	pg.evaluate("showTab('buracos')")
	pg.wait_for_selector("#tab-buracos .hole-row", timeout=20_000)
	assert pg.evaluate("document.querySelectorAll('#hole-layer *').length") == 0          # leaving the drawer clears the layer
	_no_overflow(pg)
	rows = pg.query_selector_all("#tab-buracos .hole-row")
	assert any(r.get_attribute("data-cell") == "2,3" for r in rows)
	if os.environ.get("PPF_SHOTS") and (w, h) == (1366, 768):
		os.makedirs(SHOTS, exist_ok=True)
		pg.screenshot(path=os.path.join(SHOTS, "buracos_lista.png"))
		pg.evaluate("openCell(2, 3, {zoom: true})")
		pg.wait_for_selector(".holes-block .hole-card", timeout=20_000)
		pg.screenshot(path=os.path.join(SHOTS, "buracos_gaveta.png"))
	assert errs == [], errs
	ctx.close()


def test_search_term_buracos_and_reject_confirm_flow(env, browser):
	base, pr, ids = env
	a = ids["A"]
	pg = browser.new_page(viewport={"width": 1366, "height": 768})
	errs = []
	pg.on("pageerror", lambda e: errs.append(str(e)))
	pg.goto(base + "/")
	pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
	pg.evaluate("locateQuery('buracos')")
	pg.wait_for_selector("#tab-buracos.on", timeout=5_000)
	pg.evaluate("openCell(2, 3, {zoom: true})")
	pg.wait_for_selector(".holes-block .hole-card", timeout=20_000)
	n0 = len(_events(pr, "hole_rejected"))
	pg.once("dialog", lambda d: d.accept())
	pg.click(f".holes-block .hole-card[data-hole-piece='{a}'] [data-hole-act='rejeitar']")
	t0 = time.time()
	while len(_events(pr, "hole_rejected")) == n0 and time.time() - t0 < 30:
		time.sleep(0.2)
	ev = _events(pr, "hole_rejected")[-1]
	assert ev["piece"] == a and ev["cell"] == [2, 3] and ev["rank"] == 1 and ev["m"] == 2 and ev["fit_version"]
	# after the rejection the piece is out of the ranking of that cell
	pg.wait_for_function("document.querySelector('.holes-block') && !document.querySelector(`.holes-block .hole-card[data-hole-piece='%s']`)" % a, timeout=30_000)
	# confirm through the API path of the GUI (the card is gone for this cell): another hole of A, e.g. (3,4), has the card
	pg.evaluate("openCell(3, 4, {zoom: true})")
	pg.wait_for_selector(f".holes-block .hole-card[data-hole-piece='{a}']", timeout=20_000)
	pg.click(f".holes-block .hole-card[data-hole-piece='{a}'] [data-hole-act='confirmar']")
	t0 = time.time()
	while not _events(pr, "hole_confirmed") and time.time() - t0 < 30:
		time.sleep(0.2)
	hc = _events(pr, "hole_confirmed")[-1]
	assert hc["piece"] == a and hc["cell"] == [3, 4] and hc["origin"] == "buraco" and hc["m"] == 1 and hc["confianca"] in ("media", "sem")
	pl = _events(pr, "placed")[-1]
	assert pl["piece"] == a and pl["origin"] == "buraco"
	assert errs == [], errs
	pg.close()
