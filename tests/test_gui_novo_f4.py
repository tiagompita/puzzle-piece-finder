"""F4, B4, etapa 1 da GUI nova (2026-11-18): grupos soltos no tabuleiro, desenho e lista. Escrito ANTES do codigo.

Cobre so o desenho e a lista (mover, rodar, fixar e soltar sao das etapas 2 e 3):

- o comutador «Peca a peca · N | Grupos soltos · N» e a lista de grupos («N pecas», «sacos ...», «Mostrar no tabuleiro»);
- «Mostrar no tabuleiro» (``POST /api/grupos/{gid}/mostrar`` com o centro da vista; nao entra no desfazer, C2);
- Q1 b: so o grupo escolhido se desenha com a imagem ``/api/grupos/{gid}.png?rot=``, contorno violeta e sombra; os
  outros grupos mostrados ficam com o contorno violeta tenue;
- o painel do grupo («Grupo de N pecas · Solto», «Pecas do grupo» com Saco · no, «Levar para o lugar provavel» so com
  ``lugar_provavel``, senao «Ainda sem lugar provavel fiavel») e o lugar provavel a tracejado (Q4 b);
- «N em grupos soltos» no topo, a legenda «Grupo solto: ainda nao conta como montado», o vazio «Nao ha grupos soltos.»;
- a camada ``#lyr-grupos`` por baixo dos alvos, o estado ``sobreposto`` visivel, a atualizacao por SSE ``grupos_changed``;
- 1366 x 768 e 390 px sem scroll horizontal, alvos >= 44 px, nenhum P####, G#### nem «ancora» no texto visivel (ESPEC §6).

Playwright (Chromium headless, ``slow``) sobre o projeto sintetico de ``tests/test_server_grupos.py`` (grelha 4 x 6; G1 = 1
peca com candidato (2,4) de margem 2,0, G2 = 2 pecas com candidato de margem 1,0, ou seja sem lugar provavel)."""

import json
import re
import urllib.request

import pytest

pytestmark = pytest.mark.slow
pytest.importorskip("fastapi")
pytest.importorskip("uvicorn")
sync_api = pytest.importorskip("playwright.sync_api")

from src import server as SV  # noqa: E402
from test_gui_novo import browser, _serve  # noqa: E402,F401
from test_server_grupos import _board_project, _cand, PSI_W  # noqa: E402

PROIBIDO = [r"\bP\d{4}\b", r"\bG\d{4}\b", r"[Âa]ncora", r"\(\s*\d+\s*,\s*\d+\s*\)"]


@pytest.fixture
def gr(tmp_path):
	from src.query import run_query
	pr, ids = _board_project(tmp_path, cand1=_cand((2, 4)), cand2=_cand((3, 3), margin=1.0))
	run_query(pr, use_image=False)
	gui = SV.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp_path / "uploads"), log=None)
	url, server, th = _serve(gui)
	yield url, gui, ids
	server.should_exit = True
	th.join(10)


def _post(url, path, body=None):
	rq = urllib.request.Request(url + path, data=json.dumps(body or {}).encode(), method="POST",
								headers={"Content-Type": "application/json"})
	try:
		with urllib.request.urlopen(rq, timeout=60) as r:
			return r.status, json.loads(r.read())
	except urllib.error.HTTPError as e:
		return e.code, json.loads(e.read())


def _abrir(browser, url, vp=(1366, 768), vista=True):
	pg = browser.new_page(viewport={"width": vp[0], "height": vp[1]})
	errs = []
	pg.on("pageerror", lambda e: errs.append(str(e)))
	pg.goto(url + "/novo/")
	pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
	pg.wait_for_selector("#vista-sw button", timeout=10_000)
	if vista:
		pg.click("#vista-grupos")
		pg.wait_for_selector("#tab-montar [data-vista='grupos']", timeout=10_000)
	return pg, errs


def _visivel(pg):
	return pg.evaluate("document.body.innerText")


