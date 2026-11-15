"""P0 da fase de desempenho (2026-11-15): a vista do Montar só segue o cartão por ação do Tiago.

Antes, qualquer recarga do Montar vinda do servidor (``holes_changed``, ``fetch_changed``, ``board_changed``) levava a
vista de volta ao alvo do cartão e pedia o detalhe na hora, mesmo a meio de um arrasto (a causa de
``test_jump_asks_detail_at_once_drag_and_wheel_keep_debounce`` falhar ao acaso). Decisão do Tiago: quando o cartão
atual muda sozinho a vista não salta; se o alvo novo ficar fora da vista, «localizar» pisca uma vez (marca estática com
``prefers-reduced-motion``). Playwright, ``slow``."""
import json

import pytest

pytestmark = pytest.mark.slow
sync_api = pytest.importorskip("playwright.sync_api")

from test_gui_novo import DETAIL_TIMES, base, browser  # noqa: E402,F401 - fixtures

SHOWN = "S.detailKey && document.body.dataset.detail === S.detailKey"
# o centro da célula dentro da vista (sem a margem de 12 % de ``cellInView``: um salto para um canto do tabuleiro
# sintético 4 × 6 mostra-o inteiro, com o canto dentro da margem)
IN_VB = "((l, c) => { const x = c - 0.5, y = (l - 0.5) * S.hr, v = S.vb; return x > v.x && x < v.x + v.w && y > v.y && y < v.y + v.h; })"


def _open(browser, url, extra=None, **kw):
	pg = browser.new_page(viewport={"width": 1366, "height": 768}, **kw)
	pg.add_init_script(DETAIL_TIMES)
	errs = []
	pg.on("pageerror", lambda e: errs.append(str(e)))
	st = {"extra": extra, "only_extra": False}
	if extra is not None:
		def handle(route):
			# /api/montar com um cartão a mais à frente (``extra``: cópia do cartão real, outra peça e outra célula);
			# ``only_extra``: só ele (o real já foi posto)
			r = route.fetch()
			m = r.json()
			if m.get("itens") and "tpl" not in st:
				st["tpl"] = m["itens"][0]
			if st["extra"] and "tpl" in st:
				fake = dict(st["tpl"], piece="P9999", n_no_lote=99, cell=list(st["extra"]))
				m["itens"] = [fake] if st["only_extra"] else [fake] + m["itens"]
				m["total"] = len(m["itens"])
			route.fulfill(response=r, body=json.dumps(m), headers=dict(r.headers, **{"content-type": "application/json"}))
		pg.route("**/api/montar*", handle)
		st["extra"] = None                         # a 1.ª carga só com o cartão real
	pg.goto(url + "/novo/")
	pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
	pg.wait_for_selector("#b-localizar", timeout=30_000)
	pg.wait_for_function("!!document.body.dataset.raster", timeout=30_000)
	pg.wait_for_timeout(1200)                       # os eventos do arranque acalmam
	return pg, errs, st


def _settle_on(pg, view):
	pg.evaluate(f"setView({json.dumps(view)})")
	pg.wait_for_timeout(450)                        # depois da espera de 280 ms do setView
	pg.wait_for_function(SHOWN, timeout=30_000)
	return pg.evaluate("S.vb"), pg.evaluate("window.__dt.fetch.length")


def _away(pg):
	"""A vista de 2 células à volta da célula mais longe do alvo do cartão (o Tiago olha para outro sítio)."""
	l, c = _far_cell(pg)
	hr = pg.evaluate("S.hr")
	return {"x": c - 1.5, "y": (l - 0.5) * hr - 1, "w": 2}


def _far_cell(pg):
	"""A célula mais longe do alvo atual (grelha sintética 4 × 6)."""
	l, c = pg.evaluate("current().cell")
	rows, cols = pg.evaluate("[S.rows, S.cols]")
	return [rows if l <= rows / 2 else 1, cols if c <= cols / 2 else 1]


