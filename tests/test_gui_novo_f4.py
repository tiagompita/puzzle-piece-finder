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
import os
import re
import urllib.request

import pytest

pytestmark = pytest.mark.slow
pytest.importorskip("fastapi")
pytest.importorskip("uvicorn")
sync_api = pytest.importorskip("playwright.sync_api")

from src import mesa  # noqa: E402
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
	pg.wait_for_function("!!S.grupos", timeout=30_000)                  # os grupos chegam em fundo, depois do «pronto»
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
		# F4b (a): G1 (lugar provavel fiavel) ja esta no tabuleiro sozinho; G2 (sem lugar provavel) continua so na lista
		assert pg.locator("#lyr-grupos [data-grupo]").count() == 1
		assert pg.locator(f"#lyr-grupos [data-grupo='{ids['G1']}']").count() == 1
		assert not os.path.exists(mesa.mesa_path(gui.pr))
		seq0 = gui.seq
		with pg.expect_request(lambda r: r.url.endswith(f"/api/grupos/{ids['G2']}/mostrar") and r.method == "POST") as rq:
			pg.locator("#tab-montar .grp-row").nth(1).locator(".grp-mostrar").click()
		body = json.loads(rq.value.post_data)
		assert len(body["centro"]) == 2 and all(isinstance(v, (int, float)) for v in body["centro"])
		pg.wait_for_selector(f"#lyr-grupos [data-grupo='{ids['G2']}']", timeout=10_000)
		assert pg.locator("#lyr-grupos [data-grupo]").count() == 2
		d = json.loads(urllib.request.urlopen(url + "/api/grupos").read())
		g2 = next(g for g in d["grupos"] if g["id"] == ids["G2"])
		assert g2["mostrado"] and g2["posicao"]["origem"] == "mesa" and not g2["automatico"]
		assert sum(1 for _ in open(mesa.mesa_path(gui.pr), encoding="utf-8")) == 1       # so o «Mostrar» do Tiago escreve
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


def test_todos_os_grupos_mostrados_tem_imagem(gr, browser):
	"""F4b (b), decisao do Tiago 2026-11-24: a imagem aparece em todos os grupos mostrados, nao so no escolhido (a
	sombra e o fundo violeta continuam so no escolhido); chega em fundo, depois do «pronto»."""
	url, gui, ids = gr
	_mostrar_todos(url, ids)
	pg, errs = _abrir(browser, url)
	try:
		g1, g2 = ids["G1"], ids["G2"]
		pg.wait_for_selector(f"#lyr-grupos [data-grupo='{g2}']", timeout=10_000)
		pg.wait_for_function("document.querySelectorAll('#lyr-grupos image.grupo-img[href]').length === 2", timeout=15_000)
		assert pg.locator("#lyr-grupos .grupo.tenue").count() == 2                  # nenhum escolhido: contornos tenues, mas com imagem
		for g in (g1, g2):
			href = pg.get_attribute(f"#lyr-grupos [data-grupo='{g}'] image.grupo-img", "href")
			assert href.startswith(f"/api/grupos/{g}.png?rot=0")
		pg.locator("#tab-montar .grp-row").nth(0).locator(".grp-open").click()
		pg.wait_for_selector(f"#lyr-grupos [data-grupo='{g1}'].escolhido", timeout=10_000)
		assert pg.locator("#lyr-grupos image.grupo-img[href]").count() == 2         # o escolhido nao tira a imagem aos outros
		assert pg.locator(f"#lyr-grupos [data-grupo='{g1}'] .grupo-sombra").count() == 1
		assert pg.locator(f"#lyr-grupos [data-grupo='{g2}'] .grupo-sombra").count() == 0
		assert pg.locator(f"#lyr-grupos [data-grupo='{g2}']").get_attribute("class").split().count("tenue") == 1
		pg.click("#grp-voltar")                                                          # a lista; o escolhido deixa de o ser
		pg.wait_for_selector("#tab-montar .grp-row", timeout=10_000)
		assert pg.locator("#lyr-grupos image.grupo-img[href]").count() == 2
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
	assert _post(url, f"/api/grupos/{ids['G1']}/mover", {"l0": 4, "c0": 6, "rot": 0})[0] == 200    # fora do lugar provavel (senao e ele)
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
		pg.wait_for_selector("#lyr-grupos [data-grupo]", timeout=10_000)                         # G1 mostrado sozinho (F4b a)
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
		pg.wait_for_function("!!S.grupos", timeout=30_000)
		assert pg.inner_text("#vista-grupos").replace("\xa0", " ") == "Grupos soltos · 0"
		pg.click("#vista-grupos")
		assert "Não há grupos soltos." in pg.inner_text("#tab-montar")
		assert "em grupos soltos" not in pg.inner_text("#progress-txt")
	finally:
		pg.close()


def test_sobreposto_visivel(gr, browser):
	url, gui, ids = gr
	st, r = _post(url, f"/api/grupos/{ids['G1']}/mover", {"l0": 2, "c0": 4, "rot": 0})     # posicao propria (um grupo so derivado desaparece)
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
		assert pg.locator("#lyr-grupos [data-grupo]").count() == 1                          # G1, sozinho (F4b a)
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
		pg.wait_for_function("!!S.grupos", timeout=30_000)
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
		# Do harness, nao do codigo (o revisor reproduziu-o numa pagina em branco): depois de um arrasto por CDP perde-se o 1.o
		# toque seguinte (o 2.o ``tap()`` ja da ``click``); «Feito» e por isso um clique.
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
		pg.wait_for_function("(gid) => grupo(gid).posicao.l0 === 4 && grupo(gid).posicao.c0 === 1 && !S.busy", arg=g2, timeout=10_000)
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
		g["footprint"] = [[l, c], [l, c + 1]] if i % 2 else [[l, c]]            # metade dos grupos com mais de uma celula
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
		pg.wait_for_function("!!S.grupos", timeout=30_000)
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
		for i in range(1, 61):                                              # passos de ~30 px: atravessa >= 10 celulas
			pg.mouse.move(a["x"] + 30 * i, a["y"] + 10 * i)
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


# ---------------------------------------------------------------- correcoes da revisao do implementer (M1-M4)
SEL = "#lyr-grupos [data-grupo='%s']"


def test_m1_escape_a_meio_do_arrasto_no_mover_nao_da_erro(gr, browser):
	url, gui, ids = gr
	_mostrar(url, ids, "G1")
	pg, errs = _abrir(browser, url)
	reqs = _espiar(pg)
	try:
		pg.locator("#tab-montar .grp-row").nth(0).locator(".grp-open").click()
		pg.click("#g-mover")
		_arrastar(pg, (2, 4), (3, 5), soltar=False)
		pg.keyboard.press("Escape")                                         # S.mover passa a null com o arrasto a meio
		pg.mouse.up()
		pg.wait_for_timeout(150)
		assert errs == []
		assert pg.get_attribute(SEL % ids["G1"], "transform") is None
		assert _pos_no_cliente(pg, ids["G1"]) == [2, 4, 0] and _movers(reqs) == []
	finally:
		pg.close()


