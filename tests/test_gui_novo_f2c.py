"""F2c da GUI nova (teste do Tiago de 2026-11-16), escrito ANTES do código:

1. o rótulo do alvo («vai aqui» / «lugar provável») esconde-se quando o texto fica abaixo de 9 px no ecrã;
2. a pesquisa é um grupo «Procurar» com o ícone lupa e as opções Peça | Lugar («Posição» passa a «Lugar»);
3. tocar no alvo do cartão ATUAL não abre o painel do lugar (centra e faz piscar «localizar»); o cartão ganha «Ver lugar»;
4. o botão do menu (três barras) abre o menu no lugar do painel e fecha-o com o estado do separador intacto;
5. os erros do browser (``/`` e ``/novo/``, via core.js) chegam ao registo de atividade (``POST /api/cliente/erro``).

Browser (Chromium headless, ``slow``) sobre o projeto sintético de ``tests/test_query.py``; o endpoint também com TestClient.
"""

import json
import re
import time

import pytest

pytestmark = pytest.mark.slow
pytest.importorskip("fastapi")
pytest.importorskip("uvicorn")
pytest.importorskip("httpx")
sync_api = pytest.importorskip("playwright.sync_api")

from fastapi.testclient import TestClient  # noqa: E402

from src import activity as A  # noqa: E402
from src import server as SV  # noqa: E402
from test_gui_novo import base, guarda, browser, _open_any, _serve  # noqa: E402,F401
from test_query import _project  # noqa: E402

LIMIAR_PX = 9                 # abaixo desta altura de texto no ecrã o rótulo do alvo esconde-se
VP_PC, VP_TEL = (1366, 768), (390, 844)

# altura do texto do rótulo no ecrã = tamanho da fonte (unidades da viewBox) x px de ecrã por unidade da viewBox
TAG = """(() => { const g = document.querySelector('#lyr-alvo .alvo-tag'); if (!g) return null;
  const t = g.querySelector('text'), r = document.querySelector('#board').getBoundingClientRect();
  const px = parseFloat(getComputedStyle(t).fontSize) * r.width / S.vb.w;
  const b = g.getBoundingClientRect();
  return { px, visivel: b.width > 0 && b.height > 0 && getComputedStyle(g).display !== 'none', texto: t.textContent, dpx: g.dataset.px || null }; })()"""


@pytest.fixture
def grande(tmp_path, monkeypatch):
	"""Como ``guarda`` (um só cartão, «lugar provável»), mas com a grelha real 47 × 64: na grelha 4 × 6 do projeto sintético
	«ver o tabuleiro inteiro» dá > 150 px por célula e o rótulo nunca ficaria pequeno."""
	import synth
	from src.query import run_query
	orig = synth.profile
	monkeypatch.setattr(synth, "profile", lambda rows=4, cols=6, **k: orig(rows=47, cols=64, **k))
	pr, placed, tw, dec = _project(tmp_path)
	run_query(pr, use_image=False)
	gui = SV.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp_path / "uploads"), log=None)
	url, server, th = _serve(gui)
	yield url, gui, tw, dec
	server.should_exit = True
	th.join(10)


def _open_vp(browser, url, vp, **kw):
	pg = browser.new_page(viewport={"width": vp[0], "height": vp[1]}, **kw)
	errs = []
	pg.on("pageerror", lambda e: errs.append(str(e)))
	pg.goto(url + "/novo/")
	pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
	pg.wait_for_selector("#tab-montar .card[data-piece]", timeout=60_000)
	pg.wait_for_function("S.vb.w < 30", timeout=10_000)          # a vista já seguiu o alvo do cartão
	pg.wait_for_timeout(300)
	return pg, errs


def _tag(pg):
	pg.wait_for_timeout(150)         # o observador da vista corre depois do setView
	return pg.evaluate(TAG)


# ---------------------------------------------------------------- 1. rótulo do alvo
def test_alvo_tag_visible_at_card_zoom_desktop(grande, browser):
	"""No zoom do cartão (1366 × 768) o texto tem mais de 9 px: o rótulo está à vista com o texto."""
	url, gui, tw, dec = grande
	pg, errs = _open_vp(browser, url, VP_PC)
	try:
		t = _tag(pg)
		assert t and t["visivel"] and t["texto"] == "lugar provável", t
		assert t["px"] >= LIMIAR_PX, t
		assert pg.locator("#lyr-alvo .alvo-tag").is_visible()
		assert not errs, errs
	finally:
		pg.close()


