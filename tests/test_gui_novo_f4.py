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
from test_gui_novo_f2f import _fechar  # noqa: E402

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


# ============================================================================ etapa 2: mover e rodar (escrito ANTES do codigo)
#
# Contrato do servidor (src/server.py grupo_mover): POST mover {l0, c0, rot} copia o ``rodado`` da linha atual (o corpo
# pode trazer ``rodado`` explicito); {rodar: +-90} grava ``rodado: true``; a resposta traz ``anterior`` (posicao efectiva
# antes da escrita, com ``rodado``). O desfazer e um ``mover`` com a ``anterior`` e o ``rodado`` explicito de ``anterior``.


def _grupo_api(url, gid):
	d = json.loads(urllib.request.urlopen(url + "/api/grupos").read())
	return next(g for g in d["grupos"] if g["id"] == gid)


def _xy(pg, l, c):
	"""Coordenadas de ecra do centro da celula (l, c); aceita fracoes (l = 2.3 e 30 % abaixo do centro da linha 2)."""
	return pg.evaluate("""([l, c]) => { const r = svgRect(), v = S.vb;
		return { x: r.left + ((c - 0.5) - v.x) / v.w * r.width, y: r.top + (((l - 0.5) * S.hr) - v.y) / v.h * r.height }; }""", [l, c])


def _arrastar(pg, de, para, ctrl=False, passos=8, soltar=True):
	a, b = _xy(pg, *de), _xy(pg, *para)
	if ctrl:
		pg.keyboard.down("Control")
	pg.mouse.move(a["x"], a["y"])
	pg.mouse.down()
	for i in range(1, passos + 1):
		pg.mouse.move(a["x"] + (b["x"] - a["x"]) * i / passos, a["y"] + (b["y"] - a["y"]) * i / passos)
	if soltar:
		pg.mouse.up()
		if ctrl:
			pg.keyboard.up("Control")


def _espiar(pg):
	reqs = []
	pg.on("request", lambda r: reqs.append((r.method, r.url.split("?")[0], r.post_data)) if r.method == "POST" else None)
	return reqs


def _movers(reqs):
	return [json.loads(b) for m, u, b in reqs if u.endswith("/mover")]


def _pos_no_cliente(pg, gid):
	return pg.evaluate("(gid) => { const p = grupo(gid).posicao; return [p.l0, p.c0, p.rot]; }", gid)


def _mostrar(url, ids, k, centro=None):
	st, r = _post(url, f"/api/grupos/{ids[k]}/mostrar", {"centro": centro} if centro else {})
	assert st == 200, r


def test_ctrl_arrastar_encaixa_e_grava(gr, browser):
	url, gui, ids = gr
	_mostrar(url, ids, "G1")                                            # (2,4)
	pg, errs = _abrir(browser, url, vista=False)
	reqs = _espiar(pg)
	try:
		pg.wait_for_selector(f"#lyr-grupos [data-grupo='{ids['G1']}']", timeout=10_000)
		vb0 = pg.evaluate("({ ...S.vb })")
		seq0 = gui.seq
		_arrastar(pg, (2, 4), (3.2, 5.3), ctrl=True, soltar=False)
		assert pg.evaluate("S.vb") == vb0                                 # sem pan
		tr = pg.get_attribute(f"#lyr-grupos [data-grupo='{ids['G1']}']", "transform")
		assert tr and "translate" in tr                                   # a meio, o grupo anda encaixado as celulas
		pg.mouse.up()
		pg.keyboard.up("Control")
		pg.wait_for_function("(gid) => grupo(gid).posicao.l0 === 3 && !S.busy", arg=ids["G1"], timeout=10_000)
		assert _pos_no_cliente(pg, ids["G1"]) == [3, 5, 0]                # arredondado: 1 linha e 1 coluna
		g = _grupo_api(url, ids["G1"])
		assert (g["posicao"]["l0"], g["posicao"]["c0"], g["rodado"]) == (3, 5, False)
		mv = _movers(reqs)
		assert len(mv) == 1 and (mv[0]["l0"], mv[0]["c0"], mv[0]["rot"]) == (3, 5, 0)
		assert mv[0].get("rodado") in (None, False)
		assert pg.get_attribute(f"#lyr-grupos [data-grupo='{ids['G1']}']", "transform") is None     # o desenho vem da posicao gravada
		assert "board_changed" not in [n for _, n, _ in gui.events_after(seq0)]
		assert pg.locator("#m-ultimo").count() == 1                      # faixa «Desfazer»
		assert not errs, errs
	finally:
		pg.close()