def test_m1_recarga_a_meio_do_arrasto_no_mover_nao_da_erro(gr, browser):
	url, gui, ids = gr
	_mostrar(url, ids, "G1")
	pg, errs = _abrir(browser, url)
	try:
		pg.locator("#tab-montar .grp-row").nth(0).locator(".grp-open").click()
		pg.click("#g-mover")
		_arrastar(pg, (2, 4), (3, 5), soltar=False)
		pg.evaluate("S.mover = null; drawGrupos()")                          # o que um loadGrupos faria se o grupo desaparecesse
		pg.mouse.up()
		pg.wait_for_timeout(150)
		assert errs == []
		assert pg.get_attribute(SEL % ids["G1"], "transform") is None
	finally:
		pg.close()


def test_m2_segundo_dedo_no_grupo_nao_arrasta_no_mover(gr, browser):
	url, gui, ids = gr
	_mostrar(url, ids, "G1")
	ctx = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True)
	pg = ctx.new_page()
	try:
		pg.goto(url + "/novo/")
		pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
		pg.wait_for_selector("#vista-sw button", timeout=10_000)
		pg.wait_for_function("!!S.grupos", timeout=30_000)
		pg.evaluate("escolherGrupo(%r); entrarMover(%r)" % (ids["G1"], ids["G1"]))
		pg.wait_for_selector("#g-feito", timeout=5_000)
		f1, g = _xy(pg, 4, 1), _xy(pg, 2, 4)
		cdp = ctx.new_cdp_session(pg)
		send = lambda t, pts: cdp.send("Input.dispatchTouchEvent", {"type": t, "touchPoints": pts})  # noqa: E731
		send("touchStart", [{"x": f1["x"], "y": f1["y"], "id": 1}])
		send("touchStart", [{"x": f1["x"], "y": f1["y"], "id": 1}, {"x": g["x"], "y": g["y"], "id": 2}])
		for i in range(1, 9):
			send("touchMove", [{"x": f1["x"] - 6 * i, "y": f1["y"] + 6 * i, "id": 1}, {"x": g["x"] + 8 * i, "y": g["y"] + 8 * i, "id": 2}])
		send("touchEnd", [])
		pg.wait_for_timeout(200)
		assert pg.evaluate("JSON.stringify(S.mover)") == '{"gid":"%s","dl":0,"dc":0}' % ids["G1"]   # o 2.o dedo nao agarrou o grupo
		assert pg.get_attribute(SEL % ids["G1"], "transform") is None
	finally:
		_fechar(ctx)


def test_m3_pointerup_perdido_nao_mata_o_tabuleiro(gr, browser):
	url, gui, ids = gr
	_mostrar(url, ids, "G1")
	ctx = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True)
	pg = ctx.new_page()
	try:
		pg.goto(url + "/novo/")
		pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
		pg.wait_for_selector("#vista-sw button", timeout=10_000)
		pg.wait_for_function("!!S.grupos", timeout=30_000)
		pg.evaluate("escolherGrupo(%r)" % ids["G1"])
		pg.wait_for_selector(SEL % ids["G1"], timeout=10_000)
		_arrastar(pg, (2, 4), (3, 5), ctrl=True, soltar=False)
		assert pg.evaluate("arrasto !== null")
		pg.evaluate("arrasto.id = 987654")                                   # o pointerup deste ponteiro ja nao o encontra: «perdido»
		pg.mouse.up()
		pg.keyboard.up("Control")
		assert pg.evaluate("arrasto !== null")
		vb0 = pg.evaluate("({ ...S.vb })")
		a, b = _xy(pg, 4, 1), _xy(pg, 4, 2)
		cdp = ctx.new_cdp_session(pg)
		send = lambda t, pts: cdp.send("Input.dispatchTouchEvent", {"type": t, "touchPoints": pts})  # noqa: E731
		send("touchStart", [{"x": a["x"], "y": a["y"], "id": 1}])
		for i in range(1, 9):
			send("touchMove", [{"x": a["x"] + (b["x"] - a["x"]) * i / 8, "y": a["y"], "id": 1}])
		send("touchEnd", [])
		pg.wait_for_timeout(150)
		assert pg.evaluate("arrasto") is None                                # o dedo primario novo repoe o estado
		assert pg.evaluate("S.vb.x") != vb0["x"]                              # e o pan de um dedo funciona
		assert pg.get_attribute(SEL % ids["G1"], "transform") is None        # o grupo voltou onde estava
	finally:
		_fechar(ctx)


def test_m4_busy_no_inicio_e_a_meio_do_arrasto(gr, browser):
	url, gui, ids = gr
	_mostrar(url, ids, "G1")
	pg, errs = _abrir(browser, url, vista=False)
	reqs = _espiar(pg)
	try:
		pg.wait_for_selector(SEL % ids["G1"], timeout=10_000)
		pg.evaluate("S.busy = true")
		_arrastar(pg, (2, 4), (3, 5), ctrl=True)                            # a gravar: nem arranca
		assert pg.get_attribute(SEL % ids["G1"], "transform") is None
		pg.evaluate("S.busy = false")
		_arrastar(pg, (2, 4), (3, 5), ctrl=True, soltar=False)
		pg.evaluate("S.busy = true")                                          # passa a gravar a meio
		pg.mouse.up()
		pg.keyboard.up("Control")
		pg.wait_for_timeout(200)
		pg.evaluate("S.busy = false")
		assert pg.get_attribute(SEL % ids["G1"], "transform") is None
		assert "Espera um momento" in pg.inner_text("#toast")
		assert _movers(reqs) == [] and _pos_no_cliente(pg, ids["G1"]) == [2, 4, 0]
		assert not errs, errs
	finally:
		pg.close()


def test_celula_marcada_recusada_e_cheia_na_foto_aceite(gr, browser):
	url, gui, ids = gr
	_mostrar(url, ids, "G1")
	st, r = _post(url, "/api/confirm", {"acao": "cell_full", "cell": [3, 5]})
	assert st == 200, r
	pg, errs = _abrir(browser, url, vista=False)
	reqs = _espiar(pg)
	try:
		pg.wait_for_selector(SEL % ids["G1"], timeout=10_000)
		_arrastar(pg, (2, 4), (3, 5), ctrl=True)
		pg.wait_for_timeout(200)
		assert "marcada como montada" in pg.inner_text("#toast")
		assert _movers(reqs) == [] and _pos_no_cliente(pg, ids["G1"]) == [2, 4, 0]
		# «cheia na foto» (duvida) nao bloqueia: o cliente deixa passar e o servidor aceita (a celula esta vazia para ele)
		pg.evaluate("S.board.cells[2][3] = { estado: 'ocupada_legado', fonte: 'foto', peca_id: null }")      # (3,4): so ``cheia na foto``
		_arrastar(pg, (2, 4), (3, 4), ctrl=True)
		pg.wait_for_function("(gid) => grupo(gid).posicao.l0 === 3 && !S.busy", arg=ids["G1"], timeout=10_000)
		assert len(_movers(reqs)) == 1
		assert not errs, errs
	finally:
		pg.close()