@pytest.mark.parametrize("vp", [VP_PC, VP_TEL])
def test_alvo_tag_hides_below_nine_px_and_follows_zoom(grande, browser, vp):
	"""Com «ver o tabuleiro inteiro» o texto fica abaixo de 9 px e o rótulo desaparece (fica só o quadrado); ao aproximar
	volta, e volta a esconder-se ao afastar (atualiza quando o zoom muda). A 390 px o zoom do cartão já dá < 9 px."""
	url, gui, tw, dec = grande
	pg, errs = _open_vp(browser, url, vp)
	try:
		l, c = pg.evaluate("current().cell")
		card = _tag(pg)
		assert (card["px"] >= LIMIAR_PX) == (card["visivel"]), card              # o critério é a altura do texto
		if vp == VP_PC:
			assert card["visivel"], card
		pg.evaluate(f"zoomCells({l} - 2, {c} - 3, {l} + 2, {c} + 3, 0.04)")        # bem perto: o texto lê-se
		perto = _tag(pg)
		assert perto["px"] >= LIMIAR_PX and perto["visivel"], perto
		assert pg.locator("#lyr-alvo .alvo-tag").is_visible()
		pg.click("#z-fit")
		pg.wait_for_function("S.vb.w >= 60", timeout=10_000)
		longe = _tag(pg)
		assert longe["px"] < LIMIAR_PX and not longe["visivel"], longe
		assert not pg.locator("#lyr-alvo .alvo-tag").is_visible()
		assert pg.locator("#lyr-alvo rect.b-alvo-tracejado").count() == 1          # o quadrado fica
		assert pg.locator("#lyr-alvo rect.b-alvo-tracejado").is_visible()
		print(f"\n[F2c rotulo] {vp}: cartao {card['px']:.1f} px, perto {perto['px']:.1f} px, inteiro {longe['px']:.1f} px (limiar {LIMIAR_PX})")
		assert not errs, errs
	finally:
		pg.close()


# ---------------------------------------------------------------- 2. grupo «Procurar»: Peça | Lugar
@pytest.mark.parametrize("vp", [VP_PC, VP_TEL])
def test_search_group_procurar_peca_lugar(base, browser, vp):
	url, gui, tw = base
	pg, errs = _open_any(browser, url, *vp)
	try:
		grupo = pg.locator("#search [role=group]")
		assert grupo.count() == 1 and grupo.get_attribute("aria-label") == "Procurar"
		assert grupo.locator(".i-search").count() >= 1                                  # o ícone lupa
		assert pg.locator("#lupa-b-peca").inner_text().strip() == "Peça"
		assert pg.locator("#lupa-b-pos").inner_text().strip() == "Lugar"
		textos = pg.evaluate("""(() => { const r = document.querySelector('#search');
			return [...r.querySelectorAll('*'), r].flatMap((e) => ['aria-label', 'placeholder', 'title'].map((a) => e.getAttribute(a)))
				.filter(Boolean).concat([r.innerText]).join(' | '); })()""")
		assert not re.search(r"posi[çc][ãa]o", textos, re.I), textos
		assert "lugar" in textos.lower()
		if vp == VP_TEL:                                                                 # só o ícone, o nome fica no aria-label
			assert not any(w == "Procurar" for w in pg.locator("#search").inner_text().split())
		# os ids e a lupa ficam iguais: cada botão abre a sua caixa
		pg.click("#lupa-b-pos")
		assert pg.locator("#lupa-c-pos").is_visible() and not pg.locator("#lupa-c-peca").is_visible()
		pg.click("#lupa-b-peca")
		assert pg.locator("#lupa-c-peca").is_visible()
		for sel in ("#lupa-b-peca", "#lupa-b-pos"):
			bb = pg.locator(sel).bounding_box()
			assert bb and bb["height"] >= 44 - 0.5 and bb["x"] >= 0 and bb["x"] + bb["width"] <= vp[0] + 0.5, (sel, bb)
		assert not pg.evaluate("document.documentElement.scrollWidth > window.innerWidth")
		assert not errs, errs
	finally:
		pg.close()


