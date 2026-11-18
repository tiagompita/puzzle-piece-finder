"""F2f da GUI nova (decisao do Tiago, 2026-11-18): as sugestoes aparecem sempre no tabuleiro. Escrito ANTES do codigo.

- os alvos de TODAS as entradas da fila ficam desenhados (camada ``#lyr-seguinte``), tambem com outro lugar selecionado ou
  com o painel de um lugar aberto; o do cartao atual fica forte e com rotulo (``#lyr-alvo``), os outros tenues e sem rotulo;
- os tenues desaparecem quando a celula tem menos de ``FRACO_MIN_PX`` (16) px no ecra e nao roubam o toque nesse caso;
- tocar (rato ou toque) num alvo tenue escolhe o cartao, sem contar como toque duplo nem abrir o painel do lugar;
- a selecao de um lugar (``.painel-sel``) fica distinta dos alvos;
- o alvo de um cartao que sai da fila (Encaixa) desaparece e volta com o desfazer, sem recarregar a pagina.

Playwright (Chromium headless, ``slow``) sobre o projeto sintetico de ``tests/test_query.py`` com a grelha real 47 x 64 e
cartoes a mais injetados em ``/api/montar``."""

import json

import pytest

pytestmark = pytest.mark.slow
pytest.importorskip("fastapi")
pytest.importorskip("uvicorn")
sync_api = pytest.importorskip("playwright.sync_api")

from src import server as SV  # noqa: E402
from test_gui_novo import browser, _serve  # noqa: E402,F401
from test_query import _project  # noqa: E402

FRACO_MIN_PX = 16
NEXTS = 5

# px de ecra por celula (a menor das duas escalas) e o centro de uma celula em coordenadas de ecra
PX = "(() => { const r = svgRect(); return Math.min(r.width / S.vb.w, r.height / S.vb.h); })()"
XY = """(([l, c]) => { const p = svg().createSVGPoint(); p.x = c - 0.5; p.y = (l - 0.5) * S.hr;
  const q = p.matrixTransform(svg().getScreenCTM()); return [q.x, q.y]; })"""


@pytest.fixture
def fila(tmp_path, monkeypatch):
	"""Grelha 47 x 64, um cartao real «coloca agora» (vizinha marcada) e ``NEXTS`` cartoes a mais injetados no browser."""
	import synth
	from src.query import run_query, load_fetch
	orig = synth.profile
	monkeypatch.setattr(synth, "profile", lambda rows=4, cols=6, **k: orig(rows=47, cols=64, **k))
	pr, placed, tw, dec = _project(tmp_path)
	run_query(pr, use_image=False)
	cell = [e for e in load_fetch(pr)["entries"] if e.get("piece")][0]["cell"]
	nb = [n for n in pr.board.neighbours(tuple(cell)) if pr.board[n]["estado"] == "vazia"][0]
	pr.mark_cell_full(nb)
	pr.save()
	gui = SV.Gui(pr.path, prepare=False, use_image=False, uploads=str(tmp_path / "uploads"), log=None)
	url, server, th = _serve(gui)
	l0, c0 = cell
	extra = [[l0, c0 - 3], [l0 - 2, c0 - 5], [l0 - 2, c0 - 1], [l0 - 3, c0 - 7], [l0 - 1, c0 - 9]][:NEXTS]
	yield url, gui, tw, cell, extra
	server.should_exit = True
	th.join(10)


def _abrir(browser, url, extra, vp=(1366, 768), touch=False):
	ctx = browser.new_context(viewport={"width": vp[0], "height": vp[1]}, has_touch=touch)
	pg = ctx.new_page()
	errs = []
	pg.on("pageerror", lambda e: errs.append(str(e)))

	tpl = {}

	def handle(route):
		r = route.fetch()
		m = r.json()
		if m.get("itens") and not tpl:
			tpl.update(m["itens"][0])                      # o modelo fica: depois do Encaixa a fila real fica vazia
		if tpl:
			for i, ce in enumerate(extra):
				m["itens"].append(dict(tpl, piece=f"P90{i:02d}", n_no_lote=90 + i, cell=list(ce)))
			m["total"] = len(m["itens"])
		route.fulfill(response=r, body=json.dumps(m), headers=dict(r.headers, **{"content-type": "application/json"}))
	pg.route("**/api/montar*", handle)
	pg.goto(url + "/novo/")
	pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
	pg.wait_for_selector("#tab-montar .card[data-piece]", timeout=60_000)
	pg.wait_for_function("S.vb.w < 30", timeout=10_000)
	pg.wait_for_timeout(500)
	return ctx, pg, errs