def test_ctrl_arrastar_invalido_volta_sem_post(gr, browser):
	url, gui, ids = gr
	_mostrar(url, ids, "G1")                                            # (2,4); A (colocada) em (2,3)
	_mostrar(url, ids, "G2", [3.0, 2.0])
	g2 = _grupo_api(url, ids["G2"])
	cel2 = g2["footprint"][0]
	pg, errs = _abrir(browser, url, vista=False)
	reqs = _espiar(pg)
	try:
		pg.wait_for_selector(f"#lyr-grupos [data-grupo='{ids['G2']}']", timeout=10_000)
		casos = [((2, 3), "já tem uma peça"),                              # sobre a colocada A
				 ((2, 7), "sai do tabuleiro"),                              # fora da grelha (3 colunas para a direita)
				 ((cel2[0], cel2[1]), "outro grupo")]                       # sobre o outro grupo
		for alvo, frase in casos:
			_arrastar(pg, (2, 4), alvo, ctrl=True)
			pg.wait_for_timeout(150)
			assert _pos_no_cliente(pg, ids["G1"]) == [2, 4, 0], (alvo, frase)
			assert pg.get_attribute(f"#lyr-grupos [data-grupo='{ids['G1']}']", "transform") is None, alvo
			assert frase in pg.inner_text("#toast"), (alvo, frase, pg.inner_text("#toast"))
		assert _movers(reqs) == []                                         # nenhum POST
		assert _grupo_api(url, ids["G1"])["posicao"]["l0"] == 2
		assert not errs, errs
	finally:
		pg.close()


def test_mover_feito_com_rato(gr, browser):
	url, gui, ids = gr
	_mostrar(url, ids, "G1")
	pg, errs = _abrir(browser, url)
	reqs = _espiar(pg)
	try:
		pg.locator("#tab-montar .grp-row").nth(0).locator(".grp-open").click()
		pg.wait_for_selector("#g-mover", timeout=10_000)
		assert pg.locator("#g-mover").bounding_box()["height"] >= 44
		pg.click("#g-mover")
		pg.wait_for_selector("#g-feito", timeout=5_000)
		assert pg.locator("#g-feito").bounding_box()["height"] >= 44
		assert pg.locator("#g-cancelar").count() == 1
		vb0 = pg.evaluate("({ ...S.vb })")
		_arrastar(pg, (2, 4), (3, 5))                                      # SEM Ctrl: durante o «Mover» arrasta o grupo
		assert pg.evaluate("S.vb") == vb0                                  # e nao faz pan
		assert _movers(reqs) == []                                         # so grava no «Feito»
		assert _grupo_api(url, ids["G1"])["posicao"]["l0"] == 2
		pg.click("#g-feito")
		pg.wait_for_function("(gid) => grupo(gid).posicao.l0 === 3 && !S.busy", arg=ids["G1"], timeout=10_000)
		assert len(_movers(reqs)) == 1 and (_movers(reqs)[0]["l0"], _movers(reqs)[0]["c0"]) == (3, 5)
		assert pg.locator("#g-feito").count() == 0 and pg.locator("#g-mover").count() == 1
		assert pg.locator("#m-ultimo").count() == 1
		# fora do «Mover», arrastar sem Ctrl faz pan (comportamento de sempre)
		_arrastar(pg, (1, 1), (1, 1.6))
		assert pg.evaluate("S.vb.x") != vb0["x"]
		assert not errs, errs
	finally:
		pg.close()


def test_mover_cancelar_e_sair_repoe(gr, browser):
	url, gui, ids = gr
	_mostrar(url, ids, "G1")
	pg, errs = _abrir(browser, url)
	reqs = _espiar(pg)
	try:
		pg.locator("#tab-montar .grp-row").nth(0).locator(".grp-open").click()
		sel = f"#lyr-grupos [data-grupo='{ids['G1']}']"
		for sair in ("#g-cancelar", "#grp-voltar", "Escape"):
			if not pg.locator("#g-mover").count():
				pg.locator("#tab-montar .grp-row").nth(0).locator(".grp-open").click()
			pg.click("#g-mover")
			_arrastar(pg, (2, 4), (3, 5))
			assert pg.get_attribute(sel, "transform")                       # a posicao pendente
			if sair == "Escape":
				pg.keyboard.press("Escape")
			else:
				pg.click(sair)
			pg.wait_for_timeout(150)
			assert pg.get_attribute(sel, "transform") is None, sair
			assert pg.evaluate("S.mover") is None, sair
			assert _pos_no_cliente(pg, ids["G1"]) == [2, 4, 0], sair
		assert _movers(reqs) == []
		assert _grupo_api(url, ids["G1"])["posicao"]["l0"] == 2
		assert not errs, errs
	finally:
		pg.close()