# ---------------------------------------------------------------- 3. tocar no alvo do cartão atual
def test_tap_on_current_target_recentres_and_blinks_localizar(guarda, browser):
	"""Tocar no alvo do cartão atual mantém o cartão, não abre o painel do lugar, centra o lugar e pisca «localizar» uma vez."""
	url, gui, tw, dec = guarda
	pg, errs = _open_vp(browser, url, VP_PC)
	try:
		l, c = pg.evaluate("current().cell")
		pg.evaluate("document.querySelector('#tab-montar .card').dataset.marca = '1'")
		pg.evaluate("setView({ x: S.cols + 5, y: 0, w: 2, h: 1.5 })")                  # o Tiago deslocou-se para longe do alvo
		assert not pg.evaluate(f"cellInView({l}, {c})")
		piscou = pg.evaluate(f"(() => {{ S.onBoardTap({l}, {c}); return document.querySelector('#b-localizar').classList.contains('pisca'); }})()")
		assert piscou
		assert pg.locator("#painel").count() == 0 and pg.evaluate("S.modo") == "cartao"
		card = pg.locator("#tab-montar .card")
		assert card.get_attribute("data-piece") == tw and card.get_attribute("data-marca") == "1"      # o mesmo cartão, não redesenhado
		assert pg.evaluate(f"cellInView({l}, {c})")                                      # centrou o lugar
		assert pg.locator("#b-localizar").get_attribute("data-mudou") == "pisca"
		pg.wait_for_function("!document.querySelector('#b-localizar').classList.contains('pisca')", timeout=5_000)   # uma vez só
		assert not errs, errs
	finally:
		pg.close()


def test_tap_on_current_target_reduced_motion_leaves_static_mark(guarda, browser):
	url, gui, tw, dec = guarda
	pg, errs = _open_vp(browser, url, VP_PC, reduced_motion="reduce")
	try:
		l, c = pg.evaluate("current().cell")
		pg.evaluate(f"S.onBoardTap({l}, {c})")
		assert pg.locator("#painel").count() == 0
		b = pg.locator("#b-localizar")
		assert b.get_attribute("data-mudou") == "marca" and "mudou" in (b.get_attribute("class") or "")
		assert "pisca" not in (b.get_attribute("class") or "")
		assert not errs, errs
	finally:
		pg.close()


def test_ver_lugar_button_opens_the_place_panel(guarda, browser):
	"""O cartão ganha «Ver lugar» (ícone map-pin) que abre o painel do lugar do alvo atual; tocar noutro lugar também."""
	url, gui, tw, dec = guarda
	pg, errs = _open_vp(browser, url, VP_PC)
	try:
		l, c = pg.evaluate("current().cell")
		b = pg.locator("#tab-montar .card #b-ver-lugar")
		assert b.count() == 1 and b.inner_text().strip() == "Ver lugar" and b.locator(".ico.i-map-pin").count() == 1
		bb = b.bounding_box()
		assert bb and bb["height"] >= 44 - 0.5
		b.click()
		pg.wait_for_selector("#painel", timeout=20_000)
		assert pg.evaluate("S.modo") == "painel" and pg.evaluate("S.painel.cell") == [l, c]
		pg.click("#p-voltar")
		pg.wait_for_selector("#tab-montar .card #b-ver-lugar", timeout=20_000)
		pg.evaluate(f"S.onBoardTap({l} + 1, {c})")                                       # outro lugar: abre o painel desse lugar
		pg.wait_for_selector("#painel", timeout=20_000)
		assert pg.evaluate("S.painel.cell") == [l + 1, c]
		assert not errs, errs
	finally:
		pg.close()


# ---------------------------------------------------------------- 4. menu como painel
MENU_IDS = ("m-definicoes", "m-fantasmas", "m-borda", "m-guardadas", "m-atividade", "m-diag")


def _menu_open(pg):
	return pg.locator("#menu").is_visible()