def test_comutador_e_lista(gr, browser):
	url, gui, ids = gr
	pg, errs = _abrir(browser, url, vista=False)
	try:
		assert re.search(r"Peça a peça · \d+", pg.inner_text("#vista-pecas"))
		assert pg.inner_text("#vista-grupos").replace("\xa0", " ") == "Grupos soltos · 2"
		assert pg.get_attribute("#vista-pecas", "aria-pressed") == "true"
		pg.click("#vista-grupos")
		assert pg.get_attribute("#vista-grupos", "aria-pressed") == "true"
		rows = pg.locator("#tab-montar .grp-row")
		assert rows.count() == 2
		txt = [rows.nth(i).inner_text() for i in range(2)]
		assert "1 peça" in txt[0] and "2 peças" in txt[1]
		assert "saco 4" in txt[0].lower()
		for i in range(2):
			b = rows.nth(i).locator(".grp-mostrar")
			assert b.inner_text().strip() == "Mostrar no tabuleiro"
			assert b.bounding_box()["height"] >= 44
			assert rows.nth(i).locator(".grp-open").bounding_box()["height"] >= 44
		pg.click("#vista-pecas")                                    # volta ao Montar
		assert pg.locator("#tab-montar .grp-row").count() == 0
		assert not errs, errs
	finally:
		pg.close()


def test_mostrar_no_tabuleiro_grava_e_desenha(gr, browser):
	url, gui, ids = gr
	pg, errs = _abrir(browser, url)
	try:
		assert pg.locator("#lyr-grupos [data-grupo]").count() == 0          # nunca mostrado: fora do tabuleiro
		seq0 = gui.seq
		with pg.expect_request(lambda r: r.url.endswith(f"/api/grupos/{ids['G1']}/mostrar") and r.method == "POST") as rq:
			pg.locator("#tab-montar .grp-row").nth(0).locator(".grp-mostrar").click()
		body = json.loads(rq.value.post_data)
		assert len(body["centro"]) == 2 and all(isinstance(v, (int, float)) for v in body["centro"])
		pg.wait_for_selector(f"#lyr-grupos [data-grupo='{ids['G1']}']", timeout=10_000)
		assert pg.locator("#lyr-grupos [data-grupo]").count() == 1
		d = json.loads(urllib.request.urlopen(url + "/api/grupos").read())
		g1 = next(g for g in d["grupos"] if g["id"] == ids["G1"])
		assert g1["mostrado"] and g1["posicao"]["l0"] == 2 and g1["posicao"]["c0"] == 4      # o candidato 1 (margem 2,0)
		names = [n for _, n, _ in gui.events_after(seq0)]
		assert "board_changed" not in names                                  # C2: nao toca no tabuleiro nem no desfazer
		assert pg.locator("#m-ultimo").count() == 0                          # nao ha faixa «Desfazer»
		assert not errs, errs
	finally:
		pg.close()


def _mostrar_todos(url, ids):
	for k in ("G1", "G2"):
		st, r = _post(url, f"/api/grupos/{ids[k]}/mostrar", {"centro": [2.0, 3.0]})
		assert st == 200, r


def test_so_o_grupo_escolhido_tem_imagem(gr, browser):
	url, gui, ids = gr
	_mostrar_todos(url, ids)
	pg, errs = _abrir(browser, url)
	try:
		g1, g2 = ids["G1"], ids["G2"]
		pg.wait_for_selector(f"#lyr-grupos [data-grupo='{g2}']", timeout=10_000)
		assert pg.locator("#lyr-grupos image").count() == 0                  # nenhum escolhido: so contornos tenues
		assert pg.locator("#lyr-grupos .grupo.tenue").count() == 2
		pg.locator("#tab-montar .grp-row").nth(0).locator(".grp-open").click()
		pg.wait_for_selector(f"#lyr-grupos [data-grupo='{g1}'] image.grupo-img", timeout=10_000)
		assert pg.locator("#lyr-grupos image").count() == 1
		href = pg.get_attribute(f"#lyr-grupos [data-grupo='{g1}'] image.grupo-img", "href")
		assert href.startswith(f"/api/grupos/{g1}.png?rot=0")
		assert pg.locator(f"#lyr-grupos [data-grupo='{g1}']").get_attribute("class").split().count("escolhido") == 1
		assert pg.locator(f"#lyr-grupos [data-grupo='{g1}'] .grupo-contorno").count() >= 1
		assert pg.locator(f"#lyr-grupos [data-grupo='{g2}']").get_attribute("class").split().count("tenue") == 1
		pg.click("#grp-voltar")                                                          # a lista; o escolhido deixa de o ser
		pg.wait_for_selector("#tab-montar .grp-row", timeout=10_000)
		assert pg.locator("#lyr-grupos image").count() == 0
		pg.locator("#tab-montar .grp-row").nth(1).locator(".grp-open").click()          # trocar de escolha
		pg.wait_for_selector(f"#lyr-grupos [data-grupo='{g2}'] image.grupo-img", timeout=10_000)
		assert pg.locator("#lyr-grupos image").count() == 1
		assert pg.locator(f"#lyr-grupos [data-grupo='{g1}'] image").count() == 0
		assert not errs, errs
	finally:
		pg.close()