def test_mover_feito_com_toque_cdp(gr, browser):
	url, gui, ids = gr
	_mostrar(url, ids, "G1")
	ctx = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True)
	pg = ctx.new_page()
	errs = []
	pg.on("pageerror", lambda e: errs.append(str(e)))
	reqs = _espiar(pg)
	try:
		pg.goto(url + "/novo/")
		pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
		pg.wait_for_selector("#vista-sw button", timeout=10_000)
		pg.locator("#vista-grupos").tap()
		pg.locator("#tab-montar .grp-row").nth(0).locator(".grp-open").tap()
		pg.wait_for_selector("#g-mover", timeout=10_000)
		pg.locator("#g-mover").tap()
		pg.wait_for_selector("#g-feito", timeout=5_000)
		vb0 = pg.evaluate("({ ...S.vb })")
		a, b = _xy(pg, 2, 4), _xy(pg, 3, 5)
		assert pg.evaluate("([x, y]) => { const e = document.elementFromPoint(x, y); return !!e && (e.id === 'board' || !!e.closest('#board')); }", [a["x"], a["y"]])
		cdp = ctx.new_cdp_session(pg)                                       # um dedo REAL: touchStart, touchMove ..., touchEnd sem pontos
		pt = lambda x, y: [{"x": x, "y": y, "id": 1}]  # noqa: E731
		cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": pt(a["x"], a["y"])})
		for i in range(1, 9):
			cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": pt(a["x"] + (b["x"] - a["x"]) * i / 8, a["y"] + (b["y"] - a["y"]) * i / 8)})
		cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
		pg.wait_for_timeout(100)
		assert pg.evaluate("S.vb") == vb0                                  # um dedo no grupo nao faz pan
		assert _movers(reqs) == []
		assert pg.evaluate("JSON.stringify(S.mover)") == '{"gid":"%s","dl":1,"dc":1}' % ids["G1"]
		# Depois de um arrasto por CDP o Chromium headless deixa de gerar ``click`` nos toques seguintes (medido sem nada deste
		# codigo: um pan do tabuleiro por CDP seguido de ``tap`` num botao nao da ``click``); «Feito» e por isso um clique.
		pg.locator("#g-feito").click()
		pg.wait_for_function("(gid) => grupo(gid).posicao.l0 === 3 && !S.busy", arg=ids["G1"], timeout=10_000)
		assert _grupo_api(url, ids["G1"])["posicao"]["c0"] == 5
		assert not errs, errs
	finally:
		_fechar(ctx)


def _rodar_falha(gui, gid):
	"""A direcao (+90 / -90) em que o grupo, na posicao atual, nao cabe rodado (None se couber nas duas)."""
	from src import grupos as GR
	from src import mesa as ME
	shown = ME.effective_positions(gui.pr)
	for d in (90, -90):
		if "error" in GR.rotate(gui.pr, gid, shown[gid], d, shown):
			return d
	return None


def test_rodar_sem_deslizar_e_nao_cabe(gr, browser):
	url, gui, ids = gr
	g2 = ids["G2"]
	_mostrar(url, ids, "G2", [3.0, 4.0])
	pg, errs = _abrir(browser, url)
	reqs = _espiar(pg)
	try:
		pg.locator("#tab-montar .grp-row").nth(1).locator(".grp-open").click()
		pg.wait_for_selector("#g-rodar-dir", timeout=10_000)
		for b in ("#g-rodar-dir", "#g-rodar-esq", "#g-mover"):
			assert pg.locator(b).bounding_box()["height"] >= 44, b
		from src import grupos as GR
		from src import mesa as ME
		shown = ME.effective_positions(gui.pr)
		esperado = GR.rotate(gui.pr, g2, shown[g2], 90, shown)
		if "error" in esperado:
			pytest.skip("o grupo nao cabe rodado +90 nesta posicao")
		pg.click("#g-rodar-dir")
		pg.wait_for_function("(gid) => grupo(gid).posicao.rot === 90 && !S.busy", arg=g2, timeout=10_000)
		assert _pos_no_cliente(pg, g2) == [esperado["l0"], esperado["c0"], 90]      # em torno do centro, sem deslizar
		g = _grupo_api(url, g2)
		assert g["rodado"] is True
		assert json.loads(next(b for m, u, b in reqs if u.endswith("/mover"))) == {"rodar": 90}
		pg.click("#g-rodar-esq")                                                        # volta a rot 0
		pg.wait_for_function("(gid) => grupo(gid).posicao.rot === 0 && !S.busy", arg=g2, timeout=10_000)
		# nao cabe: encostado ao fundo da grelha
		assert _post(url, f"/api/grupos/{g2}/mover", {"l0": 4, "c0": 1, "rot": 0})[0] == 200
		pg.wait_for_function("(gid) => grupo(gid).posicao.l0 === 4 && !S.busy", arg=g2, timeout=10_000)
		d = _rodar_falha(gui, g2)
		assert d is not None
		antes = _pos_no_cliente(pg, g2)
		pg.click("#g-rodar-dir" if d == 90 else "#g-rodar-esq")
		pg.wait_for_function("document.body.innerText.includes('Não cabe aqui rodado: move primeiro.')", timeout=10_000)
		assert _pos_no_cliente(pg, g2) == antes                                         # nada mudou
		assert _grupo_api(url, g2)["posicao"]["rot"] == 0
		assert not errs, errs
	finally:
		pg.close()