def test_ctrl_clique_sem_movimento_nao_faz_post(gr, browser):
	url, gui, ids = gr
	_mostrar(url, ids, "G1")
	pg, errs = _abrir(browser, url, vista=False)
	reqs = _espiar(pg)
	try:
		pg.wait_for_selector(SEL % ids["G1"], timeout=10_000)
		a = _xy(pg, 2, 4)
		pg.keyboard.down("Control")
		pg.mouse.click(a["x"], a["y"])
		pg.keyboard.up("Control")
		pg.wait_for_timeout(200)
		assert _movers(reqs) == [] and pg.get_attribute(SEL % ids["G1"], "transform") is None
		assert not errs, errs
	finally:
		pg.close()


# ============================================================================ etapa 3: fixar e soltar (escrito ANTES do codigo)
@pytest.fixture
def gr90(tmp_path):
	"""Como ``gr`` mas com G1 a rodar 90 no candidato (2,4): as vizinhas discordam."""
	from src.query import run_query
	pr, ids = _board_project(tmp_path, cand1=_cand((2, 4), 90), cand2=_cand((3, 3), margin=1.0))
	run_query(pr, use_image=False)
	gui = SV.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp_path / "uploads"), log=None)
	url, server, th = _serve(gui)
	yield url, gui, ids
	server.should_exit = True
	th.join(10)


def _fixars(reqs):
	return [(u, b) for m, u, b in reqs if u.endswith("/fixar")]


def _escolher(pg, n=0):
	pg.locator("#tab-montar .grp-row").nth(n).locator(".grp-open").click()
	pg.wait_for_selector("#g-barra", timeout=10_000)


def _ids_no_grupos(url):
	return [g["id"] for g in json.loads(urllib.request.urlopen(url + "/api/grupos").read())["grupos"]]


def test_fixar_com_confirmacao_de_um_clique(gr, browser):
	url, gui, ids = gr
	_mostrar(url, ids, "G1")
	pg, errs = _abrir(browser, url)
	reqs = _espiar(pg)
	try:
		_escolher(pg)
		assert pg.locator("#g-fixar").inner_text().strip() == "Fixar aqui"
		assert pg.locator("#g-fixar").bounding_box()["height"] >= 44
		pg.click("#g-fixar")
		pg.wait_for_selector("#g-confirma", timeout=5_000)
		assert pg.inner_text("#g-confirma-txt") == "Fixar o grupo de 1 peça aqui? Confirma na mesa que está nesta rotação."
		assert _fixars(reqs) == []                                          # so a confirmacao: nada gravado
		pg.click("#g-fixar-nao")
		assert pg.locator("#g-confirma").count() == 0 and pg.locator("#g-fixar").count() == 1 and _fixars(reqs) == []
		pg.click("#g-fixar")
		pg.keyboard.press("Escape")                                         # Escape tambem cancela
		assert pg.locator("#g-confirma").count() == 0 and _fixars(reqs) == []
		pg.click("#g-fixar")
		pg.click("#g-fixar-sim")
		pg.wait_for_selector("#g-fixado", timeout=15_000)
		fx = _fixars(reqs)
		assert len(fx) == 1 and json.loads(fx[0][1]) == {}                  # corpo vazio: o servidor ignora-o
		assert ids["G1"] not in _ids_no_grupos(url)
		t = pg.inner_text("#g-fixado")
		assert "Grupo de 1 peça fixado." in t and "A rotação está confirmada." in t and "outra rotação" not in t
		assert pg.locator("#lyr-grupos .grupo-aviso").count() == 0
		b = json.loads(urllib.request.urlopen(url + "/api/board").read())
		assert b["cells"][1][3]["estado"] == "colocada"                      # (2,4) passou a peca colocada
		assert not errs, errs
	finally:
		pg.close()


def test_sobreposto_desliga_fixar_aqui_com_a_razao(gr, browser):
	url, gui, ids = gr
	assert _post(url, f"/api/grupos/{ids['G1']}/mover", {"l0": 2, "c0": 4, "rot": 0})[0] == 200
	assert _post(url, "/api/confirm", {"acao": "place", "piece": ids["W"], "cell": [2, 4], "theta_deg": -PSI_W, "origin": "manual"})[0] == 200
	pg, errs = _abrir(browser, url)
	reqs = _espiar(pg)
	try:
		_escolher(pg)
		assert pg.locator("#g-fixar").is_disabled()
		t = pg.inner_text("#g-sobreposto").lower()
		assert "já tem uma peça" in t or "por cima" in t                     # a razao, em palavras
		pg.locator("#g-fixar").click(force=True)
		pg.wait_for_timeout(200)
		assert pg.locator("#g-confirma").count() == 0 and _fixars(reqs) == []
		assert not errs, errs
	finally:
		pg.close()


def test_aviso_ambar_esta_peca_diz_outra_rotacao_e_desfazer(gr90, browser):
	url, gui, ids = gr90
	_mostrar(url, ids, "G1")
	assert _post(url, f"/api/grupos/{ids['G1']}/mover", {"l0": 2, "c0": 4, "rot": 90, "rodado": False})[0] == 200
	pg, errs = _abrir(browser, url)
	reqs = _espiar(pg)
	try:
		_escolher(pg)
		pg.click("#g-fixar")
		pg.click("#g-fixar-sim")
		pg.wait_for_selector("#g-fixado", timeout=15_000)
		t = pg.inner_text("#g-fixado")
		assert "Esta peça diz outra rotação" in t and "As peças ao lado dizem outra rotação." in t
		assert "por confirmar" in t and "A rotação está confirmada" not in t       # a_confirmar em palavras simples
		assert pg.get_attribute("#g-fixado", "data-confianca") == "a_confirmar"
		cel = pg.locator("#lyr-grupos .grupo-aviso .grupo-cel")
		assert cel.count() == 1                                              # o contorno ambar na celula da peca que discorda
		assert pg.evaluate("getComputedStyle(document.querySelector('#lyr-grupos .grupo-aviso .grupo-cel')).stroke") != "none"
		hr = pg.evaluate("S.hr")
		assert abs(float(cel.get_attribute("x")) - 3.0) < 1e-3 and abs(float(cel.get_attribute("y")) - hr) < 1e-3   # coluna 4, linha 2
		for rx in PROIBIDO:
			assert not re.search(rx, _visivel(pg)), rx                       # nunca ids
		pg.click("#g-fixado-desfazer")                                       # o desfazer e o unanchor do /api/confirm
		pg.wait_for_function("document.querySelector('#g-fixado') === null && !S.busy", timeout=10_000)
		assert any(u.endswith("/api/confirm") and json.loads(b)["acao"] == "unanchor" for m, u, b in reqs)
		assert ids["G1"] in _ids_no_grupos(url)                              # solto outra vez, onde estava fixado (Q10 a)
		g = _grupo_api(url, ids["G1"])
		assert g["mostrado"] and (g["posicao"]["l0"], g["posicao"]["c0"], g["posicao"]["rot"]) == (2, 4, 90)
		assert pg.locator("#lyr-grupos .grupo-aviso").count() == 0
		assert not errs, errs
	finally:
		pg.close()