def test_menu_button_icon_and_open_close_same_button(base, browser):
	url, gui, tw = base
	pg, errs = _open_any(browser, url)
	try:
		btn = pg.locator("#menu-btn")
		assert btn.get_attribute("aria-label") == "Menu" and btn.locator(".ico.i-menu").count() == 1
		assert btn.locator(".i-ellipsis").count() == 0
		assert not _menu_open(pg) and btn.get_attribute("aria-expanded") == "false"
		btn.click()
		assert _menu_open(pg) and btn.get_attribute("aria-expanded") == "true"
		for i in MENU_IDS:                                                                # o conteúdo de hoje, os mesmos ids
			assert pg.locator(f"#menu #{i}").count() == 1, i
		assert pg.locator("#menu #m-teclas").count() == 1
		btn.click()
		assert not _menu_open(pg) and btn.get_attribute("aria-expanded") == "false"
		btn.click()
		pg.keyboard.press("Escape")                                                       # Esc fecha
		assert not _menu_open(pg) and btn.get_attribute("aria-expanded") == "false"
		btn.click()
		pg.click("#m-definicoes")                                                         # compatível com os testes existentes
		pg.wait_for_selector("#definicoes", timeout=5_000)
		assert not errs, errs
	finally:
		pg.close()


def test_menu_has_the_size_of_the_panel_on_desktop(base, browser):
	url, gui, tw = base
	pg, errs = _open_any(browser, url, *VP_PC)
	try:
		pg.click("#menu-btn")
		pg.wait_for_timeout(300)
		m, p = pg.locator("#menu").bounding_box(), pg.locator("#panel").bounding_box()
		assert abs(m["width"] - p["width"]) <= 1.5 and abs(m["height"] - p["height"]) <= 1.5, (m, p)
		assert abs(m["x"] - p["x"]) <= 1.5 and abs(m["y"] - p["y"]) <= 1.5, (m, p)
		assert not pg.locator("#tab-montar").is_visible()                                 # esconde o separador, não o desenha por cima
		assert not errs, errs
	finally:
		pg.close()


def test_menu_fills_the_phone_screen_with_fechar(base, browser):
	url, gui, tw = base
	pg, errs = _open_any(browser, url, *VP_TEL)
	try:
		pg.click("#menu-btn")
		pg.wait_for_timeout(300)
		m = pg.locator("#menu").bounding_box()
		assert m["x"] <= 0.5 and m["y"] <= 0.5 and m["width"] >= VP_TEL[0] - 1 and m["height"] >= VP_TEL[1] - 1, m
		f = pg.locator("#menu #menu-fechar")
		assert f.is_visible() and f.get_attribute("aria-label") == "Fechar" and f.locator(".ico.i-x").count() == 1   # F2e: só o ícone X (antes o texto «Fechar»)
		bb = f.bounding_box()
		assert bb["height"] >= 44 - 0.5 and bb["x"] >= 0 and bb["x"] + bb["width"] <= VP_TEL[0] + 0.5
		assert not pg.evaluate("document.documentElement.scrollWidth > window.innerWidth")
		f.click()
		assert not _menu_open(pg) and pg.get_attribute("#menu-btn", "aria-expanded") == "false"
		assert not errs, errs
	finally:
		pg.close()


# a 390 px o menu ocupa o ecrã inteiro e tapa o botão: fecha-se por Esc ou «Fechar» (o botão só fecha a 1366)
@pytest.mark.parametrize("vp,maneira", [(VP_PC, "botao"), (VP_PC, "esc"), (VP_PC, "fechar"), (VP_TEL, "esc"), (VP_TEL, "fechar")])
def test_menu_close_keeps_the_card_and_the_undo_strip(base, browser, vp, maneira):
	"""Com o cartão X atual e a faixa «Desfazer» à vista, abrir e fechar o menu (pelo botão, por Esc ou por «Fechar») deixa
	lá o mesmo cartão e o «Desfazer», sem os redesenhar e sem mudar ``S.pick`` / ``S.modo``. A faixa é posta em ``S.undo``
	(nenhum projeto de teste tem um cartão e uma ação real desfazível ao mesmo tempo); o desenho é o mesmo caminho."""
	url, gui, tw = base
	pg, errs = _open_vp(browser, url, vp)
	try:
		pg.evaluate("S.undo = { tipo: 'saltar', msg: 'Teste F2c: ação que se pode desfazer' }; renderMontar()")
		pg.wait_for_selector("#m-ultimo #b-desfazer-ultimo", timeout=5_000)
		x = pg.locator("#tab-montar .card").get_attribute("data-piece")
		pg.evaluate("document.querySelector('#tab-montar .card').dataset.marca = '1'; document.querySelector('#m-ultimo').dataset.marca = '1'")
		antes = pg.evaluate("[S.pick, S.modo, S.tab]")
		pg.click("#menu-btn")
		assert _menu_open(pg) and not pg.locator("#tab-montar").is_visible()
		if maneira == "botao":
			pg.click("#menu-btn")
		elif maneira == "esc":
			pg.keyboard.press("Escape")
		else:
			pg.click("#menu-fechar")
		assert not _menu_open(pg)
		assert pg.locator("#tab-montar").is_visible()
		card = pg.locator("#tab-montar .card")
		assert card.get_attribute("data-piece") == x and card.get_attribute("data-marca") == "1"
		assert pg.locator("#m-ultimo").get_attribute("data-marca") == "1" and pg.locator("#b-desfazer-ultimo").is_visible()
		assert pg.evaluate("[S.pick, S.modo, S.tab]") == antes
		assert not errs, errs
	finally:
		pg.close()