@pytest.mark.parametrize("evento", ["holes_changed", "fetch_changed"])
def test_server_reload_without_action_keeps_view_and_asks_nothing(base, browser, evento):
	url, gui, tw = base
	pg, errs, _ = _open(browser, url)
	try:
		vb0, n0 = _settle_on(pg, _away(pg))        # o Tiago olha para outro canto
		gui.emit(evento, {"versao": gui.version()})
		pg.wait_for_timeout(1200)                                  # recarga (350 ms) + composição
		assert pg.evaluate("window.__dt.fetch.length") == n0
		assert pg.evaluate("S.vb") == vb0
		assert pg.locator("#b-localizar[data-mudou]").count() == 0  # o mesmo cartão: nada a avisar
		assert errs == []
	finally:
		pg.close()


def test_reload_during_drag_asks_detail_only_after_the_drag(base, browser):
	url, gui, tw = base
	pg, errs, _ = _open(browser, url)
	try:
		_settle_on(pg, _away(pg))
		bb = pg.locator("#board").bounding_box()
		cy = bb["y"] + bb["height"] / 2
		x0, x1 = bb["x"] + 0.9 * bb["width"], bb["x"] + 0.1 * bb["width"]
		n = pg.evaluate("window.__dt.fetch.length")
		pg.mouse.move(x0, cy)
		pg.mouse.down()
		for i in range(1, 17):
			pg.mouse.move(x0 + (x1 - x0) * i / 16, cy)
			if i == 2:
				gui.emit("holes_changed", {"versao": gui.version()})   # a recarga cai a meio do arrasto
			pg.wait_for_timeout(60)
		assert pg.evaluate("window.__dt.fetch.length") == n
		pg.mouse.up()
		pg.wait_for_function(f"window.__dt.fetch.length > {n}", timeout=5_000)
		d = pg.evaluate(f"window.__dt.fetch[{n}] - window.__dt.move")
		assert d >= 250, d
		assert errs == []
	finally:
		pg.close()


def test_jump_during_a_gesture_waits_for_the_pointer_up(base, browser):
	url, gui, tw = base
	pg, errs, _ = _open(browser, url)
	try:
		_settle_on(pg, _away(pg))
		bb = pg.locator("#board").bounding_box()
		cx, cy = bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2
		pg.mouse.move(cx, cy)
		pg.mouse.down()
		pg.mouse.move(cx - 40, cy)
		n = pg.evaluate("window.__dt.fetch.length")
		vb = pg.evaluate("zoomCells(1, 1, 4, 6, 0.04); S.vb")          # um salto pedido com o dedo em baixo
		assert pg.evaluate("S.saltoPendente") is not None
		assert pg.evaluate("window.__dt.fetch.length") == n and pg.evaluate("S.vb") == vb
		pg.mouse.up()
		assert pg.evaluate("S.saltoPendente") is None and pg.evaluate("S.gesto") is False
		pg.wait_for_function(f"window.__dt.fetch.length > {n} || S.detailKey === null", timeout=5_000)
		assert pg.evaluate("S.vb") != vb                                  # o salto fez-se no fim do gesto
		assert errs == []
	finally:
		pg.close()


