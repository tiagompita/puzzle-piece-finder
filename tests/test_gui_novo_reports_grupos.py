"""A2-A4 (2026-11-25): flag vermelha dos reports abertos e seta de voltar no painel do grupo (GUI nova). Escrito ANTES do codigo.

- um report enviado no painel do grupo deixa a flag vermelha na peca, no titulo do grupo e na linha da lista, sem recarregar;
- um report fechado pela CLI (``reports.set_state``) volta ao normal depois do SSE seguinte;
- o painel da peca (lugar) tem a flag vermelha com um report aberto da peca;
- a seta «Voltar a lista» (``#grp-voltar``) fica no cabecalho, a esquerda do titulo, alvo >= 44 px, visivel sem scroll num
  grupo com 8 pecas a 390 x 844 (mesmo com o painel rolado) e volta a lista.

Playwright (Chromium headless, ``slow``) sobre o projeto sintetico de ``tests/test_server_grupos.py``."""

import json

import pytest

pytestmark = pytest.mark.slow
pytest.importorskip("fastapi")
pytest.importorskip("uvicorn")
sync_api = pytest.importorskip("playwright.sync_api")

from src import reports as RP  # noqa: E402
from test_gui_novo import browser  # noqa: E402,F401
from test_gui_novo_f4 import gr, _abrir, _post  # noqa: E402,F401

VERMELHO = "rgb(255, 107, 95)"


def _abrir_g2(pg):
	pg.locator("#tab-montar .grp-row").nth(1).locator(".grp-open").click()                 # G2: 2 pecas
	pg.wait_for_selector("#tab-montar .grp-painel", timeout=10_000)


def _cor(pg, sel):
	return pg.evaluate("(s) => getComputedStyle(document.querySelector(s)).color", sel)


def test_report_no_painel_do_grupo_poe_a_flag_vermelha_sem_recarregar(gr, browser):
	url, gui, ids = gr
	pg, errs = _abrir(browser, url)
	try:
		assert pg.locator("#tab-montar .grp-row .flag-report").count() == 0
		_abrir_g2(pg)
		assert pg.locator(".grp-errado.tem-report").count() == 0 and pg.locator(".grp-titulo .flag-report").count() == 0
		pg.evaluate("window.__marca = 1")
		pg.locator(".grp-errado").nth(1).click()
		pg.click("[data-report] .tipos [data-tipo='mal_lida']")
		pg.fill(".grp-report-txt", "torta")
		pg.click(".grp-report-enviar")
		pg.wait_for_selector(".grp-errado.tem-report", timeout=10_000)
		assert pg.locator(".grp-errado.tem-report").count() == 1                       # so a peca reportada
		assert pg.locator(".grp-peca-linha").nth(1).locator(".grp-errado.tem-report").count() == 1
		assert pg.locator(".grp-titulo .flag-report").count() == 1
		assert pg.get_attribute(".grp-titulo .flag-report", "aria-label") == "Tem um report aberto"
		assert pg.get_attribute(".grp-errado.tem-report", "title") == "Tem um report aberto"
		assert _cor(pg, ".grp-errado.tem-report .ico") == VERMELHO
		assert _cor(pg, ".grp-titulo .flag-report") == VERMELHO
		assert "Já reportaste: o recorte está mal («torta»)" in pg.inner_text(".grp-peca-linha >> nth=1")
		assert pg.evaluate("window.__marca") == 1                                       # sem recarregar a pagina
		pg.click("#grp-voltar")
		pg.wait_for_selector("#tab-montar .grp-row", timeout=10_000)
		assert pg.locator("#tab-montar .grp-row").nth(1).locator(".flag-report").count() == 1
		assert pg.locator("#tab-montar .grp-row").nth(0).locator(".flag-report").count() == 0
		assert not errs, errs
	finally:
		pg.close()