# ---------------------------------------------------------------- 5. erros do browser → atividade
@pytest.fixture
def cli(tmp_path):
	"""Servidor com o registo de atividade ligado (anel + ficheiro do dia) e TestClient."""
	pr, placed, tw, dec = _project(tmp_path)
	ring = A.RingHandler()
	gui = SV.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp_path / "uploads"), ring=ring, queue=False)
	gui.activity_setup(console=False, file=True)
	yield gui, TestClient(SV.create_app(gui)), ring
	A.teardown()


def _linhas(ring):
	return [r for r in ring.last() if r["tipo"] == "erro_cliente"]


def test_erro_cliente_is_an_activity_type():
	assert "erro_cliente" in A.TIPOS


def test_endpoint_writes_one_activity_line_and_the_daily_file(cli):
	gui, client, ring = cli
	corpo = {"tipo": "error", "mensagem": "Uncaught Error: teste-f2c", "fonte": "http://h/novo/novo.js:12:34",
			 "stack": "Error: teste-f2c\n    at f (novo.js:12:34)", "pagina": "/novo/", "ua": "UA-de-teste/1.0"}
	r = client.post("/api/cliente/erro", content=json.dumps(corpo), headers={"Content-Type": "text/plain;charset=UTF-8"})   # sendBeacon
	assert r.status_code in (200, 204), r.text
	ls = _linhas(ring)
	assert len(ls) == 1 and ls[0]["nivel"] == "aviso"
	m = ls[0]["msg"]
	assert "teste-f2c" in m and "novo.js:12:34" in m and "/novo/" in m and "UA-de-teste/1.0" in m and "\n" not in m, m
	d = client.get("/api/atividade").json()
	assert "erro_cliente" in d["tipos"] and any(x["tipo"] == "erro_cliente" for x in d["linhas"])
	with open(d["ficheiro"], encoding="utf-8") as f:
		assert any("erro_cliente" in ln and "teste-f2c" in ln for ln in f.read().splitlines())


def test_endpoint_cuts_the_body_at_4_kb(cli):
	gui, client, ring = cli
	grande = {"tipo": "error", "mensagem": "m" * 20_000, "fonte": "f" * 5000, "stack": "s" * 50_000, "pagina": "/", "ua": "u" * 9000}
	assert client.post("/api/cliente/erro", content=json.dumps(grande)).status_code in (200, 204)
	assert client.post("/api/cliente/erro", content="x" * 100_000).status_code in (200, 204)       # nem JSON é
	ls = _linhas(ring)
	assert len(ls) == 2
	for r in ls:
		assert len(r["msg"].encode("utf-8")) <= 4096, len(r["msg"])
	assert client.post("/api/cliente/erro", content="").status_code == 400                         # vazio: sem linha
	assert len(_linhas(ring)) == 2


def test_endpoint_rate_limit_per_client(cli):
	gui, client, ring = cli
	codes = [client.post("/api/cliente/erro", content=json.dumps({"tipo": "error", "mensagem": f"e{i}", "pagina": "/"})).status_code
			 for i in range(30)]
	assert len(_linhas(ring)) == 20, len(_linhas(ring))                                            # 20 por minuto por cliente
	assert codes[:20] == [codes[0]] * 20 and codes[0] in (200, 204) and set(codes[20:]) == {429}, codes