def test_desfazer_fixar_pela_faixa_e_ctrl_z(gr, browser):
	url, gui, ids = gr
	_mostrar(url, ids, "G1")
	pg, errs = _abrir(browser, url)
	try:
		_escolher(pg)
		pg.click("#g-fixar")
		pg.click("#g-fixar-sim")
		pg.wait_for_selector("#g-fixado", timeout=15_000)
		assert pg.locator("#m-ultimo").count() == 0                          # o cartao ja traz o «Desfazer»: nao ha duas faixas
		pg.click("#g-fixado-ok")                                             # «Está bem» fecha o cartao
		assert pg.locator("#g-fixado").count() == 0
		pg.keyboard.press("Control+z")
		pg.wait_for_function("(gid) => !!grupo(gid) && !S.busy", arg=ids["G1"], timeout=15_000)
		g = _grupo_api(url, ids["G1"])
		assert g["mostrado"] and (g["posicao"]["l0"], g["posicao"]["c0"]) == (2, 4)
		assert not errs, errs
	finally:
		pg.close()


def test_tirar_o_grupo_inteiro_deixa_o_grupo_onde_estava_e_desfaz(gr, browser):
	url, gui, ids = gr
	_mostrar(url, ids, "G1")
	st, r = _post(url, f"/api/grupos/{ids['G1']}/fixar", {})
	assert st == 200, r
	pg, errs = _abrir(browser, url, vista=False)
	try:
		assert pg.locator("#lyr-grupos [data-grupo]").count() == 0           # fixado: ja nao e solto
		a = _xy(pg, 2, 4)
		pg.mouse.click(a["x"], a["y"])
		pg.wait_for_selector("#p-tirar", timeout=10_000)
		assert pg.inner_text("#p-tirar").strip() == "Tirar o grupo inteiro do lugar (1 peça)"
		pg.click("#p-tirar")
		pg.wait_for_selector(f"#lyr-grupos [data-grupo='{ids['G1']}']", timeout=15_000)   # solto, no mesmo sitio (Q10 a)
		g = _grupo_api(url, ids["G1"])
		assert g["mostrado"] and (g["posicao"]["l0"], g["posicao"]["c0"]) == (2, 4)
		pg.wait_for_selector("#b-desfazer-ultimo", timeout=10_000)
		pg.click("#b-desfazer-ultimo")
		pg.wait_for_function("(gid) => !grupo(gid)", arg=ids["G1"], timeout=15_000)      # fixado outra vez
		assert ids["G1"] not in _ids_no_grupos(url)
		assert not errs, errs
	finally:
		pg.close()


def test_b1_recarga_a_meio_do_ctrl_arrastar_mantem_o_deslocamento(gr, browser):
	url, gui, ids = gr
	_mostrar(url, ids, "G1")
	pg, errs = _abrir(browser, url, vista=False)
	reqs = _espiar(pg)
	try:
		pg.wait_for_selector(SEL % ids["G1"], timeout=10_000)
		_arrastar(pg, (2, 4), (3, 5), ctrl=True, soltar=False)
		antes = pg.get_attribute(SEL % ids["G1"], "transform")
		assert antes
		pg.evaluate("loadGrupos()")                                           # o que um grupos_changed de outro cliente faz
		pg.wait_for_function("!S.busy", timeout=5_000)
		pg.wait_for_timeout(300)
		assert pg.get_attribute(SEL % ids["G1"], "transform") == antes       # o desenho nao salta para tras a meio
		pg.mouse.up()
		pg.keyboard.up("Control")
		pg.wait_for_function("(gid) => grupo(gid).posicao.l0 === 3 && !S.busy", arg=ids["G1"], timeout=10_000)
		assert len(_movers(reqs)) == 1 and not errs
	finally:
		pg.close()


def test_b2_encaixe_pela_celula_debaixo_do_ponteiro(gr, browser):
	url, gui, ids = gr
	_mostrar(url, ids, "G1")                                                  # (2,4); (2,5) livre
	pg, errs = _abrir(browser, url, vista=False)
	reqs = _espiar(pg)
	try:
		pg.wait_for_selector(SEL % ids["G1"], timeout=10_000)
		# o ponteiro cai perto do bordo direito da celula (2,4) e atravessa para (2,5) com 0,15 de celula: um arredondamento do
		# deslocamento daria 0 colunas, a celula debaixo do ponteiro da 1
		_arrastar(pg, (2, 4.45), (2, 4.6), ctrl=True)
		pg.wait_for_function("(gid) => grupo(gid).posicao.c0 === 5 && !S.busy", arg=ids["G1"], timeout=10_000)
		assert [(m["l0"], m["c0"]) for m in _movers(reqs)] == [(2, 5)]
		# e o inverso: sair da celula e voltar a de origem nao faz POST
		n = len(_movers(reqs))
		_arrastar(pg, (2, 5), (2, 7), ctrl=True, soltar=False)
		a = _xy(pg, 2, 5.2)
		pg.mouse.move(a["x"], a["y"])
		pg.mouse.up()
		pg.keyboard.up("Control")
		pg.wait_for_timeout(300)
		assert len(_movers(reqs)) == n and pg.get_attribute(SEL % ids["G1"], "transform") is None
		assert not errs, errs
	finally:
		pg.close()