def _perto(pg, cell):
	l, c = cell
	pg.evaluate(f"zoomCells({l - 5}, {c - 10}, {l}, {c + 2}, 0.04)")
	pg.wait_for_timeout(500)
	assert pg.evaluate(PX) >= FRACO_MIN_PX


def _fracos(pg):
	return pg.locator("#lyr-seguinte rect.b-seguinte")


def test_alvos_de_todos_os_cartoes_com_outro_lugar_selecionado(fila, browser):
	url, gui, tw, cell, extra = fila
	ctx, pg, errs = _abrir(browser, url, extra)
	try:
		_perto(pg, cell)
		assert _fracos(pg).count() == NEXTS                                   # todos, nao so 3
		assert {_fracos(pg).nth(i).get_attribute("data-piece") for i in range(NEXTS)} == {f"P90{i:02d}" for i in range(NEXTS)}
		l, c = cell
		pg.evaluate(f"openPainel({l - 1}, {c - 3})")                           # outro lugar selecionado, painel aberto
		pg.wait_for_selector("#painel[data-kind]:not([data-kind='a_carregar'])", timeout=20_000)
		assert pg.evaluate("S.modo") == "painel"
		assert _fracos(pg).count() == NEXTS                                   # continuam desenhados
		assert pg.locator("#lyr-alvo rect.b-alvo").count() == 1               # o do cartao atual tambem
		assert pg.locator("#lyr-alvo rect.painel-sel").count() == 1
		for i in range(NEXTS):
			assert _fracos(pg).nth(i).is_visible()
		assert not errs, errs
	finally:
		ctx.close()


def test_atual_forte_com_rotulo_e_outros_tenues_sem_rotulo(fila, browser):
	url, gui, tw, cell, extra = fila
	ctx, pg, errs = _abrir(browser, url, extra)
	try:
		_perto(pg, cell)
		assert pg.locator("#lyr-alvo .alvo-tag").is_visible()
		assert pg.locator("#lyr-seguinte .alvo-tag").count() == 0 and pg.locator("#lyr-seguinte text").count() == 0
		st = pg.evaluate("""(() => { const f = (e) => { const s = getComputedStyle(e); return { w: parseFloat(s.strokeWidth), stroke: s.stroke }; };
			return { forte: f(document.querySelector('#lyr-alvo rect.b-alvo')), tenue: f(document.querySelector('#lyr-seguinte rect.b-seguinte')) }; })()""")
		alfa = lambda cor: float(cor.split(",")[3].strip(" )")) if cor.count(",") == 3 else 1.0
		assert st["forte"]["w"] > st["tenue"]["w"], st
		assert alfa(st["forte"]["stroke"]) > alfa(st["tenue"]["stroke"]), st
		assert not errs, errs
	finally:
		ctx.close()


@pytest.mark.parametrize("vp", [(1366, 768), (390, 844)])
def test_limiar_de_zoom_esconde_os_tenues_e_nao_roubam_o_toque(fila, browser, vp):
	url, gui, tw, cell, extra = fila
	ctx, pg, errs = _abrir(browser, url, extra, vp)
	try:
		_perto(pg, cell)
		assert pg.locator("#lyr-seguinte").get_attribute("data-celula-px") is not None
		assert float(pg.locator("#lyr-seguinte").get_attribute("data-celula-px")) >= FRACO_MIN_PX
		pg.click("#z-fit")
		pg.wait_for_function("S.vb.w >= 60", timeout=10_000)
		pg.wait_for_timeout(300)
		px_inteiro = pg.evaluate(PX)
		assert px_inteiro < FRACO_MIN_PX, px_inteiro                          # o tabuleiro inteiro fica abaixo do limiar
		for i in range(NEXTS):
			assert not _fracos(pg).nth(i).is_visible()
		assert pg.locator("#lyr-alvo rect.b-alvo").is_visible()               # o do cartao atual fica sempre
		# escondido: tocar no sitio do alvo nao escolhe o cartao (abre o painel do lugar)
		x, y = pg.evaluate(XY + "(" + json.dumps(extra[0]) + ")")
		pg.mouse.click(x, y)
		pg.wait_for_timeout(300)
		assert pg.evaluate("S.pick") in (None, tw) and pg.evaluate("S.modo") == "painel"
		print(f"\n[F2f limiar] {vp}: inteiro {px_inteiro:.1f} px/celula, limiar {FRACO_MIN_PX}")
		assert not errs, errs
	finally:
		ctx.close()


