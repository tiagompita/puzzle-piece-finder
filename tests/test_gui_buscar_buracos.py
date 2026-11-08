"""Playwright (``slow``): sugestões ``alta`` em «Vai buscar» (chip «por buraco · alta», contador, nenhuma média / baixa lá),
a página «Buracos» por grupos com as 3 melhores por buraco e «Não encaixa» em um clique (rank 2 gravado), a regra de
pausa (aviso + «Reativar») — a 1366×768, 1366×768 a 150 % (911×512) e telemóvel, sem overflow.
Projeto sintético de :func:`test_server_alta._alta_project` (o buraco (2,3) é ``alta`` com m = 2).
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
from src.state import Project  # noqa: E402
from test_server_alta import _alta_project  # noqa: E402

SHOTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "gui", "screenshots")
VIEWPORTS = [(1366, 768), (911, 512), (390, 844)]


def _serve(gui):
	import uvicorn
	s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
	server = uvicorn.Server(uvicorn.Config(S.create_app(gui), host="127.0.0.1", port=port, log_level="warning"))
	th = threading.Thread(target=server.run, daemon=True)
	th.start()
	t0 = time.time()
	while not server.started and time.time() - t0 < 30:
		time.sleep(0.05)
	return f"http://127.0.0.1:{port}", server, th


@pytest.fixture(scope="module")
def env(tmp_path_factory):
	tmp = tmp_path_factory.mktemp("alta")
	pr, ids = _alta_project(tmp)
	gui = S.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp / "uploads"), log=None)
	gui.holes_json(wait=True)
	base, server, th = _serve(gui)
	yield base, gui, pr, ids
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


def _page(browser, w, h):
	phone = w <= 430
	ctx = browser.new_context(viewport={"width": w, "height": h}, has_touch=phone, is_mobile=phone, device_scale_factor=1.5 if (w, h) == (911, 512) else 1.0)
	pg = ctx.new_page()
	errs = []
	pg.on("pageerror", lambda e: errs.append(str(e)))
	return ctx, pg, errs


@pytest.mark.parametrize("w,h", VIEWPORTS)
def test_alta_card_in_vai_buscar_and_holes_page(env, browser, w, h):
	base, gui, pr, ids = env
	phone = w <= 430
	ctx, pg, errs = _page(browser, w, h)
	pg.goto(base + "/")
	pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
	pg.wait_for_selector("#tab-buscar .card.hole-sug", timeout=30_000)
	cards = pg.query_selector_all("#tab-buscar .card.hole-sug")
	assert len(cards) >= 1
	card = pg.query_selector(f"#tab-buscar .card.hole-sug[data-piece='{ids['A']}']")
	assert card is not None and card.get_attribute("data-rank") == "1"
	assert pg.query_selector(f"#tab-buscar .card.hole-sug[data-piece='{ids['A']}'] .chip.buraco") is not None
	assert "Saco" in pg.inner_text(f"#tab-buscar .card.hole-sug[data-piece='{ids['A']}'] .who") and "nº" in pg.inner_text(f"#tab-buscar .card.hole-sug[data-piece='{ids['A']}'] .who")
	assert "(2, 3)" in pg.inner_text(f"#tab-buscar .card.hole-sug[data-piece='{ids['A']}'] .where")
	assert pg.query_selector(f"#tab-buscar .card.hole-sug[data-piece='{ids['A']}'] .hole-mini") is not None    # drawn in the hole with the neighbours
	assert pg.evaluate(f"document.querySelectorAll(\"#tab-buscar .card.hole-sug[data-piece='{ids['A']}'] .hole-mini .hole-neigh\").length") >= 2
	for act in ("confirmar", "rejeitar", "ver"):
		b = pg.query_selector(f"#tab-buscar .card.hole-sug[data-piece='{ids['A']}'] [data-hole-act='{act}']")
		assert b is not None and b.bounding_box()["height"] >= (40 if phone else 28)
	# the counter line and no media / baixa / sem card in «Vai buscar»
	cnt = pg.query_selector("#tab-buscar .alta-count")
	assert cnt is not None and cnt.get_attribute("data-total") == "0" and "acertos 0 / falhas 0 / total 0" in cnt.inner_text()
	assert pg.evaluate("document.querySelectorAll('#tab-buscar .hole-card').length") == 0
	assert pg.evaluate("[...document.querySelectorAll('#tab-buscar .card.hole-sug .chip.buraco')].every((c) => c.textContent.includes('alta'))")
	assert pg.inner_text("#n-buscar").strip() == str(len(cards))
	_no_overflow(pg)
	pb = pg.query_selector("#panel").bounding_box()
	cb = cards[0].bounding_box()
	assert cb["x"] >= pb["x"] - 1 and cb["x"] + cb["width"] <= pb["x"] + pb["width"] + 1
	# the «Buracos» page: groups, the alta hole only as reference, a row opens with up to 3 cards
	pg.evaluate("locateQuery('buracos')")
	pg.wait_for_selector("#tab-buracos.on", timeout=5_000)
	pg.wait_for_selector("#tab-buracos details.hole-group", timeout=20_000)
	groups = pg.evaluate("[...document.querTselectorAll ? [] : document.querySelectorAll('#tab-buracos details.hole-group')].map((g) => g.dataset.group)")
	assert "alta_buscar" in groups and not pg.evaluate("document.querySelector('#tab-buracos details.hole-group[data-group=alta_buscar]').open")
	assert pg.evaluate("document.querySelectorAll('#tab-buracos details.hole-group[data-group=alta_pausa]').length") == 0
	assert pg.query_selector("#tab-buracos .alta-banner .alta-count") is not None
	row = pg.query_selector("#tab-buracos details.hole-row[data-cell='2,3']")
	assert row is not None and row.get_attribute("data-group") == "alta_buscar"
	pg.evaluate("document.querySelector('#tab-buracos details.hole-group[data-group=alta_buscar]').open = true")
	pg.click("#tab-buracos details.hole-row[data-cell='2,3'] > summary")
	pg.wait_for_selector("#tab-buracos details.hole-row[data-cell='2,3'] .hole-card", timeout=20_000)
	n = pg.evaluate("document.querySelectorAll(\"#tab-buracos details.hole-row[data-cell='2,3'] .hole-card\").length")
	assert 1 <= n <= 3
	assert pg.query_selector("#tab-buracos details.hole-row[data-cell='2,3'] [data-hole-open]") is not None
	_no_overflow(pg)
	if os.environ.get("PPF_SHOTS") and (w, h) == (1366, 768):
		os.makedirs(SHOTS, exist_ok=True)
		pg.screenshot(path=os.path.join(SHOTS, "buracos_pagina_grupos.png"))
		pg.evaluate("showTab('buscar')")
		pg.wait_for_selector("#tab-buscar .card.hole-sug", timeout=10_000)
		pg.screenshot(path=os.path.join(SHOTS, "vai_buscar_por_buraco.png"))
	assert errs == [], errs
	ctx.close()


def test_reject_rank2_from_page_then_pause_and_resume(env, browser):
	base, gui, pr, ids = env
	ctx, pg, errs = _page(browser, 1366, 768)
	pg.goto(base + "/")
	pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
	pg.evaluate("locateQuery('buracos')")
	pg.wait_for_selector("#tab-buracos details.hole-group", timeout=20_000)
	pg.evaluate("document.querySelector('#tab-buracos details.hole-group[data-group=alta_buscar]').open = true")
	pg.click("#tab-buracos details.hole-row[data-cell='2,3'] > summary")
	pg.wait_for_selector("#tab-buracos details.hole-row[data-cell='2,3'] .hole-card[data-rank='2']", timeout=20_000)
	second = pg.get_attribute("#tab-buracos details.hole-row[data-cell='2,3'] .hole-card[data-rank='2']", "data-hole-piece")
	n0 = len(_events(pr, "hole_rejected"))
	pg.click("#tab-buracos details.hole-row[data-cell='2,3'] .hole-card[data-rank='2'] [data-hole-act='rejeitar']")   # one click, no dialog
	t0 = time.time()
	while len(_events(pr, "hole_rejected")) == n0 and time.time() - t0 < 30:
		time.sleep(0.2)
	ev = _events(pr, "hole_rejected")[-1]
	assert ev["piece"] == second and ev["rank"] == 2 and ev["confianca"] == "alta" and ev["m"] == 2 and ev["fit_version"] and ev["custo"] > 0
	pg.wait_for_selector("#toast div:has-text('Rejeição registada')", timeout=10_000)
	# a rank-2 rejection is not a decision: the counter stays at 0 and the suggestion stays in «Vai buscar»
	pg.wait_for_function("document.querySelector('#tab-buracos .alta-count') && document.querySelector('#tab-buracos .alta-count').dataset.total === '0'", timeout=20_000)
	# pause: 3 alta rank-1 rejections written behind the server (as three physical «não encaixa» would)
	for cell in [(1, 1), (1, 2), (1, 3)]:
		pr.log_event("hole_rejected", piece=ids["D"], cell=cell, origin="buraco", rank=1, custo=1.0, margem=2.0, confianca="alta", m=2, fit_version="t")
	pr.save()
	gui.sync()
	gui.holes_json(wait=True)
	pg.reload()
	pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
	pg.wait_for_selector("#tab-buscar .alta-pause", timeout=30_000)
	assert pg.evaluate("document.querySelectorAll('#tab-buscar .card.hole-sug').length") == 0        # moved out of «Vai buscar»
	assert "3 falhas" in pg.inner_text("#tab-buscar .alta-count") or "falhas 3" in pg.inner_text("#tab-buscar .alta-count")
	pg.evaluate("locateQuery('buracos')")
	pg.wait_for_selector("#tab-buracos details.hole-group[data-group=alta_pausa]", timeout=20_000)
	assert pg.query_selector("#tab-buracos details.hole-row[data-cell='2,3'][data-group='alta_pausa']") is not None
	_no_overflow(pg)
	# reactivate from the page: event + the suggestions come back
	pg.click("#tab-buracos [data-alta-reativar]")
	t0 = time.time()
	while not _events(pr, "holes_alta_resumed") and time.time() - t0 < 30:
		time.sleep(0.2)
	assert _events(pr, "holes_alta_resumed")[-1]["autor"] == "tiago"
	pg.evaluate("showTab('buscar')")
	pg.wait_for_selector("#tab-buscar .card.hole-sug", timeout=30_000)
	assert pg.evaluate("document.querySelectorAll('#tab-buscar .alta-pause').length") == 0
	assert Project.open(pr.path).check_invariants(disk=True) == []
	assert errs == [], errs
	ctx.close()