@pytest.mark.parametrize("vp", [(1366, 768), (390, 844)])
def test_fixar_sem_scroll_horizontal_nem_ids_em_todos_os_estados(gr90, browser, vp):
	url, gui, ids = gr90
	_mostrar(url, ids, "G1")
	assert _post(url, f"/api/grupos/{ids['G1']}/mover", {"l0": 2, "c0": 4, "rot": 90, "rodado": False})[0] == 200
	_mostrar(url, ids, "G2", [3.0, 2.0])
	pg, errs = _abrir(browser, url, vp=vp)

	def ver(estado):
		assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), (vp, estado)
		assert pg.evaluate("document.body.scrollWidth <= window.innerWidth + 1"), (vp, estado)
		t = _visivel(pg)
		for rx in PROIBIDO:
			assert not re.search(rx, t), (rx, vp, estado)
		small = pg.evaluate("""[...document.querySelectorAll('#vista-sw button, #tab-montar button')]
			.filter(b => b.offsetParent !== null && b.getBoundingClientRect().height < 43.5).map(b => b.id || b.className)""")
		assert small == [], (vp, estado, small)
	try:
		ver("lista")
		pg.locator("#tab-montar .grp-row").nth(0).locator(".grp-open").click()
		pg.wait_for_selector("#g-barra", timeout=10_000)
		ver("grupo mostrado")
		pg.click("#g-mover"); pg.wait_for_selector("#g-feito")
		ver("mover")
		pg.click("#g-cancelar"); pg.wait_for_selector("#g-fixar")
		pg.click("#g-fixar"); pg.wait_for_selector("#g-confirma")
		ver("confirmacao")
		pg.click("#g-fixar-sim"); pg.wait_for_selector("#g-fixado", timeout=15_000)
		ver("aviso ambar")
		assert not errs, errs
	finally:
		pg.close()


def test_o_alvo_das_sugestoes_fica_por_cima_do_grupo(gr, browser):
	url, gui, ids = gr
	pg, errs = _abrir(browser, url)
	try:
		ordem = pg.evaluate("[...document.querySelectorAll('#board > g')].map(g => g.id)")
		assert ordem.index("lyr-grupos") < ordem.index("lyr-seguinte") < ordem.index("lyr-alvo")
	finally:
		pg.close()


# ============================================================================ M3 e M4 (decisões do Tiago, 2026-11-19)
def _ancora(gui, gid):
	from src.state import Project
	return dict(Project.open(gui.path).sections[gid].anchor)


def test_m4_desfazer_fixar_depois_de_rodar_volta_a_dar_tiago(gr, browser):
	"""Rodar → Fixar (tiago, confirmado) → «Desfazer» do cartão = ``unanchor`` + «Mover» para o mesmo sítio com
	``rodado: true``: o grupo fica solto, no mesmo sítio e rotação, e voltar a fixar dá tiago / confirmado."""
	url, gui, ids = gr
	g1 = ids["G1"]
	_mostrar(url, ids, "G1")
	assert _post(url, f"/api/grupos/{g1}/mover", {"l0": 4, "c0": 6, "rot": 0})[0] == 200    # sem vizinhas
	pg, errs = _abrir(browser, url)
	reqs = _espiar(pg)
	try:
		_escolher(pg)
		pg.click("#g-rodar-dir")
		pg.wait_for_function("(gid) => grupo(gid).rodado && !S.busy", arg=g1, timeout=10_000)
		pg.click("#g-fixar"); pg.click("#g-fixar-sim")
		pg.wait_for_selector("#g-fixado", timeout=15_000)
		assert pg.get_attribute("#g-fixado", "data-confianca") == "confirmado"
		a = _ancora(gui, g1)
		assert a["rot_fonte"] == "tiago"
		pg.wait_for_function("!S.busy", timeout=15_000)                    # com S.busy o botao do cartao esta desligado (A1b): espera-se para o poder clicar
		n0 = len(reqs)
		pg.click("#g-fixado-desfazer")
		pg.wait_for_function("(gid) => !!grupo(gid) && !S.busy && document.querySelector('#g-fixado') === null", arg=g1, timeout=15_000)
		feitos = [(u.split("/api/")[1], json.loads(b)) for m, u, b in reqs[n0:]]
		assert feitos == [("confirm", {"acao": "unanchor", "section": g1}),
						  (f"grupos/{g1}/mover", {"l0": a["l0"], "c0": a["c0"], "rot": a["rot"], "rodado": True})], feitos
		g = _grupo_api(url, g1)
		assert g["rodado"] is True and (g["posicao"]["l0"], g["posicao"]["c0"], g["posicao"]["rot"]) == (a["l0"], a["c0"], a["rot"])
		st, d = _post(url, f"/api/grupos/{g1}/fixar", {})
		assert st == 200 and d["rot_fonte"] == "tiago" and d["confianca"] == "confirmado", d
		assert not errs, errs
	finally:
		pg.close()


def test_m4_desfazer_fixar_sem_rodar_so_faz_unanchor(gr, browser):
	"""Sem «Rodar» (rot_fonte programa) a inversa continua a ser só o ``unanchor``."""
	url, gui, ids = gr
	_mostrar(url, ids, "G1")
	pg, errs = _abrir(browser, url)
	reqs = _espiar(pg)
	try:
		_escolher(pg)
		pg.click("#g-fixar"); pg.click("#g-fixar-sim")
		pg.wait_for_selector("#g-fixado", timeout=15_000)
		pg.wait_for_function("!S.busy", timeout=15_000)                    # com S.busy o botao do cartao esta desligado (A1b): espera-se para o poder clicar
		n0 = len(reqs)
		pg.click("#g-fixado-desfazer")
		pg.wait_for_function("(gid) => !!grupo(gid) && !S.busy", arg=ids["G1"], timeout=15_000)
		assert [u.split("/api/")[1] for m, u, b in reqs[n0:]] == ["confirm"]
		assert _grupo_api(url, ids["G1"])["rodado"] is False
		assert not errs, errs
	finally:
		pg.close()


def test_m3_desfazer_tirar_o_grupo_repoe_a_confianca(gr90, browser):
	"""«Tirar o grupo inteiro do lugar» → «Desfazer» manda ``desfaz: true`` e a âncora volta com a mesma meta
	(a_confirmar / programa / discordam), não com o ``confirmado`` por omissão."""
	url, gui, ids = gr90
	g1 = ids["G1"]
	_mostrar(url, ids, "G1")
	assert _post(url, f"/api/grupos/{g1}/mover", {"l0": 2, "c0": 4, "rot": 90, "rodado": False})[0] == 200
	st, d = _post(url, f"/api/grupos/{g1}/fixar", {})
	assert st == 200 and d["confianca"] == "a_confirmar", d
	antes = _ancora(gui, g1)
	pg, errs = _abrir(browser, url, vista=False)
	reqs = _espiar(pg)
	try:
		a = _xy(pg, 2, 4)
		pg.mouse.click(a["x"], a["y"])
		pg.wait_for_selector("#p-tirar", timeout=10_000)
		pg.click("#p-tirar")
		pg.wait_for_selector(f"#lyr-grupos [data-grupo='{g1}']", timeout=15_000)
		pg.wait_for_selector("#b-desfazer-ultimo", timeout=10_000)
		pg.click("#b-desfazer-ultimo")
		pg.wait_for_function("(gid) => !grupo(gid) && !S.busy", arg=g1, timeout=15_000)
		ult = [json.loads(b) for m, u, b in reqs if u.endswith("/api/confirm")][-1]
		assert ult["acao"] == "anchor" and ult["desfaz"] is True
		depois = _ancora(gui, g1)
		for k in ("confianca", "rot_fonte", "vizinhas", "vizinhas_pecas"):
			assert depois.get(k) == antes[k], k
		assert not errs, errs
	finally:
		pg.close()