def test_clique_num_alvo_tenue_escolhe_o_cartao(fila, browser):
	url, gui, tw, cell, extra = fila
	ctx, pg, errs = _abrir(browser, url, extra)
	try:
		_perto(pg, cell)
		x, y = pg.evaluate(XY + "(" + json.dumps(extra[1]) + ")")
		pg.mouse.click(x, y)
		pg.wait_for_selector("#tab-montar .card[data-piece='P9001']", timeout=10_000)
		assert pg.evaluate("S.modo") == "cartao" and pg.evaluate("current().piece") == "P9001"
		assert pg.locator("#lyr-seguinte rect.b-seguinte[data-piece='P9001']").count() == 0     # agora e o forte
		assert pg.locator(f"#lyr-seguinte rect.b-seguinte[data-piece='{tw}']").count() == 1     # o de antes passou a tenue
		assert not errs, errs
	finally:
		ctx.close()


def test_toque_num_alvo_tenue_escolhe_o_cartao_sem_toque_duplo_nem_painel(fila, browser):
	url, gui, tw, cell, extra = fila
	ctx, pg, errs = _abrir(browser, url, extra, touch=True)
	try:
		_perto(pg, cell)
		l, c = cell
		pg.evaluate(f"openPainel({l - 1}, {c - 3})")                           # um lugar selecionado: o toque tira-o
		pg.wait_for_selector("#painel[data-kind]:not([data-kind='a_carregar'])", timeout=20_000)
		w0 = pg.evaluate("S.vb.w")
		x, y = pg.evaluate(XY + "(" + json.dumps(extra[2]) + ")")
		pg.touchscreen.tap(x, y)
		pg.wait_for_selector("#tab-montar .card[data-piece='P9002']", timeout=10_000)   # depois da espera de 250 ms
		assert pg.evaluate("S.modo") == "cartao"
		pg.wait_for_timeout(500)
		assert pg.evaluate("S.vb.w") >= w0 * 0.99                              # nao aproximou (nao foi toque duplo)
		assert pg.locator("#lyr-alvo rect.painel-sel").count() == 0            # nem abriu o painel do lugar
		assert not errs, errs
	finally:
		ctx.close()


def test_alvo_sai_com_encaixa_e_volta_com_o_desfazer(fila, browser):
	url, gui, tw, cell, extra = fila
	ctx, pg, errs = _abrir(browser, url, extra)
	try:
		_perto(pg, cell)
		assert pg.locator("#lyr-alvo rect.b-alvo").count() == 1 and _fracos(pg).count() == NEXTS
		pg.click("#b-encaixa")
		pg.wait_for_function(f"!S.busy && current() && current().piece !== '{tw}'", timeout=60_000)
		pg.wait_for_timeout(400)
		assert pg.locator(f"#lyr-seguinte rect[data-piece='{tw}']").count() == 0            # a peca colocada saiu
		assert pg.locator("#lyr-alvo rect.b-alvo").count() == 1
		assert _fracos(pg).count() == NEXTS - 1                                  # o primeiro a mais e agora o atual
		pg.click("#b-desfazer-ultimo")
		pg.wait_for_function(f"current() && current().piece === '{tw}'", timeout=60_000)
		pg.wait_for_timeout(400)
		assert _fracos(pg).count() == NEXTS
		assert pg.locator(f"#lyr-seguinte rect[data-piece='{tw}']").count() == 0            # e o atual outra vez, forte
		assert not errs, errs
	finally:
		ctx.close()