def test_camada_por_baixo_dos_alvos(gr, browser):
	url, gui, ids = gr
	pg, errs = _abrir(browser, url)
	try:
		ordem = pg.evaluate("""[...document.querySelectorAll('#board > g')].map(g => g.id)""")
		i = ordem.index("lyr-grupos")
		assert i < ordem.index("lyr-seguinte") < ordem.index("lyr-alvo")      # o alvo das sugestoes fica por cima do grupo
		assert i > ordem.index("lyr-fantasma")
		assert pg.evaluate("getComputedStyle(document.querySelector('#lyr-grupos')).pointerEvents") == "none"
	finally:
		pg.close()


def test_painel_do_grupo(gr, browser):
	url, gui, ids = gr
	pg, errs = _abrir(browser, url)
	try:
		pg.locator("#tab-montar .grp-row").nth(1).locator(".grp-open").click()                 # G2: sem lugar provavel
		pg.wait_for_selector("#tab-montar .grp-painel", timeout=10_000)
		t = pg.inner_text("#tab-montar .grp-painel")
		assert "Grupo de 2 peças" in t and "Solto" in t
		assert "Peças do grupo" in t
		assert len(pg.locator("#tab-montar .grp-peca").all()) == 2
		assert re.search(r"Saco 4 · \d", pg.locator("#tab-montar .grp-peca").nth(0).inner_text())
		assert "Ainda sem lugar provável fiável" in t
		assert pg.locator("#g-levar").count() == 0
		assert pg.locator("#lyr-grupos .grupo-provavel").count() == 0
		pg.click("#grp-voltar")
		pg.locator("#tab-montar .grp-row").nth(0).locator(".grp-open").click()                 # G1: lugar provavel (2,4)
		pg.wait_for_selector("#tab-montar .grp-painel", timeout=10_000)
		t = pg.inner_text("#tab-montar .grp-painel")
		assert "Grupo de 1 peça" in t and "Grupo de 1 peças" not in t
		assert pg.locator("#g-levar").inner_text().strip() == "Levar para o lugar provável"
		assert pg.locator("#g-levar").bounding_box()["height"] >= 44
		assert "Ainda sem lugar provável fiável" not in t
		pg.wait_for_selector("#lyr-grupos .grupo-provavel", timeout=10_000)                    # a tracejado (Q4 b)
		assert pg.evaluate("getComputedStyle(document.querySelector('#lyr-grupos .grupo-provavel .grupo-contorno')).strokeDasharray") not in ("none", "")
		assert not errs, errs
	finally:
		pg.close()


def test_n_em_grupos_soltos_no_topo(gr, browser):
	url, gui, ids = gr
	pg, errs = _abrir(browser, url, vista=False)
	try:
		assert "3 em grupos soltos" in pg.inner_text("#progress-txt")
	finally:
		pg.close()


def test_legenda_do_grupo_solto(gr, browser):
	url, gui, ids = gr
	pg, errs = _abrir(browser, url)
	try:
		assert "Grupo solto: ainda não conta como montado" not in pg.inner_text("#legend")      # nenhum mostrado ainda
		_mostrar_todos(url, ids)
		pg.wait_for_selector("#lyr-grupos [data-grupo]", timeout=10_000)
		assert "Grupo solto: ainda não conta como montado" in pg.inner_text("#legend")
	finally:
		pg.close()


def test_vazio(gr, browser):
	url, gui, ids = gr
	pg = browser.new_page(viewport={"width": 1366, "height": 768})
	vazio = {"versao": 0, "n_grupos": 0, "n_pecas": 0, "n_mostrados": 0, "grupos": [], "aviso": []}
	pg.route("**/api/grupos", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(vazio)))
	try:
		pg.goto(url + "/novo/")
		pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
		pg.wait_for_selector("#vista-sw button", timeout=10_000)
		assert pg.inner_text("#vista-grupos").replace("\xa0", " ") == "Grupos soltos · 0"
		pg.click("#vista-grupos")
		assert "Não há grupos soltos." in pg.inner_text("#tab-montar")
		assert "em grupos soltos" not in pg.inner_text("#progress-txt")
	finally:
		pg.close()