# ---------------------------------------------------------------- correcoes da revisao da etapa 3 (A1, A1b, M1, M2, M5, B2, B3)
def _fixar_g(pg, gid):
	pg.locator(f"#tab-montar .grp-row[data-grupo='{gid}'] .grp-open").click()
	pg.wait_for_selector("#g-fixar", timeout=10_000)
	pg.click("#g-fixar")
	pg.click("#g-fixar-sim")
	pg.wait_for_selector("#g-fixado", timeout=15_000)
	pg.wait_for_function("!S.busy", timeout=10_000)


def _discorda_g2(url, gui, ids):
	"""G2 em (3,3) rodado 90: a 1.a peca (celula (3,3)) discorda, a 2.a ((4,3)) nao tem vizinhas."""
	_mostrar(url, ids, "G2", [3.0, 3.0])
	assert _post(url, f"/api/grupos/{ids['G2']}/mover", {"l0": 3, "c0": 3, "rot": 90, "rodado": False})[0] == 200


def test_a1_o_desfazer_do_cartao_so_desfaz_o_fixar(gr, browser):
	url, gui, ids = gr
	_mostrar(url, ids, "G1")
	_mostrar(url, ids, "G2", [3.0, 4.0])
	pg, errs = _abrir(browser, url)
	reqs = _espiar(pg)
	try:
		_fixar_g(pg, ids["G1"])
		pg.locator(f"#tab-montar .grp-row[data-grupo='{ids['G2']}'] .grp-open").click()
		pg.wait_for_selector("#g-rodar-dir")
		if _rodar_falha(gui, ids["G2"]) == 90:
			pytest.skip("G2 nao cabe rodado +90 aqui")
		pg.click("#g-rodar-dir")
		pg.wait_for_function("(gid) => grupo(gid).posicao.rot === 90 && !S.busy", arg=ids["G2"], timeout=10_000)
		assert pg.locator("#g-fixado-desfazer").count() == 0             # outra escrita substituiu o desfazer: o cartao ja la nao esta
		assert pg.locator("#g-fixado").count() == 0
		assert ids["G1"] not in _ids_no_grupos(url)                      # G1 continua fixado
		# e mesmo que o cartao ficasse, o botao so aparece se o ultimo desfazer for o do fixar
		pg.evaluate("S.fixado = { gid: %r, n: 1, confianca: 'confirmado', vizinhas: 'confirmam', discordam: [] }; renderMontar()" % ids["G1"])
		assert pg.locator("#g-fixado").count() == 1 and pg.locator("#g-fixado-desfazer").count() == 0
		assert not errs, errs
	finally:
		pg.close()


def test_a1b_desfazer_do_cartao_desligado_com_busy(gr, browser):
	url, gui, ids = gr
	_mostrar(url, ids, "G1")
	pg, errs = _abrir(browser, url)
	try:
		_fixar_g(pg, ids["G1"])
		assert pg.locator("#g-fixado-desfazer").is_enabled()
		pg.evaluate("S.busy = true; renderMontar()")                      # a gravar (o afterWrite do fixar): o clique nao se perde em silencio
		assert pg.locator("#g-fixado-desfazer").is_disabled()
		pg.evaluate("S.busy = false; renderMontar()")
		assert pg.locator("#g-fixado-desfazer").is_enabled()
	finally:
		pg.close()


def test_m1_o_aviso_ambar_so_na_vista_dos_grupos_e_some_se_o_grupo_for_solto(gr90, browser):
	url, gui, ids = gr90
	_mostrar(url, ids, "G1")
	assert _post(url, f"/api/grupos/{ids['G1']}/mover", {"l0": 2, "c0": 4, "rot": 90, "rodado": False})[0] == 200
	pg, errs = _abrir(browser, url)
	try:
		_fixar_g(pg, ids["G1"])
		assert pg.locator("#lyr-grupos .grupo-aviso").count() == 1
		pg.click("#vista-pecas")
		assert pg.locator("#lyr-grupos .grupo-aviso").count() == 0         # na vista «Peca a peca» nao fica contorno nenhum
		pg.click("#vista-grupos")
		assert pg.locator("#lyr-grupos .grupo-aviso").count() == 1
		assert _post(url, "/api/confirm", {"acao": "unanchor", "section": ids["G1"]})[0] == 200      # solto por outro caminho
		pg.wait_for_function("(gid) => !!grupo(gid) && S.fixado === null", arg=ids["G1"], timeout=10_000)
		assert pg.locator("#g-fixado").count() == 0 and pg.locator("#lyr-grupos .grupo-aviso").count() == 0
		assert not errs, errs
	finally:
		pg.close()


def test_m2_ambar_com_outro_traco_etiqueta_e_legenda(gr90, browser):
	url, gui, ids = gr90
	_mostrar(url, ids, "G1")
	assert _post(url, f"/api/grupos/{ids['G1']}/mover", {"l0": 2, "c0": 4, "rot": 90, "rodado": False})[0] == 200
	pg, errs = _abrir(browser, url)
	try:
		assert pg.locator("#legend [data-legend='grupo_aviso']").count() == 0
		_fixar_g(pg, ids["G1"])
		dash = pg.evaluate("getComputedStyle(document.querySelector('#lyr-grupos .grupo-aviso .grupo-cel')).strokeDasharray")
		assert dash not in ("none", "") and dash != "6px, 4px"                # nao e o tracejado do «Lugar provavel»
		assert pg.evaluate("getComputedStyle(document.querySelector('#lyr-grupos .grupo-aviso .grupo-cel')).stroke") != "none"
		assert pg.evaluate("document.querySelector('#lyr-grupos .aviso-tag text').textContent") == "outra rotação"
		assert "diz outra rotação" in pg.inner_text("#legend") or "Peça que diz outra rotação" in pg.inner_text("#legend")
		assert pg.locator("#legend [data-legend='grupo_aviso']").count() == 1
		pg.click("#g-fixado-ok")
		assert pg.locator("#legend [data-legend='grupo_aviso']").count() == 0 and pg.locator("#lyr-grupos .aviso-tag").count() == 0
		assert not errs, errs
	finally:
		pg.close()