# ---------------------------------------------------------------------------------------------------------------
# F2f, limiar RELATIVO ao zoom (2026-11-18, orientador): os tenues escondem-se enquanto o zoom <= FRACO_ZOOM_REL (1,3) x o
# zoom de «caber tudo» (o do botao «z-fit»); o toque usa o mesmo criterio. Escritos ANTES do codigo.
FRACO_ZOOM_REL = 1.3


def _inteiro(pg):
	pg.click("#z-fit")
	pg.wait_for_function("S.vb.w >= 60", timeout=10_000)
	pg.wait_for_timeout(300)
	return pg.evaluate(PX)


def _ampliar(pg, cell, fator, base):
	"""Poe a vista a ``fator`` x o zoom de caber tudo (``base`` px/celula), centrada na celula."""
	l, c = cell
	pg.evaluate(f"""(() => {{ const r = svgRect(); const w = r.width / ({base} * {fator});
		setView({{ x: {c - 0.5} - w / 2, y: ({l} - 0.5) * S.hr - w * (r.height / r.width) / 2, w }}); }})()""")
	pg.wait_for_timeout(500)


@pytest.mark.parametrize("vp", [(1366, 768), (1920, 1080)])
def test_relativo_vista_inteira_sem_tenues(fila, browser, vp):
	url, gui, tw, cell, extra = fila
	ctx, pg, errs = _abrir(browser, url, extra, vp)
	try:
		px = _inteiro(pg)
		print(f"\n[F2f relativo] {vp}: inteiro {px:.1f} px/celula")
		for i in range(NEXTS):
			assert not _fracos(pg).nth(i).is_visible(), (vp, px)
		assert not errs, errs
	finally:
		ctx.close()


@pytest.mark.parametrize("vp", [(1366, 768), (1920, 1080)])
def test_relativo_a_1_5_vezes_o_zoom_de_caber_tudo_os_tenues_aparecem(fila, browser, vp):
	url, gui, tw, cell, extra = fila
	ctx, pg, errs = _abrir(browser, url, extra, vp)
	try:
		base = _inteiro(pg)
		_ampliar(pg, cell, 1.5, base)
		assert pg.evaluate(PX) >= base * 1.45
		for i in range(NEXTS):
			assert _fracos(pg).nth(i).is_visible(), (vp, base)
		_ampliar(pg, cell, 1.2, base)                                            # abaixo de 1,3 x: escondidos
		for i in range(NEXTS):
			assert not _fracos(pg).nth(i).is_visible(), (vp, base)
		assert not errs, errs
	finally:
		ctx.close()


def test_vista_inteira_toque_no_alvo_do_cartao_atual_centra_e_pisca_sem_abrir_o_painel(fila, browser):
	"""Pergunta 4 (documenta o comportamento ATUAL, nao o muda): com os tenues escondidos (vista inteira), tocar no alvo
	FORTE do cartao atual mantem o comportamento da F2d (centra, «localizar» pisca, sem painel do lugar)."""
	url, gui, tw, cell, extra = fila
	ctx, pg, errs = _abrir(browser, url, extra)
	try:
		_inteiro(pg)
		assert pg.evaluate("S.modo") == "cartao" and pg.evaluate("current().piece") == tw
		w0 = pg.evaluate("S.vb.w")
		x, y = pg.evaluate(XY + "(" + json.dumps(cell) + ")")
		pg.mouse.click(x, y)
		pg.wait_for_timeout(600)
		assert pg.evaluate("S.modo") == "cartao" and pg.evaluate("current().piece") == tw   # nao foi para o lugar
		assert pg.locator("#lyr-alvo rect.painel-sel").count() == 0
		assert pg.evaluate("S.painel") in (None, False)
		assert pg.evaluate("S.vb.w") < w0 * 0.9                                   # centrou (aproximou)
		assert pg.locator("#b-localizar").get_attribute("data-mudou") in ("pisca", "marca")
		assert not errs, errs
	finally:
		ctx.close()