def test_desfazer_mover_e_rodar(gr, browser):
	url, gui, ids = gr
	_mostrar(url, ids, "G1")                                            # (2,4), rodado false
	_mostrar(url, ids, "G2", [3.0, 4.0])
	pg, errs = _abrir(browser, url)
	reqs = _espiar(pg)
	try:
		# mover pelo Ctrl+arrastar e desfazer pela faixa
		_arrastar(pg, (2, 4), (3, 5), ctrl=True)
		pg.wait_for_function("(gid) => grupo(gid).posicao.l0 === 3 && !S.busy", arg=ids["G1"], timeout=10_000)
		pg.click("#b-desfazer-ultimo")
		pg.wait_for_function("(gid) => grupo(gid).posicao.l0 === 2 && !S.busy", arg=ids["G1"], timeout=10_000)
		mv = _movers(reqs)
		assert len(mv) == 2 and (mv[1]["l0"], mv[1]["c0"], mv[1]["rot"], mv[1]["rodado"]) == (2, 4, 0, False)   # `anterior`, rodado explicito
		assert _grupo_api(url, ids["G1"])["rodado"] is False
		assert pg.locator("#m-ultimo").count() == 0                        # um nivel: gasto
		# rodar e desfazer por Ctrl+Z
		if _rodar_falha(gui, ids["G2"]) == 90:
			pytest.skip("G2 nao cabe rodado +90 aqui")
		pg.click("#grp-voltar")
		pg.locator("#tab-montar .grp-row").nth(1).locator(".grp-open").click()
		pg.click("#g-rodar-dir")
		pg.wait_for_function("(gid) => grupo(gid).posicao.rot === 90 && !S.busy", arg=ids["G2"], timeout=10_000)
		assert _grupo_api(url, ids["G2"])["rodado"] is True
		pg.keyboard.press("Control+z")
		pg.wait_for_function("(gid) => grupo(gid).posicao.rot === 0 && !S.busy", arg=ids["G2"], timeout=10_000)
		g = _grupo_api(url, ids["G2"])
		assert g["rodado"] is False and g["posicao"]["rot"] == 0           # repoe o valor anterior do `rodado` (C1)
		assert _movers(reqs)[-1]["rodado"] is False
		assert not errs, errs
	finally:
		pg.close()


def test_ver_no_tabuleiro_de_grupo_mostrado_nao_faz_post(gr, browser):
	url, gui, ids = gr
	_mostrar(url, ids, "G1")
	pg, errs = _abrir(browser, url)
	reqs = _espiar(pg)
	try:
		pg.locator("#tab-montar .grp-row").nth(0).locator(".grp-open").click()
		pg.wait_for_selector("#g-mostrar", timeout=10_000)
		assert pg.inner_text("#g-mostrar").strip() == "Ver no tabuleiro"
		pg.click("#g-mostrar")                                              # grupo ja mostrado: so showCell
		pg.click("#grp-voltar")
		pg.locator("#tab-montar .grp-row").nth(0).locator(".grp-mostrar").click()   # tambem o botao da lista
		pg.wait_for_timeout(300)
		assert [r for r in reqs if "/api/grupos/" in r[1]] == []            # nenhum POST
		assert pg.locator("#m-ultimo").count() == 0                         # e «Mostrar» continua fora do desfazer (C2)
		assert not errs, errs
	finally:
		pg.close()