def test_m2_etiqueta_escondida_abaixo_do_limiar_de_texto(gr90, browser):
	url, gui, ids = gr90
	_mostrar(url, ids, "G1")
	assert _post(url, f"/api/grupos/{ids['G1']}/mover", {"l0": 2, "c0": 4, "rot": 90, "rodado": False})[0] == 200
	pg, errs = _abrir(browser, url, vp=(390, 844))
	try:
		_fixar_g(pg, ids["G1"])
		pg.evaluate("setView({ x: S.vb.x, y: S.vb.y, w: boardW() * 3 }, true)")      # tudo ao longe: o texto fica abaixo de 9 px
		pg.wait_for_function("document.querySelector('#lyr-grupos .aviso-tag').classList.contains('longe')", timeout=5_000)
		assert pg.evaluate("getComputedStyle(document.querySelector('#lyr-grupos .aviso-tag')).display") == "none"
		pg.evaluate("fitBoard()")
		pg.wait_for_function("!document.querySelector('#lyr-grupos .aviso-tag').classList.contains('longe')", timeout=5_000)
	finally:
		pg.close()


@pytest.mark.parametrize("vp", [(1366, 768), (390, 844)])
def test_m5_rodar_com_texto_e_sem_quebras(gr, browser, vp):
	url, gui, ids = gr
	_mostrar(url, ids, "G1")
	pg, errs = _abrir(browser, url, vp=vp)
	try:
		_escolher(pg)
		assert pg.inner_text("#g-rodar-esq").strip() == "Rodar à esquerda" and pg.inner_text("#g-rodar-dir").strip() == "Rodar à direita"
		for b in ("#g-mover", "#g-rodar-esq", "#g-rodar-dir"):
			assert pg.evaluate("(s) => { const e = document.querySelector(s); return e.scrollWidth <= e.clientWidth + 1; }", b), (vp, b)   # o texto cabe
			assert pg.locator(b).bounding_box()["height"] < 70, (vp, b)                                                               # numa linha
		bb = {b: pg.locator(b).bounding_box() for b in ("#g-mover", "#g-rodar-esq", "#g-rodar-dir")}
		assert bb["#g-rodar-esq"]["y"] == bb["#g-rodar-dir"]["y"] and bb["#g-rodar-esq"]["x"] < bb["#g-rodar-dir"]["x"]   # lado a lado
		assert bb["#g-mover"]["y"] < bb["#g-rodar-esq"]["y"]                                                               # «Mover» na linha de cima
		assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
	finally:
		pg.close()


def test_b2_discordam_sem_celulas_nao_diz_marcada_a_ambar(gr, browser):
	url, gui, ids = gr
	pg, errs = _abrir(browser, url)
	try:
		pg.evaluate("S.fixado = { gid: 'X', n: 1, confianca: 'a_confirmar', vizinhas: 'discordam', discordam: [] }; renderMontar()")
		t = pg.inner_text("#g-fixado")
		assert "As peças ao lado dizem outra rotação." in t and "âmbar" not in t and "Esta peça" not in t
	finally:
		pg.close()


def test_b3_o_409_do_fixar_repoe_o_estado_e_diz_a_frase(gr, browser):
	url, gui, ids = gr
	_mostrar(url, ids, "G1")
	pg, errs = _abrir(browser, url)
	frase = "Não dá para fixar aqui: a linha 2, coluna 4 já tem uma peça. Move o grupo primeiro."
	pg.route("**/api/grupos/*/fixar", lambda r: r.fulfill(status=409, content_type="application/json", body=json.dumps({"error": frase, "motivo": "sobreposto"})))
	try:
		pg.locator("#tab-montar .grp-row").nth(0).locator(".grp-open").click()
		pg.wait_for_selector("#g-fixar", timeout=10_000)
		pg.click("#g-fixar")
		pg.click("#g-fixar-sim")
		pg.wait_for_function("!S.busy && S.pendente === null", timeout=10_000)
		pg.wait_for_selector("#g-aviso", timeout=5_000)
		assert pg.inner_text("#g-aviso") == frase
		assert pg.locator("#g-fixado").count() == 0 and pg.locator("#g-confirma").count() == 0
		assert pg.locator("#g-fixar").is_enabled()
		assert ids["G1"] in _ids_no_grupos(url) and not errs
	finally:
		_fechar(pg.context)


def test_b3_ambar_so_na_celula_da_peca_que_discorda_num_grupo_rodado(gr, browser):
	url, gui, ids = gr
	_discorda_g2(url, gui, ids)
	pg, errs = _abrir(browser, url)
	reqs = _espiar(pg)
	try:
		_fixar_g(pg, ids["G2"])
		cel = pg.locator("#lyr-grupos .grupo-aviso .grupo-cel")
		assert cel.count() == 1                                            # so a peca que discorda: (3,3), nao (4,3)
		hr = pg.evaluate("S.hr")
		assert abs(float(cel.get_attribute("x")) - 2.0) < 1e-3 and abs(float(cel.get_attribute("y")) - 2 * hr) < 1e-3
		assert "Esta peça diz outra rotação" in pg.inner_text("#g-fixado") and "Estas peças" not in pg.inner_text("#g-fixado")
		assert not errs, errs
	finally:
		pg.close()


@pytest.mark.parametrize("vp", [(1366, 768), (390, 844)])
def test_aviso_do_fundo_nao_tapa_a_legenda(gr90, browser, vp):
	"""O aviso do fundo («Grupo de N peça fixado · Desfazer», e os outros) nunca cobre a legenda do tabuleiro, com a
	legenda no estado mais comprido («Peça que diz outra rotação» visível)."""
	url, gui, ids = gr90
	_mostrar(url, ids, "G1")
	assert _post(url, f"/api/grupos/{ids['G1']}/mover", {"l0": 2, "c0": 4, "rot": 90, "rodado": False})[0] == 200
	pg, errs = _abrir(browser, url, vp)
	try:
		_escolher(pg)
		pg.click("#g-fixar")
		pg.click("#g-fixar-sim")
		pg.wait_for_selector("#g-fixado", timeout=15_000)
		pg.wait_for_selector("#legend [data-legend='grupo_aviso']", timeout=10_000)
		pg.evaluate("toast('Um aviso de teste com texto comprido para ocupar largura no fundo do ecrã', true)")
		pg.wait_for_timeout(300)
		cx = pg.evaluate("""(() => { const r = (e) => { const b = e.getBoundingClientRect(); return { x: b.x, y: b.y, w: b.width, h: b.height }; };
			return { leg: r(document.querySelector('#legend')), toasts: [...document.querySelectorAll('#toast > div')].map(r).filter((b) => b.w > 0 && b.h > 0) }; })()""")
		assert cx["toasts"], "sem aviso visível"
		L = cx["leg"]
		assert L["w"] > 0 and L["h"] > 0
		for T in cx["toasts"]:
			livre = T["x"] + T["w"] <= L["x"] or L["x"] + L["w"] <= T["x"] or T["y"] + T["h"] <= L["y"] or L["y"] + L["h"] <= T["y"]
			assert livre, (vp, T, L)
		assert not errs, errs
	finally:
		_fechar(pg.context)