@pytest.fixture
def act(tmp_path):
	"""Servidor real (uvicorn) com atividade ligada, para o browser."""
	pr, placed, tw, dec = _project(tmp_path)
	ring = A.RingHandler()
	gui = SV.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp_path / "uploads"), ring=ring, queue=False)
	gui.activity_setup(console=False, file=True)
	url, server, th = _serve(gui)
	yield url, gui, ring
	server.should_exit = True
	th.join(10)
	A.teardown()


def _esperar(ring, n, tmax=8.0):
	t0 = time.time()
	while len(_linhas(ring)) < n and time.time() - t0 < tmax:
		time.sleep(0.1)


@pytest.mark.parametrize("pagina", ["/", "/novo/"])
def test_browser_errors_reach_the_activity_log_once_per_minute(act, browser, pagina):
	"""Um ``throw`` num temporizador, um ``Promise.reject`` e um ``console.error`` chegam como linhas ``erro_cliente``
	(``/`` e ``/novo/``); o 2.º erro igual dentro de 1 minuto não é enviado; o ``console.error`` original continua a correr."""
	url, gui, ring = act
	pg = browser.new_page(viewport={"width": 1366, "height": 768})
	consola = []
	pg.on("console", lambda m: consola.append(m.text))
	pg.on("pageerror", lambda e: None)               # os erros são de propósito
	try:
		pg.goto(url + pagina)
		pg.wait_for_load_state("load")
		pg.wait_for_timeout(800)
		n0 = len(_linhas(ring))
		pg.evaluate("""() => {
			for (let i = 0; i < 2; i++) setTimeout(() => { throw new Error('teste-f2c-erro'); }, 0);
			for (let i = 0; i < 2; i++) Promise.reject(new Error('teste-f2c-rej'));
			for (let i = 0; i < 2; i++) console.error('teste-f2c-consola', 7);
		}""")
		_esperar(ring, n0 + 3)
		pg.wait_for_timeout(1200)                       # tempo para uma 2.ª cópia, se houvesse
		novas = [r["msg"] for r in _linhas(ring)[n0:]]
		for chave in ("teste-f2c-erro", "teste-f2c-rej", "teste-f2c-consola"):
			assert sum(chave in m for m in novas) == 1, (chave, novas)
		assert len(novas) == 3, novas
		assert all(pagina in m for m in novas), novas   # location.pathname
		assert any("Mozilla" in m or "Chrome" in m for m in novas), novas
		assert sum("teste-f2c-consola" in t for t in consola) == 2          # o original continua a ser chamado
		# um erro diferente passa
		pg.evaluate("() => setTimeout(() => { throw new Error('teste-f2c-outro'); }, 0)")
		_esperar(ring, n0 + 4)
		assert sum("teste-f2c-outro" in r["msg"] for r in _linhas(ring)) == 1
		with open(gui._activity_file(), encoding="utf-8") as f:
			assert "erro_cliente" in f.read()
	finally:
		pg.close()


def test_error_hook_does_not_loop_when_sending_fails(act, browser):
	"""Um erro dentro do próprio envio (beacon e fetch a falhar) não volta a ser enviado nem rebenta a página."""
	url, gui, ring = act
	pg = browser.new_page(viewport={"width": 1366, "height": 768})
	vistos = []
	pg.on("pageerror", lambda e: vistos.append(str(e)))
	pg.on("console", lambda m: vistos.append(m.text))
	try:
		pg.goto(url + "/novo/")
		pg.wait_for_load_state("load")
		pg.wait_for_timeout(500)
		pg.evaluate("""() => {
			navigator.sendBeacon = () => { throw new Error('envio-quebrado-beacon'); };
			window.fetch = () => Promise.reject(new Error('envio-quebrado-fetch'));
			setTimeout(() => { throw new Error('teste-f2c-original'); }, 0);
		}""")
		pg.wait_for_timeout(1500)
		assert sum("teste-f2c-original" in v for v in vistos) == 1, vistos
		assert not any("envio-quebrado" in v for v in vistos), vistos        # o erro do envio não sai para a página
		assert pg.evaluate("1 + 1") == 2                                       # a página continua viva
		assert not any("teste-f2c-original" in r["msg"] for r in _linhas(ring))
	finally:
		pg.close()