def test_saltar_and_encaixa_move_the_view(base, browser):
	url, gui, tw = base
	pg, errs, st = _open(browser, url, extra=True)
	try:
		far = _far_cell(pg)
		st["extra"] = far
		gui.emit("fetch_changed", {})                                    # o cartão a mais aparece à frente
		pg.wait_for_selector("#tab-montar .card[data-piece='P9999']", timeout=10_000)
		# «Saltar» no cartão a mais: o real volta a ser o atual e a vista vai até ele
		_settle_on(pg, {"x": far[1] - 1.5, "y": (far[0] - 1) * pg.evaluate("S.hr"), "w": 1.5})
		pg.click("#b-saltar")
		pg.wait_for_selector(f"#tab-montar .card[data-piece='{tw}']", timeout=10_000)
		l, c = pg.evaluate("current().cell")
		assert pg.evaluate(f"{IN_VB}({l}, {c})")
		# «Encaixa» no real: o seguinte (o a mais, longe) passa a atual e a vista vai até ele
		_settle_on(pg, {"x": c - 1.5, "y": (l - 1) * pg.evaluate("S.hr"), "w": 1.5})
		assert not pg.evaluate(f"cellInView({far[0]}, {far[1]})")
		st["only_extra"] = True
		pg.click("#b-encaixa")
		pg.wait_for_function("!S.busy && current() && current().piece === 'P9999'", timeout=60_000)
		pg.wait_for_timeout(300)
		assert pg.evaluate(f"{IN_VB}({far[0]}, {far[1]})"), pg.evaluate("S.vb")
		assert gui.pr.piece(tw).estado == "colocada"
		assert errs == []
	finally:
		pg.close()


@pytest.mark.parametrize("onde", ["fora", "dentro"])
def test_card_changes_by_itself_localizar_blinks_only_when_target_out_of_view(base, browser, onde):
	url, gui, tw = base
	pg, errs, st = _open(browser, url, extra=True)
	try:
		l, c = pg.evaluate("current().cell")
		hr = pg.evaluate("S.hr")
		if onde == "fora":
			far = _far_cell(pg)
			vb0, n0 = _settle_on(pg, {"x": c - 1.6, "y": (l - 1) * hr - 0.3, "w": 2.2})
			assert not pg.evaluate(f"cellInView({far[0]}, {far[1]})")
			st["extra"] = far
		else:
			vb0, n0 = _settle_on(pg, {"x": -0.5, "y": -0.5, "w": 7})       # o tabuleiro inteiro à vista
			st["extra"] = [l, c + 1 if c < 6 else c - 1]
			assert pg.evaluate(f"cellInView({st['extra'][0]}, {st['extra'][1]})")
		gui.emit("fetch_changed", {})
		pg.wait_for_selector("#tab-montar .card[data-piece='P9999']", timeout=10_000)
		pg.wait_for_timeout(500)
		assert pg.evaluate("S.vb") == vb0                                  # a vista não salta
		assert pg.evaluate("window.__dt.fetch.length") == n0
		loc = pg.locator("#b-localizar")
		if onde == "fora":
			assert loc.get_attribute("data-mudou") == "pisca"
			# pisca uma vez e acaba (a classe sai no fim da animação)
			pg.wait_for_function("!document.querySelector('#b-localizar').classList.contains('pisca')", timeout=5_000)
			loc.click()                                                    # «localizar» leva lá e apaga o aviso
			assert loc.get_attribute("data-mudou") is None
			assert pg.evaluate(f"{IN_VB}({far[0]}, {far[1]})")
		else:
			assert loc.get_attribute("data-mudou") is None
			assert "pisca" not in (loc.get_attribute("class") or "")
		assert errs == []
	finally:
		pg.close()


def test_card_changes_by_itself_reduced_motion_static_mark(base, browser):
	url, gui, tw = base
	pg, errs, st = _open(browser, url, extra=True, reduced_motion="reduce")
	try:
		l, c = pg.evaluate("current().cell")
		far = _far_cell(pg)
		vb0, n0 = _settle_on(pg, {"x": c - 1.6, "y": (l - 1) * pg.evaluate("S.hr") - 0.3, "w": 2.2})
		st["extra"] = far
		gui.emit("fetch_changed", {})
		pg.wait_for_selector("#tab-montar .card[data-piece='P9999']", timeout=10_000)
		pg.wait_for_timeout(500)
		assert pg.evaluate("S.vb") == vb0
		loc = pg.locator("#b-localizar")
		assert loc.get_attribute("data-mudou") == "marca"
		cls = loc.get_attribute("class") or ""
		assert "mudou" in cls and "pisca" not in cls
		assert pg.evaluate("getComputedStyle(document.querySelector('#b-localizar')).animationName") == "none"
		# a marca fica numa recarga do mesmo cartão e sai ao clicar
		gui.emit("holes_changed", {"versao": gui.version()})
		pg.wait_for_timeout(900)
		assert pg.locator("#b-localizar").get_attribute("data-mudou") == "marca"
		pg.locator("#b-localizar").click()
		assert pg.locator("#b-localizar").get_attribute("data-mudou") is None
		assert errs == []
	finally:
		pg.close()