# ---------------------------------------------------------------- F4b (2026-11-24): (a) lugar provavel sozinho, (b) imagem em todos
def _mesa_bytes(gui):
	p = mesa.mesa_path(gui.pr)
	return open(p, "rb").read() if os.path.exists(p) else None


def test_f4b_a_grupo_com_lugar_provavel_aparece_sozinho_sem_escrever(gr, browser):
	"""(a): G1 (candidato (2,4), margem 2,0 >= margin_min) aparece no tabuleiro sem «Mostrar», na posicao e rotacao do
	candidato; G2 (margem 1,0) so na lista. Abrir a pagina nao escreve no mesa.jsonl (bytes iguais)."""
	url, gui, ids = gr
	antes = _mesa_bytes(gui)
	log0 = open(gui.pr.log_path, "rb").read()
	pg, errs = _abrir(browser, url)
	try:
		pg.wait_for_selector(f"#lyr-grupos [data-grupo='{ids['G1']}']", timeout=10_000)
		assert pg.locator("#lyr-grupos [data-grupo]").count() == 1
		assert pg.locator(f"#lyr-grupos [data-grupo='{ids['G2']}']").count() == 0
		p = pg.evaluate("(g) => { const x = grupo(g); return [x.posicao.l0, x.posicao.c0, x.posicao.rot, x.posicao.origem, x.automatico]; }", ids["G1"])
		assert p == [2, 4, 0, "provavel", True]
		assert pg.evaluate("(g) => grupo(g).mostrado", ids["G2"]) is False
		# «Ver no tabuleiro» de um grupo que ja la esta nao escreve
		pg.locator("#tab-montar .grp-row").nth(0).locator(".grp-mostrar").click()
		pg.wait_for_timeout(300)
		assert not errs, errs
	finally:
		pg.close()
	assert _mesa_bytes(gui) == antes == None                                   # nunca escrito
	assert open(gui.pr.log_path, "rb").read() == log0


def test_f4b_a_mesa_existente_fica_igual_e_a_posicao_propria_manda(gr, browser):
	url, gui, ids = gr
	assert _post(url, f"/api/grupos/{ids['G1']}/mover", {"l0": 4, "c0": 6, "rot": 0})[0] == 200
	antes = _mesa_bytes(gui)
	assert antes
	pg, errs = _abrir(browser, url)
	try:
		pg.wait_for_selector(f"#lyr-grupos [data-grupo='{ids['G1']}']", timeout=10_000)
		p = pg.evaluate("(g) => { const x = grupo(g); return [x.posicao.l0, x.posicao.c0, x.posicao.origem, x.automatico]; }", ids["G1"])
		assert p == [4, 6, "mesa", False]                                       # a posicao gravada manda sobre o lugar provavel
		assert not errs, errs
	finally:
		pg.close()
	assert _mesa_bytes(gui) == antes


def test_f4b_a_candidato_invalido_nao_aparece(gr, browser):
	"""Candidato (2,4) com a celula ocupada: o grupo nao aparece sozinho (so na lista)."""
	url, gui, ids = gr
	assert _post(url, "/api/confirm", {"acao": "place", "piece": ids["W"], "cell": [2, 4], "theta_deg": -PSI_W, "origin": "manual"})[0] == 200
	pg, errs = _abrir(browser, url)
	try:
		pg.wait_for_function("!!S.grupos", timeout=10_000)
		assert pg.locator("#lyr-grupos [data-grupo]").count() == 0
		assert pg.evaluate("(g) => grupo(g).mostrado", ids["G1"]) is False
		assert _mesa_bytes(gui) is None
		assert not errs, errs
	finally:
		pg.close()


def test_f4b_a_mover_e_rodar_escrevem_o_fixar_tambem(gr, browser):
	"""So «Mover», «Rodar» ou «Fixar» escrevem: um «Rodar» de um grupo derivado grava a posicao (rodado) no mesa.jsonl."""
	url, gui, ids = gr
	assert _mesa_bytes(gui) is None
	st, r = _post(url, f"/api/grupos/{ids['G1']}/mover", {"rodar": 90})
	assert st == 200, r
	assert r["grupo"]["posicao"]["origem"] == "mesa" and r["grupo"]["posicao"]["rot"] == 90 and r["grupo"]["rodado"] is True
	assert _mesa_bytes(gui)


def test_f4b_b_imagem_em_todos_os_mostrados_so_depois_do_detalhe(gr, browser):
	"""(b): todos os grupos mostrados levam a imagem; nenhum PNG de grupo e pedido antes de o detalhe inicial chegar;
	cada PNG pede-se uma vez."""
	url, gui, ids = gr
	_mostrar(url, ids, "G2")
	pg = browser.new_page(viewport={"width": 1366, "height": 768})
	ev = []
	pg.on("request", lambda r: ev.append(("png", r.url)) if "/api/grupos/" in r.url and ".png" in r.url else None)
	pg.on("requestfinished", lambda r: ev.append(("detalhe", r.url)) if "/api/board.jpg" in r.url and "region=" in r.url else None)
	errs = []
	pg.on("pageerror", lambda e: errs.append(str(e)))
	try:
		pg.goto(url + "/novo/")
		pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
		pg.wait_for_function("document.querySelectorAll('#lyr-grupos image.grupo-img[href]').length === 2", timeout=20_000)
		g1, g2 = ids["G1"], ids["G2"]
		for g in (g1, g2):                                                         # os dois: o derivado e o da mesa
			assert pg.locator(f"#lyr-grupos [data-grupo='{g}'] image.grupo-img[href]").count() == 1
		kinds = [k for k, _ in ev]
		assert "detalhe" in kinds and "png" in kinds
		assert kinds.index("png") > kinds.index("detalhe"), ev                    # nenhum PNG antes do 1.o detalhe
		pngs = [u for k, u in ev if k == "png"]
		assert len(pngs) == len(set(pngs)) == 2, pngs                              # um pedido por grupo
		assert not errs, errs
	finally:
		pg.close()


def test_lupa_peca_num_grupo_abre_o_grupo(gr, browser):
	"""A lupa numa peça de um grupo solto leva ao painel desse grupo, não à interface completa."""
	url, gui, ids = gr
	p = next(p for p in gui.pr.model.pieces.values() if p.estado == "em_seccao")
	pg, errs = _abrir(browser, url, vista=False)
	try:
		pg.evaluate(f"findPiece({p.id!r})")
		pg.wait_for_selector("#lupa-res[data-kind=peca]:not([hidden])", timeout=30_000)
		assert "interface completa" not in pg.inner_text("#lupa-res")
		pg.click("#lupa-ver-grupo")
		assert pg.locator("#lupa-res").is_hidden()
		assert pg.get_attribute("#vista-grupos", "aria-pressed") == "true"
		assert pg.evaluate("S.grupoSel") == p.seccao_id
		assert not errs, errs
	finally:
		pg.close()