def test_sobreposto_visivel(gr, browser):
	url, gui, ids = gr
	st, r = _post(url, f"/api/grupos/{ids['G1']}/mostrar", {})
	assert st == 200, r
	st, r = _post(url, "/api/confirm", {"acao": "place", "piece": ids["W"], "cell": [2, 4], "theta_deg": -PSI_W, "origin": "manual"})
	assert st == 200, r
	pg, errs = _abrir(browser, url)
	try:
		pg.wait_for_selector(f"#lyr-grupos [data-grupo='{ids['G1']}'].sobreposto", timeout=10_000)
		row = pg.locator("#tab-montar .grp-row").nth(0)
		assert "por cima" in row.inner_text().lower()
		row.locator(".grp-open").click()
		pg.wait_for_selector("#tab-montar .grp-painel", timeout=10_000)
		assert "por cima" in pg.inner_text("#tab-montar .grp-painel").lower() or "já tem uma peça" in pg.inner_text("#tab-montar .grp-painel")
		assert not errs, errs
	finally:
		pg.close()


def test_atualiza_por_sse_grupos_changed(gr, browser):
	url, gui, ids = gr
	pg, errs = _abrir(browser, url)
	try:
		assert pg.locator("#lyr-grupos [data-grupo]").count() == 0
		st, r = _post(url, f"/api/grupos/{ids['G2']}/mostrar", {"centro": [3.0, 3.0]})      # outro cliente
		assert st == 200, r
		pg.wait_for_selector(f"#lyr-grupos [data-grupo='{ids['G2']}']", timeout=10_000)
		assert "Grupo solto: ainda não conta como montado" in pg.inner_text("#legend")
		assert not errs, errs
	finally:
		pg.close()


def test_levar_para_o_lugar_provavel(gr, browser):
	url, gui, ids = gr
	assert _post(url, f"/api/grupos/{ids['G1']}/mostrar", {})[0] == 200                     # o candidato 1: (2,4)
	st, r = _post(url, f"/api/grupos/{ids['G1']}/mover", {"l0": 4, "c0": 1, "rot": 0})      # para longe do lugar provavel
	assert st == 200, r
	pg, errs = _abrir(browser, url)
	try:
		pg.locator("#tab-montar .grp-row").nth(0).locator(".grp-open").click()
		pg.click("#g-levar")
		pg.wait_for_function("document.querySelector('#lyr-grupos .grupo-provavel') === null", timeout=10_000)   # ja la esta
		d = json.loads(urllib.request.urlopen(url + "/api/grupos").read())
		g1 = next(g for g in d["grupos"] if g["id"] == ids["G1"])
		assert (g1["posicao"]["l0"], g1["posicao"]["c0"]) == (2, 4)
		assert not errs, errs
	finally:
		pg.close()


@pytest.mark.parametrize("vp", [(1366, 768), (390, 844)])
def test_sem_scroll_horizontal_alvos_e_texto(gr, browser, vp):
	url, gui, ids = gr
	_mostrar_todos(url, ids)
	pg, errs = _abrir(browser, url, vp=vp)
	try:
		pg.wait_for_selector("#lyr-grupos [data-grupo]", timeout=10_000)
		pg.locator("#tab-montar .grp-row").nth(0).locator(".grp-open").click()
		pg.wait_for_selector("#tab-montar .grp-painel", timeout=10_000)
		for etapa in ("painel", "lista"):
			assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), (vp, etapa)
			assert pg.evaluate("document.body.scrollWidth <= window.innerWidth + 1"), (vp, etapa)
			t = _visivel(pg)
			for rx in PROIBIDO:
				assert not re.search(rx, t), (rx, vp, etapa)
			small = pg.evaluate("""[...document.querySelectorAll('#vista-sw button, #tab-montar button')]
				.filter(b => b.offsetParent !== null && b.getBoundingClientRect().height < 43.5).map(b => b.id || b.className)""")
			assert small == [], (vp, etapa, small)
			if etapa == "painel":
				pg.click("#grp-voltar")
				pg.wait_for_selector("#tab-montar .grp-row", timeout=10_000)
		assert not errs, errs
	finally:
		pg.close()