def test_levar_manda_rodado_false_e_desfaz(gr, browser):
	url, gui, ids = gr
	_mostrar(url, ids, "G1")
	assert _post(url, f"/api/grupos/{ids['G1']}/mover", {"l0": 4, "c0": 1, "rot": 0, "rodado": True})[0] == 200
	assert _grupo_api(url, ids["G1"])["rodado"] is True
	pg, errs = _abrir(browser, url)
	reqs = _espiar(pg)
	try:
		pg.locator("#tab-montar .grp-row").nth(0).locator(".grp-open").click()
		pg.click("#g-levar")
		pg.wait_for_function("(gid) => grupo(gid).posicao.l0 === 2 && !S.busy", arg=ids["G1"], timeout=10_000)
		mv = _movers(reqs)
		assert len(mv) == 1 and (mv[0]["l0"], mv[0]["c0"], mv[0]["rot"]) == (2, 4, 0) and mv[0]["rodado"] is False
		assert _grupo_api(url, ids["G1"])["rodado"] is False
		pg.wait_for_selector("#b-desfazer-ultimo", timeout=5_000)           # desfazivel pela `anterior`
		pg.click("#b-desfazer-ultimo")
		pg.wait_for_function("(gid) => grupo(gid).posicao.l0 === 4 && !S.busy", arg=ids["G1"], timeout=10_000)
		mv = _movers(reqs)
		assert (mv[1]["l0"], mv[1]["c0"], mv[1]["rodado"]) == (4, 1, True)
		assert _grupo_api(url, ids["G1"])["rodado"] is True
		assert not errs, errs
	finally:
		pg.close()


def test_criterio_14_arrastar_com_32_grupos_sem_frames_lentos(gr, browser):
	"""Criterio 14: 60 passos de arrasto com 32 grupos mostrados, 0 frames acima de 25 ms (Chromium headless). Os 32 grupos
	vem de uma resposta de /api/grupos fabricada (o desenho e o arrasto sao do cliente); o POST do fim nao chega ao servidor."""
	url, gui, ids = gr
	_mostrar(url, ids, "G1")
	base = _grupo_api(url, ids["G1"])
	grupos = []
	for i in range(32):
		g = json.loads(json.dumps(base))
		g["id"] = f"G{9000 + i}"
		l, c = 1 + (i % 4), 1 + (i // 4) % 6
		g["posicao"] = {"l0": l, "c0": c, "rot": 0, "mirror": False, "origem": "mesa"}
		g["footprint"] = [[l, c]]
		g["mostrado"], g["sobreposto"], g["lugar_provavel"] = True, None, None
		grupos.append(g)
	grupos[0]["id"] = ids["G1"]
	fake = {"versao": 1, "n_grupos": 32, "n_pecas": 32, "n_mostrados": 32, "grupos": grupos, "aviso": []}
	pg = browser.new_page(viewport={"width": 1366, "height": 768})
	pg.route("**/api/grupos", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(fake)))
	pg.route("**/api/grupos/*/mover", lambda r: r.fulfill(status=409, content_type="application/json", body=json.dumps({"error": "teste"})))
	try:
		pg.goto(url + "/novo/")
		pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
		pg.wait_for_selector("#vista-sw button", timeout=10_000)
		pg.click("#vista-grupos")
		pg.wait_for_selector("#lyr-grupos .grupo", timeout=10_000)
		assert pg.locator("#lyr-grupos > .grupo").count() == 32
		pg.evaluate("""() => { window.__ft = []; window.__stop = false; let last = 0;
			const loop = (t) => { if (last) window.__ft.push(t - last); last = t; if (!window.__stop) requestAnimationFrame(loop); };
			requestAnimationFrame(loop); }""")
		a = _xy(pg, 1, 1)
		pg.keyboard.down("Control")
		pg.mouse.move(a["x"], a["y"])
		pg.mouse.down()
		for i in range(1, 61):
			pg.mouse.move(a["x"] + 3 * i, a["y"] + 2 * i)
		assert pg.get_attribute(f"#lyr-grupos [data-grupo='{ids['G1']}']", "transform")          # o arrasto esta mesmo a andar
		pg.mouse.up()
		pg.keyboard.up("Control")
		pg.wait_for_timeout(100)
		ft = pg.evaluate("(() => { window.__stop = true; return window.__ft; })()")
		lentos = [round(x, 1) for x in ft if x > 25]
		print(f"criterio 14: {len(ft)} frames, max {max(ft):.1f} ms, mediana {sorted(ft)[len(ft) // 2]:.1f} ms, acima de 25 ms: {lentos}")
		assert len(ft) >= 20 and lentos == [], lentos
	finally:
		_fechar(pg.context)