def test_fechar_pela_cli_volta_ao_normal_no_sse_seguinte(gr, browser):
	url, gui, ids = gr
	rid = _post(url, "/api/report", {"piece": ids["Z"], "tipo": "outro", "texto": ""})[1]["id"]
	pg, errs = _abrir(browser, url)
	try:
		pg.wait_for_selector("#tab-montar .grp-row .flag-report", timeout=10_000)
		_abrir_g2(pg)
		assert pg.locator(".grp-errado.tem-report").count() == 1 and pg.locator(".grp-titulo .flag-report").count() == 1
		RP.set_state(gui.pr, rid, "close", "feito")                                       # como a CLI
		gui.emit("suspeitas_changed", {})                                               # o SSE a seguir; a CLI real mexe no log (board_changed externo)
		pg.wait_for_function("document.querySelectorAll('.grp-errado.tem-report').length === 0", timeout=10_000)
		assert pg.locator(".grp-titulo .flag-report").count() == 0
		assert pg.locator(".p-reportado").count() == 0
		pg.click("#grp-voltar")
		assert pg.locator("#tab-montar .grp-row .flag-report").count() == 0
		assert not errs, errs
	finally:
		pg.close()


def test_painel_da_peca_com_report_aberto_tem_a_flag_vermelha(gr, browser):
	url, gui, ids = gr
	pg, errs = _abrir(browser, url, vista=False)
	try:
		pg.evaluate("openPainel(2, 3)")
		pg.wait_for_selector("#painel[data-kind='peca']", timeout=20_000)
		assert pg.locator("#p-errado.tem-report").count() == 0
		assert _post(url, "/api/report", {"piece": ids["A"], "cell": [2, 3], "tipo": "mal_lida", "texto": ""})[0] == 200
		pg.wait_for_selector("#p-errado.tem-report", timeout=10_000)                      # o SSE refaz o painel aberto
		assert pg.get_attribute("#p-errado", "title") == "Tem um report aberto"
		assert _cor(pg, "#p-errado.tem-report .ico") == VERMELHO
		assert "Já reportaste" in pg.inner_text("#painel")
		assert not errs, errs
	finally:
		pg.close()


def _com_8_pecas(pg_ctx_route):
	def h(route):
		r = route.fetch()
		d = r.json()
		for g in d["grupos"]:
			if g["n"] == 2:
				g["pecas"] = [dict(g["pecas"][i % 2], id=f"{g['pecas'][i % 2]['id']}", n_no_lote=i + 1) for i in range(8)]
				g["n"] = 8
		route.fulfill(response=r, body=json.dumps(d), headers={"content-type": "application/json"})
	return h


def test_seta_no_topo_sem_scroll_com_8_pecas_a_390_e_volta(gr, browser):
	url, gui, ids = gr
	ctx = browser.new_context(viewport={"width": 390, "height": 844})
	ctx.route("**/api/grupos", _com_8_pecas(None))
	pg = ctx.new_page()
	errs = []
	pg.on("pageerror", lambda e: errs.append(str(e)))
	try:
		pg.goto(url + "/novo/")
		pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
		pg.wait_for_function("!!S.grupos", timeout=30_000)
		pg.click("#vista-grupos")
		pg.wait_for_selector("#tab-montar .grp-row", timeout=10_000)
		pg.locator("#tab-montar .grp-row").nth(1).locator(".grp-open").click()
		pg.wait_for_selector("#tab-montar .grp-painel", timeout=10_000)
		assert pg.locator(".grp-peca-linha").count() == 8
		v = pg.locator("#grp-voltar")
		assert v.get_attribute("aria-label") == "Voltar à lista"
		bb, tb, tab = v.bounding_box(), pg.locator(".grp-titulo").bounding_box(), pg.locator("#tab-montar").bounding_box()
		assert bb["width"] >= 44 - 0.5 and bb["height"] >= 44 - 0.5, bb
		assert bb["x"] + bb["width"] <= tb["x"] + 0.5                                   # a esquerda do titulo
		assert tab["y"] - 0.5 <= bb["y"] and bb["y"] + bb["height"] <= tab["y"] + tab["height"]
		assert pg.evaluate("document.querySelector('#tab-montar').scrollHeight > document.querySelector('#tab-montar').clientHeight")
		pg.evaluate("document.querySelector('#tab-montar').scrollTop = 10000")            # mesmo com o painel rolado ate ao fim
		bb2 = v.bounding_box()
		assert tab["y"] - 0.5 <= bb2["y"] and bb2["y"] + bb2["height"] <= tab["y"] + tab["height"] + 0.5, (bb2, tab)
		assert not pg.evaluate("document.documentElement.scrollWidth > window.innerWidth")
		v.click()
		pg.wait_for_selector("#tab-montar .grp-row", timeout=10_000)
		assert pg.locator("#tab-montar .grp-painel").count() == 0
		assert not errs, errs
	finally:
		pg.unroute_all(behavior="ignoreErrors")
		ctx.close()