# ---------------------------------------------------------------- P1a: salto da lupa a 390 px com o teclado aberto
def _lupa_pos(pg, txt, kb_h=None):
	pg.click("#lupa-b-pos")
	pg.fill("#lupa-q-pos", txt)
	if kb_h:
		pg.set_viewport_size({"width": 390, "height": kb_h})   # o teclado no ecrã tira ≈ 60 % da altura
		pg.wait_for_timeout(300)
	pg.press("#lupa-q-pos", "Enter")
	pg.wait_for_timeout(600)


def test_lupa_jump_at_390_with_keyboard_ends_around_the_place(base, browser):
	"""P1a (2026-11-15): a 390 × 844, a procura de um lugar com o teclado aberto (390 × 330) e o teclado a fechar a
	seguir deixa a vista à volta do lugar, como sem teclado (antes ficava com a largura no limite, 3 × o tabuleiro)."""
	url, gui, tw = base
	ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=3)
	pg = ctx.new_page()
	errs = []
	pg.on("pageerror", lambda e: errs.append(str(e)))
	try:
		pg.goto(url + "/novo/")
		pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
		pg.wait_for_timeout(1500)
		_lupa_pos(pg, "3 4")                                          # sem teclado: a referência
		w_ref = pg.evaluate("S.vb.w")
		pg.evaluate("setView({ x: 0, y: 0, w: 1.5 })")
		_lupa_pos(pg, "3 4", kb_h=330)
		pg.set_viewport_size({"width": 390, "height": 844})           # o teclado fecha
		pg.wait_for_timeout(800)
		w = pg.evaluate("S.vb.w")
		assert abs(w - w_ref) <= 0.1 * w_ref, (w, w_ref)
		assert pg.evaluate("document.activeElement.tagName") != "INPUT"
		assert errs == []
	finally:
		ctx.close()


# ---------------------------------------------------------------- P1b: a caixa da lupa não abre sozinha
@pytest.mark.parametrize("vw,vh", [(1366, 768), (390, 844)])
@pytest.mark.parametrize("guardado", [None, "pos", "peca"])
def test_lupa_box_never_opens_by_itself(base, browser, vw, vh, guardado):
	"""P1b (2026-11-15, decisões): ao carregar, nenhuma caixa da lupa aberta nem com foco, com e sem o último modo
	guardado (``novo-lupa-modo``), a 1366 e a 390. Já era assim; o teste guarda-o."""
	url, gui, tw = base
	ctx = browser.new_context(viewport={"width": vw, "height": vh}, device_scale_factor=3 if vw < 500 else 1)
	pg = ctx.new_page()
	if guardado:
		pg.add_init_script(f"try {{ localStorage.setItem('novo-lupa-modo', '{guardado}'); }} catch (e) {{}}")
	try:
		pg.goto(url + "/novo/")
		pg.wait_for_selector("body[data-ready='1']", timeout=60_000)
		pg.wait_for_timeout(1500)
		abertas = pg.evaluate("[...document.querySelectorAll('.lupa-caixa')].filter((x) => !x.hidden && x.offsetParent).map((x) => x.id)")
		assert abertas == []
		assert pg.evaluate("(document.activeElement && document.activeElement.tagName) || ''") != "INPUT"
		assert pg.evaluate("S.lupa") is None
		if guardado:
			assert pg.locator(f"#lupa-b-{guardado}.lupa-ult").count() == 1      # o último modo só fica marcado
	finally:
		ctx.close()
